"""
Outil de provisioning hors-ligne du coffre chiffre NOVA (Lot 1).

Lance par IT SPIRIT au deploiement, ou pour regenerer le coffre hors UI.

Usages :
  - Generer une cle maitre a conserver :
        python scripts/provision_secrets.py --genkey

  - Produire secrets.enc a partir d'un .env (ou d'un template rempli) :
        # la cle maitre doit etre dans l'environnement (NOVA_VAULT_KEY)
        python scripts/provision_secrets.py --source .env --out secrets.enc

Aucun emoji. Messages explicites. N'ecrit jamais la cle maitre sur disque.
"""

import os
import sys
import argparse

# Permet l'execution directe (python scripts/provision_secrets.py) en ajoutant
# la racine du projet au path d'import.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cryptography.fernet import Fernet

from services import secure_config


def _cmd_genkey() -> int:
    key = Fernet.generate_key().decode("ascii")
    print("Cle maitre generee (Fernet, base64). A conserver dans un endroit sur.")
    print("Elle ne sera PAS reaffichee et n'est ecrite nulle part sur disque.")
    print("")
    print(f"NOVA_VAULT_KEY={key}")
    print("")
    print("Pour generer le coffre, exposer cette cle dans l'environnement puis :")
    print("  python scripts/provision_secrets.py --source .env --out secrets.enc")
    return 0


def _cmd_build(source: str, out_path: str) -> int:
    if not os.path.isfile(source):
        print(f"ERREUR : fichier source introuvable : {source}", file=sys.stderr)
        return 1

    if not os.getenv("NOVA_VAULT_KEY"):
        print(
            "ERREUR : NOVA_VAULT_KEY absente de l'environnement.\n"
            "Generer une cle avec --genkey puis l'exposer avant de construire le coffre.",
            file=sys.stderr,
        )
        return 1

    try:
        written = secure_config.encrypt_env_to_vault(source, out_path=out_path)
    except Exception as exc:  # noqa: BLE001 - on veut un message CLI clair
        print(f"ERREUR : echec de construction du coffre : {exc}", file=sys.stderr)
        return 1

    # Relecture de verification : confirme que le coffre est dechiffrable.
    try:
        pairs = secure_config.decrypt_vault(written)
    except Exception as exc:  # noqa: BLE001
        print(f"ERREUR : coffre ecrit mais non relisible : {exc}", file=sys.stderr)
        return 1

    print(f"Coffre chiffre ecrit : {written}")
    print(f"Paires chiffrees : {len(pairs)}")
    print("Verification de relecture : OK")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="provision_secrets",
        description="Genere une cle maitre ou produit le coffre chiffre secrets.enc.",
    )
    parser.add_argument(
        "--genkey",
        action="store_true",
        help="Genere et affiche une cle maitre Fernet a conserver.",
    )
    parser.add_argument(
        "--source",
        metavar="CHEMIN",
        help="Fichier .env (ou template rempli) a chiffrer.",
    )
    parser.add_argument(
        "--out",
        metavar="CHEMIN",
        default=secure_config.DEFAULT_VAULT_PATH,
        help=f"Chemin du coffre a ecrire (defaut: {secure_config.DEFAULT_VAULT_PATH}).",
    )

    args = parser.parse_args(argv)

    if args.genkey:
        return _cmd_genkey()

    if args.source:
        return _cmd_build(args.source, args.out)

    parser.print_help(sys.stderr)
    print(
        "\nERREUR : indiquer soit --genkey, soit --source <fichier>.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
