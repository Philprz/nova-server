"""
Base de données pour l'apprentissage automatique des correspondances produits.
Stocke les mappings entre références externes (fournisseurs) et codes SAP RONDOT.
"""

import sqlite3
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class ProductMappingDB:
    """
    Gère les correspondances entre codes produits externes (fournisseurs)
    et codes produits SAP RONDOT.
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(Path(__file__).parent.parent / "supplier_tariffs.db")
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialise la table product_code_mapping."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS product_code_mapping (
                external_code TEXT NOT NULL,
                external_description TEXT,
                supplier_card_code TEXT NOT NULL,
                matched_item_code TEXT,
                match_method TEXT,
                confidence_score REAL,
                last_used TIMESTAMP,
                use_count INTEGER DEFAULT 1,
                status TEXT DEFAULT 'PENDING',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (external_code, supplier_card_code)
            )
        """)

        # Index pour recherche rapide
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_external_code
            ON product_code_mapping(external_code)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_supplier_code
            ON product_code_mapping(supplier_card_code)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_status
            ON product_code_mapping(status)
        """)

        conn.commit()
        conn.close()

        logger.info(f"ProductMappingDB initialized at {self.db_path}")

    def get_mapping(
        self,
        external_code: str,
        supplier_card_code: str
    ) -> Optional[Dict[str, Any]]:
        """
        Récupère un mapping existant pour un code externe + fournisseur.

        Returns:
            Dict avec matched_item_code, confidence_score, etc. ou None
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM product_code_mapping
            WHERE external_code = ? AND supplier_card_code = ?
            AND status = 'VALIDATED'
        """, (external_code, supplier_card_code))

        row = cursor.fetchone()
        conn.close()

        if row:
            # Mettre à jour use_count et last_used
            self._increment_usage(external_code, supplier_card_code)
            return dict(row)

        return None

    def save_mapping(
        self,
        external_code: str,
        external_description: str,
        supplier_card_code: str,
        matched_item_code: Optional[str] = None,
        match_method: str = "PENDING",
        confidence_score: float = 0.0,
        status: str = "PENDING"
    ):
        """
        Enregistre ou met à jour un mapping produit.

        Args:
            external_code: Code fournisseur (ex: "HST-117-03")
            external_description: Description (ex: "SIZE 3 PUSHER BLADE")
            supplier_card_code: CardCode du fournisseur (ex: "C0249")
            matched_item_code: Code SAP RONDOT trouvé (optionnel)
            match_method: "EXACT", "FUZZY_NAME", "MANUAL", "PENDING"
            confidence_score: Score de confiance 0-100
            status: "PENDING", "VALIDATED", "REJECTED"
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO product_code_mapping
            (external_code, external_description, supplier_card_code,
             matched_item_code, match_method, confidence_score,
             last_used, use_count, status)
            VALUES (?, ?, ?, ?, ?, ?, ?,
                    COALESCE((SELECT use_count FROM product_code_mapping
                              WHERE external_code = ? AND supplier_card_code = ?), 1),
                    ?)
        """, (
            external_code,
            external_description,
            supplier_card_code,
            matched_item_code,
            match_method,
            confidence_score,
            datetime.now().isoformat(),
            external_code,
            supplier_card_code,
            status
        ))

        conn.commit()
        conn.close()

        logger.info(f"Mapping saved: {external_code} → {matched_item_code or 'PENDING'} "
                    f"({match_method}, score={confidence_score:.0f})")

    def _increment_usage(self, external_code: str, supplier_card_code: str):
        """Incrémente le compteur d'utilisation d'un mapping."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE product_code_mapping
            SET use_count = use_count + 1,
                last_used = ?
            WHERE external_code = ? AND supplier_card_code = ?
        """, (datetime.now().isoformat(), external_code, supplier_card_code))

        conn.commit()
        conn.close()

    def get_pending_mappings(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Récupère les mappings en attente de validation manuelle.

        Returns:
            Liste de dicts avec external_code, description, supplier, etc.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM product_code_mapping
            WHERE status = 'PENDING'
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def validate_mapping(
        self,
        external_code: str,
        supplier_card_code: str,
        matched_item_code: str
    ):
        """
        Valide manuellement un mapping en attente.

        Args:
            external_code: Code externe
            supplier_card_code: Fournisseur
            matched_item_code: Code SAP RONDOT validé manuellement
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE product_code_mapping
            SET matched_item_code = ?,
                match_method = 'MANUAL',
                confidence_score = 100.0,
                status = 'VALIDATED',
                last_used = ?
            WHERE external_code = ? AND supplier_card_code = ?
        """, (matched_item_code, datetime.now().isoformat(),
              external_code, supplier_card_code))

        conn.commit()
        conn.close()

        logger.info(f"Mapping validated: {external_code} → {matched_item_code}")

    def get_statistics(self) -> Dict[str, int]:
        """Retourne des statistiques sur les mappings."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'VALIDATED' THEN 1 ELSE 0 END) as validated,
                SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN match_method = 'EXACT' THEN 1 ELSE 0 END) as exact_matches,
                SUM(CASE WHEN match_method = 'FUZZY_NAME' THEN 1 ELSE 0 END) as fuzzy_matches,
                SUM(CASE WHEN match_method = 'MANUAL' THEN 1 ELSE 0 END) as manual_matches
            FROM product_code_mapping
        """)

        row = cursor.fetchone()
        conn.close()

        return {
            "total": row[0] or 0,
            "validated": row[1] or 0,
            "pending": row[2] or 0,
            "exact_matches": row[3] or 0,
            "fuzzy_matches": row[4] or 0,
            "manual_matches": row[5] or 0
        }


# Singleton
_product_mapping_db: Optional[ProductMappingDB] = None


def get_product_mapping_db() -> ProductMappingDB:
    """Factory pattern pour obtenir l'instance unique."""
    global _product_mapping_db
    if _product_mapping_db is None:
        _product_mapping_db = ProductMappingDB()
        logger.info("ProductMappingDB singleton created")
    return _product_mapping_db
