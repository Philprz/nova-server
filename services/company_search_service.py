"""
Service d'intégration de l'agent de recherche d'entreprises dans NOVA
Adapte l'agent multi-sources pour l'architecture NOVA existante
"""

import os
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

# Import de l'agent de recherche d'entreprises
from .company_agent import MultiSourceCompanyAgent, NovaCompanyAgentFactory

logger = logging.getLogger(__name__)

class CompanySearchService:
    """
    Service d'intégration de l'agent de recherche d'entreprises dans NOVA
    """
    
    def __init__(self):
        """Initialise le service avec la configuration NOVA"""
        self.agent = None
        self._initialize_agent()
    
    def _initialize_agent(self):
        """Initialise l'agent avec la configuration NOVA"""
        try:
            # Configuration depuis les variables d'environnement
            config = {
                'insee_key': os.getenv('INSEE_API_KEY'),
                'pappers_key': os.getenv('PAPPERS_API_KEY', '29fbe59dd017f52bcb7bb0532d72935f3cedfa6b96123170')
            }
            
            # Créer l'agent via la factory
            self.agent = NovaCompanyAgentFactory.create_agent(config)
            logger.info("Agent de recherche d'entreprises initialisé avec succès")
            
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation de l'agent: {e}")
            # Fallback vers un agent avec des clés par défaut
            self._initialize_fallback_agent()
    
    def _initialize_fallback_agent(self):
        """Initialise un agent avec des clés par défaut en cas d'échec"""
        try:
            fallback_config = {
                'insee_key': 'c83c88f1-ca96-4272-bc88-f1ca96827240',
                'pappers_key': '29fbe59dd017f52bcb7bb0532d72935f3cedfa6b96123170'
            }
            
            self.agent = NovaCompanyAgentFactory.create_agent(fallback_config)
            logger.warning("Agent initialisé avec configuration fallback")
            
        except Exception as e:
            logger.error(f"Erreur critique lors de l'initialisation fallback: {e}")
            self.agent = None
    
    async def search_company(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        """
        Recherche une entreprise (interface asynchrone pour compatibilité NOVA)
        
        Args:
            query: Nom de l'entreprise ou SIREN
            max_results: Nombre maximum de résultats
            
        Returns:
            Résultat de la recherche formaté pour NOVA
        """
        if not self.agent:
            return {
                'success': False,
                'error': 'Agent de recherche non disponible',
                'companies': []
            }
        
        try:
            # Recherche synchrone de l'agent
            companies = self.agent.search(query, max_results)
            
            # Formatage pour NOVA
            return {
                'success': True,
                'query': query,
                'companies_found': len(companies),
                'companies': companies,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Erreur lors de la recherche: {e}")
            return {
                'success': False,
                'error': str(e),
                'companies': []
            }
    
    async def validate_siren(self, siren: str) -> Dict[str, Any]:
        """
        Valide un SIREN (interface asynchrone)
        
        Args:
            siren: Numéro SIREN à valider
            
        Returns:
            Résultat de validation
        """
        if not self.agent:
            return {'valid': False, 'error': 'Agent non disponible'}
        
        try:
            is_valid = self.agent.validate_siren(siren)
            return {
                'valid': is_valid,
                'siren': siren,
                'formatted_siren': siren.replace(' ', '').replace('-', '')
            }
            
        except Exception as e:
            logger.error(f"Erreur lors de la validation SIREN: {e}")
            return {'valid': False, 'error': str(e)}
    
    async def get_company_by_siren(self, siren: str) -> Dict[str, Any]:
        """
        Récupère une entreprise par SIREN
        
        Args:
            siren: Numéro SIREN
            
        Returns:
            Informations de l'entreprise
        """
        if not self.agent:
            return {
                'success': False,
                'error': 'Agent non disponible'
            }
        
        try:
            company = self.agent.search_by_siren(siren)
            
            if company:
                return {
                    'success': True,
                    'company': company,
                    'source': company.get('source', 'unknown')
                }
            else:
                return {
                    'success': False,
                    'error': 'Entreprise non trouvée'
                }
                
        except Exception as e:
            logger.error(f"Erreur lors de la récupération par SIREN: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def get_suggestions(self, partial_name: str, max_suggestions: int = 5) -> List[str]:
        """
        Obtient des suggestions de noms d'entreprises
        
        Args:
            partial_name: Nom partiel
            max_suggestions: Nombre maximum de suggestions
            
        Returns:
            Liste des suggestions
        """
        if not self.agent:
            return []
        
        try:
            return self.agent.get_suggestions(partial_name, max_suggestions)
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des suggestions: {e}")
            return []
    
    async def enrich_client_data(self, client_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enrichit les données client avec les informations de l'agent
        
        Args:
            client_data: Données client existantes
            
        Returns:
            Données enrichies
        """
        if not self.agent or not client_data:
            return client_data
        
        try:
            # Recherche par nom d'entreprise
            company_name = client_data.get('company_name') or client_data.get('name')
            if not company_name:
                return client_data
            
            # Recherche de l'entreprise
            search_result = await self.search_company(company_name, max_results=1)
            
            if search_result['success'] and search_result['companies']:
                company_info = search_result['companies'][0]
                
                # Enrichissement des données
                enriched_data = client_data.copy()
                
                # Ajouter les informations trouvées
                enriched_data['enriched_data'] = {
                    'siren': company_info.get('siren'),
                    'denomination_officielle': company_info.get('denomination'),
                    'activite_principale': company_info.get('activite_principale'),
                    'forme_juridique': company_info.get('forme_juridique'),
                    'etat_administratif': company_info.get('etat_administratif'),
                    'source': company_info.get('source'),
                    'enriched_at': datetime.now().isoformat()
                }
                
                # Mise à jour des champs si vides
                if not enriched_data.get('industry') and company_info.get('activite_principale'):
                    enriched_data['industry'] = company_info.get('activite_principale')
                
                if not enriched_data.get('legal_form') and company_info.get('forme_juridique'):
                    enriched_data['legal_form'] = company_info.get('forme_juridique')
                
                return enriched_data
            
            return client_data
            
        except Exception as e:
            logger.error(f"Erreur lors de l'enrichissement: {e}")
            return client_data
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """
        Retourne les statistiques du cache de l'agent
        
        Returns:
            Statistiques du cache
        """
        if not self.agent:
            return {'error': 'Agent non disponible'}
        
        try:
            return self.agent.get_cache_stats()
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des stats: {e}")
            return {'error': str(e)}
    
    async def export_search_results(self, results: List[Dict[str, Any]], 
                                   format: str = 'json') -> str:
        """
        Exporte les résultats de recherche
        
        Args:
            results: Résultats à exporter
            format: Format d'export ('json' ou 'csv')
            
        Returns:
            Nom du fichier exporté
        """
        if not self.agent:
            raise ValueError("Agent non disponible")
        
        try:
            if format.lower() == 'csv':
                return self.agent.export_to_csv(results)
            else:
                return self.agent.export_to_json(results)
                
        except Exception as e:
            logger.error(f"Erreur lors de l'export: {e}")
            raise
    
    def clear_cache(self):
        """Vide le cache de l'agent"""
        if self.agent:
            self.agent.clear_cache()
            logger.info("Cache de l'agent vidé")


# Instance singleton pour l'application
company_search_service = CompanySearchService()