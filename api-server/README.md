# API-сервер Secure Deployment Platform

## Быстрый старт

### Через Docker Compose (рекомендуется)

```bash
# Запуск всех сервисов
docker-compose up -d

# Просмотр логов
docker-compose logs -f api
docker-compose logs -f worker

# Остановка
docker-compose down
```

Сервисы будут доступны по адресам:
- API: http://localhost:8000
- Frontend: http://localhost:3000
- Redis: localhost:6379
- Swagger docs: http://localhost:8000/docs

### Локальная разработка

#### 1. Установка зависимостей

```bash
cd api-server
pip install -r requirements.txt
```

#### 2. Запуск Redis

```bash
docker run -d -p 6379:6379 redis:7-alpine
```

#### 3. Запуск API сервера

```bash
cd api-server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### 4. Запуск Celery worker

```bash
cd api-server
celery -A worker.celery_app worker --loglevel=info -Q deployments -c 2
```

#### 5. Запуск Frontend (опционально)

```bash
cd frontend
pip install -r requirements.txt
python app/app.py
```

## API Endpoints

### Deployments

- `POST /api/v1/deployments/` - Создать новый деплой
- `GET /api/v1/deployments/` - Список деплоев
- `GET /api/v1/deployments/{id}` - Получить статус деплоя
- `GET /api/v1/deployments/{id}/stream` - SSE стрим логов
- `GET /api/v1/deployments/{id}/logs` - Получить все логи
- `DELETE /api/v1/deployments/{id}` - Удалить деплой

### Пример использования API

```bash
# Создание деплоя
curl -X POST http://localhost:8000/api/v1/deployments/ \
  -F "ansible_host=192.168.1.100" \
  -F "ansible_port=22" \
  -F "ansible_user=root" \
  -F "app_deploy_image_name=myapp" \
  -F "app_deploy_container_name=myapp-container" \
  -F "app_host_port=8080" \
  -F "app_container_port=80" \
  -F "enable_trivy=true" \
  -F "trivy_fail_on=HIGH" \
  -F "ssh_key=@~/.ssh/id_rsa" \
  -F "docker_image=@myapp.tar"

# Получение статуса
curl http://localhost:8000/api/v1/deployments/{deployment_id}

# Подключение к SSE стриму (JavaScript)
const eventSource = new EventSource('http://localhost:8000/api/v1/deployments/{id}/stream');
eventSource.onmessage = (event) => {
    console.log(JSON.parse(event.data));
};
```

## Архитектура

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Frontend   │────▶│  API Server  │────▶│    Redis    │
│  (Flask)    │◀────│  (FastAPI)   │◀────│  (Broker)   │
└─────────────┘     └──────────────┘     └─────────────┘
                                              │
                                              ▼
                                       ┌─────────────┐
                                       │   Worker    │
                                       │  (Celery)   │
                                       └─────────────┘
                                              │
                                              ▼
                                       ┌─────────────┐
                                       │   Tools     │
                                       │ - Trivy     │
                                       │ - Hadolint  │
                                       │ - Ansible   │
                                       └─────────────┘
```

## Переменные окружения

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| DATABASE_URL | URL базы данных | sqlite+aiosqlite:///./deployments.db |
| REDIS_URL | URL Redis | redis://localhost:6379/0 |
| CELERY_BROKER_URL | Broker для Celery | redis://localhost:6379/0 |
| CELERY_RESULT_BACKEND | Backend для результатов | redis://localhost:6379/0 |
| UPLOAD_DIR | Директория для загрузок | /tmp/sdp_uploads |
| TRIVY_PATH | Путь к бинарнику Trivy | trivy |
| HADOLINT_PATH | Путь к бинарнику Hadolint | hadolint |
| ANSIBLE_BASE_DIR | Директория Ansible | /app/ansible |

## Требования

- Python 3.11+
- Redis 7+
- Docker (опционально, для контейнеризации)
- Trivy
- Hadolint
- Ansible
