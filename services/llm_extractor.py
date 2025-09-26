# services/llm_extractor.py - VERSION NOVA-SERVER-TEST
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
    
    def _extract_client_from_prompt(self, prompt: str) -> str:
        """Extrait le nom du client depuis le prompt original"""
        import re
        
        # Chercher des patterns clients courants
        patterns = [
            r'pour\s+([A-Z][A-Za-z]+)',
            r'client\s+([A-Z][A-Za-z]+)',
            r'société\s+([A-Z][A-Za-z]+)',
            r'entreprise\s+([A-Z][A-Za-z]+)',
            r'([A-Z][A-Za-z]+)\s+souhaite',
            r'([A-Z][A-Za-z]+)\s+demande'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, prompt)
            if match:
                client_name = match.group(1).strip()
                if len(client_name) > 2:  # Éviter les mots courts
                    return client_name
        
        return ""
    

    async def extract_quote_info(self, prompt: str) -> Dict[str, Any]:
        logger.debug(f"FONCTION extract_quote_info APPELÉE AVEC: {prompt}")
        logger.info(f"Extraction d'informations de devis à partir de: {prompt}")

        def _strip_code_fences(txt: str) -> str:
            t = txt.strip()
            if t.startswith("```"):
                # supprime ```lang\n ... \n```
                t = t.split("```", 2)
                if len(t) == 3:
                    return t[1].split("\n", 1)[-1]
            return txt

        def _extract_json_from_text(txt: str) -> Dict[str, Any]:
            """1) tente json direct ; 2) tente premier bloc { ... } ; sinon ValueError"""
            raw = _strip_code_fences(txt)
            # essai direct
            try:
                return json.loads(raw)
            except Exception:
                pass
            # essai bloc
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(raw[start:end])
            raise ValueError("Aucun JSON détecté dans la réponse LLM")

        try:
            # 1) Appel principal (Claude)
            response_data = await self._call_claude(prompt)
            claude_text = (response_data.get("content") or [{}])[0].get("text", "") or ""
            extracted: Dict[str, Any] = _extract_json_from_text(claude_text)
            logger.info(f"EXTRACTION RÉUSSIE: {extracted}")

        except Exception as e:
            logger.error(f"❌ Claude échoué: {e} – fallback OpenAI")
            if not OPENAI_API_KEY:
                return {"error": f"Extraction impossible (fallback indisponible): {e}"}

            # 2) Fallback OpenAI
            try:
                openai_payload = await self._call_openai(prompt)
                openai_text = (
                    (openai_payload.get("text") or "") or
                    ((openai_payload.get("choices") or [{}])[0].get("message", {}) or {}).get("content", "") or
                    ""
                )
                extracted = _extract_json_from_text(openai_text)
                logger.info(f"EXTRACTION RÉUSSIE (fallback OpenAI): {extracted}")
            except Exception as e2:
                logger.error(f"❌ Fallback OpenAI échoué: {e2}")
                return {"error": f"Format de réponse invalide – pas de JSON trouvé ({e2})"}

        # 3) Normalisation & compléments
        action = (extracted.get("action_type") or "").upper() or "AUTRE"
        extracted["action_type"] = action

        if action == "DEVIS":
            if not extracted.get("client"):
                inferred = (self._extract_client_from_prompt(prompt) or "").strip()
                if inferred:
                    extracted["client"] = inferred
            extracted["products"] = extracted.get("products") or []

        elif action == "RECHERCHE_PRODUIT":
            if not extracted.get("client"):
                inferred = (self._extract_client_from_prompt(prompt) or "").strip()
                if inferred:
                    extracted["client"] = inferred
            extracted["search_criteria"] = extracted.get("search_criteria") or {}

        # 4) Retour final
        return extracted

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
        
    async def extract_suggestion_list(self, prompt: str) -> List[str]:
        """Extrait une liste de suggestions contextuelles à partir d'un prompt donné."""
        try:
            system_prompt = """
            Tu es NOVA, assistant intelligent. Génère 4-5 suggestions courtes et pertinentes.
            RÈGLES STRICTES :
            - Format exact : "💡 [action courte]"
            - Maximum 8 mots par suggestion
            - Suggestions ACTIONABLES et PERTINENTES
            - Éviter les généralités
            - Retourner SEULEMENT une liste JSON de strings

            Exemple de réponse attendue :
            ["💡 Ajouter la garantie étendue", "💡 Voir les détails du devis", "💡 Modifier les quantités", "💡 Créer un devis similaire"]
            """

            response = await self._call_claude(f"{system_prompt}\n\nCONTEXTE:\n{prompt}")

            # Parser la réponse JSON
            import json
            import re

            # Recherche d'une liste JSON dans la réponse
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                try:
                    suggestions = json.loads(json_match.group())
                    return [
                        suggestion for suggestion in suggestions
                        if isinstance(suggestion, str) and suggestion.startswith("💡")
                    ][:5]

                except json.JSONDecodeError:
                    logger.warning("Réponse JSON invalide dans l'extraction des suggestions.")
                    return []

        except Exception as e:
            logger.warning(f"Erreur lors de l'extraction des suggestions : {e}")
            return []

        return []

    async def extract_with_claude(self, text: str) -> Dict[str, Any]:
        """
        Méthode de compatibilité pour LocalProductSearchService
        Utilise extract_quote_info en interne et adapte le format
        """
        try:
            logger.info(f"extract_with_claude appelée avec: {text}")
            
            # Réutiliser la logique existante
            result = await self.extract_quote_info(text)
            
            # Adapter le format pour LocalProductSearchService
            if result.get("action_type") == "RECHERCHE_PRODUIT":
                search_criteria = result.get("search_criteria", {})
                return {
                    "found": True,
                    "products": [],  # Sera rempli par la recherche PostgreSQL
                    "search_criteria": search_criteria,
                    "category": search_criteria.get("category", ""),
                    "characteristics": search_criteria.get("characteristics", []),
                    "client": result.get("client", ""),
                    "confidence": 85.0
                }
            elif result.get("action_type") == "DEVIS":
                products = result.get("products", [])
                return {
                    "found": len(products) > 0,
                    "products": products,
                    "client": result.get("client", ""),
                    "action_type": "DEVIS",
                    "confidence": 90.0
                }
            else:
                # Fallback pour autres types
                return {
                    "found": False,
                    "products": [],
                    "reason": f"Action type '{result.get('action_type')}' non supportée pour recherche produit",
                    "confidence": 0.0
                }
                
        except Exception as e:
            logger.error(f"Erreur extract_with_claude: {str(e)}")
            return {
                "found": False,
                "products": [],
                "error": str(e),
                "confidence": 0.0
            }    
    def _extract_client_from_original_prompt(self, prompt: str) -> str:
        """Extrait le nom du client depuis le prompt original avec patterns robustes"""
        import re
        
        # Patterns pour détecter les clients (ordre de priorité)
        patterns = [
            r'(?:pour|chez|client)\s+([A-Z][A-Z0-9\s]+?)(?:\s+avec|\s+de|\s*,|\s*$)',
            r'([A-Z][A-Z0-9\s]{2,15})\s+(?:souhaite|demande|veut)',
            r'société\s+([A-Z][A-Za-z\s]+)',
            r'entreprise\s+([A-Z][A-Za-z\s]+)',
            r'([A-Z]{3,}(?:\s+[A-Z]+)*)'  # Mots en majuscules
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, prompt)
            for match in matches:
                client_name = match.strip()
                # Filtrer les mots courts et les mots courants
                if (len(client_name) >= 3 and 
                    client_name.upper() not in ['AVEC', 'POUR', 'DANS', 'SUR', 'PAR', 'DEVIS']):
                    logger.info(f"Client détecté avec pattern '{pattern}': {client_name}")
                    return client_name
        
        return ""        
    
    def _extract_json_from_response(self, content: str) -> Dict[str, Any]:
        """Extrait et parse le JSON de la réponse LLM."""
        start_idx = content.find("{")
        end_idx = content.rfind("}") + 1
        if start_idx >= 0 and end_idx > start_idx:
            json_str = content[start_idx:end_idx]
            try:
                return json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.error(f"Erreur parsing JSON: {str(e)}")
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
                    logger.info(f"Extraction client réussie: {extracted_json}")
                    return extracted_json
                else:
                    logger.warning("JSON non valide dans la réponse Claude")
                    return {"success": False, "error": "Format de réponse invalide"}
            else:
                return {"success": False, "error": "Erreur communication LLM"}
        except Exception as e:
            logger.error(f"Erreur extraction client: {e}")
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

