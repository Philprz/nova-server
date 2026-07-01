"""
Tests de l'ecran d'administration de la configuration (coffre chiffre) — Lot 2 / 2a.

Couvre :
  - matcher de cle SENSIBLE + regroupement par categorie (fonctions pures) ;
  - GET /api/admin/config ne renvoie AUCUNE valeur secrete en clair (preview masque) ;
  - PUT /api/admin/config fusionne une map partielle SANS effacer les autres cles
    (round-trip coffre verifie) ;
  - acces refuse (403) sans role ADMIN, 401 sans authentification ;
  - validation des noms de cle (PUT).

Usage :
    .venv\\Scripts\\python.exe -m pytest tests/test_admin_config.py -v
"""

import os
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

sys.path.insert(0, str(Path(__file__).parent.parent))

from services import secure_config


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def set_jwt_secret(monkeypatch):
    monkeypatch.setenv("NOVA_JWT_SECRET", "test_secret_key_for_unit_tests_32chars!!")


@pytest.fixture
def tmp_auth_db(tmp_path, monkeypatch):
    import auth.auth_db as auth_db_module
    test_db = tmp_path / "nova_auth_test.db"
    monkeypatch.setattr(auth_db_module, "DB_PATH", test_db)
    auth_db_module._init_db()
    return test_db


@pytest.fixture
def admin_ctx(tmp_auth_db):
    """Societe + utilisateur ADMIN + token JWT ADMIN pret a l'emploi."""
    import auth.auth_db as db
    from auth.jwt_service import create_access_token
    sid = db.create_society("Test Corp", "TEST_DB", "https://sap.test/b1s/v1", max_users=10)
    uid = db.create_user(sid, "admin_user", "Admin Test", "ADMIN")
    token = create_access_token(uid, "admin_user", sid, "TEST_DB", "ADMIN", [])
    return {"society_id": sid, "user_id": uid, "token": token}


@pytest.fixture
def adv_token(admin_ctx):
    import auth.auth_db as db
    from auth.jwt_service import create_access_token
    uid = db.create_user(admin_ctx["society_id"], "adv_user", "ADV Test", "ADV")
    return create_access_token(uid, "adv_user", admin_ctx["society_id"], "TEST_DB", "ADV", [])


# Valeur secrete temoin : ne doit JAMAIS apparaitre dans une reponse GET.
SECRET_SENTINEL = "S3cr3t-V4lue-NEVER-IN-CLEAR-xyz789"

SAMPLE_VAULT = {
    "APP_PORT": "8001",
    "DATABASE_URL": "sqlite:///./nova.db",
    "SAP_USER": "manager",
    "SAP_CLIENT_PASSWORD": SECRET_SENTINEL,
    "NOVA_JWT_SECRET": "another-" + SECRET_SENTINEL,
    "PRICING_DEFAULT_MARGIN": "0.45",
}


@pytest.fixture
def vault(tmp_path, monkeypatch):
    """Cle maitre + coffre temporaire pointe par NOVA_VAULT_PATH."""
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("NOVA_VAULT_KEY", key)
    vault_path = str(tmp_path / "secrets.enc")
    secure_config.encrypt_env_to_vault(dict(SAMPLE_VAULT), out_path=vault_path)
    monkeypatch.setenv("NOVA_VAULT_PATH", vault_path)
    return vault_path


def _make_client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes.routes_admin import router as admin_router
    app = FastAPI()
    app.include_router(admin_router)
    return TestClient(app)


# ── Fonctions pures : matcher sensible + categorisation ─────────────────────────

class TestSensitiveMatcher:
    def test_sensitive_keys(self):
        from routes.routes_admin import _is_sensitive_key
        for k in ("SAP_CLIENT_PASSWORD", "NOVA_JWT_SECRET", "INSEE_API_KEY",
                  "MS_CLIENT_SECRET",
                  "INSEE_CONSUMER_SECRET", "NOVA_VAULT_KEY", "DATABASE_URL"):
            assert _is_sensitive_key(k) is True, k

    def test_non_sensitive_keys(self):
        from routes.routes_admin import _is_sensitive_key
        for k in ("APP_PORT", "SAP_USER", "PRICING_DEFAULT_MARGIN",
                  "MS_TENANT_ID", "PAPPERS_URL"):
            assert _is_sensitive_key(k) is False, k


class TestCategorize:
    def test_categories(self):
        from routes.routes_admin import _categorize_key
        cases = {
            "SAP_USER": "SAP",
            "MS_CLIENT_ID": "Microsoft 365",
            "INSEE_API_KEY": "INSEE",
            "PAPPERS_URL": "Pappers",
            "PRICING_DEFAULT_MARGIN": "Pricing",
            "DHL_USERNAME": "Transport DHL",
            "ANTHROPIC_MODEL": "LLM",
            "QUOTA_DEVIS_MAX": "Quota devis",
            "APP_PORT": "Application",
            "NOVA_JWT_SECRET": "Application",
        }
        for key, expected in cases.items():
            assert _categorize_key(key) == expected, key

    def test_unknown_prefix_is_default(self):
        from routes.routes_admin import _categorize_key, _DEFAULT_CATEGORY
        assert _categorize_key("ZZZ_UNKNOWN") == _DEFAULT_CATEGORY


# ── GET : masquage des secrets ──────────────────────────────────────────────────

class TestGetConfig:
    def test_get_never_returns_secret_in_clear(self, admin_ctx, vault):
        client = _make_client()
        resp = client.get("/api/admin/config",
                           headers={"Authorization": f"Bearer {admin_ctx['token']}"})
        assert resp.status_code == 200
        # AUCUNE valeur secrete en clair, nulle part dans la reponse brute.
        assert SECRET_SENTINEL not in resp.text

        data = resp.json()
        assert data["vault_present"] is True
        assert data["total"] == len(SAMPLE_VAULT)

        # Index par cle pour les assertions
        by_key = {}
        for entries in data["groups"].values():
            for e in entries:
                by_key[e["key"]] = e

        # Secret : pas de champ 'value', preview masque, is_set vrai
        sec = by_key["SAP_CLIENT_PASSWORD"]
        assert sec["is_secret"] is True
        assert sec["is_set"] is True
        assert "value" not in sec
        assert sec["preview"] == "********"

        # Non-secret : valeur renvoyee en clair (autorise)
        port = by_key["APP_PORT"]
        assert port["is_secret"] is False
        assert port["value"] == "8001"

    def test_get_requires_admin(self, admin_ctx, adv_token, vault):
        client = _make_client()
        resp = client.get("/api/admin/config",
                          headers={"Authorization": f"Bearer {adv_token}"})
        assert resp.status_code == 403

    def test_get_requires_auth(self, admin_ctx, vault):
        client = _make_client()
        resp = client.get("/api/admin/config")
        assert resp.status_code in (401, 403)

    def test_get_vault_absent(self, admin_ctx, tmp_path, monkeypatch):
        monkeypatch.setenv("NOVA_VAULT_KEY", Fernet.generate_key().decode("ascii"))
        monkeypatch.setenv("NOVA_VAULT_PATH", str(tmp_path / "missing.enc"))
        client = _make_client()
        resp = client.get("/api/admin/config",
                          headers={"Authorization": f"Bearer {admin_ctx['token']}"})
        assert resp.status_code == 200
        assert resp.json()["vault_present"] is False


# ── PUT : fusion partielle sans ecrasement ──────────────────────────────────────

class TestPutConfig:
    def test_put_partial_merge_preserves_others(self, admin_ctx, vault):
        client = _make_client()
        resp = client.put(
            "/api/admin/config",
            headers={"Authorization": f"Bearer {admin_ctx['token']}"},
            json={"updates": {"APP_PORT": "9999", "NEW_FLAG": "on"}},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["restart_required"] is True
        assert sorted(body["modified_keys"]) == ["APP_PORT", "NEW_FLAG"]

        # Round-trip coffre : la cle ciblee est modifiee, les autres preservees.
        pairs = secure_config.decrypt_vault(vault)
        assert pairs["APP_PORT"] == "9999"          # modifiee
        assert pairs["NEW_FLAG"] == "on"            # ajoutee
        assert pairs["SAP_USER"] == "manager"       # preservee
        assert pairs["PRICING_DEFAULT_MARGIN"] == "0.45"  # preservee
        # Le secret NON re-soumis n'est PAS efface.
        assert pairs["SAP_CLIENT_PASSWORD"] == SECRET_SENTINEL

    def test_put_updates_a_secret_only_when_sent(self, admin_ctx, vault):
        client = _make_client()
        resp = client.put(
            "/api/admin/config",
            headers={"Authorization": f"Bearer {admin_ctx['token']}"},
            json={"updates": {"SAP_CLIENT_PASSWORD": "brand-new-pwd"}},
        )
        assert resp.status_code == 200
        pairs = secure_config.decrypt_vault(vault)
        assert pairs["SAP_CLIENT_PASSWORD"] == "brand-new-pwd"
        # Aucune autre cle touchee
        assert pairs["NOVA_JWT_SECRET"] == SAMPLE_VAULT["NOVA_JWT_SECRET"]
        assert pairs["APP_PORT"] == "8001"

    def test_put_requires_admin(self, admin_ctx, adv_token, vault):
        client = _make_client()
        resp = client.put(
            "/api/admin/config",
            headers={"Authorization": f"Bearer {adv_token}"},
            json={"updates": {"APP_PORT": "1234"}},
        )
        assert resp.status_code == 403
        # Coffre intact
        assert secure_config.decrypt_vault(vault)["APP_PORT"] == "8001"

    def test_put_rejects_invalid_key(self, admin_ctx, vault):
        client = _make_client()
        resp = client.put(
            "/api/admin/config",
            headers={"Authorization": f"Bearer {admin_ctx['token']}"},
            json={"updates": {"bad key!": "x"}},
        )
        assert resp.status_code == 422

    def test_put_rejects_empty_updates(self, admin_ctx, vault):
        client = _make_client()
        resp = client.put(
            "/api/admin/config",
            headers={"Authorization": f"Bearer {admin_ctx['token']}"},
            json={"updates": {}},
        )
        assert resp.status_code == 422
