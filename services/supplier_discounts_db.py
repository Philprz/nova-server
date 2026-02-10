"""
services/supplier_discounts_db.py
Gestion des remises fournisseurs (discounts)
"""

import os
import sqlite3
import logging
from typing import List, Optional, Dict
from datetime import datetime, date
from pydantic import BaseModel


logger = logging.getLogger(__name__)


class SupplierDiscount(BaseModel):
    """Modèle de remise fournisseur"""
    discount_id: Optional[int] = None
    supplier_code: str
    supplier_name: Optional[str] = None
    item_code: Optional[str] = None  # None = applicable à tous les articles
    discount_type: str  # "PERCENTAGE" ou "FIXED_AMOUNT"
    discount_value: float  # Pourcentage (ex: 10.0) ou montant fixe
    min_quantity: Optional[float] = None  # Quantité minimale pour bénéficier de la remise
    min_amount: Optional[float] = None  # Montant minimum pour bénéficier de la remise
    start_date: Optional[date] = None  # Date de début de validité
    end_date: Optional[date] = None  # Date de fin de validité
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    notes: Optional[str] = None


class SupplierDiscountDB:
    """Service de gestion des remises fournisseurs"""

    def __init__(self, db_path: str = "data/supplier_tariffs.db"):
        self.db_path = db_path
        self._init_database()

    def _init_database(self):
        """Initialise les tables de remises fournisseurs"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Table des remises fournisseurs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS supplier_discounts (
                discount_id INTEGER PRIMARY KEY AUTOINCREMENT,
                supplier_code TEXT NOT NULL,
                supplier_name TEXT,
                item_code TEXT,  -- NULL = remise globale
                discount_type TEXT NOT NULL CHECK(discount_type IN ('PERCENTAGE', 'FIXED_AMOUNT')),
                discount_value REAL NOT NULL,
                min_quantity REAL,
                min_amount REAL,
                start_date TEXT,
                end_date TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Index pour performance
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_supplier_discounts_supplier
            ON supplier_discounts(supplier_code, is_active)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_supplier_discounts_item
            ON supplier_discounts(item_code, is_active)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_supplier_discounts_dates
            ON supplier_discounts(start_date, end_date, is_active)
        """)

        conn.commit()
        conn.close()

        logger.info("✓ Table supplier_discounts initialisée")

    def add_discount(self, discount: SupplierDiscount) -> int:
        """
        Ajoute une nouvelle remise fournisseur

        Returns:
            ID de la remise créée
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO supplier_discounts (
                supplier_code, supplier_name, item_code,
                discount_type, discount_value,
                min_quantity, min_amount,
                start_date, end_date,
                is_active, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            discount.supplier_code,
            discount.supplier_name,
            discount.item_code,
            discount.discount_type,
            discount.discount_value,
            discount.min_quantity,
            discount.min_amount,
            discount.start_date.isoformat() if discount.start_date else None,
            discount.end_date.isoformat() if discount.end_date else None,
            1 if discount.is_active else 0,
            discount.notes
        ))

        discount_id = cursor.lastrowid
        conn.commit()
        conn.close()

        logger.info(f"✓ Remise fournisseur ajoutée: {discount_id} pour {discount.supplier_code}")
        return discount_id

    def get_applicable_discounts(
        self,
        supplier_code: str,
        item_code: Optional[str] = None,
        quantity: Optional[float] = None,
        amount: Optional[float] = None,
        check_date: Optional[date] = None
    ) -> List[SupplierDiscount]:
        """
        Récupère les remises applicables pour un fournisseur/article

        Args:
            supplier_code: Code fournisseur
            item_code: Code article (optionnel)
            quantity: Quantité (pour vérifier min_quantity)
            amount: Montant (pour vérifier min_amount)
            check_date: Date de vérification (par défaut aujourd'hui)

        Returns:
            Liste des remises applicables
        """
        if check_date is None:
            check_date = date.today()

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Requête pour remises applicables
        query = """
            SELECT * FROM supplier_discounts
            WHERE supplier_code = ?
            AND is_active = 1
            AND (item_code = ? OR item_code IS NULL)
            AND (start_date IS NULL OR DATE(start_date) <= DATE(?))
            AND (end_date IS NULL OR DATE(end_date) >= DATE(?))
        """
        params = [supplier_code, item_code, check_date.isoformat(), check_date.isoformat()]

        if quantity is not None:
            query += " AND (min_quantity IS NULL OR min_quantity <= ?)"
            params.append(quantity)

        if amount is not None:
            query += " AND (min_amount IS NULL OR min_amount <= ?)"
            params.append(amount)

        query += " ORDER BY discount_value DESC"  # Plus grosse remise en premier

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        discounts = []
        for row in rows:
            discounts.append(SupplierDiscount(
                discount_id=row["discount_id"],
                supplier_code=row["supplier_code"],
                supplier_name=row["supplier_name"],
                item_code=row["item_code"],
                discount_type=row["discount_type"],
                discount_value=row["discount_value"],
                min_quantity=row["min_quantity"],
                min_amount=row["min_amount"],
                start_date=date.fromisoformat(row["start_date"]) if row["start_date"] else None,
                end_date=date.fromisoformat(row["end_date"]) if row["end_date"] else None,
                is_active=bool(row["is_active"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
                notes=row["notes"]
            ))

        return discounts

    def calculate_discounted_price(
        self,
        base_price: float,
        supplier_code: str,
        item_code: Optional[str] = None,
        quantity: float = 1.0
    ) -> Dict:
        """
        Calcule le prix après application des remises

        Returns:
            Dict avec:
            - original_price: Prix de base
            - discounted_price: Prix après remises
            - total_discount_amount: Montant total de remise
            - total_discount_percent: Pourcentage total de remise
            - applied_discounts: Liste des remises appliquées
        """
        amount = base_price * quantity

        # Récupérer remises applicables
        discounts = self.get_applicable_discounts(
            supplier_code=supplier_code,
            item_code=item_code,
            quantity=quantity,
            amount=amount
        )

        if not discounts:
            return {
                "original_price": base_price,
                "discounted_price": base_price,
                "total_discount_amount": 0.0,
                "total_discount_percent": 0.0,
                "applied_discounts": []
            }

        # Appliquer remises (cumulatives)
        current_price = base_price
        total_discount = 0.0
        applied_discounts = []

        for discount in discounts:
            if discount.discount_type == "PERCENTAGE":
                discount_amount = (current_price * discount.discount_value / 100)
                current_price -= discount_amount
            else:  # FIXED_AMOUNT
                discount_amount = min(discount.discount_value, current_price)
                current_price -= discount_amount

            total_discount += discount_amount

            applied_discounts.append({
                "discount_id": discount.discount_id,
                "type": discount.discount_type,
                "value": discount.discount_value,
                "amount_saved": round(discount_amount, 2)
            })

        discounted_price = round(current_price, 2)
        total_discount_percent = round((total_discount / base_price) * 100, 2) if base_price > 0 else 0

        return {
            "original_price": base_price,
            "discounted_price": discounted_price,
            "total_discount_amount": round(total_discount, 2),
            "total_discount_percent": total_discount_percent,
            "applied_discounts": applied_discounts
        }

    def update_discount(
        self,
        discount_id: int,
        updates: Dict
    ) -> bool:
        """
        Met à jour une remise existante
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Construire la requête UPDATE dynamiquement
        set_clauses = []
        params = []

        for key, value in updates.items():
            if key == "discount_id":
                continue  # Ne pas mettre à jour l'ID

            set_clauses.append(f"{key} = ?")
            params.append(value)

        if not set_clauses:
            return False

        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
        query = f"UPDATE supplier_discounts SET {', '.join(set_clauses)} WHERE discount_id = ?"
        params.append(discount_id)

        cursor.execute(query, params)
        conn.commit()
        updated = cursor.rowcount > 0
        conn.close()

        if updated:
            logger.info(f"✓ Remise {discount_id} mise à jour")

        return updated

    def deactivate_discount(self, discount_id: int) -> bool:
        """Désactive une remise"""
        return self.update_discount(discount_id, {"is_active": 0})

    def delete_discount(self, discount_id: int) -> bool:
        """Supprime définitivement une remise"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM supplier_discounts WHERE discount_id = ?", (discount_id,))
        conn.commit()
        deleted = cursor.rowcount > 0
        conn.close()

        if deleted:
            logger.info(f"✓ Remise {discount_id} supprimée")

        return deleted

    def list_all_discounts(
        self,
        supplier_code: Optional[str] = None,
        active_only: bool = True
    ) -> List[SupplierDiscount]:
        """Liste toutes les remises"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = "SELECT * FROM supplier_discounts WHERE 1=1"
        params = []

        if supplier_code:
            query += " AND supplier_code = ?"
            params.append(supplier_code)

        if active_only:
            query += " AND is_active = 1"

        query += " ORDER BY supplier_code, created_at DESC"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        discounts = []
        for row in rows:
            discounts.append(SupplierDiscount(
                discount_id=row["discount_id"],
                supplier_code=row["supplier_code"],
                supplier_name=row["supplier_name"],
                item_code=row["item_code"],
                discount_type=row["discount_type"],
                discount_value=row["discount_value"],
                min_quantity=row["min_quantity"],
                min_amount=row["min_amount"],
                start_date=date.fromisoformat(row["start_date"]) if row["start_date"] else None,
                end_date=date.fromisoformat(row["end_date"]) if row["end_date"] else None,
                is_active=bool(row["is_active"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
                notes=row["notes"]
            ))

        return discounts


# Singleton
_supplier_discounts_db = None


def get_supplier_discounts_db() -> SupplierDiscountDB:
    """Retourne l'instance singleton du service de remises"""
    global _supplier_discounts_db
    if _supplier_discounts_db is None:
        _supplier_discounts_db = SupplierDiscountDB()
        logger.info("SupplierDiscountDB initialisé")
    return _supplier_discounts_db
