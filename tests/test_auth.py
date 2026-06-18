"""
Tests NOVA Auth Layer
Couvre : auth_db, jwt_service, sap_validator, flux login complet, dépendances RBAC.

Usage :
    .venv\\Scripts\\python.exe -m pytest tests/test_auth.py -v
"""

import os
import sys
import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Racine du projet dans le path
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def set_jwt_secret(monkeypatch):
    monkeypatch.setenv("NOVA_JWT_SECRET", "test_secret_key_for_unit_tests_32chars!!")


@pytest.fixture
def tmp_auth_db(tmp_path, monkeypatch):
    """Redirige nova_auth.db vers un fichier temporaire pour chaque test."""
    import auth.auth_db as auth_db_module
    test_db = tmp_path / "nova_auth_test.db"
    monkeypatch.setattr(auth_db_module, "DB_PATH", test_db)
    auth_db_module._init_db()
    return test_db


@pytest.fixture
def seeded_db(tmp_auth_db):
    """DB avec une société, un user ADMIN et une boîte mail.

    max_users=10 : plusieurs tests (TestDependencies) ajoutent des users à cette
    société ; la capacité par défaut (1) les bloquerait. Les tests de capacité
    dédiés (TestUserCapacity) créent leurs propres sociétés à capacité contrôlée.
    """
    import auth.auth_db as db
    sid = db.create_society("Test Corp", "TEST_DB", "https://sap.test/b1s/v1", max_users=10)
    uid = db.create_user(sid, "admin_user", "Admin Test", "ADMIN")
    mid = db.create_mailbox(sid, "test@corp.fr", "Test Mailbox")
    db.grant_mailbox_permission(uid, mid, can_write=True, granted_by=uid)
    return {"society_id": sid, "user_id": uid, "mailbox_id": mid}


# ── TestAuthDB ─────────────────────────────────────────────────────────────────

class TestAuthDB:

    def test_create_and_get_society(self, tmp_auth_db):
        import auth.auth_db as db
        sid = db.create_society("ACME", "ACME_DB", "https://sap.acme/b1s/v1")
        assert sid > 0
        s = db.get_society_by_id(sid)
        assert s["name"] == "ACME"
        assert s["sap_company_db"] == "ACME_DB"
        assert s["is_active"] == 1

    def test_get_society_by_sap_company(self, tmp_auth_db):
        import auth.auth_db as db
        db.create_society("ACME", "ACME_DB", "https://sap.acme/b1s/v1")
        s = db.get_society_by_sap_company("ACME_DB")
        assert s is not None
        assert s["name"] == "ACME"

    def test_duplicate_sap_company_raises(self, tmp_auth_db):
        import auth.auth_db as db
        import sqlite3
        db.create_society("ACME", "ACME_DB", "https://sap.acme/b1s/v1")
        with pytest.raises(Exception):
            db.create_society("ACME2", "ACME_DB", "https://sap.acme2/b1s/v1")

    def test_create_user_and_get_by_login(self, tmp_auth_db):
        import auth.auth_db as db
        sid = db.create_society("Corp", "CORP_DB", "https://sap.corp/b1s/v1")
        uid = db.create_user(sid, "john", "John Doe", "ADV")
        assert uid > 0
        u = db.get_user_by_sap_login(sid, "john")
        assert u is not None
        assert u["display_name"] == "John Doe"
        assert u["role"] == "ADV"

    def test_user_role_constraint_rejects_invalid(self, tmp_auth_db):
        import auth.auth_db as db
        sid = db.create_society("Corp", "CORP_DB", "https://sap.corp/b1s/v1")
        with pytest.raises(Exception):
            db.create_user(sid, "john", "John", "SUPERADMIN")

    def test_grant_and_check_permission(self, seeded_db):
        import auth.auth_db as db
        perm = db.check_mailbox_permission(seeded_db["user_id"], seeded_db["mailbox_id"])
        assert perm is not None
        assert perm["can_read"] == 1
        assert perm["can_write"] == 1

    def test_revoke_permission(self, seeded_db):
        import auth.auth_db as db
        db.revoke_mailbox_permission(seeded_db["user_id"], seeded_db["mailbox_id"])
        perm = db.check_mailbox_permission(seeded_db["user_id"], seeded_db["mailbox_id"])
        assert perm is None

    def test_get_user_mailbox_ids(self, seeded_db):
        import auth.auth_db as db
        ids = db.get_user_mailbox_ids(seeded_db["user_id"])
        assert seeded_db["mailbox_id"] in ids

    def test_refresh_token_store_and_lookup(self, seeded_db):
        import auth.auth_db as db
        expires = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        db.store_refresh_token(seeded_db["user_id"], "hash123", expires)
        row = db.get_refresh_token("hash123")
        assert row is not None
        assert row["user_id"] == seeded_db["user_id"]
        assert row["revoked"] == 0

    def test_revoked_token_not_returned(self, seeded_db):
        import auth.auth_db as db
        expires = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        db.store_refresh_token(seeded_db["user_id"], "hash456", expires)
        db.revoke_refresh_token("hash456")
        assert db.get_refresh_token("hash456") is None

    def test_cleanup_expired_tokens(self, seeded_db):
        import auth.auth_db as db
        expired = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        db.store_refresh_token(seeded_db["user_id"], "old_hash", expired)
        count = db.cleanup_expired_tokens()
        assert count >= 1
        assert db.get_refresh_token("old_hash") is None

    def test_deactivate_user(self, seeded_db):
        import auth.auth_db as db
        db.deactivate_user(seeded_db["user_id"])
        u = db.get_user_by_sap_login(1, "admin_user")
        assert u is None  # is_active=0 filtré par get_user_by_sap_login


# ── TestJWTService ─────────────────────────────────────────────────────────────

class TestJWTService:

    def test_access_token_roundtrip(self):
        from auth.jwt_service import create_access_token, decode_access_token
        token = create_access_token(
            user_id=1,
            sap_username="manager",
            society_id=1,
            sap_company_db="RON_DB",
            role="ADMIN",
            mailbox_ids=[1, 2],
        )
        payload = decode_access_token(token)
        assert payload["sub"] == "1"
        assert payload["role"] == "ADMIN"
        assert payload["mailbox_ids"] == [1, 2]
        assert payload["sap_company"] == "RON_DB"

    def test_expired_token_raises(self):
        import jwt as pyjwt
        from auth.jwt_service import ALGORITHM, SECRET_KEY, _require_secret, decode_access_token
        from datetime import timezone
        expired_payload = {
            "sub": "1",
            "sap_user": "manager",
            "society_id": 1,
            "sap_company": "TEST",
            "role": "ADV",
            "mailbox_ids": [],
            "exp": datetime.now(timezone.utc) - timedelta(seconds=10),
            "iat": datetime.now(timezone.utc) - timedelta(minutes=5),
            "jti": "test",
        }
        token = pyjwt.encode(expired_payload, _require_secret(), algorithm=ALGORITHM)
        with pytest.raises(pyjwt.ExpiredSignatureError):
            decode_access_token(token)

    def test_tampered_signature_raises(self):
        import jwt as pyjwt
        from auth.jwt_service import create_access_token, decode_access_token
        token = create_access_token(1, "u", 1, "DB", "ADV", [])
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(pyjwt.InvalidTokenError):
            decode_access_token(tampered)

    def test_refresh_token_hash_differs_from_raw(self):
        from auth.jwt_service import create_refresh_token, hash_token
        raw, token_hash, expires = create_refresh_token(1)
        assert raw != token_hash
        assert len(raw) > 30
        assert hash_token(raw) == token_hash

    def test_missing_secret_raises(self, monkeypatch):
        import importlib
        import auth.jwt_service as jwt_mod
        monkeypatch.setenv("NOVA_JWT_SECRET", "")
        # Recharger la variable module-level
        monkeypatch.setattr(jwt_mod, "SECRET_KEY", "")
        with pytest.raises(RuntimeError, match="NOVA_JWT_SECRET"):
            jwt_mod._require_secret()


# ── TestSAPValidator ──────────────────────────────────────────────────────────

class TestSAPValidator:

    @pytest.mark.asyncio
    async def test_valid_credentials_returns_true(self):
        from auth.sap_validator import validate_sap_credentials
        mock_response = MagicMock()
        mock_response.status_code = 200
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client
            result = await validate_sap_credentials(
                "https://sap.test/b1s/v1", "TEST_DB", "user", "pass"
            )
        assert result is True

    @pytest.mark.asyncio
    async def test_invalid_credentials_returns_false(self):
        from auth.sap_validator import validate_sap_credentials
        mock_response = MagicMock()
        mock_response.status_code = 401
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client
            result = await validate_sap_credentials(
                "https://sap.test/b1s/v1", "TEST_DB", "user", "wrong"
            )
        assert result is False

    @pytest.mark.asyncio
    async def test_sap_timeout_returns_false(self):
        import httpx
        from auth.sap_validator import validate_sap_credentials
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            mock_client_cls.return_value = mock_client
            result = await validate_sap_credentials(
                "https://sap.test/b1s/v1", "TEST_DB", "user", "pass"
            )
        assert result is False

    @pytest.mark.asyncio
    async def test_sap_network_error_returns_false(self):
        from auth.sap_validator import validate_sap_credentials
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=Exception("connection refused"))
            mock_client_cls.return_value = mock_client
            result = await validate_sap_credentials(
                "https://sap.test/b1s/v1", "TEST_DB", "user", "pass"
            )
        assert result is False


# ── TestLoginFlow ─────────────────────────────────────────────────────────────

class TestLoginFlow:
    """Tests d'intégration du flux login via FastAPI TestClient.

    Le flux login/refresh utilise des cookies HttpOnly (nova_session / nova_refresh) :
    le raw refresh token n'est jamais exposé dans le corps JSON. Les assertions
    portent donc sur les Set-Cookie, pas sur un body { access_token, refresh_token }.
    """

    @pytest.fixture(autouse=True)
    def _no_real_sap(self, monkeypatch):
        """Neutralise l'appel best-effort ensure_session() (évite un vrai login SAP)."""
        from services import sap_business_service
        fake = MagicMock()
        fake.ensure_session = AsyncMock(return_value=True)
        monkeypatch.setattr(sap_business_service, "get_sap_business_service", lambda: fake)

    def _make_app(self):
        from fastapi import FastAPI
        from routes.routes_auth import router
        app = FastAPI()
        app.include_router(router)
        return app

    def test_login_success_sets_auth_cookies(self, seeded_db):
        from fastapi.testclient import TestClient
        app = self._make_app()
        client = TestClient(app)

        with patch("routes.routes_auth.validate_sap_credentials", new_callable=AsyncMock, return_value=True):
            response = client.post("/api/auth/login", json={
                "sap_company_db": "TEST_DB",
                "sap_username":   "admin_user",
                "sap_password":   "anypass",
            })

        assert response.status_code == 200
        # Tokens posés en cookies HttpOnly, jamais dans le corps
        assert response.cookies.get("nova_session")
        assert response.cookies.get("nova_refresh")
        data = response.json()
        assert "access_token" not in data
        assert "refresh_token" not in data
        assert data["expires_in"] > 0

    def test_login_unknown_company_returns_401(self, seeded_db):
        from fastapi.testclient import TestClient
        app = self._make_app()
        client = TestClient(app)

        response = client.post("/api/auth/login", json={
            "sap_company_db": "UNKNOWN_DB",
            "sap_username":   "admin_user",
            "sap_password":   "anypass",
        })
        assert response.status_code == 401
        assert "Société inconnue" in response.json()["detail"]

    def test_login_unknown_user_returns_401(self, seeded_db):
        from fastapi.testclient import TestClient
        app = self._make_app()
        client = TestClient(app)

        response = client.post("/api/auth/login", json={
            "sap_company_db": "TEST_DB",
            "sap_username":   "ghost_user",
            "sap_password":   "anypass",
        })
        assert response.status_code == 401
        assert "non enregistré" in response.json()["detail"]

    def test_login_wrong_sap_password_returns_401(self, seeded_db):
        from fastapi.testclient import TestClient
        app = self._make_app()
        client = TestClient(app)

        with patch("routes.routes_auth.validate_sap_credentials", new_callable=AsyncMock, return_value=False):
            response = client.post("/api/auth/login", json={
                "sap_company_db": "TEST_DB",
                "sap_username":   "admin_user",
                "sap_password":   "wrong",
            })
        assert response.status_code == 401
        assert "Credentials SAP" in response.json()["detail"]

    def test_refresh_rotates_tokens(self, seeded_db):
        from fastapi.testclient import TestClient
        app = self._make_app()
        client = TestClient(app)

        # 1. Login → cookie nova_refresh posé dans le jar du client
        with patch("routes.routes_auth.validate_sap_credentials", new_callable=AsyncMock, return_value=True):
            login_resp = client.post("/api/auth/login", json={
                "sap_company_db": "TEST_DB",
                "sap_username":   "admin_user",
                "sap_password":   "anypass",
            })
        assert login_resp.status_code == 200
        old_refresh = login_resp.cookies["nova_refresh"]

        # 2. Refresh : on pose le cookie nova_refresh sur le client (le cookie est
        # path-scopé sur /api/auth/refresh côté serveur).
        client.cookies.clear()
        client.cookies.set("nova_refresh", old_refresh)
        refresh_resp = client.post("/api/auth/refresh")
        assert refresh_resp.status_code == 200
        assert refresh_resp.cookies.get("nova_session")
        new_refresh = refresh_resp.cookies["nova_refresh"]
        assert new_refresh != old_refresh  # token rotaté

    def test_revoked_refresh_returns_401(self, seeded_db):
        from fastapi.testclient import TestClient
        app = self._make_app()
        client = TestClient(app)

        with patch("routes.routes_auth.validate_sap_credentials", new_callable=AsyncMock, return_value=True):
            login_resp = client.post("/api/auth/login", json={
                "sap_company_db": "TEST_DB",
                "sap_username":   "admin_user",
                "sap_password":   "anypass",
            })
        old_refresh = login_resp.cookies["nova_refresh"]

        # Utiliser une première fois (rotation → l'ancien est révoqué)
        client.cookies.clear()
        client.cookies.set("nova_refresh", old_refresh)
        first = client.post("/api/auth/refresh")
        assert first.status_code == 200

        # Rejouer l'ancien cookie révoqué → 401
        client.cookies.clear()
        client.cookies.set("nova_refresh", old_refresh)
        resp2 = client.post("/api/auth/refresh")
        assert resp2.status_code == 401


# ── TestDependencies ──────────────────────────────────────────────────────────

class TestDependencies:
    """Tests des dépendances FastAPI RBAC."""

    def _make_app_with_protected_routes(self):
        from fastapi import FastAPI, Depends
        from auth.dependencies import (
            AuthenticatedUser,
            get_current_user,
            require_mailbox_access,
            require_role,
        )
        app = FastAPI()

        @app.get("/admin-only")
        async def admin_only(_u=Depends(require_role("ADMIN"))):
            return {"ok": True}

        @app.get("/manager-or-admin")
        async def manager_or_admin(_u=Depends(require_role("ADMIN", "MANAGER"))):
            return {"ok": True}

        @app.get("/mailbox/{mailbox_id}")
        async def mailbox_route(_u=Depends(require_mailbox_access("mailbox_id"))):
            return {"ok": True}

        @app.get("/any-auth")
        async def any_auth(u: AuthenticatedUser = Depends(get_current_user)):
            return {"role": u.role}

        return app

    def _token_for(self, role: str, mailbox_ids=None):
        from auth.jwt_service import create_access_token
        return create_access_token(
            user_id=99,
            sap_username="test",
            society_id=1,
            sap_company_db="TEST",
            role=role,
            mailbox_ids=mailbox_ids or [],
        )

    def test_admin_role_allowed_on_admin_route(self, seeded_db):
        from fastapi.testclient import TestClient
        app = self._make_app_with_protected_routes()
        client = TestClient(app)
        # Utiliser l'user existant en DB (user_id=seeded_db['user_id'])
        from auth.jwt_service import create_access_token
        token = create_access_token(
            user_id=seeded_db["user_id"],
            sap_username="admin_user",
            society_id=seeded_db["society_id"],
            sap_company_db="TEST_DB",
            role="ADMIN",
            mailbox_ids=[seeded_db["mailbox_id"]],
        )
        resp = client.get("/admin-only", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_adv_rejected_on_admin_route(self, seeded_db):
        import auth.auth_db as db
        from fastapi.testclient import TestClient
        app = self._make_app_with_protected_routes()
        client = TestClient(app)
        # Créer un user ADV
        uid = db.create_user(seeded_db["society_id"], "adv1", "ADV 1", "ADV")
        from auth.jwt_service import create_access_token
        token = create_access_token(uid, "adv1", seeded_db["society_id"], "TEST_DB", "ADV", [])
        resp = client.get("/admin-only", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

    def test_admin_bypasses_mailbox_check(self, seeded_db):
        from fastapi.testclient import TestClient
        app = self._make_app_with_protected_routes()
        client = TestClient(app)
        from auth.jwt_service import create_access_token
        token = create_access_token(
            user_id=seeded_db["user_id"],
            sap_username="admin_user",
            society_id=seeded_db["society_id"],
            sap_company_db="TEST_DB",
            role="ADMIN",
            mailbox_ids=[],
        )
        # L'admin accède à n'importe quelle boîte sans permission explicite
        resp = client.get("/mailbox/999", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_adv_without_permission_raises_403(self, seeded_db):
        import auth.auth_db as db
        from fastapi.testclient import TestClient
        app = self._make_app_with_protected_routes()
        client = TestClient(app)
        uid = db.create_user(seeded_db["society_id"], "adv2", "ADV 2", "ADV")
        # Pas de permission accordée sur la boîte
        from auth.jwt_service import create_access_token
        token = create_access_token(uid, "adv2", seeded_db["society_id"], "TEST_DB", "ADV", [])
        resp = client.get(
            f"/mailbox/{seeded_db['mailbox_id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    def test_expired_token_raises_401(self, seeded_db):
        import jwt as pyjwt
        from fastapi.testclient import TestClient
        from auth.jwt_service import ALGORITHM, _require_secret
        app = self._make_app_with_protected_routes()
        client = TestClient(app)
        expired = pyjwt.encode(
            {
                "sub": str(seeded_db["user_id"]),
                "sap_user": "admin_user",
                "society_id": 1,
                "sap_company": "TEST",
                "role": "ADMIN",
                "mailbox_ids": [],
                "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
                "iat": datetime.now(timezone.utc) - timedelta(minutes=2),
                "jti": "x",
            },
            _require_secret(),
            algorithm=ALGORITHM,
        )
        resp = client.get("/any-auth", headers={"Authorization": f"Bearer {expired}"})
        assert resp.status_code == 401

    def test_no_bearer_raises_401(self, seeded_db):
        from fastapi.testclient import TestClient
        app = self._make_app_with_protected_routes()
        client = TestClient(app)
        resp = client.get("/any-auth")
        assert resp.status_code in (401, 403)


# ── TestUserCapacity ──────────────────────────────────────────────────────────

class TestUserCapacity:
    """Capacité d'utilisateurs actifs par société (max_users, défaut 1)."""

    def test_default_capacity_is_one(self, tmp_auth_db):
        import auth.auth_db as db
        sid = db.create_society("Cap", "CAP_DB", "https://sap.cap/b1s/v1")
        s = db.get_society_by_id(sid)
        assert s["max_users"] == 1

    def test_second_user_blocked_at_default_capacity(self, tmp_auth_db):
        import auth.auth_db as db
        sid = db.create_society("Cap", "CAP_DB", "https://sap.cap/b1s/v1")  # max 1
        db.create_user(sid, "u1", "User 1", "ADV")
        with pytest.raises(db.CapacityExceededError):
            db.create_user(sid, "u2", "User 2", "ADV")
        assert db.count_active_users(sid) == 1

    def test_capacity_is_parametrable_per_society(self, tmp_auth_db):
        import auth.auth_db as db
        sid = db.create_society("Cap3", "CAP3_DB", "https://sap.cap3/b1s/v1", max_users=3)
        db.create_user(sid, "a", "A", "ADV")
        db.create_user(sid, "b", "B", "ADV")
        db.create_user(sid, "c", "C", "ADV")
        assert db.count_active_users(sid) == 3
        with pytest.raises(db.CapacityExceededError):
            db.create_user(sid, "d", "D", "ADV")

    def test_deactivation_frees_a_slot(self, tmp_auth_db):
        import auth.auth_db as db
        sid = db.create_society("Cap4", "CAP4_DB", "https://sap.cap4/b1s/v1")  # max 1
        u1 = db.create_user(sid, "u1", "U1", "ADV")
        db.deactivate_user(u1)
        # Capacité libérée → on peut créer un nouvel utilisateur
        u2 = db.create_user(sid, "u2", "U2", "ADV")
        assert u2 > 0
        assert db.count_active_users(sid) == 1

    def test_reactivation_blocked_when_capacity_full(self, tmp_auth_db):
        import auth.auth_db as db
        sid = db.create_society("Cap5", "CAP5_DB", "https://sap.cap5/b1s/v1", max_users=2)
        db.create_user(sid, "u1", "U1", "ADV")
        u2 = db.create_user(sid, "u2", "U2", "ADV")
        db.deactivate_user(u2)
        # On resserre la capacité : u1 actif occupe déjà l'unique slot
        db.update_society(sid, max_users=1)
        with pytest.raises(db.CapacityExceededError):
            db.update_user(u2, is_active=1)
        assert db.count_active_users(sid) == 1

    def test_reactivation_allowed_when_slot_free(self, tmp_auth_db):
        import auth.auth_db as db
        sid = db.create_society("Cap6", "CAP6_DB", "https://sap.cap6/b1s/v1", max_users=2)
        u1 = db.create_user(sid, "u1", "U1", "ADV")
        db.deactivate_user(u1)
        assert db.update_user(u1, is_active=1) is True
        assert db.count_active_users(sid) == 1

    def test_update_non_activating_fields_not_blocked(self, tmp_auth_db):
        import auth.auth_db as db
        sid = db.create_society("Cap7", "CAP7_DB", "https://sap.cap7/b1s/v1")  # max 1
        u1 = db.create_user(sid, "u1", "U1", "ADV")
        # u1 déjà actif : renommer ne doit pas déclencher la garde capacité
        assert db.update_user(u1, display_name="Renommé") is True

    def test_migration_adds_max_users_to_existing_db(self, tmp_path, monkeypatch):
        """Une base créée AVANT max_users doit recevoir la colonne via _init_db."""
        import sqlite3
        import auth.auth_db as db
        legacy = tmp_path / "legacy_auth.db"
        # Base "ancienne" : table societies sans la colonne max_users
        conn = sqlite3.connect(str(legacy))
        conn.execute(
            """CREATE TABLE societies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                sap_company_db TEXT NOT NULL UNIQUE,
                sap_base_url TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )"""
        )
        conn.execute(
            "INSERT INTO societies (name, sap_company_db, sap_base_url) "
            "VALUES ('Old', 'OLD_DB', 'https://sap.old/b1s/v1')"
        )
        conn.commit()
        conn.close()

        monkeypatch.setattr(db, "DB_PATH", legacy)
        db._init_db()  # doit ajouter max_users sans perdre les données

        s = db.get_society_by_sap_company("OLD_DB")
        assert s is not None
        assert s["max_users"] == 1  # DEFAULT appliqué aux lignes existantes


# ── TestSessionEviction ───────────────────────────────────────────────────────

class TestSessionEviction:
    """Session unique par utilisateur : la connexion la plus récente évince l'ancienne."""

    @pytest.fixture(autouse=True)
    def _clean_store(self):
        from auth.sap_session import store
        store._store.clear()
        yield
        store._store.clear()

    def _make_session(self, user_id, society_id=1):
        from auth.sap_session import store
        now = datetime.now(timezone.utc)
        return store.create_session(
            b1_session=f"b1-{user_id}",
            sap_cookie_header=f"B1SESSION=b1-{user_id}",
            company_db="DB",
            sap_base_url="https://sap.test/b1s/v1",
            sap_user=f"user{user_id}",
            user_id=user_id,
            society_id=society_id,
            display_name="U",
            role="ADV",
            session_timeout_minutes=30,
            idle_expires_at=now + timedelta(minutes=30),
            absolute_expires_at=now + timedelta(minutes=60),
        )

    def test_evict_removes_user_sessions(self):
        from auth.sap_session import store
        s1 = self._make_session(42)
        assert store.get_session(s1.session_id) is not None
        evicted = store.evict_user_sessions(42)
        assert s1.session_id in evicted
        assert store.get_session(s1.session_id) is None

    def test_evict_spares_other_users(self):
        from auth.sap_session import store
        sa = self._make_session(1)
        sb = self._make_session(2)
        store.evict_user_sessions(1)
        assert store.get_session(sa.session_id) is None
        assert store.get_session(sb.session_id) is not None

    def test_login_route_evicts_previous_session(self, seeded_db, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from auth.sap_session import cookie_signing, store
        from auth.sap_session.sap_auth_service import SapLoginResult
        from routes.routes_sap_session import router

        # Secret requis pour signer le cookie pa_session (lu au runtime).
        monkeypatch.setattr(cookie_signing, "_SECRET", "test_cookie_secret_32_chars_long!!")

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        fake = SapLoginResult(
            b1_session="b1",
            sap_cookie_header="B1SESSION=b1",
            session_timeout_minutes=30,
        )
        body = {"companyDb": "TEST_DB", "userName": "admin_user", "password": "x"}
        with patch("routes.routes_sap_session.sap_login", new_callable=AsyncMock, return_value=fake):
            r1 = client.post("/api/sapauth/login", json=body)
            assert r1.status_code == 200
            assert store.count_active_sessions() == 1
            r2 = client.post("/api/sapauth/login", json=body)
            assert r2.status_code == 200

        # La 2e connexion a évincé la 1re : une seule session active subsiste
        assert store.count_active_sessions() == 1
