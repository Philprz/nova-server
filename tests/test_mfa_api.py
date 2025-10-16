# tests/test_mfa_api.py - Tests d'intégration API MFA

import pytest
from httpx import AsyncClient
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone

# Imports NOVA
from main import app
from db.models import Base
from models.user import User, MFABackupMethod
from core.security import create_final_access_token, create_mfa_pending_token, get_password_hash
from routes.mfa import get_db


# Setup test database
TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Override de la dépendance get_db pour les tests."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="function")
def test_db():
    """Fixture pour créer une DB test propre à chaque test."""
    Base.metadata.create_all(bind=engine)
    yield TestingSessionLocal()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_user(test_db):
    """Fixture pour créer un utilisateur de test."""
    user = User(
        email="test@example.com",
        username="testuser",
        hashed_password=get_password_hash("password123"),
        full_name="Test User",
        is_active=True,
        is_superuser=False,
        mfa_enforced=True
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def test_user_with_totp(test_db):
    """Fixture pour utilisateur avec TOTP activé."""
    from services.mfa_totp import totp_service

    secret = totp_service.generate_secret()

    user = User(
        email="totp@example.com",
        username="totpuser",
        hashed_password=get_password_hash("password123"),
        is_active=True,
        totp_secret=secret,
        is_totp_enabled=True,
        totp_enrolled_at=datetime.now(timezone.utc)
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def access_token(test_user):
    """Token d'accès complet (post-MFA)."""
    return create_final_access_token(test_user.id, test_user.email, test_user.is_superuser)


@pytest.fixture
def mfa_pending_token(test_user):
    """Token mfa_pending (pré-MFA)."""
    return create_mfa_pending_token(test_user.id, test_user.email)


@pytest.fixture
def client():
    """Client de test FastAPI."""
    return TestClient(app)


# =====================================
# Tests TOTP Enrollment
# =====================================

def test_totp_enroll_start_success(client, test_user, access_token):
    """Test démarrage enrôlement TOTP."""
    response = client.post(
        "/api/mfa/totp/enroll/start",
        headers={"Authorization": f"Bearer {access_token}"}
    )

    assert response.status_code == 200
    data = response.json()

    assert "secret" in data
    assert "provisioning_uri" in data
    assert "qr_code" in data
    assert data["qr_code"].startswith("data:image/png;base64,")
    assert "otpauth://" in data["provisioning_uri"]


def test_totp_enroll_start_requires_auth(client):
    """Test enrôlement TOTP sans auth (doit échouer)."""
    response = client.post("/api/mfa/totp/enroll/start")

    assert response.status_code == 403  # Unauthorized


def test_totp_enroll_verify_success(client, test_db, test_user, access_token):
    """Test vérification enrôlement TOTP avec code valide."""
    from services.mfa_totp import totp_service

    # Démarrer enrôlement
    response_start = client.post(
        "/api/mfa/totp/enroll/start",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response_start.status_code == 200
    secret = response_start.json()["secret"]

    # Générer code valide
    current_code = totp_service.get_current_code(secret)

    # Vérifier
    response_verify = client.post(
        "/api/mfa/totp/enroll/verify",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"code": current_code}
    )

    assert response_verify.status_code == 200
    data = response_verify.json()

    assert data["success"] is True
    assert "recovery_codes" in data
    assert len(data["recovery_codes"]) == 10

    # Vérifier en DB
    test_db.refresh(test_user)
    assert test_user.is_totp_enabled is True
    assert test_user.recovery_codes_hashes is not None
    assert len(test_user.recovery_codes_hashes) == 10


def test_totp_enroll_verify_invalid_code(client, test_user, access_token):
    """Test vérification enrôlement avec code invalide."""
    # Démarrer enrôlement
    client.post(
        "/api/mfa/totp/enroll/start",
        headers={"Authorization": f"Bearer {access_token}"}
    )

    # Vérifier avec code invalide
    response = client.post(
        "/api/mfa/totp/enroll/verify",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"code": "000000"}
    )

    assert response.status_code == 400
    assert "Invalid TOTP code" in response.json()["detail"]


# =====================================
# Tests MFA Verification
# =====================================

def test_verify_totp_success(client, test_db, test_user_with_totp, mfa_pending_token):
    """Test vérification TOTP après login."""
    from services.mfa_totp import totp_service

    # Générer code valide
    current_code = totp_service.get_current_code(test_user_with_totp.totp_secret)

    # Vérifier
    response = client.post(
        "/api/mfa/verify/totp",
        headers={"Authorization": f"Bearer {mfa_pending_token}"},
        json={"code": current_code}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["mfa_ok"] is True
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_verify_totp_invalid_code(client, test_user_with_totp, mfa_pending_token):
    """Test vérification TOTP avec code invalide."""
    response = client.post(
        "/api/mfa/verify/totp",
        headers={"Authorization": f"Bearer {mfa_pending_token}"},
        json={"code": "000000"}
    )

    assert response.status_code == 400
    assert "Invalid TOTP code" in response.json()["detail"]


def test_verify_totp_requires_mfa_pending(client, test_user_with_totp, access_token):
    """Test vérification TOTP avec token complet (doit échouer)."""
    from services.mfa_totp import totp_service

    current_code = totp_service.get_current_code(test_user_with_totp.totp_secret)

    response = client.post(
        "/api/mfa/verify/totp",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"code": current_code}
    )

    assert response.status_code == 403
    assert "pending MFA token" in response.json()["detail"]


# =====================================
# Tests Recovery Codes
# =====================================

def test_verify_recovery_code_success(client, test_db, test_user_with_totp):
    """Test vérification recovery code."""
    from services.recovery_codes import recovery_service

    # Générer recovery codes
    codes_plain = recovery_service.generate_codes(10)
    codes_hashes = recovery_service.hash_codes(codes_plain)
    test_user_with_totp.recovery_codes_hashes = codes_hashes
    test_db.commit()

    # Token pending
    pending_token = create_mfa_pending_token(test_user_with_totp.id, test_user_with_totp.email)

    # Utiliser un recovery code
    response = client.post(
        "/api/mfa/verify/recovery",
        headers={"Authorization": f"Bearer {pending_token}"},
        json={"code": codes_plain[0]}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["mfa_ok"] is True
    assert "access_token" in data

    # Vérifier qu'il ne reste que 9 codes
    test_db.refresh(test_user_with_totp)
    assert len(test_user_with_totp.recovery_codes_hashes) == 9


def test_verify_recovery_code_already_used(client, test_db, test_user_with_totp):
    """Test réutilisation d'un recovery code (doit échouer)."""
    from services.recovery_codes import recovery_service

    codes_plain = recovery_service.generate_codes(5)
    codes_hashes = recovery_service.hash_codes(codes_plain)
    test_user_with_totp.recovery_codes_hashes = codes_hashes
    test_db.commit()

    pending_token = create_mfa_pending_token(test_user_with_totp.id, test_user_with_totp.email)

    # Utiliser le code une fois
    response1 = client.post(
        "/api/mfa/verify/recovery",
        headers={"Authorization": f"Bearer {pending_token}"},
        json={"code": codes_plain[0]}
    )
    assert response1.status_code == 200

    # Réessayer avec le même code (doit échouer)
    pending_token2 = create_mfa_pending_token(test_user_with_totp.id, test_user_with_totp.email)

    response2 = client.post(
        "/api/mfa/verify/recovery",
        headers={"Authorization": f"Bearer {pending_token2}"},
        json={"code": codes_plain[0]}
    )

    assert response2.status_code == 400
    assert "Invalid recovery code" in response2.json()["detail"]


def test_recovery_regenerate(client, test_db, test_user, access_token):
    """Test régénération recovery codes."""
    response = client.post(
        "/api/mfa/recovery/regenerate",
        headers={"Authorization": f"Bearer {access_token}"}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert len(data["recovery_codes"]) == 10

    # Vérifier en DB
    test_db.refresh(test_user)
    assert len(test_user.recovery_codes_hashes) == 10


def test_recovery_list(client, test_db, test_user, access_token):
    """Test liste recovery codes (masqués)."""
    from services.recovery_codes import recovery_service

    # Générer codes
    codes_plain = recovery_service.generate_codes(10)
    codes_hashes = recovery_service.hash_codes(codes_plain)
    test_user.recovery_codes_hashes = codes_hashes
    test_db.commit()

    response = client.get(
        "/api/mfa/recovery/list",
        headers={"Authorization": f"Bearer {access_token}"}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["count"] == 10
    # Les codes ne peuvent pas être affichés (hashes)


# =====================================
# Tests SMS
# =====================================

@pytest.mark.asyncio
async def test_sms_send_success(client, test_db, test_user):
    """Test envoi SMS OTP."""
    # Configurer téléphone vérifié
    test_user.phone_e164 = "+33612345678"
    test_user.is_phone_verified = True
    test_db.commit()

    pending_token = create_mfa_pending_token(test_user.id, test_user.email)

    response = client.post(
        "/api/mfa/sms/send",
        headers={"Authorization": f"Bearer {pending_token}"}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert "message_id" in data
    assert "expires_at" in data


def test_sms_send_no_phone(client, test_user, mfa_pending_token):
    """Test envoi SMS sans téléphone vérifié (doit échouer)."""
    response = client.post(
        "/api/mfa/sms/send",
        headers={"Authorization": f"Bearer {mfa_pending_token}"}
    )

    assert response.status_code == 400
    assert "not verified" in response.json()["detail"]


# =====================================
# Tests Phone Verification
# =====================================

@pytest.mark.asyncio
async def test_phone_set_and_verify(client, test_db, test_user, access_token):
    """Test configuration et vérification téléphone."""
    # Configurer téléphone
    response_set = client.post(
        "/api/mfa/phone/set",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"phone": "+33612345678"}
    )

    assert response_set.status_code == 200
    data_set = response_set.json()
    assert data_set["success"] is True

    # Vérifier en DB
    test_db.refresh(test_user)
    assert test_user.phone_e164 == "+33612345678"
    assert test_user.is_phone_verified is False

    # Récupérer OTP du stockage (pour test)
    from services.mfa_sms import sms_otp_service
    otp_data = sms_otp_service._get_otp_data(test_user.id)
    assert otp_data is not None
    code = otp_data["otp"]

    # Vérifier téléphone
    response_verify = client.post(
        "/api/mfa/phone/verify",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"code": code}
    )

    assert response_verify.status_code == 200
    data_verify = response_verify.json()
    assert data_verify["success"] is True

    # Vérifier en DB
    test_db.refresh(test_user)
    assert test_user.is_phone_verified is True


# =====================================
# Tests Status
# =====================================

def test_mfa_status(client, test_user_with_totp, access_token):
    """Test endpoint /mfa/status."""
    response = client.get(
        "/api/mfa/status",
        headers={"Authorization": f"Bearer {access_token}"}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["user_id"] == test_user_with_totp.id
    assert data["email"] == test_user_with_totp.email
    assert data["totp_enabled"] is True
    assert data["mfa_enforced"] is True


# =====================================
# Tests Rate Limiting
# =====================================

def test_rate_limiting_totp_verify(client, test_user_with_totp):
    """Test rate limiting sur vérification TOTP."""
    pending_token = create_mfa_pending_token(test_user_with_totp.id, test_user_with_totp.email)

    # Faire 11 requêtes (max 10/min)
    for i in range(11):
        response = client.post(
            "/api/mfa/verify/totp",
            headers={"Authorization": f"Bearer {pending_token}"},
            json={"code": "000000"}
        )

        if i < 10:
            assert response.status_code in (400, 200)  # Invalid code ou success
        else:
            # 11ème requête: rate limited
            assert response.status_code == 429
            assert "Too many requests" in str(response.json())


# =====================================
# Tests Anti-Bruteforce
# =====================================

def test_account_lockout_after_failures(client, test_db, test_user_with_totp):
    """Test verrouillage compte après 10 échecs."""
    pending_token = create_mfa_pending_token(test_user_with_totp.id, test_user_with_totp.email)

    # 10 tentatives échouées
    for _ in range(10):
        client.post(
            "/api/mfa/verify/totp",
            headers={"Authorization": f"Bearer {pending_token}"},
            json={"code": "000000"}
        )

    # Vérifier verrouillage en DB
    test_db.refresh(test_user_with_totp)
    assert test_user_with_totp.mfa_failed_attempts >= 10
    assert test_user_with_totp.mfa_lock_until is not None

    # Nouvelle tentative (doit être bloquée)
    pending_token2 = create_mfa_pending_token(test_user_with_totp.id, test_user_with_totp.email)

    response = client.post(
        "/api/mfa/verify/totp",
        headers={"Authorization": f"Bearer {pending_token2}"},
        json={"code": "123456"}
    )

    assert response.status_code == 429
    assert "locked" in response.json()["detail"]["error"]
