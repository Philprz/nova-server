#!/usr/bin/env python3
"""
Script d'analyse de la structure JSON des devis NOVA
Génère un devis et analyse ses champs éditables
"""

import json
import requests
from datetime import datetime
from typing import Dict, List, Any

class QuoteAnalyzer:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
    
    def generate_sample_quote(self, draft_mode: bool = True) -> Dict[str, Any]:
        """Génère un devis d'exemple pour analyser sa structure"""
        
        payload = {
            "prompt": "faire un devis pour 100 ref A00002 pour le client Edge Communications",
            "draft_mode": draft_mode
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/generate_quote",
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ Erreur API: {response.status_code}")
                print(f"Réponse: {response.text}")
                return {}
                
        except Exception as e:
            print(f"❌ Erreur lors de la génération: {e}")
            return {}
    
    def analyze_json_structure(self, data: Dict[str, Any], level: int = 0, path: str = "") -> Dict[str, Any]:
        """Analyse récursive de la structure JSON avec chemins complets"""
        
        analysis = {
            "editable_fields": [],
            "nested_objects": [],
            "arrays": [],
            "read_only_fields": []
        }
        
        for key, value in data.items():
            # Construction du chemin complet
            current_path = f"{path}.{key}" if path else key
            
            field_info = {
                "field": key,
                "type": type(value).__name__,
                "level": level,
                "path": current_path,
                "value_sample": self.get_value_sample(value)
            }
            
            # Détermine si le champ est éditable selon des critères business
            if self.is_editable_field(key, value, current_path):
                field_info["editable"] = True
                field_info["validation_rules"] = self.get_validation_rules(key, value)
                analysis["editable_fields"].append(field_info)
            else:
                field_info["editable"] = False
                analysis["read_only_fields"].append(field_info)
            
            # Analyse des objets imbriqués - RÉCURSION PROFONDE
            if isinstance(value, dict):
                sub_analysis = self.analyze_json_structure(value, level + 1, current_path)
                field_info["sub_analysis"] = sub_analysis
                
                # Remonte les champs éditables des sous-objets
                analysis["editable_fields"].extend(sub_analysis["editable_fields"])
                analysis["nested_objects"].extend(sub_analysis["nested_objects"])
                analysis["arrays"].extend(sub_analysis["arrays"])
                analysis["read_only_fields"].extend(sub_analysis["read_only_fields"])
                
                analysis["nested_objects"].append(field_info)
            
            # Analyse des tableaux avec exploration du contenu
            elif isinstance(value, list) and len(value) > 0:
                field_info["array_length"] = len(value)
                
                # Analyse du premier élément si c'est un objet
                if isinstance(value[0], dict):
                    item_analysis = self.analyze_json_structure(value[0], level + 1, f"{current_path}[0]")
                    field_info["item_structure"] = item_analysis
                    
                    # Remonte les champs éditables des éléments du tableau
                    for editable in item_analysis["editable_fields"]:
                        editable["is_array_item"] = True
                        editable["array_path"] = current_path
                    analysis["editable_fields"].extend(item_analysis["editable_fields"])
                    analysis["nested_objects"].extend(item_analysis["nested_objects"])
                    analysis["arrays"].extend(item_analysis["arrays"])
                    analysis["read_only_fields"].extend(item_analysis["read_only_fields"])
                
                # Échantillon des valeurs du tableau
                field_info["sample_values"] = [str(v)[:50] for v in value[:3]]
                analysis["arrays"].append(field_info)
        
        return analysis
    
    def get_value_sample(self, value: Any) -> str:
        """Retourne un échantillon de la valeur pour comprendre le contenu"""
        if isinstance(value, (dict, list)):
            return f"{type(value).__name__} ({len(value)} items)"
        elif isinstance(value, str) and len(value) > 50:
            return f"{value[:47]}..."
        else:
            return str(value)
    
    def is_editable_field(self, key: str, value: Any, path: str = "") -> bool:
        """Détermine si un champ devrait être éditable selon les règles business"""
        
        # Champs systèmes (non éditables)
        system_fields = {
            "id", "created_at", "updated_at", "version", "status_code", 
            "workflow_id", "processing_time", "timestamp", "request_id",
            "success", "quote_id", "salesforce_quote_id", "sap_doc_entry", "sap_doc_num"
        }
        
        # Champs business éditables prioritaires  
        editable_fields = {
            "quantity", "quantite", "price", "prix", "unit_price", "prix_unitaire",
            "discount", "remise", "comment", "commentaire", "description", "remarks",
            "delivery_date", "date_livraison", "payment_terms", "conditions_paiement",
            "total", "total_ht", "total_ttc", "tva", "vat", "reference", "ref",
            "itemcode", "item_code", "unitprice", "linetotal", "vatpercent",
            "companyname", "company_name", "cardname", "cardcode", "docdate",
            "contactperson", "address", "street", "city", "zipcode", "country",
            "phone", "email", "opportunity", "amount"
        }
        
        key_lower = key.lower()
        path_lower = path.lower()
        
        # Exclusions système
        if key_lower in system_fields:
            return False
        
        # Inclusions prioritaires
        if key_lower in editable_fields:
            return True
        
        # Champs dans sap_result ou salesforce_result (données métier)
        if "sap_result" in path_lower or "salesforce_result" in path_lower:
            # Champs contenant des mots-clés éditables
            editable_keywords = [
                "prix", "price", "quantit", "quantity", "remise", "discount", 
                "comment", "remark", "note", "desc", "total", "amount", "value",
                "date", "address", "phone", "email", "name", "contact"
            ]
            if any(keyword in key_lower for keyword in editable_keywords):
                return True
        
        # Types de données éditables pour les données métier
        if isinstance(value, (int, float, str)) and not key_lower.endswith("_id"):
            # Seulement dans les résultats SAP/Salesforce, pas dans les métadonnées
            if any(section in path_lower for section in ["sap_result", "salesforce_result", "document", "lines"]):
                return True
        
        return False
    
    def get_validation_rules(self, key: str, value: Any) -> Dict[str, Any]:
        """Retourne les règles de validation pour un champ"""
        
        rules = {"required": False, "type": type(value).__name__}
        key_lower = key.lower()
        
        # Règles spécifiques par type de champ
        if any(word in key_lower for word in ["quantit", "quantity"]):
            rules.update({
                "min_value": 1,
                "max_value": 999999,
                "step": 1,
                "required": True
            })
        
        elif any(word in key_lower for word in ["prix", "price", "total"]):
            rules.update({
                "min_value": 0.01,
                "max_value": 999999.99,
                "step": 0.01,
                "required": True,
                "currency": "EUR"
            })
        
        elif any(word in key_lower for word in ["remise", "discount"]):
            rules.update({
                "min_value": 0,
                "max_value": 100,
                "step": 0.01,
                "unit": "%"
            })
        
        elif key_lower in ["comment", "commentaire", "description"]:
            rules.update({
                "max_length": 500,
                "multiline": True
            })
        
        return rules
    
    def print_analysis(self, analysis: Dict[str, Any], title: str = "Analyse de Structure"):
        """Affiche l'analyse de manière formatée avec focus sur les données métier"""
        
        print(f"\n{'='*70}")
        print(f"📊 {title}")
        print(f"{'='*70}")
        
        # Séparation des champs par domaine
        metadata_fields = []
        business_fields = []
        
        for field in analysis["editable_fields"]:
            if any(section in field["path"] for section in ["sap_result", "salesforce_result"]):
                business_fields.append(field)
            else:
                metadata_fields.append(field)
        
        # Champs business éditables (priorité)
        if business_fields:
            print(f"\n✅ CHAMPS MÉTIER ÉDITABLES ({len(business_fields)})")
            print("-" * 50)
            
            # Groupement par contexte
            sap_fields = [f for f in business_fields if "sap_result" in f["path"]]
            sf_fields = [f for f in business_fields if "salesforce_result" in f["path"]]
            
            if sap_fields:
                print(f"\n   📋 SAP Business One ({len(sap_fields)} champs)")
                for field in sap_fields[:10]:  # Limite pour affichage
                    sample = field.get("value_sample", "")
                    print(f"     📝 {field['path']} ({field['type']}) = {sample}")
                    if "validation_rules" in field and field["validation_rules"].get("required"):
                        print("         ⚠️  Requis")
            
            if sf_fields:
                print(f"\n   🏢 Salesforce ({len(sf_fields)} champs)")
                for field in sf_fields[:10]:  # Limite pour affichage
                    sample = field.get("value_sample", "")
                    print(f"     📝 {field['path']} ({field['type']}) = {sample}")
        
        # Champs système/métadonnées 
        if metadata_fields:
            print(f"\n📊 MÉTADONNÉES ÉDITABLES ({len(metadata_fields)})")
            print("-" * 50)
            for field in metadata_fields[:5]:  # Limite pour affichage
                sample = field.get("value_sample", "")
                print(f"  📊 {field['path']} ({field['type']}) = {sample}")
        
        # Tableaux (lignes de produits, etc.)
        business_arrays = [a for a in analysis["arrays"] if any(section in a["path"] for section in ["sap_result", "salesforce_result"])]
        if business_arrays:
            print(f"\n📋 TABLEAUX/LISTES MÉTIER ({len(business_arrays)})")
            print("-" * 50)
            for array in business_arrays:
                print(f"  📦 {array['path']} ({array['array_length']} éléments)")
                if "item_structure" in array:
                    editable_count = len(array["item_structure"].get("editable_fields", []))
                    print(f"      Structure: {editable_count} champs éditables par élément")
                    
                    # Affiche quelques champs d'exemple
                    if editable_count > 0:
                        sample_fields = array["item_structure"]["editable_fields"][:3]
                        for sf in sample_fields:
                            print(f"        📝 {sf['field']} ({sf['type']})")
        
        # Statistiques générales
        total_editable = len(analysis["editable_fields"])
        total_readonly = len(analysis["read_only_fields"])
        total_arrays = len(analysis["arrays"])
        
        print("\n📊 STATISTIQUES GÉNÉRALES")
        print("-" * 50)
        print(f"  ✅ Total champs éditables: {total_editable}")
        print(f"  🔒 Total champs lecture seule: {total_readonly}")
        print(f"  📋 Total tableaux: {total_arrays}")
        print(f"  🎯 Champs métier: {len(business_fields)}")
        print(f"  📊 Métadonnées: {len(metadata_fields)}")

    def print_detailed_paths(self, analysis: Dict[str, Any]):
        """Affiche tous les chemins détaillés pour debug"""
        
        print("\n🔍 CHEMINS DÉTAILLÉS (DEBUG)")
        print("=" * 70)
        
        all_fields = analysis["editable_fields"] + analysis["read_only_fields"]
        all_fields.sort(key=lambda x: x["path"])
        
        for field in all_fields:
            status = "✅ ÉDITABLE" if field.get("editable", False) else "🔒 LECTURE SEULE"
            sample = field.get("value_sample", "")
            print(f"{status:15} | {field['path']:40} | {field['type']:10} | {sample}")
    
    def identify_key_business_objects(self, analysis: Dict[str, Any]) -> Dict[str, List]:
        """Identifie les objets métier clés pour l'édition"""
        
        key_objects = {
            "client_info": [],
            "quote_header": [],
            "product_lines": [],
            "pricing_totals": [],
            "dates_delivery": []
        }
        
        for field in analysis["editable_fields"]:
            path_lower = field["path"].lower()
            field_name = field["field"].lower()
            
            # Classification intelligente
            if any(word in path_lower for word in ["customer", "client", "cardname", "companyname"]):
                key_objects["client_info"].append(field)
            elif any(word in path_lower for word in ["lines", "items", "products"]) or any(word in field_name for word in ["quantity", "itemcode", "unitprice"]):
                key_objects["product_lines"].append(field)
            elif any(word in field_name for word in ["total", "amount", "subtotal", "taxtotal"]):
                key_objects["pricing_totals"].append(field)
            elif any(word in field_name for word in ["date", "delivery", "shipdate"]):
                key_objects["dates_delivery"].append(field)
            else:
                key_objects["quote_header"].append(field)
        
        return key_objects
    
    def generate_field_config(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Génère la configuration des champs pour l'interface d'édition"""
        
        config = {
            "form_sections": [],
            "validation_schema": {},
            "field_groups": {
                "client_info": [],
                "product_lines": [],
                "pricing": [],
                "comments": []
            }
        }
        
        # Classification des champs par groupe
        for field in analysis["editable_fields"]:
            field_name = field["field"].lower()
            
            if any(word in field_name for word in ["client", "customer", "company"]):
                config["field_groups"]["client_info"].append(field)
            elif any(word in field_name for word in ["product", "item", "line", "ref"]):
                config["field_groups"]["product_lines"].append(field)
            elif any(word in field_name for word in ["prix", "price", "total", "remise", "discount"]):
                config["field_groups"]["pricing"].append(field)
            elif any(word in field_name for word in ["comment", "note", "description"]):
                config["field_groups"]["comments"].append(field)
            
            # Schéma de validation
            config["validation_schema"][field["field"]] = field.get("validation_rules", {})
        
        return config

def main():
    """Fonction principale"""
    print("🚀 Analyse APPROFONDIE de la Structure JSON des Devis NOVA")
    print("=" * 70)
    
    analyzer = QuoteAnalyzer()
    
    # Test de connexion
    try:
        health_response = requests.get(f"{analyzer.base_url}/health", timeout=5)
        if health_response.status_code != 200:
            print("❌ API NOVA non accessible. Vérifiez que le serveur est démarré.")
            return
    except Exception:
        print("❌ Impossible de se connecter à l'API NOVA")
        print("   Démarrez le serveur avec: uvicorn main:app --reload")
        return
    
    print("✅ Connexion API OK")
    
    # Génération d'un devis en mode Draft
    print("\n📋 Génération d'un devis d'exemple...")
    quote_data = analyzer.generate_sample_quote(draft_mode=True)
    
    if not quote_data:
        print("❌ Impossible de générer un devis d'exemple")
        return
    
    print("✅ Devis généré avec succès")
    print(f"📊 Taille de la réponse: {len(str(quote_data))} caractères")
    
    # Affichage de la structure de haut niveau
    print("\n📋 Structure de haut niveau:")
    for key, value in quote_data.items():
        print(f"  📁 {key}: {type(value).__name__} ({len(str(value))} chars)")
    
    # Sauvegarde du JSON brut
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"quote_sample_detailed_{timestamp}.json"
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(quote_data, f, indent=2, ensure_ascii=False)
    
    print(f"💾 JSON brut sauvegardé: {filename}")
    
    # Analyse APPROFONDIE de la structure
    print("\n🔍 Analyse APPROFONDIE de la structure...")
    analysis = analyzer.analyze_json_structure(quote_data)
    
    # Affichage de l'analyse focalisée métier
    analyzer.print_analysis(analysis, "Analyse Détaillée - Focus Métier")
    
    # Identification des objets métier clés
    print("\n🎯 OBJETS MÉTIER CLÉS IDENTIFIÉS")
    print("=" * 70)
    
    key_objects = analyzer.identify_key_business_objects(analysis)
    
    for category, fields in key_objects.items():
        if fields:
            print(f"\n📋 {category.upper().replace('_', ' ')} ({len(fields)} champs)")
            print("-" * 50)
            for field in fields[:5]:  # Limite à 5 par catégorie
                sample = field.get("value_sample", "")
                print(f"  📝 {field['field']} = {sample}")
    
    # Affichage détaillé pour debug (optionnel)
    print("\n🤔 Voulez-vous voir tous les chemins détaillés ? (o/n)")
    choice = input().lower().strip()
    if choice in ['o', 'oui', 'y', 'yes']:
        analyzer.print_detailed_paths(analysis)
    
    # Génération de la configuration
    field_config = analyzer.generate_field_config(analysis)
    
    # Ajout des objets métier clés à la config
    field_config["business_objects"] = key_objects
    
    config_filename = f"field_config_detailed_{timestamp}.json"
    with open(config_filename, 'w', encoding='utf-8') as f:
        json.dump(field_config, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Configuration métier sauvegardée: {config_filename}")
    
    # Recommandations spécialisées
    print("\n💡 RECOMMANDATIONS SPÉCIALISÉES")
    print("=" * 70)
    
    business_editable = len([f for f in analysis["editable_fields"] if any(section in f["path"] for section in ["sap_result", "salesforce_result"])])
    business_arrays = len([a for a in analysis["arrays"] if any(section in a["path"] for section in ["sap_result", "salesforce_result"])])
    
    print(f"📊 {business_editable} champs métier éditables identifiés")
    print(f"📋 {business_arrays} tableaux métier (lignes de produits)")
    
    if business_editable > 0:
        print("✅ Structure métier compatible avec interface d'édition avancée")
        print("\n🎯 PRIORITÉS POUR L'INTERFACE D'ÉDITION:")
        print("   1. 🏢 Informations client (nom, adresse, contact)")
        print("   2. 📦 Lignes de produits (quantité, prix, remise)")
        print("   3. 💰 Totaux et calculs (sous-total, TVA, total)")
        print("   4. 📅 Dates (livraison, validité)")
        print("   5. 💬 Commentaires et notes")
        
        print("\n🛠️  PROCHAINES ÉTAPES TECHNIQUES:")
        print("   1. Créer les composants d'édition par type de champ")
        print("   2. Implémenter la validation en temps réel")
        print("   3. Gérer les recalculs automatiques (prix * quantité)")
        print("   4. Interface modal avec onglets par section")
        print("   5. API de mise à jour avec validation SAP/Salesforce")
    else:
        print("⚠️  Structure trop simple - vérifier l'intégration SAP/Salesforce")
        print("   Assurez-vous que le devis contient les données complètes")

if __name__ == "__main__":
    main()