"""Тесты обёрток над внешними сканерами (Trivy / Hadolint).

Реальные бинарники не вызываются: мокается subprocess.run.
"""

import json

import pytest

from libs import hadolint as hadolint_mod
from libs import trivy as trivy_mod
from libs.hadolint import format_hadolint_result, scan_dockerfile
from libs.scanner_base import run_binary_scanner
from libs.trivy import format_trivy_result, scan_image, scan_image_by_name


class FakeCompleted:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


TRIVY_JSON_OK = {
    "Results": [
        {
            "Vulnerabilities": [
                {"Severity": "CRITICAL", "VulnerabilityID": "CVE-1"},
                {"Severity": "HIGH", "VulnerabilityID": "CVE-2"},
                {"Severity": "LOW", "VulnerabilityID": "CVE-3"},
            ]
        }
    ]
}

TRIVY_JSON_CLEAN = {"Results": [{"Vulnerabilities": []}]}


@pytest.fixture
def mock_subprocess(monkeypatch):
    """Подменяет subprocess.run в scanner_base; возвращает (setup, calls)."""
    calls = []

    def setup(stdout="", stderr="", exc=None):
        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if exc:
                raise exc
            return FakeCompleted(stdout=stdout, stderr=stderr)

        monkeypatch.setattr("libs.scanner_base.subprocess.run", fake_run)

    return setup, calls


class TestRunBinaryScanner:
    def test_json_parsed(self, mock_subprocess):
        setup, calls = mock_subprocess(stdout=json.dumps({"a": 1}))
        ok, out, err = run_binary_scanner("tool", ["--json"])
        assert ok is True
        assert out == {"a": 1}
        assert calls[0] == ["tool", "--json"]

    def test_invalid_json_fails_gracefully(self, mock_subprocess):
        setup, _ = mock_subprocess(stdout="not json {{{")
        ok, out, err = run_binary_scanner("tool", [])
        assert ok is False
        assert "Failed to parse JSON" in err

    def test_binary_not_found(self, monkeypatch):
        import subprocess as sp

        def raise_fnf(cmd, **kwargs):
            raise FileNotFoundError()

        monkeypatch.setattr("libs.scanner_base.subprocess.run", raise_fnf)
        ok, out, err = run_binary_scanner("/usr/bin/nope", [])
        assert ok is False
        assert "Binary not found" in err


class TestTrivyScanImage:
    def test_counts_and_blocking_high(self, mock_subprocess):
        setup, calls = mock_subprocess(stdout=json.dumps(TRIVY_JSON_OK))
        result = scan_image("/tmp/image.tar", fail_on_severity="HIGH")
        assert result["success"] is True
        assert result["blocked"] is True
        assert result["blocking_count"] == 2  # CRITICAL + HIGH
        assert result["severity_counts"]["LOW"] == 1
        assert "--input" in calls[0] and "/tmp/image.tar" in calls[0]

    def test_clean_image_not_blocked(self, mock_subprocess):
        setup, calls = mock_subprocess(stdout=json.dumps(TRIVY_JSON_CLEAN))
        result = scan_image("/tmp/image.tar", fail_on_severity="CRITICAL")
        assert result["blocked"] is False
        assert result["blocking_count"] == 0

    def test_none_threshold_never_blocks(self, mock_subprocess):
        setup, calls = mock_subprocess(stdout=json.dumps(TRIVY_JSON_OK))
        result = scan_image("/tmp/i.tar", fail_on_severity="NONE")
        assert result["blocked"] is False

    def test_low_would_block_high_only_when_threshold_low(self, mock_subprocess):
        only_low = {"Results": [{"Vulnerabilities": [{"Severity": "LOW"}]}]}
        setup, calls = mock_subprocess(stdout=json.dumps(only_low))
        assert scan_image("/tmp/i.tar", fail_on_severity="HIGH")["blocked"] is False
        assert scan_image("/tmp/i.tar", fail_on_severity="LOW")["blocked"] is True

    def test_scanner_failure_returns_error(self, mock_subprocess):
        setup, calls = mock_subprocess(exc=FileNotFoundError())
        result = scan_image("/tmp/i.tar")
        assert result["success"] is False
        assert result["blocked"] is False
        assert "Binary not found" in result["error"]

    def test_registry_scan_passes_credentials(self, mock_subprocess):
        setup, calls = mock_subprocess(stdout=json.dumps(TRIVY_JSON_CLEAN))
        result = scan_image_by_name(
            "registry.example.com/myapp:1.0",
            fail_on_severity="HIGH",
            username="user",
            password="token",
        )
        assert result["success"] is True
        cmd = calls[-1]
        assert "registry.example.com/myapp:1.0" in cmd
        assert "--username" in cmd and "user" in cmd
        assert "--password" in cmd and "token" in cmd

    def test_registry_scan_without_credentials(self, mock_subprocess):
        setup, calls = mock_subprocess(stdout=json.dumps(TRIVY_JSON_CLEAN))
        scan_image_by_name("myapp:latest")
        cmd = calls[-1]
        assert "--username" not in cmd and "--password" not in cmd


class TestFormatTrivyResult:
    def test_no_vulnerabilities_message(self):
        assert "не обнаружены" in format_trivy_result([])

    def test_lists_cves(self):
        text = format_trivy_result(TRIVY_JSON_OK["Results"][0]["Vulnerabilities"])
        assert "CVE-1" in text
        assert "CRITICAL" in text

    def test_accepts_full_dict(self):
        text = format_trivy_result(TRIVY_JSON_OK)
        assert "CVE-1" in text


class TestHadolint:
    def test_scan_success_splits_errors(self, mock_subprocess):
        issues = [
            {"level": "warning", "code": "DL3008", "message": "pin versions"},
            {"level": "error", "code": "DL3006", "message": "missing tag"},
        ]
        setup, calls = mock_subprocess(stdout=json.dumps(issues))
        result = scan_dockerfile("/tmp/Dockerfile")
        assert result["success"] is True
        assert len(result["issues"]) == 2
        assert [e["code"] for e in result["errors"]] == ["DL3006"]

    def test_scan_binary_missing(self, mock_subprocess):
        setup, calls = mock_subprocess(exc=FileNotFoundError())
        result = scan_dockerfile("/tmp/Dockerfile")
        assert result["success"] is False
        assert result["issues"] == []

    def test_format_empty(self):
        assert "проблем не обнаружено" in format_hadolint_result([])

    def test_format_groups_levels(self):
        issues = [
            {"level": "error", "code": "DL1", "file": "Dockerfile", "line": 1,
             "column": 1, "message": "bad"},
            {"level": "info", "code": "DL2", "file": "Dockerfile", "line": 2,
             "column": 1, "message": "meh"},
        ]
        code, text = format_hadolint_result(issues)
        assert "ERROR (1)" in text
        assert "INFO (1)" in text
        assert "DL1" in text and "bad" in text
