"""
Quote Corrections DB - NOVA-SERVER
Persistance des corrections manuelles apportées aux données extraites d'un devis.

Les corrections complètent (overlay) le résultat d'analyse sans l'écraser :
- correction client (nom, email, card_code)
- correction produit ligne N (description, quantité, référence, prix)
- correction livraison (délai, notes)

Les prix sont gérés séparément via pricing_audit_db.py (updateDecisionPrice).
Ce service couvre TOUT LE RESTE.

DB : email_analysis.db (table quote_corrections)
"""

import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


# ============================================================
# MODÈLES
# ============================================================

class QuoteCorrection:
    """Une correction manuelle sur un champ d'un devis."""
    __slots__ = ("id", "email_id", "field_type", "field_index",
                 "field_name", "original_value", "corrected_value",
                 "corrected_at", "corrected_by")

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "email_id": self.email_id,
            "field_type": self.field_type,      # "client" | "product" | "delivery" | "general"
            "field_index": self.field_index,    # Index produit (0-based) ou None
            "field_name": self.field_name,      # Ex: "quantity", "item_description", "card_name"
            "original_value": self.original_value,
            "corrected_value": self.corrected_value,
            "corrected_at": self.corrected_at,
            "corrected_by": self.corrected_by,
        }


# ============================================================
# SERVICE
# ============================================================

class QuoteCorrectionsDB:
    """
    Stockage et application des corrections manuelles sur les devis.

    Fonctionnement :
    - save_correction() : enregistre une correction (INSERT OR REPLACE)
    - get_corrections() : retourne toutes les corrections pour un email
    - apply_corrections() : applique les corrections à un analysis_result dict
      (retourne une copie corrigée, ne modifie pas l'original)
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = str(Path(__file__).parent.parent / "email_analysis.db")
        self.db_path = db_path
        self._ensure_table()

    def _ensure_table(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS quote_corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email_id TEXT NOT NULL,
                field_type TEXT NOT NULL,
                field_index INTEGER,
                field_name TEXT NOT NULL,
                original_value TEXT,
                corrected_value TEXT NOT NULL,
                corrected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                corrected_by TEXT DEFAULT 'user',
                UNIQUE(email_id, field_type, field_index, field_name)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_qc_email_id
            ON quote_corrections(email_id)
        """)
        conn.commit()
        conn.close()

    # ----------------------------------------------------------
    # Écriture
    # ----------------------------------------------------------

    def save_correction(
        self,
        email_id: str,
        field_type: str,
        field_name: str,
        corrected_value: str,
        field_index: Optional[int] = None,
        original_value: Optional[str] = None,
        corrected_by: str = "user",
    ) -> QuoteCorrection:
        """
        Enregistre une correction (écrase si même clé).

        Args:
            email_id: ID de l'email
            field_type: "client" | "product" | "delivery" | "general"
            field_name: Nom du champ corrigé (ex: "quantity", "card_name")
            corrected_value: Nouvelle valeur (string, nombres sérialisés en str)
            field_index: Index produit (0-based) pour field_type="product"
            original_value: Valeur originale (pour affichage diff)
            corrected_by: Identifiant utilisateur
        """
        now = datetime.now().isoformat()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            """
            INSERT OR REPLACE INTO quote_corrections
            (email_id, field_type, field_index, field_name,
             original_value, corrected_value, corrected_at, corrected_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (email_id, field_type, field_index, field_name,
             original_value, corrected_value, now, corrected_by)
        )
        row_id = cursor.lastrowid
        conn.commit()
        conn.close()

        logger.info(
            "Correction sauvegardée: email=%s type=%s[%s] champ=%s: '%s' → '%s'",
            email_id[:20], field_type, field_index, field_name,
            (original_value or "")[:30], corrected_value[:30]
        )

        return QuoteCorrection(
            id=row_id,
            email_id=email_id,
            field_type=field_type,
            field_index=field_index,
            field_name=field_name,
            original_value=original_value,
            corrected_value=corrected_value,
            corrected_at=now,
            corrected_by=corrected_by,
        )

    def save_corrections_batch(
        self,
        email_id: str,
        corrections: List[Dict[str, Any]],
    ) -> List[QuoteCorrection]:
        """
        Enregistre plusieurs corrections en une fois.

        Chaque item de corrections doit avoir au minimum :
        { field_type, field_name, corrected_value }
        Et optionnellement : field_index, original_value, corrected_by
        """
        results = []
        for c in corrections:
            saved = self.save_correction(
                email_id=email_id,
                field_type=c["field_type"],
                field_name=c["field_name"],
                corrected_value=str(c["corrected_value"]),
                field_index=c.get("field_index"),
                original_value=str(c["original_value"]) if c.get("original_value") is not None else None,
                corrected_by=c.get("corrected_by", "user"),
            )
            results.append(saved)
        return results

    def delete_correction(
        self,
        email_id: str,
        field_type: str,
        field_name: str,
        field_index: Optional[int] = None,
    ):
        """Supprime une correction (annule la modification)."""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            DELETE FROM quote_corrections
            WHERE email_id = ? AND field_type = ? AND field_index IS ? AND field_name = ?
            """,
            (email_id, field_type, field_index, field_name)
        )
        conn.commit()
        conn.close()

    # ----------------------------------------------------------
    # Lecture
    # ----------------------------------------------------------

    def get_corrections(self, email_id: str) -> List[QuoteCorrection]:
        """Retourne toutes les corrections pour un email."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM quote_corrections WHERE email_id = ? ORDER BY field_type, field_index, field_name",
            (email_id,)
        ).fetchall()
        conn.close()

        return [
            QuoteCorrection(
                id=row["id"],
                email_id=row["email_id"],
                field_type=row["field_type"],
                field_index=row["field_index"],
                field_name=row["field_name"],
                original_value=row["original_value"],
                corrected_value=row["corrected_value"],
                corrected_at=row["corrected_at"],
                corrected_by=row["corrected_by"],
            )
            for row in rows
        ]

    def has_corrections(self, email_id: str) -> bool:
        conn = sqlite3.connect(self.db_path)
        count = conn.execute(
            "SELECT COUNT(*) FROM quote_corrections WHERE email_id = ?", (email_id,)
        ).fetchone()[0]
        conn.close()
        return count > 0

    # ----------------------------------------------------------
    # Application
    # ----------------------------------------------------------

    def apply_corrections(
        self,
        email_id: str,
        analysis_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Applique les corrections à un analysis_result.

        Retourne une COPIE du dict avec les corrections appliquées en overlay.
        Ne modifie pas l'original.

        Mapping field_type → clé dans analysis_result :
        - "client"   → extracted_data (client_name, client_email, client_card_code, ...)
        - "product"  → product_matches[field_index] (item_name, quantity, unit_price, ...)
        - "delivery" → extracted_data (delivery_requirement, urgency, notes)
        - "general"  → analysis_result direct
        """
        corrections = self.get_corrections(email_id)
        if not corrections:
            return analysis_result

        import copy
        result = copy.deepcopy(analysis_result)

        for correction in corrections:
            try:
                value = self._deserialize_value(correction.corrected_value)

                if correction.field_type == "client":
                    ed = result.setdefault("extracted_data", {})
                    if isinstance(ed, dict):
                        ed[correction.field_name] = value

                elif correction.field_type == "product":
                    idx = correction.field_index
                    if idx is not None:
                        pm = result.get("product_matches", [])
                        if isinstance(pm, list) and 0 <= idx < len(pm):
                            pm[idx][correction.field_name] = value

                elif correction.field_type == "delivery":
                    ed = result.setdefault("extracted_data", {})
                    if isinstance(ed, dict):
                        ed[correction.field_name] = value

                elif correction.field_type == "general":
                    result[correction.field_name] = value

            except Exception as exc:
                logger.warning(
                    "Correction ignorée (erreur): email=%s field=%s/%s: %s",
                    email_id[:20], correction.field_type, correction.field_name, exc
                )

        logger.info("Corrections appliquées pour email %s (%d corrections)", email_id[:20], len(corrections))
        return result

    @staticmethod
    def _deserialize_value(value_str: str):
        """Tente de désérialiser une valeur (int, float, bool, ou str)."""
        # Booléens
        if value_str.lower() == "true":
            return True
        if value_str.lower() == "false":
            return False
        # Nombres entiers
        try:
            return int(value_str)
        except (ValueError, TypeError):
            pass
        # Nombres décimaux
        try:
            return float(value_str)
        except (ValueError, TypeError):
            pass
        # JSON (listes, dicts)
        try:
            return json.loads(value_str)
        except (json.JSONDecodeError, TypeError):
            pass
        # String par défaut
        return value_str


# ============================================================
# SINGLETON
# ============================================================

_quote_corrections_db: Optional[QuoteCorrectionsDB] = None


def get_quote_corrections_db() -> QuoteCorrectionsDB:
    """Retourne l'instance singleton du service de corrections."""
    global _quote_corrections_db
    if _quote_corrections_db is None:
        _quote_corrections_db = QuoteCorrectionsDB()
        logger.info("QuoteCorrectionsDB singleton créé")
    return _quote_corrections_db
