#!/usr/bin/env python3
"""
Serveur NOVA minimal pour test
"""
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import os

# Créer l'application FastAPI
app = FastAPI(
    title="NOVA - Test Interface",
    description="Test de l'interface NOVA",
    version="1.0.0"
)

# Servir l'interface HTML
@app.get("/", response_class=HTMLResponse)
@app.get("/interface", response_class=HTMLResponse)
async def serve_interface():
    """Sert l'interface NOVA"""
    try:
        with open("templates/nova_interface_final.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h1>Interface non trouvée</h1><p>Le fichier templates/nova_interface_final.html est introuvable.</p>"

# Endpoint de test pour les requêtes
@app.post("/api/assistant/workflow/create_quote")
async def test_quote_endpoint(request: dict):
    """Endpoint de test pour les requêtes de devis"""
    return {
        "status": "success",
        "message": "Test réussi ! Le formulaire fonctionne.",
        "task_id": "test_task_123",
        "data": request
    }

# Endpoint de santé
@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "Serveur de test NOVA opérationnel"}

if __name__ == "__main__":
    print("🚀 Démarrage du serveur de test NOVA...")
    print("📱 Interface disponible sur: http://localhost:8000")
    print("🔍 Health check: http://localhost:8000/health")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )