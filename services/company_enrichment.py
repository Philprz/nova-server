# services/company_enrichment.py
import asyncio
import aiohttp
import logging
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class CompanyEnrichmentService:
    def __init__(self):
        self.insee_api_key = os.getenv("INSEE_API_KEY")
        self.pappers_api_key = os.getenv("PAPPERS_API_KEY")
        
    async def enrich_company_data(self, company_name: str) -> Dict[str, Any]:
        """Enrichit les données d'une entreprise via INSEE et Pappers"""
        
        logger.info(f"Enrichissement des données pour: {company_name}")
        
        # Rechercher en parallèle
        tasks = []
        
        if self.insee_api_key:
            tasks.append(self._search_insee(company_name))
        
        if self.pappers_api_key:
            tasks.append(self._search_pappers(company_name))
        
        if not tasks:
            logger.warning("Aucune API configurée pour l'enrichissement")
            return {"success": False, "error": "APIs non configurées"}
        
        # Exécuter les recherches en parallèle
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Combiner les résultats
        enriched_data = {
            "company_name": company_name,
            "search_timestamp": datetime.now().isoformat(),
            "sources": {},
            "consolidated_data": {}
        }
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Erreur enrichissement {i}: {result}")
                continue
                
            if result.get("success"):
                source = result.get("source")
                enriched_data["sources"][source] = result.get("data")
        
        # Consolider les données
        enriched_data["consolidated_data"] = self._consolidate_data(enriched_data["sources"])
        
        return enriched_data
    
    async def _search_insee(self, company_name: str) -> Dict[str, Any]:
        """Recherche via l'API INSEE"""
        try:
            url = "https://api.insee.fr/entreprises/sirene/V3/siret"
            headers = {
                "Authorization": f"Bearer {self.insee_api_key}",
                "Accept": "application/json"
            }
            params = {
                "q": f'denominationUniteLegale:"{company_name}"',
                "nombre": 5
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        establishments = data.get("etablissements", [])
                        if establishments:
                            # Prendre le premier établissement
                            establishment = establishments[0]
                            unit_legal = establishment.get("uniteLegale", {})
                            address = establishment.get("adresseEtablissement", {})
                            
                            return {
                                "success": True,
                                "source": "INSEE",
                                "data": {
                                    "siret": establishment.get("siret"),
                                    "siren": unit_legal.get("siren"),
                                    "company_name": unit_legal.get("denominationUniteLegale"),
                                    "legal_form": unit_legal.get("categorieJuridiqueUniteLegale"),
                                    "address": {
                                        "street": address.get("numeroVoieEtablissement", "") + " " + 
                                                address.get("typeVoieEtablissement", "") + " " + 
                                                address.get("libelleVoieEtablissement", ""),
                                        "postal_code": address.get("codePostalEtablissement"),
                                        "city": address.get("libelleCommuneEtablissement"),
                                        "country": "France"
                                    },
                                    "activity": {
                                        "ape_code": establishment.get("activitePrincipaleEtablissement"),
                                        "ape_label": establishment.get("nomenclatureActivitePrincipaleEtablissement")
                                    }
                                }
                            }
                        else:
                            return {"success": False, "source": "INSEE", "error": "Aucun établissement trouvé"}
                    else:
                        return {"success": False, "source": "INSEE", "error": f"Erreur API: {response.status}"}
                        
        except Exception as e:
            logger.error(f"Erreur recherche INSEE: {e}")
            return {"success": False, "source": "INSEE", "error": str(e)}
    
    async def _search_pappers(self, company_name: str) -> Dict[str, Any]:
        """Recherche via l'API Pappers"""
        try:
            url = "https://api.pappers.fr/v2/entreprise"
            params = {
                "api_token": self.pappers_api_key,
                "q": company_name,
                "longueur": 5
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        results = data.get("resultats", [])
                        if results:
                            # Prendre le premier résultat
                            company = results[0]
                            
                            return {
                                "success": True,
                                "source": "Pappers",
                                "data": {
                                    "siren": company.get("siren"),
                                    "siret": company.get("siret_siege"),
                                    "company_name": company.get("nom_entreprise"),
                                    "legal_form": company.get("forme_juridique"),
                                    "address": {
                                        "street": company.get("adresse_ligne_1"),
                                        "postal_code": company.get("code_postal"),
                                        "city": company.get("ville"),
                                        "country": "France"
                                    },
                                    "activity": {
                                        "ape_code": company.get("code_ape"),
                                        "ape_label": company.get("libelle_ape")
                                    },
                                    "financials": {
                                        "capital": company.get("capital"),
                                        "turnover": company.get("chiffre_affaires")
                                    }
                                }
                            }
                        else:
                            return {"success": False, "source": "Pappers", "error": "Aucune entreprise trouvée"}
                    else:
                        return {"success": False, "source": "Pappers", "error": f"Erreur API: {response.status}"}
                        
        except Exception as e:
            logger.error(f"Erreur recherche Pappers: {e}")
            return {"success": False, "source": "Pappers", "error": str(e)}
    
    def _consolidate_data(self, sources: Dict[str, Any]) -> Dict[str, Any]:
        """Consolide les données de plusieurs sources"""
        consolidated = {}
        
        # Priorité: INSEE > Pappers pour les données officielles
        for source in ["INSEE", "Pappers"]:
            if source in sources:
                data = sources[source]
                
                # Données de base
                if not consolidated.get("company_name") and data.get("company_name"):
                    consolidated["company_name"] = data["company_name"]
                
                if not consolidated.get("siren") and data.get("siren"):
                    consolidated["siren"] = data["siren"]
                
                if not consolidated.get("siret") and data.get("siret"):
                    consolidated["siret"] = data["siret"]
                
                # Adresse
                if not consolidated.get("address") and data.get("address"):
                    consolidated["address"] = data["address"]
                
                # Activité
                if not consolidated.get("activity") and data.get("activity"):
                    consolidated["activity"] = data["activity"]
                
                # Données financières (priorité Pappers)
                if source == "Pappers" and data.get("financials"):
                    consolidated["financials"] = data["financials"]
        
        return consolidated

# Instance globale
company_enrichment_service = CompanyEnrichmentService()