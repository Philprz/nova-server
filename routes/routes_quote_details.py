"""
API Routes pour la récupération détaillée des devis (Version MCPConnector Corrigée)
Utilise la bonne méthode du MCPConnector - performance optimale
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import logging
from datetime import datetime

# Configuration du logging
logger = logging.getLogger(__name__)

# Création du router
router = APIRouter(
    prefix="/api/quotes",
    tags=["Quote Details"],
    responses={404: {"description": "Quote not found"}}
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
        quote_id: ID du devis (format: SAP-{DocEntry} ou SF-{OpportunityId})
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
        
        elif quote_id.startswith("SF-"):
            opportunity_id = quote_id.replace("SF-", "")
            return await get_salesforce_quote_details(opportunity_id, include_lines, include_customer)
        
        else:
            raise HTTPException(
                status_code=400, 
                detail=f"Format d'ID invalide: {quote_id}. Attendu: SAP-{{DocEntry}} ou SF-{{OpportunityId}}"
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
        
        elif quote_id.startswith("SF-"):
            opportunity_id = quote_id.replace("SF-", "")
            return await modify_salesforce_quote(opportunity_id, modifications)
        
        else:
            raise HTTPException(
                status_code=400, 
                detail=f"Format d'ID invalide: {quote_id}. Attendu: SAP-{{DocEntry}} ou SF-{{OpportunityId}}"
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
        from services.mcp_connector import MCPConnector
        
        connector = MCPConnector()
        
        # Utiliser la nouvelle fonction de modification
        logger.info(f"Modification du devis SAP {doc_entry}")
        sap_response = await connector.call_sap_mcp(
            "sap_modify_quote",
            {
                "doc_entry": int(doc_entry),
                "modifications": modifications
            }
        )
        
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

async def modify_salesforce_quote(
    opportunity_id: str,
    modifications: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Modifie une opportunité Salesforce
    """
    
    try:
        from services.mcp_connector import MCPConnector
        
        connector = MCPConnector()
        
        # Préparer les données Salesforce
        sf_update_data = {}
        
        if "header" in modifications:
            header_mods = modifications["header"]
            if "comments" in header_mods:
                sf_update_data["Description"] = header_mods["comments"]
            if "doc_due_date" in header_mods:
                sf_update_data["CloseDate"] = header_mods["doc_due_date"]
            if "amount" in header_mods:
                sf_update_data["Amount"] = float(header_mods["amount"])
        
        # Mettre à jour l'opportunité
        sf_response = await connector.call_salesforce_mcp(
            "salesforce_update_record",
            {
                "sobject_type": "Opportunity",
                "record_id": opportunity_id,
                "record_data": sf_update_data
            }
        )
        
        if not sf_response or not sf_response.get("success", False):
            error_msg = sf_response.get('error', 'Erreur inconnue') if sf_response else 'Pas de réponse'
            raise HTTPException(
                status_code=400,
                detail=f"Erreur Salesforce lors de la modification: {error_msg}"
            )
        
        logger.info(f"Opportunité Salesforce {opportunity_id} modifiée avec succès")
        
        return {
            "success": True,
            "message": "Opportunité Salesforce modifiée avec succès",
            "quote_id": f"SF-{opportunity_id}",
            "updated_data": sf_response
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur modification opportunité SF {opportunity_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur Salesforce: {str(e)}")
async def get_sap_quote_details(
    doc_entry: str, 
    include_lines: bool = True, 
    include_customer: bool = True
) -> Dict[str, Any]:
    """
    Récupère les détails complets d'un devis SAP Business One
    """
    
    try:
        # Utilisation correcte du MCPConnector avec la bonne méthode
        from services.mcp_connector import MCPConnector
        
        connector = MCPConnector()
        
        # Utiliser la méthode call_sap_mcp qui existe avec la bonne signature
        sap_response = None
        logger.info(f"Appel SAP MCP pour devis {doc_entry}")
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
            # Réponse est un message d'erreur string
            raise HTTPException(
                status_code=500,
                detail=f"Erreur SAP: {sap_response}"
            )
        
        if not sap_response or not isinstance(sap_response, dict):
            raise HTTPException(
                status_code=500,
                detail="Réponse SAP invalide ou vide"
            )
        
        if not sap_response.get("success", False):
            error_msg = sap_response.get('error', 'Erreur inconnue')
            raise HTTPException(
                status_code=404,
                detail=f"Devis SAP {doc_entry} non trouvé ou erreur: {error_msg}"
            )
        
        # Structure la réponse pour l'édition
        quote_data = sap_response.get("quote", {})
        
        if not quote_data:
            raise HTTPException(
                status_code=404,
                detail=f"Données de devis vides pour DocEntry {doc_entry}"
            )
        
        # Enrichissement avec métadonnées d'édition
        editable_structure = structure_quote_for_editing(quote_data, int(doc_entry))
        
        lines_count = len(editable_structure.get('quote', {}).get('lines', []))
        logger.info(f"Devis SAP {doc_entry} récupéré avec succès - {lines_count} lignes")
        
        # Formatage pour l'affichage dans l'interface
        formatted_response = {
            "success": True,
            "quote_id": f"SAP-{doc_entry}",
            "quote": {
                "doc_entry": quote_data.get("DocEntry"),
                "doc_num": quote_data.get("DocNum"),
                "doc_date": quote_data.get("DocDate"),
                "doc_due_date": quote_data.get("DocDueDate"),
                "card_code": quote_data.get("CardCode"),
                "card_name": quote_data.get("CardName"),
                "doc_total": quote_data.get("DocTotal", 0),
                "currency": quote_data.get("DocCurrency", "EUR"),
                "comments": quote_data.get("Comments", ""),
                "status": quote_data.get("DocumentStatus", ""),
                "lines": []
            },
            "editable_structure": editable_structure
        }
        
        # Ajouter les lignes de produits
        for line_data in quote_data.get("DocumentLines", []):
            line = {
                "line_num": line_data.get("LineNum"),
                "item_code": line_data.get("ItemCode"),
                "item_description": line_data.get("ItemDescription", line_data.get("ItemName", "")),
                "quantity": line_data.get("Quantity", 0),
                "unit_price": line_data.get("UnitPrice", line_data.get("Price", 0)),
                "line_total": line_data.get("LineTotal", 0),
                "tax_code": line_data.get("TaxCode", ""),
                "discount_percent": line_data.get("DiscountPercent", 0)
            }
            formatted_response["quote"]["lines"].append(line)
        
        logger.info(f"Devis SAP {doc_entry} formaté avec succès - {len(formatted_response['quote']['lines'])} lignes")
        return formatted_response
    
    except HTTPException:
        # Re-raise HTTPException without modification
        raise
    except Exception as e:
        logger.error(f"Erreur SAP pour devis {doc_entry}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur SAP: {str(e)}")

async def get_salesforce_quote_details(
    opportunity_id: str,
    include_lines: bool = True,
    include_customer: bool = True
) -> Dict[str, Any]:
    """
    Récupère les détails complets d'une opportunité Salesforce
    """
    
    try:
        from services.mcp_connector import MCPConnector
        
        connector = MCPConnector()
        
        # Récupération de l'opportunité Salesforce complète
        sf_request = {
            "tool": "get_opportunity_details",
            "opportunity_id": opportunity_id,
            "include_products": include_lines,
            "include_account": include_customer
        }
        
        logger.info(f"Appel Salesforce MCP pour opportunité {opportunity_id}")
        sf_response = await connector.call_salesforce_mcp(sf_request)
        
        if not sf_response or not sf_response.get("success", False):
            raise HTTPException(
                status_code=404,
                detail=f"Opportunité Salesforce {opportunity_id} non trouvée: {sf_response.get('error', 'Erreur inconnue') if sf_response else 'Pas de réponse'}"
            )
        
        # Structure la réponse Salesforce pour l'édition
        opportunity = sf_response.get("opportunity", {})
        
        editable_structure = {
            "quote_id": f"SF-{opportunity_id}",
            "source_system": "Salesforce",
            "editable": True,
            "last_updated": opportunity.get("LastModifiedDate"),
            
            # Informations header
            "header": {
                "opportunity_id": opportunity.get("Id"),
                "name": opportunity.get("Name"),
                "stage": opportunity.get("StageName"),
                "close_date": opportunity.get("CloseDate"),
                "probability": opportunity.get("Probability"),
                "amount": opportunity.get("Amount"),
                "description": opportunity.get("Description", ""),
                "lead_source": opportunity.get("LeadSource"),
                "owner": opportunity.get("Owner", {}).get("Name")
            },
            
            # Informations client (Account)
            "customer": {},
            
            # Produits/lignes
            "lines": [],
            
            # Totaux
            "totals": {
                "total": opportunity.get("Amount", 0),
                "currency": "EUR"
            },
            
            # Métadonnées pour validation
            "validation_rules": {
                "can_modify_lines": True,
                "can_modify_pricing": True,
                "can_modify_customer": False,
                "required_fields": ["Name", "CloseDate", "StageName"]
            }
        }
        
        # Informations client si demandées
        if include_customer and "Account" in opportunity:
            account = opportunity["Account"]
            editable_structure["customer"] = {
                "account_id": account.get("Id"),
                "name": account.get("Name"),
                "billing_address": {
                    "street": account.get("BillingStreet"),
                    "city": account.get("BillingCity"),
                    "postal_code": account.get("BillingPostalCode"),
                    "country": account.get("BillingCountry")
                },
                "phone": account.get("Phone"),
                "website": account.get("Website")
            }
        
        # Lignes de produits si demandées
        if include_lines and "OpportunityLineItems" in sf_response:
            for idx, line in enumerate(sf_response["OpportunityLineItems"]):
                editable_line = {
                    "line_id": line.get("Id"),
                    "product_code": line.get("ProductCode"),
                    "product_name": line.get("Product2", {}).get("Name"),
                    "quantity": line.get("Quantity", 1),
                    "unit_price": line.get("UnitPrice", 0),
                    "total_price": line.get("TotalPrice", 0),
                    "description": line.get("Description", ""),
                    
                    # Métadonnées d'édition
                    "editable_fields": [
                        "quantity", "unit_price", "description"
                    ],
                    "validation": {
                        "min_quantity": 1,
                        "min_price": 0.01
                    }
                }
                
                editable_structure["lines"].append(editable_line)
        
        logger.info(f"Opportunité SF {opportunity_id} récupérée avec succès - {len(editable_structure['lines'])} produits")
        
        return {
            "success": True,
            "quote": editable_structure,
            "metadata": {
                "source": "Salesforce",
                "retrieved_at": datetime.now().isoformat(),
                "total_lines": len(editable_structure["lines"]),
                "editable_fields_count": count_editable_fields(editable_structure)
            }
        }
    
    except Exception as e:
        logger.error(f"Erreur Salesforce pour opportunité {opportunity_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur Salesforce: {str(e)}")

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
        # Structure adaptée selon le type de devis (SAP vs Salesforce)
        if quote_id.startswith("SAP-"):
            return get_sap_structure()
        elif quote_id.startswith("SF-"):
            return get_salesforce_structure()
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

def get_salesforce_structure() -> Dict[str, Any]:
    """Structure spécifique pour les opportunités Salesforce"""
    return {
        "success": True,
        "structure": {
            "sections": [
                {
                    "id": "header",
                    "title": "Informations opportunité",
                    "icon": "💼",
                    "fields": [
                        {"name": "name", "type": "text", "required": True, "label": "Nom de l'opportunité", "editable": True},
                        {"name": "close_date", "type": "date", "required": True, "label": "Date de clôture", "editable": True},
                        {"name": "stage", "type": "select", "required": True, "label": "Étape", "editable": True},
                        {"name": "probability", "type": "number", "required": False, "min": 0, "max": 100, "label": "Probabilité %", "editable": True},
                        {"name": "description", "type": "textarea", "required": False, "label": "Description", "editable": True}
                    ]
                }
            ]
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