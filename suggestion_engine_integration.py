"""
Moteur de suggestions NOVA enrichi avec l'agent de recherche d'entreprises
Extension du SuggestionEngine existant avec recherche d'entreprises
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum

# Import des services NOVA existants
from .suggestion_engine import SuggestionEngine, SuggestionType, ConfidenceLevel
from .company_search_service import company_search_service

logger = logging.getLogger(__name__)

class CompanySuggestionType(Enum):
    """Types de suggestions spécifiques aux entreprises"""
    EXACT_MATCH = "exact_match"
    SIREN_MATCH = "siren_match"
    FUZZY_MATCH = "fuzzy_match"
    LEGAL_FORM_SUGGESTION = "legal_form_suggestion"
    INDUSTRY_SUGGESTION = "industry_suggestion"
    SIMILAR_COMPANY = "similar_company"

@dataclass
class CompanySuggestion:
    """Suggestion d'entreprise enrichie"""
    suggestion_type: CompanySuggestionType
    confidence: ConfidenceLevel
    company_name: str
    siren: Optional[str] = None
    legal_form: Optional[str] = None
    industry: Optional[str] = None
    status: Optional[str] = None
    source: Optional[str] = None
    score: float = 0.0
    reason: str = ""
    enrichment_data: Dict[str, Any] = None

class EnhancedSuggestionEngine(SuggestionEngine):
    """
    Moteur de suggestions NOVA enrichi avec l'agent de recherche d'entreprises
    """
    
    def __init__(self):
        super().__init__()
        self.company_search_enabled = True
    
    async def suggest_companies(self, query: str, max_suggestions: int = 5) -> List[CompanySuggestion]:
        """
        🔍 Suggestions d'entreprises basées sur la recherche
        
        Args:
            query: Nom partiel ou complet de l'entreprise
            max_suggestions: Nombre maximum de suggestions
            
        Returns:
            Liste des suggestions d'entreprises
        """
        suggestions = []
        
        if not self.company_search_enabled:
            return suggestions
        
        try:
            # 1. Recherche exacte
            search_result = await company_search_service.search_company(query, max_results=max_suggestions)
            
            if search_result['success'] and search_result['companies']:
                for i, company in enumerate(search_result['companies']):
                    # Calcul du score de confiance
                    confidence = self._calculate_company_confidence(query, company)
                    
                    # Détermination du type de suggestion
                    suggestion_type = self._determine_suggestion_type(query, company)
                    
                    suggestion = CompanySuggestion(
                        suggestion_type=suggestion_type,
                        confidence=confidence,
                        company_name=company['denomination'],
                        siren=company.get('siren'),
                        legal_form=company.get('forme_juridique'),
                        industry=company.get('activite_principale'),
                        status=company.get('etat_administratif'),
                        source=company.get('source'),
                        score=1.0 - (i * 0.1),  # Score décroissant
                        reason=f"Correspondance trouvée via {company.get('source', 'recherche')}",
                        enrichment_data=company
                    )
                    
                    suggestions.append(suggestion)
            
            # 2. Suggestions basées sur les noms partiels
            if len(suggestions) < max_suggestions:
                partial_suggestions = await company_search_service.get_suggestions(query)
                
                for suggestion_name in partial_suggestions:
                    if len(suggestions) >= max_suggestions:
                        break
                    
                    # Éviter les doublons
                    if not any(s.company_name.upper() == suggestion_name.upper() for s in suggestions):
                        suggestion = CompanySuggestion(
                            suggestion_type=CompanySuggestionType.FUZZY_MATCH,
                            confidence=ConfidenceLevel.MEDIUM,
                            company_name=suggestion_name,
                            score=0.7,
                            reason="Correspondance partielle du nom"
                        )
                        suggestions.append(suggestion)
            
            # 3. Tri par score de confiance
            suggestions.sort(key=lambda x: x.score, reverse=True)
            
            return suggestions[:max_suggestions]
            
        except Exception as e:
            logger.error(f"Erreur suggestions entreprises: {e}")
            return []
    
    def _calculate_company_confidence(self, query: str, company: Dict[str, Any]) -> ConfidenceLevel:
        """Calcule le niveau de confiance d'une suggestion d'entreprise"""
        query_norm = query.upper().strip()
        company_name = company.get('denomination', '').upper().strip()
        
        # Correspondance exacte
        if query_norm == company_name:
            return ConfidenceLevel.HIGH
        
        # Correspondance partielle forte
        if query_norm in company_name or company_name in query_norm:
            if len(query_norm) > len(company_name) * 0.7:
                return ConfidenceLevel.HIGH
            else:
                return ConfidenceLevel.MEDIUM
        
        # Correspondance via source fiable
        if company.get('source') == 'insee':
            return ConfidenceLevel.MEDIUM
        
        # Correspondance faible
        return ConfidenceLevel.LOW
    
    def _determine_suggestion_type(self, query: str, company: Dict[str, Any]) -> CompanySuggestionType:
        """Détermine le type de suggestion basé sur la correspondance"""
        query_norm = query.upper().strip()
        company_name = company.get('denomination', '').upper().strip()
        
        # Test si le query est un SIREN
        if query_norm.replace(' ', '').replace('-', '').isdigit():
            return CompanySuggestionType.SIREN_MATCH
        
        # Correspondance exacte
        if query_norm == company_name:
            return CompanySuggestionType.EXACT_MATCH
        
        # Correspondance floue
        return CompanySuggestionType.FUZZY_MATCH
    
    async def enrich_client_suggestions(self, client_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        🔍 Enrichit les suggestions client avec les données d'entreprise
        
        Args:
            client_data: Données client à enrichir
            
        Returns:
            Suggestions enrichies
        """
        suggestions = {
            'company_suggestions': [],
            'data_improvements': [],
            'validation_suggestions': []
        }
        
        try:
            company_name = client_data.get('company_name') or client_data.get('name')
            
            if company_name:
                # Suggestions d'entreprises
                company_suggestions = await self.suggest_companies(company_name)
                suggestions['company_suggestions'] = [
                    {
                        'type': s.suggestion_type.value,
                        'confidence': s.confidence.value,
                        'company_name': s.company_name,
                        'siren': s.siren,
                        'reason': s.reason,
                        'score': s.score
                    } for s in company_suggestions
                ]
                
                # Suggestions d'amélioration des données
                if company_suggestions:
                    best_match = company_suggestions[0]
                    
                    # Suggestion SIREN si manquant
                    if not client_data.get('siren') and best_match.siren:
                        suggestions['data_improvements'].append({
                            'field': 'siren',
                            'suggested_value': best_match.siren,
                            'reason': 'SIREN trouvé via recherche officielle',
                            'confidence': best_match.confidence.value
                        })
                    
                    # Suggestion industrie si manquante
                    if not client_data.get('industry') and best_match.industry:
                        suggestions['data_improvements'].append({
                            'field': 'industry',
                            'suggested_value': best_match.industry,
                            'reason': 'Code activité principal officiel',
                            'confidence': best_match.confidence.value
                        })
                    
                    # Suggestion forme juridique si manquante
                    if not client_data.get('legal_form') and best_match.legal_form:
                        suggestions['data_improvements'].append({
                            'field': 'legal_form',
                            'suggested_value': best_match.legal_form,
                            'reason': 'Forme juridique officielle',
                            'confidence': best_match.confidence.value
                        })
            
            # Validation SIREN si présent
            if client_data.get('siren'):
                siren = client_data['siren']
                validation_result = await company_search_service.validate_siren(siren)
                
                if not validation_result['valid']:
                    suggestions['validation_suggestions'].append({
                        'type': 'error',
                        'field': 'siren',
                        'message': 'SIREN invalide selon l\'algorithme de Luhn',
                        'action': 'verify_siren'
                    })
                else:
                    suggestions['validation_suggestions'].append({
                        'type': 'success',
                        'field': 'siren',
                        'message': 'SIREN valide',
                        'action': 'none'
                    })
            
            return suggestions
            
        except Exception as e:
            logger.error(f"Erreur enrichissement suggestions: {e}")
            return suggestions
    
    async def get_intelligent_actions(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        🎯 Actions intelligentes basées sur les données d'entreprise
        
        Args:
            context: Contexte de l'action (client, devis, etc.)
            
        Returns:
            Liste des actions suggérées
        """
        actions = []
        
        try:
            # Action : Recherche d'entreprise
            if context.get('client_name') and not context.get('client_enriched'):
                actions.append({
                    'type': 'search_company',
                    'title': 'Rechercher les informations de l\'entreprise',
                    'description': 'Enrichir avec les données officielles (SIREN, activité, etc.)',
                    'priority': 'high',
                    'endpoint': '/companies/search',
                    'parameters': {'query': context['client_name']},
                    'icon': '🔍'
                })
            
            # Action : Validation SIREN
            if context.get('siren') and not context.get('siren_validated'):
                actions.append({
                    'type': 'validate_siren',
                    'title': 'Valider le SIREN',
                    'description': 'Vérifier la validité du numéro SIREN',
                    'priority': 'medium',
                    'endpoint': '/companies/validate_siren',
                    'parameters': {'siren': context['siren']},
                    'icon': '✅'
                })
            
            # Action : Enrichissement automatique
            if context.get('client_data') and not context.get('auto_enriched'):
                actions.append({
                    'type': 'auto_enrich',
                    'title': 'Enrichissement automatique',
                    'description': 'Compléter automatiquement les données client',
                    'priority': 'medium',
                    'endpoint': '/enrich_client_with_company_data',
                    'parameters': {'client_data': context['client_data']},
                    'icon': '🚀'
                })
            
            # Action : Suggestions d'entreprises similaires
            if context.get('company_not_found'):
                actions.append({
                    'type': 'suggest_similar',
                    'title': 'Entreprises similaires',
                    'description': 'Proposer des entreprises avec des noms similaires',
                    'priority': 'low',
                    'endpoint': '/companies/suggestions',
                    'parameters': {'partial_name': context.get('partial_name', '')},
                    'icon': '💡'
                })
            
            return actions
            
        except Exception as e:
            logger.error(f"Erreur actions intelligentes: {e}")
            return []
    
    async def generate_company_report(self, companies: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        📊 Génère un rapport d'analyse des entreprises
        
        Args:
            companies: Liste des entreprises à analyser
            
        Returns:
            Rapport d'analyse
        """
        report = {
            'total_companies': len(companies),
            'sources_breakdown': {},
            'legal_forms_breakdown': {},
            'industries_breakdown': {},
            'status_breakdown': {},
            'recommendations': []
        }
        
        try:
            # Analyse des sources
            for company in companies:
                source = company.get('source', 'unknown')
                report['sources_breakdown'][source] = report['sources_breakdown'].get(source, 0) + 1
                
                # Analyse des formes juridiques
                legal_form = company.get('forme_juridique', 'unknown')
                report['legal_forms_breakdown'][legal_form] = report['legal_forms_breakdown'].get(legal_form, 0) + 1
                
                # Analyse des industries
                industry = company.get('activite_principale', 'unknown')
                report['industries_breakdown'][industry] = report['industries_breakdown'].get(industry, 0) + 1
                
                # Analyse des statuts
                status = company.get('etat_administratif', 'unknown')
                report['status_breakdown'][status] = report['status_breakdown'].get(status, 0) + 1
            
            # Recommandations
            if report['total_companies'] > 0:
                # Qualité des données
                insee_count = report['sources_breakdown'].get('insee', 0)
                data_quality = (insee_count / report['total_companies']) * 100
                
                if data_quality > 80:
                    report['recommendations'].append({
                        'type': 'info',
                        'message': f'Excellente qualité des données ({data_quality:.1f}% de sources INSEE)'
                    })
                elif data_quality > 50:
                    report['recommendations'].append({
                        'type': 'warning',
                        'message': f'Qualité des données modérée ({data_quality:.1f}% de sources INSEE)'
                    })
                else:
                    report['recommendations'].append({
                        'type': 'error',
                        'message': f'Qualité des données faible ({data_quality:.1f}% de sources INSEE)'
                    })
                
                # Entreprises inactives
                inactive_count = report['status_breakdown'].get('Inactif', 0)
                if inactive_count > 0:
                    report['recommendations'].append({
                        'type': 'warning',
                        'message': f'{inactive_count} entreprise(s) inactive(s) détectée(s)'
                    })
            
            return report
            
        except Exception as e:
            logger.error(f"Erreur génération rapport: {e}")
            return report


# Instance singleton pour l'application
enhanced_suggestion_engine = EnhancedSuggestionEngine()
