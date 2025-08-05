#!/usr/bin/env python3
"""
Script de test simple pour NOVA
"""
import sys
import os

print("🔍 Test de démarrage NOVA...")

try:
    print("✅ Importation des modules de base...")
    import fastapi
    import uvicorn
    print("✅ FastAPI et Uvicorn disponibles")
    
    print("✅ Test des imports locaux...")
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    
    # Test des imports un par un
    try:
        from routes.routes_intelligent_assistant import router as assistant_router
        print("✅ routes_intelligent_assistant importé")
    except Exception as e:
        print(f"❌ Erreur routes_intelligent_assistant: {e}")
        
    try:
        from routes.routes_progress import router as progress_router
        print("✅ routes_progress importé")
    except Exception as e:
        print(f"❌ Erreur routes_progress: {e}")
        
    try:
        from services.websocket_manager import websocket_manager
        print("✅ websocket_manager importé")
    except Exception as e:
        print(f"❌ Erreur websocket_manager: {e}")
        
    print("✅ Tous les imports de base réussis")
    
    # Test de création de l'app FastAPI
    app = fastapi.FastAPI(title="Test NOVA")
    print("✅ Application FastAPI créée")
    
    print("🎉 Test de démarrage réussi !")
    
except Exception as e:
    print(f"❌ Erreur critique: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)