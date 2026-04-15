from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.core.database import Base


class DeploymentStatus(str, enum.Enum):
    """Статусы деплоя"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"


class Deployment(Base):
    """Модель деплоя"""
    __tablename__ = "deployments"
    
    id = Column(String(36), primary_key=True, index=True)
    status = Column(SQLEnum(DeploymentStatus), default=DeploymentStatus.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    # Параметры деплоя
    ansible_host = Column(String(255))
    ansible_port = Column(Integer, default=22)
    ansible_user = Column(String(255))
    app_deploy_image_name = Column(String(255))
    app_deploy_container_name = Column(String(255))
    app_host_port = Column(Integer)
    app_container_port = Column(Integer)
    
    # Пути к файлам
    ssh_key_path = Column(String(500))
    docker_image_path = Column(String(500))
    dockerfile_path = Column(String(500), nullable=True)
    
    # Опции
    enable_trivy = Column(String(10), default="off")
    trivy_fail_on = Column(String(20), default="HIGH")
    enable_selinux = Column(String(10), default="off")
    enable_fail2ban_for_ssh = Column(String(10), default="off")
    ssh_hardening_disable_pass = Column(String(10), default="off")
    app_deploy_ro_fs = Column(String(10), default="off")
    enable_container_fail2ban = Column(String(10), default="off")
    
    # Результаты
    result = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Логи (последние)
    logs = Column(JSON, default=list)
    
    # Celery task ID
    celery_task_id = Column(String(100), nullable=True)


class DeploymentLog(Base):
    """Модель логов деплоя (для истории)"""
    __tablename__ = "deployment_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    deployment_id = Column(String(36), index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    level = Column(String(20))  # info, warning, error, debug
    message = Column(Text)
    source = Column(String(50))  # deployment, hadolint, trivy, ansible
    details = Column(JSON, nullable=True)
