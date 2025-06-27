#!/usr/bin/env python3
"""
Script de test pour la récupération des détails de devis
Teste la nouvelle fonctionnalité d'édition des champs
"""

import requests
import json
import sys
from datetime import datetime

def test_quote_details_api():
    """Test complet de l'API de récupération des détails de devis"""
    
    base_url = "http://localhost:8000"
    
    print("🧪 Test de l'API de Récupération des Détails de Devis")
    print("=" * 60)
    
    # 1. Test de connexion API
    print("\n1. 🔗 Test de connexion à l'API...")
    try:
        response = requests.get(f"{base_url}/health", timeout=5)
        if response.status_code == 200:
            print("   ✅ API accessible")
        else:
            print(f"   ❌ API inaccessible: {response.status_code}")
            return False
    except Exception : 
        print("   ❌ Impossible de se connecter à l'API")
        print("   💡 Assurez-vous que le serveur est démarré: uvicorn main:app --reload")
        return False
    
    # 2. Génération d'un devis d'abord
    print("\n2. 📋 Génération d'un devis de test...")
    try:
        quote_payload = {
            "prompt": "faire un devis pour 100 ref A00002 pour le client Edge Communications",
            "draft_mode": True
        }
        
        response = requests.post(
            f"{base_url}/generate_quote",
            json=quote_payload,
            timeout=30
        )
        
        if response.status_code == 200:
            quote_result = response.json()
            print("   ✅ Devis généré avec succès")
            
            # Extraction de l'ID du devis
            quote_id = quote_result.get("quote_id")
            sap_doc_entry = quote_result.get("sap_doc_entry")
            
            if quote_id:
                print(f"   📊 Quote ID: {quote_id}")
                print(f"   📊 SAP DocEntry: {sap_doc_entry}")
                return quote_id, sap_doc_entry
            else:
                print("   ⚠️  Quote ID non trouvé dans la réponse")
                print(f"   📄 Réponse: {json.dumps(quote_result, indent=2)}")
                return None, None
        else:
            print(f"   ❌ Erreur génération devis: {response.status_code}")
            print(f"   📄 Réponse: {response.text}")
            return None, None
            
    except Exception as e:
        print(f"   ❌ Erreur lors de la génération: {str(e)}")
        return None, None

def test_quote_details_retrieval(quote_id, base_url="http://localhost:8000"):
    """Test de récupération des détails d'un devis"""
    
    print(f"\n3. 🔍 Test de récupération des détails pour {quote_id}...")
    
    try:
        # Test de l'endpoint des détails
        response = requests.get(
            f"{base_url}/api/quotes/details/{quote_id}",
            timeout=30
        )
        
        if response.status_code == 200:
            details = response.json()
            print("   ✅ Détails récupérés avec succès")
            
            # Analyse des données récupérées
            analyze_quote_details(details)
            
            return details
        
        elif response.status_code == 404:
            print(f"   ❌ Devis {quote_id} non trouvé")
            print(f"   📄 Détail: {response.text}")
            return None
            
        else:
            print(f"   ❌ Erreur {response.status_code}: {response.text}")
            return None
            
    except Exception as e:
        print(f"   ❌ Erreur lors de la récupération: {str(e)}")
        return None

def analyze_quote_details(details):
    """Analyse détaillée des données récupérées"""
    
    print("\n4. 📊 Analyse des données récupérées...")
    
    if not details.get("success", False):
        print("   ❌ Récupération échouée")
        return
    
    quote = details.get("quote", {})
    metadata = details.get("metadata", {})
    
    print(f"   📋 Source: {quote.get('source_system', 'Inconnue')}")
    print(f"   📊 Lignes: {metadata.get('lines_count', 0)}")
    print(f"   🕒 Récupéré: {metadata.get('retrieved_at', 'Inconnu')}")
    
    # Analyse des sections
    sections = ["header", "customer", "lines", "totals"]
    for section in sections:
        if section in quote:
            section_data = quote[section]
            
            if section == "lines" and isinstance(section_data, list):
                print(f"   📦 {section.title()}: {len(section_data)} éléments")
                
                if len(section_data) > 0:
                    sample_line = section_data[0]
                    editable_fields = sample_line.get("editable_fields", [])
                    print(f"       🖊️  Champs éditables par ligne: {', '.join(editable_fields)}")
                    
                    # Affiche un échantillon de ligne
                    print("       📋 Exemple de ligne:")
                    key_fields = ["item_code", "item_description", "quantity", "unit_price", "line_total"]
                    for field in key_fields:
                        if field in sample_line:
                            print(f"         • {field}: {sample_line[field]}")
            
            elif isinstance(section_data, dict):
                non_empty_fields = [k for k, v in section_data.items() if v is not None and v != ""]
                print(f"   🏷️  {section.title()}: {len(non_empty_fields)} champs")
                
                # Affiche quelques champs clés
                if section == "header":
                    key_fields = ["doc_num", "doc_date", "card_name", "comments"]
                elif section == "customer":
                    key_fields = ["card_name", "phone", "email"]
                elif section == "totals":
                    key_fields = ["subtotal", "tax_total", "total_with_tax", "currency"]
                else:
                    key_fields = list(section_data.keys())[:4]
                
                for field in key_fields:
                    if field in section_data and section_data[field] is not None:
                        value = section_data[field]
                        if isinstance(value, str) and len(value) > 50:
                            value = f"{value[:47]}..."
                        print(f"       • {field}: {value}")
    
    # Analyse des règles de validation
    validation_rules = quote.get("validation_rules", {})
    if validation_rules:
        print("   ⚖️  Règles de validation:")
        for rule, value in validation_rules.items():
            print(f"       • {rule}: {value}")

def test_structure_endpoint(base_url="http://localhost:8000"):
    """Test de l'endpoint de structure d'édition"""
    
    print("\n5. 🏗️  Test de l'endpoint de structure...")
    
    try:
        response = requests.get(f"{base_url}/api/quotes/structure", timeout=10)
        
        if response.status_code == 200:
            structure = response.json()
            print("   ✅ Structure récupérée avec succès")
            
            if structure.get("success") and "structure" in structure:
                sections = structure["structure"].get("sections", [])
                print(f"   📊 {len(sections)} sections d'édition définies:")
                
                for section in sections:
                    section_id = section.get("id", "unknown")
                    title = section.get("title", "Sans titre")
                    fields_count = len(section.get("fields", []))
                    icon = section.get("icon", "📄")
                    
                    print(f"       {icon} {title} ({section_id}): {fields_count} champs")
                    
                    # Détails pour les lignes de produits
                    if section_id == "lines":
                        can_add = section.get("can_add", False)
                        can_remove = section.get("can_remove", False)
                        print(f"         ➕ Peut ajouter: {can_add}")
                        print(f"         ➖ Peut supprimer: {can_remove}")
            
            return structure
        else:
            print(f"   ❌ Erreur {response.status_code}: {response.text}")
            return None
            
    except Exception as e:
        print(f"   ❌ Erreur: {str(e)}")
        return None

def save_results(details, structure, quote_id):
    """Sauvegarde les résultats pour analyse"""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if details:
        filename = f"quote_details_{quote_id}_{timestamp}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(details, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Détails sauvegardés: {filename}")
    
    if structure:
        filename = f"quote_structure_{timestamp}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(structure, f, indent=2, ensure_ascii=False)
        print(f"💾 Structure sauvegardée: {filename}")

def main():
    """Fonction principale de test"""
    
    print("🚀 Test Complet - Récupération des Détails de Devis")
    print("=" * 60)
    
    # Génération d'un devis de test
    quote_id, sap_doc_entry = test_quote_details_api()
    
    if not quote_id:
        print("\n❌ Impossible de continuer sans devis de test")
        sys.exit(1)
    
    # Test de récupération des détails
    details = test_quote_details_retrieval(quote_id)
    
    # Test de l'endpoint de structure
    structure = test_structure_endpoint()
    
    # Sauvegarde des résultats
    save_results(details, structure, quote_id.replace("SAP-", ""))
    
    # Résumé final
    print("\n🎯 RÉSUMÉ DU TEST")
    print("=" * 60)
    
    if details and details.get("success"):
        quote_data = details.get("quote", {})
        lines_count = len(quote_data.get("lines", []))
        
        print(f"✅ Devis {quote_id} récupéré avec succès")
        print(f"📊 {lines_count} lignes de produits trouvées")
        print(f"🏗️  Structure d'édition disponible: {'✅' if structure else '❌'}")
        
        if lines_count > 0:
            print("\n🎉 SUCCESS! L'API de récupération des détails fonctionne")
            print("📝 Prochaine étape: Créer l'interface d'édition modal")
        else:
            print("\n⚠️  Détails récupérés mais aucune ligne de produit")
            print("🔍 Vérifier l'intégration SAP et la structure des devis")
    else:
        print(f"❌ Échec de récupération des détails pour {quote_id}")
        print("🔧 Vérifier les logs et la configuration SAP")

if __name__ == "__main__":
    main()