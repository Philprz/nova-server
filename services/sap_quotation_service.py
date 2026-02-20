"""
SAP Quotation Service - NOVA-SERVER
Création de devis (Sales Quotation) dans SAP Business One via Service Layer.

Responsabilités :
- Construire le payload JSON SAP B1 depuis QuotationPayload
- Gérer l'authentification (session B1SESSION, renouvellement automatique sur 401)
- Créer le devis via POST /Quotations
- Retourner résultat structuré avec métadonnées audit

Pattern : indépendant, réutilise les variables d'env SAP_RONDOT existantes.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


# ============================================================
# MODÈLES PYDANTIC
# ============================================================


class QuotationLine(BaseModel):
    """
    Ligne de devis SAP B1.

    ItemCode est optionnel : si le produit n'est pas encore dans SAP,
    on envoie la ligne sans ItemCode (SAP créera une ligne texte libre).
    """
    ItemCode: Optional[str] = Field(None, description="Code article SAP (ex: 'C315-6305RS')")
    ItemDescription: str = Field(..., description="Description article (obligatoire)")
    Quantity: float = Field(default=1.0, gt=0, description="Quantité commandée")
    UnitPrice: Optional[float] = Field(None, ge=0, description="Prix unitaire HT (€)")
    DiscountPercent: float = Field(default=0.0, ge=0, le=100, description="Remise en %")
    TaxCode: Optional[str] = Field(None, description="Code TVA SAP (ex: 'S1' = 20%)")
    WarehouseCode: Optional[str] = Field(None, description="Code entrepôt (ex: '01')")
    FreeText: Optional[str] = Field(None, description="Note libre sur la ligne")


class QuotationPayload(BaseModel):
    """
    Payload complet pour créer un devis SAP B1.

    Champs SAP + métadonnées NOVA (email_id, nova_source) non transmises à SAP
    mais conservées pour la traçabilité dans les logs et la réponse.
    """
    # Champs SAP obligatoires
    CardCode: str = Field(..., description="Code client SAP (ex: 'C00042')")
    DocumentLines: List[QuotationLine] = Field(..., min_length=1, description="Lignes du devis")

    # Champs SAP optionnels (générés automatiquement si absent)
    DocDate: Optional[str] = Field(None, description="Date du devis (YYYY-MM-DD)")
    DocDueDate: Optional[str] = Field(None, description="Date d'échéance (YYYY-MM-DD)")
    ValidUntil: Optional[str] = Field(None, description="Valable jusqu'au (YYYY-MM-DD)")
    Comments: Optional[str] = Field(None, description="Commentaires généraux du devis")
    SalesPersonCode: Optional[int] = Field(None, description="Code vendeur SAP")
    NumAtCard: Optional[str] = Field(None, description="Référence client (ex: objet email)")
    PaymentGroupCode: Optional[int] = Field(None, description="Conditions de paiement SAP")

    # Métadonnées NOVA (non envoyées à SAP)
    email_id: Optional[str] = Field(None, description="ID email source (Microsoft Graph)")
    email_subject: Optional[str] = Field(None, description="Objet email source")
    nova_source: str = Field(default="NOVA_MAIL_TO_BIZ", description="Source NOVA")


class QuotationResult(BaseModel):
    """Résultat de la création d'un devis SAP."""
    success: bool
    doc_entry: Optional[int] = None       # DocEntry SAP (identifiant interne)
    doc_num: Optional[int] = None         # DocNum SAP (numéro visible)
    doc_total: Optional[float] = None     # Total HT
    doc_date: Optional[str] = None        # Date devis
    card_code: Optional[str] = None       # Code client
    card_name: Optional[str] = None       # Nom client (retourné par SAP)
    message: str = ""
    error_code: Optional[str] = None      # Code erreur SAP si échec
    sap_payload: Optional[Dict] = None    # Payload envoyé (pour debug/audit)


# ============================================================
# SERVICE
# ============================================================


class SAPQuotationService:
    """
    Service de création de devis SAP Business One.

    Authentification : cookie B1SESSION via POST /Login.
    Robustesse : retry automatique sur 401, timeout 10s, logs structurés.
    """

    def __init__(self):
        self.base_url = os.getenv("SAP_REST_BASE_URL")
        self.username = os.getenv("SAP_USER_RONDOT", os.getenv("SAP_USER"))
        self.company_db = os.getenv("SAP_CLIENT_RONDOT", os.getenv("SAP_CLIENT"))
        self.password = os.getenv("SAP_CLIENT_PASSWORD_RONDOT", os.getenv("SAP_CLIENT_PASSWORD"))

        self.session_id: Optional[str] = None
        self.session_timeout: Optional[datetime] = None

        if not self.base_url:
            logger.warning("SAP_REST_BASE_URL non configuré")

    # ----------------------------------------------------------
    # Gestion session
    # ----------------------------------------------------------

    async def ensure_session(self) -> bool:
        """Vérifie la session active ou en obtient une nouvelle."""
        if self.session_id and self.session_timeout and datetime.now() < self.session_timeout:
            return True
        return await self.login()

    async def login(self) -> bool:
        """Connexion SAP B1 via Service Layer - POST /Login."""
        if not self.base_url:
            logger.error("SAP_REST_BASE_URL non défini")
            return False

        try:
            login_data = {
                "CompanyDB": self.company_db,
                "UserName": self.username,
                "Password": self.password,
            }

            async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
                response = await client.post(
                    f"{self.base_url}/Login",
                    json=login_data,
                    headers={"Content-Type": "application/json", "User-Agent": "NOVA-SERVER/1.0"},
                )

            if response.status_code == 200:
                data = response.json()
                self.session_id = data.get("SessionId")
                self.session_timeout = datetime.now() + timedelta(minutes=20)
                logger.info("✅ SAP login réussi (CompanyDB=%s)", self.company_db)
                return True

            logger.error("❌ SAP login échoué: HTTP %s - %s", response.status_code, response.text[:200])
            return False

        except httpx.TimeoutException:
            logger.error("❌ SAP login timeout (10s)")
            return False
        except Exception as exc:
            logger.error("❌ SAP login erreur inattendue: %s", exc)
            return False

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Cookie": f"B1SESSION={self.session_id}",
            "Content-Type": "application/json",
        }

    # ----------------------------------------------------------
    # Construction payload SAP
    # ----------------------------------------------------------

    def _build_sap_payload(self, payload: QuotationPayload) -> Dict[str, Any]:
        """
        Convertit QuotationPayload en dict JSON attendu par SAP B1 /Quotations.

        Règles :
        - DocDate et DocDueDate par défaut = aujourd'hui
        - DocumentLines : ItemCode inclus seulement s'il est non nul
        - Champs NOVA (email_id, nova_source) exclus du payload SAP
        """
        today = datetime.now().strftime("%Y-%m-%d")

        sap_doc: Dict[str, Any] = {
            "CardCode": payload.CardCode,
            "DocDate": payload.DocDate or today,
            "DocDueDate": payload.DocDueDate or today,
        }

        if payload.Comments:
            sap_doc["Comments"] = payload.Comments
        if payload.SalesPersonCode is not None:
            sap_doc["SalesPersonCode"] = payload.SalesPersonCode
        if payload.NumAtCard:
            sap_doc["NumAtCard"] = payload.NumAtCard
        if payload.ValidUntil:
            sap_doc["ValidUntil"] = payload.ValidUntil
        if payload.PaymentGroupCode is not None:
            sap_doc["PaymentGroupCode"] = payload.PaymentGroupCode

        # Lignes de devis
        lines = []
        for line in payload.DocumentLines:
            sap_line: Dict[str, Any] = {
                "ItemDescription": line.ItemDescription,
                "Quantity": line.Quantity,
                "DiscountPercent": line.DiscountPercent,
            }
            # ItemCode optionnel (peut être absent si produit non créé dans SAP)
            if line.ItemCode:
                sap_line["ItemCode"] = line.ItemCode
            if line.UnitPrice is not None:
                sap_line["UnitPrice"] = line.UnitPrice
            if line.TaxCode:
                sap_line["TaxCode"] = line.TaxCode
            if line.WarehouseCode:
                sap_line["WarehouseCode"] = line.WarehouseCode
            if line.FreeText:
                sap_line["FreeText"] = line.FreeText
            lines.append(sap_line)

        sap_doc["DocumentLines"] = lines
        return sap_doc

    # ----------------------------------------------------------
    # Appel SAP générique
    # ----------------------------------------------------------

    async def _call_sap_post(self, endpoint: str, payload: Dict) -> Dict[str, Any]:
        """
        POST vers SAP B1 Service Layer avec retry automatique sur 401.
        Timeout : 10 secondes.
        """
        url = f"{self.base_url}{endpoint}"

        async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
            response = await client.post(url, headers=self._get_headers(), json=payload)

            if response.status_code == 401:
                logger.warning("⚠️ SAP 401 - renouvellement session...")
                self.session_id = None
                self.session_timeout = None
                if not await self.login():
                    raise Exception("Impossible de renouveler la session SAP")
                # Retry une seule fois
                response = await client.post(url, headers=self._get_headers(), json=payload)

            return response

    # ----------------------------------------------------------
    # Création devis
    # ----------------------------------------------------------

    async def create_sales_quotation(self, payload: QuotationPayload) -> QuotationResult:
        """
        Crée un devis (Sales Quotation) dans SAP B1.

        Args:
            payload: QuotationPayload validé

        Returns:
            QuotationResult avec DocEntry, DocNum, DocTotal si succès
        """
        if not await self.ensure_session():
            return QuotationResult(
                success=False,
                message="Impossible de se connecter à SAP B1",
                error_code="SAP_LOGIN_FAILED",
            )

        sap_payload = self._build_sap_payload(payload)

        logger.info(
            "📤 Création devis SAP | CardCode=%s | Lignes=%d | Source=%s | EmailId=%s",
            payload.CardCode,
            len(payload.DocumentLines),
            payload.nova_source,
            payload.email_id or "N/A",
        )

        try:
            response = await self._call_sap_post("/Quotations", sap_payload)

            if response.status_code == 201:
                data = response.json()
                doc_entry = data.get("DocEntry")
                doc_num = data.get("DocNum")
                doc_total = data.get("DocTotal")
                logger.info(
                    "✅ Devis SAP créé | DocEntry=%s | DocNum=%s | Total=%.2f€",
                    doc_entry,
                    doc_num,
                    doc_total or 0,
                )
                return QuotationResult(
                    success=True,
                    doc_entry=doc_entry,
                    doc_num=doc_num,
                    doc_total=doc_total,
                    doc_date=data.get("DocDate"),
                    card_code=data.get("CardCode"),
                    card_name=data.get("CardName"),
                    message=f"Devis SAP n°{doc_num} créé avec succès",
                    sap_payload=sap_payload,
                )

            # Erreur SAP
            try:
                error_data = response.json()
                error_msg = error_data.get("error", {}).get("message", {})
                if isinstance(error_msg, dict):
                    error_msg = error_msg.get("value", str(error_data))
                error_code = str(error_data.get("error", {}).get("code", "SAP_ERROR"))
            except Exception:
                error_msg = response.text[:300]
                error_code = f"HTTP_{response.status_code}"

            logger.error(
                "❌ Erreur SAP %s | %s | Payload CardCode=%s",
                response.status_code,
                error_msg,
                payload.CardCode,
            )
            return QuotationResult(
                success=False,
                message=f"Erreur SAP ({response.status_code}): {error_msg}",
                error_code=error_code,
                sap_payload=sap_payload,
            )

        except httpx.TimeoutException:
            logger.error("❌ Timeout SAP (10s) lors de la création du devis")
            return QuotationResult(
                success=False,
                message="Timeout SAP dépassé (10s)",
                error_code="SAP_TIMEOUT",
                sap_payload=sap_payload,
            )
        except Exception as exc:
            logger.error("❌ Erreur inattendue création devis SAP: %s", exc, exc_info=True)
            return QuotationResult(
                success=False,
                message=f"Erreur interne: {exc}",
                error_code="INTERNAL_ERROR",
                sap_payload=sap_payload,
            )


# ============================================================
# SINGLETON
# ============================================================

_sap_quotation_service: Optional[SAPQuotationService] = None


def get_sap_quotation_service() -> SAPQuotationService:
    """Retourne l'instance singleton du service de création de devis SAP."""
    global _sap_quotation_service
    if _sap_quotation_service is None:
        _sap_quotation_service = SAPQuotationService()
        logger.info("SAPQuotationService singleton créé")
    return _sap_quotation_service
