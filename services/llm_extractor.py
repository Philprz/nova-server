import os
import json
import httpx
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
import logging
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from datetime import datetime
load_dotenv()
logger = logging.getLogger("llm_extractor")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-sonnet-20240229")

class LLMExtractor:
    """
    Classe pour extraire des informations structurées à partir de texte en utilisant Claude
    """
    @retry(
        stop=stop_after_attempt(3),  # Réessaye Claude 3 fois
        wait=wait_exponential(multiplier=1, min=2, max=10),  # Attends 2s, 4s, 8s
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.RequestError)),
        reraise=True  # Relance si tout foire pour trigger le fallback
    )
    async def _call_claude(self, message: str):
        """Appel primary à Claude avec prompt système original."""
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
- Liste des produits avec codes/références, noms et quantités
Format JSON requis:
{
"products": [{"code": "CODE_PRODUIT", "name": "NOM_PRODUIT", "quantity": QUANTITÉ}]
}
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
        user_message = f"Voici la demande de devis à analyser: {message}"
        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        payload = {
            "model": ANTHROPIC_MODEL,
            "max_tokens": 1024,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_message}],
            "temperature": 0.0
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            return response.json()

    async def _call_openai(self, message: str):
        """Fallback à OpenAI."""
        logger.info("🔄 Switch to OpenAI fallback – Claude unavailable")
        # Prompt adapté pour OpenAI (copié de ton system_prompt Claude, mais en format messages)
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
- Liste des produits avec codes/références, noms et quantités
Format JSON requis:
{
"products": [{"code": "CODE_PRODUIT", "name": "NOM_PRODUIT", "quantity": QUANTITÉ}]
}
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

        user_message = f"Voici la demande de devis à analyser: {message}"

        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                json={
                    "model": OPENAI_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    "max_tokens": 1000,
                    "temperature": 0.0
                },
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]

    async def extract_quote_info(self, prompt: str) -> Dict[str, Any]:
        logger.error(f"🚨 FONCTION extract_quote_info APPELÉE AVEC: {prompt}")
        logger.info(f"Extraction d'informations de devis à partir de: {prompt}")

        try:
            response_data = await self._call_claude(prompt)
            claude_content = response_data.get("content", [{}])[0].get("text", "")
            logger.info(f"CONTENU CLAUDE EXTRAIT: {claude_content}")
            start_idx = claude_content.find("{")
            end_idx = claude_content.rfind("}") + 1
            if start_idx >= 0 and end_idx > start_idx:
                json_str = claude_content[start_idx:end_idx]
                logger.info(f"🔧 JSON EXTRAIT: {json_str}")
                extracted_data = json.loads(json_str)
                logger.info(f"EXTRACTION RÉUSSIE: {extracted_data}")
                action_type = extracted_data.get("action_type", "NON_DÉTECTÉ")
                logger.info(f"TYPE D'ACTION DÉTECTÉ: {action_type}")
                if action_type == "RECHERCHE_PRODUIT":
                    search_criteria = extracted_data.get('search_criteria', {})
                    logger.info(f"🔍 CRITÈRES DE RECHERCHE: {search_criteria}")
                elif action_type == "DEVIS":
                    client = extracted_data.get('client', 'Non spécifié')
                    products = extracted_data.get('products', [])
                    logger.info(f"CLIENT DEVIS: {client}")
                    logger.info(f"PRODUITS DEVIS: {products}")
                return extracted_data
            else:
                logger.error("Impossible de trouver du JSON dans la réponse Claude")
                return {"error": "Format de réponse invalide - pas de JSON trouvé"}
        except Exception as e:
            logger.error(f"❌ Claude failed after retries: {str(e)} – Falling back to OpenAI")
            if not OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY not set – Cannot fallback")
            openai_response = await self._call_openai(prompt)
            try:
                return json.loads(openai_response)
            except json.JSONDecodeError:
                logger.error("❌ OpenAI response not valid JSON")
                raise
    async def extract_product_search_criteria(self, product_name: str) -> Dict[str, Any]:
        """Extrait critères de recherche intelligents pour un produit"""
        
        system_prompt = """
    Tu es un assistant spécialisé dans l'identification de produits bureautiques.
    Analyse le nom de produit et extrais les critères de recherche SAP appropriés.

    Pour "Imprimante 49 ppm", extrais:
    - Catégorie: "Imprimante" 
    - Critères: ["laser", "49 ppm", "bureau"]
    - Mots-clés alternatifs: ["50 ppm", "48 ppm"] (proches)

    Format JSON:
    {
    "category": "TYPE_PRODUIT",
    "main_keywords": ["mot1", "mot2"],
    "technical_specs": {"vitesse": "49 ppm", "type": "laser"},
    "alternative_keywords": ["alternatives proches"]
    }
    """
        
        user_message = f"Analyse ce produit: {product_name}"
        
        try:
            response = await self._call_claude_with_system(system_prompt, user_message)
            return json.loads(response)
        except Exception as e:
            logger.error(f"Erreur extraction critères: {e}")
            return {"category": product_name, "main_keywords": [product_name]}
    def _extract_json_from_response(self, content: str) -> Dict[str, Any]:
        """Extrait et parse le JSON de la réponse LLM."""
        start_idx = content.find("{")
        end_idx = content.rfind("}") + 1
        if start_idx >= 0 and end_idx > start_idx:
            json_str = content[start_idx:end_idx]
            try:
                return json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.error(f"❌ Erreur parsing JSON: {str(e)}")
                return None
        else:
            logger.error("Impossible de trouver du JSON dans la réponse")
            return None

    async def extract_client_info_from_text(self, user_text: str) -> Dict[str, Any]:
        try:
            system_prompt = """
    Tu es NOVA, un assistant spécialisé dans l'extraction d'informations client.

    Analyse le texte utilisateur et extrait UNIQUEMENT les informations client disponibles.

    INFORMATIONS À RECHERCHER :
    - Nom de l'entreprise/société
    - Nom de la personne de contact
    - Ville/localisation  
    - SIRET (si mentionné)
    - Email de contact
    - Téléphone de contact
    - Adresse complète (si disponible)

    Réponds UNIQUEMENT au format JSON suivant:
    {
    "success": true/false,
    "client_data": {
    "company_name": "NOM_ENTREPRISE",
    "contact_name": "NOM_CONTACT", 
    "city": "VILLE",
    "siret": "SIRET_SI_FOURNI",
    "email": "EMAIL_SI_FOURNI",
    "phone": "TELEPHONE_SI_FOURNI",
    "address": "ADRESSE_SI_FOURNIE"
    },
    "confidence": 0-100,
    "missing_fields": ["champs_manquants"]
    }

    Si aucune information client n'est détectable, success = false.
    """
            user_message = f"Texte à analyser pour extraction client: {user_text}"
            response = await self._call_claude(user_message)
            if response and isinstance(response, dict) and "content" in response:
                content = response.get("content", [{}])[0].get("text", "")
                extracted_json = self._extract_json_from_response(content)
                if extracted_json:
                    logger.info(f"✅ Extraction client réussie: {extracted_json}")
                    return extracted_json
                else:
                    logger.warning("⚠️ JSON non valide dans la réponse Claude")
                    return {"success": False, "error": "Format de réponse invalide"}
            else:
                return {"success": False, "error": "Erreur communication LLM"}
        except Exception as e:
            logger.error(f"❌ Erreur extraction client: {e}")
            return {"success": False, "error": str(e)}


    async def extract_quote_request(self, text_input: str) -> Dict[str, Any]:
        """
        Méthode de compatibilité - utilise extract_quote_info en interne
        Correction pour l'erreur AttributeError 'extract_quote_request'
        """
        try:
            logger.info("extract_quote_request appelée, redirection vers extract_quote_info")
            result = await self.extract_quote_info(text_input)
            
            # Adapter le format si nécessaire pour compatibilité
            return {
                "success": True if "error" not in result else False,
                "timestamp": datetime.now().isoformat(),
                "extraction_type": "quote_request",
                "raw_input": text_input,
                "extracted_info": result,
                "confidence_score": 85.0,  # Score par défaut
                "extraction_notes": ["Extraction via LLM réussie"]
            }
        except Exception as e:
            logger.error(f"Erreur extract_quote_request: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "extraction_type": "quote_request",
                "timestamp": datetime.now().isoformat()
            }

    async def extract_customer_data(self, text_input: str) -> Dict[str, Any]:
        """
        Extrait spécifiquement les données client
        Correction pour les erreurs de méthodes manquantes
        """
        try:
            logger.info("Extraction de données client démarrée")
            result = await self.extract_client_info_from_text(text_input)
            
            return {
                "success": result.get("success", False),
                "extraction_type": "customer_data",
                "customer_info": result.get("client_data", {}),
                "confidence_score": result.get("confidence", 0),
                "missing_fields": result.get("missing_fields", []),
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Erreur extraction données client: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "extraction_type": "customer_data"
            }

    def get_supported_extractions(self) -> List[str]:
        """Retourne la liste des types d'extraction supportés"""
        return [
            "quote_request",
            "customer_data", 
            "product_search",
            "contact_info",
            "stock_inquiry"
        ]

    async def extract_product_search(self, text_input: str) -> Dict[str, Any]:
        """
        Extrait les critères de recherche de produits
        """
        try:
            logger.info("Extraction de critères de recherche produit")
            result = await self.extract_quote_info(text_input)
            
            if result.get("action_type") == "RECHERCHE_PRODUIT":
                return {
                    "success": True,
                    "extraction_type": "product_search",
                    "search_criteria": result.get("search_criteria", {}),
                    "query_details": result.get("query_details", ""),
                    "timestamp": datetime.now().isoformat()
                }
            else:
                return {
                    "success": False,
                    "error": "Pas de critères de recherche produit détectés",
                    "extraction_type": "product_search"
                }
        except Exception as e:
            logger.error(f"Erreur extraction recherche produit: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "extraction_type": "product_search"
            }

# ====
# FACTORY PATTERN ET INSTANCE GLOBALE  
# ====

# Instance globale de l'extracteur
_llm_extractor: Optional['LLMExtractor'] = None

def get_llm_extractor() -> LLMExtractor:
    """
    Factory pattern pour obtenir l'instance de l'extracteur LLM
    Singleton pattern pour éviter les connexions multiples
    """
    global _llm_extractor
    if _llm_extractor is None:
        _llm_extractor = LLMExtractor()
        logger.info("Nouvelle instance LLMExtractor créée")
    return _llm_extractor

