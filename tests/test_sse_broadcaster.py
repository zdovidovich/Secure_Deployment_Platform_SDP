"""Тесты SSE-бroadcaster (стриминг логов деплоя в реальном времени)."""

from sse.broadcaster import LogEntry, SSEBroadcaster


class TestLogEntry:
    def test_to_dict_contains_all_fields(self):
        entry = LogEntry("info", "hello", source="ansible", details={"host": "h1"})
        d = entry.to_dict()
        assert d["level"] == "info"
        assert d["message"] == "hello"
        assert d["source"] == "ansible"
        assert d["details"] == {"host": "h1"}
        assert d["timestamp"].endswith("Z")

    def test_details_defaults_to_empty_dict(self):
        assert LogEntry("debug", "m").details == {}


class TestSSEBroadcaster:
    SESSION = "test-session-unique-id"

    def setup_method(self):
        SSEBroadcaster.cleanup_session(self.SESSION)

    def teardown_method(self):
        SSEBroadcaster.cleanup_session(self.SESSION)

    def test_channel_created_on_init(self):
        SSEBroadcaster(self.SESSION)
        assert self.SESSION in SSEBroadcaster._channels

    def test_send_and_get_events(self):
        b = SSEBroadcaster(self.SESSION)
        b.info("первая")
        b.warning("вторая")
        events = SSEBroadcaster.get_events(self.SESSION)
        assert [e["message"] for e in events] == ["первая", "вторая"]
        assert events[1]["level"] == "warning"

    def test_get_events_with_last_index(self):
        b = SSEBroadcaster(self.SESSION)
        for i in range(3):
            b.info(f"msg{i}")
        first_two = SSEBroadcaster.get_events(self.SESSION, last_index=0)
        assert len(first_two) == 2 + 1
        tail = SSEBroadcaster.get_events(self.SESSION, last_index=3)
        assert tail == []

    def test_unknown_session_returns_empty(self):
        assert SSEBroadcaster.get_events("no-such-session") == []

    def test_ansible_logs_tagged_by_source(self):
        b = SSEBroadcaster(self.SESSION)
        b.ansible("TASK [Gathering Facts] ***")
        events = SSEBroadcaster.get_events(self.SESSION)
        assert events[0]["source"] == "ansible"
        assert events[0]["level"] == "debug"

    def test_send_host_log_contains_host(self):
        b = SSEBroadcaster(self.SESSION)
        b.send_host_log("error", "FAILED!", host="10.0.0.1")
        event = SSEBroadcaster.get_events(self.SESSION)[0]
        assert event["details"]["host"] == "10.0.0.1"
        assert event["level"] == "error"

    def test_send_servers_event_snapshot(self):
        b = SSEBroadcaster(self.SESSION)
        servers = [
            {"host": "10.0.0.1", "port": 22, "user": "u", "status": "running"},
            {"host": "10.0.0.2", "port": 22, "user": "u", "status": "pending"},
        ]
        b.send_servers_event(servers)
        event = SSEBroadcaster.get_events(self.SESSION)[0]
        assert event["source"] == "servers"
        assert len(event["details"]["servers"]) == 2
        assert event["details"]["servers"][0]["status"] == "running"

    def test_hadolint_and_trivy_reports(self):
        b = SSEBroadcaster(self.SESSION)
        b.hadolint("report-h")
        b.trivy("report-t")
        events = SSEBroadcaster.get_events(self.SESSION)
        assert events[0]["source"] == "hadolint"
        assert events[0]["details"]["report"] == "report-h"
        assert events[1]["source"] == "trivy"
        assert events[1]["details"]["report"] == "report-t"

    def test_complete_event(self):
        b = SSEBroadcaster(self.SESSION)
        b.complete({"success": True})
        event = SSEBroadcaster.get_events(self.SESSION)[0]
        assert event["details"]["type"] == "completion"
        assert event["details"]["result"] == {"success": True}

    def test_cleanup_session(self):
        SSEBroadcaster(self.SESSION).info("x")
        SSEBroadcaster.cleanup_session(self.SESSION)
        assert SSEBroadcaster.get_events(self.SESSION) == []

    def test_sessions_are_isolated(self):
        other = "other-session-unique-id"
        try:
            SSEBroadcaster(self.SESSION).info("a")
            SSEBroadcaster(other).info("b")
            assert [e["message"] for e in SSEBroadcaster.get_events(self.SESSION)] == ["a"]
            assert [e["message"] for e in SSEBroadcaster.get_events(other)] == ["b"]
        finally:
            SSEBroadcaster.cleanup_session(other)
