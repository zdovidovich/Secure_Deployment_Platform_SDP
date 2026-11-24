"""Тесты Telegram-уведомлений (libs/telegram_notifier.py).

Сеть не используется: проверяются форматирование, экранирование и то, что
без токена/библиотеки уведомления молча отключаются и не ломают деплой.
"""

import pytest

from libs import telegram_notifier as tn
from libs.telegram_notifier import (
    TelegramNotifier,
    get_bot_token,
    notify_deploy_error,
    notify_deploy_failed,
    notify_deploy_started,
    notify_deploy_success,
)


class TestConfig:
    def test_no_token_returns_none(self):
        assert get_bot_token() is None

    def test_empty_string_token_treated_as_missing(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "   ")
        assert get_bot_token() is None

    def test_token_read_from_env(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
        assert get_bot_token() == "123:abc"

    def test_notifier_requires_token(self):
        with pytest.raises(RuntimeError):
            TelegramNotifier(token=None)  # env пуст (clean_environment)


class TestDisabledWithoutToken:
    """Без TELEGRAM_BOT_TOKEN все notify_* должны возвращать 0 без исключений."""

    def test_started(self):
        assert notify_deploy_started("dep1", 2, chat_id="111") == 0

    def test_success(self):
        assert notify_deploy_success("dep1", server_count=1, chat_id="111") == 0

    def test_failed(self):
        assert notify_deploy_failed("dep1", "err", chat_id="111") == 0

    def test_error(self):
        assert notify_deploy_error(ValueError("boom"), chat_id="111") == 0


class TestCleanMessage:
    def test_escapes_html(self):
        out = tn._clean_message("<script>alert('x')</script>")
        assert "<script>" not in out
        assert "&lt;script&gt;" in out

    def test_truncates_to_1500(self):
        assert len(tn._clean_message("x" * 5000)) == 1500


class TestSendWithMockedBot:
    """Отправка с подменённым Bot: проверяем корректность вызова."""

    def _make_notifier_with_capture(self, monkeypatch):
        sent = []

        class CapturingBot:
            def __init__(self, token, **kwargs):
                self.token = token

            async def send_message(self, chat_id, text, **kwargs):
                sent.append({"chat_id": chat_id, "text": text, **kwargs})

        monkeypatch.setattr(tn, "Bot", CapturingBot)
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:token")
        return tn.TelegramNotifier(), sent

    def test_send_success(self, monkeypatch):
        notifier, sent = self._make_notifier_with_capture(monkeypatch)
        assert notifier.send("42", "hello") == 1
        assert sent[0]["chat_id"] == "42"
        assert sent[0]["text"] == "hello"

    def test_send_empty_chat_id_skipped(self, monkeypatch):
        notifier, sent = self._make_notifier_with_capture(monkeypatch)
        assert notifier.send("", "hello") == 0
        assert sent == []

    def test_send_swallows_exceptions(self, monkeypatch):
        class BrokenBot:
            def __init__(self, token, **kwargs):
                pass

            async def send_message(self, *args, **kwargs):
                raise RuntimeError("network down")

        monkeypatch.setattr(tn, "Bot", BrokenBot)
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:token")
        notifier = tn.TelegramNotifier()
        # ошибка сети не должна всплывать наружу
        assert notifier.send("42", "hello") == 0

    def test_notify_messages_contain_deployment_id(self, monkeypatch):
        _, sent = self._make_notifier_with_capture(monkeypatch)
        monkeypatch.setattr(tn, "_PTB_AVAILABLE", True)

        tn.notify_deploy_started("abc123", 3, chat_id="42")
        assert "abc123" in sent[-1]["text"]

        tn.notify_deploy_success("abc123", server_count=3, message="ok", chat_id="42")
        assert "✅" in sent[-1]["text"]

        tn.notify_deploy_failed("abc123", "Ansible failed", server_count=2, chat_id="42")
        assert "❌" in sent[-1]["text"] and "Ansible failed" in sent[-1]["text"]

        tn.notify_deploy_error(ValueError("kaboom"), chat_id="42")
        assert "💥" in sent[-1]["text"] and "kaboom" in sent[-1]["text"]
