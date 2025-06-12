"""
API Routes pour la récupération détaillée des devis
Permet de récupérer le contenu complet d'un devis SAP/Salesforce pour édition
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import logging
from services.mcp_connector import MCPConnector

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
                detail=f"Format d'ID invalide: {quote_id}. Attendu: SAP-<DocEntry> ou SF-<OpportunityId>"
            )
    
    except Exception as e:
        logger.error(f"Erreur lors de la récupération du devis {quote_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur interne: {str(e)}")

async def get_sap_quote_details(
    doc_entry: str, 
    include_lines: bool = True, 
    include_customer: bool = True
) -> Dict[str, Any]:
    """
    Récupère les détails complets d'un devis SAP Business One
    """
    
    try:
        connector = MCPConnector()
        
        # Récupération du document SAP complet
        sap_request = {
            "tool": "get_quotation_details",
            "doc_entry": int(doc_entry),
            "include_lines": include_lines,
            "include_customer": include_customer
        }
        
        sap_response = await connector.call_mcp("sap_mcp", sap_request)
        
        if not sap_response.get("success", False):
            raise HTTPException(
                status_code=404,
                detail=f"Devis SAP {doc_entry} non trouvé ou erreur: {sap_response.get('error', 'Erreur inconnue')}"
            )
        
        # Structure la réponse pour l'édition
        quote_data = sap_response.get("quote", {})
        
        # Enrichissement avec métadonnées d'édition
        editable_structure = {
            "quote_id": f"SAP-{doc_entry}",
            "source_system": "SAP Business One",
            "editable": True,
            "last_updated": quote_data.get("UpdateDate"),
            
            # Informations header
            "header": {
                "doc_entry": quote_data.get("DocEntry"),
                "doc_num": quote_data.get("DocNum"), 
                "doc_date": quote_data.get("DocDate"),
                "doc_due_date": quote_data.get("DocDueDate"),
                "status": quote_data.get("DocumentStatus"),
                "remarks": quote_data.get("Comments", ""),
                "reference": quote_data.get("NumAtCard", ""),
                "sales_person": quote_data.get("SalesPersonCode"),
                "payment_terms": quote_data.get("PaymentGroupCode")
            },
            
            # Informations client
            "customer": {},
            
            # Lignes de produits
            "lines": [],
            
            # Totaux
            "totals": {
                "subtotal": quote_data.get("DocTotal", 0),
                "tax_total": quote_data.get("VatSum", 0),
                "total": quote_data.get("DocTotal", 0) + quote_data.get("VatSum", 0),
                "currency": quote_data.get("DocCurrency", "EUR")
            },
            
            # Métadonnées pour validation
            "validation_rules": {
                "can_modify_lines": True,
                "can_modify_pricing": True,
                "can_modify_customer": False,  # Généralement non modifiable
                "required_fields": ["DocDate", "CardCode", "Lines"]
            }
        }
        
        # Informations client si demandées
        if include_customer and "CardCode" in quote_data:
            editable_structure["customer"] = {
                "card_code": quote_data.get("CardCode"),
                "card_name": quote_data.get("CardName"),
                "contact_person": quote_data.get("ContactPersonCode"),
                "address": {
                    "bill_to": quote_data.get("Address"),
                    "ship_to": quote_data.get("Address2")
                },
                "phone": quote_data.get("Phone1"),
                "email": quote_data.get("EmailAddress")
            }
        
        # Lignes de produits si demandées
        if include_lines and "DocumentLines" in quote_data:
            for idx, line in enumerate(quote_data["DocumentLines"]):
                editable_line = {
                    "line_num": line.get("LineNum", idx),
                    "item_code": line.get("ItemCode"),
                    "item_description": line.get("ItemDescription"),
                    "quantity": line.get("Quantity", 1),
                    "unit_price": line.get("UnitPrice", 0),
                    "discount_percent": line.get("DiscountPercent", 0),
                    "line_total": line.get("LineTotal", 0),
                    "tax_code": line.get("TaxCode"),
                    "warehouse": line.get("WarehouseCode"),
                    "currency": line.get("Currency", "EUR"),
                    
                    # Métadonnées d'édition pour cette ligne
                    "editable_fields": [
                        "quantity", "unit_price", "discount_percent", 
                        "item_description", "warehouse"
                    ],
                    "validation": {
                        "min_quantity": 1,
                        "max_quantity": 999999,
                        "min_price": 0.01,
                        "max_discount": 100
                    }
                }
                
                editable_structure["lines"].append(editable_line)
        
        logger.info(f"Devis SAP {doc_entry} récupéré avec succès - {len(editable_structure['lines'])} lignes")
        
        return {
            "success": True,
            "quote": editable_structure,
            "metadata": {
                "source": "SAP Business One",
                "retrieved_at": "now",
                "total_lines": len(editable_structure["lines"]),
                "editable_fields_count": count_editable_fields(editable_structure)
            }
        }
    
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
        connector = MCPConnector()
        
        # Récupération de l'opportunité Salesforce complète
        sf_request = {
            "tool": "get_opportunity_details",
            "opportunity_id": opportunity_id,
            "include_products": include_lines,
            "include_account": include_customer
        }
        
        sf_response = await connector.call_mcp("salesforce_mcp", sf_request)
        
        if not sf_response.get("success", False):
            raise HTTPException(
                status_code=404,
                detail=f"Opportunité Salesforce {opportunity_id} non trouvée: {sf_response.get('error', 'Erreur inconnue')}"
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
                "currency": "EUR"  # À adapter selon Salesforce
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
                "retrieved_at": "now",
                "total_lines": len(editable_structure["lines"]),
                "editable_fields_count": count_editable_fields(editable_structure)
            }
        }
    
    except Exception as e:
        logger.error(f"Erreur Salesforce pour opportunité {opportunity_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur Salesforce: {str(e)}")

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
        # Pour l'instant, retourne une structure générique
        # TODO: Adapter selon le type de devis (SAP vs Salesforce)
        
        return {
            "success": True,
            "structure": {
                "sections": [
                    {
                        "id": "header",
                        "title": "Informations générales",
                        "fields": [
                            {"name": "doc_date", "type": "date", "required": True, "label": "Date du devis"},
                            {"name": "doc_due_date", "type": "date", "required": False, "label": "Date d'échéance"},
                            {"name": "remarks", "type": "textarea", "required": False, "label": "Commentaires"},
                            {"name": "reference", "type": "text", "required": False, "label": "Référence client"}
                        ]
                    },
                    {
                        "id": "customer",
                        "title": "Informations client",
                        "editable": False,
                        "fields": [
                            {"name": "card_name", "type": "text", "readonly": True, "label": "Nom du client"},
                            {"name": "phone", "type": "tel", "required": False, "label": "Téléphone"},
                            {"name": "email", "type": "email", "required": False, "label": "Email"}
                        ]
                    },
                    {
                        "id": "lines",
                        "title": "Lignes de produits",
                        "type": "array",
                        "can_add": True,
                        "can_remove": True,
                        "fields": [
                            {"name": "item_code", "type": "text", "required": True, "label": "Code produit"},
                            {"name": "item_description", "type": "text", "required": True, "label": "Description"},
                            {"name": "quantity", "type": "number", "required": True, "min": 1, "step": 1, "label": "Quantité"},
                            {"name": "unit_price", "type": "number", "required": True, "min": 0.01, "step": 0.01, "label": "Prix unitaire"},
                            {"name": "discount_percent", "type": "number", "required": False, "min": 0, "max": 100, "step": 0.01, "label": "Remise %"}
                        ]
                    }
                ]
            }
        }
    
    except Exception as e:
        logger.error(f"Erreur structure pour {quote_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")