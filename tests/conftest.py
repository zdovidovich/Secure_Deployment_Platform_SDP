"""
Общая конфигурация pytest для проекта SDP.

Чтобы тесты можно было запускать без установленных ansible-runner и
python-telegram-bot (тяжёлые/сетевые зависимости), в ``sys.modules``
подставляются моки из ``tests/mocks`` — но только если настоящие пакеты
не установлены. Если они установлены, используются настоящие.
"""

import os
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).parent
PROJECT_ROOT = TESTS_DIR.parent
APP_DIR = PROJECT_ROOT / "app"
MOCKS_DIR = TESTS_DIR / "mocks"

# tests/ в sys.path, чтобы пакеты mocks и сами тесты импортировались стабильно
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

# Код приложения использует плоские импорты (from libs..., from services...),
# поэтому app/ должен быть в sys.path — так же, как при запуске app/app.py.
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


def _install_mock_if_missing(module_name: str, mock_path: str):
    try:
        __import__(module_name)
    except ImportError:
        if str(MOCKS_DIR) not in sys.path:
            sys.path.insert(0, str(MOCKS_DIR))
        import importlib

        importlib.import_module(mock_path)
        sys.modules[module_name] = sys.modules[mock_path]


_install_mock_if_missing("ansible_runner", "mocks.ansible_runner")
_install_mock_if_missing("telegram", "mocks.telegram")

from mocks import ansible_runner as ansible_runner_mock  # noqa: E402


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    """Изоляция каждого теста: чистим env и мок ansible-runner."""
    for var in ("SDP_API_KEY", "TELEGRAM_BOT_TOKEN", "TRIVY_PATH", "HADOLINT_PATH"):
        monkeypatch.delenv(var, raising=False)
    ansible_runner_mock.reset()
    yield
    ansible_runner_mock.reset()


@pytest.fixture
def valid_form_data():
    """Корректные данные формы деплоя (один сервер, tar-образ)."""
    return {
        "image_source": ["tar"],
        "ansible_host": ["192.168.1.10"],
        "ansible_port": ["22"],
        "ansible_user": ["ubuntu"],
        "app_deploy_image_name": ["myapp:latest"],
        "app_deploy_container_name": ["myapp"],
        "app_host_port": ["8080"],
        "app_container_port": ["80"],
    }


@pytest.fixture
def multi_server_form_data(valid_form_data):
    """Форма с двумя серверами (новая фича мульти-машины)."""
    data = dict(valid_form_data)
    data["ansible_host"] = ["192.168.1.10", "192.168.1.11"]
    data["ansible_port"] = ["22", "2222"]
    data["ansible_user"] = ["ubuntu", "root"]
    return data


@pytest.fixture
def ssh_key_file(tmp_path):
    """Файл, проходящий валидацию приватного SSH-ключа."""
    path = tmp_path / "id_test"
    path.write_text(
        "-----BEGIN OPENSSH PRIVATE KEY-----\n"
        "b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMgAAA\n"
        "-----END OPENSSH PRIVATE KEY-----\n"
    )
    return str(path)


@pytest.fixture
def docker_tar_file(tmp_path):
    """Настоящий tar-архив (проходит validate_tar_archive)."""
    import tarfile

    path = tmp_path / "image.tar"
    with tarfile.open(path, "w") as tar:
        info = tarfile.TarInfo(name="config.json")
        payload = b'{"architecture": "amd64"}'
        info.size = len(payload)
        import io

        tar.addfile(info, io.BytesIO(payload))
    return str(path)


@pytest.fixture
def flask_client():
    """TestClient приложения Flask (без реальных зависимостей)."""
    from app import app as flask_app

    flask_app.config["TESTING"] = True
    with flask_app.test_client() as client:
        yield client
