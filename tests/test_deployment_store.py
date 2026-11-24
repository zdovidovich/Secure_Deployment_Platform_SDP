"""Тесты хранилища деплоев (services/deployment_store.py)."""

from concurrent.futures import ThreadPoolExecutor

from services.deployment_store import DeploymentStore


class TestDeploymentStore:
    def test_create_returns_unique_ids(self):
        store = DeploymentStore()
        ids = {store.create().deployment_id for _ in range(20)}
        assert len(ids) == 20

    def test_get_existing(self):
        store = DeploymentStore()
        job = store.create()
        assert store.get(job.deployment_id) is job

    def test_get_missing_returns_none(self):
        assert DeploymentStore().get("deadbeef") is None

    def test_job_has_service_and_created_at(self):
        job = DeploymentStore().create()
        assert job.service.status == "pending"
        assert isinstance(job.created_at, str)
        assert "T" in job.created_at  # ISO-8601

    def test_remove(self):
        store = DeploymentStore()
        job = store.create()
        store.remove(job.deployment_id)
        assert store.get(job.deployment_id) is None

    def test_remove_missing_is_noop(self):
        DeploymentStore().remove("nope")  # без исключения

    def test_thread_safety(self):
        store = DeploymentStore()
        with ThreadPoolExecutor(max_workers=8) as pool:
            jobs = list(pool.map(lambda _: store.create(), range(50)))
        ids = [j.deployment_id for j in jobs]
        assert len(set(ids)) == 50
        assert all(store.get(i) is not None for i in ids)
