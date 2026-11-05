"""
Уведомления о ходе деплоя в Telegram.

Как это работает:
1. В env приложения задаётся токен бота: TELEGRAM_BOT_TOKEN (получить у @BotFather).
2. Пользователь вводит свой chat_id в поле «Telegram chat id» главной формы
   (узнать его можно у @userinfobot) — он сохраняется в настройках браузера
   (localStorage) и подставляется при каждом следующем деплое.
3. Во время деплоя приложение отправляет в чат сообщения: старт, успех,
   провал и критическую ошибку.

Если токен не задан или bot/python-telegram-bot недоступен, уведомления
просто молча отключаются — на ход деплоя это не влияет.
"""

import html
import logging
import os
import threading
from typing import Optional

try:
    from telegram import Bot
    from telegram.constants import ParseMode
    from telegram.error import TelegramError

    _PTB_AVAILABLE = True
except ImportError:  # pragma: no cover - fallback если зависимость не установлена
    Bot = None  # type: ignore[assignment]
    ParseMode = None  # type: ignore[assignment]
    TelegramError = Exception  # type: ignore[assignment,misc]
    _PTB_AVAILABLE = False

logger = logging.getLogger(__name__)


def get_bot_token() -> Optional[str]:
    """Токен бота из окружения (пустая строка трактуется как «не задан»)."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    return token or None


def _is_configured() -> bool:
    return _PTB_AVAILABLE and get_bot_token() is not None


def _clean_message(text: str) -> str:
    """Ограничивает длину и экранирует HTML-спецсимволы."""
    text = (text or "").strip()[:1500]
    return html.escape(text)


class TelegramNotifier:
    """
    Синхронная обёртка над python-telegram-bot.

    Библиотека асинхронная, а деплой выполняется в обычном потоке, поэтому
    каждый запрос запускается в собственном временном event loop.
    Ошибки доставки не должны прерывать деплой — они только логируются.
    """

    def __init__(self, token: Optional[str] = None):
        self.token = token or get_bot_token()
        if not _PTB_AVAILABLE:
            raise RuntimeError("python-telegram-bot не установлен")
        if not self.token:
            raise RuntimeError("Не задан TELEGRAM_BOT_TOKEN")

    def send(self, chat_id, text: str) -> int:
        """
        Отправляет сообщение в чат `chat_id`. Возвращает 1 при успехе, 0 иначе.
        """
        chat_id = str(chat_id or "").strip()
        if not chat_id:
            return 0
        try:
            import asyncio

            async def _send():
                bot = Bot(token=self.token)
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                )

            asyncio.run(_send())
            return 1
        except TelegramError as exc:
            logger.warning(f"Telegram: не удалось отправить уведомление: {exc}")
            return 0
        except Exception as exc:  # noqa: BLE001 — уведомления не должны ронять деплой
            logger.warning(f"Telegram: ошибка отправки уведомления: {exc}")
            return 0

    def send_async(self, chat_id, text: str) -> None:
        """Отправка в отдельном потоке (чтобы не блокировать пайплайн деплоя)."""
        thread = threading.Thread(
            target=self.send, args=(chat_id, text), daemon=True
        )
        thread.start()


# ---------------------------------------------------------------------------
# Публичные функции уведомлений о фазах деплоя
# ---------------------------------------------------------------------------


def notify_deploy_started(
    deployment_id: str, server_count: int, *, chat_id=None
) -> int:
    if not _is_configured():
        return 0

    text = (
        "<b>🚀 Начался деплой</b>\n"
        f"<b>ID:</b> <code>{deployment_id}</code>\n"
        f"<b>Серверов:</b> <code>{server_count}</code>"
    )
    return TelegramNotifier().send(chat_id, text)


def notify_deploy_success(
    deployment_id: str,
    *,
    server_count: int,
    message: Optional[str] = None,
    chat_id=None,
) -> int:
    if not _is_configured():
        return 0

    body = (
        "<b>✅ Деплой успешно завершён</b>\n"
        f"<b>ID:</b> <code>{deployment_id}</code>\n"
        f"<b>Серверов:</b> <code>{server_count}</code>"
    )
    if message:
        body += "\n" + _clean_message(message)
    return TelegramNotifier().send(chat_id, body)


def notify_deploy_failed(
    deployment_id: str, error: str, *, server_count: int = 0, chat_id=None
) -> int:
    if not _is_configured():
        return 0

    body = (
        "<b>❌ Деплой не удался</b>\n"
        f"<b>ID:</b> <code>{deployment_id}</code>\n"
        f"<b>Серверов:</b> <code>{server_count}</code>"
    )
    if error:
        body += f"\n<b>Причина:</b>\n<code>{_clean_message(error)}</code>"
    return TelegramNotifier().send(chat_id, body)


def notify_deploy_error(exception, *, chat_id=None) -> int:
    if not _is_configured():
        return 0

    safe_message = _clean_message(str(exception))
    body = f"<b>💥 Критическая ошибка деплоя</b>\n<code>{safe_message}</code>"
    return TelegramNotifier().send(chat_id, body)
