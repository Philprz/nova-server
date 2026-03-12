"""
Base de données pour persister les résultats d'analyse email
Évite de relancer l'analyse à chaque consultation
"""

import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class EmailAnalysisDB:
    """
    Stockage persistant des résultats d'analyse email avec pricing.
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(Path(__file__).parent.parent / "email_analysis.db")
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialise la table email_analysis."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS email_analysis (
                email_id TEXT PRIMARY KEY,
                subject TEXT,
                from_address TEXT,
                analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                analysis_result TEXT NOT NULL,
                has_pricing BOOLEAN DEFAULT 0,
                is_quote_request BOOLEAN DEFAULT 0,
                client_card_code TEXT,
                product_count INTEGER DEFAULT 0
            )
        """)

        # Index pour recherche rapide
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_analyzed_at
            ON email_analysis(analyzed_at DESC)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_is_quote
            ON email_analysis(is_quote_request)
        """)

        # Table pour les demandes manuelles
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS manual_requests (
                email_id TEXT PRIMARY KEY,
                subject TEXT NOT NULL,
                from_name TEXT NOT NULL,
                body_preview TEXT,
                client_card_code TEXT,
                client_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()

        logger.info(f"EmailAnalysisDB initialized at {self.db_path}")

    def save_analysis(
        self,
        email_id: str,
        subject: str,
        from_address: str,
        analysis_result: Dict[str, Any]
    ):
        """
        Sauvegarde le résultat d'analyse complet.

        Args:
            email_id: ID unique de l'email
            subject: Sujet de l'email
            from_address: Adresse expéditeur
            analysis_result: Résultat complet de l'analyse (dict)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Extraire métadonnées
        is_quote = analysis_result.get('is_quote_request', False)
        product_matches = analysis_result.get('product_matches', [])
        has_pricing = any(p.get('unit_price') is not None for p in product_matches)

        extracted_data = analysis_result.get('extracted_data', {})
        client_card_code = extracted_data.get('client_card_code') if extracted_data else None

        # Sérialiser en JSON
        analysis_json = json.dumps(analysis_result, ensure_ascii=False)

        cursor.execute("""
            INSERT OR REPLACE INTO email_analysis (
                email_id, subject, from_address, analyzed_at,
                analysis_result, has_pricing, is_quote_request,
                client_card_code, product_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            email_id,
            subject,
            from_address,
            datetime.now().isoformat(),
            analysis_json,
            has_pricing,
            is_quote,
            client_card_code,
            len(product_matches)
        ))

        conn.commit()
        conn.close()

        logger.info(f"Analysis saved for email {email_id} (pricing: {has_pricing})")

    def get_analysis(self, email_id: str) -> Optional[Dict[str, Any]]:
        """
        Récupère le résultat d'analyse depuis la base.

        Args:
            email_id: ID unique de l'email

        Returns:
            Dict avec le résultat d'analyse ou None si non trouvé
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT analysis_result, analyzed_at
            FROM email_analysis
            WHERE email_id = ?
        """, (email_id,))

        row = cursor.fetchone()
        conn.close()

        if row:
            analysis = json.loads(row['analysis_result'])
            logger.info(f"Analysis retrieved from DB for email {email_id}")
            return analysis

        return None

    def delete_analysis(self, email_id: str):
        """Supprime une analyse (utile pour forcer une réanalyse)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM email_analysis WHERE email_id = ?", (email_id,))

        conn.commit()
        conn.close()

        logger.info(f"Analysis deleted for email {email_id}")

    def update_analysis_result(self, email_id: str, analysis_result: Dict[str, Any]):
        """
        Met à jour uniquement le analysis_result sans toucher subject/from_address.
        Utilisé après les mutations (recalcul pricing, exclusions, corrections de code).
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        product_matches = analysis_result.get('product_matches', [])
        has_pricing = any(p.get('unit_price') is not None for p in product_matches)
        extracted_data = analysis_result.get('extracted_data', {})
        client_card_code = extracted_data.get('client_card_code') if extracted_data else None

        cursor.execute("""
            UPDATE email_analysis
            SET analysis_result = ?, has_pricing = ?, client_card_code = ?,
                product_count = ?, analyzed_at = ?
            WHERE email_id = ?
        """, (
            json.dumps(analysis_result, ensure_ascii=False),
            has_pricing,
            client_card_code,
            len(product_matches),
            datetime.now().isoformat(),
            email_id,
        ))

        conn.commit()
        conn.close()
        logger.info(f"Analysis result updated for email {email_id} (pricing: {has_pricing})")

    # ----------------------------------------------------------
    # Draft state — state UI spécifique (quantités, articles ignorés, client sélectionné)
    # ----------------------------------------------------------

    def _init_draft_table(self):
        """Crée la table quote_draft_state si elle n'existe pas."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS quote_draft_state (
                email_id            TEXT PRIMARY KEY,
                quantity_overrides  TEXT,
                ignored_line_nums   TEXT,
                selected_client_code TEXT,
                selected_client_name TEXT,
                transport_price_override REAL,
                updated_at          TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()

    def save_draft_state(
        self,
        email_id: str,
        quantity_overrides: Dict[str, int],
        ignored_line_nums: list,
        selected_client_code: Optional[str],
        selected_client_name: Optional[str],
        transport_price_override: Optional[float] = None,
    ):
        """Sauvegarde l'état UI d'un devis en cours d'édition."""
        self._init_draft_table()
        # Migration silencieuse : ajouter la colonne si absente
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("ALTER TABLE quote_draft_state ADD COLUMN transport_price_override REAL")
            conn.commit()
            conn.close()
        except Exception:
            pass
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO quote_draft_state
            (email_id, quantity_overrides, ignored_line_nums,
             selected_client_code, selected_client_name, transport_price_override, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            email_id,
            json.dumps(quantity_overrides),
            json.dumps(ignored_line_nums),
            selected_client_code,
            selected_client_name,
            transport_price_override,
            datetime.now().isoformat(),
        ))
        conn.commit()
        conn.close()
        logger.debug(f"Draft state saved for email {email_id}")

    def get_draft_state(self, email_id: str) -> Optional[Dict[str, Any]]:
        """Charge l'état UI sauvegardé pour un devis."""
        self._init_draft_table()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM quote_draft_state WHERE email_id = ?", (email_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "quantity_overrides": json.loads(row["quantity_overrides"] or "{}"),
            "ignored_line_nums": json.loads(row["ignored_line_nums"] or "[]"),
            "selected_client_code": row["selected_client_code"],
            "selected_client_name": row["selected_client_name"],
            "transport_price_override": row["transport_price_override"],
            "updated_at": row["updated_at"],
        }

    def get_statistics(self) -> Dict[str, int]:
        """Retourne des statistiques sur les analyses."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN is_quote_request = 1 THEN 1 ELSE 0 END) as quotes,
                SUM(CASE WHEN has_pricing = 1 THEN 1 ELSE 0 END) as with_pricing,
                SUM(product_count) as total_products
            FROM email_analysis
        """)

        row = cursor.fetchone()
        conn.close()

        return {
            "total_analyzed": row[0] or 0,
            "quote_requests": row[1] or 0,
            "with_pricing": row[2] or 0,
            "total_products": row[3] or 0
        }


    # ----------------------------------------------------------
    # Manual requests — demandes saisies manuellement (hors email)
    # ----------------------------------------------------------

    def save_manual_request(
        self,
        email_id: str,
        subject: str,
        from_name: str,
        body_preview: str,
        client_card_code: str,
        client_name: str,
    ):
        """Enregistre les métadonnées d'une demande manuelle."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO manual_requests
            (email_id, subject, from_name, body_preview, client_card_code, client_name, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (email_id, subject, from_name, body_preview, client_card_code, client_name,
              datetime.now().isoformat()))
        conn.commit()
        conn.close()
        logger.info(f"Manual request saved: {email_id}")

    def list_manual_requests(self) -> list:
        """Retourne toutes les demandes manuelles triées par date décroissante."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT email_id, subject, from_name, body_preview, client_card_code, client_name, created_at
            FROM manual_requests
            ORDER BY created_at DESC
        """)
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ----------------------------------------------------------
    # Email status — archive, étoile, label
    # ----------------------------------------------------------

    def _init_status_table(self):
        """Crée la table email_status si elle n'existe pas."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS email_status (
                email_id TEXT PRIMARY KEY,
                archived BOOLEAN DEFAULT 0,
                starred  BOOLEAN DEFAULT 0,
                label    TEXT,
                updated_at TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()

    def set_email_status(
        self,
        email_id: str,
        archived: Optional[bool] = None,
        starred: Optional[bool] = None,
        label: Optional[str] = None,
    ):
        """Met à jour le statut d'un email (archive, étoile, label). Seuls les champs fournis sont modifiés."""
        self._init_status_table()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT archived, starred, label FROM email_status WHERE email_id = ?", (email_id,))
        row = cursor.fetchone()

        new_archived = archived if archived is not None else (bool(row["archived"]) if row else False)
        new_starred  = starred  if starred  is not None else (bool(row["starred"])  if row else False)
        new_label    = label    if label    is not None else (row["label"]           if row else None)

        cursor.execute("""
            INSERT OR REPLACE INTO email_status (email_id, archived, starred, label, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (email_id, new_archived, new_starred, new_label, datetime.now().isoformat()))

        conn.commit()
        conn.close()
        logger.info(f"Status updated for email {email_id}: archived={new_archived}, starred={new_starred}")

    def get_status_map(self) -> Dict[str, Any]:
        """Retourne tous les statuts connus sous forme {email_id: {archived, starred, label}}."""
        self._init_status_table()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT email_id, archived, starred, label FROM email_status")
        rows = cursor.fetchall()
        conn.close()
        return {
            r["email_id"]: {
                "archived": bool(r["archived"]),
                "starred":  bool(r["starred"]),
                "label":    r["label"],
            }
            for r in rows
        }


# Singleton
_email_analysis_db: Optional[EmailAnalysisDB] = None


def get_email_analysis_db() -> EmailAnalysisDB:
    """Factory pattern pour obtenir l'instance unique."""
    global _email_analysis_db
    if _email_analysis_db is None:
        _email_analysis_db = EmailAnalysisDB()
        logger.info("EmailAnalysisDB singleton created")
    return _email_analysis_db
