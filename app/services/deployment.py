import subprocess
from typing import Dict, Optional

from libs.ansible import run_full_configuring
from libs.hadolint import format_hadolint_result, scan_dockerfile
from libs.temp_files import cleanup_specific_files, create_inventory_temp_file
from libs.trivy import format_trivy_result, scan_image
from libs.validation import validate_all_data
from sse.broadcaster import SSEBroadcaster


class DeploymentService:
    """
    Оркестрирует весь процесс деплоя:
    валидация → сканирование → Ansible → отчёт
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.logger = SSEBroadcaster(session_id)
        self.status = "pending"  # pending, running, success, error
        self.result: Optional[Dict] = None

    def execute(self, form_data: dict, file_paths: dict) -> Dict:
        """
        Главный метод: выполняет весь пайплайн деплоя.

        Args:
            form_data: Словарь с данными формы
            file_paths: Словарь с путями к сохранённым файлам
                        {'ssh_key': '/tmp/ssh_key_...', 'docker_image': '/tmp/docker_image_...'}
        """
        inventory_path = None

        try:
            self.status = "running"
            self.logger.info("Запуск процесса деплоя...")

            self.logger.info("Загруженные файлы готовы")
            ssh_key_path = file_paths.get("ssh_key")
            image_path = file_paths.get("docker_image")
            dockerfile_path = file_paths.get("dockerfile")

            self.logger.info("Проверка корректности данных...")
            is_valid, errors, validated_data = validate_all_data(
                form_data, image_path, ssh_key_path
            )

            if not is_valid:
                self.status = "error"
                self.result = {"error": "Validation failed", "details": errors}
                self.logger.error(f"Валидация не пройдена: {errors}")
                return self.result

            if dockerfile_path:
                self.logger.info("Проверка Dockerfile (Hadolint)...")
                hadolint_result = scan_dockerfile(dockerfile_path)
                if hadolint_result["success"]:
                    formatted = format_hadolint_result(hadolint_result["issues"])
                    self.logger.hadolint(formatted[-1])
                    if hadolint_result.get("errors"):
                        self.status = "error"
                        self.result = {
                            "error": "Hadolint found errors",
                            "details": formatted,
                        }
                        self.logger.error("Hadolint обнаружил критические ошибки")
                        return self.result
                else:
                    self.status = "error"
                    self.result = {
                        "error": "Hadolint scan failed",
                        "details": hadolint_result["error"],
                    }
                    self.logger.error(f"Hadolint ошибка: {hadolint_result['error']}")
                    return self.result

            image_source = form_data.get("docker_image_source", "tar")
            full_image_name = validated_data.get("app_deploy_image_name", "")

            if image_source == "registry":
                registry_url = form_data.get("registry_url", "")
                registry_username = form_data.get("registry_username", "")
                registry_password = form_data.get("registry_password", "")

                # Docker login при наличии кредов
                if registry_username and registry_password:
                    self.logger.info(f"Вход в registry {registry_url}...")
                    login_cmd = [
                        "docker", "login",
                        registry_url,
                        "-u", registry_username,
                        "--password-stdin",
                    ]
                    try:
                        login_result = subprocess.run(
                            login_cmd,
                            input=registry_password,
                            capture_output=True,
                            text=True,
                            timeout=120,
                        )
                        if login_result.returncode != 0:
                            self.status = "error"
                            self.result = {
                                "error": "Docker login failed",
                                "details": login_result.stderr,
                            }
                            self.logger.error(
                                f"Docker login ошибка: {login_result.stderr}"
                            )
                            return self.result
                        self.logger.info("Успешный вход в registry")
                    except subprocess.TimeoutExpired:
                        self.status = "error"
                        self.result = {"error": "Docker login timeout"}
                        self.logger.error("Docker login превысил время ожидания")
                        return self.result

                # Docker pull образа
                self.logger.info(f"Загрузка образа {full_image_name}...")
                pull_cmd = ["docker", "pull", full_image_name]
                try:
                    pull_result = subprocess.run(
                        pull_cmd,
                        capture_output=True,
                        text=True,
                        timeout=3600,
                    )
                    if pull_result.returncode != 0:
                        self.status = "error"
                        self.result = {
                            "error": "Docker pull failed",
                            "details": pull_result.stderr,
                        }
                        self.logger.error(
                            f"Docker pull ошибка: {pull_result.stderr}"
                        )
                        return self.result
                    self.logger.info(f"Образ {full_image_name} успешно загружен")
                except subprocess.TimeoutExpired:
                    self.status = "error"
                    self.result = {"error": "Docker pull timeout"}
                    self.logger.error("Docker pull превысил время ожидания")
                    return self.result

            if form_data.get("enable_trivy") == "on":
                trivy_fail_on = form_data.get("trivy_fail_on", "HIGH")
                self.logger.info(
                    f"Сканирование образа (Trivy), порог блокировки: {trivy_fail_on}..."
                )

                if image_source == "registry":
                    trivy_result = scan_image(
                        full_image_name, fail_on_severity=trivy_fail_on, is_tar=False
                    )
                else:
                    trivy_result = scan_image(image_path, fail_on_severity=trivy_fail_on)

                if not trivy_result["success"]:
                    self.status = "error"
                    self.result = {
                        "error": "Trivy scan failed",
                        "details": trivy_result["error"],
                    }
                    self.logger.error(f"Trivy ошибка: {trivy_result['error']}")
                    return self.result

                formatted = format_trivy_result(trivy_result["vulnerabilities"])
                self.logger.trivy(formatted)

                if trivy_result.get("blocked", False):
                    self.status = "error"
                    self.result = {
                        "error": f"Найдено {trivy_result['blocking_count']} уязвимостей уровня {trivy_result['blocking_severity']}+",
                        "blocking_count": trivy_result["blocking_count"],
                        "blocking_severity": trivy_result["blocking_severity"],
                        "severity_counts": trivy_result.get("severity_counts", {}),
                        "details": formatted,
                    }
                    self.logger.error(
                        f"Деплой заблокирован: {trivy_result['blocking_count']} уязвимостей уровня "
                        f"{trivy_result['blocking_severity']}+ (порог: {trivy_fail_on})"
                    )
                    return self.result

                counts = trivy_result.get("severity_counts", {})
                self.logger.info(
                    f"Trivy: CRITICAL={counts.get('CRITICAL', 0)}, HIGH={counts.get('HIGH', 0)}, "
                    f"MEDIUM={counts.get('MEDIUM', 0)}, LOW={counts.get('LOW', 0)}"
                )

            self.logger.info("Подготовка Ansible inventory...")
            inventory_path = create_inventory_temp_file(
                {
                    "ansible_host": validated_data["ansible_host"],
                    "ansible_port": validated_data["ansible_port"],
                    "ansible_user": validated_data["ansible_user"],
                },
                ssh_key_path,
            )

            self.logger.info("Запуск Ansible playbook...")
            # Для режима registry передаём имя образа с полным путём (registry/image:tag)
            # Для режима tar передаём путь к архиву
            if image_source == "registry":
                app_deploy_image_path = ""
            else:
                app_deploy_image_path = image_path

            extra_vars = {
                "ssh_hardening_port": validated_data.get(
                    "ssh_hardening_port", validated_data["ansible_port"]
                ),
                "ssh_fail2ban_configuration_port": validated_data.get(
                    "ssh_hardening_port", validated_data["ansible_port"]
                ),
                "app_deploy_image_path": app_deploy_image_path,
                "docker_image_source": image_source,
                "registry_url": form_data.get("registry_url", ""),
                "registry_username": form_data.get("registry_username", ""),
                "registry_password": form_data.get("registry_password", ""),
                "selinux_configuration_state": (
                    "enforcing"
                    if form_data.get("enable_selinux") == "on"
                    else "disabled"
                ),
                "ssh_fail2ban_state": form_data.get("enable_fail2ban_for_ssh") == "on",
                "ssh_hardening_disable_pass": (
                    form_data.get("ssh_hardening_disable_pass") == "on"
                ),
                "app_deploy_image_name": validated_data["app_deploy_image_name"],
                "app_deploy_container_name": validated_data[
                    "app_deploy_container_name"
                ],
                "app_deploy_ports": [
                    f"{validated_data['app_host_port']}:{validated_data['app_container_port']}"
                ],
                "app_deploy_volumes": validated_data["app_deploy_volumes"],
                "app_deploy_envs": validated_data["app_deploy_envs"],
                "app_deploy_ro_fs": form_data.get("app_deploy_ro_fs") == "on",
                "app_deploy_cpus": validated_data.get("app_deploy_cpus", None),
                "app_deploy_memory": validated_data.get("app_deploy_memory", None),
                "enable_container_fail2ban": (
                    form_data.get("enable_container_fail2ban") == "on"
                ),
                "fail2ban_configuration_app_log_path": validated_data.get(
                    "fail2ban_configuration_app_log_path", "/var/log/app/access.log"
                ),
                "fail2ban_configuration_app_filter": validated_data.get(
                    "fail2ban_configuration_app_filter", "app-generic"
                ),
                "fail2ban_configuration_app_regex": validated_data.get(
                    "fail2ban_configuration_app_regex", ""
                ),
                "fail2ban_configuration_app_maxretry": validated_data.get(
                    "fail2ban_configuration_app_maxretry", 5
                ),
                "fail2ban_configuration_app_bantime": validated_data.get(
                    "fail2ban_configuration_app_bantime", 86400
                ),
                "fail2ban_configuration_app_findtime": validated_data.get(
                    "fail2ban_configuration_app_findtime", 7200
                ),
                "fail2ban_configuration_app_ports": validated_data.get(
                    "fail2ban_configuration_app_ports",
                    validated_data["app_host_port"],
                ),
            }

            ansible_result = run_full_configuring(extra_vars, inventory_path)

            for line in ansible_result.stdout.read().split("\n"):
                if line.strip():
                    self.logger.ansible(line)

            if ansible_result.status != "successful":
                self.status = "error"
                self.result = {
                    "error": "Ansible playbook failed",
                    "stats": ansible_result.stats,
                    "stderr": ansible_result.stderr.read(),
                }
                self.logger.error("Ansible завершился с ошибкой")
            else:
                self.status = "success"
                self.logger.info("Деплой успешно завершён!")
                self.logger.info(
                    "Возможно были изменены настройки безопасности на RHEL-системах: для применения SELinux может потребоваться перезагрузка."
                )
                self.result = {
                    "success": True,
                    "stats": ansible_result.stats,
                    "message": "Деплой успешно завершён",
                }

            return self.result

        except Exception as exc:
            self.status = "error"
            self.result = {"error": f"Unexpected error: {str(exc)}"}
            self.logger.error(f"Критическая ошибка: {str(exc)}")
            return self.result
        finally:
            self.logger.info("Очистка временных файлов...")
            cleanup_specific_files(file_paths)
            if inventory_path:
                cleanup_specific_files({"inventory": inventory_path})

            # Выход из registry если был вход
            image_source = form_data.get("docker_image_source", "tar")
            if image_source == "registry":
                registry_url = form_data.get("registry_url", "")
                registry_username = form_data.get("registry_username", "")
                if registry_url and registry_username:
                    try:
                        self.logger.info(f"Выход из registry {registry_url}...")
                        subprocess.run(
                            ["docker", "logout", registry_url],
                            capture_output=True,
                            text=True,
                            timeout=30,
                        )
                    except Exception:
                        pass  # Игнорируем ошибки logout
