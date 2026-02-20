"""
Service SAP Business One pour mail-to-biz
Gère les articles, prix, clients et création de devis
"""

import os
import httpx
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


# Modèles de données
class SAPItem(BaseModel):
    """Article SAP"""
    ItemCode: str
    ItemName: str
    Price: Optional[float] = None
    Currency: str = "EUR"
    UnitOfMeasure: Optional[str] = None
    InStock: Optional[float] = None


class SAPBusinessPartner(BaseModel):
    """Client SAP"""
    CardCode: str
    CardName: str
    EmailAddress: Optional[str] = None
    Phone1: Optional[str] = None


class SAPQuotationLine(BaseModel):
    """Ligne de devis SAP"""
    ItemCode: Optional[str] = None
    ItemDescription: str
    Quantity: float = 1
    UnitPrice: Optional[float] = None
    DiscountPercent: float = 0


class SAPQuotation(BaseModel):
    """Devis SAP"""
    CardCode: str
    DocDate: str
    DocDueDate: str
    Comments: Optional[str] = None
    DocumentLines: List[Dict[str, Any]]


class SAPBusinessService:
    """Service métier SAP B1 pour mail-to-biz"""

    def __init__(self):
        self.base_url = os.getenv("SAP_REST_BASE_URL")
        self.username = os.getenv("SAP_USER_RONDOT", os.getenv("SAP_USER"))
        self.company_db = os.getenv("SAP_CLIENT_RONDOT", os.getenv("SAP_CLIENT"))
        self.password = os.getenv("SAP_CLIENT_PASSWORD_RONDOT", os.getenv("SAP_CLIENT_PASSWORD"))

        self.session_id: Optional[str] = None
        self.session_timeout: Optional[datetime] = None

        logger.info(f"SAP Service initialized with DB: {self.company_db}")

    async def ensure_session(self) -> bool:
        """Assure qu'une session SAP valide existe"""
        if self.session_id and self.session_timeout and datetime.now() < self.session_timeout:
            return True

        return await self.login()

    async def login(self) -> bool:
        """Connexion à SAP Business One"""
        try:
            login_data = {
                "CompanyDB": self.company_db,
                "UserName": self.username,
                "Password": self.password
            }

            async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/Login",
                    json=login_data
                )

            if response.status_code == 200:
                result = response.json()
                self.session_id = result.get("SessionId")
                # Session valide 20 minutes
                self.session_timeout = datetime.now() + timedelta(minutes=20)
                logger.info(f"✓ SAP login successful - Session: {self.session_id[:20]}...")
                return True
            else:
                logger.error(f"✗ SAP login failed: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logger.error(f"✗ SAP login error: {e}")
            return False

    async def _call_sap(
        self,
        endpoint: str,
        method: str = "GET",
        payload: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Appel générique à l'API SAP avec gestion de session"""
        if not await self.ensure_session():
            raise Exception("Impossible de se connecter à SAP")

        headers = {
            "Cookie": f"B1SESSION={self.session_id}",
            "Content-Type": "application/json"
        }

        url = f"{self.base_url}{endpoint}"

        try:
            async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
                if method == "GET":
                    response = await client.get(url, headers=headers, params=params)
                elif method == "POST":
                    response = await client.post(url, headers=headers, json=payload)
                elif method == "PATCH":
                    response = await client.patch(url, headers=headers, json=payload)
                else:
                    raise ValueError(f"Méthode HTTP non supportée: {method}")

                response.raise_for_status()
                return response.json()

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                # Session expirée, réessayer après login
                logger.warning("Session expirée, reconnexion...")
                self.session_id = None
                if await self.login():
                    return await self._call_sap(endpoint, method, payload, params)

            elif e.response.status_code == 500:
                # Vérifier si c'est un Switch company error (code 305)
                try:
                    error_body = e.response.json()
                    if error_body.get("error", {}).get("code") == 305:
                        logger.warning("Switch company error (305), réinitialisation session et reconnexion...")
                        self.session_id = None
                        self.session_timeout = None
                        if await self.login():
                            return await self._call_sap(endpoint, method, payload, params)
                except Exception:
                    pass

            logger.error(f"Erreur SAP {e.response.status_code}: {e.response.text}")
            raise

        except Exception as e:
            logger.error(f"Erreur appel SAP: {e}")
            raise

    # ===== RECHERCHE D'ARTICLES =====

    async def search_items(self, query: str, top: int = 10) -> List[SAPItem]:
        """
        Recherche d'articles dans SAP par code ou description

        Args:
            query: Terme de recherche
            top: Nombre maximum de résultats

        Returns:
            Liste d'articles SAP
        """
        try:
            # Filtre OData pour rechercher dans ItemCode ou ItemName
            # SAP B1 supporte contains() mais pas toujours startswith()
            params = {
                "$top": top,
                "$select": "ItemCode,ItemName,QuantityOnStock"
            }

            # Ajouter le filtre seulement si query n'est pas vide
            if query and query.strip():
                filter_query = f"contains(ItemCode, '{query}') or contains(ItemName, '{query}')"
                params["$filter"] = filter_query

            result = await self._call_sap("/Items", params=params)

            items = []
            for item_data in result.get("value", []):
                items.append(SAPItem(
                    ItemCode=item_data.get("ItemCode", ""),
                    ItemName=item_data.get("ItemName", ""),
                    Price=None,  # Prix à récupérer via get_item_price
                    InStock=item_data.get("QuantityOnStock")
                ))

            logger.info(f"✓ Recherche articles '{query}': {len(items)} résultats")
            return items

        except Exception as e:
            logger.error(f"✗ Erreur recherche articles: {e}")
            return []

    async def get_item_price(
        self,
        item_code: str,
        card_code: Optional[str] = None,
        quantity: float = 1
    ) -> Optional[float]:
        """
        Récupère le prix d'un article (avec tarif client si spécifié)

        Args:
            item_code: Code de l'article
            card_code: Code du client (optionnel pour tarif spécifique)
            quantity: Quantité (pour prix dégressifs)

        Returns:
            Prix unitaire ou None
        """
        try:
            # Récupérer l'article
            item_data = await self._call_sap(f"/Items('{item_code}')")

            # Prix de base depuis les champs standards SAP
            # ItemPrices contient les prix par liste de prix
            base_price = None

            # Essayer de récupérer le prix depuis ItemPrices (liste de prix 1 par défaut)
            item_prices = item_data.get("ItemPrices", [])
            if item_prices and len(item_prices) > 0:
                base_price = item_prices[0].get("Price")

            # Fallback sur le dernier prix d'achat
            if base_price is None:
                base_price = item_data.get("LastPurchasePrice")

            logger.info(f"Prix article {item_code}: {base_price} EUR" if base_price else f"Prix article {item_code}: non defini")
            return base_price

        except Exception as e:
            logger.error(f"✗ Erreur récupération prix {item_code}: {e}")
            return None

    # ===== CRÉATION D'ARTICLES =====

    async def create_item(
        self,
        item_code: str,
        item_name: str,
        purchase_price: float,  # OBLIGATOIRE
        # Nouveaux paramètres pour métadonnées
        delivery_days: Optional[int] = None,
        transport_cost: Optional[float] = None,
        transport_days: Optional[int] = None,
        supplier_code: Optional[str] = None,
        supplier_name: Optional[str] = None,
        weight: Optional[float] = None,
        dimensions: Optional[str] = None,
        characteristics: Optional[str] = None
    ) -> Optional[str]:
        """
        Crée un nouvel article dans SAP avec prix OBLIGATOIRE et métadonnées enrichies

        Args:
            item_code: Code de l'article
            item_name: Nom/description de l'article
            purchase_price: Prix d'achat (OBLIGATOIRE)
            delivery_days: Délai de livraison fournisseur (jours)
            transport_cost: Coût transport unitaire
            transport_days: Délai transport (jours)
            supplier_code: Code fournisseur
            supplier_name: Nom fournisseur
            weight: Poids (kg)
            dimensions: Dimensions (format texte: LxlxH)
            characteristics: Caractéristiques techniques (format texte)

        Returns:
            ItemCode de l'article créé ou None en cas d'erreur
        """
        if not purchase_price or purchase_price <= 0:
            logger.error(f"Prix obligatoire manquant pour l'article {item_code}")
            return None

        try:
            item_data = {
                "ItemCode": item_code,
                "ItemName": item_name[:100],  # Limiter à 100 caractères
                "ItemsGroupCode": 100,  # Groupe par défaut
                "ItemType": "itItems",
                "PurchaseItem": "tYES",
                "SalesItem": "tYES",
                "InventoryItem": "tNO",  # Pas de gestion stock pour articles à la demande
                "ItemPrices": [
                    {
                        "PriceList": 1,  # Liste de prix par défaut
                        "Price": purchase_price
                    }
                ],

                # Métadonnées enrichies (champs utilisateur SAP - à adapter selon config)
                "U_DELAI_LIVRAISON": delivery_days if delivery_days else None,
                "U_COUT_TRANSPORT": transport_cost if transport_cost else None,
                "U_DELAI_TRANSPORT": transport_days if transport_days else None,
                "U_CODE_FOURNISSEUR": supplier_code or "",
                "U_NOM_FOURNISSEUR": supplier_name or "",
                "U_POIDS": weight if weight else None,
                "U_DIMENSIONS": dimensions or "",
                "U_CARACTERISTIQUES": characteristics or "",

                # Champs standards SAP
                "DefaultWarehouse": "01",  # Entrepôt par défaut
                "PurchaseUnit": "PCE",  # Unité d'achat
                "SalesUnit": "PCE"  # Unité de vente
            }

            # Nettoyer les champs None pour éviter erreurs SAP
            item_data = {k: v for k, v in item_data.items() if v is not None}

            # Remettre les champs obligatoires
            item_data.update({
                "ItemCode": item_code,
                "ItemName": item_name[:100],
                "ItemsGroupCode": 100,
                "ItemType": "itItems",
                "PurchaseItem": "tYES",
                "SalesItem": "tYES",
                "InventoryItem": "tNO",
                "ItemPrices": [{"PriceList": 1, "Price": purchase_price}]
            })

            await self._call_sap("/Items", method="POST", payload=item_data)

            logger.info(f"✓ Article créé dans SAP: {item_code} - Prix: {purchase_price} EUR")
            if delivery_days:
                logger.info(f"  Délai livraison: {delivery_days} jours")
            if supplier_name:
                logger.info(f"  Fournisseur: {supplier_name}")

            return item_code

        except Exception as e:
            # Si l'article existe déjà, ce n'est pas une erreur
            if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                logger.info(f"Article {item_code} existe déjà dans SAP")
                return item_code

            logger.error(f"Erreur création article {item_code}: {e}")
            return None

    async def create_item_simple(
        self,
        item_code: str,
        item_name: str,
        item_group_code: Optional[int] = None,
        default_price: Optional[float] = None,
        purchase_item: bool = True,
        sales_item: bool = True,
        inventory_item: bool = True,
        manufacturer: Optional[str] = None,
        bar_code: Optional[str] = None,
        remarks: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Crée un article dans SAP avec une interface simplifiée pour le frontend

        Args:
            item_code: Code de l'article (obligatoire)
            item_name: Nom de l'article (obligatoire)
            item_group_code: Groupe d'articles (catégorie)
            default_price: Prix par défaut
            purchase_item: Article achetable
            sales_item: Article vendable
            inventory_item: Article de stock
            manufacturer: Fabricant
            bar_code: Code-barres
            remarks: Remarques

        Returns:
            Dict avec ItemCode et ItemName créés

        Raises:
            HTTPException si la création échoue
        """
        try:
            # Construire le payload SAP
            item_data = {
                "ItemCode": item_code,
                "ItemName": item_name[:100],  # Limite SAP
                "ItemsGroupCode": item_group_code or 100,  # Groupe par défaut
                "ItemType": "itItems",
                "PurchaseItem": "tYES" if purchase_item else "tNO",
                "SalesItem": "tYES" if sales_item else "tNO",
                "InventoryItem": "tYES" if inventory_item else "tNO",
                "Manufacturer": manufacturer if manufacturer else "",
                "BarCode": bar_code if bar_code else "",
                "User_Text": remarks if remarks else "",
            }

            # Ajouter le prix si fourni
            if default_price and default_price > 0:
                item_data["ItemPrices"] = [
                    {
                        "PriceList": 1,  # Liste de prix par défaut
                        "Price": default_price
                    }
                ]

            # Appeler SAP pour créer l'article
            await self._call_sap("/Items", method="POST", payload=item_data)

            logger.info(f"✓ Article créé dans SAP: {item_code} - {item_name}")
            if default_price:
                logger.info(f"  Prix: {default_price} EUR")

            return {
                "ItemCode": item_code,
                "ItemName": item_name
            }

        except Exception as e:
            error_msg = str(e)

            # Si l'article existe déjà
            if "already exists" in error_msg.lower() or "duplicate" in error_msg.lower():
                logger.warning(f"Article {item_code} existe déjà dans SAP")
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=409,
                    detail=f"L'article {item_code} existe déjà dans SAP"
                )

            # Autre erreur
            logger.error(f"❌ Erreur création article {item_code}: {error_msg}")
            from fastapi import HTTPException
            raise HTTPException(
                status_code=500,
                detail=f"Erreur création article: {error_msg}"
            )

    # ===== GESTION DES BUSINESS PARTNERS =====

    async def search_business_partner(
        self,
        name: Optional[str] = None,
        email: Optional[str] = None
    ) -> Optional[SAPBusinessPartner]:
        """
        Recherche un Business Partner (client) dans SAP

        Args:
            name: Nom du client
            email: Email du client

        Returns:
            Business Partner ou None si non trouvé
        """
        try:
            filters = []

            if name:
                filters.append(f"contains(CardName, '{name}')")

            if email:
                filters.append(f"EmailAddress eq '{email}'")

            if not filters:
                return None

            filter_query = " and ".join(filters)

            params = {
                "$filter": filter_query,
                "$top": 1,
                "$select": "CardCode,CardName,EmailAddress,Phone1"
            }

            result = await self._call_sap("/BusinessPartners", params=params)

            partners = result.get("value", [])
            if partners:
                bp_data = partners[0]
                logger.info(f"✓ Client trouvé: {bp_data.get('CardName')}")
                return SAPBusinessPartner(
                    CardCode=bp_data.get("CardCode"),
                    CardName=bp_data.get("CardName"),
                    EmailAddress=bp_data.get("EmailAddress"),
                    Phone1=bp_data.get("Phone1")
                )

            logger.info(f"Client non trouvé pour: {name or email}")
            return None

        except Exception as e:
            logger.error(f"✗ Erreur recherche client: {e}")
            return None

    async def create_business_partner(
        self,
        card_name: str,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        # Nouveaux paramètres pour enrichissement
        siret: Optional[str] = None,
        tva_intra: Optional[str] = None,
        address: Optional[str] = None,
        city: Optional[str] = None,
        zip_code: Optional[str] = None,
        country: Optional[str] = None,
        legal_form: Optional[str] = None,
        capital: Optional[float] = None
    ) -> Optional[str]:
        """
        Crée un nouveau Business Partner dans SAP avec données enrichies

        Args:
            card_name: Nom du client
            email: Email du client
            phone: Téléphone
            siret: Numéro SIRET
            tva_intra: Numéro TVA intracommunautaire
            address: Adresse complète
            city: Ville
            zip_code: Code postal
            country: Pays (code ISO)
            legal_form: Forme juridique
            capital: Capital social

        Returns:
            CardCode du client créé ou None en cas d'erreur
        """
        try:
            # Générer un CardCode (ex: AUTO_001, AUTO_002...)
            # En production, utiliser une logique de génération appropriée
            card_code = f"AUTO_{datetime.now().strftime('%Y%m%d%H%M%S')}"

            bp_data = {
                "CardCode": card_code,
                "CardName": card_name,
                "CardType": "cCustomer",
                "EmailAddress": email,
                "Phone1": phone,
                "GroupCode": 100,  # Groupe par défaut

                # Adresse de facturation
                "BillToStreet": address or "",
                "BillToCity": city or "",
                "BillToZipCode": zip_code or "",
                "BillToCountry": country or "FR",

                # Adresse de livraison (même que facturation par défaut)
                "ShipToStreet": address or "",
                "ShipToCity": city or "",
                "ShipToZipCode": zip_code or "",
                "ShipToCountry": country or "FR",

                # Informations fiscales
                "FederalTaxID": siret or "",  # SIRET
                "VatIDNum": tva_intra or "",  # TVA intracommunautaire

                # Informations complémentaires (champs utilisateur si disponibles)
                "U_FORME_JURIDIQUE": legal_form or "",
                "U_CAPITAL_SOCIAL": capital or 0
            }

            # Nettoyer les champs vides pour éviter les erreurs SAP
            bp_data = {k: v for k, v in bp_data.items() if v not in [None, "", 0]}

            # Remettre les champs obligatoires même s'ils sont vides
            bp_data.update({
                "CardCode": card_code,
                "CardName": card_name,
                "CardType": "cCustomer",
                "GroupCode": 100
            })

            await self._call_sap("/BusinessPartners", method="POST", payload=bp_data)

            logger.info(f"✓ Client créé: {card_name} ({card_code})")
            if tva_intra:
                logger.info(f"  TVA Intra: {tva_intra}")
            if siret:
                logger.info(f"  SIRET: {siret}")

            return card_code

        except Exception as e:
            logger.error(f"✗ Erreur création client: {e}")
            return None

    # ===== CRÉATION DE DEVIS =====

    async def create_quotation(
        self,
        card_code: str,
        lines: List[Dict[str, Any]],
        comments: Optional[str] = None,
        reference: Optional[str] = None
    ) -> Optional[int]:
        """
        Crée un devis (Sales Quotation) dans SAP

        Args:
            card_code: Code du client
            lines: Liste des lignes du devis
            comments: Commentaires
            reference: Référence externe (ex: ID email)

        Returns:
            DocEntry du devis créé ou None en cas d'erreur
        """
        try:
            doc_date = datetime.now().strftime("%Y-%m-%d")
            doc_due_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

            quotation_data = {
                "CardCode": card_code,
                "DocDate": doc_date,
                "DocDueDate": doc_due_date,
                "Comments": comments or "",
                "NumAtCard": reference or "",
                "DocumentLines": lines
            }

            result = await self._call_sap("/Quotations", method="POST", payload=quotation_data)

            doc_entry = result.get("DocEntry")
            logger.info(f"✓ Devis créé: DocEntry {doc_entry}")
            return doc_entry

        except Exception as e:
            logger.error(f"✗ Erreur création devis: {e}")
            return None

    async def logout(self) -> bool:
        """Déconnexion de SAP"""
        if not self.session_id:
            return True

        try:
            headers = {
                "Cookie": f"B1SESSION={self.session_id}",
                "Content-Type": "application/json"
            }

            async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
                await client.post(f"{self.base_url}/Logout", headers=headers)

            self.session_id = None
            self.session_timeout = None
            logger.info("✓ SAP logout successful")
            return True

        except Exception as e:
            logger.error(f"✗ Erreur déconnexion SAP: {e}")
            return False


# Instance singleton
_sap_business_service: Optional[SAPBusinessService] = None


def get_sap_business_service() -> SAPBusinessService:
    """Factory pour obtenir l'instance du service SAP"""
    global _sap_business_service
    if _sap_business_service is None:
        _sap_business_service = SAPBusinessService()
    return _sap_business_service
