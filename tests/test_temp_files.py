"""Тесты работы с временными файлами (libs/temp_files.py)."""

import glob
import os
import stat
import tempfile

from libs.temp_files import (
    cleanup_specific_files,
    create_inventory_temp_file,
    save_temp_file,
)


class FakeFileStorage:
    """Минимальная замена werkzeug FileStorage для тестов."""

    def __init__(self, filename: str, content: bytes = b"data"):
        self.filename = filename
        self._content = content

    def save(self, path):
        with open(path, "wb") as f:
            f.write(self._content)


class TestSaveTempFile:
    def test_saves_content_and_returns_path(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
        path = save_temp_file(FakeFileStorage("my key.pem"), "ssh_key_")
        assert os.path.exists(path)
        with open(path, "rb") as f:
            assert f.read() == b"data"

    def test_filename_is_secure_and_prefixed(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
        path = save_temp_file(
            FakeFileStorage("../../etc/passwd"), "ssh_key_"
        )
        name = os.path.basename(path)
        assert name.startswith("ssh_key_")
        assert ".." not in name and "/" not in name.replace(os.sep, "")

    def test_permissions_are_600(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
        path = save_temp_file(FakeFileStorage("key.pem"), "ssh_key_")
        mode = stat.S_IMODE(os.stat(path).st_mode)
        assert mode == 0o600

    def test_unique_names_for_same_filename(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
        p1 = save_temp_file(FakeFileStorage("a.txt"), "x_")
        p2 = save_temp_file(FakeFileStorage("a.txt"), "x_")
        assert p1 != p2


class TestCreateInventory:
    SERVERS = [
        {"host": "10.0.0.1", "port": 22, "user": "ubuntu"},
        {"host": "10.0.0.2", "port": 2222, "user": "root"},
    ]

    def test_inventory_contains_all_servers(self):
        path, hostnames = create_inventory_temp_file(self.SERVERS, "/tmp/key.pem")
        try:
            content = open(path).read()
            assert content.startswith("[server]")
            assert "ansible_host=10.0.0.1" in content
            assert "ansible_port=2222" in content
            assert "ansible_ssh_private_key_file=/tmp/key.pem" in content
            assert len(hostnames) == 2
            # имена хостов уникальны и детерминированы по индексу
            assert hostnames[0].startswith("server_1_")
            assert hostnames[1].startswith("server_2_")
        finally:
            os.remove(path)

    def test_single_server_backcompat(self):
        path, hostnames = create_inventory_temp_file(
            [self.SERVERS[0]], "/tmp/key.pem"
        )
        try:
            assert len(hostnames) == 1
        finally:
            os.remove(path)


class TestCleanup:
    def test_cleanup_specific_files_removes_existing_and_ignores_missing(self, tmp_path):
        f = tmp_path / "gone"
        f.write_text("x")
        cleanup_specific_files({"a": str(f), "b": None, "c": str(tmp_path / "nope")})
        assert not f.exists()

    def test_cleanup_temp_files_removes_prefixes(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
        stale = tmp_path / "ssh_key_deadbeef_id.pem"
        stale.write_text("x")
        other = tmp_path / "unrelated.txt"
        other.write_text("keep")
        from libs.temp_files import cleanup_temp_files

        cleanup_temp_files()
        assert not stale.exists()
        assert other.exists()
