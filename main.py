# main.py - VERSION CORRIGÉE AVEC SYNCHRONISATION
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# Import seulement des routes qui existent réellement
try:
    from routes.routes_sync import router as sync_router
    sync_available = True
    print("✅ routes_sync chargées avec succès")
except ImportError as e:
    sync_available = False
    print(f"⚠️ routes_sync non disponible: {e}")

try:
    from routes.routes_products import router as products_router
    products_available = True
    print("✅ routes_products chargées avec succès")
except ImportError as e:
    products_available = False
    print(f"⚠️ routes_products non disponible: {e}")
try:
    from routes.routes_claude import router as claude_router
    claude_available = True
except ImportError:
    claude_available = False
    print("⚠️ routes_claude non disponible")

try:
    from routes.routes_salesforce import router as salesforce_router
    salesforce_available = True
except ImportError:
    salesforce_available = False
    print("⚠️ routes_salesforce non disponible")

try:
    from routes.routes_sap import router as sap_router
    sap_available = True
except ImportError:
    sap_available = False
    print("⚠️ routes_sap non disponible")

try:
    from routes.routes_devis import router as devis_router
    devis_available = True
except ImportError:
    devis_available = False
    print("⚠️ routes_devis non disponible")

try:
    from routes.routes_clients import router as clients_router
    clients_available = True
except ImportError:
    clients_available = False
    print("⚠️ routes_clients non disponible")

try:
    from routes.routes_sync import router as sync_router
    sync_available = True
    print("✅ routes_sync chargées avec succès")
except ImportError as e:
    sync_available = False
    print(f"⚠️ routes_sync non disponible: {e}")

# Créer l'application FastAPI
app = FastAPI(
    title="NOVA Middleware",
    description="Middleware d'intégration LLM - SAP - Salesforce",
    version="1.0.0"
)

# Monter le dossier static pour servir les fichiers statiques
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
else:
    print("⚠️ Dossier static non trouvé")

# Inclusion des routers disponibles
if claude_available:
    app.include_router(claude_router, tags=["Claude"])
    print("✅ Routes Claude chargées")

if salesforce_available:
    app.include_router(salesforce_router, tags=["Salesforce"])
    print("✅ Routes Salesforce chargées")

if sap_available:
    app.include_router(sap_router, tags=["SAP"])
    print("✅ Routes SAP chargées")

if devis_available:
    app.include_router(devis_router, tags=["Devis"])
    print("✅ Routes Devis chargées")

if clients_available:
    app.include_router(clients_router, prefix="/clients", tags=["Clients"])
    print("✅ Routes Clients chargées")

if sync_available:
    app.include_router(sync_router, prefix="/sync", tags=["Synchronisation"])
    print("✅ Routes Synchronisation chargées")

if products_available:
    app.include_router(products_router, prefix="/products", tags=["Produits"])
    print("✅ Routes Produits chargées")
    
@app.get("/", tags=["Health"])
def root():
    """Point d'entrée principal - Vérification de santé"""
    return {
        "message": "NOVA Middleware opérationnel",
        "version": "1.0.0",
        "status": "running",
        "modules": {
            "claude": claude_available,
            "salesforce": salesforce_available,
            "sap": sap_available,
            "devis": devis_available,
            "clients": clients_available,
            "sync": sync_available
        }
    }

@app.get("/health", tags=["Health"])
def health_check():
    """Contrôle de santé détaillé"""
    return {
        "status": "healthy",
        "timestamp": "2025-06-04T16:00:00Z",
        "services": {
            "claude_routes": "available" if claude_available else "unavailable",
            "salesforce_routes": "available" if salesforce_available else "unavailable", 
            "sap_routes": "available" if sap_available else "unavailable",
            "devis_workflow": "available" if devis_available else "unavailable",
            "clients_management": "available" if clients_available else "unavailable",
            "sync_module": "available" if sync_available else "unavailable"
        }
    }

if __name__ == "__main__":
    import uvicorn
    print("🚀 Démarrage de NOVA Middleware...")
    print("📝 Documentation API : http://localhost:8000/docs")
    print("🏥 Contrôle santé : http://localhost:8000/health")
    if os.path.exists("static"):
        print("🎮 Démo devis : http://localhost:8000/static/nova_interface.html")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)