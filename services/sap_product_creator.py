"""
Service de création de produits dans SAP B1.
Gère la création d'articles depuis les références externes validées.
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime
from services.sap_business_service import get_sap_business_service
from services.product_mapping_db import get_product_mapping_db
from services.sap_cache_db import get_sap_cache_db

logger = logging.getLogger(__name__)


class SAPProductCreator:
    """
    Crée des produits dans SAP B1 depuis les références externes.
    """

    def __init__(self):
        self.sap_service = get_sap_business_service()
        self.mapping_db = get_product_mapping_db()
        self.cache_db = get_sap_cache_db()

    async def create_product(
        self,
        item_code: str,
        item_name: str,
        item_group: str = "100",
        purchase_item: bool = True,
        sales_item: bool = True,
        inventory_item: bool = True,
        external_code: Optional[str] = None,
        external_description: Optional[str] = None,
        supplier_card_code: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Crée un nouveau produit dans SAP B1.

        Args:
            item_code: Code article SAP (ex: "RONDOT-TRI037")
            item_name: Nom article (ex: "LIFT ROLLER STUD SHEPPEE")
            item_group: Groupe articles (défaut: "100")
            purchase_item: Article achetable
            sales_item: Article vendable
            inventory_item: Article stockable
            external_code: Code externe/fournisseur (ex: "TRI-037")
            external_description: Description externe
            supplier_card_code: CardCode fournisseur pour mapping
            **kwargs: Paramètres additionnels SAP

        Returns:
            Dict avec success, item_code, message
        """
        try:
            # Vérifier si le code existe déjà dans SAP
            existing = await self._check_item_exists(item_code)
            if existing:
                return {
                    "success": False,
                    "error": f"Le code {item_code} existe déjà dans SAP",
                    "item_code": item_code
                }

            # Construire le payload SAP
            payload = {
                "ItemCode": item_code,
                "ItemName": item_name,
                "ItemsGroupCode": int(item_group),
                "PurchaseItem": "tYES" if purchase_item else "tNO",
                "SalesItem": "tYES" if sales_item else "tNO",
                "InventoryItem": "tYES" if inventory_item else "tNO",
            }

            # Ajouter paramètres additionnels
            for key, value in kwargs.items():
                if value is not None:
                    payload[key] = value

            logger.info(f"Création produit SAP: {item_code} - {item_name}")

            # Créer dans SAP B1
            result = await self.sap_service._call_sap(
                "/Items",
                method="POST",
                data=payload
            )

            # Mettre à jour le cache local
            await self._update_local_cache(item_code, item_name, item_group)

            # Créer/valider le mapping si code externe fourni
            if external_code and supplier_card_code:
                self.mapping_db.validate_mapping(
                    external_code=external_code,
                    supplier_card_code=supplier_card_code,
                    matched_item_code=item_code
                )
                logger.info(f"Mapping validé: {external_code} → {item_code}")

            return {
                "success": True,
                "item_code": item_code,
                "message": f"Produit {item_code} créé avec succès dans SAP",
                "sap_response": result
            }

        except Exception as e:
            logger.error(f"Erreur création produit SAP {item_code}: {e}")
            return {
                "success": False,
                "error": str(e),
                "item_code": item_code
            }

    async def _check_item_exists(self, item_code: str) -> bool:
        """Vérifie si un code article existe déjà dans SAP."""
        try:
            result = await self.sap_service._call_sap(f"/Items('{item_code}')")
            return True
        except Exception:
            return False

    async def _update_local_cache(
        self,
        item_code: str,
        item_name: str,
        item_group: str
    ):
        """Met à jour le cache local SQLite avec le nouveau produit."""
        try:
            import sqlite3
            db_path = self.cache_db.db_path
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            cursor.execute("""
                INSERT OR REPLACE INTO sap_items
                (ItemCode, ItemName, ItemGroup, last_updated)
                VALUES (?, ?, ?, ?)
            """, (item_code, item_name, item_group, datetime.now().isoformat()))

            conn.commit()
            conn.close()

            logger.info(f"Cache local mis à jour: {item_code}")

        except Exception as e:
            logger.warning(f"Erreur mise à jour cache local: {e}")

    def generate_item_code(
        self,
        external_code: str,
        prefix: str = "RONDOT"
    ) -> str:
        """
        Génère un code article SAP depuis un code externe.

        Args:
            external_code: Code externe (ex: "TRI-037")
            prefix: Préfixe (défaut: "RONDOT")

        Returns:
            Code SAP généré (ex: "RONDOT-TRI037")
        """
        # Nettoyer le code externe (enlever tirets multiples)
        clean_code = external_code.replace("-", "").upper()

        # Générer le code SAP
        item_code = f"{prefix}-{clean_code}"

        # Limiter à 20 caractères max (limite SAP)
        if len(item_code) > 20:
            item_code = item_code[:20]

        return item_code

    async def bulk_create_from_pending(
        self,
        supplier_card_code: str,
        prefix: str = "RONDOT",
        auto_generate_codes: bool = True
    ) -> Dict[str, Any]:
        """
        Crée en masse les produits PENDING pour un fournisseur.

        Args:
            supplier_card_code: CardCode du fournisseur
            prefix: Préfixe pour génération codes
            auto_generate_codes: Auto-générer les codes SAP

        Returns:
            Dict avec statistiques (created, failed, skipped)
        """
        stats = {
            "created": [],
            "failed": [],
            "skipped": []
        }

        # Récupérer les mappings PENDING pour ce fournisseur
        import sqlite3
        db_path = self.mapping_db.db_path
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM product_code_mapping
            WHERE supplier_card_code = ?
            AND status = 'PENDING'
            ORDER BY created_at
        """, (supplier_card_code,))

        pending = cursor.fetchall()
        conn.close()

        logger.info(f"Création en masse: {len(pending)} produits PENDING pour {supplier_card_code}")

        for row in pending:
            external_code = row["external_code"]
            external_desc = row["external_description"]

            # Générer code SAP
            if auto_generate_codes:
                item_code = self.generate_item_code(external_code, prefix)
            else:
                # Sauter si pas de code auto
                stats["skipped"].append({
                    "external_code": external_code,
                    "reason": "Auto-generation disabled"
                })
                continue

            # Générer nom article
            item_name = external_desc[:100] if external_desc else f"Article {external_code}"

            # Créer dans SAP
            result = await self.create_product(
                item_code=item_code,
                item_name=item_name,
                external_code=external_code,
                external_description=external_desc,
                supplier_card_code=supplier_card_code
            )

            if result["success"]:
                stats["created"].append({
                    "external_code": external_code,
                    "item_code": item_code
                })
            else:
                stats["failed"].append({
                    "external_code": external_code,
                    "error": result.get("error")
                })

        return {
            "total": len(pending),
            "created": len(stats["created"]),
            "failed": len(stats["failed"]),
            "skipped": len(stats["skipped"]),
            "details": stats
        }


# Singleton
_sap_product_creator: Optional[SAPProductCreator] = None


def get_sap_product_creator() -> SAPProductCreator:
    """Factory pattern pour obtenir l'instance unique."""
    global _sap_product_creator
    if _sap_product_creator is None:
        _sap_product_creator = SAPProductCreator()
        logger.info("SAPProductCreator singleton created")
    return _sap_product_creator
