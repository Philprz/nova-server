"""
scripts/seed_rondot.py
Initialisation de nova_auth.db pour RONDOT SAS.
Idempotent : safe à relancer plusieurs fois.

Usage :
    .venv\\Scripts\\python.exe scripts/seed_rondot.py
"""

import os
import sys

# Ajouter la racine du projet au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth.auth_db import (
    _init_db,
    create_mailbox,
    create_society,
    create_user,
    get_mailbox_by_address,
    get_society_by_sap_company,
    get_user_by_sap_login,
    grant_mailbox_permission,
)

# ── Données RONDOT ─────────────────────────────────────────────────────────────

SOCIETY = {
    "name":           "RONDOT SAS",
    "sap_company_db": "RON_20260109",
    "sap_base_url":   "https://141.94.132.62:50000/b1s/v1",
}

USERS = [
    {
        "sap_username": "manager",
        "display_name": "Manager RONDOT",
        "role":         "ADMIN",
    },
    # Ajouter d'autres utilisateurs ici si nécessaire
    # {"sap_username": "adv1", "display_name": "ADV 1", "role": "ADV"},
]

MAILBOXES = [
    {
        "address":      "devis@rondot-poc.itspirit.ovh",
        "display_name": "Devis RONDOT",
        "ms_tenant_id": "203feedd-7ba1-4180-a7c4-bb0d4e1d238f",
    },
]


# ── Seed ───────────────────────────────────────────────────────────────────────

def seed():
    print("── Initialisation nova_auth.db ──────────────────────────")
    _init_db()

    # 1. Société
    existing_society = get_society_by_sap_company(SOCIETY["sap_company_db"])
    if not existing_society:
        sid = create_society(**SOCIETY)
        print(f"[+] Société créée : {SOCIETY['name']} (id={sid})")
    else:
        sid = existing_society["id"]
        print(f"[=] Société déjà présente : {SOCIETY['name']} (id={sid})")

    # 2. Utilisateurs
    user_ids: dict = {}
    for u in USERS:
        existing = get_user_by_sap_login(sid, u["sap_username"])
        if not existing:
            uid = create_user(
                society_id=sid,
                sap_username=u["sap_username"],
                display_name=u["display_name"],
                role=u["role"],
            )
            print(f"[+] Utilisateur créé : {u['sap_username']} role={u['role']} (id={uid})")
        else:
            uid = existing["id"]
            print(f"[=] Utilisateur déjà présent : {u['sap_username']} (id={uid})")
        user_ids[u["sap_username"]] = {"id": uid, "role": u["role"]}

    # 3. Boîtes mail
    mailbox_ids: dict = {}
    for m in MAILBOXES:
        existing = get_mailbox_by_address(m["address"])
        if not existing:
            mid = create_mailbox(
                society_id=sid,
                address=m["address"],
                display_name=m.get("display_name"),
                ms_tenant_id=m.get("ms_tenant_id"),
            )
            print(f"[+] Boîte mail créée : {m['address']} (id={mid})")
        else:
            mid = existing["id"]
            print(f"[=] Boîte mail déjà présente : {m['address']} (id={mid})")
        mailbox_ids[m["address"]] = mid

    # 4. Permissions : tous les users sur toutes les boîtes
    for sap_user, info in user_ids.items():
        can_write = info["role"] in ("ADMIN", "MANAGER")
        for address, mid in mailbox_ids.items():
            grant_mailbox_permission(
                user_id=info["id"],
                mailbox_id=mid,
                can_write=can_write,
                granted_by=info["id"],
            )
            print(
                f"[+] Permission : {sap_user} → {address} "
                f"(read=True, write={can_write})"
            )

    print()
    print("✓ Seed terminé. nova_auth.db prête pour RONDOT SAS.")
    print()
    print("  Prochaine étape : ajouter dans .env")
    print("  NOVA_JWT_SECRET=<python -c \"import secrets; print(secrets.token_hex(32))\">")


if __name__ == "__main__":
    seed()
