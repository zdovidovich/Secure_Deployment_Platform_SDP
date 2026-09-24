import re
from typing import Dict, Any, List, Tuple, Optional
import tarfile


class ValidationRule:
    """Класс правила валидации"""

    def __init__(
        self, pattern: str, error_msg: str, required: bool = True, to_int: bool = False
    ):
        self.pattern = re.compile(pattern)
        self.error_msg = error_msg
        self.required = required
        self.to_int = to_int

    def validate(self, value: str) -> Tuple[bool, Optional[Any]]:
        if not value or value.strip() == "":
            if self.required:
                return False, None
            return True, None

        if len(value) > 500:
            return False, None

        if self.to_int:
            try:
                value = int(value)
            except ValueError:
                return False, None

        if not self.to_int and not self.pattern.match(str(value)):
            return False, None

        return True, value


DEPLOY_FORM_RULES: Dict[str, ValidationRule] = {
    # ansible_host / ansible_port / ansible_user теперь задаются списком
    # серверов и валидируются через parse_servers_from_form().
    # Правила ниже оставлены (необязательные) для обратной совместимости
    # со старыми вызовами API с одиночным сервером.
    "ansible_host": ValidationRule(
        pattern=r"^(\d{1,3}\.){3}\d{1,3}$",
        error_msg="Неверный формат IP адреса",
        required=False,
    ),
    "ansible_port": ValidationRule(
        pattern=r"^\d+$",
        error_msg="Порт должен быть числом",
        required=False,
        to_int=True,
    ),
    "ssh_hardening_port": ValidationRule(
        pattern=r"^\d+$",
        error_msg="SSH порт должен быть числом",
        required=False,
        to_int=True,
    ),
    "app_host_port": ValidationRule(
        pattern=r"^\d+$",
        error_msg="Порт хоста должен быть числом",
        required=True,
        to_int=True,
    ),
    "app_container_port": ValidationRule(
        pattern=r"^\d+$",
        error_msg="Порт контейнера должен быть числом",
        required=True,
        to_int=True,
    ),
    "ansible_user": ValidationRule(
        pattern=r"^[a-zA-Z][a-zA-Z0-9_-]*$",
        error_msg="Имя пользователя должно начинаться с буквы и содержать только буквы, цифры, _ и -",
        required=False,
    ),
    "app_deploy_container_name": ValidationRule(
        pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]+$",
        error_msg="Неверный формат имени контейнера",
        required=True,
    ),
    "app_deploy_image_name": ValidationRule(
        pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:/-]*$",
        error_msg="Неверный формат имени образа",
        required=True,
    ),
    "app_deploy_volumes": ValidationRule(
        pattern=r"^.*:.*$",
        error_msg="Volume должен быть в формате host:container",
        required=False,
    ),
    "app_deploy_envs": ValidationRule(
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*=[A-Za-z0-9_]*$",
        error_msg="Переменная окружения должна быть в формате KEY=value",
        required=False,
    ),
    "app_deploy_cpus": ValidationRule(
        pattern=r"^\d+(?:\.5)?$",
        error_msg="Переменная должна быть в формате целого или с плавающей точкой числа",
        required=False,
    ),
    "app_deploy_memory": ValidationRule(
        pattern=r"^\d+[BKMGTP]?$",
        error_msg="Переменная должна быть в формате целого числа + одна из букв [BKMGTP]",
        required=False,
    ),
    "fail2ban_configuration_app_log_path": ValidationRule(
        pattern=r"^((/[a-zA-Z0-9-_.]+)+|/)$",
        error_msg="Переменная должна содержать правильный путь",
        required=False,
    ),
    "fail2ban_configuration_app_filter": ValidationRule(
        pattern=r"^[a-zA-Z0-9_-]+$",
        error_msg="Имя переменной должно содержать только буквы, цифры, - и _",
        required=False,
    ),
    "fail2ban_configuration_app_regex": ValidationRule(
        pattern=r"^.*<HOST>.*$",
        error_msg="Неверный формат регулярного выражения",
        required=False,
    ),
    "fail2ban_configuration_app_maxretry": ValidationRule(
        pattern=r"^[0-9]+$",
        error_msg="Переменная должна содержать число",
        required=False,
        to_int=True,
    ),
    "fail2ban_configuration_app_bantime": ValidationRule(
        pattern=r"^[0-9]+$",
        error_msg="Переменная должна содержать число",
        required=False,
        to_int=True,
    ),
    "fail2ban_configuration_app_findtime": ValidationRule(
        pattern=r"^[0-9]+$",
        error_msg="Переменная должна содержать число",
        required=False,
        to_int=True,
    ),
    "fail2ban_configuration_app_ports": ValidationRule(
        pattern=r"^\d+(?:,\d+)*$",
        error_msg="Неправильно заданы порты для fail2ban",
        required=False,
    ),
}


IP_PATTERN = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")
USERNAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*$")


def _as_list(value) -> List[str]:
    """Приводит значение поля формы к списку строк (поддержка multi-value)."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value]
    return [str(value).strip()]


def _scalar_form_value(value) -> str:
    """Скаляр из значения поля формы: список -> первая непустая строка."""
    if isinstance(value, (list, tuple)):
        for v in value:
            v = str(v).strip()
            if v:
                return v
        return ""
    if value is None:
        return ""
    return str(value)


def _get_field(form_data: dict, name: str) -> List[str]:
    """Достаёт поле формы как список, совместимо с dict и MultiDict."""
    if hasattr(form_data, "getlist"):
        return [str(v).strip() for v in form_data.getlist(name)]
    return _as_list(form_data.get(name))


def parse_servers_from_form(form_data: dict) -> Tuple[List[dict], List[str]]:
    """
    Извлекает список серверов из данных формы.

    Поддерживаются форматы:
    1. Множественный (новая форма): списки ansible_host[], ansible_port[],
       ansible_user[] (одинаковые имена полей, разные значения).
    2. Одиночный (обратная совместимость со старым API): скалярные поля
       ansible_host, ansible_port, ansible_user.

    Возвращает (servers, errors), где servers — список словарей
    {'host', 'port', 'user'}.
    """
    errors: List[str] = []

    hosts = _get_field(form_data, "ansible_host")
    ports = _get_field(form_data, "ansible_port")
    users = _get_field(form_data, "ansible_user")

    # Убираем полностью пустые записи (пустые строки в списке)
    entries = list(
        zip(
            hosts,
            ports + [""] * max(0, len(hosts) - len(ports)),
            users + [""] * max(0, len(hosts) - len(users)),
        )
    )
    entries = [(h, p, u) for h, p, u in entries if h or p or u]

    if not entries:
        return [], ["Не указано ни одного сервера"]

    servers: List[dict] = []
    seen_hosts = set()

    for idx, (host, port, user) in enumerate(entries, 1):
        label = f"Сервер {idx}"

        if not host:
            errors.append(f"{label}: Не указан IP адрес")
            continue
        if not IP_PATTERN.match(host) or not all(0 <= int(o) <= 255 for o in host.split(".")):
            errors.append(f"{label}: Неверный формат IP адреса '{host}'")
            continue
        if host in seen_hosts:
            errors.append(f"{label}: Дублирующийся IP адрес '{host}'")
            continue
        seen_hosts.add(host)

        if not port:
            port = "22"
        if not port.isdigit():
            errors.append(f"{label}: Порт должен быть числом ('{port}')")
            continue
        port_int = int(port)
        if not (0 < port_int <= 65535):
            errors.append(f"{label}: Порт должен быть в диапазоне 1-65535")
            continue

        if not user:
            errors.append(f"{label}: Не указан пользователь")
            continue
        if not USERNAME_PATTERN.match(user):
            errors.append(f"{label}: Неверный формат имени пользователя '{user}'")
            continue

        servers.append({"host": host, "port": port_int, "user": user})

    return servers, errors


def validate_all_data(
    form_data: dict, file_path_image, file_path_private_ssh_key
) -> Tuple[bool, List[str], dict]:
    """
    Полная валидация всех данных.
    Возвращает (success, errors, validated_data)
    """
    if not file_path_image or not file_path_private_ssh_key:
        return False, ["Не загружены файлы (образ или ключ)"], {}
    is_valid, errors, validated_data = validate_form_data(form_data)

    servers, server_errors = parse_servers_from_form(form_data)
    errors.extend(server_errors)
    if server_errors:
        is_valid = False
    validated_data["servers"] = servers

    for field, min_val, max_val in [
        ("app_fail2ban_maxretry", 1, 20),
        ("app_fail2ban_bantime", 60, 86400),
        ("app_fail2ban_findtime", 60, 86400),
    ]:
        if field in validated_data:
            val = validated_data[field]
            if not (min_val <= val <= max_val):
                errors.append(f"{field}: Должно быть от {min_val} до {max_val}")

    if validated_data.get("app_fail2ban_regex"):
        try:
            re.compile(validated_data["app_fail2ban_regex"])
        except re.error as e:
            errors.append(
                f"app_fail2ban_regex: Неверный формат регулярного выражения ({e})"
            )

        regex = validated_data["app_fail2ban_regex"]
        if "\n" in regex or "\r" in regex or "\x00" in regex:
            errors.append("app_fail2ban_regex: Содержит недопустимые символы")

    if not validate_tar_archive(file_path_image):
        is_valid = False
        errors.append("docker_image: Неверный формат Docker образа (не TAR)")

    if not validate_ssh_private_key(file_path_private_ssh_key):
        is_valid = False
        errors.append("ssh_key: Неверный формат приватного SSH-ключа")

    return is_valid, errors, validated_data


def validate_multiline_field(
    value: str, line_pattern: re.Pattern, field_name: str, required: bool = False
) -> List[str]:
    """
    Валидирует мульти-строчное поле (каждая строка проверяется отдельно).
    Возвращает список ошибок (пустой, если всё ок).
    """
    errors = []

    if not value or value.strip() == "":
        if required:
            errors.append(f"{field_name}: Поле обязательно для заполнения")
        return errors

    lines = [line.strip() for line in value.splitlines() if line.strip()]

    for i, line in enumerate(lines, 1):
        if not line_pattern.match(line):
            errors.append(f"{field_name} (строка {i}): Неверный формат '{line}'")

    return errors


def validate_form_data(form_data: dict) -> Tuple[bool, List[str], dict]:
    """
    Валидирует данные формы по правилам.
    Возвращает (success, errors_list, validated_data)
    """
    errors = []
    validated_data = {}

    for field_name, rule in DEPLOY_FORM_RULES.items():
        if field_name in ["app_deploy_volumes", "app_deploy_envs"]:
            continue

        # Значения могут приходить списками (повторяющиеся поля формы —
        # несколько серверов или дубликаты полей). Для скалярных правил
        # берём первое непустое значение.
        raw_value = form_data.get(field_name, "")
        value_str = _scalar_form_value(raw_value)

        is_valid, processed_value = rule.validate(value_str)

        if not is_valid:
            errors.append(f"{field_name}: {rule.error_msg}")
        elif processed_value is not None:
            validated_data[field_name] = processed_value

    # Многострочные поля могут прийти списком (повторяющиеся textarea) —
    # склеиваем элементы в один текст построчно
    def _multiline(name: str) -> str:
        return "\n".join(_as_list(form_data.get(name)))

    volumes_raw = _multiline("app_deploy_volumes")
    envs_raw = _multiline("app_deploy_envs")

    volumes_pattern = re.compile(DEPLOY_FORM_RULES["app_deploy_volumes"].pattern)
    volumes_errors = validate_multiline_field(
        value=volumes_raw,
        line_pattern=volumes_pattern,
        field_name="app_deploy_volumes",
        required=False,
    )
    errors.extend(volumes_errors)

    if not volumes_errors and volumes_raw.strip():
        unique_volumes_host = []
        unique_volumes_container = []

        for line in volumes_raw.splitlines():
            new_line = line.split(":")

            if new_line[0] not in unique_volumes_host:
                unique_volumes_host.append(new_line[0])
            else:
                errors.append(
                    f"app_deploy_volumes: {new_line[0]} используется несколько раз"
                )
            if new_line[1] not in unique_volumes_container:
                unique_volumes_container.append(new_line[1])
            else:
                errors.append(
                    f"app_deploy_volumes: {new_line[1]} используется несколько раз"
                )

        validated_data["app_deploy_volumes"] = [
            line.strip() for line in volumes_raw.splitlines() if line.strip()
        ]
    else:
        validated_data["app_deploy_volumes"] = []

    env_pattern = re.compile(DEPLOY_FORM_RULES["app_deploy_envs"].pattern)
    env_errors = validate_multiline_field(
        value=envs_raw,
        line_pattern=env_pattern,
        field_name="app_deploy_envs",
        required=False,
    )
    errors.extend(env_errors)

    if not env_errors and envs_raw.strip():
        unique_env = []

        for line in envs_raw.splitlines():
            new_line = line.split("=")

            if new_line[0] not in unique_env:
                unique_env.append(new_line[0])
            else:
                errors.append(
                    f"app_deploy_envs: {new_line[0]} используется несколько раз"
                )

        validated_data["app_deploy_envs"] = {}
        for line in envs_raw.splitlines():
            line = line.strip()
            if line and "=" in line:
                key, value = line.split("=", 1)
                validated_data["app_deploy_envs"][key.strip()] = value.strip()
    else:
        validated_data["app_deploy_envs"] = {}

    for port_field in [
        "ansible_port",
        "ssh_hardening_port",
        "app_host_port",
        "app_container_port",
    ]:
        if port_field in validated_data:
            port = validated_data[port_field]
            if not (0 < port <= 65535):
                errors.append(f"{port_field}: Должен быть в диапазоне 1-65535")

    if "ansible_host" in validated_data:
        octets = validated_data["ansible_host"].split(".")
        if not all(0 <= int(o) <= 255 for o in octets):
            errors.append("ansible_host: Каждый октет должен быть в диапазоне 0-255")

    return len(errors) == 0, errors, validated_data


def validate_tar_archive(file_path_image):
    try:
        with tarfile.open(file_path_image) as tar:
            tar.getnames()
        return True
    except tarfile.ReadError:
        return False
    except tarfile.CompressionError:
        return False
    except FileNotFoundError:
        return False


def validate_ssh_private_key(file_path: str) -> bool:
    try:
        with open(file_path, "r") as f:
            lines = f.readlines()

        if len(lines) < 2:
            return False

        first_line = lines[0].strip()
        last_line = lines[-1].strip()

        begin_pattern = r"^-----BEGIN\s+(?:OPENSSH\s+)?PRIVATE\s+KEY-----$"
        if not re.match(begin_pattern, first_line):
            return False

        end_pattern = r"^-----END\s+(?:OPENSSH\s+)?PRIVATE\s+KEY-----$"
        if not re.match(end_pattern, last_line):
            return False

        return True

    except (IOError, UnicodeDecodeError):
        return False
