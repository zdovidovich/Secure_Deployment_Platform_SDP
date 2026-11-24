"""
Мок ansible_runner для тестов.

Позволяет запускать код приложения (libs/ansible.py, services/deployment.py)
без установленного ansible-runner и без реальных серверов.

Управление поведением:
- ``set_run_result(result)`` — задать объект-результат, который вернет ``run()``;
- ``add_event(event_dict)`` — добавить событие, которое будет передано в
  ``event_handler`` (для проверки стриминга логов Ansible в SSE);
- ``reset()`` — сброс состояния между тестами;
- ``calls`` — список всех вызовов ``run()`` с их kwargs.
"""

from collections import namedtuple

RunCall = namedtuple("RunCall", ["kwargs"])

_state = {
    "result": None,
    "events": [],
}

calls = []


class MockRunnerResult:
    """Заглушка ansible_runner.Runner."""

    def __init__(
        self,
        status="successful",
        stats=None,
        stdout="",
        stderr="",
    ):
        self.status = status
        self.stats = stats if stats is not None else {}
        self._stdout = stdout
        self._stderr = stderr

    def stdout_read(self):
        return self._stdout

    def stderr_read(self):
        return self._stderr


def _make_result():
    if _state["result"] is not None:
        return _state["result"]

    class _DefaultResult:
        status = "successful"
        stats = {}

        @staticmethod
        def stdout_read():
            return ""

        @staticmethod
        def stderr_read():
            return ""

    return _DefaultResult()


def run(**kwargs):
    calls.append(RunCall(kwargs=kwargs))

    handler = kwargs.get("event_handler")
    if handler is not None:
        for event in _state["events"]:
            handler(event)

    return _make_result()


# --- helpers for tests -------------------------------------------------------


def set_run_result(result):
    _state["result"] = result


def add_event(event_dict):
    _state["events"].append(event_dict)


def reset():
    _state["result"] = None
    _state["events"] = []
    calls.clear()
