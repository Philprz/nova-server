"""
run.py — Point d'entree mince et NON compile de NOVA (Lot 3 - SPEC_COMPILATION_RONDOT).

Raison d'etre : un module compile en .pyd ne peut pas se lancer via
`python main.pyd`. Ce lanceur reste en .py et orchestre le demarrage.

Contrainte d'ordonnancement CRITIQUE (cf. SPEC, section "Contrainte d'ordonnancement") :
db/session.py lit DATABASE_URL a l'import et leve une RuntimeError si absent,
et main.py fait load_dotenv() en haut de module. Le coffre doit donc peupler
os.environ AVANT le premier import de `main` / `db` / `routes`.

Ordre EXACT respecte ci-dessous :
  1. Chargement OPTIONNEL du coffre chiffre (secrets.enc + NOVA_VAULT_KEY).
     Si absent -> on ne fait rien, le comportement .env actuel prend le relais.
     Aucune exception n'est levee si le coffre est absent.
  2. Migrations Alembic OPTIONNELLES (Lot 4) : seulement si NOVA_AUTO_MIGRATE
     vaut "true"/"1". Par defaut : ne rien faire (comportement actuel preserve).
     Si actif et que la migration echoue : c'est FATAL (arret du demarrage), PAS
     de repli gracieux ici (contrairement au coffre) — on ne lance jamais uvicorn
     sur une base potentiellement a moitie migree.
  3. SEULEMENT APRES : import de l'app (`from main import app`) + uvicorn.
  4. Reprise a l'identique de la logique du bloc __main__ de main.py.

NOTE : le bloc __main__ de main.py est CONSERVE en repli (compat dev :
`python main.py` fonctionne toujours).
"""

import os
import sys
import logging

from services.secure_config import DEFAULT_VAULT_PATH

_MASTER_KEY_ENV_VAR = "NOVA_VAULT_KEY"


def _load_vault_if_present() -> None:
    """
    Charge le coffre chiffre dans os.environ s'il est present ET que la cle
    maitre est definie. Sinon, ne fait rien (repli sur .env via load_dotenv()
    dans main.py). Ne leve JAMAIS d'exception si le coffre est simplement absent.

    Logue clairement lequel des deux modes est actif :
      - mode COFFRE : secrets.enc + NOVA_VAULT_KEY presents
      - mode .env   : sinon
    """
    # Handler temporaire : main.py configure le logging (RotatingFileHandler ->
    # nova.log) a son import, et logging.basicConfig() est un no-op si le root
    # logger a deja des handlers. On installe donc un handler console JETABLE
    # juste pour cette phase pre-import, puis on le RETIRE avant d'importer main,
    # afin de ne pas court-circuiter la configuration logging definitive.
    root = logging.getLogger()
    _tmp_handler = logging.StreamHandler(sys.stdout)
    _tmp_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    _prev_level = root.level
    root.addHandler(_tmp_handler)
    root.setLevel(logging.INFO)
    log = logging.getLogger("run")

    try:
        vault_path = os.getenv("NOVA_VAULT_PATH", DEFAULT_VAULT_PATH)
        vault_exists = os.path.isfile(vault_path)
        key_present = bool(os.getenv(_MASTER_KEY_ENV_VAR))

        if vault_exists and key_present:
            try:
                from services.secure_config import load_secrets_into_environ
                count = load_secrets_into_environ(vault_path)
                log.info(
                    "Mode COFFRE actif : %d paire(s) chargee(s) depuis le coffre chiffre '%s'.",
                    count, vault_path,
                )
            except Exception as exc:
                # Le coffre existe mais le dechiffrement echoue (cle erronee,
                # coffre corrompu). On NE bloque PAS le demarrage : repli sur
                # .env. On signale clairement l'anomalie.
                log.error(
                    "Mode COFFRE indisponible : echec d'ouverture du coffre '%s' (%s). "
                    "Repli sur le mode .env.",
                    vault_path, exc,
                )
        else:
            if vault_exists and not key_present:
                log.warning(
                    "Coffre '%s' present mais %s absente de l'environnement : repli sur le mode .env.",
                    vault_path, _MASTER_KEY_ENV_VAR,
                )
            else:
                log.info(
                    "Mode .env actif : pas de coffre chiffre detecte (%s introuvable). "
                    "La configuration sera lue depuis .env par main.py.",
                    vault_path,
                )
    finally:
        # CRITIQUE : retirer le handler jetable pour rendre le root logger
        # vierge, afin que le logging.basicConfig() de main.py s'applique.
        root.removeHandler(_tmp_handler)
        root.setLevel(_prev_level)


_AUTO_MIGRATE_ENV_VAR = "NOVA_AUTO_MIGRATE"


def _run_migrations_if_enabled() -> None:
    """
    Execute 'alembic upgrade head' par programme, UNIQUEMENT si NOVA_AUTO_MIGRATE
    vaut "true" ou "1". Par defaut (variable absente/autre valeur) : ne fait
    STRICTEMENT RIEN -> comportement actuel preserve a l'identique.

    A executer APRES le chargement du coffre (DATABASE_URL doit etre dans
    os.environ) et AVANT 'from main import app'. alembic/env.py refait son propre
    load_dotenv() et lit DATABASE_URL via os.getenv -> les deux modes (coffre /
    .env) fonctionnent.

    Politique d'erreur : a l'inverse du coffre, l'echec ici est FATAL. On NE
    lance PAS uvicorn sur une base potentiellement a moitie migree : on logue
    l'erreur et on quitte avec un code non nul (SystemExit(1)).
    """
    flag = os.getenv(_AUTO_MIGRATE_ENV_VAR, "").strip().lower()
    if flag not in ("true", "1"):
        return  # defaut : aucune migration declenchee

    # Handler console JETABLE pour la phase pre-import (meme raison que le coffre :
    # ne pas court-circuiter le logging.basicConfig() de main.py). alembic/env.py
    # appelle fileConfig() qui RECONFIGURE le root logger ; on restaure donc l'etat
    # initial du root logger en sortie, quoi qu'il arrive.
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    _tmp_handler = logging.StreamHandler(sys.stdout)
    _tmp_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))

    def _ensure_visible() -> None:
        # alembic/env.py (fileConfig) reconfigure le logging : il peut retirer
        # notre handler, remonter le niveau a WARNING, et surtout DESACTIVER les
        # loggers existants (disable_existing_loggers=True par defaut) -> notre
        # logger "run" devient muet. On retablit tout pour garder nos messages.
        if _tmp_handler not in root.handlers:
            root.addHandler(_tmp_handler)
        root.setLevel(logging.INFO)
        logging.getLogger("run").disabled = False

    _ensure_visible()
    log = logging.getLogger("run")

    try:
        log.info("%s actif : execution de 'alembic upgrade head'...", _AUTO_MIGRATE_ENV_VAR)
        from alembic.config import Config
        from alembic import command

        ini_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alembic.ini")
        cfg = Config(ini_path)
        command.upgrade(cfg, "head")

        _ensure_visible()
        log.info("Migrations Alembic appliquees avec succes (base a jour : head).")
    except Exception as exc:
        _ensure_visible()
        log.critical(
            "ECHEC des migrations Alembic (%s) : %s. "
            "Arret du demarrage : uvicorn NE sera PAS lance sur une base a moitie migree.",
            type(exc).__name__, exc, exc_info=True,
        )
        # FATAL : pas de repli gracieux. finally restaure le logging, puis on quitte.
        raise SystemExit(1)
    finally:
        # Restaurer l'etat initial du root logger pour que le basicConfig() de
        # main.py s'applique (RotatingFileHandler -> nova.log).
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)


# ── 1. Coffre AVANT tout import applicatif ────────────────────────────────────
_load_vault_if_present()

# ── 2. Migrations Alembic optionnelles (Lot 4) — FATAL si actives et en echec ─
_run_migrations_if_enabled()

# ── 3. SEULEMENT APRES : import de l'app (main devient main.pyd au Lot 5) ─────
import uvicorn
from main import app, kill_process_on_port


def main() -> None:
    """
    Reprend a l'identique la logique du bloc __main__ de main.py :
    encodage Windows, liberation du port, lecture APP_PORT, uvicorn.run.
    """
    # Configuration specifique pour Windows
    if sys.platform == "win32":
        # Configuration pour eviter les problemes d'encodage
        os.environ["PYTHONIOENCODING"] = "utf-8"
        # Liberer le port si occupe
        backend_port = int(os.getenv("APP_PORT", 8001))
        kill_process_on_port(backend_port)

    # Demarrage du serveur
    backend_port = int(os.getenv("APP_PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=backend_port, log_config=None, loop="asyncio")


# ── 4. Point d'entree ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
