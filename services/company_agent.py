"""
Agent multi-sources pour rechercher les entreprises françaises.
Combine API INSEE, base locale et API Pappers avec fallback intelligent.

Intégration Nova - Agent de recherche d'entreprises
Version adaptée pour l'architecture NOVA
"""

import requests
import json
import csv
import re
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
from difflib import SequenceMatcher
import unicodedata
import logging

logger = logging.getLogger(__name__)

class MultiSourceCompanyAgent:
    """
    Agent multi-sources pour rechercher les entreprises françaises.
    Combine API INSEE, base locale et API Pappers comme fallback.
    """
    
    def __init__(self, insee_key: str, pappers_key: str):
        """
        Initialise l'agent avec les clés des APIs.
        
        Args:
            insee_key (str): Clé API INSEE
            pappers_key (str): Clé API Pappers
        """
        self.insee_key = insee_key
        self.pappers_key = pappers_key
        
        # Configuration INSEE
        self.insee_base_url = "https://api.insee.fr/api-sirene/3.11"
        self.insee_headers = {
            'X-INSEE-Api-Key-Integration': insee_key,
            'Accept': 'application/json',
            'User-Agent': 'Nova-CompanyAgent/1.0'
        }
        
        # Configuration Pappers
        self.pappers_base_url = "https://api.pappers.fr/v2"
        
        # Cache pour éviter les appels répétés
        self.cache = {}
        
        # Base de données locale des grandes entreprises françaises
        self.companies_db = {
            "542051180": {
                "siren": "542051180",
                "names": ["TOTALENERGIES SE", "TOTAL SE", "TOTAL SA", "TOTALENERGIES", "TOTAL"],
                "activity": "70.10Z",
                "legal_form": "5800"
            },
            "552120222": {
                "siren": "552120222", 
                "names": ["SOCIETE GENERALE", "SOGEGEN", "SG", "SOCIETE GENERALE SA"],
                "activity": "64.19Z",
                "legal_form": "5599"
            },
            "542107651": {
                "siren": "542107651",
                "names": ["SNCF CONNECT", "SNCF", "SOCIETE NATIONALE CHEMINS DE FER"],
                "activity": "4910Z",
                "legal_form": "7389"
            },
            "775665019": {
                "siren": "775665019",
                "names": ["ORANGE", "FRANCE TELECOM", "ORANGE SA"],
                "activity": "6110Z", 
                "legal_form": "5599"
            },
            "552120222": {
                "siren": "552120222",
                "names": ["CARREFOUR", "CARREFOUR SA", "CARREFOUR GROUPE"],
                "activity": "4711D",
                "legal_form": "5599"
            },
            "572015246": {
                "siren": "572015246",
                "names": ["BOUYGUES", "BOUYGUES SA", "GROUPE BOUYGUES"],
                "activity": "70.10Z",
                "legal_form": "5599"
            },
            "775751518": {
                "siren": "775751518",
                "names": ["RENAULT", "RENAULT SA", "GROUPE RENAULT"],
                "activity": "29.10Z",
                "legal_form": "5599"
            },
            "552081317": {
                "siren": "552081317",
                "names": ["PEUGEOT", "PEUGEOT SA", "GROUPE PEUGEOT"],
                "activity": "29.10Z",
                "legal_form": "5599"
            }
        }
        
        # Index de recherche optimisé
        self.search_index = self._build_search_index()
    
    def _build_search_index(self) -> Dict[str, str]:
        """Construit un index de recherche optimisé pour la base locale."""
        index = {}
        
        for siren, company in self.companies_db.items():
            for name in company["names"]:
                normalized = self._normalize_name(name)
                index[normalized] = siren
                
                # Ajout de variantes
                words = normalized.split()
                if len(words) > 1:
                    index[words[0]] = siren
                    for i in range(len(words)):
                        for j in range(i+1, len(words)+1):
                            variant = " ".join(words[i:j])
                            if len(variant) > 2:
                                index[variant] = siren
        
        return index
    
    def _normalize_name(self, name: str) -> str:
        """Normalise un nom d'entreprise pour la recherche."""
        # Supprimer les accents
        name = unicodedata.normalize('NFD', name)
        name = ''.join(c for c in name if unicodedata.category(c) != 'Mn')
        
        # Majuscules et nettoyage
        name = name.upper().strip()
        name = re.sub(r'[^A-Z0-9\s]', ' ', name)
        name = re.sub(r'\s+', ' ', name)
        
        return name
    
    def validate_siren(self, siren: str) -> bool:
        """
        Valide un numéro SIREN avec l'algorithme de Luhn.
        
        Args:
            siren (str): Numéro SIREN à valider
            
        Returns:
            bool: True si valide, False sinon
        """
        clean_siren = re.sub(r'[^0-9]', '', siren)
        
        if len(clean_siren) != 9:
            return False
        
        try:
            total = 0
            for i, digit in enumerate(clean_siren):
                n = int(digit)
                if i % 2 == 1:
                    n *= 2
                    if n > 9:
                        n = n // 10 + n % 10
                total += n
            
            return total % 10 == 0
        except ValueError:
            return False
    
    def search_by_siren(self, siren: str) -> Optional[Dict[str, Any]]:
        """
        Recherche une entreprise par SIREN via l'API INSEE.
        
        Args:
            siren (str): Numéro SIREN
            
        Returns:
            Optional[Dict[str, Any]]: Informations de l'entreprise ou None
        """
        clean_siren = re.sub(r'[^0-9]', '', siren)
        
        if not self.validate_siren(clean_siren):
            return None
        
        # Vérifier le cache
        cache_key = f"insee_siren_{clean_siren}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        url = f"{self.insee_base_url}/siren/{clean_siren}"
        
        try:
            response = requests.get(url, headers=self.insee_headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                formatted_data = self._format_insee_data(data)
                self.cache[cache_key] = formatted_data
                return formatted_data
            else:
                logger.warning(f"Erreur API INSEE pour SIREN {clean_siren}: {response.status_code}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Erreur API INSEE: {e}")
            return None
    
    def search_local_by_name(self, name: str) -> List[Dict[str, Any]]:
        """
        Recherche dans la base de données locale.
        
        Args:
            name (str): Nom de l'entreprise
            
        Returns:
            List[Dict[str, Any]]: Liste des entreprises trouvées
        """
        results = []
        normalized_query = self._normalize_name(name)
        
        # Recherche exacte dans l'index
        if normalized_query in self.search_index:
            siren = self.search_index[normalized_query]
            company = self.search_by_siren(siren)
            if company:
                company['source'] = 'local'
                results.append(company)
        
        # Recherche par inclusion
        for indexed_name, siren in self.search_index.items():
            if (normalized_query in indexed_name or 
                indexed_name in normalized_query):
                company = self.search_by_siren(siren)
                if company and company not in results:
                    company['source'] = 'local'
                    results.append(company)
        
        return results
    
    def search_pappers_by_name(self, name: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Recherche dans l'API Pappers par nom d'entreprise.
        
        Args:
            name (str): Nom de l'entreprise
            max_results (int): Nombre maximum de résultats
            
        Returns:
            List[Dict[str, Any]]: Liste des entreprises trouvées
        """
        # Vérifier le cache
        cache_key = f"pappers_name_{name.lower()}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        url = f"{self.pappers_base_url}/recherche"
        params = {
            'api_token': self.pappers_key,
            'q': name,
            'longueur': min(max_results, 20),
            'formatage': 1
        }
        
        try:
            response = requests.get(url, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                results = []
                
                if 'resultats' in data:
                    for entreprise in data['resultats']:
                        formatted_data = self._format_pappers_data(entreprise)
                        if formatted_data:
                            formatted_data['source'] = 'pappers'
                            results.append(formatted_data)
                
                # Enrichir avec les données INSEE si possible
                enriched_results = []
                for company in results:
                    if company.get('siren'):
                        insee_data = self.search_by_siren(company['siren'])
                        if insee_data:
                            enriched_company = self._merge_company_data(company, insee_data)
                            enriched_company['source'] = 'pappers+insee'
                            enriched_results.append(enriched_company)
                        else:
                            enriched_results.append(company)
                    else:
                        enriched_results.append(company)
                
                self.cache[cache_key] = enriched_results
                return enriched_results
            
            elif response.status_code == 429:
                logger.warning("Limite de taux Pappers atteinte")
                time.sleep(2)
                return []
            else:
                logger.error(f"Erreur API Pappers: {response.status_code}")
                return []
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Erreur Pappers: {e}")
            return []
    
    def search_by_name(self, name: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Recherche par nom avec fallback intelligent.
        
        Workflow:
        1. Recherche dans la base locale
        2. Si pas de résultats, recherche dans Pappers
        3. Enrichissement avec INSEE si SIREN disponible
        
        Args:
            name (str): Nom de l'entreprise
            max_results (int): Nombre maximum de résultats
            
        Returns:
            List[Dict[str, Any]]: Liste des entreprises trouvées
        """
        # 1. Recherche locale d'abord
        local_results = self.search_local_by_name(name)
        
        if local_results:
            return local_results[:max_results]
        
        # 2. Fallback vers Pappers
        pappers_results = self.search_pappers_by_name(name, max_results)
        
        return pappers_results
    
    def search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Recherche universelle (SIREN ou nom).
        
        Args:
            query (str): SIREN ou nom d'entreprise
            max_results (int): Nombre maximum de résultats
            
        Returns:
            List[Dict[str, Any]]: Liste des entreprises trouvées
        """
        # Test si c'est un SIREN
        if re.match(r'^\d{9}$', re.sub(r'[^0-9]', '', query)):
            company = self.search_by_siren(query)
            return [company] if company else []
        else:
            return self.search_by_name(query, max_results)
    
    def _format_insee_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Formate les données INSEE."""
        if 'uniteLegale' not in data:
            return {}
        
        unite = data['uniteLegale']
        current_info = {}
        
        if 'periodesUniteLegale' in unite and unite['periodesUniteLegale']:
            current_period = unite['periodesUniteLegale'][0]
            current_info = {
                'denomination': current_period.get('denominationUniteLegale', 'N/A'),
                'activite_principale': current_period.get('activitePrincipaleUniteLegale', 'N/A'),
                'forme_juridique': current_period.get('categorieJuridiqueUniteLegale', 'N/A'),
                'etat_administratif': current_period.get('etatAdministratifUniteLegale', 'N/A')
            }
        
        return {
            'siren': unite.get('siren', ''),
            'denomination': current_info.get('denomination', 'N/A'),
            'activite_principale': current_info.get('activite_principale', 'N/A'),
            'forme_juridique': current_info.get('forme_juridique', 'N/A'),
            'etat_administratif': 'Actif' if current_info.get('etat_administratif') == 'A' else 'Inactif',
            'date_creation': unite.get('dateCreationUniteLegale', 'N/A'),
            'tranche_effectifs': unite.get('trancheEffectifsUniteLegale', 'N/A'),
            'categorie_entreprise': unite.get('categorieEntreprise', 'N/A'),
            'source': 'insee'
        }
    
    def _format_pappers_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Formate les données Pappers."""
        return {
            'siren': data.get('siren', ''),
            'denomination': data.get('nom_entreprise', 'N/A'),
            'activite_principale': data.get('code_ape', 'N/A'),
            'forme_juridique': data.get('forme_juridique', 'N/A'),
            'etat_administratif': 'Actif' if data.get('entreprise_cessee', False) == False else 'Inactif',
            'date_creation': data.get('date_creation', 'N/A'),
            'adresse': data.get('adresse', 'N/A'),
            'ville': data.get('ville', 'N/A'),
            'code_postal': data.get('code_postal', 'N/A'),
            'dirigeants': data.get('dirigeants', []),
            'source': 'pappers'
        }
    
    def _merge_company_data(self, pappers_data: Dict[str, Any], insee_data: Dict[str, Any]) -> Dict[str, Any]:
        """Fusionne les données Pappers et INSEE."""
        merged = pappers_data.copy()
        
        # Privilégier les données INSEE pour certains champs
        if insee_data.get('denomination') != 'N/A':
            merged['denomination_insee'] = insee_data['denomination']
        
        if insee_data.get('activite_principale') != 'N/A':
            merged['activite_principale_insee'] = insee_data['activite_principale']
        
        if insee_data.get('forme_juridique') != 'N/A':
            merged['forme_juridique_insee'] = insee_data['forme_juridique']
        
        merged['etat_administratif_insee'] = insee_data.get('etat_administratif', 'N/A')
        merged['tranche_effectifs'] = insee_data.get('tranche_effectifs', 'N/A')
        merged['categorie_entreprise'] = insee_data.get('categorie_entreprise', 'N/A')
        
        return merged
    
    def get_suggestions(self, partial_name: str, max_suggestions: int = 5) -> List[str]:
        """
        Obtient des suggestions de noms d'entreprises.
        
        Args:
            partial_name (str): Nom partiel
            max_suggestions (int): Nombre maximum de suggestions
            
        Returns:
            List[str]: Liste des suggestions
        """
        normalized = self._normalize_name(partial_name)
        suggestions = []
        
        for indexed_name in self.search_index.keys():
            if normalized in indexed_name:
                suggestions.append(indexed_name)
        
        return suggestions[:max_suggestions]
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques du cache."""
        return {
            'total_entries': len(self.cache),
            'insee_entries': len([k for k in self.cache.keys() if k.startswith('insee_')]),
            'pappers_entries': len([k for k in self.cache.keys() if k.startswith('pappers_')]),
            'local_companies': len(self.companies_db),
            'search_index_size': len(self.search_index)
        }
    
    def clear_cache(self):
        """Vide le cache."""
        self.cache.clear()
    
    def export_to_csv(self, companies: List[Dict[str, Any]], filename: str = None) -> str:
        """Export CSV avec toutes les données disponibles."""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"companies_export_{timestamp}.csv"
        
        if not companies:
            return filename
        
        # Récupère toutes les clés possibles
        all_keys = set()
        for company in companies:
            all_keys.update(company.keys())
        
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=sorted(all_keys))
            writer.writeheader()
            writer.writerows(companies)
        
        return filename
    
    def export_to_json(self, companies: List[Dict[str, Any]], filename: str = None) -> str:
        """Export JSON avec structure complète."""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"companies_export_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as jsonfile:
            json.dump(companies, jsonfile, indent=2, ensure_ascii=False)
        
        return filename


# Classe d'exception personnalisée pour Nova
class NovaCompanyAgentException(Exception):
    """Exception personnalisée pour l'agent de recherche d'entreprises Nova."""
    pass


# Factory pour instancier l'agent avec la configuration Nova
class NovaCompanyAgentFactory:
    """Factory pour créer et configurer l'agent de recherche d'entreprises Nova."""
    
    @staticmethod
    def create_agent(config: Dict[str, str]) -> MultiSourceCompanyAgent:
        """
        Crée un agent avec la configuration Nova.
        
        Args:
            config (Dict[str, str]): Configuration avec les clés API
            
        Returns:
            MultiSourceCompanyAgent: Agent configuré
            
        Raises:
            NovaCompanyAgentException: Si la configuration est invalide
        """
        required_keys = ['insee_key', 'pappers_key']
        
        for key in required_keys:
            if key not in config:
                raise NovaCompanyAgentException(f"Clé manquante: {key}")
        
        return MultiSourceCompanyAgent(
            insee_key=config['insee_key'],
            pappers_key=config['pappers_key']
        )