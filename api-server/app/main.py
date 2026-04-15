from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.database import init_db
from app.routes import deployments


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Инициализация при запуске приложения"""
    # Создание таблиц БД
    await init_db()
    yield
    # Очистка при остановке (если нужно)


app = FastAPI(
    title="Secure Deployment Platform API",
    description="API для управления деплоями с использованием Trivy, Hadolint и Ansible",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене указать конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Регистрация роутеров
app.include_router(deployments.router, prefix=settings.API_PREFIX)


@app.get("/")
async def root():
    """Корневой эндпоинт"""
    return {
        "message": "Secure Deployment Platform API",
        "docs": "/docs",
        "redoc": "/redoc"
    }


@app.get("/health")
async def health_check():
    """Проверка здоровья сервиса"""
    return {"status": "healthy"}
