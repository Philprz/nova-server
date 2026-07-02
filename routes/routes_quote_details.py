"""
API Routes pour la récupération détaillée des devis (Version MCPConnector Corrigée)
Utilise la bonne méthode du MCPConnector - performance optimale
"""

from fastapi import APIRouter, Depends, HTTPException
from auth.dependencies import get_current_user
from typing import Dict, Any
import logging
from datetime import datetime

# Configuration du logging
logger = logging.getLogger(__name__)

# Création du router
router = APIRouter(
    prefix="/api/quotes",
    tags=["Quote Details"],
    responses={404: {"description": "Quote not found"}},
    dependencies=[Depends(get_current_user)],
)

@router.get("/details/{quote_id}")
async def get_quote_details(
    quote_id: str,
    include_lines: bool = True,
    include_customer: bool = True
) -> Dict[str, Any]:
    """
    Récupère les détails complets d'un devis pour édition
    
    Args:
        quote_id: ID du devis (format: SAP-{DocEntry})
        include_lines: Inclure les lignes de produits
        include_customer: Inclure les informations client
    
    Returns:
        Dict contenant toutes les informations éditables du devis
    """
    
    try:
        logger.info(f"Récupération des détails du devis: {quote_id}")
        
        # Parsing de l'ID pour déterminer le système source
        if quote_id.startswith("SAP-"):
            doc_entry = quote_id.replace("SAP-", "")
            return await get_sap_quote_details(doc_entry, include_lines, include_customer)

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Format d'ID invalide: {quote_id}. Attendu: SAP-{{DocEntry}}"
            )

    except Exception as e:
        logger.error(f"Erreur lors de la récupération du devis {quote_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur interne: {str(e)}")
@router.put("/modify/{quote_id}")
async def modify_quote(
    quote_id: str,
    modifications: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Modifie un devis existant
    
    Args:
        quote_id: ID du devis (format: SAP-{DocEntry})
        modifications: Dict contenant les modifications à apporter
    
    Returns:
        Dict contenant le statut de la modification
    """
    
    try:
        logger.info(f"Modification du devis: {quote_id}")
        logger.info(f"Modifications: {modifications}")
        
        # Parsing de l'ID pour déterminer le système source
        if quote_id.startswith("SAP-"):
            doc_entry = quote_id.replace("SAP-", "")
            return await modify_sap_quote(doc_entry, modifications)

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Format d'ID invalide: {quote_id}. Attendu: SAP-{{DocEntry}}"
            )

    except Exception as e:
        logger.error(f"Erreur lors de la modification du devis {quote_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur interne: {str(e)}")

async def modify_sap_quote(
    doc_entry: str, 
    modifications: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Modifie un devis SAP Business One
    """
    
    try:
        from services.mcp_connector import get_mcp_connector

        connector = get_mcp_connector()
        
        # Utiliser la nouvelle fonction de modification
        logger.info(f"Modification du devis SAP {doc_entry}")
        # Correction de la syntaxe d'appel
        sap_response = await connector.call_sap_mcp("sap_modify_quote", {
            "doc_entry": int(doc_entry),
            "modifications": modifications
        })
        # Unwrap éventuel des réponses encapsulées
        if isinstance(sap_response, dict) and "result" in sap_response:
            sap_response = sap_response["result"]
        
        if not sap_response or not isinstance(sap_response, dict):
            raise HTTPException(
                status_code=500,
                detail="Réponse SAP invalide ou vide"
            )
        
        if not sap_response.get("success", False):
            error_msg = sap_response.get('error', 'Erreur inconnue')
            raise HTTPException(
                status_code=400,
                detail=f"Erreur SAP lors de la modification: {error_msg}"
            )
        
        logger.info(f"Devis SAP {doc_entry} modifié avec succès")
        
        return {
            "success": True,
            "message": sap_response.get("message", "Devis modifié avec succès"),
            "quote_id": f"SAP-{doc_entry}",
            "updated_data": sap_response.get("updated_quote", {})
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur modification devis SAP {doc_entry}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur SAP: {str(e)}")

async def get_sap_quote_details(
    doc_entry: str,
    include_lines: bool = True,
    include_customer: bool = True
) -> Dict[str, Any]:
    """
    Récupère les détails d'un devis SAP Business One
    """
    from services.mcp_connector import get_mcp_connector

    try:
        connector = get_mcp_connector()
        logger.info(f"Récupération du devis SAP {doc_entry}")

        # Essayer d'abord avec get_quotation_details (si disponible)
        try:
            sap_response = await connector.call_sap_mcp("get_quotation_details", {
                "doc_entry": int(doc_entry),
                "include_lines": include_lines,
                "include_customer": include_customer
            })
        except Exception as e:
            # Fallback sur sap_read si get_quotation_details n'existe pas
            logger.warning(f"get_quotation_details non disponible, utilisation de sap_read: {str(e)}")
            # Appel corrigé avec les bons paramètres
            sap_response = await connector.call_sap_mcp("sap_read", {
                "endpoint": f"/Quotations({doc_entry})",
                "method": "GET"
            })

        logger.info(f"Réponse SAP reçue pour devis {doc_entry}")

        # CORRECTION: Traitement spécial si le résultat MCP est encapsulé dans 'result'
        if isinstance(sap_response, dict) and 'result' in sap_response:
            actual_response = sap_response['result']
            if isinstance(actual_response, str):
                # Tenter de parser le JSON si c'est une string
                try:
                    import json
                    sap_response = json.loads(actual_response)
                except:
                    raise HTTPException(status_code=500, detail=f"Erreur SAP: {actual_response}")
            else:
                sap_response = actual_response

        # CORRECTION: Vérifier le type de réponse d'abord
        if isinstance(sap_response, str):
            if "error" in sap_response.lower() or "not found" in sap_response.lower():
                raise HTTPException(status_code=404, detail=f"Devis {doc_entry} non trouvé")
            else:
                raise HTTPException(status_code=500, detail=f"Format de réponse SAP invalide: {sap_response}")

        # Vérifier les erreurs dans la réponse dict
        if isinstance(sap_response, dict):
            # Si la réponse contient un champ error
            if "error" in sap_response:
                error_msg = sap_response.get("error", {})
                if isinstance(error_msg, dict):
                    error_msg = error_msg.get("message", sap_response.get("message", "Erreur inconnue"))
                logger.error(f"Erreur SAP: {error_msg}")
                raise HTTPException(status_code=500, detail=str(error_msg))

            # Si la réponse contient un champ success = False
            if "success" in sap_response and not sap_response["success"]:
                error_msg = sap_response.get("message", sap_response.get("error", "Échec de récupération du devis"))
                logger.error(f"Échec SAP: {error_msg}")
                raise HTTPException(status_code=400, detail=str(error_msg))

        # Extraire les données du devis
        quote_data = None
        if isinstance(sap_response, dict):
            # Si les données sont dans "value" (format oData)
            if "value" in sap_response:
                values = sap_response["value"]
                if isinstance(values, list) and len(values) > 0:
                    quote_data = values[0]
                else:
                    logger.error(f"Devis {doc_entry} non trouvé dans SAP")
                    raise HTTPException(status_code=404, detail=f"Devis {doc_entry} non trouvé")
            # Si les données sont directement dans la réponse
            elif "DocEntry" in sap_response:
                quote_data = sap_response
            # Si les données sont dans "quote"
            elif "quote" in sap_response:
                quote_data = sap_response["quote"]

        if not quote_data:
            logger.error(f"Structure de réponse SAP inattendue: {sap_response}")
            raise HTTPException(status_code=500, detail="Format de réponse SAP invalide")

        # Formater la réponse pour l'interface
        formatted_response = {
            "success": True,
            "quote": {
                "doc_entry": quote_data.get("DocEntry"),
                "doc_num": quote_data.get("DocNum"),
                "doc_date": quote_data.get("DocDate"),
                "doc_due_date": quote_data.get("DocDueDate"),
                "doc_total": quote_data.get("DocTotal", 0),
                "card_code": quote_data.get("CardCode"),
                "card_name": quote_data.get("CardName"),
                "comments": quote_data.get("Comments", ""),
                "lines": []
            }
        }

        # Ajouter les lignes si demandées
        if include_lines and "DocumentLines" in quote_data:
            for line in quote_data["DocumentLines"]:
                formatted_response["quote"]["lines"].append({
                    "line_num": line.get("LineNum"),
                    "item_code": line.get("ItemCode"),
                    "item_description": line.get("ItemDescription"),
                    "quantity": line.get("Quantity", 0),
                    "unit_price": line.get("UnitPrice", 0),
                    "discount_percent": line.get("DiscountPercent", 0),
                    "line_total": line.get("LineTotal", 0)
                })

        logger.info(f"Devis SAP {doc_entry} récupéré avec succès")
        return formatted_response
    except HTTPException:
        # Re-raise HTTPException as-is
        raise
    except Exception as e:
        logger.error(f"Erreur SAP pour devis {doc_entry}: {str(e)}")

        # Tentative avec l'instance globale du connecteur
        try:
            from services.mcp_connector import get_mcp_connector
            connector = get_mcp_connector()

            sap_response = await connector.call_sap_mcp("sap_read", {
                "endpoint": f"/Quotations({doc_entry})",
                "method": "GET"
            })

            if sap_response and "error" not in sap_response:
                # Formatter directement la réponse ici au lieu d'appeler une fonction non définie
                quote_data = sap_response
                if isinstance(sap_response, dict):
                    if "value" in sap_response and isinstance(sap_response["value"], list):
                        quote_data = sap_response["value"][0] if sap_response["value"] else None
                    elif "quote" in sap_response:
                        quote_data = sap_response["quote"]

                if quote_data:
                    formatted_response = {
                        "success": True,
                        "quote": {
                            "doc_entry": quote_data.get("DocEntry"),
                            "doc_num": quote_data.get("DocNum"),
                            "doc_date": quote_data.get("DocDate"),
                            "doc_due_date": quote_data.get("DocDueDate"),
                            "doc_total": quote_data.get("DocTotal", 0),
                            "card_code": quote_data.get("CardCode"),
                            "card_name": quote_data.get("CardName"),
                            "comments": quote_data.get("Comments", ""),
                            "lines": []
                        }
                    }

                    if include_lines and "DocumentLines" in quote_data:
                        for line in quote_data["DocumentLines"]:
                            formatted_response["quote"]["lines"].append({
                                "line_num": line.get("LineNum"),
                                "item_code": line.get("ItemCode"),
                                "item_description": line.get("ItemDescription"),
                                "quantity": line.get("Quantity", 0),
                                "unit_price": line.get("UnitPrice", 0),
                                "discount_percent": line.get("DiscountPercent", 0),
                                "line_total": line.get("LineTotal", 0)
                            })

                    return formatted_response

        except Exception as e2:
            logger.error(f"Fallback échoué: {str(e2)}")

        # Si tout échoue, retourner une erreur détaillée
        raise HTTPException(
            status_code=500,
            detail=f"Erreur SAP: {str(e)}"
        )

def structure_quote_for_editing(quote_data: Dict[str, Any], doc_entry: int) -> Dict[str, Any]:
    """Structure les données SAP pour l'interface d'édition"""
    
    # Informations header du devis
    header = {
        "doc_entry": quote_data.get("DocEntry"),
        "doc_num": quote_data.get("DocNum"),
        "doc_date": quote_data.get("DocDate"),
        "doc_due_date": quote_data.get("DocDueDate"),
        "valid_until": quote_data.get("ValidUntil"),
        "card_code": quote_data.get("CardCode"),
        "card_name": quote_data.get("CardName"),
        "comments": quote_data.get("Comments", ""),
        "reference": quote_data.get("NumAtCard", ""),
        "sales_person": quote_data.get("SalesPersonCode"),
        "payment_terms": quote_data.get("PaymentGroupCode"),
        "document_status": quote_data.get("DocumentStatus")
    }
    
    # Informations client détaillées
    customer = {}
    customer_details = quote_data.get("CustomerDetails", {})
    if customer_details:
        customer = {
            "card_code": customer_details.get("CardCode"),
            "card_name": customer_details.get("CardName"),
            "phone": customer_details.get("Phone1"),
            "email": customer_details.get("EmailAddress"),
            "website": customer_details.get("Website"),
            "billing_address": customer_details.get("BillingAddress", {}),
            "shipping_address": customer_details.get("ShippingAddress", {})
        }
    else:
        # Fallback avec les données de base du devis
        customer = {
            "card_code": quote_data.get("CardCode"),
            "card_name": quote_data.get("CardName"),
            "phone": "",
            "email": "",
            "website": "",
            "billing_address": {},
            "shipping_address": {}
        }
    
    # Lignes de produits
    lines = []
    for line_data in quote_data.get("DocumentLines", []):
        line = {
            "line_num": line_data.get("LineNum"),
            "item_code": line_data.get("ItemCode"),
            "item_description": line_data.get("ItemDescription"),
            "quantity": line_data.get("Quantity", 1),
            "unit_price": line_data.get("UnitPrice", 0),
            "price_after_vat": line_data.get("PriceAfterVAT", 0),
            "discount_percent": line_data.get("DiscountPercent", 0),
            "line_total": line_data.get("LineTotal", 0),
            "line_total_with_vat": line_data.get("LineTotalSys", 0),
            "tax_code": line_data.get("TaxCode"),
            "tax_percent": line_data.get("TaxPercentagePerRow", 0),
            "warehouse_code": line_data.get("WarehouseCode"),
            "currency": line_data.get("Currency", "EUR"),
            "free_text": line_data.get("FreeText", ""),
            
            # Métadonnées d'édition
            "editable_fields": [
                "quantity", "unit_price", "discount_percent",
                "item_description", "warehouse_code", "free_text"
            ],
            "validation": {
                "min_quantity": 1,
                "max_quantity": 999999,
                "min_price": 0.01,
                "max_discount": 100,
                "step_quantity": 1,
                "step_price": 0.01,
                "step_discount": 0.01
            }
        }
        lines.append(line)
    
    # Totaux
    totals = {
        "subtotal": quote_data.get("DocTotal", 0),
        "total_before_discount": quote_data.get("TotalDiscount", 0),
        "discount_total": quote_data.get("TotalDiscountFC", 0),
        "tax_total": quote_data.get("VatSum", 0),
        "total_with_tax": (quote_data.get("DocTotal", 0) + quote_data.get("VatSum", 0)),
        "currency": quote_data.get("DocCurrency", "EUR"),
        "rounding": quote_data.get("RoundingDiffAmount", 0)
    }
    
    # Structure finale pour l'édition
    editable_structure = {
        "quote_id": f"SAP-{quote_data.get('DocEntry')}",
        "source_system": "SAP Business One",
        "last_updated": quote_data.get("UpdateDate"),
        "editable": True,
        
        "header": header,
        "customer": customer,
        "lines": lines,
        "totals": totals,
        
        # Règles de validation globales
        "validation_rules": {
            "can_modify_header": True,
            "can_modify_lines": True,
            "can_add_lines": True,
            "can_remove_lines": True,
            "can_modify_customer": False,  # Généralement non modifiable
            "required_fields": ["DocDate", "CardCode"],
            "business_rules": {
                "auto_recalculate_totals": True,
                "validate_stock_availability": True,
                "apply_customer_discounts": True
            }
        }
    }
    
    return {
        "success": True,
        "quote": editable_structure,
        "metadata": {
            "source": "SAP Business One",
            "retrieved_at": datetime.now().isoformat(),
            "total_lines": len(lines),
            "editable_fields_count": count_editable_fields(editable_structure),
            "doc_entry": doc_entry
        }
    }

def count_editable_fields(structure: Dict[str, Any]) -> int:
    """
    Compte le nombre total de champs éditables dans la structure
    """
    count = 0
    
    # Header
    if "header" in structure:
        count += len([k for k, v in structure["header"].items() if v is not None])
    
    # Customer
    if "customer" in structure:
        count += len([k for k, v in structure["customer"].items() if v is not None])
    
    # Lines
    for line in structure.get("lines", []):
        count += len(line.get("editable_fields", []))
    
    return count

@router.get("/structure/{quote_id}")
async def get_quote_structure_for_editing(quote_id: str) -> Dict[str, Any]:
    """
    Retourne uniquement la structure d'édition (champs, types, validations)
    sans les données, pour construire l'interface dynamique
    """
    
    try:
        # Structure adaptée selon le type de devis (SAP)
        if quote_id.startswith("SAP-"):
            return get_sap_structure()
        else:
            return get_generic_structure()
            
    except Exception as e:
        logger.error(f"Erreur structure pour {quote_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")

def get_sap_structure() -> Dict[str, Any]:
    """Structure spécifique pour les devis SAP"""
    return {
        "success": True,
        "structure": {
            "sections": [
                {
                    "id": "header",
                    "title": "Informations générales",
                    "icon": "📋",
                    "fields": [
                        {"name": "doc_date", "type": "date", "required": True, "label": "Date du devis", "editable": True},
                        {"name": "doc_due_date", "type": "date", "required": False, "label": "Date d'échéance", "editable": True},
                        {"name": "valid_until", "type": "date", "required": False, "label": "Valide jusqu'au", "editable": True},
                        {"name": "comments", "type": "textarea", "required": False, "label": "Commentaires", "editable": True, "max_length": 254},
                        {"name": "reference", "type": "text", "required": False, "label": "Référence client", "editable": True, "max_length": 100}
                    ]
                },
                {
                    "id": "customer",
                    "title": "Informations client",
                    "icon": "🏢",
                    "editable": False,
                    "description": "Informations client (lecture seule)",
                    "fields": [
                        {"name": "card_name", "type": "text", "readonly": True, "label": "Nom du client"},
                        {"name": "phone", "type": "tel", "readonly": True, "label": "Téléphone"},
                        {"name": "email", "type": "email", "readonly": True, "label": "Email"}
                    ]
                },
                {
                    "id": "lines",
                    "title": "Lignes de produits",
                    "icon": "📦",
                    "type": "array",
                    "can_add": True,
                    "can_remove": True,
                    "can_reorder": True,
                    "fields": [
                        {"name": "item_code", "type": "text", "required": True, "label": "Code produit", "editable": True},
                        {"name": "item_description", "type": "text", "required": True, "label": "Description", "editable": True, "max_length": 200},
                        {"name": "quantity", "type": "number", "required": True, "min": 1, "max": 999999, "step": 1, "label": "Quantité", "editable": True},
                        {"name": "unit_price", "type": "number", "required": True, "min": 0.01, "step": 0.01, "label": "Prix unitaire", "editable": True, "currency": "EUR"},
                        {"name": "discount_percent", "type": "number", "required": False, "min": 0, "max": 100, "step": 0.01, "label": "Remise %", "editable": True},
                        {"name": "line_total", "type": "number", "readonly": True, "label": "Total ligne", "currency": "EUR", "calculated": True}
                    ]
                },
                {
                    "id": "totals",
                    "title": "Totaux",
                    "icon": "💰", 
                    "editable": False,
                    "description": "Totaux calculés automatiquement",
                    "fields": [
                        {"name": "subtotal", "type": "number", "readonly": True, "label": "Sous-total HT", "currency": "EUR"},
                        {"name": "tax_total", "type": "number", "readonly": True, "label": "Total TVA", "currency": "EUR"},
                        {"name": "total_with_tax", "type": "number", "readonly": True, "label": "Total TTC", "currency": "EUR", "highlight": True}
                    ]
                }
            ],
            "validation_rules": {
                "business_rules": [
                    "Auto-calcul des totaux de lignes",
                    "Validation des stocks disponibles", 
                    "Application des remises client",
                    "Contrôle des prix minimum"
                ],
                "required_sections": ["header", "lines"],
                "min_lines": 1
            }
        }
    }

def get_generic_structure() -> Dict[str, Any]:
    """Structure générique pour les devis"""
    return {
        "success": True,
        "structure": {
            "sections": [
                {
                    "id": "header",
                    "title": "Informations générales",
                    "fields": [
                        {"name": "date", "type": "date", "required": True, "label": "Date", "editable": True},
                        {"name": "comments", "type": "textarea", "required": False, "label": "Commentaires", "editable": True}
                    ]
                }
            ]
        }
    }

@router.get("/structure")
async def get_quote_edit_structure() -> Dict[str, Any]:
    """
    Retourne la structure d'édition générique pour les devis SAP
    Utile pour construire l'interface d'édition dynamique
    """
    
    return get_sap_structure()