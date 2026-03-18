"""
NOVA Auth DB — nova_auth.db
Gestion des sociétés, utilisateurs NOVA, boîtes mail et permissions.
Pattern identique aux autres modules SQLite du projet.
"""

import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "data" / "nova_auth.db"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _init_db() -> None:
    """Initialise toutes les tables. Appelé au démarrage de l'application."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS societies (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT    NOT NULL UNIQUE,
            sap_company_db  TEXT    NOT NULL UNIQUE,
            sap_base_url    TEXT    NOT NULL,
            is_active       INTEGER NOT NULL DEFAULT 1,
            created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS nova_users (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            society_id      INTEGER NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
            sap_username    TEXT    NOT NULL,
            display_name    TEXT    NOT NULL,
            role            TEXT    NOT NULL
                            CHECK (role IN ('ADMIN','MANAGER','ADV')),
            is_active       INTEGER NOT NULL DEFAULT 1,
            last_login_at   TEXT,
            created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at      TEXT    NOT NULL DEFAULT (datetime('now')),
            UNIQUE (society_id, sap_username)
        );

        CREATE TABLE IF NOT EXISTS mailboxes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            society_id      INTEGER NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
            address         TEXT    NOT NULL UNIQUE,
            display_name    TEXT,
            ms_tenant_id    TEXT,
            is_active       INTEGER NOT NULL DEFAULT 1,
            created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS user_mailbox_permissions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES nova_users(id) ON DELETE CASCADE,
            mailbox_id  INTEGER NOT NULL REFERENCES mailboxes(id) ON DELETE CASCADE,
            can_read    INTEGER NOT NULL DEFAULT 1,
            can_write   INTEGER NOT NULL DEFAULT 0,
            granted_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            granted_by  INTEGER REFERENCES nova_users(id),
            UNIQUE (user_id, mailbox_id)
        );

        CREATE TABLE IF NOT EXISTS refresh_tokens (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES nova_users(id) ON DELETE CASCADE,
            token_hash  TEXT    NOT NULL UNIQUE,
            expires_at  TEXT    NOT NULL,
            revoked     INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_nova_users_society   ON nova_users(society_id);
        CREATE INDEX IF NOT EXISTS idx_nova_users_sap_login ON nova_users(sap_username, society_id);
        CREATE INDEX IF NOT EXISTS idx_mailboxes_society    ON mailboxes(society_id);
        CREATE INDEX IF NOT EXISTS idx_ump_user             ON user_mailbox_permissions(user_id);
        CREATE INDEX IF NOT EXISTS idx_ump_mailbox          ON user_mailbox_permissions(mailbox_id);
        CREATE INDEX IF NOT EXISTS idx_refresh_user         ON refresh_tokens(user_id);
        CREATE INDEX IF NOT EXISTS idx_refresh_hash         ON refresh_tokens(token_hash);
    """)

    conn.commit()
    conn.close()
    logger.info("nova_auth.db initialisée")


# ── Societies ──────────────────────────────────────────────────────────────────

def create_society(name: str, sap_company_db: str, sap_base_url: str) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO societies (name, sap_company_db, sap_base_url) VALUES (?, ?, ?)",
        (name, sap_company_db, sap_base_url),
    )
    conn.commit()
    society_id = cursor.lastrowid
    conn.close()
    return society_id


def get_society_by_id(society_id: int) -> Optional[Dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM societies WHERE id = ?", (society_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_society_by_sap_company(sap_company_db: str) -> Optional[Dict]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM societies WHERE sap_company_db = ? AND is_active = 1",
        (sap_company_db,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def list_societies() -> List[Dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM societies ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_society(society_id: int, **kwargs) -> bool:
    allowed = {"name", "sap_base_url", "is_active"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return False
    fields["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [society_id]
    conn = get_connection()
    cursor = conn.execute(f"UPDATE societies SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


# ── Nova Users ─────────────────────────────────────────────────────────────────

def create_user(society_id: int, sap_username: str, display_name: str, role: str) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO nova_users (society_id, sap_username, display_name, role) VALUES (?, ?, ?, ?)",
        (society_id, sap_username, display_name, role),
    )
    conn.commit()
    user_id = cursor.lastrowid
    conn.close()
    return user_id


def get_user_by_id(user_id: int) -> Optional[Dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM nova_users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_sap_login(society_id: int, sap_username: str) -> Optional[Dict]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM nova_users WHERE society_id = ? AND sap_username = ? AND is_active = 1",
        (society_id, sap_username),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def list_users(society_id: Optional[int] = None) -> List[Dict]:
    conn = get_connection()
    if society_id is not None:
        rows = conn.execute(
            "SELECT * FROM nova_users WHERE society_id = ? ORDER BY display_name",
            (society_id,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM nova_users ORDER BY society_id, display_name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_user(user_id: int, **kwargs) -> bool:
    allowed = {"display_name", "role", "is_active"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return False
    fields["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [user_id]
    conn = get_connection()
    cursor = conn.execute(f"UPDATE nova_users SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def deactivate_user(user_id: int) -> bool:
    return update_user(user_id, is_active=0)


def touch_last_login(user_id: int) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE nova_users SET last_login_at = ? WHERE id = ?",
        (datetime.now().isoformat(), user_id),
    )
    conn.commit()
    conn.close()


# ── Mailboxes ──────────────────────────────────────────────────────────────────

def create_mailbox(
    society_id: int,
    address: str,
    display_name: Optional[str] = None,
    ms_tenant_id: Optional[str] = None,
) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO mailboxes (society_id, address, display_name, ms_tenant_id) VALUES (?, ?, ?, ?)",
        (society_id, address, display_name, ms_tenant_id),
    )
    conn.commit()
    mailbox_id = cursor.lastrowid
    conn.close()
    return mailbox_id


def get_mailbox_by_id(mailbox_id: int) -> Optional[Dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM mailboxes WHERE id = ?", (mailbox_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_mailbox_by_address(address: str) -> Optional[Dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM mailboxes WHERE address = ?", (address,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_mailboxes(society_id: Optional[int] = None) -> List[Dict]:
    conn = get_connection()
    if society_id is not None:
        rows = conn.execute(
            "SELECT * FROM mailboxes WHERE society_id = ? ORDER BY address",
            (society_id,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM mailboxes ORDER BY society_id, address").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_mailbox(mailbox_id: int, **kwargs) -> bool:
    allowed = {"display_name", "ms_tenant_id", "is_active"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [mailbox_id]
    conn = get_connection()
    cursor = conn.execute(f"UPDATE mailboxes SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


# ── Permissions ────────────────────────────────────────────────────────────────

def grant_mailbox_permission(
    user_id: int,
    mailbox_id: int,
    can_write: bool = False,
    granted_by: Optional[int] = None,
) -> None:
    conn = get_connection()
    conn.execute(
        """INSERT INTO user_mailbox_permissions (user_id, mailbox_id, can_read, can_write, granted_by)
           VALUES (?, ?, 1, ?, ?)
           ON CONFLICT(user_id, mailbox_id) DO UPDATE SET can_write = excluded.can_write""",
        (user_id, mailbox_id, int(can_write), granted_by),
    )
    conn.commit()
    conn.close()


def revoke_mailbox_permission(user_id: int, mailbox_id: int) -> None:
    conn = get_connection()
    conn.execute(
        "DELETE FROM user_mailbox_permissions WHERE user_id = ? AND mailbox_id = ?",
        (user_id, mailbox_id),
    )
    conn.commit()
    conn.close()


def get_user_mailbox_ids(user_id: int) -> List[int]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT mailbox_id FROM user_mailbox_permissions WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    conn.close()
    return [r["mailbox_id"] for r in rows]


def get_user_mailbox_addresses(user_id: int) -> List[str]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT m.address FROM mailboxes m
           JOIN user_mailbox_permissions p ON p.mailbox_id = m.id
           WHERE p.user_id = ? AND m.is_active = 1""",
        (user_id,),
    ).fetchall()
    conn.close()
    return [r["address"] for r in rows]


def check_mailbox_permission(user_id: int, mailbox_id: int) -> Optional[Dict]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM user_mailbox_permissions WHERE user_id = ? AND mailbox_id = ?",
        (user_id, mailbox_id),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def list_user_permissions(user_id: int) -> List[Dict]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT p.*, m.address, m.display_name AS mailbox_name
           FROM user_mailbox_permissions p
           JOIN mailboxes m ON m.id = p.mailbox_id
           WHERE p.user_id = ?""",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Refresh Tokens ─────────────────────────────────────────────────────────────

def store_refresh_token(user_id: int, token_hash: str, expires_at: str) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO refresh_tokens (user_id, token_hash, expires_at) VALUES (?, ?, ?)",
        (user_id, token_hash, expires_at),
    )
    conn.commit()
    conn.close()


def get_refresh_token(token_hash: str) -> Optional[Dict]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM refresh_tokens WHERE token_hash = ? AND revoked = 0",
        (token_hash,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def revoke_refresh_token(token_hash: str) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE refresh_tokens SET revoked = 1 WHERE token_hash = ?",
        (token_hash,),
    )
    conn.commit()
    conn.close()


def revoke_all_user_tokens(user_id: int) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE refresh_tokens SET revoked = 1 WHERE user_id = ?",
        (user_id,),
    )
    conn.commit()
    conn.close()


def cleanup_expired_tokens() -> int:
    conn = get_connection()
    cursor = conn.execute(
        "DELETE FROM refresh_tokens WHERE expires_at < ?",
        (datetime.now().isoformat(),),
    )
    conn.commit()
    count = cursor.rowcount
    conn.close()
    if count:
        logger.info(f"Refresh tokens expirés supprimés : {count}")
    return count
