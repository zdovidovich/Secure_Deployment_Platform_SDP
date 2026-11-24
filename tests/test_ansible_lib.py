"""Тесты обёртки над ansible-runner (libs/ansible.py).

Реальный ansible не запускается — модуль ansible_runner подменён моком.
"""

import os

import pytest

from libs import ansible as ansible_lib
from libs.ansible import (
    _get_event_host,
    get_base_dir_ansible,
    make_host_event_callback,
    run_check,
    run_full_configuring,
    run_playbook,
)
from mocks import ansible_runner as mock_ar


class TestPaths:
    def test_base_dir_points_to_repo_ansible(self):
        base = get_base_dir_ansible()
        assert os.path.basename(os.path.normpath(base)) == "ansible"
        assert os.path.isdir(base)


class TestGetEventHost:
    def test_runner_nested_host(self):
        event = {"event_data": {"runner": {"host": "server_1_abcd"}}}
        assert _get_event_host(event) == "server_1_abcd"

    def test_flat_host(self):
        assert _get_event_host({"event_data": {"host": "h1"}}) == "h1"

    def test_no_host(self):
        assert _get_event_host({}) is None
        assert _get_event_host({"event_data": {}}) is None


class TestMakeHostEventCallback:
    def test_host_event_routed(self):
        seen = []
        cb = make_host_event_callback(
            lambda t, h, d: seen.append(("host", t, h)),
            lambda t, d: seen.append(("other", t)),
        )
        result = cb(
            {"event": "runner_on_ok", "event_data": {"runner": {"host": "h1"}}}
        )
        assert result is True  # ansible-runner требует truthy return
        assert ("host", "runner_on_ok", "h1") in seen

    def test_other_event_routed(self):
        seen = []
        cb = make_host_event_callback(
            lambda *a: None, lambda t, d: seen.append(t)
        )
        cb({"event": "playbook_on_start", "event_data": {}})
        assert seen == ["playbook_on_start"]

    def test_exception_inside_handler_swallowed(self):
        def boom(*args):
            raise RuntimeError("handler crashed")

        cb = make_host_event_callback(boom, None)
        # не должно выбрасывать наружу — иначе упадёт весь стрим логов
        assert cb({"event": "x", "event_data": {"runner": {"host": "h"}}}) is True

    def test_missing_on_other_event_ok(self):
        cb = make_host_event_callback(lambda *a: None)
        assert cb({"event": "eof", "event_data": {}}) is True


class TestRunnerCalls:
    def test_run_check_calls_ping(self):
        run_check("/tmp/inventory")
        kwargs = mock_ar.calls[-1].kwargs
        assert kwargs["module"] == "ping"
        assert kwargs["host_pattern"] == "all"
        assert kwargs["inventory"] == "/tmp/inventory"

    def test_run_playbook_adds_become_and_forks(self):
        run_playbook("configure.yml", {"a": 1}, "/tmp/inv", forks=5)
        kwargs = mock_ar.calls[-1].kwargs
        assert kwargs["extravars"]["ansible_become"] == "True"
        assert kwargs["extravars"]["a"] == 1
        assert kwargs["forks"] == 5
        assert kwargs["playbook"].endswith("configure.yml")

    def test_run_full_configuring_uses_configure_playbook(self):
        run_full_configuring({"x": 2}, "/tmp/inv")
        kwargs = mock_ar.calls[-1].kwargs
        assert kwargs["playbook"].endswith("configure.yml")

    def test_event_handler_passed_when_given(self):
        def handler(e):
            return True

        run_playbook("p.yml", {}, "/tmp/inv", event_callback=handler)
        assert mock_ar.calls[-1].kwargs.get("event_handler") is handler

    def test_events_flow_to_handler(self):
        received = []
        mock_ar.add_event(
            {"event": "runner_on_ok", "event_data": {"runner": {"host": "h"}}}
        )
        run_check("/tmp/inv", event_callback=lambda e: received.append(e) or True)
        assert len(received) == 1

    def test_nocolor_env_set(self):
        run_check("/tmp/inv")
        assert mock_ar.calls[-1].kwargs["envvars"]["ANSIBLE_NOCOLOR"] == "true"
