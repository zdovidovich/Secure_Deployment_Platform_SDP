"""Тесты HTTP API (routes/api.py) — интеграция CI/CD."""

import io
import json
import time

import pytest


def make_deploy_request_data(tar_bytes=b"fake-tar", key_text=None):
    """Формирует multipart-данные валидного запроса на деплой."""
    if key_text is None:
        key_text = (
            "-----BEGIN OPENSSH PRIVATE KEY-----\nAAAA\n"
            "-----END OPENSSH PRIVATE KEY-----\n"
        )
    return {
        "ssh_key": (io.BytesIO(key_text.encode()), "id_test"),
        "docker_image": (io.BytesIO(tar_bytes), "image.tar"),
        "image_source": "tar",
        "ansible_host": "127.0.0.1",
        "ansible_port": "22",
        "ansible_user": "root",
        "app_deploy_image_name": "myapp:latest",
        "app_deploy_container_name": "myapp",
        "app_host_port": "8080",
        "app_container_port": "80",
    }


class TestHealth:
    def test_health_ok(self, flask_client):
        resp = flask_client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.get_json() == {"status": "ok"}

    def test_health_no_auth_required(self, flask_client, monkeypatch):
        monkeypatch.setenv("SDP_API_KEY", "secret")
        assert flask_client.get("/api/v1/health").status_code == 200


class TestAuth:
    def test_missing_api_key_rejected(self, flask_client, monkeypatch):
        monkeypatch.setenv("SDP_API_KEY", "secret")
        resp = flask_client.get("/api/v1/deployments/whatever")
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "Unauthorized"

    def test_wrong_api_key_rejected(self, flask_client, monkeypatch):
        monkeypatch.setenv("SDP_API_KEY", "secret")
        resp = flask_client.get(
            "/api/v1/deployments/x", headers={"X-API-Key": "wrong"}
        )
        assert resp.status_code == 401

    def test_correct_api_key_accepted(self, flask_client, monkeypatch):
        monkeypatch.setenv("SDP_API_KEY", "secret")
        resp = flask_client.get(
            "/api/v1/deployments/nonexistent",
            headers={"X-API-Key": "secret"},
        )
        assert resp.status_code == 404  # прошла авторизацию, не найдена запись

    def test_no_key_configured_allows_anonymous(self, flask_client):
        resp = flask_client.get("/api/v1/deployments/nonexistent")
        assert resp.status_code == 404


class TestCreateDeployment:
    def test_requires_ssh_key(self, flask_client):
        resp = flask_client.post("/api/v1/deployments", data={}, content_type="multipart/form-data")
        assert resp.status_code == 400
        body = resp.get_json()
        assert "ssh_key" in body["required_files"]

    def test_tar_mode_requires_image(self, flask_client):
        data = make_deploy_request_data()
        del data["docker_image"]
        resp = flask_client.post(
            "/api/v1/deployments", data=data, content_type="multipart/form-data"
        )
        assert resp.status_code == 400
        assert "docker_image" in resp.get_json()["required_files"]

    def test_registry_mode_without_image_starts(self, flask_client, monkeypatch):
        from mocks import ansible_runner as mock_ar
        from services.deployment_store import deployment_store

        mock_ar.set_run_result(
            mock_ar.MockRunnerResult(status="successful", stats={})
        )
        data = make_deploy_request_data()
        del data["docker_image"]
        data["image_source"] = "registry"
        resp = flask_client.post(
            "/api/v1/deployments", data=data, content_type="multipart/form-data"
        )
        assert resp.status_code == 202
        body = resp.get_json()
        deployment_id = body["deployment_id"]
        try:
            assert body["status"] in ("pending", "running")
            assert body["status_url"].endswith(deployment_id)
            assert body["events_url"].endswith(f"/{deployment_id}/events")
            assert body["web_url"].startswith("/deploy/status/")
        finally:
            deployment_store.remove(deployment_id)

    def test_created_job_visible_in_store(self, flask_client):
        from services.deployment_store import deployment_store

        resp = flask_client.post(
            "/api/v1/deployments",
            data=make_deploy_request_data(),
            content_type="multipart/form-data",
        )
        assert resp.status_code == 202
        deployment_id = resp.get_json()["deployment_id"]
        try:
            job = deployment_store.get(deployment_id)
            assert job is not None
        finally:
            deployment_store.remove(deployment_id)


class TestGetDeployment:
    def _create(self, flask_client):
        resp = flask_client.post(
            "/api/v1/deployments",
            data=make_deploy_request_data(),
            content_type="multipart/form-data",
        )
        return resp.get_json()["deployment_id"]

    def test_not_found(self, flask_client):
        resp = flask_client.get("/api/v1/deployments/nope123")
        assert resp.status_code == 404
        assert resp.get_json()["error"] == "Deployment not found"

    def test_returns_status_and_fields(self, flask_client):
        deployment_id = self._create(flask_client)
        try:
            resp = flask_client.get(f"/api/v1/deployments/{deployment_id}")
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["deployment_id"] == deployment_id
            assert body["status"] in ("pending", "running", "success", "error")
            assert "created_at" in body
            assert "servers" in body
            assert "result" in body
        finally:
            from services.deployment_store import deployment_store

            deployment_store.remove(deployment_id)


class TestSSEStream:
    def test_stream_not_found(self, flask_client):
        resp = flask_client.get("/api/v1/deployments/nope/events")
        assert resp.status_code == 404

    def test_stream_content_type(self, flask_client):
        from services.deployment_store import deployment_store

        resp = flask_client.post(
            "/api/v1/deployments",
            data=make_deploy_request_data(),
            content_type="multipart/form-data",
        )
        deployment_id = resp.get_json()["deployment_id"]
        try:
            resp = flask_client.get(f"/api/v1/deployments/{deployment_id}/events")
            assert resp.status_code == 200
            assert resp.mimetype == "text/event-stream"
            # вычитываем первые события (стрим бесконечный до завершения)
            chunk = next(resp.response.iter_encoded(), b"") if resp.response else b""
        finally:
            deployment_store.remove(deployment_id)


class TestLegacyRedirects:
    def test_legacy_status_redirect(self, flask_client):
        resp = flask_client.get("/deploy/api/status/abc")
        assert resp.status_code in (302, 307)
        assert "/api/v1/deployments/abc" in resp.headers["Location"]

    def test_legacy_stream_redirect(self, flask_client):
        resp = flask_client.get("/deploy/stream/abc")
        assert resp.status_code in (302, 307)
        assert "/events" in resp.headers["Location"]

    def test_index_redirects_to_deploy(self, flask_client):
        resp = flask_client.get("/")
        assert resp.status_code == 301
        assert resp.headers["Location"] == "/deploy/"
