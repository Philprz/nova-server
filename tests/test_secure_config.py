"""
Tests du coffre de configuration chiffre (services/secure_config.py - Lot 1).

Couvre : round-trip .env -> chiffrement -> relecture avec egalite stricte des
paires, et echec d'authentification avec une cle maitre erronee.

Usage :
    .venv\\Scripts\\python.exe -m pytest tests/test_secure_config.py -v
"""

import os
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

# Racine du projet dans le path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services import secure_config


SAMPLE_ENV = """\
# Exemple de configuration NOVA
APP_PORT=8001
DATABASE_URL=sqlite:///./nova.db
SAP_USER=manager
SAP_PASSWORD=p@ss=word/with:special
# Commentaire intermediaire ignore

EMPTY_VALUE=
QUOTED_DOUBLE="valeur entre guillemets"
QUOTED_SINGLE='autre valeur'
export EXPORTED_KEY=exported_value
"""

EXPECTED_PAIRS = {
    "APP_PORT": "8001",
    "DATABASE_URL": "sqlite:///./nova.db",
    "SAP_USER": "manager",
    "SAP_PASSWORD": "p@ss=word/with:special",
    "EMPTY_VALUE": "",
    "QUOTED_DOUBLE": "valeur entre guillemets",
    "QUOTED_SINGLE": "autre valeur",
    "EXPORTED_KEY": "exported_value",
}


@pytest.fixture
def master_key(monkeypatch):
    """Pose une cle maitre Fernet valide dans l'environnement pour le test."""
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("NOVA_VAULT_KEY", key)
    return key


@pytest.fixture
def sample_env_file(tmp_path):
    env_path = tmp_path / "sample.env"
    env_path.write_text(SAMPLE_ENV, encoding="utf-8")
    return str(env_path)


def test_roundtrip_from_env_file(master_key, sample_env_file, tmp_path):
    """Chiffre un .env puis le relit : egalite stricte des paires attendues."""
    vault = str(tmp_path / "secrets.enc")
    secure_config.encrypt_env_to_vault(sample_env_file, out_path=vault)

    assert os.path.isfile(vault)
    decrypted = secure_config.decrypt_vault(vault)
    assert decrypted == EXPECTED_PAIRS


def test_roundtrip_from_dict(master_key, tmp_path):
    """Chiffre un dict source puis le relit : egalite stricte."""
    source = {"FOO": "bar", "BAZ": "42", "URL": "https://example/x?y=1&z=2"}
    vault = str(tmp_path / "secrets.enc")
    secure_config.encrypt_env_to_vault(source, out_path=vault)

    assert secure_config.decrypt_vault(vault) == source


def test_wrong_master_key_fails_authentication(master_key, sample_env_file, tmp_path, monkeypatch):
    """Une cle maitre erronee doit faire echouer le dechiffrement (integrite)."""
    vault = str(tmp_path / "secrets.enc")
    secure_config.encrypt_env_to_vault(sample_env_file, out_path=vault)

    # On remplace la cle maitre par une autre cle valide mais differente.
    wrong_key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("NOVA_VAULT_KEY", wrong_key)

    with pytest.raises(RuntimeError):
        secure_config.decrypt_vault(vault)


def test_missing_master_key_raises():
    """Absence de NOVA_VAULT_KEY -> erreur explicite."""
    saved = os.environ.pop("NOVA_VAULT_KEY", None)
    try:
        with pytest.raises(RuntimeError):
            secure_config.get_master_key()
    finally:
        if saved is not None:
            os.environ["NOVA_VAULT_KEY"] = saved


def test_load_secrets_into_environ_setdefault(master_key, tmp_path, monkeypatch):
    """load_secrets_into_environ injecte les paires sans ecraser l'existant."""
    source = {"NEW_VAR_LOT1": "from_vault", "EXISTING_VAR_LOT1": "from_vault"}
    vault = str(tmp_path / "secrets.enc")
    secure_config.encrypt_env_to_vault(source, out_path=vault)

    # Variable deja posee par l'OS : ne doit PAS etre ecrasee.
    monkeypatch.setenv("EXISTING_VAR_LOT1", "from_os")
    monkeypatch.delenv("NEW_VAR_LOT1", raising=False)

    count = secure_config.load_secrets_into_environ(vault)

    assert count == 2
    assert os.environ["EXISTING_VAR_LOT1"] == "from_os"
    assert os.environ["NEW_VAR_LOT1"] == "from_vault"
