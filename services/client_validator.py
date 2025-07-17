# services/client_validator.py
"""
Module de validation complète des données client
Version POC avec validations SIRET, doublons, normalisation
"""

import re
import logging
from typing import Dict, Any, List
from datetime import datetime, timedelta # Ajout de timedelta
import os # Ajout de os
import httpx # Ajout de httpx
# NOUVEAU : Import du service de recherche d'entreprises
from .company_search_service import company_search_service
# Importer les dépendances avec gestion des erreurs
try:
    from fuzzywuzzy import fuzz
    FUZZYWUZZY_AVAILABLE = True
except ImportError:
    FUZZYWUZZY_AVAILABLE = False
    print("fuzzywuzzy non disponible - controle de doublons limite")

try:
    from email_validator import validate_email, EmailNotValidError
    EMAIL_VALIDATOR_AVAILABLE = True
except ImportError:
    EMAIL_VALIDATOR_AVAILABLE = False
    print("email-validator non disponible - validation email basique")

# Configuration du cache pour les requêtes HTTP
try:
    import requests_cache
    HTTP_CACHE_AVAILABLE = True
except ImportError:
    HTTP_CACHE_AVAILABLE = False
    print("requests-cache non disponible - les appels API ne seront pas mis en cache")

logger = logging.getLogger(__name__)
# Constantes pour l'API INSEE
INSEE_TOKEN_URL = "https://api.insee.fr/token"
INSEE_API_BASE_URL = "https://api.insee.fr/entreprises/sirene/V3.11"
# Constante pour l'API Adresse Gouv
API_ADRESSE_GOUV_URL = "https://api-adresse.data.gouv.fr/search/"
class ClientValidator:
    """Validateur complet pour les données client"""
    
    def __init__(self):
        # self.api_cache = {} # Remplacé par requests-cache si disponible
        self.validation_stats = {
            "total_validations": 0,
            "successful_validations": 0,
            "failed_validations": 0
        }
        
        self.insee_consumer_key = os.getenv("INSEE_CONSUMER_KEY")
        self.insee_consumer_secret = os.getenv("INSEE_CONSUMER_SECRET")
        self.insee_access_token = None
        self.insee_token_expires_at = datetime.now()

        # Initialisation du client HTTP avec cache si disponible
        if HTTP_CACHE_AVAILABLE:
            # Cache les requêtes pour 1 heure, expire les anciennes après 1 jour
            # Les erreurs 5xx ne sont pas mises en cache par défaut
            self.http_client = httpx.AsyncClient(
                event_hooks={'response': [self._raise_on_4xx_5xx]}
            )
            self.cached_http_client = requests_cache.CachedSession(
                cache_name='api_cache',
                backend='sqlite',
                expire_after=timedelta(hours=1),
                allowable_codes=[200], # Cache seulement les succès
                old_data_on_error=True # Utilise le cache si l'API est down
            )
            # Monkey patch pour utiliser requests_cache avec httpx de manière synchrone pour le token
            # Pour les appels asynchrones, nous gérerons le cache manuellement ou via une lib compatible
        else:
            self.http_client = httpx.AsyncClient(
                 event_hooks={'response': [self._raise_on_4xx_5xx]}
            )
        
        if not self.insee_consumer_key or not self.insee_consumer_secret:
            logger.warning("INSEE_CONSUMER_KEY ou INSEE_CONSUMER_SECRET non configurés. Validation INSEE désactivée.")

    async def _raise_on_4xx_5xx(self, response):
        """Hook pour httpx pour lever une exception sur les erreurs HTTP."""
        # L'objectif principal de ce hook est de s'assurer que les erreurs HTTP
        # sont levées pour que le code appelant puisse les intercepter.
        # Les détails de l'erreur (comme le corps de la réponse) seront gérés
        # par le bloc `except` spécifique dans la méthode appelante.
        response.raise_for_status()

    async def _get_insee_token(self) -> str | None:
        """Récupère ou renouvelle le token d'accès INSEE."""
        if not self.insee_consumer_key or not self.insee_consumer_secret:
            return None

        if self.insee_access_token and datetime.now() < self.insee_token_expires_at:
            return self.insee_access_token

        logger.info("Demande d'un nouveau token d'accès INSEE...")
        auth = (self.insee_consumer_key, self.insee_consumer_secret)
        data = {"grant_type": "client_credentials"}
        
        try:
            # Utilisation d'un client httpx synchrone pour cette partie critique ou gestion manuelle du cache
            # Pour simplifier, appel direct sans cache spécifique pour le token ici, car géré par l'expiration.
            async with httpx.AsyncClient() as client: # Client temporaire pour le token
                response = await client.post(INSEE_TOKEN_URL, auth=auth, data=data)
            response.raise_for_status()
            
            token_data = response.json()
            self.insee_access_token = token_data["access_token"]
            # Mettre une marge de 60 secondes avant l'expiration réelle
            self.insee_token_expires_at = datetime.now() + timedelta(seconds=token_data["expires_in"] - 60)
            logger.info("✅ Token INSEE obtenu avec succès.")
            return self.insee_access_token
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ Échec d'obtention du token INSEE: {e.response.status_code} - {e.response.text}")
            self.insee_access_token = None # S'assurer que le token est invalidé
        except Exception as e:
            logger.error(f"❌ Erreur inattendue lors de l'obtention du token INSEE: {str(e)}")
            self.insee_access_token = None
        return None
    # NOUVEAU : Méthode d'enrichissement avec l'agent
    async def enrich_with_company_agent(self, client_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        🔍 Enrichit les données client avec l'agent de recherche d'entreprises
        
        Args:
            client_data: Données client à enrichir
            
        Returns:
            Données enrichies avec informations officielles
        """
        try:
            # Enrichissement via l'agent
            enriched_data = await company_search_service.enrich_client_data(client_data)
            
            # Log de l'enrichissement
            if 'enriched_data' in enriched_data:
                logger.info(f"Client enrichi: {client_data.get('company_name')} -> SIREN: {enriched_data['enriched_data'].get('siren')}")
            
            return enriched_data
            
        except Exception as e:
            logger.error(f"Erreur enrichissement agent: {e}")
            return client_data
    
    # NOUVEAU : Validation SIREN avec l'agent
    async def validate_siren_with_agent(self, siren: str) -> Dict[str, Any]:
        """
        ✅ Valide un SIREN avec l'agent de recherche
        
        Args:
            siren: Numéro SIREN à valider
            
        Returns:
            Résultat de validation avec informations entreprise
        """
        try:
            # Validation via l'agent
            validation_result = await company_search_service.validate_siren(siren)
            
            if validation_result['valid']:
                # Récupération des informations entreprise
                company_info = await company_search_service.get_company_by_siren(siren)
                
                if company_info['success']:
                    validation_result['company_info'] = company_info['company']
                    validation_result['source'] = company_info['source']
            
            return validation_result
            
        except Exception as e:
            logger.error(f"Erreur validation SIREN agent: {e}")
            return {'valid': False, 'error': str(e)}    
    async def validate_complete(self, client_data: Dict[str, Any], country: str = "FR") -> Dict[str, Any]:
        """
        Validation complète d'un client avec enrichissement et contrôle de doublons

        Effectue une validation en 6 étapes:
        1. Validations de base universelles (champs obligatoires, formats)
        2. Validations spécifiques au pays
        3. Validation avancée de l'email
        4. Contrôle de doublons (tolérant aux erreurs)
        5. Enrichissement des données (tolérant aux erreurs)
        6. Validation finale de cohérence

        Args:
            client_data: Données du client à valider (doit contenir au minimum email et pays)
            country: Code pays ISO (FR, US, UK, etc.), FR par défaut

        Returns:
            Dict contenant:
            - valid: bool - Statut global de validation
            - errors: List[str] - Erreurs bloquantes
            - warnings: List[str] - Avertissements non bloquants
            - suggestions: List[str] - Suggestions d'amélioration
            - enriched_data: Dict - Données enrichies
            - duplicate_check: Dict - Résultats du contrôle doublons
            - country: str - Pays utilisé pour la validation
            - validation_timestamp: str - Horodatage ISO de la validation
            - validation_level: str - Niveau de validation ("complete")

        Raises:
            ValueError: Si les données client sont vides ou invalides
        """
        self.validation_stats["total_validations"] += 1
        logger.info(f"🔍 Validation complète client pour pays: {country}")
        
        validation_result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "suggestions": [],
            "enriched_data": {},
            "duplicate_check": {},
            "country": country,
            "validation_timestamp": datetime.now().isoformat(),
            "validation_level": "complete"
        }
        
        try:
            # 1. Validations de base universelles
            logger.info("1️⃣ Validations de base...")
            await self._validate_basic_fields(client_data, validation_result)
            
            # 2. Validations spécifiques par pays
            logger.info(f"2️⃣ Validations spécifiques {country}...")
            if country == "FR":
                await self._validate_france(client_data, validation_result)
            elif country == "US":
                await self._validate_usa(client_data, validation_result)
            elif country == "UK":
                await self._validate_uk(client_data, validation_result)
            else:
                validation_result["warnings"].append(f"Validations spécifiques non disponibles pour {country}")
            
            # 3. Validation email avancée
            logger.info("3️⃣ Validation email avancée...")
            await self._validate_email_advanced(client_data, validation_result)
            
            # 4. Contrôle de doublons - AVEC GESTION D'ERREUR
            logger.info("4️⃣ Contrôle de doublons...")
            try:
                await self._check_duplicates(client_data, validation_result)
            except Exception as e:
                logger.warning(f"Erreur contrôle doublons: {e}")
                validation_result["warnings"].append(f"Contrôle de doublons partiel: {e}")

            # 5. Enrichissement automatique des données
            logger.info("5️⃣ Enrichissement des données...")
            try:
                await self._enrich_data(client_data, validation_result)
            except Exception as e:
                logger.warning(f"Erreur enrichissement: {e}")
                validation_result["warnings"].append(f"Enrichissement partiel: {e}")
            
            # 6. Validation finale de cohérence
            logger.info("6️⃣ Validation de cohérence...")
            await self._validate_consistency(client_data, validation_result)
            
            # Déterminer le statut final
            validation_result["valid"] = not validation_result["errors"]
            
            if validation_result["valid"]:
                self.validation_stats["successful_validations"] += 1
                logger.info("✅ Validation réussie")
            else:
                self.validation_stats["failed_validations"] += 1
                logger.warning(f"❌ Validation échouée - {len(validation_result['errors'])} erreur(s)")
            
            return validation_result
            
        except Exception as e:
            logger.exception(f"💥 Erreur lors de la validation: {str(e)}")
            self.validation_stats["failed_validations"] += 1
            validation_result["valid"] = False
            validation_result["errors"].append(f"Erreur système de validation: {str(e)}")
            return validation_result
    
    async def _validate_basic_fields(self, client_data: Dict[str, Any], result: Dict[str, Any]):
        """Validations de base universelles"""
        logger.debug("Validation des champs de base")
        
        # Nom obligatoire
        company_name = client_data.get("company_name", "").strip()
        if not company_name:
            result["errors"].append("Le nom de l'entreprise est obligatoire")
        elif len(company_name) < 2:
            result["errors"].append("Le nom de l'entreprise doit contenir au moins 2 caractères")
        elif len(company_name) > 100:
            result["errors"].append("Le nom de l'entreprise ne peut pas dépasser 100 caractères")
        else:
            # Vérifier les caractères spéciaux problématiques
            if re.search(r'[<>{}[\]\\|`~]', company_name):
                result["warnings"].append("Le nom contient des caractères spéciaux qui pourraient poser problème")
        
        # Validation téléphone
        phone = client_data.get("phone", "")
        if phone:
            if not self._validate_phone_format(phone):
                result["warnings"].append("Format de téléphone invalide ou non reconnu")
            else:
                result["suggestions"].append("Format de téléphone valide")
        
        # Au moins un moyen de contact
        email = client_data.get("email", "")
        if not phone and not email:
            result["errors"].append("Au moins un moyen de contact est requis (téléphone ou email)")
        
        # Validation adresse minimale
        city = client_data.get("billing_city", "")
        country = client_data.get("billing_country", "")
        if not city or not country:
            result["warnings"].append("Adresse incomplète - ville et pays recommandés")
        
        # Validation des champs optionnels
        website = client_data.get("website", "")
        if website and not website.startswith(("http://", "https://")):
            result["suggestions"].append("L'URL du site web devrait commencer par http:// ou https://")
    
    async def _validate_france(self, client_data: Dict[str, Any], result: Dict[str, Any]):
        """Validations spécifiques à la France"""
        logger.debug("Validation spécifique France")
        
        siret = client_data.get("siret", "").replace(" ", "").replace("-", "").replace(".", "")
        
        if siret:
            # Validation format SIRET
            if not re.match(r'^\d{14}$', siret):
                result["errors"].append("Format SIRET invalide (14 chiffres requis)")
            else:
                # Validation SIRET via API INSEE (simulé pour le POC)
                siret_validation = await self._validate_siret_insee(siret)
                if siret_validation["valid"]:
                    result["enriched_data"]["siret_data"] = siret_validation["data"]
                    result["suggestions"].append("✅ SIRET validé via API INSEE")
                else:
                    result["warnings"].append(f"SIRET non validé: {siret_validation['error']}")
        else:
            # SIRET fortement recommandé pour la France
            result["warnings"].append("SIRET non fourni - fortement recommandé pour les entreprises françaises")
            result["suggestions"].append("Ajoutez le numéro SIRET pour validation automatique et enrichissement")
        
        # Validation code postal français
        postal_code = client_data.get("billing_postal_code", "")
        if postal_code:
            if not re.match(r'^\d{5}$', postal_code):
                result["warnings"].append("Format de code postal français invalide (5 chiffres requis)")
            else:
                result["suggestions"].append("Code postal français valide")
        
        # Normalisation adresse via API Adresse gouv.fr (simulé)
        if client_data.get("billing_street") and client_data.get("billing_city"):
            address_validation = await self._validate_address_france(client_data)
            if address_validation["found"]:
                result["enriched_data"]["normalized_address"] = address_validation["address"]
                result["suggestions"].append("✅ Adresse normalisée via API Adresse gouv.fr")
            else:
                result["warnings"].append("Adresse non trouvée dans la base officielle")
    
    async def _validate_usa(self, client_data: Dict[str, Any], result: Dict[str, Any]):
        """Validations spécifiques aux USA"""
        logger.debug("Validation spécifique USA")
        
        # EIN (Employer Identification Number) optionnel
        ein = client_data.get("ein", "").replace("-", "")
        if ein:
            if not re.match(r'^\d{9}$', ein):
                result["warnings"].append("Format EIN invalide (9 chiffres requis)")
            else:
                result["suggestions"].append("Format EIN valide")
        
        # État obligatoire pour les USA
        state = client_data.get("billing_state", "")
        if not state:
            result["errors"].append("État obligatoire pour les entreprises américaines")
        elif state.upper() not in self._get_us_states():
            result["warnings"].append(f"Code d'état '{state}' non reconnu")
        else:
            result["suggestions"].append("Code d'état US valide")
        
        # Validation code postal US
        postal_code = client_data.get("billing_postal_code", "")
        if postal_code:
            if not re.match(r'^\d{5}(-\d{4})?$', postal_code):
                result["warnings"].append("Format de code postal US invalide (12345 ou 12345-6789)")
            else:
                result["suggestions"].append("Code postal US valide")
    
    async def _validate_uk(self, client_data: Dict[str, Any], result: Dict[str, Any]):
        """Validations spécifiques au Royaume-Uni"""
        logger.debug("Validation spécifique UK")
        
        # Company Number optionnel
        company_number = client_data.get("company_number", "")
        if company_number:
            if not re.match(r'^[A-Z0-9]{8}$', company_number.upper()):
                result["warnings"].append("Format Company Number invalide (8 caractères alphanumériques)")
            else:
                result["suggestions"].append("Format Company Number valide")
        
        # Validation postcode UK
        postal_code = client_data.get("billing_postal_code", "")
        if postal_code:
            if not re.match(r'^[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}$', postal_code.upper()):
                result["warnings"].append("Format postcode UK invalide")
            else:
                result["suggestions"].append("Format postcode UK valide")
    
    async def _validate_email_advanced(self, client_data: Dict[str, Any], result: Dict[str, Any]):
        """Validation email avancée"""
        email = client_data.get("email", "")
        if not email:
            return
        
        if EMAIL_VALIDATOR_AVAILABLE:
            try:
                # Validation avec email-validator
                valid_email = validate_email(email)
                result["enriched_data"]["normalized_email"] = valid_email.email
                result["suggestions"].append("✅ Email validé et normalisé")
                
                # Vérification domaine
                domain = email.split("@")[1].lower()
                suspicious_domains = ["test.com", "example.com", "tempmail.com", "10minutemail.com", "guerrillamail.com"]
                if domain in suspicious_domains:
                    result["warnings"].append("Adresse email temporaire ou de test détectée")
                
            except EmailNotValidError as e:
                result["errors"].append(f"Email invalide: {str(e)}")
        else:
            # Validation basique par regex
            if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
                result["errors"].append("Format d'email invalide")
            else:
                result["suggestions"].append("Format d'email basique valide")
    
    async def _check_duplicates(self, client_data: Dict[str, Any], result: Dict[str, Any]):
        """Contrôle de doublons dans Salesforce et SAP"""

        duplicate_check = {
            "salesforce_duplicates": [],
            "sap_duplicates": [],
            "similarity_scores": [],
            "warnings": []
        }

        company_name = client_data.get("company_name", "").strip()

        try:
            # 🔧 CORRECTION : Import du connecteur MCP
            from services.mcp_connector import MCPConnector

            # Recherche doublons Salesforce
            sf_search = await MCPConnector.call_salesforce_mcp("salesforce_query", {
                "query": f"SELECT Id, Name, AccountNumber, Phone, Email FROM Account WHERE Name LIKE '%{company_name[:10]}%' LIMIT 10"
            })

            if sf_search.get("success") and sf_search.get("data"):
                for account in sf_search["data"]:
                    # Calculer similarité si fuzzywuzzy disponible
                    if FUZZYWUZZY_AVAILABLE:
                        similarity = fuzz.ratio(company_name.lower(), account["Name"].lower())
                        if similarity > 70:  # Seuil de similarité
                            duplicate_check["salesforce_duplicates"].append({
                                "id": account["Id"],
                                "name": account["Name"],
                                "similarity": similarity
                            })

            # 🔧 CORRECTION : Recherche doublons SAP avec gestion d'erreur
            try:
                sap_result = await MCPConnector.call_sap_mcp("sap_search", {
                    "query": company_name,
                    "entity_type": "BusinessPartners",
                    "limit": 10
                })

                if sap_result.get("success") and sap_result.get("data"):
                    for partner in sap_result["data"]:
                        partner_name = partner.get("CardName", "")
                        if FUZZYWUZZY_AVAILABLE and partner_name:
                            similarity = fuzz.ratio(company_name.lower(), partner_name.lower())
                            if similarity > 70:
                                duplicate_check["sap_duplicates"].append({
                                    "card_code": partner.get("CardCode"),
                                    "name": partner_name,
                                    "similarity": similarity
                                })
            except Exception as sap_error:
                logger.warning(f"Erreur recherche SAP: {sap_error}")
                duplicate_check["warnings"].append(f"Impossible de vérifier les doublons SAP: {sap_error}")

            # Ajouter les résultats au résultat principal
            result["duplicate_check"] = duplicate_check

            # Avertissements si doublons trouvés
            if duplicate_check["salesforce_duplicates"]:
                result["warnings"].append(f"Doublons potentiels trouvés dans Salesforce: {len(duplicate_check['salesforce_duplicates'])}")

            if duplicate_check["sap_duplicates"]:
                result["warnings"].append(f"Doublons potentiels trouvés dans SAP: {len(duplicate_check['sap_duplicates'])}")

        except Exception as e:
            logger.exception(f"Erreur vérification doublons: {str(e)}")
            duplicate_check["warnings"].append(f"❌ Erreur vérification doublons: {str(e)}")
            result["duplicate_check"] = duplicate_check
    
    async def _enrich_data(self, client_data: Dict[str, Any], result: Dict[str, Any]):
        """Enrichissement automatique des données"""
        
        # Normalisation du nom
        company_name = client_data.get("company_name", "")
        if company_name:
            # Nettoyer et normaliser
            normalized_name = re.sub(r'\s+', ' ', company_name.strip())
            normalized_name = normalized_name.title()  # Capitalisation
            
            if normalized_name != company_name:
                result["enriched_data"]["normalized_company_name"] = normalized_name
                result["suggestions"].append("Nom d'entreprise normalisé")
        
        # Génération d'un code client unique suggéré
        if company_name:
            clean_name = re.sub(r'[^a-zA-Z0-9]', '', company_name)[:8].upper()
            timestamp = str(int(datetime.now().timestamp()))[-4:]
            suggested_code = f"C{clean_name}{timestamp}"
            result["enriched_data"]["suggested_client_code"] = suggested_code
        
        # Enrichissement de l'adresse web
        website = client_data.get("website", "")
        if website and not website.startswith(("http://", "https://")):
            result["enriched_data"]["normalized_website"] = f"https://{website}"
        
        # Génération d'un email de contact si manquant
        email = client_data.get("email", "")
        if not email and website:
            domain = website.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
            suggested_email = f"contact@{domain}"
            result["enriched_data"]["suggested_email"] = suggested_email
            result["suggestions"].append(f"Email suggéré: {suggested_email}")
    
    async def _validate_consistency(self, client_data: Dict[str, Any], result: Dict[str, Any]):
        """Validation de cohérence globale"""
        
        # Cohérence adresse/pays
        country = client_data.get("billing_country", "").lower()
        postal_code = client_data.get("billing_postal_code", "")
        
        if "france" in country and postal_code:
            validation = FormatValidator.validate_format(postal_code, 'postal_code', 'FR')
            if not validation["valid"]:
                result["warnings"].append(validation["error"])
        
        elif "united states" in country or "usa" in country and postal_code:
            if not re.match(r'^\d{5}(-\d{4})?$', postal_code):
                result["warnings"].append("Code postal incohérent avec le pays USA")
        
        # Cohérence téléphone/pays
        phone = client_data.get("phone", "")
        if phone and "france" in country:
            if not (phone.startswith("+33") or phone.startswith("0")):
                result["warnings"].append("Numéro de téléphone incohérent avec le pays France")
    
    # Méthodes utilitaires
    async def _call_insee_api(self, endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Appel générique à l'API INSEE
        
        Args:
            endpoint: Point d'accès API (ex: /siret/12345678901234)
            params: Paramètres de requête
        
        Returns:
            Résultat de l'appel API
        """
        access_token = await self._get_insee_token()
        if not access_token:
            return {"error": "Token INSEE indisponible"}
        
        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"{INSEE_API_BASE_URL}{endpoint}"
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, params=params, timeout=10.0)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("header", {}).get("statut") == 200:
                    return {"success": True, "data": data}
                else:
                    error_msg = data.get("header", {}).get("message", "Erreur API")
                    return {"error": error_msg}
            
            elif response.status_code == 404:
                return {"error": "Non trouvé", "status_code": 404}
            
            else:
                return {"error": f"Erreur HTTP {response.status_code}"}
        
        except Exception as e:
            logger.error(f"Erreur appel INSEE: {e}")
            return {"error": str(e)}
    async def _validate_siret_insee(self, siret: str) -> Dict[str, Any]:
        """Validation SIRET simplifiée"""
        result = await self._call_insee_api(f"/siret/{siret}")
        
        if result.get("success"):
            # Traitement des données spécifique SIRET
            return self._process_siret_data(result["data"])
        else:
            return {"valid": False, "error": result["error"]}
    
    async def _validate_address_france(self, client_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validation adresse via API Adresse gouv.fr."""
        street = client_data.get("billing_street", "")
        city = client_data.get("billing_city", "")
        postal_code = client_data.get("billing_postal_code", "")

        if not street or not (city or postal_code): # Au moins rue + (ville ou CP)
            logger.warning("Adresse incomplète pour validation via API Adresse Gouv.")
            return {"found": False, "error": "Adresse incomplète pour validation", "validation_method": "skipped"}

        # Construire la requête, donner la priorité au code postal s'il est présent
        query_parts = [street, postal_code if postal_code else city]
        query = " ".join(filter(None, query_parts))
        
        params = {"q": query, "limit": 1} # On prend le premier meilleur résultat
        
        logger.info(f"Validation adresse via API gouv.fr: {query}")

        try:
            response = await self.http_client.get(API_ADRESSE_GOUV_URL, params=params, timeout=10.0)
            # La levée d'exception pour 4xx/5xx est gérée par le hook _raise_on_4xx_5xx

            data = response.json()
            
            if response.status_code == 200 and data.get("features"):
                best_match = data["features"][0] # On prend le premier résultat
                properties = best_match.get("properties", {})
                geometry = best_match.get("geometry", {})
                
                # Vérifier la pertinence du résultat (score élevé)
                # L'API retourne un score, un score > 0.7 est généralement bon.
                # Pour simplifier, on prend le premier, mais en production on vérifierait le score.
                # score = properties.get("score", 0.0)
                # if score < 0.7: # Seuil de pertinence
                #     logger.warning(f"Adresse trouvée mais score faible ({score:.2f}): {properties.get('label')}")
                #     return {"found": False, "error": "Adresse non trouvée avec certitude", "validation_method": "api_ban", "low_score": True}


                normalized_address = {
                    "label": properties.get("label"), # Adresse complète formatée
                    "street_number": properties.get("housenumber"),
                    "street_name": properties.get("street") or properties.get("name"), # "name" pour les lieux-dits/routes
                    "postal_code": properties.get("postcode"),
                    "city": properties.get("city"),
                    "context": properties.get("context"), # Ex: "75, Paris, Île-de-France"
                    "type": properties.get("type"), # Ex: "housenumber", "street"
                    "coordinates": {
                        "latitude": geometry.get("coordinates", [None, None])[1], # Ordre: lon, lat
                        "longitude": geometry.get("coordinates", [None, None])[0]
                    },
                    "validation_method": "api_ban" # BAN = Base Adresse Nationale
                }
                
                # Comparer si l'adresse trouvée est significativement différente
                # (logique de suggestion ou d'alerte à affiner)
                # Par exemple, si le code postal ou la ville diffèrent de l'entrée.
                
                return {"found": True, "address": normalized_address}
            
            elif not data.get("features"):
                logger.warning(f"Aucune adresse trouvée pour: {query}")
                return {"found": False, "error": "Adresse non trouvée", "validation_method": "api_ban"}
            else:
                # Cas d'erreur non standard de l'API si la structure est inattendue
                logger.error(f"Réponse inattendue de l'API Adresse pour {query}: {data}")
                return {"found": False, "error": "Réponse API Adresse inattendue", "validation_method": "api_ban"}

        except httpx.HTTPStatusError as e:
            error_detail = e.response.text[:200] if e.response else str(e)
            logger.error(f"Erreur HTTP lors de la validation d'adresse {query}: {str(e)} - {error_detail}")
            return {"found": False, "error": f"Erreur HTTP API Adresse: {e.response.status_code}", "validation_method": "api_ban"}
        except httpx.TimeoutException:
            logger.error(f"Timeout lors de la validation d'adresse {query} via API Adresse.")
            return {"found": False, "error": "Timeout API Adresse", "validation_method": "api_ban"}
        except Exception as e:
            logger.exception(f"Erreur inattendue validation adresse {query}: {str(e)}")
            return {"found": False, "error": f"Erreur interne: {str(e)}", "validation_method": "api_ban"}
    
    def _validate_phone_format(self, phone: str) -> bool:
        """Validation format téléphone international"""
        # Nettoyer le numéro
        clean_phone = re.sub(r'[\s\-\.\(\)]', '', phone)
        
        # Patterns pour différents formats
        patterns = [
            r'^(\+33|0033)[1-9]\d{8}$',  # France
            r'^(\+1|001)?[2-9]\d{2}[2-9]\d{2}\d{4}$',  # USA/Canada
            r'^(\+44|0044|0)[1-9]\d{8,9}$',  # UK
            r'^\+[1-9]\d{1,14}$'  # Format international général
        ]
        
        return any(re.match(pattern, clean_phone) for pattern in patterns)
    
    def _get_us_states(self) -> List[str]:
        """Liste des codes d'états américains"""
        return [
            "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
            "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
            "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
            "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
            "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY"
        ]

    async def _search_company_insee(self, query: str) -> Dict[str, Any]:
        """Recherche d'entreprise simplifiée"""
        result = await self._call_insee_api("/siret", {"q": query, "nombre": 10})
        
        if result.get("success"):
            return self._process_search_results(result["data"])
        else:
            return {"error": result["error"]}
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques de validation"""
        # Calculer la taille du cache selon le type utilisé
        cache_size = 0
        cache_type = "none"
        
        if HTTP_CACHE_AVAILABLE and hasattr(self, 'cached_http_client'):
            try:
                # Essayer d'obtenir la taille du cache requests_cache
                cache_size = len(self.cached_http_client.cache.responses)
                cache_type = "requests_cache"
            except Exception:
                cache_size = 0
                cache_type = "requests_cache_error"
        elif hasattr(self, 'api_cache'):
            cache_size = len(self.api_cache)
            cache_type = "dict"
        
        return {
            "validation_stats": self.validation_stats,
            "cache_info": {
                "size": cache_size,
                "type": cache_type
            },
            "dependencies": {
                "fuzzywuzzy": FUZZYWUZZY_AVAILABLE,
                "email_validator": EMAIL_VALIDATOR_AVAILABLE,
                "http_cache": HTTP_CACHE_AVAILABLE
            },
            "insee_config": {
                "consumer_key_set": bool(self.insee_consumer_key),
                "consumer_secret_set": bool(self.insee_consumer_secret),
                "token_valid": bool(self.insee_access_token and self.insee_token_expires_at > datetime.now())
            }
        }
# MODIFICATION : Méthode de validation principale enrichie
    async def validate_client_data_enriched(self, client_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        🔍 Validation client enrichie avec l'agent de recherche d'entreprises
        
        Workflow:
        1. Validation des données de base
        2. Enrichissement avec l'agent de recherche
        3. Validation SIREN si disponible
        4. Suggestions si entreprise non trouvée
        
        Args:
            client_data: Données client à valider
            
        Returns:
            Résultat de validation enrichi
        """
        try:
            # 1. Validation de base existante
            base_validation = await self.validate_client_data(client_data)
            
            # 2. Enrichissement avec l'agent
            enriched_data = await self.enrich_with_company_agent(client_data)
            
            # 3. Validation SIREN si disponible
            siren_validation = None
            if enriched_data.get('enriched_data', {}).get('siren'):
                siren = enriched_data['enriched_data']['siren']
                siren_validation = await self.validate_siren_with_agent(siren)
            
            # 4. Suggestions si entreprise non trouvée
            suggestions = []
            if not enriched_data.get('enriched_data'):
                company_name = client_data.get('company_name') or client_data.get('name')
                if company_name:
                    suggestions = await company_search_service.get_suggestions(company_name)
            
            # Résultat consolidé
            return {
                'base_validation': base_validation,
                'enriched_data': enriched_data,
                'siren_validation': siren_validation,
                'suggestions': suggestions,
                'enhanced_with_agent': True,
                'validation_timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Erreur validation enrichie: {e}")
            # Fallback vers validation de base
            return await self.validate_client_data(client_data)
    
    # NOUVEAU : Recherche d'entreprises similaires
    async def find_similar_companies(self, company_name: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """
        🔍 Trouve des entreprises similaires pour résolution de doublons
        
        Args:
            company_name: Nom de l'entreprise à rechercher
            max_results: Nombre maximum de résultats
            
        Returns:
            Liste des entreprises similaires
        """
        try:
            search_result = await company_search_service.search_company(
                query=company_name,
                max_results=max_results
            )
            
            if search_result['success']:
                return search_result['companies']
            else:
                return []
                
        except Exception as e:
            logger.error(f"Erreur recherche entreprises similaires: {e}")
            return []

# NOUVEAU : Décorateur pour l'enrichissement automatique
def with_company_enrichment(func):
    """
    Décorateur pour enrichir automatiquement les données client avec l'agent
    """
    async def wrapper(self, client_data: Dict[str, Any], *args, **kwargs):
        # Enrichissement automatique
        enriched_data = await self.enrich_with_company_agent(client_data)

        # Appel de la fonction originale avec les données enrichies
        result = await func(self, enriched_data, *args, **kwargs)

        # Ajout des informations d'enrichissement au résultat
        if isinstance(result, dict):
            result['enrichment_applied'] = 'enriched_data' in enriched_data
            result['enrichment_source'] = enriched_data.get('enriched_data', {}).get('source')

        return result

    return wrapper


class FormatValidator:
    """Validateur de formats réutilisable"""
    
    PATTERNS = {
        'postal_code': {
            'FR': r'^\d{5}$',
            'US': r'^\d{5}(-\d{4})?$',
            'UK': r'^[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}$'
        },
        'phone': {
            'FR': r'^(\+33|0033|0)[1-9]\d{8}$',
            'US': r'^(\+1|001)?[2-9]\d{2}[2-9]\d{2}\d{4}$',
            'UK': r'^(\+44|0044|0)[1-9]\d{8,9}$'
        },
        'business_id': {
            'FR': r'^\d{14}$',  # SIRET
            'US': r'^\d{9}$',   # EIN
            'UK': r'^[A-Z0-9]{8}$'  # Company Number
        }
    }
    
    @classmethod
    def validate_format(cls, value: str, format_type: str, 
                       country: str) -> Dict[str, Any]:
        """
        Valide un format selon le pays
        
        Args:
            value: Valeur à valider
            format_type: Type de format (postal_code, phone, business_id)
            country: Code pays
        
        Returns:
            Résultat de validation
        """
        if not value:
            return {"valid": False, "error": "Valeur vide"}
        
        pattern = cls.PATTERNS.get(format_type, {}).get(country)
        if not pattern:
            return {"valid": False, "error": f"Format non supporté pour {country}"}
        
        clean_value = re.sub(r'[\s\-\.\(\)]', '', value)
        is_valid = bool(re.match(pattern, clean_value.upper()))
        
        return {
            "valid": is_valid,
            "cleaned_value": clean_value,
            "pattern_used": pattern,
            "error": None if is_valid else f"Format invalide pour {country}"
        }
# EXEMPLE D'UTILISATION du décorateur
class EnhancedClientValidator(ClientValidator):
    """Validateur client avec enrichissement automatique"""
    
    @with_company_enrichment
    async def validate_for_salesforce(self, client_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validation enrichie pour Salesforce"""
        return await self.validate_client_data(client_data)
    
    @with_company_enrichment
    async def validate_for_sap(self, client_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validation enrichie pour SAP"""
        return await self.validate_client_data(client_data)
# Fonction utilitaire pour usage direct
async def validate_client_data(client_data: Dict[str, Any], country: str = "FR") -> Dict[str, Any]:
    """Fonction utilitaire pour valider des données client"""
    validator = ClientValidator()
    return await validator.validate_complete(client_data, country)