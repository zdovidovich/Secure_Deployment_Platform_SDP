"""
Мок python-telegram-bot (пакет ``telegram``).

Тесты не должны ходить в сеть; подменяем модуль целиком.
"""


class Bot:
    def __init__(self, token, **kwargs):
        self.token = token

    async def send_message(self, chat_id, text, **kwargs):
        return {"chat_id": chat_id, "text": text}


class ParseMode:
    HTML = "HTML"
