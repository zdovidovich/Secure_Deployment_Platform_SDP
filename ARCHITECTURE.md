# Архитектура API-сервиса для Secure Deployment Platform

## Обзор архитектуры

Предлагается микросервисная архитектура с разделением на:

1. **API Server (FastAPI)** - REST API для приема запросов
2. **Task Queue (Redis + Celery)** - очередь задач для асинхронного выполнения
3. **Worker** - воркеры для выполнения сканирований и Ansible playbook
4. **Frontend (Flask или React)** - веб-интерфейс (опционально)
5. **Database (PostgreSQL/SQLite)** - хранение истории деплоев и статусов

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Frontend   │────▶│  API Server  │────▶│    Redis    │
│  (Flask/    │◀────│  (FastAPI)   │◀────│  (Broker)   │
│   React)    │ SSE │              │     └─────────────┘
└─────────────┘     └──────────────┘           │
       ▲                                      ▼
       │                              ┌─────────────┐
       │                              │   Worker    │
       │                              │  (Celery)   │
       │                              └─────────────┘
       │                                      │
       │                                      ▼
       │                              ┌─────────────┐
       │                              │   Tools     │
       │                              │ - Trivy     │
       │                              │ - Hadolint  │
       │                              │ - Ansible   │
       │                              └─────────────┘
       │
       │     ┌──────────────┐
       └─────│   Database   │
             │  (PostgreSQL)│
             └──────────────┘
```

## Преимущества такой архитектуры

1. **Масштабируемость** - можно добавлять воркеры горизонтально
2. **Асинхронность** - API не блокируется во время выполнения долгих операций
3. **Надежность** - задачи не теряются при перезапуске API
4. **Разделение ответственности** - API принимает запросы, воркеры выполняют
5. **Real-time обновления** - SSE/WebSocket для стриминга логов

## Структура проекта

```
/workspace/
├── api-server/           # FastAPI сервер
│   ├── app/
│   │   ├── main.py       # Точка входа
│   │   ├── core/         # Конфигурация, безопасность
│   │   ├── models/       # Pydantic модели
│   │   ├── routes/       # API эндпоинты
│   │   ├── services/     # Бизнес-логика
│   │   └── libs/         # Утилиты
│   ├── worker/           # Celery воркер
│   │   ├── celery_app.py
│   │   └── tasks/        # Задачи Celery
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/             # Flask фронтенд (опционально)
│   └── app/
├── docker-compose.yml    # Оркестрация всех сервисов
└── README.md
```

## Реализация

### 1. API Server (FastAPI)

**Основные эндпоинты:**
- `POST /api/v1/deployments` - создать новый деплой
- `GET /api/v1/deployments/{id}` - получить статус деплоя
- `GET /api/v1/deployments/{id}/stream` - SSE стрим логов
- `GET /api/v1/deployments` - список всех деплоев
- `DELETE /api/v1/deployments/{id}` - удалить деплой

### 2. Task Queue (Celery + Redis)

**Задачи:**
- `run_deployment(deployment_id)` - основная задача деплоя
- `scan_dockerfile(dockerfile_path)` - сканирование Hadolint
- `scan_image(image_path)` - сканирование Trivy
- `run_ansible(inventory_path, extra_vars)` - запуск Ansible

### 3. База данных

**Модели:**
- `Deployment` - информация о деплое (статус, логи, результаты)
- `ScanResult` - результаты сканирований

### 4. Frontend (Flask)

- Форма загрузки файлов
- Страница статуса с SSE
- История деплоев

## Пошаговая реализация

См. файлы в директории `/workspace/api-server/` и `/workspace/frontend/`
