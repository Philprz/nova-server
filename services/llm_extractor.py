# services/llm_extractor.py

import os
import json
import httpx
from typing import Dict, Any
from dotenv import load_dotenv
import logging
load_dotenv()
logger = logging.getLogger("llm_extractor")

class LLMExtractor:
    """
    Classe pour extraire des informations structurées à partir de texte en utilisant Claude
    """
    
    @staticmethod
    async def extract_quote_info(prompt: str) -> Dict[str, Any]:
        # 🚨 LOG FORCÉ POUR TEST - NIVEAU ERROR pour s'assurer qu'il s'affiche
        logger.error(f"🚨 FONCTION extract_quote_info APPELÉE AVEC: {prompt}")
        logger.info(f"Extraction d'informations de devis à partir de: {prompt}")

        # Construire le prompt pour Claude
        system_prompt = """
        Tu es NOVA, un assistant commercial intelligent qui comprend différents types de demandes.

        Analyse la demande utilisateur et détermine le TYPE D'ACTION puis extrais les informations :

        TYPES D'ACTIONS POSSIBLES :
        1. "DEVIS" - Génération de devis/proposition commerciale
        2. "RECHERCHE_PRODUIT" - Recherche de produits par caractéristiques
        3. "INFO_CLIENT" - Consultation d'informations client
        4. "CONSULTATION_STOCK" - Vérification de stock
        5. "AUTRE" - Autre demande

        Pour une demande de DEVIS, extrais :
        - Nom du client
        - Liste des produits avec codes/références et quantités

        Pour une RECHERCHE_PRODUIT, extrais :
        - Caractéristiques recherchées (vitesse, type, fonctionnalités...)
        - Catégorie de produit (imprimante, ordinateur, etc.)
        - Critères spécifiques (recto-verso, réseau, laser, etc.)

        Réponds UNIQUEMENT au format JSON suivant:
        {
            "action_type": "DEVIS|RECHERCHE_PRODUIT|INFO_CLIENT|CONSULTATION_STOCK|AUTRE",
            "client": "NOM_DU_CLIENT (si pertinent)",
            "products": [{"code": "CODE_PRODUIT", "quantity": QUANTITÉ}] (pour DEVIS),
            "search_criteria": {
                "category": "TYPE_PRODUIT",
                "characteristics": ["caractéristique1", "caractéristique2"],
                "specifications": {"vitesse": "50 ppm", "type": "laser", "fonctions": ["recto-verso", "réseau"]}
            } (pour RECHERCHE_PRODUIT),
            "query_details": "détails spécifiques de la demande"
        }
        """

        user_message = f"Voici la demande de devis à analyser: {prompt}"

        try:
            # Appel API à Claude
            api_key = os.getenv("ANTHROPIC_API_KEY")

            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }

            # CORRECTION ICI: system est maintenant un paramètre de premier niveau
            # et non plus un message avec le rôle "system"
            payload = {
                "model": "claude-3-7-sonnet-20250219",
                "max_tokens": 1024,
                "system": system_prompt,  # Paramètre system de premier niveau
                "messages": [
                    {"role": "user", "content": user_message}
                ],
                "temperature": 0.0  # Réponse déterministe pour extraction précise
            }
            
            # 🔍 DEBUG: Log de la requête envoyée à Claude
            logger.info(f"🤖 PROMPT SYSTÈME ENVOYÉ: {system_prompt}")
            logger.info(f"📝 MESSAGE UTILISATEUR: {user_message}")
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json=payload
                )
                
                # 🔍 DEBUG DÉTAILLÉ - Réponse brute de Claude
                logger.info(f"📊 STATUS CODE: {response.status_code}")
                logger.info(f"🤖 RÉPONSE BRUTE CLAUDE: {response.text}")
                
                # Vérifier le code de statut
                if response.status_code != 200:
                    try:
                        error_detail = response.json()
                        logger.error(f"Détail erreur API: {error_detail}")
                        return {"error": f"Erreur API Claude: {error_detail}"}
                    except:
                        logger.error(f"Erreur HTTP {response.status_code}: {response.text}")
                        return {"error": f"Erreur HTTP {response.status_code}"}

                # Parser la réponse JSON
                try:
                    response_data = response.json()
                    
                    # Validation des données de réponse
                    if "content" not in response_data:
                        logger.error("Réponse API invalide: contenu manquant")
                        return {"error": "Réponse API invalide: contenu manquant"}
                    
                    if not response_data["content"] or len(response_data["content"]) == 0:
                        logger.error("Réponse API invalide: contenu vide")
                        return {"error": "Réponse API invalide: contenu vide"}
                    
                    # Extraire le contenu textuel de Claude
                    claude_content = response_data["content"][0].get("text", "")
                    logger.info(f"🎯 CONTENU CLAUDE EXTRAIT: {claude_content}")
                    
                    # Extraire les données JSON de la réponse Claude
                    try:
                        # Trouver les délimiteurs JSON dans la réponse
                        start_idx = claude_content.find("{")
                        end_idx = claude_content.rfind("}") + 1
                        
                        if start_idx >= 0 and end_idx > start_idx:
                            json_str = claude_content[start_idx:end_idx]
                            logger.info(f"🔧 JSON EXTRAIT: {json_str}")
                            
                            extracted_data = json.loads(json_str)
                            logger.info(f"✅ EXTRACTION RÉUSSIE: {extracted_data}")
                            
                            # 🔍 DEBUG : Vérifier le type d'action détecté
                            action_type = extracted_data.get("action_type", "NON_DÉTECTÉ")
                            logger.info(f"🎯 TYPE D'ACTION DÉTECTÉ: {action_type}")
                            
                            if action_type == "RECHERCHE_PRODUIT":
                                search_criteria = extracted_data.get('search_criteria', {})
                                logger.info(f"🔍 CRITÈRES DE RECHERCHE: {search_criteria}")
                            elif action_type == "DEVIS":
                                client = extracted_data.get('client', 'Non spécifié')
                                products = extracted_data.get('products', [])
                                logger.info(f"📋 CLIENT DEVIS: {client}")
                                logger.info(f"📦 PRODUITS DEVIS: {products}")
                            
                            return extracted_data
                        else:
                            logger.error("Impossible de trouver du JSON dans la réponse Claude")
                            logger.error(f"📋 CONTENU BRUT SANS JSON: {claude_content}")
                            return {"error": "Format de réponse invalide - pas de JSON trouvé"}
                            
                    except json.JSONDecodeError as json_error:
                        logger.error(f"❌ ERREUR DE DÉCODAGE JSON: {json_error}")
                        logger.error(f"📋 CONTENU NON-JSON: {claude_content}")
                        return {"error": f"Erreur de décodage JSON: {json_error}"}
                        
                except json.JSONDecodeError as response_error:
                    logger.error(f"❌ ERREUR PARSING RÉPONSE HTTP: {response_error}")
                    logger.error(f"📋 RÉPONSE BRUTE: {response.text}")
                    return {"error": f"Erreur parsing réponse HTTP: {response_error}"}
                    
        except httpx.TimeoutException:
            logger.error("❌ TIMEOUT lors de l'appel à Claude API")
            return {"error": "Timeout lors de l'appel à Claude API"}
            
        except httpx.ConnectError:
            logger.error("❌ ERREUR DE CONNEXION à Claude API")
            return {"error": "Erreur de connexion à Claude API"}
            
        except Exception as e:
            logger.error(f"❌ ERREUR GÉNÉRALE lors de l'extraction: {str(e)}")
            logger.error(f"📋 TYPE D'ERREUR: {type(e).__name__}")
            return {"error": f"Erreur lors de l'extraction des informations: {str(e)}"}