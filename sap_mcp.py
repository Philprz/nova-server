# sap_mcp.py
from mcp.server.fastmcp import FastMCP
import os
import json
import httpx
import asyncio
from datetime import datetime
import sys
import io
from typing import Optional, Dict, Any, List
import traceback
import argparse

# Configuration de l'encodage pour Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Créer les dossiers nécessaires
os.makedirs("logs", exist_ok=True)
os.makedirs("cache", exist_ok=True)
log_file = open("logs/sap_mcp.log", "w", encoding="utf-8")

# Journalisation
def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_message = f"[{timestamp}] {message}"
    log_file.write(f"{formatted_message}\n")
    log_file.flush()
    print(formatted_message)

log("Démarrage du serveur MCP SAP...")

# Création du serveur MCP
mcp = FastMCP("sap_mcp")

# Charger les variables d'environnement
from dotenv import load_dotenv
load_dotenv()

# Configuration SAP
SAP_BASE_URL = os.getenv("SAP_REST_BASE_URL")
SAP_USER = os.getenv("SAP_USER")
SAP_CLIENT_PASSWORD = os.getenv("SAP_CLIENT_PASSWORD")
SAP_CLIENT = os.getenv("SAP_CLIENT")

# Cache pour les métadonnées SAP
CACHE_FILE = "cache/metadata_sap.json"

# Session SAP partagée
sap_session = {"cookies": None, "expires": None}

def load_cache():
    """Charge le cache des métadonnées SAP"""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log(f"Erreur lors du chargement du cache: {str(e)}")
    return {}

def save_cache(data):
    """Enregistre le cache des métadonnées SAP"""
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log(f"Erreur lors de l'enregistrement du cache: {str(e)}")

async def login_sap():
    """Authentification à SAP B1"""
    url = SAP_BASE_URL + "/Login"
    auth_payload = {
        "UserName": SAP_USER,
        "Password": SAP_CLIENT_PASSWORD,
        "CompanyDB": SAP_CLIENT
    }
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        log(f"Connexion à SAP {SAP_BASE_URL}...")
        
        async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
            response = await client.post(url, json=auth_payload, headers=headers)
            response.raise_for_status()
            
            sap_session["cookies"] = response.cookies
            sap_session["expires"] = datetime.utcnow().timestamp() + 60 * 20  # 20 minutes
            
            log("✅ Connexion SAP établie avec succès")
            return True
    except Exception as e:
        log(f"❌ Erreur de connexion SAP: {str(e)}")
        return False

async def call_sap(endpoint: str, method="GET", payload: Optional[Dict[str, Any]] = None):
    """Appel à l'API REST SAP B1"""
    # Vérifier et rafraîchir la session si nécessaire
    if not sap_session["cookies"] or datetime.utcnow().timestamp() > sap_session["expires"]:
        if not await login_sap():
            return {"error": "Impossible de se connecter à SAP"}
    
    try:
        url = SAP_BASE_URL + endpoint
        
        async with httpx.AsyncClient(cookies=sap_session["cookies"], verify=False, timeout=30.0) as client:
            if method == "GET":
                response = await client.get(url)
            else:
                response = await client.post(url, json=payload or {})
            
            response.raise_for_status()
            
            if response.status_code == 204:  # No Content
                return {"status": "success", "message": "Opération réussie"}
            
            return response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            # Session expirée, tenter de se reconnecter
            log("Session SAP expirée, reconnexion...")
            
            if await login_sap():
                return await call_sap(endpoint, method, payload)
            
        log(f"Erreur HTTP lors de l'appel à {endpoint}: {str(e)}")
        
        try:
            # Tenter de récupérer le message d'erreur SAP
            error_msg = e.response.json()
            return {"error": error_msg}
        except:
            return {"error": f"Erreur HTTP {e.response.status_code}: {str(e)}"}
    except Exception as e:
        log(f"Erreur lors de l'appel à {endpoint}: {str(e)}")
        return {"error": str(e)}

async def fetch_sap_metadata():
    """Récupère les métadonnées SAP"""
    try:
        # Tenter d'utiliser l'endpoint standard OData
        try:
            metadata = await call_sap("/$metadata")
            log("Métadonnées récupérées via /$metadata")
        except:
            # Si ça échoue, essayer une approche alternative
            log("Impossible d'utiliser /$metadata, utilisation d'une stratégie alternative")
            
            # Récupérer un échantillon de données pour quelques endpoints clés
            endpoints_to_test = ["/Items", "/BusinessPartners", "/Orders", "/Invoices"]
            metadata = {"value": []}
            
            for endpoint in endpoints_to_test:
                try:
                    result = await call_sap(endpoint + "?$top=1")
                    if "value" in result and result["value"]:
                        # Récupérer les champs du premier élément
                        fields = list(result["value"][0].keys())
                        metadata["value"].append({
                            "name": endpoint.strip("/"),
                            "fields": fields
                        })
                except Exception as inner_e:
                    log(f"Impossible de récupérer des métadonnées pour {endpoint}: {str(inner_e)}")
        
        # Formatter les métadonnées
        schema = {
            "endpoints": [
                {
                    "name": "Items",
                    "path": "/Items",
                    "description": "Produits/articles",
                    "fields": []
                },
                {
                    "name": "BusinessPartners",
                    "path": "/BusinessPartners",
                    "description": "Partenaires commerciaux (clients, fournisseurs)",
                    "fields": []
                },
                {
                    "name": "Orders",
                    "path": "/Orders",
                    "description": "Commandes clients",
                    "fields": []
                },
                {
                    "name": "Invoices",
                    "path": "/Invoices",
                    "description": "Factures",
                    "fields": []
                },
                {
                    "name": "StockTransfers",
                    "path": "/StockTransfers",
                    "description": "Transferts de stock",
                    "fields": []
                },
                {
                    "name": "InventoryGenEntries",
                    "path": "/InventoryGenEntries",
                    "description": "Entrées de stock",
                    "fields": []
                },
                {
                    "name": "InventoryGenExits",
                    "path": "/InventoryGenExits",
                    "description": "Sorties de stock",
                    "fields": []
                }
            ],
            "update_time": datetime.utcnow().isoformat()
        }
        
        # Enrichir avec les champs découverts
        if "value" in metadata:
            for endpoint_data in metadata["value"]:
                for endpoint in schema["endpoints"]:
                    if endpoint["name"] == endpoint_data["name"]:
                        endpoint["fields"] = endpoint_data.get("fields", [])
        
        # Sauvegarder dans le cache
        save_cache(schema)
        return schema
    except Exception as e:
        log(f"Erreur lors de la récupération des métadonnées SAP: {str(e)}")
        
        # Fallback: liste manuelle d'endpoints courants
        schema = {
            "endpoints": [
                {
                    "name": "Items",
                    "path": "/Items",
                    "description": "Produits/articles"
                },
                {
                    "name": "BusinessPartners",
                    "path": "/BusinessPartners",
                    "description": "Partenaires commerciaux (clients, fournisseurs)"
                },
                {
                    "name": "Orders",
                    "path": "/Orders",
                    "description": "Commandes clients"
                },
                {
                    "name": "Invoices",
                    "path": "/Invoices",
                    "description": "Factures"
                },
                {
                    "name": "StockTransfers",
                    "path": "/StockTransfers",
                    "description": "Transferts de stock"
                },
                {
                    "name": "InventoryGenEntries",
                    "path": "/InventoryGenEntries",
                    "description": "Entrées de stock"
                },
                {
                    "name": "InventoryGenExits",
                    "path": "/InventoryGenExits",
                    "description": "Sorties de stock"
                }
            ],
            "update_time": datetime.utcnow().isoformat(),
            "note": "Liste manuelle des endpoints (échec de la récupération automatique)"
        }
        
        # Sauvegarder dans le cache
        save_cache(schema)
        return schema

# Outils MCP
@mcp.tool(name="ping")
def ping() -> str:
    """Test simple de disponibilité du serveur MCP SAP"""
    log("Ping reçu!")
    return "pong! Serveur MCP SAP opérationnel"

@mcp.tool(name="sap_read")
async def sap_read(endpoint: str, method: str = "GET", payload: Optional[Dict[str, Any]] = None) -> dict:
    """
    Lecture de données SAP B1 via l'API REST.
    
    Args:
        endpoint: Endpoint SAP à appeler (ex: "/Items")
        method: Méthode HTTP à utiliser (GET par défaut)
        payload: Données à envoyer (pour POST)
        
    Returns:
        Un dictionnaire contenant les résultats ou une erreur
    """
    try:
        log(f"Lecture SAP: {method} {endpoint}")
        start_time = datetime.now()
        result = await call_sap(endpoint, method, payload)
        end_time = datetime.now()
        
        # Ajouter des métadonnées utiles
        if isinstance(result, dict) and "error" not in result:
            result["_metadata"] = {
                "query_time_ms": (end_time - start_time).total_seconds() * 1000,
                "endpoint": endpoint,
                "method": method
            }
        
        if "value" in result:
            log(f"Lecture réussie - {len(result['value'])} résultats")
        else:
            log(f"Lecture réussie - réponse sans liste 'value'")
        
        return result
    except Exception as e:
        log(f"Erreur lors de l'appel à l'API SAP: {str(e)}")
        return {"error": str(e)}

@mcp.tool(name="sap_inspect")
async def sap_inspect() -> dict:
    """
    Liste les endpoints SAP depuis le cache.
    
    Returns:
        Un dictionnaire contenant les endpoints disponibles ou une erreur
    """
    try:
        log("Inspection des endpoints SAP")
        cache = load_cache()
        
        if not cache or "endpoints" not in cache:
            # Cache vide ou invalide, utiliser les données par défaut
            log("Cache SAP vide ou invalide, utilisation de valeurs par défaut")
            return {
                "endpoints": [
                    {"name": "Items", "path": "/Items"},
                    {"name": "BusinessPartners", "path": "/BusinessPartners"},
                    {"name": "Orders", "path": "/Orders"},
                    {"name": "Invoices", "path": "/Invoices"}
                ],
                "note": "Données par défaut (cache non disponible)",
                "update_time": datetime.utcnow().isoformat()
            }
        
        log(f"Inspection réussie - {len(cache.get('endpoints', []))} endpoints disponibles")
        return cache
    except Exception as e:
        log(f"Erreur lors de l'inspection SAP: {str(e)}")
        return {"error": str(e)}

@mcp.tool(name="sap_refresh_metadata")
async def sap_refresh_metadata() -> dict:
    """
    Force la mise à jour des endpoints SAP.
    
    Returns:
        Un dictionnaire contenant le résultat de l'opération
    """
    try:
        log("Rafraîchissement des métadonnées SAP")
        start_time = datetime.now()
        schema = await fetch_sap_metadata()
        end_time = datetime.now()
        
        return {
            "status": "ok",
            "endpoints_count": len(schema.get("endpoints", [])),
            "refresh_time_ms": (end_time - start_time).total_seconds() * 1000,
            "update_time": schema.get("update_time")
        }
    except Exception as e:
        log(f"Erreur lors du rafraîchissement des métadonnées SAP: {str(e)}")
        return {"error": str(e)}

@mcp.tool(name="sap_search")
async def sap_search(query: str, entity_type: str = "Items", limit: int = 5) -> dict:
    """
    Recherche dans SAP.
    
    Args:
        query: Texte à rechercher
        entity_type: Type d'entité à rechercher (Items, BusinessPartners, etc.)
        limit: Nombre maximal de résultats
        
    Returns:
        Un dictionnaire contenant les résultats de la recherche
    """
    try:
        log(f"Recherche SAP: {query} dans {entity_type}")
        
        # Déterminer le bon champ pour la recherche
        search_field = ""
        if entity_type == "Items":
            search_field = "ItemName"
        elif entity_type == "BusinessPartners":
            search_field = "CardName"
        elif entity_type == "Orders":
            search_field = "DocNum"
        elif entity_type == "Invoices":
            search_field = "DocNum"
        else:
            search_field = "Name"
        
        # Construire la requête
        endpoint = f"/{entity_type}?$filter=contains({search_field},'{query}')&$top={limit}"
        
        result = await call_sap(endpoint)
        
        if "value" in result:
            log(f"Recherche réussie - {len(result['value'])} résultats")
            return {
                "query": query,
                "entity_type": entity_type,
                "results": result["value"],
                "count": len(result["value"])
            }
        else:
            log("Recherche réussie - aucun résultat ou format inattendu")
            return {
                "query": query,
                "entity_type": entity_type,
                "results": [],
                "count": 0,
                "raw_response": result
            }
    except Exception as e:
        log(f"Erreur lors de la recherche SAP: {str(e)}")
        return {"error": str(e)}

@mcp.tool(name="sap_get_product_details")
async def sap_get_product_details(item_code: str) -> dict:
    """
    Récupère les détails d'un produit.
    
    Args:
        item_code: Code du produit
        
    Returns:
        Un dictionnaire contenant les détails du produit
    """
    try:
        log(f"Récupération des détails du produit {item_code}")
        
        # Récupérer les informations de base du produit
        product = await call_sap(f"/Items('{item_code}')")
        
        if "error" in product:
            log(f"Erreur lors de la récupération du produit {item_code}: {product['error']}")
            return product
        
        # Récupérer le stock disponible
        try:
            inventory = await call_sap(f"/Items('{item_code}')/InventoryPostingItem")
            warehouses = []
            
            if "value" in inventory:
                warehouses = inventory["value"]
            
            # Calculer le stock total
            total_stock = sum(w.get("QuantityOnStock", 0) for w in warehouses)
            
            product["stock"] = {
                "total": total_stock,
                "warehouses": warehouses
            }
        except Exception as stock_error:
            log(f"Erreur lors de la récupération du stock pour {item_code}: {str(stock_error)}")
            product["stock"] = {"error": str(stock_error)}
        
        # Récupérer les prix
        try:
            prices = await call_sap(f"/Items('{item_code}')/ItemPrices")
            
            if "value" in prices:
                product["prices"] = prices["value"]
            else:
                product["prices"] = []
        except Exception as price_error:
            log(f"Erreur lors de la récupération des prix pour {item_code}: {str(price_error)}")
            product["prices"] = {"error": str(price_error)}
        
        log(f"Détails du produit {item_code} récupérés avec succès")
        return product
    except Exception as e:
        log(f"Erreur lors de la récupération des détails du produit {item_code}: {str(e)}")
        return {"error": str(e)}

@mcp.tool(name="sap_check_product_availability")
async def sap_check_product_availability(item_code: str, quantity: int = 1) -> dict:
    """
    Vérifie la disponibilité d'un produit.
    
    Args:
        item_code: Code du produit
        quantity: Quantité demandée
        
    Returns:
        Un dictionnaire contenant les informations de disponibilité
    """
    try:
        log(f"Vérification de la disponibilité du produit {item_code} (quantité: {quantity})")
        
        # Récupérer le stock
        product = await get_product_details(item_code)
        
        if "error" in product:
            return product
        
        stock = product.get("stock", {})
        total_stock = stock.get("total", 0)
        
        # Vérifier la disponibilité
        is_available = total_stock >= quantity
        
        # Calculer le délai estimé si non disponible
        estimated_delay = None
        if not is_available:
            # Cette logique pourrait être plus complexe dans un système réel
            # Par exemple, vérifier les commandes fournisseurs en cours
            if total_stock > 0:
                estimated_delay = "1-2 semaines"
            else:
                estimated_delay = "3-4 semaines"
        
        result = {
            "item_code": item_code,
            "item_name": product.get("ItemName", ""),
            "requested_quantity": quantity,
            "available_quantity": total_stock,
            "is_available": is_available,
            "estimated_delay": estimated_delay if not is_available else None,
            "warehouses": stock.get("warehouses", [])
        }
        
        log(f"Vérification de disponibilité terminée pour {item_code}: {'disponible' if is_available else 'non disponible'}")
        return result
    except Exception as e:
        log(f"Erreur lors de la vérification de disponibilité pour {item_code}: {str(e)}")
        return {"error": str(e)}

@mcp.tool(name="sap_find_alternatives")
async def sap_find_alternatives(item_code: str) -> dict:
    """
    Trouve des produits alternatifs pour un produit donné.
    
    Args:
        item_code: Code du produit
        
    Returns:
        Un dictionnaire contenant les produits alternatifs
    """
    try:
        log(f"Recherche d'alternatives pour le produit {item_code}")
        
        # Récupérer les informations du produit
        product = await sap_get_product_details(item_code)
        
        if "error" in product:
            return product
        
        item_name = product.get("ItemName", "")
        item_group = product.get("ItemsGroupCode")
        
        # Stratégie 1: Rechercher par groupe d'articles
        alternatives = []
        
        if item_group:
            group_query = await call_sap(f"/Items?$filter=ItemsGroupCode eq {item_group} and ItemCode ne '{item_code}'&$top=5")
            
            if "value" in group_query:
                alternatives.extend(group_query["value"])
        
        # Stratégie 2: Rechercher par nom similaire si pas assez d'alternatives
        if len(alternatives) < 3 and item_name:
            # Extraire les mots clés du nom
            words = item_name.split()
            if len(words) > 1:
                # Utiliser le mot le plus long comme terme de recherche
                search_term = max(words, key=len)
                
                name_query = await call_sap(f"/Items?$filter=contains(ItemName,'{search_term}') and ItemCode ne '{item_code}'&$top=5")
                
                if "value" in name_query:
                    # Ajouter uniquement les articles qui ne sont pas déjà dans les alternatives
                    existing_codes = [alt["ItemCode"] for alt in alternatives]
                    for item in name_query["value"]:
                        if item["ItemCode"] not in existing_codes:
                            alternatives.append(item)
        
        # Simplifier la réponse
        simplified_alternatives = []
        for alt in alternatives[:5]:  # Limiter à 5 alternatives
            # Récupérer le stock
            try:
                inventory = await call_sap(f"/Items('{alt['ItemCode']}')/InventoryPostingItem")
                total_stock = 0
                
                if "value" in inventory:
                    total_stock = sum(w.get("QuantityOnStock", 0) for w in inventory["value"])
            except:
                total_stock = "N/A"
            
            simplified_alternatives.append({
                "ItemCode": alt.get("ItemCode"),
                "ItemName": alt.get("ItemName"),
                "Price": alt.get("Price"),
                "Stock": total_stock
            })
        
        result = {
            "original_item": {
                "ItemCode": item_code,
                "ItemName": item_name,
                "Price": product.get("Price"),
                "Stock": product.get("stock", {}).get("total", 0)
            },
            "alternatives": simplified_alternatives,
            "count": len(simplified_alternatives)
        }
        
        log(f"Alternatives trouvées pour {item_code}: {len(simplified_alternatives)}")
        return result
    except Exception as e:
        log(f"Erreur lors de la recherche d'alternatives pour {item_code}: {str(e)}")
        return {"error": str(e)}

@mcp.tool(name="sap_create_draft_order")
async def sap_create_draft_order(customer_code: str, items: List[Dict[str, Any]]) -> dict:
    """
    Crée un brouillon de commande dans SAP.
    
    Args:
        customer_code: Code du client
        items: Liste des articles de la commande (format: [{"ItemCode": "X", "Quantity": Y, "Price": Z}])
        
    Returns:
        Un dictionnaire contenant le résultat de l'opération
    """
    try:
        log(f"Création d'un brouillon de commande pour le client {customer_code}")
        
        # Vérifier que le client existe
        customer = await call_sap(f"/BusinessPartners('{customer_code}')")
        
        if "error" in customer:
            log(f"Client {customer_code} non trouvé: {customer['error']}")
            return {"error": f"Client non trouvé: {customer_code}"}
        
        # Vérifier la disponibilité des articles
        unavailable_items = []
        for item in items:
            availability = await sap_check_product_availability(item["ItemCode"], item.get("Quantity", 1))
            if "error" in availability or not availability.get("is_available", False):
                unavailable_items.append({
                    "ItemCode": item["ItemCode"],
                    "Quantity": item.get("Quantity", 1),
                    "Available": availability.get("available_quantity", 0),
                    "Reason": availability.get("error", "Stock insuffisant")
                })
        
        # Préparer la commande
        order_data = {
            "CardCode": customer_code,
            "DocDueDate": datetime.now().strftime("%Y-%m-%d"),
            "DocumentLines": [
                {
                    "ItemCode": item["ItemCode"],
                    "Quantity": item.get("Quantity", 1),
                    "Price": item.get("Price")
                }
                for item in items
            ]
        }
        
        # Si mode brouillon, ne pas envoyer à SAP mais simuler
        result = {
            "status": "draft",
            "customer": {
                "CardCode": customer_code,
                "CardName": customer.get("CardName", "")
            },
            "items": [
                {
                    "ItemCode": item["ItemCode"],
                    "Quantity": item.get("Quantity", 1),
                    "Price": item.get("Price"),
                    "LineTotal": item.get("Quantity", 1) * (item.get("Price") or 0)
                }
                for item in items
            ],
            "unavailable_items": unavailable_items,
            "creation_time": datetime.now().isoformat(),
            "document_total": sum(item.get("Quantity", 1) * (item.get("Price") or 0) for item in items)
        }
        
        # Dans un environnement réel, vous pourriez appeler:
        # actual_result = await call_sap("/Orders", "POST", order_data)
        
        log(f"Brouillon de commande créé pour {customer_code} avec {len(items)} articles")
        
        if unavailable_items:
            log(f"⚠️ {len(unavailable_items)} articles indisponibles dans la commande")
            
        return result
    except Exception as e:
        log(f"Erreur lors de la création du brouillon de commande: {str(e)}")
        return {"error": str(e)}

# Tentative d'initialisation au démarrage
async def init_sap():
    """Initialisation de la connexion SAP"""
    await login_sap()
# Table de mappage des noms d'outils MCP vers les fonctions correspondantes
mcp_functions = {
    "ping": ping,
    "sap_read": sap_read,
    "sap_inspect": sap_inspect,
    "sap_refresh_metadata": sap_refresh_metadata,
    "sap_search": sap_search,
    "sap_get_product_details": sap_get_product_details,
    "sap_check_product_availability": sap_check_product_availability,
    "sap_find_alternatives": sap_find_alternatives,
    "sap_create_draft_order": sap_create_draft_order
}

# Traitement des arguments en ligne de commande
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-file", help="Fichier d'entrée JSON")
    parser.add_argument("--output-file", help="Fichier de sortie JSON")
    args, unknown = parser.parse_known_args()
    
    if args.input_file and args.output_file:
        with open(args.input_file, 'r') as f:
            input_data = json.load(f)
        
        action = input_data.get("action")
        params = input_data.get("params", {})
        
        # Utiliser la table de mappage
        if action in mcp_functions:
            try:
                result = asyncio.run(mcp_functions[action](**params))
                # Écrire résultat
                with open(args.output_file, 'w') as f:
                    json.dump(result, f)
                sys.exit(0)
            except Exception as e:
                log(f"Erreur lors de l'exécution de {action}: {str(e)}")
                with open(args.output_file, 'w') as f:
                    json.dump({"error": str(e)}, f)
                sys.exit(1)
        else:
            log(f"Action inconnue: {action}. Actions disponibles: {list(mcp_functions.keys())}")
            with open(args.output_file, 'w') as f:
                json.dump({"error": f"Action inconnue: {action}"}, f)
            sys.exit(1)

    # Cette partie reste inchangée
    try:
        log("Lancement du serveur MCP SAP...")
        mcp.run(transport="stdio")
    except KeyboardInterrupt:
        log("Arrêt du serveur MCP SAP par l'utilisateur")
    except Exception as e:
        log(f"Erreur fatale du serveur MCP SAP: {str(e)}")
        log(traceback.format_exc())
