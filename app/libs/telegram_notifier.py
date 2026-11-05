def notify_deploy_started(deployment_id: str, server_count: int) -> int:
    if not _is_configured():
        return 0

    text = (
        "<b>🚀 Начался деплой</b>\n"
        f"<b>ID:</b> <code>{deployment_id}</code>\n"
        f"<b>Серверов:</b> <code>{server_count}</code>"
    )
    return TelegramNotifier().send(text)


def notify_deploy_success(
    deployment_id: str,
    *,
    server_count: int,
    message: Optional[str] = None,
) -> int:
    if not _is_configured():
        return 0

    body = (
        "<b>✅ Деплой успешно завершён</b>\n"
        f"<b>ID:</b> <code>{deployment_id}</code>\n"
        f"<b>Серверов:</b> <code>{server_count}</code>"
    )
    if message:
        body += "\n" + message
    return TelegramNotifier().send(body)


def notify_deploy_failed(deployment_id: str, error: str, *, server_count: int = 0) -> int:
    if not _is_configured():
        return 0

    body = (
        "<b>❌ Деплой не удался</b>\n"
        f"<b>ID:</b> <code>{deployment_id}</code>\n"
        f"<b>Серверов:</b> <code>{server_count}</code>"
    )
    if error:
        body += f"\n<b>Причина:</b>\n<code>{error}</code>"
    return TelegramNotifier().send(body)


def notify_deploy_error(exception: Exception) -> int:
    if not _is_configured():
        return 0

    safe_message = _clean_message(str(exception))
    body = "<b>💥 Критическая ошибка деплоя</b>\n" f"<code>{safe_message}</code>"
    return TelegramNotifier().send(body)
