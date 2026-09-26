import ansible_runner
import os
from typing import Callable, Optional

from libs.utils import get_project_root

# Типы событий Ansible Runner, которые относятся к конкретному хосту.
# Используются потребителями (например, DeploymentService) для фильтрации.
HOST_EVENT_TYPES = {
    "runner_on_start",
    "runner_on_ok",
    "runner_on_failed",
    "runner_on_unreachable",
    "runner_on_skipped",
    "runner_on_error",
    "runner_on_async_failed",
    "runner_item_on_ok",
    "runner_item_on_failed",
    "runner_item_on_skipped",
}


def get_base_dir_ansible():
    return os.path.join(get_project_root(), "..", "ansible")


def _get_event_host(event_data: dict) -> Optional[str]:
    """Достаёт имя хоста из события ansible-runner (для любых типов событий)."""
    data = event_data.get("event_data") or {}
    runner = data.get("runner") or {}
    return runner.get("host") or data.get("host")


def make_host_event_callback(
    on_host_event: Callable[[str, str, dict], None]
) -> Callable[[dict], None]:
    """
    Оборачивает колбэк «по хостам» в формат event_handler ansible-runner.

    Args:
        on_host_event: функция (event_type, host, event_data), вызывается
                       только для событий, привязанных к конкретному хосту.

    Возвращает callback, который можно передать в run_playbook/run_full_configuring,
    чтобы стримить логи каждой машины из inventory в реальном времени.
    """

    def callback(event_data: dict):
        try:
            event_type = event_data.get("event", "")
            host = _get_event_host(event_data)
            if not host:
                return True
            on_host_event(event_type, host, event_data)
        except Exception:
            # Логи не должны ронять процесс деплоя
            pass
        # ansible-runner трактует возвращаемое значение как "сохранять ли
        # событие в job_events". Любое falsy-значение (в т.ч. None) отключает
        # запись, из-за чего Runner.stats (читает job_events с диска) вернёт
        # None и итоговые статусы серверов сломаются. Возвращаем True —
        # это поведение ansible-runner по умолчанию.
        return True

    return callback


def run_check(file_path_inventory, event_callback: Optional[Callable] = None):
    """
    Пингует все хосты inventory (поддерживает несколько серверов сразу).
    Возвращает ansible_runner.Runner; у результата доступны .stats и .stdout.
    """
    kwargs = {}
    if event_callback is not None:
        # ansible-runner ожидает параметр event_handler (не event_callback):
        # иначе неизвестный ключ утекает в RunnerConfig/BaseConfig и падает
        # с "BaseConfig.__init__() got an unexpected keyword argument".
        kwargs["event_handler"] = event_callback
    result = ansible_runner.run(
        private_data_dir=get_base_dir_ansible(),
        inventory=file_path_inventory,
        module="ping",
        host_pattern="all",
        envvars={"ANSIBLE_NOCOLOR": "true"},
        **kwargs,
    )
    return result


def run_full_configuring(
    extravars: dict,
    file_path_inventory,
    event_callback: Optional[Callable] = None,
    forks: int = 10,
):
    """
    Запускает configure.yml сразу на всех хостах inventory.
    Ansible сам распараллеливает настройку серверов (forks — поток на хост).
    """
    return run_playbook(
        "configure.yml",
        extravars,
        file_path_inventory,
        event_callback=event_callback,
        forks=forks,
    )


def run_playbook(
    playbook,
    extravars: dict,
    file_path_inventory,
    event_callback: Optional[Callable] = None,
    forks: int = 10,
):
    extravars.update({"ansible_become": "True"})
    kwargs = {}
    if event_callback is not None:
        # Вызывается для каждого события Ansible (в т.ч. с привязкой к хосту),
        # что позволяет стримить логи каждой машины в реальном времени.
        # Важно: ansible-runner принимает именно event_handler.
        kwargs["event_handler"] = event_callback
    result = ansible_runner.run(
        private_data_dir=get_base_dir_ansible(),
        inventory=file_path_inventory,
        playbook=os.path.join(get_base_dir_ansible(), playbook),
        host_pattern="all",
        extravars=extravars,
        envvars={"ANSIBLE_NOCOLOR": "true"},
        forks=forks,
        **kwargs,
    )
    return result


def run_role(
    role,
    extravars: dict,
    file_path_inventory,
    event_callback: Optional[Callable] = None,
):
    extravars.update({"ansible_become": "True"})
    kwargs = {}
    if event_callback is not None:
        # ansible-runner принимает callback событий под именем event_handler
        kwargs["event_handler"] = event_callback
    result = ansible_runner.run(
        private_data_dir=get_base_dir_ansible(),
        inventory=file_path_inventory,
        role=role,
        host_pattern="all",
        extravars=extravars,
        envvars={"ANSIBLE_NOCOLOR": "true"},
        **kwargs,
    )
    return result.stdout.read()
