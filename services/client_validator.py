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
    
    async def validate_complete(self, client_data: Dict[str, Any], country: str = "FR") -> Dict[str, Any]:
        """
        Validation complète d'un client selon le pays
        
        Args:
            client_data: Données du client à valider
            country: Code pays (FR, US, UK, etc.)
            
        Returns:
            Résultat de validation avec erreurs, avertissements et données enrichies
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
            
            # 4. Contrôle de doublons
            logger.info("4️⃣ Contrôle de doublons...")
            await self._check_duplicates(client_data, validation_result)
            
            # 5. Enrichissement automatique des données
            logger.info("5️⃣ Enrichissement des données...")
            await self._enrich_data(client_data, validation_result)
            
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
        """Contrôle de doublons avancé avec similarité"""
        company_name = client_data.get("company_name", "")
        if not company_name or not FUZZYWUZZY_AVAILABLE:
            if not FUZZYWUZZY_AVAILABLE:
                result["warnings"].append("Contrôle de doublons limité (fuzzywuzzy non disponible)")
            return
        
        try:
            # Import conditionnel des connecteurs
            try:
                from services.mcp_connector import MCPConnector
                MCP_AVAILABLE = True
            except ImportError:
                MCP_AVAILABLE = False  # noqa: F841
                result["warnings"].append("Contrôle de doublons non disponible (MCPConnector non disponible)")
                return
            
            similar_clients = []
            
            # Recherche Salesforce
            try:
                # Échapper les apostrophes pour SOQL
                safe_name = company_name.replace("'", "\\'")[:20]
                sf_query = f"SELECT Id, Name, Phone, BillingCity FROM Account WHERE Name LIKE '%{safe_name}%' LIMIT 10"
                sf_result = await MCPConnector.call_salesforce_mcp("salesforce_query", {"query": sf_query})
                
                if "error" not in sf_result and sf_result.get("records"):
                    for record in sf_result["records"]:
                        similarity = fuzz.ratio(company_name.lower(), record.get("Name", "").lower())
                        if similarity >= 80:  # Seuil de similarité configuré
                            similar_clients.append({
                                "system": "Salesforce",
                                "id": record.get("Id"),
                                "name": record.get("Name"),
                                "similarity": similarity,
                                "phone": record.get("Phone"),
                                "city": record.get("BillingCity")
                            })
            except Exception as e:
                logger.warning(f"Erreur recherche Salesforce: {str(e)}")
            
            # Recherche SAP
            try:
                sap_result = await MCPConnector.call_sap_mcp("sap_search", {
                    "query": company_name[:20],
                    "entity_type": "BusinessPartners",
                    "limit": 10
                })
                
                if "error" not in sap_result and sap_result.get("results"):
                    for record in sap_result["results"]:
                        similarity = fuzz.ratio(company_name.lower(), record.get("CardName", "").lower())
                        if similarity >= 80:
                            similar_clients.append({
                                "system": "SAP",
                                "card_code": record.get("CardCode"),
                                "name": record.get("CardName"),
                                "similarity": similarity,
                                "phone": record.get("Phone1"),
                                "city": record.get("City")
                            })
            except Exception as e:
                logger.warning(f"Erreur recherche SAP: {str(e)}")
            
            # Résultats de la recherche de doublons
            if similar_clients:
                # Trier par similarité décroissante
                similar_clients.sort(key=lambda x: x["similarity"], reverse=True)
                
                result["duplicate_check"] = {
                    "duplicates_found": True,
                    "count": len(similar_clients),
                    "similar_clients": similar_clients[:5],  # Limiter à 5 résultats
                    "action_required": True,
                    "highest_similarity": similar_clients[0]["similarity"]
                }
                
                if similar_clients[0]["similarity"] >= 90:
                    result["errors"].append(f"Client très similaire trouvé (similarité: {similar_clients[0]['similarity']}%)")
                    result["suggestions"].append("Vérifiez s'il s'agit d'un doublon avant création")
                else:
                    result["warnings"].append(f"{len(similar_clients)} client(s) potentiellement similaire(s) trouvé(s)")
            else:
                result["duplicate_check"] = {
                    "duplicates_found": False,
                    "count": 0,
                    "similar_clients": [],
                    "action_required": False
                }
                result["suggestions"].append("✅ Aucun doublon détecté")
        
        except Exception as e:
            logger.warning(f"Erreur contrôle doublons: {str(e)}")
            result["warnings"].append("Impossible de vérifier les doublons")
    
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
            if not re.match(r'^\d{5}$', postal_code):
                result["warnings"].append("Code postal incohérent avec le pays France")
        
        elif "united states" in country or "usa" in country and postal_code:
            if not re.match(r'^\d{5}(-\d{4})?$', postal_code):
                result["warnings"].append("Code postal incohérent avec le pays USA")
        
        # Cohérence téléphone/pays
        phone = client_data.get("phone", "")
        if phone and "france" in country:
            if not (phone.startswith("+33") or phone.startswith("0")):
                result["warnings"].append("Numéro de téléphone incohérent avec le pays France")
    
    # Méthodes utilitaires
    
    async def _validate_siret_insee(self, siret: str) -> Dict[str, Any]:
            """Validation SIRET via API INSEE - VERSION CORRIGÉE."""
            
            if not self.insee_consumer_key or not self.insee_consumer_secret:
                logger.warning("Validation INSEE désactivée (clés manquantes).")
                return {"valid": False, "error": "Configuration API INSEE manquante", "validation_method": "skipped"}

            access_token = await self._get_insee_token()
            if not access_token:
                return {"valid": False, "error": "Impossible d'obtenir le token INSEE", "validation_method": "token_error"}

            headers = {"Authorization": f"Bearer {access_token}"}
            url = f"{INSEE_API_BASE_URL}/siret/{siret}"
            
            logger.info(f"Validation SIRET {siret} via API INSEE...")

            try:
                # CORRECTION: Appel HTTP sans le hook qui lève automatiquement les exceptions
                # pour pouvoir gérer les 404 proprement
                async with httpx.AsyncClient() as client:
                    response = await client.get(url, headers=headers, timeout=10.0)
                
                # CORRECTION: Gestion manuelle des codes de statut
                if response.status_code == 200:
                    data = response.json()
                    
                    if data.get("header", {}).get("statut") == 200:
                        etablissement = data.get("etablissement", {})
                        unite_legale = etablissement.get("uniteLegale", {})
                        adresse = etablissement.get("adresseEtablissement", {})
                        
                        # Construction d'une adresse lisible
                        full_address_parts = [
                            adresse.get("numeroVoieEtablissement"),
                            adresse.get("typeVoieEtablissement"),
                            adresse.get("libelleVoieEtablissement"),
                            adresse.get("codePostalEtablissement"),
                            adresse.get("libelleCommuneEtablissement")
                        ]
                        full_address = " ".join(filter(None, full_address_parts)).strip()

                        result = {
                            "valid": True,
                            "data": {
                                "siret": etablissement.get("siret"),
                                "siren": etablissement.get("siren"),
                                "nic": etablissement.get("nic"),
                                "company_name": unite_legale.get("denominationUniteLegale") or \
                                                f"{unite_legale.get('nomUniteLegale', '')} {unite_legale.get('prenom1UniteLegale', '')}".strip(),
                                "creation_date": unite_legale.get("dateCreationUniteLegale"),
                                "activity_code": etablissement.get("activitePrincipaleEtablissement"),
                                "activity_label": "N/A", # L'API Siret ne fournit pas le libellé direct
                                "address": full_address,
                                "postal_code": adresse.get("codePostalEtablissement"),
                                "city": adresse.get("libelleCommuneEtablissement"),
                                "status": "Actif" if unite_legale.get("etatAdministratifUniteLegale") == "A" else "Inactif",
                                "is_siege": etablissement.get("etablissementSiege"),
                                "validation_method": "api_insee"
                            }
                        }
                        return result
                    else:
                        error_message = data.get("header", {}).get("message", "Erreur inconnue de l'API INSEE")
                        logger.error(f"Erreur API INSEE pour SIRET {siret}: {error_message}")
                        return {"valid": False, "error": f"API INSEE: {error_message}", "validation_method": "api_insee"}
                
                elif response.status_code == 404:
                    # CORRECTION: Gestion propre du 404 sans essayer de lire le contenu
                    logger.warning(f"SIRET {siret} non trouvé via API INSEE (404).")
                    return {"valid": False, "error": "SIRET non trouvé", "validation_method": "api_insee"}
                
                else:
                    # CORRECTION: Autres codes d'erreur - essayer de lire le contenu si possible
                    try:
                        error_data = response.json()
                        error_message = error_data.get("header", {}).get("message", f"Erreur HTTP {response.status_code}")
                    except Exception:
                        error_message = f"Erreur HTTP {response.status_code}"
                    
                    logger.error(f"Erreur API INSEE pour SIRET {siret}: {response.status_code} - {error_message}")
                    return {"valid": False, "error": f"API INSEE: {error_message}", "validation_method": "api_insee"}

            except httpx.TimeoutException:
                logger.error(f"Timeout lors de la validation SIRET {siret} via API INSEE.")
                return {"valid": False, "error": "Timeout API INSEE", "validation_method": "api_insee"}
            except Exception as e:
                logger.exception(f"Erreur inattendue validation SIRET {siret}: {str(e)}")
                return {"valid": False, "error": f"Erreur interne: {str(e)}", "validation_method": "api_insee"}
    
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

    async def _search_company_insee(self, search_query: str) -> Dict[str, Any]:
        """
        Recherche d'entreprises via l'API INSEE

        Args:
            search_query: Terme de recherche (nom d'entreprise, SIREN, etc.)

        Returns:
            Dictionnaire contenant les résultats de la recherche ou vide en cas d'erreur
        """
        if not self.insee_consumer_key or not self.insee_consumer_secret:
            logger.warning("Clés INSEE non configurées pour la recherche")
            return {"error": "Configuration API INSEE manquante"}

        access_token = await self._get_insee_token()
        if not access_token:
            logger.error("Impossible d'obtenir le token INSEE pour la recherche")
            return {"error": "Impossible d'obtenir le token INSEE"}

        try:
            headers = {"Authorization": f"Bearer {access_token}"}
            # Utiliser l'API de recherche INSEE
            url = f"{INSEE_API_BASE_URL}/siret"
            params = {
                'q': search_query,
                'nombre': 10,  # Limiter à 10 résultats
                'masquerValeursNulles': 'true'  # Ne pas retourner les champs vides
            }

            logger.info(f"Recherche d'entreprise INSEE: {search_query}")

            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, params=params, timeout=10.0)

                if response.status_code == 200:
                    data = response.json()
                    if data.get("header", {}).get("statut") == 200:
                        return {
                            "success": True,
                            "results": data.get("etablissements", []),
                            "count": len(data.get("etablissements", [])),
                            "query": search_query
                        }
                    else:
                        error_message = data.get("header", {}).get("message", "Erreur inconnue de l'API INSEE")
                        logger.error(f"Erreur API INSEE recherche: {error_message}")
                        return {"error": error_message}
                elif response.status_code == 404:
                    return {"success": True, "results": [], "count": 0, "query": search_query}
                else:
                    logger.error(f"Erreur HTTP API INSEE recherche: {response.status_code}")
                    return {"error": f"Erreur HTTP {response.status_code}"}

        except httpx.TimeoutException:
            logger.error("Timeout lors de la recherche INSEE")
            return {"error": "Timeout API INSEE"}
        except Exception as e:
            logger.exception(f"Erreur inattendue lors de la recherche INSEE: {str(e)}")
            return {"error": f"Erreur interne: {str(e)}"}
    
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

# Fonction utilitaire pour usage direct
async def validate_client_data(client_data: Dict[str, Any], country: str = "FR") -> Dict[str, Any]:
    """Fonction utilitaire pour valider des données client"""
    validator = ClientValidator()
    return await validator.validate_complete(client_data, country)