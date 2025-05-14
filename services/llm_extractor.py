# services/llm_extractor.py

import os
import json
import httpx
from typing import Dict, Any, List
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
        """
        Extrait les informations de devis à partir d'une demande en langage naturel
        
        Args:
            prompt: Demande en langage naturel
            
        Returns:
            Informations structurées (client, produits, quantités)
        """
        logger.info(f"Extraction d'informations de devis à partir de: {prompt}")
        
        # Construire le prompt pour Claude
        system_prompt = """
        Tu es un assistant spécialisé dans l'extraction d'informations pour les devis.
        Extrais les informations suivantes de la demande de devis:
        1. Nom du client
        2. Liste des produits avec leurs codes/références et quantités
        
        Réponds UNIQUEMENT au format JSON suivant:
        {
            "client": "NOM_DU_CLIENT",
            "products": [
                {"code": "CODE_PRODUIT", "quantity": QUANTITÉ},
                ...
            ]
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
            
            payload = {
                "model": "claude-3-opus-20240229",
                "max_tokens": 1000,
                "messages": [
                    {"role": "system", "content": system_prompt},
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
                
                response.raise_for_status()
                result = response.json()
                
                # Extraire la réponse de Claude
                content = result["content"][0]["text"]
                
                # Analyser le JSON de la réponse
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
        except Exception as e:
            logger.error(f"Erreur lors de l'extraction: {str(e)}")
            return {"error": str(e)}