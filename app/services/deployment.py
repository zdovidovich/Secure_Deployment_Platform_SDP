from typing import Dict, Optional

from libs.ansible import make_host_event_callback, run_full_configuring
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
        # Статусы по каждому серверу: {hostname: {"host", "user", "status", ...}}
        self.servers: list = []
        self._host_to_label: Dict[str, str] = {}
        # True, если хотя бы одна строка вывода ansible ушла в консоль по ходу
        # выполнения (см. _build_event_handler и fallback после запуска).
        self._streamed_ansible_output = False

    def _build_event_handler(self):
        """
        Возвращает callback для ansible-runner: каждое событие Ansible
        транслируется в SSE-поток настоящей строкой своего вывода (поле stdout
        события — то же, что печатает ansible в терминале), поэтому консоль
        показывает реальный ход настройки, а не служебные метки задач.

        События конкретного хоста получают метку сервера, из-за чего работают
        фильтр по серверам и подсветка ошибок.
        """

        def _emit(text: str, level: str, host: Optional[str] = None):
            """
            Отправляет одну строку вывода ansible в консоль.

            host — публичный адрес сервера: строки с ним получают метку сервера
            (фильтр по серверам), строки без хоста идут как обычный вывод ansible.
            """
            line = self._replace_hostnames(text).strip()
            if not line:
                return
            self._streamed_ansible_output = True
            if host is None:
                self.logger.ansible(line)
            else:
                self.logger.send_host_log(level, line, host=host)

        def on_host_event(event_type: str, host: str, event_data: dict):
            label = self._host_to_label.get(host)
            if label is None:
                return

            entry = next((s for s in self.servers if s["hostname"] == host), None)

            # Статусы карточек серверов меняем сразу по ходу выполнения
            if event_type == "runner_on_start":
                if entry is not None and entry["status"] == "pending":
                    entry["status"] = "running"
            elif event_type in (
                "runner_on_failed",
                "runner_on_error",
                "runner_on_async_failed",
            ):
                if entry is not None:
                    entry["status"] = "failed"
            elif event_type == "runner_on_unreachable":
                if entry is not None:
                    entry["status"] = "unreachable"

            error_events = (
                "runner_on_failed",
                "runner_on_error",
                "runner_on_unreachable",
                "runner_on_async_failed",
            )
            level = "error" if event_type in error_events else "debug"

            lines = [
                ln
                for ln in (event_data.get("stdout") or "").splitlines()
                if ln.strip()
            ]
            for index, line in enumerate(lines):
                # Первую строку ошибки (fatal: ... / FAILED! => ...) подсвечиваем,
                # остальные строки вывода модуля выводим как обычный лог
                _emit(line, level if index == 0 else "debug", host=label)

        def on_other_event(event_type: str, event_data: dict):
            """События без хоста: баннеры PLAY/TASK, предупреждения, PLAY RECAP."""
            for line in (event_data.get("stdout") or "").splitlines():
                _emit(line, "debug")

        # make_host_event_callback защищает вызовы от исключений — логи не
        # должны уронить процесс деплоя
        return make_host_event_callback(on_host_event, on_other_event)

    def _replace_hostnames(self, text: str) -> str:
        """
        Внутренние имена хостов Ansible (server_1_ab12cd34) → публичные IP.

        В строках вида «ok: [server_1_ab12cd34]» квадратные скобки убираем:
        адрес сервера уже выводится меткой рядом со строкой.
        """
        for hostname, label in self._host_to_label.items():
            if hostname in text:
                text = text.replace(f"[{hostname}]", label)
                text = text.replace(hostname, label)
        return text

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

            # form_data может приходить как из API (значения — списки,
            # т.к. поля повторяются для нескольких серверов), так и из
            # обычных форм (строки) — нормализуем к скалярному виду
            def _scalar(value, default=None):
                if isinstance(value, (list, tuple)):
                    value = value[0] if len(value) > 0 else None
                if value is None:
                    return default
                return value

            def _flag(name: str) -> bool:
                return _scalar(form_data.get(name)) in ("on", "true", "1")

            if _flag("enable_trivy"):
                trivy_fail_on = _scalar(form_data.get("trivy_fail_on"), "HIGH")
                self.logger.info(
                    f"Сканирование образа (Trivy), порог блокировки: {trivy_fail_on}..."
                )

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
            servers = validated_data["servers"]
            inventory_path, hostnames = create_inventory_temp_file(
                servers,
                ssh_key_path,
            )

            # Маппинг внутренних имён хостов Ansible в публичные IP-адреса
            self._host_to_label = {
                hostname: server["host"]
                for hostname, server in zip(hostnames, servers)
            }
            self.servers = [
                {
                    "hostname": hostname,
                    "host": server["host"],
                    "port": server["port"],
                    "user": server["user"],
                    "status": "pending",
                }
                for hostname, server in zip(hostnames, servers)
            ]
            self.logger.info(
                f"Серверов в inventory: {len(servers)}: "
                + ", ".join(s["host"] for s in servers)
            )
            self.logger.send_servers_event(self.servers)

            self.logger.info("Запуск Ansible playbook...")
            # Порт по умолчанию берём из первого сервера (в валидированных
            # данных ansible_port — скаляр, даже если серверов несколько)
            default_ssh_port = _scalar(validated_data.get("ansible_port"), 22)
            ssh_new_port = _scalar(validated_data.get("ssh_hardening_port")) or default_ssh_port

            extra_vars = {
                "ssh_hardening_port": ssh_new_port,
                "ssh_fail2ban_configuration_port": ssh_new_port,
                "app_deploy_image_path": image_path,
                "selinux_configuration_state": (
                    "enforcing" if _flag("enable_selinux") else "disabled"
                ),
                "ssh_fail2ban_state": _flag("enable_fail2ban_for_ssh"),
                "ssh_hardening_disable_pass": _flag("ssh_hardening_disable_pass"),
                "app_deploy_image_name": validated_data["app_deploy_image_name"],
                "app_deploy_container_name": validated_data[
                    "app_deploy_container_name"
                ],
                "app_deploy_ports": [
                    f"{validated_data['app_host_port']}:{validated_data['app_container_port']}"
                ],
                "app_deploy_volumes": validated_data["app_deploy_volumes"],
                "app_deploy_envs": validated_data["app_deploy_envs"],
                "app_deploy_ro_fs": _flag("app_deploy_ro_fs"),
                "app_deploy_cpus": validated_data.get("app_deploy_cpus", None),
                "app_deploy_memory": validated_data.get("app_deploy_memory", None),
                "enable_container_fail2ban": _flag("enable_container_fail2ban"),
                "fail2ban_configuration_app_log_path": _scalar(
                    form_data.get("fail2ban_configuration_app_log_path"),
                    "/var/log/app/access.log",
                ),
                "fail2ban_configuration_app_filter": _scalar(
                    form_data.get("fail2ban_configuration_app_filter"), "app-generic"
                ),
                "fail2ban_configuration_app_regex": _scalar(
                    form_data.get("fail2ban_configuration_app_regex"), ""
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

            ansible_result = run_full_configuring(
                extra_vars,
                inventory_path,
                event_callback=self._build_event_handler(),
            )

            # Итоговые статусы по каждому серверу на основе статистики Ansible.
            # ansible-runner (Runner.stats) отдаёт ключи ok / dark / failures /
            # processed, а не contacted / unreachable / failed — старые имена
            # оставлены как fallback для совместимости.
            stats = ansible_result.stats or {}
            contact_stats = stats.get("ok") or stats.get("contacted") or {}
            unreachable_stats = stats.get("dark") or stats.get("unreachable") or {}
            failed_stats = stats.get("failures") or stats.get("failed") or {}
            processed_stats = stats.get("processed", {})
            for server in self.servers:
                hostname = server["hostname"]
                if hostname in unreachable_stats:
                    server["status"] = "unreachable"
                elif hostname in failed_stats:
                    server["status"] = "failed"
                elif hostname in contact_stats or hostname in processed_stats:
                    server["status"] = "success"
                elif server["status"] not in ("failed", "unreachable"):
                    server["status"] = "skipped"
            self.logger.send_servers_event(self.servers)

            # Настоящий вывод ansible уже ушёл в консоль по ходу выполнения
            # (см. _build_event_handler). Если события вообще не дошли —
            # например, изменился контракт event_handler в ansible-runner —
            # показываем артефакт целиком, чтобы вывод не потерялся.
            if not self._streamed_ansible_output:
                for line in ansible_result.stdout.read().split("\n"):
                    line = self._replace_hostnames(line).strip()
                    if line:
                        self.logger.ansible(line)

            if ansible_result.status != "successful":
                self.status = "error"
                self.result = {
                    "error": "Ansible playbook failed",
                    "stats": ansible_result.stats,
                    "servers": self.servers,
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
                    "servers": self.servers,
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
