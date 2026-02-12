# routes/routes_clients.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, validator
from typing import Dict, Any, Optional
import re
import time
from services.mcp_connector import MCPConnector


router = APIRouter()

class ClientCreationRequest(BaseModel):
    """Modèle pour la création de client"""
    company_name: str
    industry: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    annual_revenue: Optional[float] = None
    employees_count: Optional[int] = None
    description: Optional[str] = None
    
    # Adresse de facturation
    billing_street: Optional[str] = None
    billing_city: Optional[str] = None
    billing_state: Optional[str] = None
    billing_postal_code: Optional[str] = None
    billing_country: Optional[str] = None
    
    # Adresse de livraison (optionnelle)
    shipping_street: Optional[str] = None
    shipping_city: Optional[str] = None
    shipping_state: Optional[str] = None
    shipping_postal_code: Optional[str] = None
    shipping_country: Optional[str] = None
    
    # Paramètres de création
    create_in_sap: bool = True
    create_in_salesforce: bool = True
    
    @validator('company_name')
    def validate_company_name(cls, v):
        if not v or len(v.strip()) < 2:
            raise ValueError('Le nom de l\'entreprise doit contenir au moins 2 caractères')
        if len(v) > 100:
            raise ValueError('Le nom de l\'entreprise ne peut pas dépasser 100 caractères')
        return v.strip()
    
    @validator('phone')
    def validate_phone(cls, v):
        if v and not re.match(r'^[+]?[0-9\s\-\.\(\)]+$', v):
            raise ValueError('Format de téléphone invalide')
        return v
    
    @validator('email')
    def validate_email(cls, v):
        if v and not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', v):
            raise ValueError('Format d\'email invalide')
        return v
    
    @validator('billing_postal_code', 'shipping_postal_code')
    def validate_postal_code(cls, v):
        if v and not re.match(r'^[0-9]{5}$|^[0-9]{5}-[0-9]{4}$', v):
            raise ValueError('Format de code postal invalide')
        return v

class ClientValidationRequest(BaseModel):
    """Modèle pour la validation des données client avant création"""
    client_data: Dict[str, Any]

@router.post("/validate_client_data")
async def validate_client_data(request: ClientValidationRequest):
    """
    Valide les données client selon l'analyse des champs
    """
    try:
        # Utiliser l'analyseur de champs pour valider
        # Charger les exigences depuis l'analyse précédente ou faire une analyse rapide
        # Pour l'instant, utilisons des règles de base
        validation_result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "suggestions": []
        }
        
        # Validation des champs requis
        required_fields = ["company_name"]
        for field in required_fields:
            if not request.client_data.get(field):
                validation_result["valid"] = False
                validation_result["errors"].append(f"Champ requis manquant: {field}")
        
        # Validation des formats
        if request.client_data.get("email"):
            email = request.client_data["email"]
            if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
                validation_result["valid"] = False
                validation_result["errors"].append("Format d'email invalide")
        
        # Suggestions d'amélioration
        if not request.client_data.get("phone") and not request.client_data.get("email"):
            validation_result["warnings"].append("Aucune information de contact fournie")
            validation_result["suggestions"].append("Ajoutez un téléphone ou un email")
        
        if not request.client_data.get("billing_city"):
            validation_result["warnings"].append("Adresse de facturation incomplète")
        
        return validation_result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de validation: {str(e)}")

@router.post("/create_client")
async def create_client(request: ClientCreationRequest):
    """
    Crée un client dans Salesforce et/ou SAP selon les paramètres
    """
    try:
        results = {
            "status": "success",
            "client_data": {},
            "salesforce_result": None,
            "sap_result": None,
            "errors": [],
            "warnings": []
        }
        
        # 1. Créer le client dans Salesforce si demandé
        if request.create_in_salesforce:
            sf_result = await _create_salesforce_client(request)
            results["salesforce_result"] = sf_result
            
            if sf_result.get("success"):
                results["client_data"]["salesforce_id"] = sf_result.get("id")
                results["client_data"]["salesforce_name"] = sf_result.get("name")
            else:
                results["errors"].append(f"Erreur Salesforce: {sf_result.get('error')}")
        
        # 2. Créer le client dans SAP si demandé
        if request.create_in_sap:
            sap_result = await _create_sap_client(request, results["client_data"])
            results["sap_result"] = sap_result
            
            if sap_result.get("success"):
                results["client_data"]["sap_card_code"] = sap_result.get("card_code")
                results["client_data"]["sap_card_name"] = sap_result.get("card_name")
            else:
                results["errors"].append(f"Erreur SAP: {sap_result.get('error')}")
        
        # 3. Déterminer le statut global
        if results["errors"]:
            if results["salesforce_result"] and results["salesforce_result"].get("success"):
                results["status"] = "partial_success"
            elif results["sap_result"] and results["sap_result"].get("success"):
                results["status"] = "partial_success"
            else:
                results["status"] = "error"
        
        return results
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la création du client: {str(e)}")

async def _create_salesforce_client(request: ClientCreationRequest) -> Dict[str, Any]:
    """Crée un client dans Salesforce"""
    try:
        # Préparer les données Salesforce
        sf_data = {
            "Name": request.company_name,
            "Type": "Customer",
            "Industry": request.industry,
            "Phone": request.phone,
            "Website": request.website,
            "AnnualRevenue": request.annual_revenue,
            "NumberOfEmployees": request.employees_count,
            "Description": request.description,
        }
        
        # Adresse de facturation
        if request.billing_street:
            sf_data["BillingStreet"] = request.billing_street
        if request.billing_city:
            sf_data["BillingCity"] = request.billing_city
        if request.billing_state:
            sf_data["BillingState"] = request.billing_state
        if request.billing_postal_code:
            sf_data["BillingPostalCode"] = request.billing_postal_code
        if request.billing_country:
            sf_data["BillingCountry"] = request.billing_country
        
        # Adresse de livraison
        if request.shipping_street:
            sf_data["ShippingStreet"] = request.shipping_street
        if request.shipping_city:
            sf_data["ShippingCity"] = request.shipping_city
        if request.shipping_state:
            sf_data["ShippingState"] = request.shipping_state
        if request.shipping_postal_code:
            sf_data["ShippingPostalCode"] = request.shipping_postal_code
        if request.shipping_country:
            sf_data["ShippingCountry"] = request.shipping_country
        
        # Nettoyer les valeurs None
        sf_data = {k: v for k, v in sf_data.items() if v is not None}
        
        # Créer dans Salesforce
        result = await MCPConnector.call_salesforce_mcp("salesforce_create_record", {
            "sobject": "Account",
            "data": sf_data
        })
        
        if result.get("success"):
            return {
                "success": True,
                "id": result.get("id"),
                "name": request.company_name,
                "data": sf_data
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "Erreur inconnue lors de la création Salesforce")
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": f"Exception lors de la création Salesforce: {str(e)}"
        }

async def _create_sap_client(request: ClientCreationRequest, existing_client_data: Dict[str, Any]) -> Dict[str, Any]:
    """Crée un client dans SAP"""
    try:
        # Générer un CardCode unique
        clean_name = re.sub(r'[^a-zA-Z0-9]', '', request.company_name)[:8]
        timestamp = str(int(time.time()))[-4:]
        card_code = f"C{clean_name}{timestamp}".upper()[:15]
        
        # Préparer les données SAP
        sap_data = {
            "CardCode": card_code,
            "CardName": request.company_name,
            "CardType": "cCustomer",
            "GroupCode": 100,
            "Currency": "EUR",
            "Valid": "tYES",
            "Frozen": "tNO",
        }
        
        # Informations de contact
        if request.phone:
            sap_data["Phone1"] = request.phone[:20]
        if request.website:
            sap_data["Website"] = request.website[:100]
        if request.industry:
            sap_data["Industry"] = request.industry[:30]
        if request.description:
            sap_data["Notes"] = request.description[:254]
        
        # Adresse de facturation
        if request.billing_street:
            sap_data["BillToStreet"] = request.billing_street[:254]
        if request.billing_city:
            sap_data["BillToCity"] = request.billing_city[:100]
        if request.billing_state:
            sap_data["BillToState"] = request.billing_state[:100]
        if request.billing_postal_code:
            sap_data["BillToZipCode"] = request.billing_postal_code[:20]
        if request.billing_country:
            sap_data["BillToCountry"] = request.billing_country[:3]
        
        # Adresse de livraison (ou copie de facturation)
        sap_data["ShipToStreet"] = request.shipping_street or request.billing_street or ""
        sap_data["ShipToCity"] = request.shipping_city or request.billing_city or ""
        sap_data["ShipToState"] = request.shipping_state or request.billing_state or ""
        sap_data["ShipToZipCode"] = request.shipping_postal_code or request.billing_postal_code or ""
        sap_data["ShipToCountry"] = request.shipping_country or request.billing_country or ""
        
        # Référence croisée Salesforce
        if existing_client_data.get("salesforce_id"):
            sap_data["FederalTaxID"] = existing_client_data["salesforce_id"][:32]
        
        # Créer dans SAP
        result = await MCPConnector.call_sap_mcp("sap_create_customer_complete", {
            "customer_data": sap_data
        })
        
        if result.get("success"):
            return {
                "success": True,
                "card_code": card_code,
                "card_name": request.company_name,
                "created": result.get("created", True),
                "data": sap_data
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "Erreur inconnue lors de la création SAP")
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": f"Exception lors de la création SAP: {str(e)}"
        }

@router.get("/search_clients")
async def search_clients(q: str, source: str = "both", limit: int = 10):
    """
    Recherche de clients existants dans Salesforce et/ou SAP
    """
    try:
        results = {
            "query": q,
            "salesforce": [],
            "sap": [],
            "total": 0
        }
        
        if source in ["both", "salesforce"]:
            # Recherche Salesforce
            sf_query = f"SELECT Id, Name, AccountNumber, Phone, BillingCity, BillingCountry FROM Account WHERE Name LIKE '%{q}%' LIMIT {limit}"
            sf_result = await MCPConnector.call_salesforce_mcp("salesforce_query", {
                "query": sf_query
            })
            
            if "error" not in sf_result:
                results["salesforce"] = sf_result.get("records", [])
        
        if source in ["both", "sap"]:
            # Recherche SAP depuis cache SQLite local (ultra-rapide)
            from services.sap_cache_db import get_sap_cache_db
            cache_db = get_sap_cache_db()
            sap_clients = cache_db.search_clients(q, limit=limit)

            # Formater les résultats pour correspondre au format attendu
            results["sap"] = [
                {
                    "CardCode": client["CardCode"],
                    "CardName": client["CardName"],
                    "EmailAddress": client.get("EmailAddress"),
                    "Phone1": client.get("Phone1"),
                    "City": client.get("City"),
                    "Country": client.get("Country"),
                    "similarity": 100  # Score par défaut (TODO: implémenter scoring fuzzy)
                }
                for client in sap_clients
            ]
        
        results["total"] = len(results["salesforce"]) + len(results["sap"])

        # Format compatible avec le frontend (QuoteSummary.tsx attend {success, results})
        return {
            "success": True,
            "query": q,
            "results": results["sap"] + results["salesforce"],  # SAP en priorité
            "total": results["total"],
            "breakdown": {
                "sap": len(results["sap"]),
                "salesforce": len(results["salesforce"])
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la recherche: {str(e)}")

@router.get("/client_requirements")
async def get_client_requirements():
    """
    Retourne les exigences pour la création de clients basées sur l'analyse des champs
    """
    try:
        # Charger les exigences depuis l'analyse ou utiliser des valeurs par défaut
        requirements = {
            "required_fields": [
                {
                    "name": "company_name",
                    "label": "Nom de l'entreprise",
                    "type": "string",
                    "required": True,
                    "min_length": 2,
                    "max_length": 100
                }
            ],
            "recommended_fields": [
                {
                    "name": "phone",
                    "label": "Téléphone",
                    "type": "string",
                    "required": False,
                    "pattern": "^[+]?[0-9\\s\\-\\.\\(\\)]+$"
                },
                {
                    "name": "email",
                    "label": "Email",
                    "type": "email",
                    "required": False
                },
                {
                    "name": "billing_city",
                    "label": "Ville de facturation",
                    "type": "string",
                    "required": False
                }
            ],
            "optional_fields": [
                {
                    "name": "industry",
                    "label": "Secteur d'activité",
                    "type": "string",
                    "required": False
                },
                {
                    "name": "annual_revenue",
                    "label": "Chiffre d'affaires annuel",
                    "type": "number",
                    "required": False
                }
            ]
        }
        
        return requirements
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération des exigences: {str(e)}")

@router.get("/search_clients_advanced")
async def search_clients_advanced(q: str = "", limit: int =50):
    """
    Recherche de clients Salesforce pour l'interface avancée - VERSION CORRIGÉE
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Recherche clients avancée: q='{q}', limit={limit}")
    
    try:
        # Requête enrichie avec plus de champs et correction du tri
        if not q.strip():
            query = f"""
            SELECT Id, Name, BillingCity, BillingCountry, BillingState, Phone, Type, Industry, Symbol,
                   ShippingCity, ShippingCountry, AccountNumber, CreatedDate
            FROM Account 
            WHERE Name != null 
            ORDER BY Name ASC
            LIMIT {limit}
            """
        else:
            # Échapper correctement la recherche pour éviter les injections SOQL
            escaped_query = q.replace("'", "\\'").replace("\\", "\\\\")
            query = f"""
            SELECT Id, Name, BillingCity, BillingCountry, BillingState, Phone, Type, Industry,
                   ShippingCity, ShippingCountry, AccountNumber, CreatedDate
            FROM Account 
            WHERE Name LIKE '%{escaped_query}%' OR AccountNumber LIKE '%{escaped_query}%'
            ORDER BY Name ASC
            LIMIT {limit}
            """
        
        # Log de debugging pour la requête Salesforce
        logger.info(f"Requête SOQL: {query}")
        
        # Appel au connecteur MCP avec délai augmenté
        result = await MCPConnector.call_salesforce_mcp("salesforce_query", {
            "query": query
        })
        
        # Vérification d'erreur explicite
        if "error" in result:
            logger.error(f"Erreur Salesforce MCP: {result['error']}")
            return {"success": False, "error": result["error"], "clients": []}
        
        # Vérification des données reçues
        if "records" not in result:
            logger.error(f"Réponse Salesforce invalide: 'records' manquant. Réponse: {result}")
            return {"success": False, "error": "Format de réponse Salesforce invalide", "clients": []}
        
        # Log du nombre de résultats
        logger.info(f"Nombre de clients trouvés: {len(result.get('records', []))}")
        
        # Formatage amélioré avec gestion des valeurs nulles
        formatted_clients = []
        for record in result.get("records", []):
            # Extraction sécurisée des données avec valeurs par défaut
            client = {
                "id": record.get("Id", ""),
                "name": record.get("Name", "Client sans nom")
            }
            
            # Ne pas inclure un client sans ID ou sans nom
            if not client["id"] or not client["name"]:
                continue
                
            # Gestion intelligente de la localisation
            city = record.get("BillingCity") or record.get("ShippingCity") or ""
            country = record.get("BillingCountry") or record.get("ShippingCountry") or ""
            state = record.get("BillingState") or ""
            
            # Construction de l'affichage de localisation
            location_parts = []
            if city:
                location_parts.append(city)
            if state and country == "United States":
                location_parts.append(state)
            elif country:
                location_parts.append(country)
            
            # Type de client enrichi
            client_type = record.get("Type") or "Client standard"
            industry = record.get("Industry")
            
            # Compléter l'objet client
            client.update({
                "city": city,
                "country": country,
                "state": state,
                "phone": record.get("Phone", ""),
                "type": client_type,
                "industry": industry or "",
                "account_number": record.get("AccountNumber") or "",
                "location_display": " • ".join(location_parts) if location_parts else "Localisation non spécifiée",
                "type_display": f"{client_type} • {industry}" if industry else client_type,
                "created_date": record.get("CreatedDate", "")
            })
            
            formatted_clients.append(client)
        
        # Tri par ordre alphabétique si nécessaire
        formatted_clients.sort(key=lambda x: x["name"])
        
        return {
            "success": True,
            "clients": formatted_clients,
            "count": len(formatted_clients),
            "query": q,
            "debug_info": {
                "query_used": query,
                "salesforce_records": len(result.get("records", []))
            }
        }
        
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error(f"Exception dans search_clients_advanced: {str(e)}\n{tb}")
        return {"success": False, "error": str(e), "clients": []}