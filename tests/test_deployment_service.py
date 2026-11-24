"""Интеграционные тесты пайплайна деплоя (services/deployment.py).

ansible-runner подменён моком (tests/mocks/ansible_runner.py), поэтому
плейбук реально не запускается, но весь остальной путь — валидация,
генерация inventory, маппинг хостов, стриминг логов Ansible в SSE,
обработка ошибок — выполняется как в проде.
"""

import io
import os
import tarfile
import time

import pytest

from mocks import ansible_runner as mock_ar
from services.deployment import DeploymentService
from sse.broadcaster import SSEBroadcaster


def make_tar_bytes():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        info = tarfile.TarInfo("config.json")
        payload = b"{}"
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    return buf.getvalue()


@pytest.fixture
def uploaded_files(tmp_path):
    """Файлы на «сервере приложений» — как после save_temp_file."""
    ssh_key = tmp_path / "ssh_key_x_id"
    ssh_key.write_text(
        "-----BEGIN OPENSSH PRIVATE KEY-----\nAAAA\n"
        "-----END OPENSSH PRIVATE KEY-----\n"
    )
    image = tmp_path / "docker_image_x.tar"
    image.write_bytes(make_tar_bytes())
    return {"ssh_key": str(ssh_key), "docker_image": str(image)}


@pytest.fixture
def successful_runner():
    mock_ar.set_run_result(
        mock_ar.MockRunnerResult(
            status="successful",
            stats={},
        )
    )
    return mock_ar


def stats_for(hostnames, kind="ok"):
    return {kind: {h: {} for h in hostnames}, "processed": {h: {} for h in hostnames}}


class TestHappyPath:
    def test_successful_deployment_single_server(
        self, valid_form_data, uploaded_files
    ):
        service = DeploymentService("hp-single")
        try:
            mock_ar.set_run_result(mock_ar.MockRunnerResult(status="successful"))
            result = service.execute(valid_form_data, dict(uploaded_files))
            assert service.status == "success"
            assert result["success"] is True
            assert len(service.servers) == 1
            assert service.servers[0]["host"] == "192.168.1.10"
            assert service.servers[0]["status"] == "skipped"  # нет статистики ok
        finally:
            SSEBroadcaster.cleanup_session("hp-single")

    def test_two_servers_deployed_in_one_playbook(
        self, multi_server_form_data, uploaded_files
    ):
        """Мульти-машины: один запуск ansible-runner со всеми хостами в inventory."""
        service = DeploymentService("hp-multi")
        try:
            mock_ar.set_run_result(mock_ar.MockRunnerResult(status="successful"))
            result = service.execute(multi_server_form_data, dict(uploaded_files))
            assert service.status == "success", result
            assert len(service.servers) == 2
            assert len(mock_ar.calls) == 1
            kwargs = mock_ar.calls[0].kwargs
            inventory_content = open(kwargs["inventory"]).read()
            assert "ansible_host=192.168.1.10" in inventory_content
            assert "ansible_host=192.168.1.11" in inventory_content
            assert kwargs["forks"] >= 1  # параллельная настройка машин
        finally:
            SSEBroadcaster.cleanup_session("hp-multi")

    def test_extra_vars_passed_to_ansible(
        self, valid_form_data, uploaded_files
    ):
        valid_form_data["app_deploy_cpus"] = ["2"]
        valid_form_data["app_deploy_memory"] = ["512M"]
        valid_form_data["enable_selinux"] = "on"
        service = DeploymentService("ev-1")
        try:
            mock_ar.set_run_result(mock_ar.MockRunnerResult(status="successful"))
            service.execute(valid_form_data, dict(uploaded_files))
            extravars = mock_ar.calls[0].kwargs["extravars"]
            assert extravars["app_deploy_image_name"] == "myapp:latest"
            assert extravars["app_deploy_ports"] == ["8080:80"]
            assert extravars["app_deploy_cpus"] == "2"
            assert extravars["app_deploy_memory"] == "512M"
            assert extravars["selinux_configuration_state"] == "enforcing"
            assert extravars["app_deploy_image_source"] == "tar"
        finally:
            SSEBroadcaster.cleanup_session("ev-1")

    def test_registry_mode_derives_registry_from_image_name(
        self, valid_form_data, uploaded_files
    ):
        valid_form_data["image_source"] = ["registry"]
        valid_form_data["app_deploy_image_name"] = [
            "registry.example.com/team/myapp:1.2"
        ]
        service = DeploymentService("reg-1")
        try:
            mock_ar.set_run_result(mock_ar.MockRunnerResult(status="successful"))
            service.execute(valid_form_data, dict(uploaded_files))
            extravars = mock_ar.calls[0].kwargs["extravars"]
            assert extravars["app_deploy_registry"] == "registry.example.com"
            assert extravars["app_deploy_image_source"] == "registry"
        finally:
            SSEBroadcaster.cleanup_session("reg-1")

    def test_dockerhub_default_registry(self, valid_form_data, uploaded_files):
        valid_form_data["image_source"] = ["registry"]
        service = DeploymentService("reg-2")
        try:
            mock_ar.set_run_result(mock_ar.MockRunnerResult(status="successful"))
            service.execute(valid_form_data, dict(uploaded_files))
            extravars = mock_ar.calls[0].kwargs["extravars"]
            assert "index.docker.io" in extravars["app_deploy_registry"]
        finally:
            SSEBroadcaster.cleanup_session("reg-2")


class TestValidationFailure:
    def test_invalid_form_stops_before_ansible(
        self, valid_form_data, uploaded_files
    ):
        valid_form_data["app_host_port"] = ["99999"]
        service = DeploymentService("vf-1")
        try:
            result = service.execute(valid_form_data, dict(uploaded_files))
            assert service.status == "error"
            assert result["error"] == "Validation failed"
            assert mock_ar.calls == []  # ansible не запускался
        finally:
            SSEBroadcaster.cleanup_session("vf-1")

    def test_no_server_in_form(self, valid_form_data, uploaded_files):
        del valid_form_data["ansible_host"]
        del valid_form_data["ansible_user"]
        service = DeploymentService("vf-2")
        try:
            result = service.execute(valid_form_data, dict(uploaded_files))
            assert service.status == "error"
            assert any("Сервер" in e or "сервера" in e for e in result["details"])
        finally:
            SSEBroadcaster.cleanup_session("vf-2")


class TestAnsibleFailure:
    def test_playbook_failure_sets_error_status(self, valid_form_data, uploaded_files):
        service = DeploymentService("af-1")
        try:
            mock_ar.set_run_result(
                mock_ar.MockRunnerResult(
                    status="failed",
                    stats={"failures": {"server_1_x": {}}},
                )
            )
            result = service.execute(valid_form_data, dict(uploaded_files))
            assert service.status == "error"
            assert result["error"] == "Ansible playbook failed"
            assert "servers" in result
        finally:
            SSEBroadcaster.cleanup_session("af-1")

    def test_unreachable_host_marked_in_servers(
        self, multi_server_form_data, uploaded_files, monkeypatch
    ):
        service = DeploymentService("af-2")
        try:
            # имя хоста узнаем из inventory-вызова: server_2_<uid>
            def run_with_stats(**kwargs):
                hostnames = []
                content = open(kwargs["inventory"]).read()
                for line in content.splitlines():
                    if line and not line.startswith("["):
                        hostnames.append(line.split()[0])
                mock_ar.set_run_result(
                    mock_ar.MockRunnerResult(
                        status="failed",
                        stats={"dark": {hostnames[1]: {}}},
                    )
                )
                mock_ar.calls.append(mock_ar.RunCall(kwargs=kwargs))
                return mock_ar._make_result()

            import libs.ansible as ansible_lib

            monkeypatch.setattr(ansible_lib.ansible_runner, "run", run_with_stats)
            service.execute(multi_server_form_data, dict(uploaded_files))

            statuses = {s["host"]: s["status"] for s in service.servers}
            assert statuses["192.168.1.11"] == "unreachable"
        finally:
            SSEBroadcaster.cleanup_session("af-2")


class TestAnsibleLiveStreaming:
    """Новая фича: живой вывод Ansible транслируется в SSE построчно."""

    def test_host_events_stream_stdout_lines(
        self, valid_form_data, uploaded_files, monkeypatch
    ):
        service = DeploymentService("ls-1")
        try:
            hostname = None

            def capture_inventory_and_emit(**kwargs):
                nonlocal hostname
                content = open(kwargs["inventory"]).read()
                hostname = [
                    l.split()[0]
                    for l in content.splitlines()
                    if l and not l.startswith("[")
                ][0]
                handler = kwargs.get("event_handler")
                if handler:
                    handler(
                        {
                            "event": "runner_on_ok",
                            "event_data": {
                                "runner": {"host": hostname},
                                "stdout": "TASK [Deploy container] ****\nchanged: [server]",
                            },
                        }
                    )
                    handler(
                        {
                            "event": "playbook_on_start",
                            "event_data": {"stdout": "PLAY [Configure servers]"},
                        }
                    )
                return mock_ar.MockRunnerResult(status="successful")

            import libs.ansible as ansible_lib

            monkeypatch.setattr(
                ansible_lib.ansible_runner, "run", capture_inventory_and_emit
            )
            service.execute(valid_form_data, dict(uploaded_files))

            events = SSEBroadcaster.get_events("ls-1")
            ansible_events = [e for e in events if e["source"] == "ansible"]
            messages = "\n".join(e["message"] for e in ansible_events)
            # реальные строки вывода ansible, а не служебные метки
            assert "TASK [Deploy container]" in messages
            assert "PLAY [Configure servers]" in messages
            # внутренние имена хостов заменены на публичный IP
            assert "192.168.1.10" in messages
            assert hostname not in messages
            # событие привязано к серверу (метка для фильтра по машинам)
            host_tagged = [
                e for e in ansible_events if e["details"].get("host") == "192.168.1.10"
            ]
            assert host_tagged
        finally:
            SSEBroadcaster.cleanup_session("ls-1")


class TestCleanupAndSafety:
    def test_temp_files_removed_after_execution(
        self, valid_form_data, uploaded_files
    ):
        service = DeploymentService("cl-1")
        paths = dict(uploaded_files)
        try:
            mock_ar.set_run_result(mock_ar.MockRunnerResult(status="successful"))
            service.execute(valid_form_data, paths)
            assert not os.path.exists(paths["ssh_key"])
            assert not os.path.exists(paths["docker_image"])
        finally:
            SSEBroadcaster.cleanup_session("cl-1")

    def test_unexpected_exception_does_not_crash(
        self, valid_form_data, uploaded_files, monkeypatch
    ):
        service = DeploymentService("ex-1")
        try:
            monkeypatch.setattr(
                "services.deployment.validate_all_data",
                lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
            )
            result = service.execute(valid_form_data, dict(uploaded_files))
            assert service.status == "error"
            assert "Unexpected error" in result["error"]
        finally:
            SSEBroadcaster.cleanup_session("ex-1")


class TestTelegramChatIdExtraction:
    def test_extract_scalar(self):
        assert DeploymentService._extract_telegram_chat_id(
            {"telegram_chat_id": "42"}
        ) == "42"

    def test_extract_from_list(self):
        assert DeploymentService._extract_telegram_chat_id(
            {"telegram_chat_id": ["-100123"]}
        ) == "-100123"

    def test_extract_empty(self):
        assert DeploymentService._extract_telegram_chat_id({}) is None
        assert DeploymentService._extract_telegram_chat_id(
            {"telegram_chat_id": "  "}
        ) is None
