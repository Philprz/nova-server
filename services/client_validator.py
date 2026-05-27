# services/client_validator.py
"""
Module de validation complÃ¨te des donnÃ©es client
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
from services.security_helpers import escape_soql
# Importer les dÃ©pendances avec gestion des erreurs
try:
    from thefuzz import fuzz
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

# Configuration du cache pour les requÃªtes HTTP
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
    """Validateur complet pour les donnÃ©es client"""
    
    def __init__(self):
        # self.api_cache = {} # RemplacÃ© par requests-cache si disponible
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
            # Cache les requÃªtes pour 1 heure, expire les anciennes aprÃ¨s 1 jour
            # Les erreurs 5xx ne sont pas mises en cache par dÃ©faut
            self.http_client = httpx.AsyncClient(
                event_hooks={'response': [self._raise_on_4xx_5xx]}
            )
            self.cached_http_client = requests_cache.CachedSession(
                cache_name='api_cache',
                backend='sqlite',
                expire_after=timedelta(hours=1),
                allowable_codes=[200], # Cache seulement les succÃ¨s
                old_data_on_error=True # Utilise le cache si l'API est down
            )
            # Monkey patch pour utiliser requests_cache avec httpx de maniÃ¨re synchrone pour le token
            # Pour les appels asynchrones, nous gÃ©rerons le cache manuellement ou via une lib compatible
        else:
            self.http_client = httpx.AsyncClient(
                 event_hooks={'response': [self._raise_on_4xx_5xx]}
            )
        
        if not self.insee_consumer_key or not self.insee_consumer_secret:
            logger.warning("INSEE_CONSUMER_KEY ou INSEE_CONSUMER_SECRET non configurÃ©s. Validation INSEE dÃ©sactivÃ©e.")

    async def _raise_on_4xx_5xx(self, response):
        """Hook pour httpx pour lever une exception sur les erreurs HTTP."""
        # L'objectif principal de ce hook est de s'assurer que les erreurs HTTP
        # sont levÃ©es pour que le code appelant puisse les intercepter.
        # Les dÃ©tails de l'erreur (comme le corps de la rÃ©ponse) seront gÃ©rÃ©s
        # par le bloc `except` spÃ©cifique dans la mÃ©thode appelante.
        response.raise_for_status()

    async def _get_insee_token(self) -> str | None:
        """RÃ©cupÃ¨re ou renouvelle le token d'accÃ¨s INSEE."""
        if not self.insee_consumer_key or not self.insee_consumer_secret:
            return None

        if self.insee_access_token and datetime.now() < self.insee_token_expires_at:
            return self.insee_access_token

        logger.info("Demande d'un nouveau token d'accÃ¨s INSEE...")
        auth = (self.insee_consumer_key, self.insee_consumer_secret)
        data = {"grant_type": "client_credentials"}
        
        try:
            # Utilisation d'un client httpx synchrone pour cette partie critique ou gestion manuelle du cache
            # Pour simplifier, appel direct sans cache spÃ©cifique pour le token ici, car gÃ©rÃ© par l'expiration.
            async with httpx.AsyncClient() as client: # Client temporaire pour le token
                response = await client.post(INSEE_TOKEN_URL, auth=auth, data=data)
            response.raise_for_status()
            
            token_data = response.json()
            self.insee_access_token = token_data["access_token"]
            # Mettre une marge de 60 secondes avant l'expiration rÃ©elle
            self.insee_token_expires_at = datetime.now() + timedelta(seconds=token_data["expires_in"] - 60)
            logger.info("âœ… Token INSEE obtenu avec succÃ¨s.")
            return self.insee_access_token
        except httpx.HTTPStatusError as e:
            logger.error(f"âŒ Ã‰chec d'obtention du token INSEE: {e.response.status_code} - {e.response.text}")
            self.insee_access_token = None # S'assurer que le token est invalidÃ©
        except Exception as e:
            logger.error(f"âŒ Erreur inattendue lors de l'obtention du token INSEE: {str(e)}")
            self.insee_access_token = None
        return None
    # NOUVEAU : MÃ©thode d'enrichissement avec l'agent
    async def enrich_with_company_agent(self, client_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        ðŸ” Enrichit les donnÃ©es client avec l'agent de recherche d'entreprises
        
        Args:
            client_data: DonnÃ©es client Ã  enrichir
            
        Returns:
            DonnÃ©es enrichies avec informations officielles
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
        âœ… Valide un SIREN avec l'agent de recherche
        
        Args:
            siren: NumÃ©ro SIREN Ã  valider
            
        Returns:
            RÃ©sultat de validation avec informations entreprise
        """
        try:
            # Validation via l'agent
            validation_result = await company_search_service.validate_siren(siren)
            
            if validation_result['valid']:
                # RÃ©cupÃ©ration des informations entreprise
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
        Validation complÃ¨te d'un client avec enrichissement et contrÃ´le de doublons

        Effectue une validation en 6 Ã©tapes:
        1. Validations de base universelles (champs obligatoires, formats)
        2. Validations spÃ©cifiques au pays
        3. Validation avancÃ©e de l'email
        4. ContrÃ´le de doublons (tolÃ©rant aux erreurs)
        5. Enrichissement des donnÃ©es (tolÃ©rant aux erreurs)
        6. Validation finale de cohÃ©rence

        Args:
            client_data: DonnÃ©es du client Ã  valider (doit contenir au minimum email et pays)
            country: Code pays ISO (FR, US, UK, etc.), FR par dÃ©faut

        Returns:
            Dict contenant:
            - valid: bool - Statut global de validation
            - errors: List[str] - Erreurs bloquantes
            - warnings: List[str] - Avertissements non bloquants
            - suggestions: List[str] - Suggestions d'amÃ©lioration
            - enriched_data: Dict - DonnÃ©es enrichies
            - duplicate_check: Dict - RÃ©sultats du contrÃ´le doublons
            - country: str - Pays utilisÃ© pour la validation
            - validation_timestamp: str - Horodatage ISO de la validation
            - validation_level: str - Niveau de validation ("complete")

        Raises:
            ValueError: Si les donnÃ©es client sont vides ou invalides
        """
        self.validation_stats["total_validations"] += 1
        logger.info(f"ðŸ” Validation complÃ¨te client pour pays: {country}")
        
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
            logger.info("1ï¸âƒ£ Validations de base...")
            await self._validate_basic_fields(client_data, validation_result)
            
            # 2. Validations spÃ©cifiques par pays
            logger.info(f"2ï¸âƒ£ Validations spÃ©cifiques {country}...")
            if country == "FR":
                await self._validate_france(client_data, validation_result)
            elif country == "US":
                await self._validate_usa(client_data, validation_result)
            elif country == "UK":
                await self._validate_uk(client_data, validation_result)
            else:
                validation_result["warnings"].append(f"Validations spÃ©cifiques non disponibles pour {country}")
            
            # 3. Validation email avancÃ©e
            logger.info("3ï¸âƒ£ Validation email avancÃ©e...")
            await self._validate_email_advanced(client_data, validation_result)
            
            # 4. ContrÃ´le de doublons - AVEC GESTION D'ERREUR
            logger.info("4ï¸âƒ£ ContrÃ´le de doublons...")
            try:
                await self._check_duplicates(client_data, validation_result)
            except Exception as e:
                logger.warning(f"Erreur contrÃ´le doublons: {e}")
                validation_result["warnings"].append(f"ContrÃ´le de doublons partiel: {e}")

            # 5. Enrichissement automatique des donnÃ©es
            logger.info("5ï¸âƒ£ Enrichissement des donnÃ©es...")
            try:
                await self._enrich_data(client_data, validation_result)
            except Exception as e:
                logger.warning(f"Erreur enrichissement: {e}")
                validation_result["warnings"].append(f"Enrichissement partiel: {e}")
            
            # 6. Validation finale de cohÃ©rence
            logger.info("6ï¸âƒ£ Validation de cohÃ©rence...")
            await self._validate_consistency(client_data, validation_result)
            
            # DÃ©terminer le statut final
            validation_result["valid"] = not validation_result["errors"]
            
            if validation_result["valid"]:
                self.validation_stats["successful_validations"] += 1
                logger.info("âœ… Validation rÃ©ussie")
            else:
                self.validation_stats["failed_validations"] += 1
                logger.warning(f"âŒ Validation Ã©chouÃ©e - {len(validation_result['errors'])} erreur(s)")
            
            return validation_result
            
        except Exception as e:
            logger.exception(f"ðŸ’¥ Erreur lors de la validation: {str(e)}")
            self.validation_stats["failed_validations"] += 1
            validation_result["valid"] = False
            validation_result["errors"].append(f"Erreur systÃ¨me de validation: {str(e)}")
            return validation_result
    
    async def _validate_basic_fields(self, client_data: Dict[str, Any], result: Dict[str, Any]):
        """Validations de base universelles"""
        logger.debug("Validation des champs de base")
        
        # Nom obligatoire
        company_name = client_data.get("company_name", "").strip()
        if not company_name:
            result["errors"].append("Le nom de l'entreprise est obligatoire")
        elif len(company_name) < 2:
            result["errors"].append("Le nom de l'entreprise doit contenir au moins 2 caractÃ¨res")
        elif len(company_name) > 100:
            result["errors"].append("Le nom de l'entreprise ne peut pas dÃ©passer 100 caractÃ¨res")
        else:
            # VÃ©rifier les caractÃ¨res spÃ©ciaux problÃ©matiques
            if re.search(r'[<>{}[\]\\|`~]', company_name):
                result["warnings"].append("Le nom contient des caractÃ¨res spÃ©ciaux qui pourraient poser problÃ¨me")
        
        # Validation tÃ©lÃ©phone
        phone = client_data.get("phone", "")
        if phone:
            if not self._validate_phone_format(phone):
                result["warnings"].append("Format de tÃ©lÃ©phone invalide ou non reconnu")
            else:
                result["suggestions"].append("Format de tÃ©lÃ©phone valide")
        
        # Au moins un moyen de contact
        email = client_data.get("email", "")
        if not phone and not email:
            result["errors"].append("Au moins un moyen de contact est requis (tÃ©lÃ©phone ou email)")
        
        # Validation adresse minimale
        city = client_data.get("billing_city", "")
        country = client_data.get("billing_country", "")
        if not city or not country:
            result["warnings"].append("Adresse incomplÃ¨te - ville et pays recommandÃ©s")
        
        # Validation des champs optionnels
        website = client_data.get("website", "")
        if website and not website.startswith(("http://", "https://")):
            result["suggestions"].append("L'URL du site web devrait commencer par http:// ou https://")
    
    async def _validate_france(self, client_data: Dict[str, Any], result: Dict[str, Any]):
        """Validations spÃ©cifiques Ã  la France"""
        logger.debug("Validation spÃ©cifique France")
        
        siret = client_data.get("siret", "").replace(" ", "").replace("-", "").replace(".", "")
        
        if siret:
            # Validation format SIRET
            if not re.match(r'^\d{14}$', siret):
                result["errors"].append("Format SIRET invalide (14 chiffres requis)")
            else:
                # Validation SIRET via API INSEE (simulÃ© pour le POC)
                siret_validation = await self._validate_siret_insee(siret)
                if siret_validation["valid"]:
                    result["enriched_data"]["siret_data"] = siret_validation["data"]
                    result["suggestions"].append("âœ… SIRET validÃ© via API INSEE")
                else:
                    result["warnings"].append(f"SIRET non validÃ©: {siret_validation['error']}")
        else:
            # SIRET fortement recommandÃ© pour la France
            result["warnings"].append("SIRET non fourni - fortement recommandÃ© pour les entreprises franÃ§aises")
            result["suggestions"].append("Ajoutez le numÃ©ro SIRET pour validation automatique et enrichissement")
        
        # Validation code postal franÃ§ais
        postal_code = client_data.get("billing_postal_code", "")
        if postal_code:
            if not re.match(r'^\d{5}$', postal_code):
                result["warnings"].append("Format de code postal franÃ§ais invalide (5 chiffres requis)")
            else:
                result["suggestions"].append("Code postal franÃ§ais valide")
        
        # Normalisation adresse via API Adresse gouv.fr (simulÃ©)
        if client_data.get("billing_street") and client_data.get("billing_city"):
            address_validation = await self._validate_address_france(client_data)
            if address_validation["found"]:
                result["enriched_data"]["normalized_address"] = address_validation["address"]
                result["suggestions"].append("âœ… Adresse normalisÃ©e via API Adresse gouv.fr")
            else:
                result["warnings"].append("Adresse non trouvÃ©e dans la base officielle")
    
    async def _validate_usa(self, client_data: Dict[str, Any], result: Dict[str, Any]):
        """Validations spÃ©cifiques aux USA"""
        logger.debug("Validation spÃ©cifique USA")
        
        # EIN (Employer Identification Number) optionnel
        ein = client_data.get("ein", "").replace("-", "")
        if ein:
            if not re.match(r'^\d{9}$', ein):
                result["warnings"].append("Format EIN invalide (9 chiffres requis)")
            else:
                result["suggestions"].append("Format EIN valide")
        
        # Ã‰tat obligatoire pour les USA
        state = client_data.get("billing_state", "")
        if not state:
            result["errors"].append("Ã‰tat obligatoire pour les entreprises amÃ©ricaines")
        elif state.upper() not in self._get_us_states():
            result["warnings"].append(f"Code d'Ã©tat '{state}' non reconnu")
        else:
            result["suggestions"].append("Code d'Ã©tat US valide")
        
        # Validation code postal US
        postal_code = client_data.get("billing_postal_code", "")
        if postal_code:
            if not re.match(r'^\d{5}(-\d{4})?$', postal_code):
                result["warnings"].append("Format de code postal US invalide (12345 ou 12345-6789)")
            else:
                result["suggestions"].append("Code postal US valide")
    
    async def _validate_uk(self, client_data: Dict[str, Any], result: Dict[str, Any]):
        """Validations spÃ©cifiques au Royaume-Uni"""
        logger.debug("Validation spÃ©cifique UK")
        
        # Company Number optionnel
        company_number = client_data.get("company_number", "")
        if company_number:
            if not re.match(r'^[A-Z0-9]{8}$', company_number.upper()):
                result["warnings"].append("Format Company Number invalide (8 caractÃ¨res alphanumÃ©riques)")
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
        """Validation email avancÃ©e"""
        email = client_data.get("email", "")
        if not email:
            return
        
        if EMAIL_VALIDATOR_AVAILABLE:
            try:
                # Validation avec email-validator
                valid_email = validate_email(email)
                result["enriched_data"]["normalized_email"] = valid_email.email
                result["suggestions"].append("âœ… Email validÃ© et normalisÃ©")
                
                # VÃ©rification domaine
                domain = email.split("@")[1].lower()
                suspicious_domains = ["test.com", "example.com", "tempmail.com", "10minutemail.com", "guerrillamail.com"]
                if domain in suspicious_domains:
                    result["warnings"].append("Adresse email temporaire ou de test dÃ©tectÃ©e")
                
            except EmailNotValidError as e:
                result["errors"].append(f"Email invalide: {str(e)}")
        else:
            # Validation basique par regex
            if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
                result["errors"].append("Format d'email invalide")
            else:
                result["suggestions"].append("Format d'email basique valide")
    
    async def _check_duplicates(self, client_data: Dict[str, Any], result: Dict[str, Any]):
        """ContrÃ´le de doublons dans Salesforce et SAP"""

        duplicate_check = {
            "salesforce_duplicates": [],
            "sap_duplicates": [],
            "similarity_scores": [],
            "warnings": []
        }

        company_name = client_data.get("company_name", "").strip()

        try:
            # ðŸ”§ CORRECTION : Import du connecteur MCP
            from services.mcp_connector import MCPConnector

            # Recherche doublons Salesforce
            sf_search = await MCPConnector.call_salesforce_mcp("salesforce_query", {
                "query": f"SELECT Id, Name, AccountNumber, Phone, Email FROM Account WHERE Name LIKE '%{escape_soql(company_name[:10])}%' LIMIT 10"
            })

            if sf_search.get("success") and sf_search.get("data"):
                for account in sf_search["data"]:
                    # Calculer similaritÃ© si fuzzywuzzy disponible
                    if FUZZYWUZZY_AVAILABLE:
                        similarity = fuzz.ratio(company_name.lower(), account["Name"].lower())
                        if similarity > 70:  # Seuil de similaritÃ©
                            duplicate_check["salesforce_duplicates"].append({
                                "id": account["Id"],
                                "name": account["Name"],
                                "similarity": similarity
                            })

            # ðŸ”§ CORRECTION : Recherche doublons SAP avec gestion d'erreur
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
                duplicate_check["warnings"].append(f"Impossible de vÃ©rifier les doublons SAP: {sap_error}")

            # Ajouter les rÃ©sultats au rÃ©sultat principal
            result["duplicate_check"] = duplicate_check

            # Avertissements si doublons trouvÃ©s
            if duplicate_check["salesforce_duplicates"]:
                result["warnings"].append(f"Doublons potentiels trouvÃ©s dans Salesforce: {len(duplicate_check['salesforce_duplicates'])}")

            if duplicate_check["sap_duplicates"]:
                result["warnings"].append(f"Doublons potentiels trouvÃ©s dans SAP: {len(duplicate_check['sap_duplicates'])}")

        except Exception as e:
            logger.exception(f"Erreur vÃ©rification doublons: {str(e)}")
            duplicate_check["warnings"].append(f"âŒ Erreur vÃ©rification doublons: {str(e)}")
            result["duplicate_check"] = duplicate_check
    
    async def _enrich_data(self, client_data: Dict[str, Any], result: Dict[str, Any]):
        """Enrichissement automatique des donnÃ©es"""
        
        # Normalisation du nom
        company_name = client_data.get("company_name", "")
        if company_name:
            # Nettoyer et normaliser
            normalized_name = re.sub(r'\s+', ' ', company_name.strip())
            normalized_name = normalized_name.title()  # Capitalisation
            
            if normalized_name != company_name:
                result["enriched_data"]["normalized_company_name"] = normalized_name
                result["suggestions"].append("Nom d'entreprise normalisÃ©")
        
        # GÃ©nÃ©ration d'un code client unique suggÃ©rÃ©
        if company_name:
            clean_name = re.sub(r'[^a-zA-Z0-9]', '', company_name)[:8].upper()
            timestamp = str(int(datetime.now().timestamp()))[-4:]
            suggested_code = f"C{clean_name}{timestamp}"
            result["enriched_data"]["suggested_client_code"] = suggested_code
        
        # Enrichissement de l'adresse web
        website = client_data.get("website", "")
        if website and not website.startswith(("http://", "https://")):
            result["enriched_data"]["normalized_website"] = f"https://{website}"
        
        # GÃ©nÃ©ration d'un email de contact si manquant
        email = client_data.get("email", "")
        if not email and website:
            domain = website.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
            suggested_email = f"contact@{domain}"
            result["enriched_data"]["suggested_email"] = suggested_email
            result["suggestions"].append(f"Email suggÃ©rÃ©: {suggested_email}")
    
    async def _validate_consistency(self, client_data: Dict[str, Any], result: Dict[str, Any]):
        """Validation de cohÃ©rence globale"""
        
        # CohÃ©rence adresse/pays
        country = client_data.get("billing_country", "").lower()
        postal_code = client_data.get("billing_postal_code", "")
        
        if "france" in country and postal_code:
            validation = FormatValidator.validate_format(postal_code, 'postal_code', 'FR')
            if not validation["valid"]:
                result["warnings"].append(validation["error"])
        
        elif "united states" in country or "usa" in country and postal_code:
            if not re.match(r'^\d{5}(-\d{4})?$', postal_code):
                result["warnings"].append("Code postal incohÃ©rent avec le pays USA")
        
        # CohÃ©rence tÃ©lÃ©phone/pays
        phone = client_data.get("phone", "")
        if phone and "france" in country:
            if not (phone.startswith("+33") or phone.startswith("0")):
                result["warnings"].append("NumÃ©ro de tÃ©lÃ©phone incohÃ©rent avec le pays France")
    
    # MÃ©thodes utilitaires
    async def _call_insee_api(self, endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Appel gÃ©nÃ©rique Ã  l'API INSEE
        
        Args:
            endpoint: Point d'accÃ¨s API (ex: /siret/12345678901234)
            params: ParamÃ¨tres de requÃªte
        
        Returns:
            RÃ©sultat de l'appel API
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
                return {"error": "Non trouvÃ©", "status_code": 404}
            
            else:
                return {"error": f"Erreur HTTP {response.status_code}"}
        
        except Exception as e:
            logger.error(f"Erreur appel INSEE: {e}")
            return {"error": str(e)}
    async def _validate_siret_insee(self, siret: str) -> Dict[str, Any]:
        """Validation SIRET simplifiÃ©e"""
        result = await self._call_insee_api(f"/siret/{siret}")
        
        if result.get("success"):
            # Traitement des donnÃ©es spÃ©cifique SIRET
            return self._process_siret_data(result["data"])
        else:
            return {"valid": False, "error": result["error"]}
    
    async def _validate_address_france(self, client_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validation adresse via API Adresse gouv.fr."""
        street = client_data.get("billing_street", "")
        city = client_data.get("billing_city", "")
        postal_code = client_data.get("billing_postal_code", "")

        if not street or not (city or postal_code): # Au moins rue + (ville ou CP)
            logger.warning("Adresse incomplÃ¨te pour validation via API Adresse Gouv.")
            return {"found": False, "error": "Adresse incomplÃ¨te pour validation", "validation_method": "skipped"}

        # Construire la requÃªte, donner la prioritÃ© au code postal s'il est prÃ©sent
        query_parts = [street, postal_code if postal_code else city]
        query = " ".join(filter(None, query_parts))
        
        params = {"q": query, "limit": 1} # On prend le premier meilleur rÃ©sultat
        
        logger.info(f"Validation adresse via API gouv.fr: {query}")

        try:
            response = await self.http_client.get(API_ADRESSE_GOUV_URL, params=params, timeout=10.0)
            # La levÃ©e d'exception pour 4xx/5xx est gÃ©rÃ©e par le hook _raise_on_4xx_5xx

            data = response.json()
            
            if response.status_code == 200 and data.get("features"):
                best_match = data["features"][0] # On prend le premier rÃ©sultat
                properties = best_match.get("properties", {})
                geometry = best_match.get("geometry", {})
                
                # VÃ©rifier la pertinence du rÃ©sultat (score Ã©levÃ©)
                # L'API retourne un score, un score > 0.7 est gÃ©nÃ©ralement bon.
                # Pour simplifier, on prend le premier, mais en production on vÃ©rifierait le score.
                # score = properties.get("score", 0.0)
                # if score < 0.7: # Seuil de pertinence
                #     logger.warning(f"Adresse trouvÃ©e mais score faible ({score:.2f}): {properties.get('label')}")
                #     return {"found": False, "error": "Adresse non trouvÃ©e avec certitude", "validation_method": "api_ban", "low_score": True}


                normalized_address = {
                    "label": properties.get("label"), # Adresse complÃ¨te formatÃ©e
                    "street_number": properties.get("housenumber"),
                    "street_name": properties.get("street") or properties.get("name"), # "name" pour les lieux-dits/routes
                    "postal_code": properties.get("postcode"),
                    "city": properties.get("city"),
                    "context": properties.get("context"), # Ex: "75, Paris, ÃŽle-de-France"
                    "type": properties.get("type"), # Ex: "housenumber", "street"
                    "coordinates": {
                        "latitude": geometry.get("coordinates", [None, None])[1], # Ordre: lon, lat
                        "longitude": geometry.get("coordinates", [None, None])[0]
                    },
                    "validation_method": "api_ban" # BAN = Base Adresse Nationale
                }
                
                # Comparer si l'adresse trouvÃ©e est significativement diffÃ©rente
                # (logique de suggestion ou d'alerte Ã  affiner)
                # Par exemple, si le code postal ou la ville diffÃ¨rent de l'entrÃ©e.
                
                return {"found": True, "address": normalized_address}
            
            elif not data.get("features"):
                logger.warning(f"Aucune adresse trouvÃ©e pour: {query}")
                return {"found": False, "error": "Adresse non trouvÃ©e", "validation_method": "api_ban"}
            else:
                # Cas d'erreur non standard de l'API si la structure est inattendue
                logger.error(f"RÃ©ponse inattendue de l'API Adresse pour {query}: {data}")
                return {"found": False, "error": "RÃ©ponse API Adresse inattendue", "validation_method": "api_ban"}

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
        """Validation format tÃ©lÃ©phone international"""
        # Nettoyer le numÃ©ro
        clean_phone = re.sub(r'[\s\-\.\(\)]', '', phone)
        
        # Patterns pour diffÃ©rents formats
        patterns = [
            r'^(\+33|0033)[1-9]\d{8}$',  # France
            r'^(\+1|001)?[2-9]\d{2}[2-9]\d{2}\d{4}$',  # USA/Canada
            r'^(\+44|0044|0)[1-9]\d{8,9}$',  # UK
            r'^\+[1-9]\d{1,14}$'  # Format international gÃ©nÃ©ral
        ]
        
        return any(re.match(pattern, clean_phone) for pattern in patterns)
    
    def _get_us_states(self) -> List[str]:
        """Liste des codes d'Ã©tats amÃ©ricains"""
        return [
            "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
            "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
            "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
            "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
            "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY"
        ]

    async def _search_company_insee(self, query: str) -> Dict[str, Any]:
        """Recherche d'entreprise simplifiÃ©e"""
        result = await self._call_insee_api("/siret", {"q": query, "nombre": 10})
        
        if result.get("success"):
            return self._process_search_results(result["data"])
        else:
            return {"error": result["error"]}
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques de validation"""
        # Calculer la taille du cache selon le type utilisÃ©
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
# MODIFICATION : MÃ©thode de validation principale enrichie
    async def validate_client_data_enriched(self, client_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        ðŸ” Validation client enrichie avec l'agent de recherche d'entreprises
        
        Workflow:
        1. Validation des donnÃ©es de base
        2. Enrichissement avec l'agent de recherche
        3. Validation SIREN si disponible
        4. Suggestions si entreprise non trouvÃ©e
        
        Args:
            client_data: DonnÃ©es client Ã  valider
            
        Returns:
            RÃ©sultat de validation enrichi
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
            
            # 4. Suggestions si entreprise non trouvÃ©e
            suggestions = []
            if not enriched_data.get('enriched_data'):
                company_name = client_data.get('company_name') or client_data.get('name')
                if company_name:
                    suggestions = await company_search_service.get_suggestions(company_name)
            
            # RÃ©sultat consolidÃ©
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
        ðŸ” Trouve des entreprises similaires pour rÃ©solution de doublons
        
        Args:
            company_name: Nom de l'entreprise Ã  rechercher
            max_results: Nombre maximum de rÃ©sultats
            
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

# NOUVEAU : DÃ©corateur pour l'enrichissement automatique
def with_company_enrichment(func):
    """
    DÃ©corateur pour enrichir automatiquement les donnÃ©es client avec l'agent
    """
    async def wrapper(self, client_data: Dict[str, Any], *args, **kwargs):
        # Enrichissement automatique
        enriched_data = await self.enrich_with_company_agent(client_data)

        # Appel de la fonction originale avec les donnÃ©es enrichies
        result = await func(self, enriched_data, *args, **kwargs)

        # Ajout des informations d'enrichissement au rÃ©sultat
        if isinstance(result, dict):
            result['enrichment_applied'] = 'enriched_data' in enriched_data
            result['enrichment_source'] = enriched_data.get('enriched_data', {}).get('source')

        return result

    return wrapper


class FormatValidator:
    """Validateur de formats rÃ©utilisable"""
    
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
            value: Valeur Ã  valider
            format_type: Type de format (postal_code, phone, business_id)
            country: Code pays
        
        Returns:
            RÃ©sultat de validation
        """
        if not value:
            return {"valid": False, "error": "Valeur vide"}
        
        pattern = cls.PATTERNS.get(format_type, {}).get(country)
        if not pattern:
            return {"valid": False, "error": f"Format non supportÃ© pour {country}"}
        
        clean_value = re.sub(r'[\s\-\.\(\)]', '', value)
        is_valid = bool(re.match(pattern, clean_value.upper()))
        
        return {
            "valid": is_valid,
            "cleaned_value": clean_value,
            "pattern_used": pattern,
            "error": None if is_valid else f"Format invalide pour {country}"
        }
# EXEMPLE D'UTILISATION du dÃ©corateur
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
    """Fonction utilitaire pour valider des donnÃ©es client"""
    validator = ClientValidator()
    return await validator.validate_complete(client_data, country)
