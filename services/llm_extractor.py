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

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json=payload
                )

                if response.status_code != 200:
                    error_detail = response.json()
                    logger.error(f"Détail erreur API: {error_detail}")
                    return {"error": f"Erreur API Claude: {error_detail}"}

                result = response.json()

                # Validation des données extraites
                if "content" not in result:
                    logger.error("Réponse API invalide: contenu manquant")
                    return {"error": "Réponse API invalide: contenu manquant"}

                content = result["content"][0]["text"]
                                
                # Extraire les données JSON de la réponse
                try:
                    # Trouver les délimiteurs JSON dans la réponse
                    start_idx = content.find("{")
                    end_idx = content.rfind("}") + 1
                    
                    if start_idx >= 0 and end_idx > start_idx:
                        json_str = content[start_idx:end_idx]
                        extracted_data = json.loads(json_str)
                        logger.info(f"Extraction réussie: {extracted_data}")
                        return extracted_data
                    else:
                        logger.error("Impossible de trouver du JSON dans la réponse")
                        return {"error": "Format de réponse invalide"}
                except json.JSONDecodeError:
                    logger.error("Erreur de décodage JSON")
                    return {"error": "Erreur de décodage JSON"}

        except Exception as e:
            logger.error(f"Erreur lors de l'extraction des informations de devis: {e}")
            return {"error": f"Erreur lors de l'extraction des informations de devis: {e}"}