"""
Repository pour la persistance stricte des quote_draft.

Table quote_draft:
- Stocke TOUS les résultats SAP avec métadonnées complètes
- Garantit idempotence via UNIQUE constraint sur mail_id
- Structure JSONB lines avec search_metadata détaillées

IMPORTANT: AUCUNE requête SAP dans ce module - uniquement CRUD SQLite.
"""

import sqlite3
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class QuoteDraft(BaseModel):
    """
    Modèle Pydantic représentant un quote_draft complet.

    Structure lines[] (JSONB):
    [
        {
            "line_id": "uuid",
            "supplier_code": "HST-117-03",
            "description": "SIZE 3 PUSHER BLADE",
            "quantity": 50,
            "sap_item_code": "C315-6305RS" ou null,
            "sap_status": "FOUND" | "NOT_FOUND" | "AMBIGUOUS",
            "sap_price": 125.50 ou null,
            "search_metadata": {
                "search_type": "EXACT" | "FUZZY" | "HISTORICAL" | "MANUAL",
                "sap_query_used": "ItemCode eq 'HST-117-03'",
                "search_timestamp": "2026-02-13T10:30:00Z",
                "match_score": 100
            }
        }
    ]
    """
    id: str
    mail_id: str
    client_code: Optional[str] = None
    client_status: str  # FOUND | NOT_FOUND | AMBIGUOUS
    status: str = "ANALYZED"  # ANALYZED | VALIDATED | SAP_CREATED
    raw_email_payload: Dict[str, Any]
    lines: List[Dict[str, Any]]
    created_at: str
    updated_at: str


class QuoteRepository:
    """
    Repository pour accès base de données quote_draft.

    Responsabilités:
    - Créer/lire quote_draft avec structure stricte
    - Garantir idempotence via mail_id UNIQUE
    - Update lignes après retry SAP

    AUCUNE logique métier - uniquement CRUD.
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(Path(__file__).parent.parent / "email_analysis.db")
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialise la table quote_draft avec contraintes strictes."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Table quote_draft avec structure stricte
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS quote_draft (
                id TEXT PRIMARY KEY,
                mail_id TEXT UNIQUE NOT NULL,
                client_code TEXT,
                client_status TEXT CHECK (client_status IN ('FOUND','NOT_FOUND','AMBIGUOUS')),
                status TEXT CHECK (status IN ('ANALYZED','VALIDATED','SAP_CREATED')) DEFAULT 'ANALYZED',
                raw_email_payload TEXT NOT NULL,
                lines TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        # Index UNIQUE sur mail_id pour idempotence
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_quote_mail_id
            ON quote_draft(mail_id)
        """)

        # Index sur status pour filtrage
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_quote_status
            ON quote_draft(status)
        """)

        conn.commit()
        conn.close()

        logger.info(f"QuoteRepository initialized at {self.db_path}")

    def check_mail_id_exists(self, mail_id: str) -> bool:
        """
        Vérifie si un email a déjà été traité (idempotence).

        Args:
            mail_id: ID email Microsoft

        Returns:
            True si quote_draft existe pour ce mail_id
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT 1 FROM quote_draft WHERE mail_id = ?
        """, (mail_id,))

        exists = cursor.fetchone() is not None
        conn.close()

        return exists

    def create_quote_draft(
        self,
        mail_id: str,
        raw_payload: Dict[str, Any],
        client_code: Optional[str],
        client_status: str,
        lines: List[Dict[str, Any]]
    ) -> str:
        """
        Crée un quote_draft avec structure stricte.

        Args:
            mail_id: ID email Microsoft (UNIQUE)
            raw_payload: Email complet (subject, body, from_address, pdf_contents)
            client_code: CardCode SAP ou None si NOT_FOUND
            client_status: FOUND | NOT_FOUND | AMBIGUOUS
            lines: Liste lignes avec métadonnées SAP complètes
                [
                    {
                        "line_id": "uuid",
                        "supplier_code": "HST-117-03",
                        "description": "...",
                        "quantity": 50,
                        "sap_item_code": "C315-6305RS" ou null,
                        "sap_status": "FOUND",
                        "sap_price": 125.50,
                        "search_metadata": {...}
                    }
                ]

        Returns:
            quote_id (UUID)

        Raises:
            sqlite3.IntegrityError: Si mail_id existe déjà
        """
        quote_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat() + "Z"

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO quote_draft (
                    id, mail_id, client_code, client_status,
                    status, raw_email_payload, lines,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'ANALYZED', ?, ?, ?, ?)
            """, (
                quote_id,
                mail_id,
                client_code,
                client_status,
                json.dumps(raw_payload, ensure_ascii=False),
                json.dumps(lines, ensure_ascii=False),
                timestamp,
                timestamp
            ))

            conn.commit()
            logger.info(f"✅ Quote draft created: {quote_id} for mail {mail_id[:20]}...")

        except sqlite3.IntegrityError as e:
            logger.warning(f"⚠️ Quote draft already exists for mail_id {mail_id}")
            raise

        finally:
            conn.close()

        return quote_id

    def get_quote_draft(self, quote_id: str) -> Optional[QuoteDraft]:
        """
        Récupère un quote_draft depuis DB (LECTURE SEULE - AUCUNE requête SAP).

        Args:
            quote_id: UUID du quote_draft

        Returns:
            QuoteDraft complet ou None si non trouvé
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, mail_id, client_code, client_status, status,
                   raw_email_payload, lines, created_at, updated_at
            FROM quote_draft
            WHERE id = ?
        """, (quote_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        # Désérialiser JSON
        return QuoteDraft(
            id=row["id"],
            mail_id=row["mail_id"],
            client_code=row["client_code"],
            client_status=row["client_status"],
            status=row["status"],
            raw_email_payload=json.loads(row["raw_email_payload"]),
            lines=json.loads(row["lines"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )

    def get_quote_by_mail_id(self, mail_id: str) -> Optional[QuoteDraft]:
        """
        Récupère un quote_draft par son mail_id.

        Args:
            mail_id: ID email Microsoft

        Returns:
            QuoteDraft complet ou None si non trouvé
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, mail_id, client_code, client_status, status,
                   raw_email_payload, lines, created_at, updated_at
            FROM quote_draft
            WHERE mail_id = ?
        """, (mail_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return QuoteDraft(
            id=row["id"],
            mail_id=row["mail_id"],
            client_code=row["client_code"],
            client_status=row["client_status"],
            status=row["status"],
            raw_email_payload=json.loads(row["raw_email_payload"]),
            lines=json.loads(row["lines"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )

    def update_line_sap_data(
        self,
        quote_id: str,
        line_id: str,
        sap_item_code: Optional[str],
        sap_status: str,
        sap_price: Optional[float],
        search_metadata: Dict[str, Any]
    ):
        """
        Update une ligne après retry SAP.
        Modifie UNIQUEMENT la ligne concernée dans le JSON lines.

        Args:
            quote_id: UUID du quote_draft
            line_id: UUID de la ligne à updater
            sap_item_code: Nouveau code SAP (ou None)
            sap_status: FOUND | NOT_FOUND | AMBIGUOUS
            sap_price: Nouveau prix (ou None)
            search_metadata: Nouvelles métadonnées search
                {
                    "search_type": "MANUAL" | "RETRY_FUZZY",
                    "sap_query_used": "...",
                    "search_timestamp": "...",
                    "match_score": 100
                }

        Raises:
            ValueError: Si quote_id ou line_id non trouvé
        """
        # 1. Récupérer quote_draft
        quote = self.get_quote_draft(quote_id)
        if not quote:
            raise ValueError(f"Quote {quote_id} not found")

        # 2. Trouver et update ligne
        line_found = False
        for line in quote.lines:
            if line["line_id"] == line_id:
                line["sap_item_code"] = sap_item_code
                line["sap_status"] = sap_status
                line["sap_price"] = sap_price
                line["search_metadata"] = search_metadata
                line_found = True
                break

        if not line_found:
            raise ValueError(f"Line {line_id} not found in quote {quote_id}")

        # 3. Persister changement
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        timestamp = datetime.utcnow().isoformat() + "Z"

        cursor.execute("""
            UPDATE quote_draft
            SET lines = ?, updated_at = ?
            WHERE id = ?
        """, (json.dumps(quote.lines, ensure_ascii=False), timestamp, quote_id))

        conn.commit()
        conn.close()

        logger.info(f"✅ Line {line_id} updated in quote {quote_id}: sap_status={sap_status}")

    def update_status(self, quote_id: str, new_status: str):
        """
        Update le statut global du quote_draft.

        Args:
            quote_id: UUID du quote_draft
            new_status: ANALYZED | VALIDATED | SAP_CREATED

        Raises:
            ValueError: Si quote_id non trouvé
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        timestamp = datetime.utcnow().isoformat() + "Z"

        cursor.execute("""
            UPDATE quote_draft
            SET status = ?, updated_at = ?
            WHERE id = ?
        """, (new_status, timestamp, quote_id))

        if cursor.rowcount == 0:
            conn.close()
            raise ValueError(f"Quote {quote_id} not found")

        conn.commit()
        conn.close()

        logger.info(f"✅ Quote {quote_id} status updated to {new_status}")


# Singleton instance
_quote_repository: Optional[QuoteRepository] = None


def get_quote_repository() -> QuoteRepository:
    """Factory pattern pour obtenir l'instance unique."""
    global _quote_repository
    if _quote_repository is None:
        _quote_repository = QuoteRepository()
        logger.info("QuoteRepository singleton created")
    return _quote_repository
