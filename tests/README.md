# Тесты SDP (pytest)

Юнит- и интеграционные тесты Python-части проекта. Реальные серверы,
Ansible, Trivy/Hadolint и Telegram **не требуются** — всё внешнее замокано.

## Запуск

```bash
pip install -r requirements-dev.txt   # pytest (+ существующие зависимости app)
pytest                                 # из корня репозитория
pytest -v                              # подробный вывод
pytest --cov=app --cov-report=term-missing   # с покрытием (нужен pytest-cov)
```

## Структура

| Файл | Что покрывает |
|---|---|
| `test_validation.py` | `libs/validation.py`: правила, мульти-серверные формы, tar/SSH-ключи, telegram chat_id |
| `test_api.py` | HTTP API `/api/v1/*`: health, API-ключ, создание/чтение деплоя, SSE, legacy-редиректы |
| `test_deployment_service.py` | Пайплайн `services/deployment.py`: успех, валидация, падение Ansible, живой стрим логов, клининг |
| `test_sse_broadcaster.py` | `sse/broadcaster.py`: каналы, события, изоляция сессий |
| `test_deployment_store.py` | `services/deployment_store.py`: уникальность ID, потокобезопасность |
| `test_scanners.py` | `libs/trivy.py`, `libs/hadolint.py`, `libs/scanner_base.py` (subprocess моканут) |
| `test_telegram_notifier.py` | `libs/telegram_notifier.py`: форматирование, экранирование, деградация без токена |
| `test_temp_files.py` | `libs/temp_files.py`: безопасное сохранение, inventory, cleanup |
| `test_ansible_lib.py` | `libs/ansible.py`: колбэк событий, параметры ansible-runner |
| `mocks/` | Мок `ansible_runner` и мок пакета `telegram` (ставятся в sys.modules автоматически в `conftest.py`, если настоящие пакеты не установлены) |

## Замечания

- Код приложения использует плоские импорты (`from libs...`), поэтому
  `conftest.py` добавляет `app/` в `sys.path`.
- Тесты намеренно не трогают сеть: Telegram Bot подменяется, subprocess для
  сканеров мокается, ansible-runner — полный mock.
