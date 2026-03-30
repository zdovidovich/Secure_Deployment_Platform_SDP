# app/services/deployment.py
import os
import threading
from typing import Dict, Optional
from werkzeug.utils import secure_filename

from libs.temp_files import save_temp_file, create_inventory_temp_file, cleanup_temp_files
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
            self.logger.info("🚀 Запуск процесса деплоя...")
            
            # === ШАГ 1: Файлы уже сохранены, используем пути ===
            self.logger.info("Загруженные файлы готовы")
            ssh_key_path = file_paths.get('ssh_key')
            image_path = file_paths.get('docker_image')
            dockerfile_path = file_paths.get('dockerfile')
            
            # === ШАГ 2: Валидация ===
            self.logger.info("Проверка корректности данных...")
            is_valid, errors, validated_data = validate_all_data(
                form_data, image_path, ssh_key_path
            )
            if not is_valid:
                self.status = "error"
                self.result = {"error": "Validation failed", "details": errors}
                self.logger.error(f"Валидация не пройдена: {errors}")
                return self.result
            
            # === ШАГ 3: Hadolint (если есть Dockerfile) ===
            if dockerfile_path:
                self.logger.info("Проверка Dockerfile (Hadolint)...")
                hadolint_result = scan_dockerfile(dockerfile_path)
                if hadolint_result['success']:
                    formatted = format_hadolint_result(hadolint_result['issues'])
                    self.logger.hadolint(formatted)
                    if hadolint_result.get('errors'):
                        self.status = "error"
                        self.result = {"error": "Hadolint found errors", "details": formatted}
                        self.logger.error("Hadolint обнаружил критические ошибки")
                        return self.result
                else:
                    self.status = "error"
                    self.result = {"error": "Hadolint scan failed", "details": hadolint_result['error']}
                    self.logger.error(f"Hadolint ошибка: {hadolint_result['error']}")
                    return self.result
            
            # === ШАГ 4: Trivy ===
            if form_data.get('enable_trivy') == "on":
                self.logger.info("Сканирование образа (Trivy)...")
                trivy_result = scan_image(image_path)
                if trivy_result['success']:
                    formatted = format_trivy_result(trivy_result['vulnerabilities'])
                    self.logger.trivy(formatted)
                    if trivy_result.get('critical_count', 0) + trivy_result.get('high_count', 0) > 0:
                        self.status = "error"
                        self.result = {
                            "error": "Vulnerabilities found",
                            "critical": trivy_result['critical_count'],
                            "high": trivy_result['high_count'],
                            "details": formatted
                        }
                        self.logger.error(f"Найдено уязвимостей: CRITICAL={trivy_result['critical_count']}, HIGH={trivy_result['high_count']}")
                        return self.result
                else:
                    self.status = "error"
                    self.result = {"error": "Trivy scan failed", "details": trivy_result['error']}
                    self.logger.error(f"Trivy ошибка: {trivy_result['error']}")
                    return self.result
            
            # === ШАГ 5: Ansible Inventory ===
            self.logger.info("Подготовка Ansible inventory...")
            inventory_path = create_inventory_temp_file({
                'ansible_host': validated_data['ansible_host'],
                'ansible_port': validated_data['ansible_port'],
                'ansible_user': validated_data['ansible_user']
            }, ssh_key_path)
            
            # === ШАГ 6: Ansible Playbook ===
            self.logger.info("Запуск Ansible playbook...")
            extra_vars = {
                'ssh_port': validated_data['ssh_port'],
                'app_image_path': image_path,
                'selinux_state': "enforcing" if form_data.get('enable_selinux') == 'on' else "disabled",
                'fail2ban_state': form_data.get('enable_fail2ban') == 'on',
                'app_image_name': validated_data['app_image_name'],
                'app_container_name': validated_data['app_container_name'],
                'app_ports': [f"{validated_data['app_host_port']}:{validated_data['app_container_port']}"],
                'app_volumes': validated_data['app_volumes'],
                'app_envs': validated_data['app_envs'],
            }
            
            ansible_result = run_full_configuring(extra_vars, inventory_path)
            
            # Парсим логи Ansible и отправляем в SSE
            for line in ansible_result.stdout.read().split('\n'):
                if line.strip():
                    self.logger.ansible(line)
            
            # === ШАГ 7: Очистка ===
            self.logger.info("Очистка временных файлов...")
            cleanup_temp_files()
            
            # === ШАГ 8: Финальный статус ===
            if ansible_result.failed:
                self.status = "error"
                self.result = {
                    "error": "Ansible playbook failed",
                    "stats": ansible_result.stats,
                    "stderr": ansible_result.stderr.read()
                }
                self.logger.error("Ansible завершился с ошибкой")
            else:
                self.status = "success"
                self.result = {
                    "success": True,
                    "stats": ansible_result.stats,
                    "message": "Деплой успешно завершён"
                }
                self.logger.info("✅ Деплой успешно завершён!")
            
            # Отправляем событие завершения
            self.logger.complete(self.result)
            
            return self.result
            
        except Exception as e:
            self.status = "error"
            self.result = {"error": f"Unexpected error: {str(e)}"}
            self.logger.error(f"Критическая ошибка: {str(e)}")
            return self.result