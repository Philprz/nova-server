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


# Singleton
_email_analysis_db: Optional[EmailAnalysisDB] = None


def get_email_analysis_db() -> EmailAnalysisDB:
    """Factory pattern pour obtenir l'instance unique."""
    global _email_analysis_db
    if _email_analysis_db is None:
        _email_analysis_db = EmailAnalysisDB()
        logger.info("EmailAnalysisDB singleton created")
    return _email_analysis_db
