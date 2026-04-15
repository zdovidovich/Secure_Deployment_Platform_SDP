from celery import current_task
from worker.celery_app import celery_app
from sqlalchemy import select, create_engine
from sqlalchemy.orm import Session
import os
import sys

# Добавляем корень проекта в путь для импортов из оригинального кода
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.core.config import settings
from app.models.deployment import Deployment, DeploymentStatus, DeploymentLog


def get_db_session():
    """Создает синхронную сессию БД для использования в Celery задаче"""
    # Для SQLite используем обычный движок
    db_url = settings.DATABASE_URL.replace("sqlite+aiosqlite", "sqlite")
    engine = create_engine(db_url)
    return Session(engine)


@celery_app.task(bind=True, max_retries=3)
def run_deployment(self, deployment_id: str):
    """
    Основная задача деплоя.
    Выполняет весь пайплайн: валидация → сканирование → Ansible → отчет
    """
    from libs.temp_files import create_inventory_temp_file, cleanup_temp_files
    from libs.validation import validate_all_data
    from libs.hadolint import scan_dockerfile, format_hadolint_result
    from libs.trivy import scan_image, format_trivy_result
    from libs.ansible import run_full_configuring
    
    db = get_db_session()
    
    def add_log(level: str, message: str, source: str = "deployment", details: dict = None):
        """Добавляет лог в БД и обновляет кэш логов"""
        from datetime import datetime
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level,
            "message": message,
            "source": source,
            "details": details or {}
        }
        
        deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
        if deployment:
            if not deployment.logs:
                deployment.logs = []
            deployment.logs.append(log_entry)
            db.commit()
    
    try:
        # Получаем информацию о деплое
        deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
        if not deployment:
            raise Exception(f"Deployment {deployment_id} not found")
        
        add_log("info", "Запуск процесса деплоя...")
        
        ssh_key_path = deployment.ssh_key_path
        image_path = deployment.docker_image_path
        dockerfile_path = deployment.dockerfile_path
        
        # Подготовка данных для валидации
        form_data = {
            'ansible_host': deployment.ansible_host,
            'ansible_port': deployment.ansible_port,
            'ansible_user': deployment.ansible_user,
            'app_deploy_image_name': deployment.app_deploy_image_name,
            'app_deploy_container_name': deployment.app_deploy_container_name,
            'app_host_port': deployment.app_host_port,
            'app_container_port': deployment.app_container_port,
        }
        
        # Дополнительные параметры из result JSON
        if deployment.result:
            form_data.update(deployment.result)
        
        add_log("info", "Проверка корректности данных...")
        is_valid, errors, validated_data = validate_all_data(
            form_data, image_path, ssh_key_path
        )
        
        if not is_valid:
            deployment.status = DeploymentStatus.ERROR
            deployment.error_message = f"Validation failed: {errors}"
            db.commit()
            add_log("error", f"Валидация не пройдена: {errors}")
            return {"error": "Validation failed", "details": errors}
        
        # Hadolint сканирование
        if dockerfile_path and os.path.exists(dockerfile_path):
            add_log("info", "Проверка Dockerfile (Hadolint)...")
            hadolint_result = scan_dockerfile(dockerfile_path)
            
            if hadolint_result['success']:
                formatted = format_hadolint_result(hadolint_result['issues'])
                add_log("info", "Отчёт Hadolint", source="hadolint", details={"report": formatted[1] if isinstance(formatted, tuple) else formatted})
                
                if hadolint_result.get('errors'):
                    deployment.status = DeploymentStatus.ERROR
                    deployment.error_message = "Hadolint found errors"
                    deployment.result = {"error": "Hadolint found errors", "details": formatted}
                    db.commit()
                    add_log("error", "Hadolint обнаружил критические ошибки")
                    return {"error": "Hadolint found errors", "details": formatted}
            else:
                deployment.status = DeploymentStatus.ERROR
                deployment.error_message = f"Hadolint scan failed: {hadolint_result['error']}"
                db.commit()
                add_log("error", f"Hadolint ошибка: {hadolint_result['error']}")
                return {"error": "Hadolint scan failed", "details": hadolint_result['error']}
        
        # Trivy сканирование
        if deployment.enable_trivy == "on":
            trivy_fail_on = deployment.trivy_fail_on or "HIGH"
            add_log("info", f"Сканирование образа (Trivy), порог блокировки: {trivy_fail_on}...")
            
            trivy_result = scan_image(image_path, fail_on_severity=trivy_fail_on)
            
            if not trivy_result['success']:
                deployment.status = DeploymentStatus.ERROR
                deployment.error_message = f"Trivy scan failed: {trivy_result['error']}"
                db.commit()
                add_log("error", f"Trivy ошибка: {trivy_result['error']}")
                return {"error": "Trivy scan failed", "details": trivy_result['error']}
            
            formatted = format_trivy_result(trivy_result['vulnerabilities'])
            add_log("info", "Отчёт Trivy", source="trivy", details={"report": formatted})
            
            if trivy_result.get('blocked', False):
                deployment.status = DeploymentStatus.ERROR
                deployment.error_message = f"Найдено {trivy_result['blocking_count']} уязвимостей уровня {trivy_result['blocking_severity']}+"
                deployment.result = {
                    "error": f"Найдено {trivy_result['blocking_count']} уязвимостей уровня {trivy_result['blocking_severity']}+",
                    "blocking_count": trivy_result['blocking_count'],
                    "blocking_severity": trivy_result['blocking_severity'],
                    "severity_counts": trivy_result.get('severity_counts', {}),
                }
                db.commit()
                add_log("error", f"Деплой заблокирован: {trivy_result['blocking_count']} уязвимостей уровня {trivy_result['blocking_severity']}+")
                return {"error": "Trivy blocked deployment", **deployment.result}
            
            counts = trivy_result.get('severity_counts', {})
            add_log("info", f"Trivy: CRITICAL={counts.get('CRITICAL', 0)}, HIGH={counts.get('HIGH', 0)}, MEDIUM={counts.get('MEDIUM', 0)}, LOW={counts.get('LOW', 0)}")
        
        # Ansible playbook
        add_log("info", "Подготовка Ansible inventory...")
        inventory_path = create_inventory_temp_file({
            'ansible_host': validated_data['ansible_host'],
            'ansible_port': validated_data['ansible_port'],
            'ansible_user': validated_data['ansible_user']
        }, ssh_key_path)
        
        add_log("info", "Запуск Ansible playbook...")
        
        # Подготовка extra_vars
        extra_vars = {
            'ssh_hardening_port': form_data.get('ssh_hardening_port', validated_data['ansible_port']),
            'ssh_fail2ban_configuration_port': form_data.get('ssh_hardening_port', validated_data['ansible_port']),
            'app_deploy_image_path': image_path,
            'selinux_configuration_state': "enforcing" if deployment.enable_selinux == "on" else "disabled",
            'ssh_fail2ban_state': deployment.enable_fail2ban_for_ssh == "on",
            'ssh_hardening_disable_pass': deployment.ssh_hardening_disable_pass == "on",
            'app_deploy_image_name': validated_data['app_deploy_image_name'],
            'app_deploy_container_name': validated_data['app_deploy_container_name'],
            'app_deploy_ports': [f"{validated_data['app_host_port']}:{validated_data['app_container_port']}"],
            'app_deploy_volumes': form_data.get('app_deploy_volumes', []),
            'app_deploy_envs': form_data.get('app_deploy_envs', {}),
            'app_deploy_ro_fs': deployment.app_deploy_ro_fs == "on",
            'app_deploy_cpus': form_data.get('app_deploy_cpus'),
            'app_deploy_memory': form_data.get('app_deploy_memory'),
            'enable_container_fail2ban': deployment.enable_container_fail2ban == "on",
            'fail2ban_configuration_app_log_path': form_data.get('fail2ban_configuration_app_log_path', '/var/log/app/access.log'),
            'fail2ban_configuration_app_filter': form_data.get('fail2ban_configuration_app_filter', 'app-generic'),
            'fail2ban_configuration_app_regex': form_data.get('fail2ban_configuration_app_regex', ''),
            'fail2ban_configuration_app_maxretry': form_data.get('fail2ban_configuration_app_maxretry', 5),
            'fail2ban_configuration_app_bantime': form_data.get('fail2ban_configuration_app_bantime', 86400),
            'fail2ban_configuration_app_findtime': form_data.get('fail2ban_configuration_app_findtime', 7200),
            'fail2ban_configuration_app_ports': form_data.get('fail2ban_configuration_app_ports', validated_data['app_host_port'])
        }
        
        ansible_result = run_full_configuring(extra_vars, inventory_path)
        
        # Логи Ansible
        for line in ansible_result.stdout.read().split('\n'):
            if line.strip():
                add_log("debug", line, source="ansible")
        
        add_log("info", "Очистка временных файлов...")
        cleanup_temp_files()
        
        if ansible_result.status != "successful":
            deployment.status = DeploymentStatus.ERROR
            deployment.error_message = "Ansible playbook failed"
            deployment.result = {
                "error": "Ansible playbook failed",
                "stats": ansible_result.stats,
                "stderr": ansible_result.stderr.read()
            }
            db.commit()
            add_log("error", "Ansible завершился с ошибкой")
            return {"error": "Ansible failed", "stats": ansible_result.stats}
        else:
            deployment.status = DeploymentStatus.SUCCESS
            deployment.result = {
                "success": True,
                "stats": ansible_result.stats,
                "message": "Деплой успешно завершён"
            }
            db.commit()
            add_log("info", "Деплой успешно завершён!")
            add_log("info", "Возможно были изменены настройки безопасности на RHEL-системах: для применения SELinux может потребоваться перезагрузка.")
            return {"success": True, "stats": ansible_result.stats}
    
    except Exception as e:
        deployment.status = DeploymentStatus.ERROR
        deployment.error_message = f"Unexpected error: {str(e)}"
        db.commit()
        add_log("error", f"Критическая ошибка: {str(e)}")
        
        # Retry logic
        retry_in = 60 * (self.request.retries + 1)
        raise self.retry(exc=e, countdown=retry_in)
    
    finally:
        db.close()
