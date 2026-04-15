from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any
from datetime import datetime
from enum import Enum


class DeploymentStatusEnum(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"


class DeploymentCreate(BaseModel):
    """Модель для создания деплоя"""
    ansible_host: str = Field(..., description="IP или hostname сервера")
    ansible_port: int = Field(default=22, ge=1, le=65535)
    ansible_user: str = Field(..., description="Пользователь SSH")
    
    app_deploy_image_name: str = Field(..., description="Имя образа Docker")
    app_deploy_container_name: str = Field(..., description="Имя контейнера")
    app_host_port: int = Field(..., ge=1, le=65535)
    app_container_port: int = Field(..., ge=1, le=65535)
    
    # Опциональные поля
    app_deploy_cpus: Optional[float] = Field(None, ge=0)
    app_deploy_memory: Optional[str] = None  # например "512m", "1g"
    app_deploy_volumes: Optional[List[str]] = []
    app_deploy_envs: Optional[Dict[str, str]] = {}
    
    # Опции безопасности
    enable_trivy: bool = False
    trivy_fail_on: str = Field(default="HIGH", pattern="^(CRITICAL|HIGH|MEDIUM|LOW|NONE)$")
    enable_selinux: bool = False
    enable_fail2ban_for_ssh: bool = False
    ssh_hardening_disable_pass: bool = False
    ssh_hardening_port: Optional[int] = None
    app_deploy_ro_fs: bool = False
    enable_container_fail2ban: bool = False
    
    # Fail2ban для приложения
    fail2ban_configuration_app_log_path: Optional[str] = "/var/log/app/access.log"
    fail2ban_configuration_app_filter: Optional[str] = "app-generic"
    fail2ban_configuration_app_regex: Optional[str] = ""
    fail2ban_configuration_app_maxretry: int = Field(default=5, ge=1)
    fail2ban_configuration_app_bantime: int = Field(default=86400, ge=0)
    fail2ban_configuration_app_findtime: int = Field(default=7200, ge=0)
    fail2ban_configuration_app_ports: Optional[int] = None


class DeploymentResponse(BaseModel):
    """Модель ответа с информацией о деплое"""
    id: str
    status: DeploymentStatusEnum
    created_at: datetime
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    ansible_host: str
    ansible_port: int
    ansible_user: str
    app_deploy_image_name: str
    app_deploy_container_name: str
    app_host_port: int
    app_container_port: int
    
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    celery_task_id: Optional[str] = None
    
    class Config:
        from_attributes = True


class DeploymentListResponse(BaseModel):
    """Модель списка деплоев"""
    deployments: List[DeploymentResponse]
    total: int


class LogEntry(BaseModel):
    """Модель записи лога"""
    timestamp: datetime
    level: str
    message: str
    source: str
    details: Optional[Dict[str, Any]] = None


class DeploymentLogsResponse(BaseModel):
    """Модель ответа с логами"""
    deployment_id: str
    status: DeploymentStatusEnum
    logs: List[LogEntry]
