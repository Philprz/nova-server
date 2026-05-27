# utils/client_lister.py - VERSION CORRIGÉE
"""
Fonctions utilitaires pour lister tous les clients de Salesforce et SAP
CORRECTION: Traitement approprié des réponses MCP
"""

import logging
import asyncio
from typing import List, Dict, Any
from services.mcp_connector import MCPConnector
from services.security_helpers import escape_soql

logger = logging.getLogger(__name__)

class ClientLister:
    """Classe pour lister les clients des deux systèmes - VERSION CORRIGÉE"""
    
    def __init__(self):
        self.mcp_connector = MCPConnector()
    
    async def get_all_salesforce_clients(self) -> List[Dict[str, Any]]:
        """Récupère tous les comptes Salesforce - CORRIGÉ"""
        logger.info("Récupération de tous les comptes Salesforce...")
        
        try:
            query = """
            SELECT Id, Name, AccountNumber, Type, Industry, AnnualRevenue, 
                   Phone, Fax, Website, Description,
                   BillingStreet, BillingCity, BillingState, BillingPostalCode, BillingCountry,
                   ShippingStreet, ShippingCity, ShippingState, ShippingPostalCode, ShippingCountry,
                   CreatedDate, LastModifiedDate
            FROM Account 
            ORDER BY Name
            """
            
            result = await self.mcp_connector.call_mcp(
                "salesforce_mcp", 
                "salesforce_query",
                {"query": query}
            )
            
            # CORRECTION: Vérifier d'abord si 'success' est False ou 'error' existe
            if result.get("success") is False or "error" in result:
                error_msg = result.get("error", "Erreur inconnue")
                logger.error(f"❌ Erreur Salesforce explicite: {error_msg}")
                return []
            
            # CORRECTION: Vérifier 'records' au lieu de success
            if "records" in result:
                clients = result["records"]
                logger.info(f"✅ {len(clients)} comptes Salesforce récupérés")
                return clients
            
            # CORRECTION: Essayer aussi 'data' comme fallback
            if "data" in result:
                clients = result["data"]
                logger.info(f"✅ {len(clients)} comptes Salesforce récupérés (via data)")
                return clients
            
            # Aucun champ attendu trouvé
            logger.warning(f"⚠️ Réponse Salesforce inattendue. Clés disponibles: {list(result.keys())}")
            logger.debug(f"Contenu complet de la réponse: {result}")
            return []
                
        except Exception as e:
            logger.error(f"❌ Exception lors de la récupération Salesforce: {str(e)}")
            return []
    
    async def get_all_sap_clients(self) -> List[Dict[str, Any]]:
        """Récupère tous les clients SAP (BusinessPartners) - CORRIGÉ"""
        logger.info("Récupération de tous les clients SAP...")
        
        try:
            result = await self.mcp_connector.call_mcp(
                "sap_mcp",
                "sap_read", 
                {
                    "endpoint": "/BusinessPartners?$filter=CardType eq 'cCustomer'&$orderby=CardCode",
                    "method": "GET"
                }
            )
            
            # CORRECTION: Vérification explicite des erreurs uniquement
            if result.get("error") or result.get("success") is False:
                error_msg = result.get("error", "Erreur inconnue")
                logger.error(f"❌ Erreur SAP explicite: {error_msg}")
                return []

            # Extraction des données dans l'ordre de priorité
            if "value" in result and isinstance(result["value"], list):
                clients = result["value"]
                logger.info(f"✅ {len(clients)} clients SAP récupérés")
                return clients
            elif "results" in result and isinstance(result["results"], list):
                clients = result["results"]
                logger.info(f"✅ {len(clients)} clients SAP récupérés (via results)")
                return clients
            elif "data" in result and isinstance(result["data"], list):
                clients = result["data"]
                logger.info(f"✅ {len(clients)} clients SAP récupérés (via data)")
                return clients
            elif isinstance(result, list):
                logger.info(f"✅ {len(result)} clients SAP récupérés (liste directe)")
                return result
            
            # Aucun champ attendu trouvé
            logger.warning(f"⚠️ Réponse SAP inattendue. Clés disponibles: {list(result.keys()) if isinstance(result, dict) else type(result)}")
            logger.debug(f"Contenu complet de la réponse: {result}")
            return []
                
        except Exception as e:
            logger.error(f"❌ Exception lors de la récupération SAP: {str(e)}")
            return []
    
    async def _search_salesforce_by_name(self, client_name: str) -> List[Dict[str, Any]]:
        """Recherche dans Salesforce avec différentes variantes - CORRIGÉ"""
        try:
            # Requête SOQL corrigée - insensible à la casse + champs existants
            safe_name = escape_soql(client_name)
            exact_query = f"""
            SELECT Id, Name, AccountNumber, Phone, BillingCity, BillingCountry, BillingPostalCode, Type, Industry, Website
            FROM Account
            WHERE (Name = '{safe_name}'
            OR Name LIKE '{safe_name} %'
            OR Name LIKE '% {safe_name}'
            OR Name LIKE '%{safe_name}%')
            LIMIT 20
            """.strip()
            
            result = await self.mcp_connector.call_mcp(
                "salesforce_mcp",
                "salesforce_query",
                {"query": exact_query}
            )
            
            # CORRECTION: Vérifier d'abord les données, puis les erreurs
            # Gestion spéciale des sessions expirées
            if result.get("error") and "EXPIRED_PASSWORD" in str(result.get("error")):
                logger.error(f"🔐 Session Salesforce expirée - Reconnexion nécessaire")
                return []
            if "records" in result and result["records"]:
                logger.info(f"✅ Recherche exacte Salesforce: {len(result['records'])} résultats")
                return result["records"]
            elif "data" in result and result["data"]:
                logger.info(f"✅ Recherche exacte Salesforce: {len(result['data'])} résultats")
                return result["data"]
            
            # Vérifier les erreurs seulement après avoir testé les données
            # Debug complet de la réponse MCP
            logger.info(f"🔍 DEBUG Salesforce - Type réponse: {type(result)}")
            logger.info(f"🔍 DEBUG Salesforce - Clés: {list(result.keys()) if isinstance(result, dict) else 'Non-dict'}")
            if isinstance(result, dict) and result.get("error"):
                logger.error(f"🔍 DEBUG Salesforce - Erreur détaillée: {result.get('error')}")
                logger.error(f"🔍 DEBUG Salesforce - Réponse complète: {result}")
            if result.get("success") is False or "error" in result:
                error_msg = result.get("error", "Erreur inconnue")
                logger.error(f"❌ Erreur recherche exacte Salesforce: {error_msg}")
                # Ne pas retourner ici, continuer avec la recherche approximative
            
            # Si pas de résultat exact, recherche approximative simple
            fuzzy_query = f"""
            SELECT Id, Name, AccountNumber, Phone, BillingCity, BillingCountry
            FROM Account
            WHERE Name LIKE '%{escape_soql(client_name)}%'
            LIMIT 10
            """.strip()
            
            result = await self.mcp_connector.call_mcp(
                "salesforce_mcp",
                "salesforce_query",
                {"query": fuzzy_query}
            )
            
            # CORRECTION: Même logique pour la recherche approximative
            if "records" in result and result["records"]:
                logger.info(f"✅ Recherche approximative Salesforce: {len(result['records'])} résultats")
                return result["records"]
            elif "data" in result and result["data"]:
                logger.info(f"✅ Recherche approximative Salesforce: {len(result['data'])} résultats")
                return result["data"]
            
            # Vérifier les erreurs
            if result.get("success") is False or "error" in result:
                error_msg = str(result.get("error", "Erreur inconnue"))
                # Tolérer l'indisponibilité Salesforce et basculer silencieusement sur SAP
                if error_msg == "salesforce_unavailable" or "authentification salesforce" in error_msg.lower() or "invalid_login" in error_msg.lower():
                    logger.warning(f"⚠️ Salesforce indisponible (auth). Fallback SAP activé: {error_msg}")
                else:
                    logger.error(f"❌ Erreur recherche approximative Salesforce: {error_msg}")
            
            logger.info(f"⚠️ Aucun résultat Salesforce pour: {client_name}")
            return []
            
        except Exception as e:
            logger.error(f"❌ Erreur recherche Salesforce: {str(e)}")
            # En cas d'erreur Salesforce, continuer avec la recherche SAP
            logger.info("⚠️ Salesforce indisponible, recherche SAP uniquement")
            return []
    
    async def _search_sap_by_name(self, client_name: str) -> List[Dict[str, Any]]:
        """Recherche dans SAP avec différentes variantes et diagnostics améliorés"""
        try:
            # Utiliser sap_read avec OData filter au lieu de sap_search
            result = await self.mcp_connector.call_mcp(
                "sap_mcp",
                "sap_read",
                {
                    "endpoint": f"/BusinessPartners?$filter=contains(CardName,'{client_name}') or startswith(CardName,'{client_name}')&$top=10",
                    "method": "GET"
                }
            )

            # diagnostics
            logger.debug(f"🔍 Réponse SAP brute pour {client_name}: {result}")
            logger.debug(f"Type de réponse: {type(result)}")
            if isinstance(result, dict):
                logger.debug(f"Clés disponibles: {list(result.keys())}")
             # Validation et filtrage des données après appel MCP
            if isinstance(result, dict) and "value" in result:
                clients = result["value"]
                # Filtrer les entrées vides ou invalides
                clients = [c for c in clients if c and c.get('CardName') and c.get('CardName').strip()]
                logger.info(f"✅ Recherche SAP: {len(clients)} résultats valides (après filtrage)")
                return clients
            # garde-fou si None ou type inattendu
            if result is None or not isinstance(result, (dict, list)):
                logger.warning(f"⚠️ Résultat SAP invalide pour: {client_name}")
                return []

            # vérification explicite d’erreur
            if isinstance(result, dict) and (result.get("error") or result.get("success") is False):
                logger.warning(f"⚠️ Erreur SAP explicite: {result.get('error', 'Erreur inconnue')}")
                return []

            # parsing adaptatif des clés possibles
            data_keys = ["results", "value", "data", "odata.metadata"]
            clients: List[Dict[str, Any]] = []

            for key in data_keys:
                if isinstance(result, dict) and key in result and isinstance(result[key], list) and result[key]:
                    clients = result[key]
                    logger.info(f"✅ Recherche SAP: {len(clients)} résultats (clé: {key})")
                    break

            # fallback liste directe
            if not clients and isinstance(result, list):
                clients = result
                logger.info(f"✅ Recherche SAP: {len(clients)} résultats (liste directe)")

            # OData imbriqué sous 'd'
            if not clients and isinstance(result, dict) and isinstance(result.get("d"), dict):
                d_obj = result["d"]
                for key in data_keys:
                    if key in d_obj and isinstance(d_obj[key], list) and d_obj[key]:
                        clients = d_obj[key]
                        logger.info(f"✅ Recherche SAP OData: {len(clients)} résultats (d.{key})")
                        break
            # fallback tous les champs contenant des listes imbriquées dans le résultat     
            if not clients and isinstance(result, dict):
                for k, v in result.items():
                    if isinstance(v, list) and v and any(
                        isinstance(item, dict) and 
                        ('CardCode' in item or 'CardName' in item or 'Name' in item)
                        for item in v[:1]
                    ):
                        clients = v
                        logger.info(f"✅ Recherche SAP: {len(clients)} résultats (clé détectée: {k})")
                        break

            return clients or []

        except Exception as e:
            logger.exception(f"❌ Erreur recherche SAP: {e}")
            return []

    
    async def search_client_by_name(self, client_name: str) -> Dict[str, Any]:
        """Recherche spécifique d'un client par nom dans les deux systèmes - VERSION OPTIMISÉE (structure inchangée)"""
        logger.info(f"🔍 Recherche spécifique du client: {client_name}")
        # Normalisation entrée
        client_name = (client_name or "").strip()
        # Normalisation simple espaces multiples (sans import): "ACME   SA" -> "ACME SA"
        if client_name:
            client_name = " ".join(client_name.split())
        # Petit seuil anti-bruit (ex: "a" ou "x")
        MIN_LEN = 2

        # Structure de retour standardisée
        result = {
            "search_term": client_name,
            "salesforce": {"found": False, "clients": [], "count": 0},
            "sap": {"found": False, "clients": [], "count": 0},
            "deduplicated_clients": [],
            "total_found": 0
        }

        # Cas entrée vide ou trop courte
        if not client_name or len(client_name) < MIN_LEN:
            logger.warning("⚠️ Nom client vide/trop court: retour sans recherche")
            return result

        try:
            # Recherche parallèle dans les deux systèmes (avec timeout unitaire)
            # On conserve les mêmes noms de variables et la même structure.
            TIMEOUT_S = 5

            sf_task = asyncio.wait_for(self._search_salesforce_by_name(client_name), timeout=TIMEOUT_S)
            sap_task = asyncio.wait_for(self._search_sap_by_name(client_name), timeout=TIMEOUT_S)

            sf_clients, sap_clients = await asyncio.gather(sf_task, sap_task, return_exceptions=True)

            # Optionnel: borne douce pour éviter des payloads géants
            def _cap_list(lst, cap=500):
                return lst[:cap] if isinstance(lst, list) and len(lst) > cap else (lst if isinstance(lst, list) else [])

            # Traitement sécurisé des résultats Salesforce
            if isinstance(sf_clients, Exception):
                logger.error(f"❌ Erreur recherche Salesforce: {sf_clients}")
                sf_clients = []
            elif sf_clients:
                sf_clients = _cap_list(sf_clients)
                result["salesforce"] = {
                    "found": True,
                    "clients": sf_clients,
                    "count": len(sf_clients)
                }
                logger.info(f"✅ Salesforce: {len(sf_clients)} clients trouvés")

            # Traitement sécurisé des résultats SAP
            if isinstance(sap_clients, Exception):
                logger.error(f"❌ Erreur recherche SAP: {sap_clients}")
                sap_clients = []
            elif sap_clients:
                sap_clients = _cap_list(sap_clients)
                result["sap"] = {
                    "found": True,
                    "clients": sap_clients,
                    "count": len(sap_clients)
                }
                logger.info(f"✅ SAP: {len(sap_clients)} clients trouvés")

            # Protection contre les valeurs non-list
            sf_clients = sf_clients if isinstance(sf_clients, list) else []
            sap_clients = sap_clients if isinstance(sap_clients, list) else []

            # Déduplication (protégée)
            if sf_clients or sap_clients:
                try:
                    deduplicated_clients = self._deduplicate_clients(sf_clients, sap_clients)
                except Exception as dedup_err:
                    logger.exception(f"❌ Erreur déduplication: {dedup_err}")
                    # Fallback: concat simple
                    deduplicated_clients = (sf_clients or []) + (sap_clients or [])

                result["deduplicated_clients"] = deduplicated_clients
                result["total_found"] = len(deduplicated_clients)
                logger.info(
                    f"🔄 Déduplication: {len(sf_clients)} SF + {len(sap_clients)} SAP = {len(deduplicated_clients)} clients uniques"
                )

            logger.info(f"✅ Recherche terminée: {result['total_found']} clients trouvés")
            return result

        except Exception as e:
            logger.exception(f"❌ Erreur recherche client '{client_name}': {e}")
            return result
    
    def format_client_summary(self, salesforce_clients: List[Dict], sap_clients: List[Dict]) -> Dict[str, Any]:
        """Formate un résumé des clients pour affichage - CORRIGÉ"""
        
        # CORRECTION: Protection contre les clients None ou vides
        sf_clients = salesforce_clients or []
        sap_clients = sap_clients or []
        
        summary = {
            "salesforce": {
                "total": len(sf_clients),
                "sample": sf_clients[:5] if sf_clients else [],
                "names": [c.get("Name", "Sans nom") for c in sf_clients[:10] if c]
            },
            "sap": {
                "total": len(sap_clients),
                "sample": sap_clients[:5] if sap_clients else [],
                "names": [c.get("CardName", "Sans nom") for c in sap_clients[:10] if c]
            },
            "total_combined": len(sf_clients) + len(sap_clients)
        }
        
        return summary
    def _deduplicate_clients(self, sf_clients: List[Dict], sap_clients: List[Dict]) -> List[Dict]:
        """Déduplique les clients basé sur l'identifiant de liaison (AccountNumber <-> CardCode)"""
        
        unique_clients = []
        used_sap_indices = set()
        
        # Traiter clients Salesforce
        for sf_client in sf_clients:
            sf_account_number = sf_client.get('AccountNumber', '').strip()
            
            # Chercher correspondance SAP par CardCode
            best_match_idx = None
            
            if sf_account_number:  # Si Salesforce a un AccountNumber
                for idx, sap_client in enumerate(sap_clients):
                    if idx in used_sap_indices:
                        continue
                    
                    sap_card_code = sap_client.get('CardCode', '').strip()
                    
                    # Correspondance exacte sur l'identifiant
                    if sf_account_number == sap_card_code:
                        best_match_idx = idx
                        break
            
            # Fusionner si correspondance trouvée
            if best_match_idx is not None:
                used_sap_indices.add(best_match_idx)
                unique_clients.append({
                    **sf_client,
                    'sap_data': sap_clients[best_match_idx],
                    'source': 'SAP & Salesforce',
                    'CardCode': sap_clients[best_match_idx].get('CardCode', '')
                })
            else:
                unique_clients.append({**sf_client, 'source': 'Salesforce'})
        
        # Ajouter clients SAP non correspondus
        for idx, sap_client in enumerate(sap_clients):
            if idx not in used_sap_indices:
                unique_clients.append({**sap_client, 'source': 'SAP'})
        
        # Après la déduplication par identifiant, déduplication par nom similaire
        unique_clients = self._merge_similar_clients(unique_clients)
        
        return unique_clients
    
    def _normalize_company_name(self, name: str) -> str:
        """Normalise le nom d'entreprise pour comparaison"""
        if not name:
            return ""
        # Convertir en majuscules et supprimer les mots communs
        normalized = name.upper().strip()
        # Supprimer les mots génériques SAUF si c'est la différence principale
        words_to_remove = ['SA', 'SARL', 'SAS', 'EURL', 'COMPANY', 'CO', 'LTD', 'LTEE']
        # Garder GROUP/GROUPE pour distinguer les entités (ex: RONDOT vs RONDOT Group)
        for word in words_to_remove:
            normalized = normalized.replace(f' {word}', '').replace(f'{word} ', '')
        # Supprimer espaces multiples
        return ' '.join(normalized.split())

    def _find_similar_clients(self, clients: List[Dict]) -> List[List[int]]:
        """Trouve les groupes de clients similaires par nom"""
        groups = []
        used_indices = set()
        
        for i, client1 in enumerate(clients):
            if i in used_indices:
                continue
            
            name1 = self._normalize_company_name(
                client1.get('Name') or client1.get('CardName') or ''
            )
            if not name1:
                continue
                
            group = [i]
            used_indices.add(i)
            
            for j, client2 in enumerate(clients[i+1:], i+1):
                if j in used_indices:
                    continue
                    
                name2 = self._normalize_company_name(
                    client2.get('Name') or client2.get('CardName') or ''
                )
                
                # Similarité stricte : noms identiques après normalisation ET longueur similaire
                if (name1 and name2 and 
                    name1 == name2 and 
                    abs(len(client1.get('Name', '')) - len(client2.get('Name', ''))) <= 3):
                    group.append(j)
                    used_indices.add(j)
            
            if len(group) > 1:
                groups.append(group)
        
        return groups

    def _merge_similar_clients(self, clients: List[Dict]) -> List[Dict]:
        """Fusionne les clients similaires après la déduplication par identifiant"""
        if len(clients) <= 1:
            return clients
            
        similar_groups = self._find_similar_clients(clients)
        
        if not similar_groups:
            return clients
            
        result = []
        processed_indices = set()
        
        # Traiter les groupes similaires
        for group in similar_groups:
            # Prendre le client avec le plus d'informations ou SAP & Salesforce
            best_client = None
            best_score = -1
            
            for idx in group:
                client = clients[idx]
                score = 0
                
                # Privilégier les clients fusionnés SAP & Salesforce
                if client.get('source') == 'SAP & Salesforce':
                    score += 10
                
                # Compter les champs remplis
                score += sum(1 for v in client.values() if v and str(v).strip())
                
                if score > best_score:
                    best_score = score
                    best_client = client
            
            if best_client:
                result.append(best_client)
            
            processed_indices.update(group)
        
        # Ajouter les clients non groupés
        for i, client in enumerate(clients):
            if i not in processed_indices:
                result.append(client)
        
        return result
# Instance globale
client_lister = ClientLister()

# Fonctions pratiques pour utilisation directe - CORRIGÉES
async def list_all_clients() -> Dict[str, Any]:
    """Fonction principale pour lister tous les clients - CORRIGÉE"""
    logger.info("=== DÉMARRAGE LISTING COMPLET DES CLIENTS ===")
    
    # Récupération parallèle des deux systèmes
    sf_task = client_lister.get_all_salesforce_clients()
    sap_task = client_lister.get_all_sap_clients()
    
    salesforce_clients, sap_clients = await asyncio.gather(sf_task, sap_task)
    
    # CORRECTION: Protection contre None
    salesforce_clients = salesforce_clients or []
    sap_clients = sap_clients or []
    
    # Formatage du résumé
    summary = client_lister.format_client_summary(salesforce_clients, sap_clients)
    
    logger.info(f"=== RÉSUMÉ: {summary['total_combined']} clients total ===")
    logger.info(f"    Salesforce: {summary['salesforce']['total']}")
    logger.info(f"    SAP: {summary['sap']['total']}")
    
    return {
        "summary": summary,
        "salesforce_clients": salesforce_clients,
        "sap_clients": sap_clients,
        "timestamp": logger.info("Liste générée")
    }

async def find_client_everywhere(client_name: str) -> Dict[str, Any]:
    """Recherche approfondie d'un client spécifique - CORRIGÉE"""
    return await client_lister.search_client_by_name(client_name)

async def debug_raw_responses(client_name: str = "RONDOT") -> Dict[str, Any]:
    """Fonction de debug pour voir les réponses brutes des API"""
    logger.info(f"=== DEBUG: Réponses brutes pour {client_name} ===")
    
    connector = MCPConnector()
    
    # Test Salesforce
    sf_query = f"SELECT Id, Name, AccountNumber FROM Account WHERE Name LIKE '%{escape_soql(client_name)}%' LIMIT 3"
    sf_result = await connector.call_mcp("salesforce_mcp", "salesforce_query", {"query": sf_query})
    
    # Test SAP
    sap_result = await connector.call_mcp("sap_mcp", "sap_search", {
        "query": client_name,
        "entity_type": "BusinessPartners",
        "limit": 3
    })
    
    debug_info = {
        "salesforce_raw": sf_result,
        "sap_raw": sap_result,
        "salesforce_keys": list(sf_result.keys()) if isinstance(sf_result, dict) else str(type(sf_result)),
        "sap_keys": list(sap_result.keys()) if isinstance(sap_result, dict) else str(type(sap_result))
    }
    
    logger.info(f"SF Keys: {debug_info['salesforce_keys']}")
    logger.info(f"SAP Keys: {debug_info['sap_keys']}")
    
    return debug_info