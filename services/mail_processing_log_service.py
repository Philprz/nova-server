"""
Service de logging structuré pour traçabilité complète du workflow Mail-to-Biz.

Ce module enregistre chaque étape du traitement email avec métadonnées:
- WEBHOOK_RECEIVED, LLM_ANALYSIS_START, LLM_ANALYSIS_COMPLETE
- SAP_CLIENT_SEARCH_COMPLETE, SAP_PRODUCTS_SEARCH_COMPLETE
- PRICING_COMPLETE, QUOTE_DRAFT_CREATED
- RETRY_LINE_SEARCH, MANUAL_CODE_UPDATE, PROCESSING_ERROR

Chaque log inclut: step, status (SUCCESS/ERROR/PENDING), details, timestamp
"""

import sqlite3
import logging
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class MailProcessingLogService:
    """
    Service de logging structuré pour traçabilité Mail-to-Biz.

    Table: mail_processing_log
    - id: UUID
    - mail_id: ID email Microsoft
    - step: Nom de l'étape (ex: LLM_ANALYSIS_COMPLETE)
    - status: SUCCESS | ERROR | PENDING
    - details: Informations supplémentaires (optionnel)
    - timestamp: ISO datetime
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(Path(__file__).parent.parent / "email_analysis.db")
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialise la table mail_processing_log."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Table des logs de traitement
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mail_processing_log (
                id TEXT PRIMARY KEY,
                mail_id TEXT NOT NULL,
                step TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('SUCCESS','ERROR','PENDING')),
                details TEXT,
                timestamp TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        # Index pour recherche rapide par mail_id
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_log_mail_id
            ON mail_processing_log(mail_id)
        """)

        # Index pour recherche temporelle
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_log_timestamp
            ON mail_processing_log(timestamp DESC)
        """)

        conn.commit()
        conn.close()

        logger.info(f"MailProcessingLogService initialized at {self.db_path}")

    def log_step(
        self,
        mail_id: str,
        step: str,
        status: str,
        details: str = None
    ):
        """
        Enregistre une étape de traitement email.

        Args:
            mail_id: ID email Microsoft (ex: AAMk...abc123)
            step: Nom étape (ex: LLM_ANALYSIS_COMPLETE)
            status: SUCCESS | ERROR | PENDING
            details: Détails optionnels (ex: "client_status=FOUND, products=3")

        Examples:
            log_step("AAMk123", "WEBHOOK_RECEIVED", "SUCCESS")
            log_step("AAMk123", "LLM_ANALYSIS_COMPLETE", "SUCCESS", "is_quote_request=true")
            log_step("AAMk123", "PROCESSING_ERROR", "ERROR", str(exception))
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        log_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat() + "Z"

        cursor.execute("""
            INSERT INTO mail_processing_log (id, mail_id, step, status, details, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (log_id, mail_id, step, status, details, timestamp))

        conn.commit()
        conn.close()

        # Log console pour debug
        mail_id_short = mail_id[:20] + "..." if len(mail_id) > 20 else mail_id
        logger.info(f"📝 [{step}] {status} - mail_id={mail_id_short} {details or ''}")

    def get_logs_for_mail(self, mail_id: str) -> List[Dict[str, Any]]:
        """
        Récupère tous les logs d'un email (pour debug UI).

        Args:
            mail_id: ID email Microsoft

        Returns:
            Liste de logs triés par timestamp ASC
            [
                {
                    "id": "uuid",
                    "step": "LLM_ANALYSIS_COMPLETE",
                    "status": "SUCCESS",
                    "details": "is_quote_request=true",
                    "timestamp": "2026-02-13T10:30:00Z"
                },
                ...
            ]
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, step, status, details, timestamp
            FROM mail_processing_log
            WHERE mail_id = ?
            ORDER BY timestamp ASC
        """, (mail_id,))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_recent_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Récupère les logs les plus récents (tous emails confondus).

        Args:
            limit: Nombre maximum de logs à retourner

        Returns:
            Liste de logs triés par timestamp DESC
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, mail_id, step, status, details, timestamp
            FROM mail_processing_log
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_error_logs(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Récupère les logs d'erreurs récents.

        Args:
            limit: Nombre maximum de logs à retourner

        Returns:
            Liste de logs en erreur triés par timestamp DESC
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, mail_id, step, status, details, timestamp
            FROM mail_processing_log
            WHERE status = 'ERROR'
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]


# Singleton instance
_mail_processing_log_service: Optional[MailProcessingLogService] = None


def get_mail_processing_log_service() -> MailProcessingLogService:
    """Factory pattern pour obtenir l'instance unique."""
    global _mail_processing_log_service
    if _mail_processing_log_service is None:
        _mail_processing_log_service = MailProcessingLogService()
        logger.info("MailProcessingLogService singleton created")
    return _mail_processing_log_service
