from typing import Dict, Optional
from libs.temp_files import create_inventory_temp_file, cleanup_temp_files
from libs.validation import validate_all_data
from libs.hadolint import scan_dockerfile, format_hadolint_result
from libs.trivy import scan_image, format_trivy_result
from libs.ansible import run_full_configuring
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
        try:
            self.status = "running"
            self.logger.info("Запуск процесса деплоя...")

            self.logger.info("Загруженные файлы готовы")
            ssh_key_path = file_paths.get('ssh_key')
            image_path = file_paths.get('docker_image')
            dockerfile_path = file_paths.get('dockerfile')

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
                if hadolint_result['success']:
                    formatted = format_hadolint_result(
                        hadolint_result['issues'])
                    self.logger.hadolint(formatted[-1])
                    if hadolint_result.get('errors'):
                        self.status = "error"
                        self.result = {
                            "error": "Hadolint found errors", "details": formatted}
                        self.logger.error(
                            "Hadolint обнаружил критические ошибки")
                        return self.result
                else:
                    self.status = "error"
                    self.result = {"error": "Hadolint scan failed",
                                   "details": hadolint_result['error']}
                    self.logger.error(
                        f"Hadolint ошибка: {hadolint_result['error']}")
                    return self.result

            if form_data.get('enable_trivy') == "on":
                trivy_fail_on = form_data.get('trivy_fail_on', 'HIGH')
                self.logger.info(
                    f"Сканирование образа (Trivy), порог блокировки: {trivy_fail_on}...")

                trivy_result = scan_image(
                    image_path, fail_on_severity=trivy_fail_on)

                if not trivy_result['success']:
                    self.status = "error"
                    self.result = {"error": "Trivy scan failed",
                                   "details": trivy_result['error']}
                    self.logger.error(f"Trivy ошибка: {trivy_result['error']}")
                    return self.result

                formatted = format_trivy_result(
                    trivy_result['vulnerabilities']
                )
                self.logger.trivy(formatted)

                if trivy_result.get('blocked', False):
                    self.status = "error"
                    self.result = {
                        "error": f"Найдено {trivy_result['blocking_count']} уязвимостей уровня {trivy_result['blocking_severity']}+",
                        "blocking_count": trivy_result['blocking_count'],
                        "blocking_severity": trivy_result['blocking_severity'],
                        "severity_counts": trivy_result.get('severity_counts', {}),
                        "details": formatted
                    }
                    self.logger.error(
                        f"Деплой заблокирован: {trivy_result['blocking_count']} уязвимостей уровня "
                        f"{trivy_result['blocking_severity']}+ (порог: {trivy_fail_on})"
                    )
                    return self.result

                counts = trivy_result.get('severity_counts', {})
                self.logger.info(
                    f"Trivy: CRITICAL={counts.get('CRITICAL', 0)}, HIGH={counts.get('HIGH', 0)}, "
                    f"MEDIUM={counts.get('MEDIUM', 0)}, LOW={counts.get('LOW', 0)}"
                )

            self.logger.info("Подготовка Ansible inventory...")
            inventory_path = create_inventory_temp_file({
                'ansible_host': validated_data['ansible_host'],
                'ansible_port': validated_data['ansible_port'],
                'ansible_user': validated_data['ansible_user']
            }, ssh_key_path)

            self.logger.info("Запуск Ansible playbook...")
            extra_vars = {
                'ssh_hardening_port': validated_data.get('ssh_hardening_port', validated_data['ansible_port']),
                'ssh_fail2ban_configuration_port': validated_data.get('ssh_hardening_port', validated_data['ansible_port']),
                'app_deploy_image_path': image_path,
                'selinux_configuration_state': "enforcing" if form_data.get('enable_selinux') == 'on' else "disabled",
                'ssh_fail2ban_state': form_data.get('enable_fail2ban_for_ssh') == 'on',
                'ssh_hardening_disable_pass': form_data.get('ssh_hardening_disable_pass') == 'on',
                'app_deploy_image_name': validated_data['app_deploy_image_name'],
                'app_deploy_container_name': validated_data['app_deploy_container_name'],
                'app_deploy_ports': [f"{validated_data['app_host_port']}:{validated_data['app_container_port']}"],
                'app_deploy_volumes': validated_data['app_deploy_volumes'],
                'app_deploy_envs': validated_data['app_deploy_envs'],
                'app_deploy_ro_fs': form_data.get('app_deploy_ro_fs') == 'on',
                'app_deploy_cpus': validated_data.get('app_deploy_cpus', None),
                'app_deploy_memory': validated_data.get('app_deploy_memory', None),
                'enable_container_fail2ban': form_data.get("enable_container_fail2ban") == "on",
                'fail2ban_configuration_app_log_path': validated_data.get('fail2ban_configuration_app_log_path', '/var/log/app/access.log'),
                'fail2ban_configuration_app_filter': validated_data.get('fail2ban_configuration_app_filter', 'app-generic'),
                'fail2ban_configuration_app_regex': validated_data.get('fail2ban_configuration_app_regex', ''),
                'fail2ban_configuration_app_maxretry': validated_data.get("fail2ban_configuration_app_maxretry", 5),
                'fail2ban_configuration_app_bantime': validated_data.get("fail2ban_configuration_app_bantime", 86400),
                'fail2ban_configuration_app_findtime': validated_data.get('fail2ban_configuration_app_findtime', 7200),
                'fail2ban_configuration_app_ports': validated_data.get("fail2ban_configuration_app_ports", validated_data['app_host_port'])
            }
            
            ansible_result = run_full_configuring(extra_vars, inventory_path)

            for line in ansible_result.stdout.read().split('\n'):
                if line.strip():
                    self.logger.ansible(line)

            self.logger.info("Очистка временных файлов...")
            cleanup_temp_files()


            if ansible_result.status != "successful":
                self.status = "error"
                self.result = {
                    "error": "Ansible playbook failed",
                    "stats": ansible_result.stats,
                    "stderr": ansible_result.stderr.read()
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
                    "message": "Деплой успешно завершён"
                }
                
            return self.result

        except Exception as e:
            self.status = "error"
            self.result = {"error": f"Unexpected error: {str(e)}"}
            self.logger.error(f"Критическая ошибка: {str(e)}")
            return self.result
