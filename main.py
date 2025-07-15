
import os
import logging
import time
from typing import List, Dict, Any, Optional
from datetime import datetime
import asyncio
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse
from services.module_loader import ModuleLoader, ModuleConfig
security = HTTPBasic()
# Configuration logging selon charte IT SPIRIT
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('nova_server.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)
class ProductProcessor:
    """
    🔧 Processeur de produits NOVA - Compatible Salesforce/SAP
    Intégration LLM Claude pour extraction automatique des besoins
    """
    
    def __init__(self, llm_connector=None, sap_connector=None, salesforce_connector=None):
        self.llm_connector = llm_connector
        self.sap_connector = sap_connector  
        self.salesforce_connector = salesforce_connector
        self.processed_products = []
        
        logger.info("✅ ProductProcessor initialisé avec connecteurs MCP")

    async def process_products(self, products_info: List[Dict[str, Any]], 
                             client_context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        🚀 Traitement principal des produits avec extraction corrigée
        
        Args:
            products_info: Liste des produits à traiter
            client_context: Contexte client pour personnalisation
            
        Returns:
            Dict avec produits traités et totaux
        """
        try:
            logger.info(f"🔄 Début traitement de {len(products_info)} produits")
            
            processed_items = []
            total_ht = 0.0
            total_ttc = 0.0
            
            for index, product in enumerate(products_info):
                logger.debug(f"🔍 Traitement produit {index + 1}/{len(products_info)}")
                
                # 🔧 VALIDATION TYPE PRODUIT
                if not isinstance(product, dict):
                    logger.warning(f"⚠️ Produit {index} n'est pas un dictionnaire: {type(product)}")
                    continue
                    
                if "error" in product:
                    logger.warning(f"⚠️ Produit {index} contient une erreur: {product.get('error')}")
                    continue

                # 🔧 EXTRACTION CORRIGÉE DES DONNÉES PRODUIT
                product_code = (product.get("code") or
                               product.get("item_code") or
                               product.get("ItemCode") or
                               product.get("reference") or
                               product.get("sku", ""))

                product_name = (product.get("name") or
                               product.get("item_name") or
                               product.get("ItemName") or
                               product.get("description") or
                               product.get("title", "Sans nom"))

                # 🔧 GESTION ROBUSTE DES QUANTITÉS ET PRIX
                try:
                    quantity = float(product.get("quantity", 1))
                    if quantity <= 0:
                        logger.warning(f"⚠️ Quantité invalide pour {product_code}: {quantity}")
                        quantity = 1.0
                except (ValueError, TypeError):
                    logger.warning(f"⚠️ Quantité non numérique pour {product_code}")
                    quantity = 1.0

                try:
                    unit_price = float(product.get("unit_price") or 
                                     product.get("price") or
                                     product.get("unitPrice", 0))
                    if unit_price < 0:
                        logger.warning(f"⚠️ Prix négatif pour {product_code}: {unit_price}")
                        unit_price = 0.0
                except (ValueError, TypeError):
                    logger.warning(f"⚠️ Prix non numérique pour {product_code}")
                    unit_price = 0.0

                # 🔧 CALCULS AVEC GESTION D'ERREURS
                line_total = quantity * unit_price
                
                # 🔧 ENRICHISSEMENT DONNÉES SAP/SALESFORCE
                enriched_product = await self._enrich_product_data(
                    product_code, product_name, quantity, unit_price, client_context
                )

                # 🔧 CONSTRUCTION DONNÉES PRODUIT NORMALISÉES
                product_data = {
                    # Données de base
                    "code": product_code,
                    "name": product_name,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "line_total": line_total,
                    
                    # Données enrichies
                    "category": enriched_product.get("category", "Général"),
                    "supplier": enriched_product.get("supplier", "Non défini"),
                    "availability": enriched_product.get("availability", "À vérifier"),
                    "delivery_time": enriched_product.get("delivery_time", "5-7 jours"),
                    
                    # Données SAP
                    "sap_code": enriched_product.get("sap_code"),
                    "cost_center": enriched_product.get("cost_center"),
                    "margin": enriched_product.get("margin", 0),
                    
                    # Données Salesforce
                    "product_id": enriched_product.get("salesforce_id"),
                    "price_book_entry": enriched_product.get("price_book_entry"),
                    
                    # Métadonnées
                    "processed_at": datetime.now().isoformat(),
                    "processing_index": index,
                    "validation_status": "validated" if product_code and unit_price > 0 else "needs_review"
                }

                # 🔧 VALIDATION FINALE PRODUIT
                if self._validate_product_data(product_data):
                    processed_items.append(product_data)
                    total_ht += line_total
                    logger.info(f"✅ Produit traité: {product_code} - {product_name} ({quantity}x{unit_price}€)")
                else:
                    logger.error(f"❌ Échec validation produit: {product_code}")

            # 🔧 CALCULS TOTAUX
            tva_rate = client_context.get("tva_rate", 0.20) if client_context else 0.20
            total_ttc = total_ht * (1 + tva_rate)

            # 🔧 RÉSULTAT STRUCTURÉ
            result = {
                "success": len(processed_items) > 0,
                "products": processed_items,
                "summary": {
                    "total_items": len(processed_items),
                    "total_ht": round(total_ht, 2),
                    "total_ttc": round(total_ttc, 2),
                    "tva_amount": round(total_ttc - total_ht, 2),
                    "tva_rate": tva_rate
                },
                "processing_info": {
                    "processed_at": datetime.now().isoformat(),
                    "input_count": len(products_info),
                    "output_count": len(processed_items),
                    "success_rate": (len(processed_items) / len(products_info)) * 100 if products_info else 0
                }
            }
            
            logger.info(f"🎯 Traitement terminé: {len(processed_items)} produits validés sur {len(products_info)}")
            return result

        except Exception as e:
            logger.error(f"❌ Erreur dans process_products: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "products": [],
                "summary": {"total_items": 0, "total_ht": 0, "total_ttc": 0}
            }

    async def _enrich_product_data(self, code: str, name: str, quantity: float, 
                                 price: float, client_context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        🔍 Enrichissement des données produit via SAP et Salesforce
        """
        enriched_data = {}
        
        try:
            # 🔗 CONNEXION SAP pour données produit
            if self.sap_connector and code:
                sap_data = await self.sap_connector.get_product_info(code)
                if sap_data.get("success"):
                    enriched_data.update({
                        "sap_code": sap_data.get("material_code"),
                        "cost_center": sap_data.get("cost_center"),
                        "supplier": sap_data.get("vendor_name"),
                        "category": sap_data.get("material_group"),
                        "margin": sap_data.get("margin_percent", 0)
                    })
                    logger.debug(f"✅ Données SAP récupérées pour {code}")

            # 🔗 CONNEXION SALESFORCE pour prix et disponibilité  
            if self.salesforce_connector and code:
                sf_data = await self.salesforce_connector.get_product_pricing(code, client_context)
                if sf_data.get("success"):
                    enriched_data.update({
                        "salesforce_id": sf_data.get("product_id"),
                        "price_book_entry": sf_data.get("price_book_entry_id"),
                        "availability": sf_data.get("availability_status"),
                        "delivery_time": sf_data.get("delivery_estimate")
                    })
                    logger.debug(f"✅ Données Salesforce récupérées pour {code}")

        except Exception as e:
            logger.warning(f"⚠️ Erreur enrichissement produit {code}: {str(e)}")
            
        return enriched_data

    def _validate_product_data(self, product_data: Dict[str, Any]) -> bool:
        """
        ✅ Validation des données produit selon règles métier
        """
        required_fields = ["code", "name", "quantity", "unit_price"]
        
        # Vérification champs obligatoires
        for field in required_fields:
            if not product_data.get(field):
                logger.warning(f"⚠️ Champ obligatoire manquant: {field}")
                return False
        
        # Validation règles métier
        if product_data["quantity"] <= 0:
            logger.warning(f"⚠️ Quantité invalide: {product_data['quantity']}")
            return False
            
        if product_data["unit_price"] < 0:
            logger.warning(f"⚠️ Prix invalide: {product_data['unit_price']}")
            return False
            
        return True

# 🔧 EXEMPLE D'UTILISATION
async def main_processing_example():
    """
    💡 Exemple d'utilisation du ProductProcessor corrigé
    """
    # Données test selon format réel
    test_products = [
        {
            "code": "HP-LJ-P4250N",
            "name": "HP LaserJet Pro 4250n",
            "quantity": 4,
            "unit_price": 449.99
        },
        {
            "ItemCode": "CANON-TR8620", 
            "ItemName": "Canon PIXMA TR8620",
            "quantity": "2",  # String volontairement pour test conversion
            "price": 189.99
        },
        {
            "error": "Produit non trouvé"  # Test gestion erreur
        }
    ]
    
    client_context = {
        "company_name": "Rondot Group",
        "tva_rate": 0.20,
        "price_list": "CORPORATE"
    }
    
    # Initialisation processeur avec connecteurs MCP
    processor = ProductProcessor(
        llm_connector=None,  # À connecter avec Claude MCP
        sap_connector=None,   # À connecter avec SAP MCP  
        salesforce_connector=None  # À connecter avec Salesforce MCP
    )
    
    # Traitement
    result = await processor.process_products(test_products, client_context)
    
    # Affichage résultat
    if result["success"]:
        print("✅ Traitement réussi!")
        print(f"📦 Produits traités: {result['summary']['total_items']}")
        print(f"💰 Total HT: {result['summary']['total_ht']}€")
        print(f"💰 Total TTC: {result['summary']['total_ttc']}€")
    else:
        print(f"❌ Erreur: {result.get('error')}")
def get_current_user(credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.username != "admin" or credentials.password != "nova2025":
        raise HTTPException(status_code=401)
    return credentials.username
# Configuration des modules avec préfixes distincts
MODULES_CONFIG = {
    'sync': ModuleConfig('routes.routes_sync', '/sync', ['Synchronisation']),
    'products': ModuleConfig('routes.routes_products', '/products', ['Produits']),
    'devis': ModuleConfig('routes.routes_devis', '/devis', ['Devis']),  # ← CHANGÉ: préfixe /devis
    'assistant': ModuleConfig('routes.routes_intelligent_assistant', '/api/assistant', ['Assistant Intelligent']),
    'clients': ModuleConfig('routes.routes_clients', '/clients', ['Clients'])
}

# Création de l'application
app = FastAPI(
    title="NOVA Middleware",
    description="Middleware d'intégration LLM - SAP - Salesforce",
    version="1.0.0"
)

# Middleware de sécurité
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["178.33.233.120", "localhost", "127.0.0.1"]
)

# Fichiers statiques
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# Chargement automatique des modules optionnels
loader = ModuleLoader()
loader.load_modules(MODULES_CONFIG)
loader.register_to_fastapi(app)

# ✅ AJOUT : Route de compatibilité unifiée
@app.post("/generate_quote")
async def generate_quote_unified(request: dict):
    """
    🎯 Route unifiée pour éviter les conflits
    Redirige vers le bon endpoint selon le contexte
    """
    try:
        # Vérifier le format de la requête
        prompt = request.get("prompt", "").strip()
        draft_mode = request.get("draft_mode", False)

        if not prompt:
            return {"success": False, "error": "Prompt manquant"}

        # Utiliser le service assistant comme endpoint principal
        from routes.routes_intelligent_assistant import generate_quote_endpoint
        from routes.routes_intelligent_assistant import GenerateQuoteRequest

        # Créer la requête formatée
        quote_request = GenerateQuoteRequest(
            prompt=prompt,
            draft_mode=draft_mode
        )

        # Exécuter la génération
        result = await generate_quote_endpoint(quote_request)

        # Convertir le résultat en dict pour la réponse
        if hasattr(result, 'dict'):
            return result.dict()
        else:
            return result

    except Exception as e:
        print(f"❌ Erreur route unifiée: {str(e)}")
        return {
            "success": False,
            "error": f"Erreur serveur: {str(e)}"
        }

# ✅ AJOUT : Route de diagnostic
@app.get("/diagnostic")
async def diagnostic():
    """
    🔍 Endpoint de diagnostic pour tester la connectivité
    """
    try:
        # Test des modules chargés
        loaded_modules = loader.get_loaded_modules()

        # Test des endpoints disponibles
        endpoints = []
        for route in app.routes:
            if hasattr(route, 'methods') and hasattr(route, 'path'):
                endpoints.append(f"{list(route.methods)[0]} {route.path}")

        return {
            "status": "OK",
            "timestamp": str(datetime.now()),
            "loaded_modules": loaded_modules,
            "endpoints": endpoints,
            "health": "Server running"
        }

    except Exception as e:
        return {
            "status": "ERROR",
            "error": str(e)
        }

# ✅ AJOUT : Interface de diagnostic
@app.get("/diagnostic/interface", response_class=HTMLResponse)
async def diagnostic_interface():
    """
    🔍 Interface de diagnostic HTML
    """
    # Rediriger vers l'interface de diagnostic statique
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/diagnostic.html")

# ✅ AJOUT : Middleware de logging des requêtes
@app.middleware("http")
async def log_requests(request, call_next):
    """
    📝 Middleware pour logger toutes les requêtes
    """
    start_time = time.time()

    # Logger la requête entrante
    print(f"🔄 {request.method} {request.url}")

    # Traiter la requête
    response = await call_next(request)

    # Logger la réponse
    process_time = time.time() - start_time
    print(f"✅ {request.method} {request.url} - {response.status_code} - {process_time:.2f}s")

    return response

# Routes obligatoires (sans try/except car toujours présentes)
from routes.routes_quote_details import router as quote_details_router
from routes.routes_progress import router as progress_router  
from routes import routes_suggestions

app.include_router(quote_details_router, tags=["Quote Details"])
app.include_router(progress_router, prefix="/progress", tags=["Progress"])
app.include_router(routes_suggestions.router)

@app.get("/")
def root():
    """Point d'entrée avec redirection intelligente"""
    if 'assistant' in loader.get_loaded_modules():
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/api/assistant/interface")
    
    return {
        "message": "NOVA Middleware actif",
        "version": "1.0.0",
        "status": "operational", 
        "services": loader.get_status()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)