# sap_mcp.py - VERSION CORRIGÉE POUR CRÉATION RÉELLE CLIENT ET DEVIS

from mcp.server.fastmcp import FastMCP
import os
import json
import httpx
import asyncio
from datetime import datetime, timedelta
import sys
import io
from typing import Optional, Dict, Any
import traceback
import argparse
from dotenv import load_dotenv
# Configuration de l'encodage pour Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Créer les dossiers nécessaires
os.makedirs("logs", exist_ok=True)
os.makedirs("cache", exist_ok=True)
log_file = open("logs/sap_mcp.log", "w", encoding="utf-8")

# Journalisation améliorée
def log(message, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_message = f"[{timestamp}] [{level}] {message}"
    log_file.write(f"{formatted_message}\n")
    log_file.flush()
    print(formatted_message)

log("Démarrage du serveur MCP SAP - VERSION PRODUCTION", "STARTUP")

# Création du serveur MCP
mcp = FastMCP("sap_mcp")

# Charger les variables d'environnement

load_dotenv()

# Configuration SAP
SAP_BASE_URL = os.getenv("SAP_REST_BASE_URL")
SAP_USER = os.getenv("SAP_USER")
SAP_CLIENT_PASSWORD = os.getenv("SAP_CLIENT_PASSWORD")
SAP_CLIENT = os.getenv("SAP_CLIENT")

# Validation de la configuration
if not all([SAP_BASE_URL, SAP_USER, SAP_CLIENT_PASSWORD, SAP_CLIENT]):
    log("ERREUR: Configuration SAP incomplète dans .env", "ERROR")
    log(f"SAP_BASE_URL: {'✓' if SAP_BASE_URL else '✗'}", "ERROR")
    log(f"SAP_USER: {'✓' if SAP_USER else '✗'}", "ERROR")
    log(f"SAP_CLIENT_PASSWORD: {'✓' if SAP_CLIENT_PASSWORD else '✗'}", "ERROR")
    log(f"SAP_CLIENT: {'✓' if SAP_CLIENT else '✗'}", "ERROR")

# Session SAP partagée
sap_session = {"cookies": None, "expires": None}

# Correction à apporter dans sap_mcp.py
# Remplacer la section de gestion des cookies (lignes 85-95 environ)

async def login_sap():
    """Authentification à SAP B1 avec gestion d'erreurs renforcée"""
    url = SAP_BASE_URL + "/Login"
    auth_payload = {
        "UserName": SAP_USER,
        "Password": SAP_CLIENT_PASSWORD,
        "CompanyDB": SAP_CLIENT
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    try:
        log(f"Tentative de connexion à SAP: {SAP_BASE_URL}")
        log(f"Utilisateur: {SAP_USER}, Base: {SAP_CLIENT}")
        
        async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
            response = await client.post(url, json=auth_payload, headers=headers)
            
            # Log des détails de la réponse
            log(f"Statut de connexion SAP: {response.status_code}")
            log(f"Headers de réponse: {dict(response.headers)}")
            
            if response.status_code == 200:
                sap_session["cookies"] = response.cookies
                sap_session["expires"] = datetime.utcnow().timestamp() + 60 * 20  # 20 minutes
                
                # CORRECTION ICI : Vérifier que nous avons bien reçu les cookies de session
                session_id = None
                
                # Méthode corrigée pour itérer sur les cookies
                for cookie_name, cookie_value in response.cookies.items():
                    if 'B1SESSION' in cookie_name:
                        session_id = cookie_value
                        break
                
                # Alternative si la méthode ci-dessus ne fonctionne pas
                if not session_id:
                    # Chercher dans les headers Set-Cookie
                    set_cookie_header = response.headers.get('set-cookie', '')
                    if 'B1SESSION' in set_cookie_header:
                        # Extraire l'ID de session du header
                        import re
                        match = re.search(r'B1SESSION=([^;]+)', set_cookie_header)
                        if match:
                            session_id = match.group(1)
                
                if session_id:
                    log(f"✅ Connexion SAP réussie - Session ID: {session_id[:10]}...", "SUCCESS")
                    return True
                else:
                    log("⚠️ Connexion SAP sans session ID valide", "WARNING")
                    log(f"Cookies reçus: {dict(response.cookies)}", "DEBUG")
                    return False
            else:
                error_text = response.text
                log(f"❌ Échec connexion SAP - Code: {response.status_code}", "ERROR")
                log(f"Réponse: {error_text}", "ERROR")
                return False
                
    except httpx.TimeoutException:
        log("❌ Timeout lors de la connexion SAP", "ERROR")
        return False
    except Exception as e:
        log(f"❌ Erreur connexion SAP: {str(e)}", "ERROR")
        log(f"Traceback: {traceback.format_exc()}", "DEBUG")
        return False

async def call_sap(endpoint: str, method="GET", payload: Optional[Dict[str, Any]] = None):
    """Appel à l'API REST SAP B1 avec gestion d'erreurs renforcée"""
    # Vérifier et rafraîchir la session si nécessaire
    if not sap_session["cookies"] or datetime.utcnow().timestamp() > sap_session["expires"]:
        log("Session SAP expirée ou inexistante, reconnexion...")
        if not await login_sap():
            return {"error": "Impossible de se connecter à SAP"}
    
    try:
        url = SAP_BASE_URL + endpoint
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        log(f"Appel SAP: {method} {endpoint}")
        if payload:
            log(f"Payload: {json.dumps(payload, indent=2)}", "DEBUG")
        
        async with httpx.AsyncClient(cookies=sap_session["cookies"], verify=False, timeout=60.0) as client:
            if method.upper() == "GET":
                response = await client.get(url, headers=headers)
            elif method.upper() == "POST":
                response = await client.post(url, json=payload, headers=headers)
            elif method.upper() == "PUT":
                response = await client.put(url, json=payload, headers=headers)
            elif method.upper() == "DELETE":
                response = await client.delete(url, headers=headers)
            else:
                return {"error": f"Méthode HTTP non supportée: {method}"}
            
            log(f"Réponse SAP: {response.status_code}")
            
            if response.status_code == 401:
                # Session expirée, tenter de se reconnecter
                log("Session SAP expirée (401), reconnexion...")
                if await login_sap():
                    return await call_sap(endpoint, method, payload)
                else:
                    return {"error": "Impossible de renouveler la session SAP"}
            
            if response.status_code in [200, 201]:
                if response.status_code == 201:
                    log("✅ Ressource créée avec succès dans SAP", "SUCCESS")
                
                # Vérifier si la réponse contient du JSON
                content_type = response.headers.get("content-type", "")
                if "application/json" in content_type:
                    result = response.json()
                    log(f"Réponse JSON reçue: {len(str(result))} caractères")
                    return result
                else:
                    log("Réponse non-JSON reçue")
                    return {"status": "success", "message": "Opération réussie"}
            
            elif response.status_code == 204:
                log("✅ Opération réussie (204 No Content)", "SUCCESS")
                return {"status": "success", "message": "Opération réussie"}
            
            else:
                # Gérer les erreurs
                error_text = response.text
                log(f"❌ Erreur SAP {response.status_code}: {error_text}", "ERROR")
                
                try:
                    error_json = response.json()
                    return {"error": error_json}
                except Exception:
                    return {"error": f"Erreur HTTP {response.status_code}: {error_text}"}
                    
    except httpx.TimeoutException:
        log(f"❌ Timeout lors de l'appel à {endpoint}", "ERROR")
        return {"error": f"Timeout lors de l'appel à {endpoint}"}
    except Exception as e:
        log(f"❌ Erreur lors de l'appel à {endpoint}: {str(e)}", "ERROR")
        log(f"Traceback: {traceback.format_exc()}", "DEBUG")
        return {"error": str(e)}

# Outils MCP corrigés

@mcp.tool(name="ping")
async def ping() -> str:
    """Test simple de disponibilité du serveur MCP SAP"""
    log("Ping reçu!")
    return "pong! Serveur MCP SAP opérationnel - VERSION PRODUCTION"

@mcp.tool(name="sap_create_customer_complete")
async def sap_create_customer_complete(customer_data: Dict[str, Any]) -> dict:
    """
    Crée un client dans SAP avec toutes les données fournies.
    
    Args:
        customer_data: Dictionnaire contenant toutes les données du client
        
    Returns:
        Résultat de la création
    """
    try:
        log(f"Création client SAP avec données complètes: {customer_data.get('CardName', 'Nom manquant')}")
        
        # Validation des données minimales requises
        if not customer_data.get("CardCode"):
            return {"success": False, "error": "CardCode manquant"}
        if not customer_data.get("CardName"):
            return {"success": False, "error": "CardName manquant"}
        
        # Vérifier si le client existe déjà
        existing_check = await call_sap(f"/BusinessPartners('{customer_data['CardCode']}')")
        if "error" not in existing_check:
            log(f"Client {customer_data['CardCode']} existe déjà")
            return {"success": True, "data": existing_check, "created": False}
        
        # Nettoyer et valider les données
        clean_data = {}
        for key, value in customer_data.items():
            if value is not None and value != "":
                if isinstance(value, str):
                    clean_data[key] = value.strip()
                else:
                    clean_data[key] = value
        
        log(f"Données nettoyées: {json.dumps(clean_data, indent=2)}", "DEBUG")
        
        # Créer le client
        result = await call_sap("/BusinessPartners", "POST", clean_data)
        
        if "error" in result:
            log(f"❌ Erreur création client: {result['error']}", "ERROR")
            return {"success": False, "error": result["error"]}
        
        log(f"✅ Client créé avec succès: {customer_data['CardCode']}", "SUCCESS")
        
        # Vérifier la création
        verify_result = await call_sap(f"/BusinessPartners('{customer_data['CardCode']}')")
        if "error" not in verify_result:
            return {"success": True, "data": verify_result, "created": True}
        else:
            return {"success": True, "data": result, "created": True}
            
    except Exception as e:
        log(f"❌ Exception lors de la création du client: {str(e)}", "ERROR")
        return {"success": False, "error": str(e)}

@mcp.tool(name="sap_create_quotation_complete")
async def sap_create_quotation_complete(quotation_data: Dict[str, Any]) -> dict:
    """
    Crée un devis complet dans SAP.
    
    Args:
        quotation_data: Données complètes du devis
        
    Returns:
        Résultat de la création
    """
    try:
        log(f"Création devis SAP pour client: {quotation_data.get('CardCode', 'Code manquant')}")
        
        # Validation des données minimales
        required_fields = ["CardCode", "DocumentLines"]
        for field in required_fields:
            if not quotation_data.get(field):
                return {"success": False, "error": f"Champ requis manquant: {field}"}
        
        if not quotation_data["DocumentLines"]:
            return {"success": False, "error": "Aucune ligne de document fournie"}
        
        # Vérifier que le client existe
        client_check = await call_sap(f"/BusinessPartners('{quotation_data['CardCode']}')")
        if "error" in client_check:
            return {"success": False, "error": f"Client {quotation_data['CardCode']} non trouvé"}
        
        # Valider les lignes de document
        valid_lines = []
        for i, line in enumerate(quotation_data["DocumentLines"]):
            if not line.get("ItemCode"):
                log(f"⚠️ Ligne {i}: ItemCode manquant, ignorée", "WARNING")
                continue
            
            # Vérifier que le produit existe
            item_check = await call_sap(f"/Items('{line['ItemCode']}')")
            if "error" in item_check:
                log(f"⚠️ Ligne {i}: Produit {line['ItemCode']} non trouvé", "WARNING")
                continue
            
            valid_line = {
                "ItemCode": line["ItemCode"],
                "Quantity": float(line.get("Quantity", 1)),
                "Price": float(line.get("Price", 0)),
                "DiscountPercent": float(line.get("DiscountPercent", 0)),
                "TaxCode": line.get("TaxCode", "S1"),
                "WarehouseCode": line.get("WarehouseCode", "01")
            }
            valid_lines.append(valid_line)
        
        if not valid_lines:
            return {"success": False, "error": "Aucune ligne de document valide"}
        
        # Préparer les données finales du devis
        final_quotation_data = {
            "CardCode": quotation_data["CardCode"],
            "DocDate": quotation_data.get("DocDate", datetime.now().strftime("%Y-%m-%d")),
            "DocDueDate": quotation_data.get("DocDueDate", (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")),
            "DocCurrency": quotation_data.get("DocCurrency", "EUR"),
            "Comments": quotation_data.get("Comments", "Devis créé via NOVA Middleware"),
            "SalesPersonCode": quotation_data.get("SalesPersonCode", -1),
            "DocumentLines": valid_lines
        }
        
        log(f"Données finales du devis: {json.dumps(final_quotation_data, indent=2)}", "DEBUG")
        
        # Créer le devis dans SAP
        result = await call_sap("/Quotations", "POST", final_quotation_data)
        
        if "error" in result:
            log(f"❌ Erreur création devis: {result['error']}", "ERROR")
            return {"success": False, "error": result["error"]}
        
        doc_num = result.get("DocNum")
        doc_entry = result.get("DocEntry")
        
        log(f"✅ DEVIS SAP CRÉÉ AVEC SUCCÈS - DocNum: {doc_num}, DocEntry: {doc_entry}", "SUCCESS")
        
        return {
            "success": True,
            "doc_num": doc_num,
            "doc_entry": doc_entry,
            "card_code": quotation_data["CardCode"],
            "total_amount": result.get("DocTotal", 0),
            "creation_date": result.get("DocDate"),
            "due_date": result.get("DocDueDate"),
            "currency": result.get("DocCurrency", "EUR"),
            "status": result.get("DocumentStatus", "Open"),
            "lines_count": len(valid_lines),
            "raw_result": result
        }
        
    except Exception as e:
        log(f"❌ Exception lors de la création du devis: {str(e)}", "ERROR")
        log(f"Traceback: {traceback.format_exc()}", "DEBUG")
        return {"success": False, "error": str(e)}

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
                "method": method,
                "timestamp": datetime.now().isoformat()
            }
        
        if "value" in result:
            log(f"Lecture réussie - {len(result['value'])} résultats")
        else:
            log("Lecture réussie - réponse directe")
        
        return result
    except Exception as e:
        log(f"❌ Erreur lors de l'appel à l'API SAP: {str(e)}", "ERROR")
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
        log(f"Recherche SAP: '{query}' dans {entity_type}")
        
        # Déterminer le bon champ pour la recherche
        search_mappings = {
            "Items": "ItemName",
            "BusinessPartners": "CardName",
            "Orders": "DocNum",
            "Invoices": "DocNum",
            "Quotations": "DocNum"
        }
        
        search_field = search_mappings.get(entity_type, "Name")
        
        # Construire la requête avec échappement des caractères spéciaux
        escaped_query = query.replace("'", "''")  # Échapper les apostrophes
        endpoint = f"/{entity_type}?$filter=contains({search_field},'{escaped_query}')&$top={limit}"
        
        result = await call_sap(endpoint)
        
        if "error" in result:
            return {"error": result["error"]}
        
        if "value" in result:
            log(f"Recherche réussie - {len(result['value'])} résultats")
            return {
                "query": query,
                "entity_type": entity_type,
                "results": result["value"],
                "count": len(result["value"])
            }
        else:
            log("Recherche réussie - format de réponse inattendu")
            return {
                "query": query,
                "entity_type": entity_type,
                "results": [],
                "count": 0,
                "raw_response": result
            }
    except Exception as e:
        log(f"❌ Erreur lors de la recherche SAP: {str(e)}", "ERROR")
        return {"error": str(e)}

@mcp.tool(name="sap_get_product_details")
async def sap_get_product_details(item_code: str) -> dict:
    """Récupère les détails complets d'un produit avec le VRAI stock SAP."""
    try:
        log(f"Récupération des détails du produit: {item_code}")
        
        # Récupérer les informations de base du produit
        product = await call_sap(f"/Items('{item_code}')")
        
        if "error" in product:
            log(f"❌ Produit {item_code} non trouvé: {product['error']}", "ERROR")
            return product
        
        # Extraire le stock total depuis QuantityOnStock (c'est le vrai stock total !)
        total_stock = float(product.get("QuantityOnStock", 0))
        
        # Extraire le prix depuis ItemPrices
        price = 0.0
        if product.get("ItemPrices") and len(product["ItemPrices"]) > 0:
            price = float(product["ItemPrices"][0].get("Price", 0))
        
        # Récupérer les détails par entrepôt depuis ItemWarehouseInfoCollection
        warehouses = []
        total_calculated = 0.0
        
        if product.get("ItemWarehouseInfoCollection"):
            for wh in product["ItemWarehouseInfoCollection"]:
                in_stock = float(wh.get("InStock", 0))
                committed = float(wh.get("Committed", 0))
                ordered = float(wh.get("Ordered", 0))
                available = in_stock - committed
                total_calculated += in_stock
                
                warehouses.append({
                    "WarehouseCode": wh.get("WarehouseCode", ""),
                    "InStock": in_stock,
                    "Committed": committed,
                    "Ordered": ordered,
                    "Available": available
                })
        
        # Construire la réponse avec le VRAI stock
        enriched_product = {
            **product,
            "stock": {
                "total": total_stock,  # Utiliser QuantityOnStock (le vrai stock total)
                "warehouses": warehouses,
                "method_used": "QuantityOnStock_real",
                "details": {
                    "quantity_on_stock": total_stock,
                    "calculated_from_warehouses": total_calculated,
                    "warehouses_count": len(warehouses)
                }
            },
            "Price": price,
            "price_details": {
                "price": price,
                "method_used": "ItemPrices",
                "details": {"price_list": product.get("ItemPrices", [{}])[0].get("PriceList", "Standard") if product.get("ItemPrices") else "N/A"}
            }
        }
        
        log(f"✅ Détails du produit {item_code} récupérés - Stock RÉEL: {total_stock}, Prix: {price}", "SUCCESS")
        return enriched_product
        
    except Exception as e:
        log(f"❌ Erreur lors de la récupération des détails du produit {item_code}: {str(e)}", "ERROR")
        return {"error": str(e)}
        
@mcp.tool(name="sap_find_alternatives")
async def sap_find_alternatives(item_code: str, limit: int = 5) -> dict:
    """
    Trouve des alternatives pour un produit donné
    
    Args:
        item_code: Code du produit à remplacer
        limit: Nombre d'alternatives à retourner
        
    Returns:
        Liste des alternatives trouvées
    """
    try:
        log(f"Recherche d'alternatives pour le produit: {item_code}")
        
        # Récupérer les informations du produit original
        original_product = await call_sap(f"/Items('{item_code}')")
        if "error" in original_product:
            return {"error": f"Produit original {item_code} non trouvé"}
        
        # Rechercher des produits similaires par nom ou catégorie
        product_name = original_product.get("ItemName", "")
        
        # Stratégie 1: Recherche par nom similaire
        alternatives = []
        if product_name:
            # Extraire les mots clés du nom du produit
            keywords = product_name.split()[:2]  # Prendre les 2 premiers mots
            
            for keyword in keywords:
                if len(keyword) > 3:  # Ignorer les mots trop courts
                    search_result = await call_sap(
                        f"/Items?$filter=contains(ItemName,'{keyword}') and ItemCode ne '{item_code}' and OnHand gt 0&$top={limit}"
                    )
                    
                    if "error" not in search_result and "value" in search_result:
                        for item in search_result["value"]:
                            if len(alternatives) < limit:
                                alternatives.append({
                                    "ItemCode": item.get("ItemCode"),
                                    "ItemName": item.get("ItemName"),
                                    "Price": item.get("Price", 0),
                                    "Stock": item.get("OnHand", 0),
                                    "Unit": item.get("SalesUnit", "")
                                })
        
        log(f"✅ {len(alternatives)} alternative(s) trouvée(s) pour {item_code}")
        return {
            "original_item": item_code,
            "alternatives": alternatives,
            "count": len(alternatives)
        }
        
    except Exception as e:
        log(f"❌ Erreur recherche alternatives {item_code}: {str(e)}", "ERROR")
        return {"error": str(e)}
# Table de mappage des fonctions MCP
mcp_functions = {
    "ping": ping,
    "sap_read": sap_read,
    "sap_search": sap_search,
    "sap_get_product_details": sap_get_product_details,
    "sap_create_customer_complete": sap_create_customer_complete,
    "sap_create_quotation_complete": sap_create_quotation_complete
}

# Initialisation au démarrage
async def init_sap():
    """Initialisation et test de la connexion SAP"""
    log("Initialisation de la connexion SAP...")
    success = await login_sap()
    if not success:
        log("❌ ÉCHEC de l'initialisation SAP", "ERROR")
    return success

# Traitement des arguments en ligne de commande
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-file", help="Fichier d'entrée JSON")
    parser.add_argument("--output-file", help="Fichier de sortie JSON")
    args, unknown = parser.parse_known_args()
    
    if args.input_file and args.output_file:
        try:
            with open(args.input_file, 'r') as f:
                input_data = json.load(f)
            
            action = input_data.get("action")
            params = input_data.get("params", {})
            
            log(f"Exécution de l'action: {action} avec paramètres: {params}")
            
            if action in mcp_functions:
                try:
                    result = asyncio.run(mcp_functions[action](**params))
                    with open(args.output_file, 'w') as f:
                        json.dump(result, f, indent=2)
                    log(f"✅ Action {action} exécutée avec succès", "SUCCESS")
                    sys.exit(0)
                except Exception as e:
                    log(f"❌ Erreur lors de l'exécution de {action}: {str(e)}", "ERROR")
                    with open(args.output_file, 'w') as f:
                        json.dump({"error": str(e)}, f)
                    sys.exit(1)
            else:
                error_msg = f"Action inconnue: {action}. Actions disponibles: {list(mcp_functions.keys())}"
                log(error_msg, "ERROR")
                with open(args.output_file, 'w') as f:
                    json.dump({"error": error_msg}, f)
                sys.exit(1)
                
        except Exception as e:
            log(f"❌ Erreur lors du traitement des arguments: {str(e)}", "ERROR")
            sys.exit(1)
    
    # Mode serveur MCP
    try:
        log("Initialisation du serveur MCP SAP...")
        # Tester la connexion au démarrage
        init_result = asyncio.run(init_sap())
        if init_result:
            log("✅ Serveur MCP SAP prêt et connecté", "SUCCESS")
        else:
            log("⚠️ Serveur MCP SAP démarré mais connexion SAP échouée", "WARNING")
        
        log("Lancement du serveur MCP SAP...")
        mcp.run(transport="stdio")
        
    except KeyboardInterrupt:
        log("Arrêt du serveur MCP SAP par l'utilisateur", "INFO")
    except Exception as e:
        log(f"❌ Erreur fatale du serveur MCP SAP: {str(e)}", "ERROR")
        log(f"Traceback: {traceback.format_exc()}", "DEBUG")
    finally:
        log_file.close()