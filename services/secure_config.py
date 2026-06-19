"""
Coffre de configuration chiffre pour NOVA (Lot 1 - SPEC_COMPILATION_RONDOT).

Objectif : regrouper l'integralite des paires cle/valeur de configuration
(aujourd'hui dispersees dans .env) dans un unique fichier chiffre authentifie
`secrets.enc`, dechiffrable au demarrage via une cle maitre.

ETAT (Lot 1) : brique inerte. Aucune fonction de ce module n'est appelee
automatiquement au runtime. Le branchement dans le lanceur interviendra au Lot 3.

Distinction avec services/encryption_service.py : ce dernier chiffre des valeurs
individuelles (cles API stockees en base) via NOVA_ENCRYPTION_KEY. Le present
module chiffre le coffre complet de configuration via NOVA_VAULT_KEY. Les deux
sont independants.
"""

import os
import json
import logging
from typing import Dict, Union

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


_MASTER_KEY_ENV_VAR = "NOVA_VAULT_KEY"
DEFAULT_VAULT_PATH = "secrets.enc"


def get_master_key() -> bytes:
    """
    Retourne la cle maitre Fernet servant a chiffrer/dechiffrer le coffre.

    POUR L'INSTANT : la cle est lue depuis la variable d'environnement
    NOVA_VAULT_KEY. Erreur explicite si elle est absente.

    TODO Lot 5 : cette cle deviendra une constante embarquee dans un module
    compile en .pyd (jamais livree en clair dans un fichier .py ni dans le
    coffre lui-meme). A ce moment, le corps de cette fonction sera remplace par
    le retour direct de la constante compilee. La signature reste inchangee pour
    ne rien casser en aval.
    """
    key = os.getenv(_MASTER_KEY_ENV_VAR)
    if not key:
        raise RuntimeError(
            f"{_MASTER_KEY_ENV_VAR} absente de l'environnement. "
            f"Cle maitre requise pour acceder au coffre chiffre. "
            f"Generer une cle avec 'python scripts/provision_secrets.py --genkey'."
        )
    return key.encode("ascii") if isinstance(key, str) else key


def _parse_env_file(path: str) -> Dict[str, str]:
    """
    Parse un fichier .env en dictionnaire {cle: valeur}.

    Regles : ignore les lignes vides et les commentaires (#), supporte le
    prefixe optionnel 'export ', coupe sur le premier '=', retire les
    guillemets simples/doubles entourant la valeur. Ne fait aucune
    interpolation de variables.
    """
    pairs: Dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):].lstrip()
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            if key:
                pairs[key] = value
    return pairs


def encrypt_env_to_vault(
    source: Union[str, Dict[str, str]],
    out_path: str = DEFAULT_VAULT_PATH,
) -> str:
    """
    Chiffre l'ensemble des paires cle/valeur dans un coffre Fernet authentifie.

    `source` : chemin d'un fichier .env, ou dictionnaire {cle: valeur} deja construit.
    `out_path` : chemin du coffre chiffre a ecrire (defaut: secrets.enc).

    Retourne le chemin du coffre ecrit. Le contenu est serialise en JSON puis
    chiffre avec Fernet (AES-128-CBC + HMAC-SHA256, authentifie).
    """
    if isinstance(source, dict):
        pairs = {str(k): str(v) for k, v in source.items()}
    else:
        pairs = _parse_env_file(source)

    payload = json.dumps(pairs, ensure_ascii=False, sort_keys=True).encode("utf-8")
    token = Fernet(get_master_key()).encrypt(payload)

    with open(out_path, "wb") as fh:
        fh.write(token)

    logger.info("Coffre chiffre ecrit dans %s (%d paires).", out_path, len(pairs))
    return out_path


def decrypt_vault(path: str = DEFAULT_VAULT_PATH) -> Dict[str, str]:
    """
    Dechiffre le coffre et retourne le dictionnaire {cle: valeur}.

    Leve RuntimeError si la cle maitre est invalide/erronee ou si le coffre est
    corrompu (echec d'authentification Fernet).
    """
    with open(path, "rb") as fh:
        token = fh.read()

    try:
        raw = Fernet(get_master_key()).decrypt(token)
    except InvalidToken as exc:
        raise RuntimeError(
            f"Echec de dechiffrement du coffre {path} : cle maitre erronee ou "
            f"coffre corrompu (authentification Fernet invalide)."
        ) from exc

    return json.loads(raw.decode("utf-8"))


def load_secrets_into_environ(path: str = DEFAULT_VAULT_PATH) -> int:
    """
    Dechiffre le coffre et injecte chaque paire dans os.environ via setdefault.

    setdefault : ne JAMAIS ecraser une variable deja posee par l'OS / le shell.
    Retourne le nombre de paires presentes dans le coffre.

    IMPORTANT (Lot 1) : ne pas appeler cette fonction automatiquement. Son
    branchement dans le lanceur (avant tout import applicatif) est prevu au Lot 3.
    """
    pairs = decrypt_vault(path)
    for key, value in pairs.items():
        os.environ.setdefault(key, value)
    logger.info("%d paires de configuration chargees depuis le coffre %s.", len(pairs), path)
    return len(pairs)
