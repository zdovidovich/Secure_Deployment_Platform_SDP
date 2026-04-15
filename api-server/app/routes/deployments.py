from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
import uuid
import os
import aiofiles
from datetime import datetime

from app.core.database import get_db
from app.models.deployment import Deployment, DeploymentStatus, DeploymentLog
from app.models.schemas import (
    DeploymentCreate,
    DeploymentResponse,
    DeploymentListResponse,
    LogEntry,
    DeploymentLogsResponse
)
from app.core.config import settings
from worker.celery_app import celery_app


router = APIRouter(prefix="/deployments", tags=["Deployments"])


async def save_upload_file(file: UploadFile, prefix: str) -> str:
    """Сохраняет загруженный файл и возвращает путь"""
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    filename = f"{prefix}{uuid.uuid4().hex[:8]}_{file.filename}"
    file_path = os.path.join(settings.UPLOAD_DIR, filename)
    
    async with aiofiles.open(file_path, 'wb') as out_file:
        content = await file.read()
        await out_file.write(content)
    
    return file_path


@router.post("/", response_model=DeploymentResponse, status_code=201)
async def create_deployment(
    ansible_host: str = Form(...),
    ansible_port: int = Form(22),
    ansible_user: str = Form(...),
    app_deploy_image_name: str = Form(...),
    app_deploy_container_name: str = Form(...),
    app_host_port: int = Form(...),
    app_container_port: int = Form(...),
    ssh_key: UploadFile = File(..., description="SSH private key"),
    docker_image: UploadFile = File(..., description="Docker image tar file"),
    dockerfile: Optional[UploadFile] = File(None, description="Dockerfile (optional)"),
    # Опции
    enable_trivy: bool = Form(False),
    trivy_fail_on: str = Form("HIGH"),
    enable_selinux: bool = Form(False),
    enable_fail2ban_for_ssh: bool = Form(False),
    ssh_hardening_disable_pass: bool = Form(False),
    ssh_hardening_port: Optional[int] = Form(None),
    app_deploy_ro_fs: bool = Form(False),
    enable_container_fail2ban: bool = Form(False),
    # Дополнительные параметры
    app_deploy_cpus: Optional[float] = Form(None),
    app_deploy_memory: Optional[str] = Form(None),
    app_deploy_volumes: Optional[str] = Form(None),
    app_deploy_envs: Optional[str] = Form(None),
    fail2ban_configuration_app_log_path: str = Form("/var/log/app/access.log"),
    fail2ban_configuration_app_filter: str = Form("app-generic"),
    fail2ban_configuration_app_regex: str = Form(""),
    fail2ban_configuration_app_maxretry: int = Form(5),
    fail2ban_configuration_app_bantime: int = Form(86400),
    fail2ban_configuration_app_findtime: int = Form(7200),
    fail2ban_configuration_app_ports: Optional[int] = Form(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Создать новый деплой.
    
    - **ansible_host**: IP или hostname сервера
    - **ssh_key**: SSH private key файл
    - **docker_image**: Docker image в формате .tar
    - **dockerfile**: Dockerfile для сканирования (опционально)
    """
    deployment_id = uuid.uuid4().hex
    
    # Сохранение файлов
    try:
        ssh_key_path = await save_upload_file(ssh_key, "ssh_")
        docker_image_path = await save_upload_file(docker_image, "image_")
        dockerfile_path = None
        if dockerfile and dockerfile.filename:
            dockerfile_path = await save_upload_file(dockerfile, "dockerfile_")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save files: {str(e)}")
    
    # Парсинг списков и словарей из строк
    volumes = []
    if app_deploy_volumes:
        volumes = [v.strip() for v in app_deploy_volumes.split(",") if v.strip()]
    
    envs = {}
    if app_deploy_envs:
        try:
            import json
            envs = json.loads(app_deploy_envs)
        except:
            pass
    
    # Создание записи в БД
    deployment = Deployment(
        id=deployment_id,
        status=DeploymentStatus.PENDING,
        ansible_host=ansible_host,
        ansible_port=ansible_port,
        ansible_user=ansible_user,
        app_deploy_image_name=app_deploy_image_name,
        app_deploy_container_name=app_deploy_container_name,
        app_host_port=app_host_port,
        app_container_port=app_container_port,
        ssh_key_path=ssh_key_path,
        docker_image_path=docker_image_path,
        dockerfile_path=dockerfile_path,
        enable_trivy="on" if enable_trivy else "off",
        trivy_fail_on=trivy_fail_on,
        enable_selinux="on" if enable_selinux else "off",
        enable_fail2ban_for_ssh="on" if enable_fail2ban_for_ssh else "off",
        ssh_hardening_disable_pass="on" if ssh_hardening_disable_pass else "off",
        app_deploy_ro_fs="on" if app_deploy_ro_fs else "off",
        enable_container_fail2ban="on" if enable_container_fail2ban else "off",
        # Сохраняем дополнительные параметры в JSON для гибкости
        result={
            "app_deploy_cpus": app_deploy_cpus,
            "app_deploy_memory": app_deploy_memory,
            "app_deploy_volumes": volumes,
            "app_deploy_envs": envs,
            "fail2ban_configuration_app_log_path": fail2ban_configuration_app_log_path,
            "fail2ban_configuration_app_filter": fail2ban_configuration_app_filter,
            "fail2ban_configuration_app_regex": fail2ban_configuration_app_regex,
            "fail2ban_configuration_app_maxretry": fail2ban_configuration_app_maxretry,
            "fail2ban_configuration_app_bantime": fail2ban_configuration_app_bantime,
            "fail2ban_configuration_app_findtime": fail2ban_configuration_app_findtime,
            "fail2ban_configuration_app_ports": fail2ban_configuration_app_ports or app_host_port,
            "ssh_hardening_port": ssh_hardening_port or ansible_port,
        }
    )
    
    db.add(deployment)
    await db.flush()
    
    # Запуск Celery задачи
    try:
        task = celery_app.send_task(
            "worker.tasks.run_deployment",
            args=[deployment_id],
            queue="deployments"
        )
        deployment.celery_task_id = task.id
        deployment.status = DeploymentStatus.RUNNING
    except Exception as e:
        deployment.status = DeploymentStatus.ERROR
        deployment.error_message = f"Failed to start deployment task: {str(e)}"
    
    await db.commit()
    await db.refresh(deployment)
    
    return deployment


@router.get("/{deployment_id}", response_model=DeploymentResponse)
async def get_deployment(deployment_id: str, db: AsyncSession = Depends(get_db)):
    """Получить информацию о деплое"""
    result = await db.execute(
        select(Deployment).where(Deployment.id == deployment_id)
    )
    deployment = result.scalar_one_or_none()
    
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    
    return deployment


@router.get("/", response_model=DeploymentListResponse)
async def list_deployments(
    limit: int = 20,
    offset: int = 0,
    status: Optional[DeploymentStatus] = None,
    db: AsyncSession = Depends(get_db)
):
    """Получить список деплоев с пагинацией"""
    query = select(Deployment)
    
    if status:
        query = query.where(Deployment.status == status)
    
    query = query.order_by(Deployment.created_at.desc()).offset(offset).limit(limit)
    
    result = await db.execute(query)
    deployments = result.scalars().all()
    
    # Получаем общее количество
    count_query = select(Deployment.id)
    if status:
        count_query = count_query.where(Deployment.status == status)
    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())
    
    return DeploymentListResponse(
        deployments=deployments,
        total=total
    )


@router.get("/{deployment_id}/stream")
async def stream_logs(deployment_id: str, db: AsyncSession = Depends(get_db)):
    """
    SSE endpoint для стриминга логов в реальном времени.
    
    Подключайтесь через EventSource:
    ```javascript
    const eventSource = new EventSource('/api/v1/deployments/{id}/stream');
    eventSource.onmessage = (event) => {
        console.log(JSON.parse(event.data));
    };
    ```
    """
    from fastapi.responses import StreamingResponse
    import asyncio
    import json
    
    async def generate():
        last_log_count = 0
        
        while True:
            result = await db.execute(
                select(Deployment).where(Deployment.id == deployment_id)
            )
            deployment = result.scalar_one_or_none()
            
            if not deployment:
                yield f"data: {json.dumps({'error': 'Deployment not found'})}\n\n"
                break
            
            # Отправляем новые логи
            current_logs = deployment.logs or []
            if len(current_logs) > last_log_count:
                new_logs = current_logs[last_log_count:]
                for log in new_logs:
                    yield f"data: {json.dumps(log)}\n\n"
                last_log_count = len(current_logs)
            
            # Если деплой завершен
            if deployment.status in [DeploymentStatus.SUCCESS, DeploymentStatus.ERROR, DeploymentStatus.CANCELLED]:
                yield f"data: {json.dumps({'type': 'finished', 'status': deployment.status})}\n\n"
                await asyncio.sleep(2)
                break
            
            await asyncio.sleep(0.5)
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/{deployment_id}/logs", response_model=DeploymentLogsResponse)
async def get_deployment_logs(deployment_id: str, db: AsyncSession = Depends(get_db)):
    """Получить все логи деплоя"""
    result = await db.execute(
        select(Deployment).where(Deployment.id == deployment_id)
    )
    deployment = result.scalar_one_or_none()
    
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    
    logs = [LogEntry(**log) for log in (deployment.logs or [])]
    
    return DeploymentLogsResponse(
        deployment_id=deployment_id,
        status=deployment.status,
        logs=logs
    )


@router.delete("/{deployment_id}", status_code=204)
async def delete_deployment(deployment_id: str, db: AsyncSession = Depends(get_db)):
    """Удалить деплой"""
    result = await db.execute(
        select(Deployment).where(Deployment.id == deployment_id)
    )
    deployment = result.scalar_one_or_none()
    
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    
    # Удаляем файлы
    for file_path in [deployment.ssh_key_path, deployment.docker_image_path, deployment.dockerfile_path]:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass
    
    await db.delete(deployment)
    await db.commit()
