import os
import tempfile
import uuid
from werkzeug.utils import secure_filename
import glob
from libs.ansible import get_base_dir_ansible


def get_base_dir():
    return os.path.dirname(os.path.abspath(__file__))


def save_temp_file(file_obj, prefix="upload_"):
    """
    Сохраняет загруженный файл во временную папку с уникальным именем.
    Возвращает путь к файлу.
    """
    original_filename = secure_filename(file_obj.filename)

    unique_name = f"{prefix}{uuid.uuid4().hex}_{original_filename}"

    temp_dir = tempfile.gettempdir()

    file_path = os.path.join(temp_dir, unique_name)

    file_obj.save(file_path)

    os.chmod(file_path, 0o600)

    return file_path


def create_inventory_temp_file(servers: list, ssh_key_path) -> str:
    """
    Создаёт временный inventory файл для Ansible со списком серверов.

    Args:
        servers: Список словарей с параметрами подключения
                 [{'host': '1.2.3.4', 'port': 22, 'user': 'ubuntu'}, ...]
        ssh_key_path: Путь к приватному SSH-ключу

    Returns:
        (path_to_inventory, hostnames) — путь к файлу и список имён хостов
        (для обратной совместимости можно использовать только [0]).
    """
    name = uuid.uuid4().hex[:8]
    unique_name = f"inventory_{name}"

    inventory_dir = os.path.join(get_base_dir_ansible(), "inventory")

    os.makedirs(inventory_dir, exist_ok=True)

    file_path = os.path.join(inventory_dir, unique_name)

    hostnames = []

    with open(file_path, "w") as f:
        f.write("[server]\n")
        for i, server in enumerate(servers):
            hostname = f"server_{i + 1}_{name}"
            hostnames.append(hostname)
            f.write(
                f"{hostname} "
                f"ansible_host={server['host']} "
                f"ansible_port={server['port']} "
                f"ansible_user={server['user']} "
                f"ansible_ssh_private_key_file={ssh_key_path}\n"
            )

    os.chmod(file_path, 0o600)

    return file_path, hostnames


def cleanup_temp_files(
    prefixes=("ssh_key_", "docker_image_", "dockerfile_", "inventory_"),
):
    temp_dir = tempfile.gettempdir()
    for prefix in prefixes:
        for file_path in glob.glob(os.path.join(temp_dir, f"{prefix}*")):
            try:
                os.remove(file_path)
            except OSError:
                pass
    for file_path in glob.glob(
        os.path.join(os.path.join(get_base_dir_ansible(), "inventory"), "inventory_*")
    ):
        try:
            os.remove(file_path)
        except OSError:
            pass


def cleanup_specific_files(file_paths: dict):
    for file_path in file_paths.values():
        if not file_path:
            continue
        try:
            os.remove(file_path)
        except OSError:
            pass
