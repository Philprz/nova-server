#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test direct de l'API INSEE pour diagnostiquer les problèmes de 404
"""

import asyncio
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

# Configuration INSEE
INSEE_CONSUMER_KEY = os.getenv("INSEE_CONSUMER_KEY")
INSEE_CONSUMER_SECRET = os.getenv("INSEE_CONSUMER_SECRET")

async def test_insee_api_direct():
    """Test direct de l'API INSEE avec différents formats"""
    
    print("🔍 TEST DIRECT DE L'API INSEE")
    print(f"Consumer Key: {'✅ Présent' if INSEE_CONSUMER_KEY else '❌ Absent'}")
    print(f"Consumer Secret: {'✅ Présent' if INSEE_CONSUMER_SECRET else '❌ Absent'}")
    
    if not INSEE_CONSUMER_KEY or not INSEE_CONSUMER_SECRET:
        print("❌ Configuration INSEE manquante")
        return
    
    # 1. Obtenir le token
    print("\n1️⃣ Obtention du token...")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.insee.fr/token",
                auth=(INSEE_CONSUMER_KEY, INSEE_CONSUMER_SECRET),
                data={"grant_type": "client_credentials"}
            )
            response.raise_for_status()
            token_data = response.json()
            access_token = token_data["access_token"]
            print(f"✅ Token obtenu: {access_token[:20]}...")
    except Exception as e:
        print(f"❌ Erreur token: {e}")
        return
    
    # SIRET d'entreprises réelles pour les tests - AVEC SIRET VALIDE CONFIRMÉ
    TEST_SIRET_CASES = [
        {
            "siret": "51252037000036",  # IT SPIRIT - CONFIRMÉ VALIDE ✅
            "description": "IT SPIRIT - Votre entreprise (validé)"
        },
        {
            "siret": "78925320700011",  # La Poste - à tester
            "description": "La Poste (siège social)"
        },
        {
            "siret": "55204215300056",  # Microsoft - probablement invalide
            "description": "Microsoft France (test)"
        },
        {
            "siret": "12345678901234",  # SIRET invalide pour test d'erreur
            "description": "SIRET invalide (test d'erreur)"
        }
    ]
    
    headers = {"Authorization": f"Bearer {access_token}"}
    
    for i, test_case in enumerate(TEST_SIRET_CASES, 1):
        print(f"\n{i}️⃣ Test: {test_case['name']}")
        print(f"URL: {test_case['url']}")
        print(f"Description: {test_case['description']}")
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(test_case['url'], headers=headers, timeout=10.0)
                
                print(f"Status: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    print("✅ SUCCÈS!")
                    
                    # Analyser la structure de réponse
                    if "header" in data:
                        header = data["header"]
                        print(f"Header statut: {header.get('statut')}")
                        print(f"Header message: {header.get('message', 'N/A')}")
                    
                    if "etablissement" in data:
                        etab = data["etablissement"]
                        print(f"SIRET trouvé: {etab.get('siret')}")
                        unite_legale = etab.get("uniteLegale", {})
                        print(f"Dénomination: {unite_legale.get('denominationUniteLegale', 'N/A')}")
                    
                    if "etablissements" in data:
                        etabs = data["etablissements"]
                        print(f"Nombre d'établissements: {len(etabs)}")
                        if etabs:
                            print(f"Premier SIRET: {etabs[0].get('siret')}")
                    
                    # Afficher la structure pour diagnostic
                    print(f"Clés principales: {list(data.keys())}")
                    
                elif response.status_code == 404:
                    print("❌ 404 - Ressource non trouvée")
                    try:
                        error_data = response.json()
                        print(f"Détail erreur: {error_data}")
                    except:
                        print("Pas de détail d'erreur JSON")
                
                elif response.status_code == 400:
                    print("❌ 400 - Requête incorrecte")
                    try:
                        error_data = response.json()
                        print(f"Détail erreur: {error_data}")
                    except:
                        print("Pas de détail d'erreur JSON")
                
                else:
                    print(f"❌ Erreur {response.status_code}")
                    print(f"Réponse: {response.text[:200]}...")
                
        except Exception as e:
            print(f"❌ Exception: {e}")
        
        # Pause entre les tests
        await asyncio.sleep(1)
    
    # 3. Test de l'endpoint de base
    print("\n🔍 Test endpoint de base...")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.insee.fr/entreprises/sirene/V3/",
                headers=headers
            )
            print(f"Status endpoint base: {response.status_code}")
            if response.status_code == 200:
                print("✅ L'API de base répond")
            else:
                print(f"❌ Erreur: {response.text[:200]}")
    except Exception as e:
        print(f"❌ Erreur endpoint base: {e}")
    
    print("\n📋 DIAGNOSTIC:")
    print("Si tous les tests retournent 404, cela peut indiquer:")
    print("1. Les clés API n'ont pas les permissions Sirene")
    print("2. L'URL de base est incorrecte")
    print("3. Le format de requête a changé")
    print("4. Les SIRET testés sont vraiment inexistants")

if __name__ == "__main__":
    asyncio.run(test_insee_api_direct())