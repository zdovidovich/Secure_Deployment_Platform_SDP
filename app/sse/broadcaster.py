# app/sse/broadcaster.py
import threading
import time
import json
from typing import Dict, List
from datetime import datetime

class LogEntry:
    """Одно событие лога"""
    def __init__(self, level: str, message: str, source: str = "deployment", details: dict = None):
        self.timestamp = datetime.utcnow().isoformat() + "Z"
        self.level = level  # "info", "warning", "error", "debug"
        self.message = message
        self.source = source  # "deployment", "hadolint", "trivy", "ansible"
        self.details = details or {}
    
    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "level": self.level,
            "message": self.message,
            "source": self.source,
            "details": self.details
        }


class SSEBroadcaster:
    """
    Управляет SSE-каналами для каждой сессии деплоя.
    Потокобезопасный (использует Lock).
    """
    
    # Статическое хранилище: { session_id: Queue[LogEntry] }
    _channels: Dict[str, List[LogEntry]] = {}
    _lock = threading.Lock()
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self._ensure_channel()
    
    def _ensure_channel(self):
        """Создаёт очередь для сессии, если нет"""
        with SSEBroadcaster._lock:
            if self.session_id not in SSEBroadcaster._channels:
                SSEBroadcaster._channels[self.session_id] = []
    
    def send(self, entry: LogEntry):
        """Отправляет событие в канал сессии"""
        with SSEBroadcaster._lock:
            if self.session_id in SSEBroadcaster._channels:
                SSEBroadcaster._channels[self.session_id].append(entry)
    
    def info(self, message: str):
        self.send(LogEntry(level="info", message=message))
    
    def warning(self, message: str):
        self.send(LogEntry(level="warning", message=message))
    
    def error(self, message: str):
        self.send(LogEntry(level="error", message=message))
    
    def debug(self, message: str):
        self.send(LogEntry(level="debug", message=message))
    
    def hadolint(self, formatted_output: str):
        self.send(LogEntry(
            level="info",
            message="Отчёт Hadolint",
            source="hadolint",
            details={"report": formatted_output}
        ))
    
    def trivy(self, formatted_output: str):
        self.send(LogEntry(
            level="info",
            message="Отчёт Trivy",
            source="trivy",
            details={"report": formatted_output}
        ))
    
    def ansible(self, log_line: str):
        self.send(LogEntry(
            level="debug",
            message=log_line,
            source="ansible"
        ))
    
    def complete(self, result: dict):
        """Событие завершения деплоя"""
        self.send(LogEntry(
            level="info",
            message="Деплой завершён",
            details={"type": "completion", "result": result}
        ))
    
    @classmethod
    def get_events(cls, session_id: str, last_index: int = 0) -> List[dict]:
        """Получить новые события для сессии (для SSE-потока)"""
        with cls._lock:
            if session_id not in cls._channels:
                return []
            events = cls._channels[session_id][last_index:]
            return [e.to_dict() for e in events]
    
    @classmethod
    def cleanup_session(cls, session_id: str):
        """Удалить сессию из памяти (после завершения)"""
        with cls._lock:
            if session_id in cls._channels:
                del cls._channels[session_id]
    
    @classmethod
    def cleanup_old_sessions(cls, max_age_hours: int = 24):
        """Очистка старых сессий (можно вызвать по cron)"""
        # Для простоты пока не реализуем
        pass