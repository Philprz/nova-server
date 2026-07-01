"""
LOT 1 — Tests de non-régression des routes réparées (vrais HTTP 500).

Couvre :
  - CAS 7 : GET /progress/tasks/active -> 200 + {count, tasks} (tasks = liste de dicts)
  - CAS 8 : DELETE /progress/task/{task_id} -> 200/True (existante) ; 404 (inconnue)
  - CAS 9 : GET /progress/stats -> 200 + clés cohérentes (mapping total_tasks_processed
            -> total_tasks ; average_duration volontairement absent)
  - CAS 2/A : GET /api/sap/products/check-exists/{item_code} et
              GET /api/sap/clients/check-exists/{card_name} -> pas de 500/TypeError
              (call_sap mocké, query string OData construite dans l'endpoint)

Usage :
    .venv\\Scripts\\python.exe -m pytest tests/test_lot1_broken_routes.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth.dependencies import get_current_user
from services.progress_tracker import progress_tracker


# ── Fixtures communes ───────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_tracker():
    """Isole l'état global du progress_tracker entre les tests."""
    active_backup = dict(progress_tracker.active_tasks)
    completed_backup = list(progress_tracker.completed_tasks)
    progress_tracker.active_tasks.clear()
    progress_tracker.completed_tasks.clear()
    try:
        yield
    finally:
        progress_tracker.active_tasks.clear()
        progress_tracker.active_tasks.update(active_backup)
        progress_tracker.completed_tasks[:] = completed_backup


def _progress_client():
    from routes.routes_progress import router as progress_router
    app = FastAPI()
    app.include_router(progress_router, prefix="/progress")
    app.dependency_overrides[get_current_user] = lambda: {"sub": "test", "role": "ADMIN"}
    return TestClient(app)


def _sap_creation_client():
    from routes.routes_sap_creation import router as sap_router
    app = FastAPI()
    app.include_router(sap_router, prefix="/api/sap")
    app.dependency_overrides[get_current_user] = lambda: {"sub": "test", "role": "ADMIN"}
    return TestClient(app)


# ── CAS 7 : GET /progress/tasks/active ──────────────────────────────────────────

class TestActiveTasks:
    def test_active_tasks_empty(self):
        client = _progress_client()
        resp = client.get("/progress/tasks/active")
        assert resp.status_code == 200
        data = resp.json()
        assert data == {"count": 0, "tasks": []}

    def test_active_tasks_returns_list_of_dicts(self):
        progress_tracker.create_task(user_prompt="devis test", draft_mode=False)
        client = _progress_client()
        resp = client.get("/progress/tasks/active")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert isinstance(data["tasks"], list)
        # get_all_active_tasks() renvoie déjà des dicts : pas de double appel
        assert isinstance(data["tasks"][0], dict)
        assert "task_id" in data["tasks"][0]
        assert "status" in data["tasks"][0]


# ── CAS 8 : DELETE /progress/task/{task_id} ─────────────────────────────────────

class TestCancelTask:
    def test_cancel_existing_task(self):
        task = progress_tracker.create_task(user_prompt="à annuler")
        client = _progress_client()
        resp = client.delete(f"/progress/task/{task.task_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        # La tâche n'est plus active après annulation
        assert progress_tracker.get_task(task.task_id) is None

    def test_cancel_unknown_task_returns_404(self):
        client = _progress_client()
        resp = client.delete("/progress/task/inconnu_xyz")
        assert resp.status_code == 404


# ── CAS 9 : GET /progress/stats ─────────────────────────────────────────────────

class TestStats:
    def test_stats_keys_coherent(self):
        # 1 active + 1 terminée -> total = 2
        progress_tracker.create_task(user_prompt="active")
        done = progress_tracker.create_task(user_prompt="terminée")
        progress_tracker.complete_task(done.task_id, {"ok": True})

        client = _progress_client()
        resp = client.get("/progress/stats")
        assert resp.status_code == 200
        data = resp.json()

        for key in ("timestamp", "active_tasks", "completed_tasks",
                    "failed_tasks", "total_tasks", "success_rate"):
            assert key in data, key

        assert data["active_tasks"] == 1
        assert data["completed_tasks"] == 1
        # total_tasks vient du mapping total_tasks_processed
        assert data["total_tasks"] == 2
        # average_duration n'est PAS inventé : il est volontairement absent
        assert "average_duration" not in data


# ── CAS 2 + A : check-exists (call_sap mocké) ───────────────────────────────────

class TestCheckExists:
    def test_product_check_exists_found(self, monkeypatch):
        captured = {}

        async def fake_call_sap(endpoint, method="GET", payload=None):
            captured["endpoint"] = endpoint
            return {"ItemCode": "2323060165", "ItemName": "PRODUIT TEST"}

        monkeypatch.setattr("services.sap.call_sap", fake_call_sap)

        client = _sap_creation_client()
        resp = client.get("/api/sap/products/check-exists/2323060165")
        # Pas de 500 / TypeError (params=) : la route répond proprement
        assert resp.status_code == 200
        data = resp.json()
        assert data["exists"] is True
        assert data["product"]["ItemCode"] == "2323060165"
        # La query OData est dans l'endpoint, pas en kwarg params
        assert captured["endpoint"].startswith("/Items('2323060165')?")
        assert "%24select" in captured["endpoint"] or "$select" in captured["endpoint"]

    def test_product_check_exists_not_found_404(self, monkeypatch):
        async def fake_call_sap(endpoint, method="GET", payload=None):
            raise Exception("HTTP 404 not found")

        monkeypatch.setattr("services.sap.call_sap", fake_call_sap)

        client = _sap_creation_client()
        resp = client.get("/api/sap/products/check-exists/INEXISTANT")
        assert resp.status_code == 200
        data = resp.json()
        assert data["exists"] is False
        assert data["product"] is None

    def test_client_check_exists_found(self, monkeypatch):
        captured = {}

        async def fake_call_sap(endpoint, method="GET", payload=None):
            captured["endpoint"] = endpoint
            return {"value": [{"CardCode": "C0001", "CardName": "SAVERGLASS"}]}

        monkeypatch.setattr("services.sap.call_sap", fake_call_sap)

        client = _sap_creation_client()
        resp = client.get("/api/sap/clients/check-exists/SAVERGLASS")
        assert resp.status_code == 200
        data = resp.json()
        assert data["exists"] is True
        assert data["count"] == 1
        assert data["clients"][0]["CardCode"] == "C0001"
        assert captured["endpoint"].startswith("/BusinessPartners?")
