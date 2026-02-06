# routes/routes_sap_rondot.py
"""
API Routes pour SAP Business One - Compte RONDOT
Utilisé par le frontend mail-to-biz
"""

import os
import json
import httpx
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sap-rondot", tags=["SAP Rondot"])

# Configuration SAP Rondot
SAP_BASE_URL = os.getenv("SAP_REST_BASE_URL")
SAP_USER_RONDOT = os.getenv("SAP_USER_RONDOT", "manager")
SAP_CLIENT_RONDOT = os.getenv("SAP_CLIENT_RONDOT", "RON_20260109")
SAP_PASSWORD_RONDOT = os.getenv("SAP_CLIENT_PASSWORD_RONDOT", "itspirit")

# Session SAP
sap_rondot_session = {
    "cookies": None,
    "expires": None
}


# --- Pydantic Models ---

class ConnectionTestResult(BaseModel):
    success: bool
    message: str
    details: Optional[Dict[str, Any]] = None


class SAPClient(BaseModel):
    CardCode: str
    CardName: str
    CardType: Optional[str] = None
    Phone1: Optional[str] = None
    EmailAddress: Optional[str] = None
    City: Optional[str] = None
    Country: Optional[str] = None


class SAPProduct(BaseModel):
    ItemCode: str
    ItemName: str
    ItemType: Optional[str] = None
    QuantityOnStock: Optional[float] = None
    Price: Optional[float] = None


class QuoteLine(BaseModel):
    ItemCode: str
    Quantity: float
    UnitPrice: Optional[float] = None


class CreateQuoteRequest(BaseModel):
    CardCode: str
    DocDate: Optional[str] = None
    DocDueDate: Optional[str] = None
    Comments: Optional[str] = None
    DocumentLines: List[QuoteLine]


# --- Helper Functions ---

async def login_sap_rondot() -> bool:
    """Connexion au compte SAP Rondot"""
    global sap_rondot_session

    url = f"{SAP_BASE_URL}/Login"
    auth_payload = {
        "UserName": SAP_USER_RONDOT,
        "Password": SAP_PASSWORD_RONDOT,
        "CompanyDB": SAP_CLIENT_RONDOT
    }
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "curl/8.5.0"
    }

    try:
        async with httpx.AsyncClient(verify=False, http2=False, timeout=30.0) as client:
            response = await client.post(url, content=json.dumps(auth_payload), headers=headers)
            response.raise_for_status()
            sap_rondot_session["cookies"] = response.cookies
            sap_rondot_session["expires"] = datetime.utcnow().timestamp() + 60 * 20
            logger.info(f"Connexion SAP Rondot reussie - CompanyDB: {SAP_CLIENT_RONDOT}")
            return True
    except Exception as e:
        logger.error(f"Erreur connexion SAP Rondot: {e}")
        return False


async def call_sap_rondot(endpoint: str, method: str = "GET", payload: Optional[dict] = None) -> Dict[str, Any]:
    """Appel API SAP Rondot avec gestion de session"""
    global sap_rondot_session

    # Vérifier/renouveler la session
    if not sap_rondot_session["cookies"] or datetime.utcnow().timestamp() > (sap_rondot_session["expires"] or 0):
        if not await login_sap_rondot():
            return {"error": "Impossible de se connecter à SAP Rondot"}

    url = f"{SAP_BASE_URL}{endpoint}"

    try:
        async with httpx.AsyncClient(cookies=sap_rondot_session["cookies"], verify=False, timeout=30.0) as client:
            if method == "GET":
                response = await client.get(url)
            elif method == "POST":
                response = await client.post(url, json=payload or {})
            elif method == "PATCH":
                response = await client.patch(url, json=payload or {})
            else:
                return {"error": f"Methode non supportee: {method}"}

            # Reconnexion si 401
            if response.status_code == 401:
                if await login_sap_rondot():
                    return await call_sap_rondot(endpoint, method, payload)
                return {"error": "Session expiree, reconnexion echouee"}

            response.raise_for_status()
            return response.json()

    except httpx.HTTPStatusError as e:
        logger.error(f"Erreur HTTP SAP Rondot: {e}")
        return {"error": f"Erreur HTTP: {e.response.status_code}"}
    except Exception as e:
        logger.error(f"Erreur appel SAP Rondot: {e}")
        return {"error": str(e)}


# --- API Endpoints ---

@router.get("/test-connection", response_model=ConnectionTestResult)
async def test_sap_rondot_connection():
    """Teste la connexion SAP Rondot"""
    try:
        success = await login_sap_rondot()

        if success:
            # Test requête simple
            result = await call_sap_rondot("/Items?$top=1&$select=ItemCode,ItemName")

            if "error" not in result:
                return ConnectionTestResult(
                    success=True,
                    message=f"Connexion SAP Rondot reussie - Base: {SAP_CLIENT_RONDOT}",
                    details={
                        "company_db": SAP_CLIENT_RONDOT,
                        "user": SAP_USER_RONDOT,
                        "test_query": "OK"
                    }
                )

        return ConnectionTestResult(
            success=False,
            message="Echec de connexion SAP Rondot"
        )

    except Exception as e:
        return ConnectionTestResult(
            success=False,
            message=f"Erreur: {str(e)}"
        )


@router.get("/clients")
async def get_sap_rondot_clients(
    search: Optional[str] = Query(None, description="Recherche par nom ou code"),
    limit: int = Query(50, ge=1, le=500)
):
    """Récupère les clients SAP Rondot"""
    endpoint = "/BusinessPartners?$select=CardCode,CardName,CardType,Phone1,EmailAddress,City,Country"

    if search:
        endpoint += f"&$filter=contains(CardName,'{search}') or contains(CardCode,'{search}')"

    endpoint += f"&$orderby=CardName&$top={limit}"

    result = await call_sap_rondot(endpoint)

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return {
        "success": True,
        "clients": result.get("value", []),
        "count": len(result.get("value", []))
    }


@router.get("/clients/{card_code}")
async def get_sap_rondot_client(card_code: str):
    """Récupère un client SAP Rondot par son code"""
    result = await call_sap_rondot(f"/BusinessPartners('{card_code}')")

    if "error" in result:
        raise HTTPException(status_code=404, detail=f"Client non trouve: {card_code}")

    return {"success": True, "client": result}


@router.get("/products")
async def get_sap_rondot_products(
    search: Optional[str] = Query(None, description="Recherche par nom ou code"),
    limit: int = Query(50, ge=1, le=500)
):
    """Récupère les produits SAP Rondot"""
    endpoint = "/Items?$select=ItemCode,ItemName,ItemType,QuantityOnStock"

    if search:
        endpoint += f"&$filter=contains(ItemName,'{search}') or contains(ItemCode,'{search}')"

    endpoint += f"&$orderby=ItemCode&$top={limit}"

    result = await call_sap_rondot(endpoint)

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return {
        "success": True,
        "products": result.get("value", []),
        "count": len(result.get("value", []))
    }


@router.get("/products/{item_code}")
async def get_sap_rondot_product(item_code: str):
    """Récupère un produit SAP Rondot par son code"""
    result = await call_sap_rondot(f"/Items('{item_code}')")

    if "error" in result:
        raise HTTPException(status_code=404, detail=f"Produit non trouve: {item_code}")

    return {"success": True, "product": result}


@router.get("/products/{item_code}/price")
async def get_sap_rondot_product_price(item_code: str, card_code: Optional[str] = None):
    """Récupère le prix d'un produit (avec prix client si spécifié)"""
    # Prix de base
    product = await call_sap_rondot(f"/Items('{item_code}')?$select=ItemCode,ItemName,ItemPrices")

    if "error" in product:
        raise HTTPException(status_code=404, detail=f"Produit non trouve: {item_code}")

    # Prix client spécifique si demandé
    client_price = None
    if card_code:
        price_result = await call_sap_rondot(
            f"/SpecialPrices?$filter=CardCode eq '{card_code}' and ItemCode eq '{item_code}'"
        )
        if "value" in price_result and price_result["value"]:
            client_price = price_result["value"][0].get("Price")

    return {
        "success": True,
        "item_code": item_code,
        "base_prices": product.get("ItemPrices", []),
        "client_price": client_price
    }


@router.get("/quotations")
async def get_sap_rondot_quotations(
    card_code: Optional[str] = Query(None, description="Filtrer par client"),
    limit: int = Query(50, ge=1, le=500)
):
    """Récupère les devis SAP Rondot"""
    endpoint = "/Quotations?$select=DocEntry,DocNum,CardCode,CardName,DocDate,DocTotal,DocStatus"

    if card_code:
        endpoint += f"&$filter=CardCode eq '{card_code}'"

    endpoint += f"&$orderby=DocDate desc&$top={limit}"

    result = await call_sap_rondot(endpoint)

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return {
        "success": True,
        "quotations": result.get("value", []),
        "count": len(result.get("value", []))
    }


@router.get("/quotations/{doc_entry}")
async def get_sap_rondot_quotation(doc_entry: int):
    """Récupère un devis SAP Rondot par son DocEntry"""
    result = await call_sap_rondot(f"/Quotations({doc_entry})")

    if "error" in result:
        raise HTTPException(status_code=404, detail=f"Devis non trouve: {doc_entry}")

    return {"success": True, "quotation": result}


@router.post("/quotations")
async def create_sap_rondot_quotation(request: CreateQuoteRequest):
    """Crée un devis SAP Rondot"""
    # Préparer le payload SAP
    today = datetime.now().strftime("%Y-%m-%d")

    payload = {
        "CardCode": request.CardCode,
        "DocDate": request.DocDate or today,
        "DocDueDate": request.DocDueDate or today,
        "Comments": request.Comments or "Devis cree via mail-to-biz",
        "DocumentLines": [
            {
                "ItemCode": line.ItemCode,
                "Quantity": line.Quantity,
                **({"UnitPrice": line.UnitPrice} if line.UnitPrice else {})
            }
            for line in request.DocumentLines
        ]
    }

    result = await call_sap_rondot("/Quotations", method="POST", payload=payload)

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return {
        "success": True,
        "message": "Devis cree avec succes",
        "quotation": {
            "DocEntry": result.get("DocEntry"),
            "DocNum": result.get("DocNum"),
            "CardCode": result.get("CardCode"),
            "DocTotal": result.get("DocTotal")
        }
    }


@router.get("/status")
async def get_sap_rondot_status():
    """Retourne le statut de la connexion SAP Rondot"""
    is_connected = sap_rondot_session["cookies"] is not None and \
                   sap_rondot_session["expires"] and \
                   datetime.utcnow().timestamp() < sap_rondot_session["expires"]

    return {
        "connected": is_connected,
        "company_db": SAP_CLIENT_RONDOT,
        "user": SAP_USER_RONDOT,
        "session_expires": datetime.fromtimestamp(sap_rondot_session["expires"]).isoformat() if sap_rondot_session["expires"] else None
    }
