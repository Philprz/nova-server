"""
Workflow de devis NOVA enrichi avec l'agent de recherche d'entreprises
Extension du DevisWorkflow existant avec enrichissement automatique
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

# Import des services NOVA existants
from .devis_workflow import DevisWorkflow
from services.company_search_service import company_search_service
from services.suggestion_engine_enhanced import enhanced_suggestion_engine

logger = logging.getLogger(__name__)

class EnhancedDevisWorkflow(DevisWorkflow):
    """
    Workflow de devis enrichi avec l'agent de recherche d'entreprises
    """
    
    def __init__(self):
        super().__init__()
        self.company_enrichment_enabled = True
        self.auto_siren_validation = True
    
    async def process_devis_request_enhanced(self, prompt: str, draft_mode: bool = False) -> Dict[str, Any]:
        """
        🚀 Traitement enrichi d'une demande de devis
        
        Workflow enrichi:
        1. Extraction LLM classique
        2. Enrichissement client avec agent de recherche
        3. Validation SIREN automatique
        4. Suggestions intelligentes
        5. Création devis avec données enrichies
        
        Args:
            prompt: Prompt utilisateur
            draft_mode: Mode brouillon
            
        Returns:
            Résultat du traitement enrichi
        """
        try:
            # 1. Extraction LLM classique
            extraction_result = await self.llm_extractor.extract_devis_info(prompt)
            
            if not extraction_result or 'error' in extraction_result:
                return {
                    'success': False,
                    'error': 'Erreur lors de l\'extraction LLM',
                    'details': extraction_result
                }
            
            # 2. Enrichissement client avec agent de recherche
            client_name = extraction_result.get('client_name')
            enriched_client_data = None
            
            if client_name and self.company_enrichment_enabled:
                logger.info(f"🔍 Enrichissement client: {client_name}")
                
                # Recherche d'entreprise
                search_result = await company_search_service.search_company(client_name, max_results=3)
                
                if search_result['success'] and search_result['companies']:
                    best_match = search_result['companies'][0]
                    
                    # Création des données client enrichies
                    enriched_client_data = {
                        'company_name': best_match['denomination'],
                        'siren': best_match.get('siren'),
                        'industry': best_match.get('activite_principale'),
                        'legal_form': best_match.get('forme_juridique'),
                        'status': best_match.get('etat_administratif'),
                        'source': best_match.get('source'),
                        'enriched_at': datetime.now().isoformat(),
                        'enrichment_confidence': self._calculate_enrichment_confidence(client_name, best_match)
                    }
                    
                    # Validation SIREN automatique
                    if self.auto_siren_validation and enriched_client_data.get('siren'):
                        siren_validation = await company_search_service.validate_siren(enriched_client_data['siren'])
                        enriched_client_data['siren_valid'] = siren_validation['valid']
                        
                        if not siren_validation['valid']:
                            logger.warning(f"⚠️ SIREN invalide détecté: {enriched_client_data['siren']}")
                    
                    logger.info(f"✅ Client enrichi: {enriched_client_data['company_name']} (SIREN: {enriched_client_data.get('siren')})")
                
                else:
                    logger.info(f"❌ Aucune entreprise trouvée pour: {client_name}")
                    
                    # Suggestions d'entreprises similaires
                    suggestions = await company_search_service.get_suggestions(client_name)
                    enriched_client_data = {
                        'company_name': client_name,
                        'enriched_at': datetime.now().isoformat(),
                        'enrichment_confidence': 'low',
                        'suggestions': suggestions
                    }
            
            # 3. Traitement avec données enrichies
            if enriched_client_data:
                extraction_result['client_data'] = enriched_client_data
                extraction_result['enriched_workflow'] = True
            
            # 4. Traitement classique du workflow
            if draft_mode:
                return await self.process_draft_mode_enhanced(extraction_result)
            else:
                return await self.process_full_workflow_enhanced(extraction_result)
            
        except Exception as e:
            logger.error(f"Erreur workflow enrichi: {e}")
            return {
                'success': False,
                'error': str(e),
                'fallback_to_classic': True
            }
    
    async def process_draft_mode_enhanced(self, extraction_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Mode brouillon enrichi avec suggestions intelligentes
        """
        try:
            # Génération des suggestions enrichies
            client_data = extraction_result.get('client_data', {})
            suggestions = await enhanced_suggestion_engine.enrich_client_suggestions(client_data)
            
            # Actions intelligentes
            context = {
                'client_name': client_data.get('company_name'),
                'siren': client_data.get('siren'),
                'client_data': client_data,
                'client_enriched': extraction_result.get('enriched_workflow', False)
            }
            
            intelligent_actions = await enhanced_suggestion_engine.get_intelligent_actions(context)
            
            # Résultat du mode brouillon enrichi
            return {
                'success': True,
                'mode': 'draft_enhanced',
                'extraction_result': extraction_result,
                'client_enrichment': {
                    'applied': extraction_result.get('enriched_workflow', False),
                    'confidence': client_data.get('enrichment_confidence'),
                    'source': client_data.get('source')
                },
                'suggestions': suggestions,
                'intelligent_actions': intelligent_actions,
                'next_steps': self._generate_next_steps(extraction_result, suggestions)
            }
            
        except Exception as e:
            logger.error(f"Erreur mode brouillon enrichi: {e}")
            # Fallback vers mode brouillon classique
            return await self.process_draft_mode(extraction_result)
    
    async def process_full_workflow_enhanced(self, extraction_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Workflow complet enrichi avec validation automatique
        """
        try:
            # Validation des données client enrichies
            client_data = extraction_result.get('client_data', {})
            
            if client_data.get('siren'):
                # Validation SIREN si pas déjà fait
                if 'siren_valid' not in client_data:
                    siren_validation = await company_search_service.validate_siren(client_data['siren'])
                    client_data['siren_valid'] = siren_validation['valid']
                
                # Arrêt si SIREN invalide
                if not client_data.get('siren_valid'):
                    return {
                        'success': False,
                        'error': 'SIREN invalide',
                        'client_data': client_data,
                        'suggestions': await company_search_service.get_suggestions(client_data.get('company_name', '')),
                        'action_required': 'validate_siren'
                    }
            
            # Traitement classique avec données enrichies
            workflow_result = await self.process_full_workflow(extraction_result)
            
            # Enrichissement du résultat
            if workflow_result.get('success'):
                workflow_result['client_enrichment'] = {
                    'applied': True,
                    'confidence': client_data.get('enrichment_confidence'),
                    'source': client_data.get('source'),
                    'siren': client_data.get('siren'),
                    'siren_valid': client_data.get('siren_valid')
                }
            
            return workflow_result
            
        except Exception as e:
            logger.error(f"Erreur workflow complet enrichi: {e}")
            # Fallback vers workflow classique
            return await self.process_full_workflow(extraction_result)
    
    def _calculate_enrichment_confidence(self, original_name: str, company_match: Dict[str, Any]) -> str:
        """
        Calcule le niveau de confiance de l'enrichissement
        """
        original_norm = original_name.upper().strip()
        match_name = company_match.get('denomination', '').upper().strip()
        
        # Correspondance exacte
        if original_norm == match_name:
            return 'high'
        
        # Correspondance partielle forte
        if original_norm in match_name or match_name in original_norm:
            if len(original_norm) > len(match_name) * 0.7:
                return 'high'
            else:
                return 'medium'
        
        # Source fiable
        if company_match.get('source') == 'insee':
            return 'medium'
        
        return 'low'
    
    def _generate_next_steps(self, extraction_result: Dict[str, Any], suggestions: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Génère les prochaines étapes recommandées
        """
        next_steps = []
        
        client_data = extraction_result.get('client_data', {})
        
        # Étape 1: Validation des données client
        if client_data.get('suggestions'):
            next_steps.append({
                'step': 1,
                'title': 'Vérifier le nom de l\'entreprise',
                'description': 'Plusieurs entreprises trouvées, vérifier la bonne correspondance',
                'type': 'validation',
                'data': client_data.get('suggestions')
            })
        
        # Étape 2: Enrichissement des données
        if suggestions.get('data_improvements'):
            next_steps.append({
                'step': 2,
                'title': 'Compléter les données client',
                'description': 'Informations supplémentaires disponibles',
                'type': 'enrichment',
                'data': suggestions['data_improvements']
            })
        
        # Étape 3: Validation SIREN
        if client_data.get('siren') and not client_data.get('siren_valid'):
            next_steps.append({
                'step': 3,
                'title': 'Valider le SIREN',
                'description': 'Vérifier la validité du numéro SIREN',
                'type': 'validation',
                'data': {'siren': client_data.get('siren')}
            })
        
        # Étape 4: Création du devis
        next_steps.append({
            'step': len(next_steps) + 1,
            'title': 'Créer le devis',
            'description': 'Procéder à la création du devis avec les données validées',
            'type': 'creation',
            'data': {}
        })
        
        return next_steps
    
    async def validate_and_create_client_enhanced(self, client_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        🔍 Validation et création client enrichie
        
        Args:
            client_data: Données client à valider et créer
            
        Returns:
            Résultat de la validation et création
        """
        try:
            # Enrichissement préalable si pas déjà fait
            if not client_data.get('enriched_at'):
                enriched_data = await company_search_service.enrich_client_data(client_data)
                client_data.update(enriched_data)
            
            # Validation SIREN si présent
            if client_data.get('siren'):
                siren_validation = await company_search_service.validate_siren(client_data['siren'])
                
                if not siren_validation['valid']:
                    return {
                        'success': False,
                        'error': 'SIREN invalide',
                        'error_type': 'validation_error',
                        'client_data': client_data,
                        'suggestions': await company_search_service.get_suggestions(client_data.get('company_name', ''))
                    }
            
            # Création client avec données enrichies
            creation_result = await self.create_client_in_systems(client_data)
            
            if creation_result.get('success'):
                creation_result['client_enrichment'] = {
                    'applied': True,
                    'siren': client_data.get('siren'),
                    'source': client_data.get('source'),
                    'enriched_at': client_data.get('enriched_at')
                }
            
            return creation_result
            
        except Exception as e:
            logger.error(f"Erreur validation et création client enrichie: {e}")
            # Fallback vers création classique
            return await self.create_client_in_systems(client_data)
    
    async def get_client_validation_status(self, client_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        🔍 Statut de validation enrichi du client
        
        Args:
            client_data: Données client à valider
            
        Returns:
            Statut de validation détaillé
        """
        validation_status = {
            'overall_status': 'pending',
            'checks': [],
            'recommendations': [],
            'confidence_score': 0.0
        }
        
        try:
            # Validation du nom d'entreprise
            if client_data.get('company_name'):
                search_result = await company_search_service.search_company(
                    client_data['company_name'], 
                    max_results=1
                )
                
                if search_result['success'] and search_result['companies']:
                    validation_status['checks'].append({
                        'type': 'company_name',
                        'status': 'success',
                        'message': 'Entreprise trouvée dans les bases officielles',
                        'confidence': 0.9
                    })
                    validation_status['confidence_score'] += 0.3
                else:
                    validation_status['checks'].append({
                        'type': 'company_name',
                        'status': 'warning',
                        'message': 'Entreprise non trouvée dans les bases officielles',
                        'confidence': 0.3
                    })
                    validation_status['confidence_score'] += 0.1
            
            # Validation SIREN
            if client_data.get('siren'):
                siren_validation = await company_search_service.validate_siren(client_data['siren'])
                
                if siren_validation['valid']:
                    validation_status['checks'].append({
                        'type': 'siren',
                        'status': 'success',
                        'message': 'SIREN valide selon l\'algorithme de Luhn',
                        'confidence': 0.95
                    })
                    validation_status['confidence_score'] += 0.4
                else:
                    validation_status['checks'].append({
                        'type': 'siren',
                        'status': 'error',
                        'message': 'SIREN invalide',
                        'confidence': 0.0
                    })
                    validation_status['overall_status'] = 'error'
            
            # Cohérence des données
            if client_data.get('siren') and client_data.get('company_name'):
                company_info = await company_search_service.get_company_by_siren(client_data['siren'])
                
                if company_info['success']:
                    official_name = company_info['company']['denomination']
                    provided_name = client_data['company_name']
                    
                    # Comparaison des noms
                    if official_name.upper() == provided_name.upper():
                        validation_status['checks'].append({
                            'type': 'name_coherence',
                            'status': 'success',
                            'message': 'Nom cohérent avec les données officielles',
                            'confidence': 1.0
                        })
                        validation_status['confidence_score'] += 0.3
                    else:
                        validation_status['checks'].append({
                            'type': 'name_coherence',
                            'status': 'warning',
                            'message': f'Nom officiel: {official_name}',
                            'confidence': 0.7
                        })
                        validation_status['confidence_score'] += 0.2
                        
                        validation_status['recommendations'].append({
                            'type': 'name_correction',
                            'message': f'Utiliser le nom officiel: {official_name}',
                            'priority': 'medium'
                        })
            
            # Détermination du statut global
            if validation_status['overall_status'] != 'error':
                if validation_status['confidence_score'] >= 0.8:
                    validation_status['overall_status'] = 'validated'
                elif validation_status['confidence_score'] >= 0.5:
                    validation_status['overall_status'] = 'warning'
                else:
                    validation_status['overall_status'] = 'pending'
            
            return validation_status
            
        except Exception as e:
            logger.error(f"Erreur statut validation: {e}")
            validation_status['overall_status'] = 'error'
            validation_status['checks'].append({
                'type': 'system_error',
                'status': 'error',
                'message': f'Erreur système: {str(e)}',
                'confidence': 0.0
            })
            return validation_status


# Instance singleton pour l'application
enhanced_devis_workflow = EnhancedDevisWorkflow()
