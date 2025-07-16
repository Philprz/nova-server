"""
🤖 Routes pour l'Assistant Intelligent NOVA
==========================================

API conversationnelle qui transforme NOVA en collègue intelligent
capable de comprendre les demandes en langage naturel et proposer
des solutions proactives.
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import logging
from datetime import datetime
import re
import json

# Configuration du router FastAPI
router = APIRouter(tags=["Assistant Intelligent"])

# Import des services NOVA existants
from services.suggestion_engine import SuggestionEngine, SuggestionResult
from services.client_validator import ClientValidator
from services.progress_tracker import ProgressTracker
from workflow.devis_workflow import DevisWorkflow

# Import des routes existantes pour réutiliser la logique
import asyncio

import httpx

async def get_clients_data_async():
    """Récupère les clients - utilise les données réelles de Salesforce"""
    # Pour l'instant, utilisons des données réelles de Salesforce pour tester l'interface
    return {
        'clients': [
            {
                'id': '001gL000008IyXOQA0',
                'name': 'Airbus Industries',
                'city': 'BLAGNAC',
                'country': 'France',
                'state': '',
                'phone': '',
                'type': 'Customer',
                'industry': 'Manufacturing',
                'account_number': 'SFAIRBUSIN2943'
            },
            {
                'id': '001gL000005OYCEQA4',
                'name': 'Burlington Textiles Corp of America',
                'city': 'Burlington',
                'country': 'USA',
                'state': 'NC',
                'phone': '(336) 222-7000',
                'type': 'Customer - Direct',
                'industry': 'Apparel',
                'account_number': 'CD656092'
            },
            {
                'id': '001gL000008JW7eQAG',
                'name': 'Alcatel',
                'city': '',
                'country': '',
                'state': '',
                'phone': '01-27-42-65-01',
                'type': 'Customer',
                'industry': '',
                'account_number': 'C40000'
            },
            {
                'id': '001gL000008JXuwQAG',
                'name': 'Client interface Web',
                'city': '',
                'country': '',
                'state': '',
                'phone': '',
                'type': 'Customer',
                'industry': '',
                'account_number': 'C99998'
            },
            {
                'id': '001gL000008JXV9QAO',
                'name': 'Airbus Industries',
                'city': '',
                'country': '',
                'state': '',
                'phone': '',
                'type': 'Customer',
                'industry': '',
                'account_number': 'CAIRBUSIN1200'
            }
        ]
    }

async def get_products_data_async():
    """Récupère les produits - utilise les données réelles de SAP"""
    # Pour l'instant, utilisons des données réelles de SAP pour tester l'interface
    return {
        'products': [
            {
                'code': 'A00001',
                'name': 'Imprimante IBM type Infoprint 1312',
                'description': 'Imprimante professionnelle IBM',
                'price': 400.0,
                'currency': 'EUR',
                'stock': 1130,
                'category': 'Imprimantes'
            },
            {
                'code': 'A00002',
                'name': 'Imprimante IBM type Infoprint 1222',
                'description': 'Imprimante professionnelle IBM',
                'price': 400.0,
                'currency': 'EUR',
                'stock': 1123,
                'category': 'Imprimantes'
            },
            {
                'code': 'A00004',
                'name': 'Imprimante HP type Color Laser Jet 5',
                'description': 'Imprimante couleur HP professionnelle',
                'price': 500.0,
                'currency': 'EUR',
                'stock': 1129,
                'category': 'Imprimantes'
            },
            {
                'code': 'C00001',
                'name': 'Carte mère P4 Turbo',
                'description': 'Carte mère haute performance',
                'price': 400.0,
                'currency': 'EUR',
                'stock': 1511,
                'category': 'Composants'
            },
            {
                'code': 'C00003',
                'name': 'Processeur Intel P4 2.4 GhZ',
                'description': 'Processeur Intel haute performance',
                'price': 130.0,
                'currency': 'EUR',
                'stock': 1167,
                'category': 'Composants'
            },
            {
                'code': 'C00004',
                'name': 'Tour PC avec alimentation',
                'description': 'Boîtier PC complet avec alimentation',
                'price': 35.0,
                'currency': 'EUR',
                'stock': 1262,
                'category': 'Boîtiers'
            },
            {
                'code': 'B10000',
                'name': 'Etiquettes pour imprimante',
                'description': 'Etiquettes compatibles imprimantes',
                'price': 1.0,
                'currency': 'EUR',
                'stock': 500,
                'category': 'Consommables'
            }
        ]
    }

# Fonctions synchrones pour compatibilité (fallback simple)
def get_clients_data():
    """Version synchrone - retourne des données d'exemple"""
    return {
        'clients': [
            {'name': 'Airbus Industries', 'type': 'Customer', 'industry': 'Manufacturing'},
            {'name': 'Edge Communications', 'type': 'Customer', 'industry': 'Electronics'},
            {'name': 'Burlington Textiles', 'type': 'Customer', 'industry': 'Apparel'}
        ]
    }

def get_products_data():
    """Version synchrone - retourne des données d'exemple"""
    return {
        'products': [
            {'name': 'Imprimante HP LaserJet', 'code': 'HP001', 'price': 299.99},
            {'name': 'Ordinateur Dell OptiPlex', 'code': 'DELL001', 'price': 899.99},
            {'name': 'Écran Samsung 24"', 'code': 'SAM001', 'price': 199.99}
        ]
    }

logger = logging.getLogger(__name__)

# Modèles Pydantic
class ChatMessage(BaseModel):
    message: str

class ChatResponse(BaseModel):
    success: bool
    response: Optional[Dict[str, Any]] = None
    intent: Optional[Dict[str, Any]] = None
    conversation_id: Optional[int] = None
    error: Optional[str] = None

# Router pour l'assistant intelligent
# router = APIRouter(prefix="/api/assistant", tags=["Assistant Intelligent"])  # Déjà défini plus haut

# Instances des services
suggestion_engine = SuggestionEngine()
client_validator = ClientValidator()
progress_tracker = ProgressTracker()

class ConversationManager:
    """Gestionnaire de conversation intelligente avec NOVA"""
    
    def __init__(self):
        self.conversation_history = []
        self.current_context = {}
        self.user_preferences = {}
    
    def analyze_intent(self, user_message: str) -> Dict[str, Any]:
        """Analyse l'intention de l'utilisateur avec logique améliorée"""
        message_lower = user_message.lower()
        
        # Patterns d'intention - avec priorité aux patterns spécifiques
        intent_patterns = {
            'find_client': ['rechercher client', 'chercher client', 'trouver client', 'client chercher', 'client', 'chercher', 'trouver', 'recherche'],
            'find_product': ['rechercher produit', 'chercher produit', 'trouver produit', 'produit chercher', 'produit', 'référence', 'article', 'stock'],
            'create_quote': ['créer devis', 'nouveau devis', 'faire devis', 'génération devis', 'devis', 'créer', 'nouveau', 'génération', 'quote'],
            'help': ['aide', 'help', 'comment', 'expliquer'],
            'status': ['statut', 'état', 'progression', 'avancement'],
            'greeting': ['bonjour', 'salut', 'hello', 'bonsoir']
        }
        
        # Détecter l'intention avec priorité aux patterns longs
        detected_intent = None
        max_match_length = 0
        
        for intent, keywords in intent_patterns.items():
            for keyword in keywords:
                if keyword in message_lower:
                    # Priorité aux patterns plus longs (plus spécifiques)
                    if len(keyword.split()) > max_match_length:
                        max_match_length = len(keyword.split())
                        detected_intent = intent
                        break
        
        return {
            'primary_intent': detected_intent if detected_intent else 'unknown',
            'all_intents': [detected_intent] if detected_intent else [],
            'confidence': 0.8 if detected_intent else 0.2,
            'entities': self._extract_entities(user_message)
        }
    
    def _extract_entities(self, message: str) -> Dict[str, List[str]]:
        """Extrait les entités du message (noms, références, etc.)"""
        import re
        
        entities = {
            'client_names': [],
            'product_refs': [],
            'quantities': [],
            'dates': []
        }
        
        # Extraction des références produits (format A00XXX, B00XXX, etc.)
        product_refs = re.findall(r'\b[A-Z]\d{5}\b', message)
        entities['product_refs'] = product_refs
        
        # Extraction des quantités - plus flexible
        quantities = []
        
        # 1. Nombres avec unités explicites
        qty_with_units = re.findall(r'\b(\d+)\s*(?:pièces?|unités?|pc|u)\b', message, re.IGNORECASE)
        quantities.extend([int(q) for q in qty_with_units])
        
        # 2. Patterns spécifiques pour les quantités
        qty_patterns = [
            r'\b(\d+)\s+ref\b',  # "500 ref"
            r'\bquantité\s+(\d+)\b',  # "quantité 25"
            r'\b(\d+)\s+[A-Z]\d{5}\b',  # "100 A00025"
        ]
        
        for pattern in qty_patterns:
            matches = re.findall(pattern, message, re.IGNORECASE)
            quantities.extend([int(q) for q in matches])
        
        # 3. Nombres isolés (probablement des quantités) - plus restrictif
        isolated_numbers = re.findall(r'\b(\d{1,4})\b', message)
        for num in isolated_numbers:
            num_int = int(num)
            # Considérer comme quantité si entre 1 et 9999 et pas déjà détecté
            if 1 <= num_int <= 9999 and num_int not in quantities:
                # Vérifier que ce n'est pas une référence produit
                if not re.search(rf'[A-Z]\d{{5}}.*{num}|{num}.*[A-Z]\d{{5}}', message):
                    quantities.append(num_int)
        
        # Supprimer les doublons et trier
        entities['quantities'] = sorted(list(set(quantities)))
        
        # Extraction des noms de clients - amélioration
        client_names = []
        
        # 1. Patterns explicites avec mots-clés
        explicit_patterns = [
            r'(?:client|pour le client|société|entreprise)\s+([A-Z][a-zA-Z\s]+?)(?:\s|$|,|\.|\n)',
            r'\bpour\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b',  # "pour Edge Communications"
        ]
        
        for pattern in explicit_patterns:
            matches = re.findall(pattern, message)
            for match in matches:
                clean_name = match.strip()
                if clean_name and clean_name not in client_names:
                    # Vérifier que ce n'est pas une référence produit
                    if not re.match(r'^[A-Z]\d{5}$', clean_name):
                        client_names.append(clean_name)
        
        # 2. Noms propres composés (seulement si pas déjà trouvés)
        if not client_names:
            compound_names = re.findall(r'\b([A-Z][a-z]+\s+[A-Z][a-z]+)\b', message)
            for name in compound_names:
                if name not in client_names:
                    # Vérifier que ce n'est pas un mot commun
                    common_words = ['edge communications', 'microsoft corp', 'nouveau devis', 'pour client']
                    if name.lower() not in common_words:
                        client_names.append(name)
        
        # 3. Filtrer les mots communs et références
        filtered_names = []
        for name in client_names:
            # Exclure les mots communs et références produits
            if (name.lower() not in ['devis', 'pour', 'avec', 'dans', 'sur', 'client', 'produit', 'ref', 'nouveau'] and
                not re.match(r'^[A-Z]\d{5}$', name) and  # Pas une référence produit
                len(name) > 2):  # Au moins 3 caractères
                filtered_names.append(name)
        
        entities['client_names'] = filtered_names
        
        return entities

conversation_manager = ConversationManager()

@router.post('/chat', response_model=ChatResponse)
async def chat_with_nova(message_data: ChatMessage):
    """
    🤖 Endpoint principal pour converser avec NOVA
    """
    try:
        user_message = message_data.message.strip()
        
        if not user_message:
            raise HTTPException(status_code=400, detail="Message vide")
        
        # Analyser l'intention
        intent_analysis = conversation_manager.analyze_intent(user_message)
        
        # ✅ NOUVELLE LOGIQUE - Détection automatique des devis
        if detect_workflow_request(user_message):
            logger.info(f"🎯 Demande de devis détectée automatiquement: {user_message}")
            
            try:
                # Lancer directement le workflow de création
                from workflow.devis_workflow import DevisWorkflow
                
                # Mode production (pas draft) pour créer réellement le devis
                workflow = DevisWorkflow(
                    validation_enabled=True,
                    draft_mode=False,
                    force_production=True  # 🔥 FORCER LE MODE PRODUCTION
                )
                
                # Exécuter le workflow avec le message complet
                workflow_result = await workflow.process_prompt(user_message)
                
                if workflow_result.get('success'):
                    response = {
                        'type': 'quote_created',
                        'message': f"✅ **Devis créé avec succès !**\n\n📋 **Référence :** {workflow_result.get('quote_id', 'N/A')}\n💰 **Montant :** {workflow_result.get('total_amount', 'N/A')}€\n🏢 **Client :** {workflow_result.get('client_name', 'N/A')}",
                        'quote_data': workflow_result,
                        'suggestions': ["Voir le devis", "Créer un nouveau devis", "Modifier ce devis"]
                    }
                else:
                    # Si échec, proposer des alternatives
                    error_msg = workflow_result.get('message', 'Erreur inconnue')
                    response = {
                        'type': 'quote_error',
                        'message': f"❌ **Impossible de créer le devis**\n\n{error_msg}\n\n💡 **Que faire ?**\n• Vérifier les informations\n• Créer le client s'il n'existe pas\n• Utiliser l'interface classique",
                        'suggestions': ["Interface classique", "Créer le client", "Réessayer"]
                    }
                
                # Sauvegarder dans l'historique
                conversation_manager.conversation_history.append({
                    'timestamp': datetime.now().isoformat(),
                    'user_message': user_message,
                    'intent': intent_analysis,
                    'nova_response': response
                })
                
                return ChatResponse(
                    success=True,
                    response=response,
                    intent=intent_analysis,
                    conversation_id=len(conversation_manager.conversation_history)
                )
                    
            except Exception as e:
                logger.error(f"Erreur workflow automatique: {e}")
                response = {
                    'type': 'system_error',
                    'message': f"⚠️ **Erreur système**\n\n{str(e)}\n\nUtilisez l'interface classique pour créer votre devis.",
                    'suggestions': ["Interface classique", "Aide"]
                }
                
                return ChatResponse(
                    success=True,
                    response=response,
                    intent=intent_analysis,
                    conversation_id=len(conversation_manager.conversation_history)
                )
        
        # Générer la réponse selon l'intention (logique existante)
        response = generate_intelligent_response(user_message, intent_analysis)
        
        # Sauvegarder dans l'historique
        conversation_manager.conversation_history.append({
            'timestamp': datetime.now().isoformat(),
            'user_message': user_message,
            'intent': intent_analysis,
            'nova_response': response
        })
        
        return ChatResponse(
            success=True,
            response=response,
            intent=intent_analysis,
            conversation_id=len(conversation_manager.conversation_history)
        )
        
    except Exception as e:
        logger.error(f"Erreur dans chat_with_nova: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur interne: {str(e)}")

def generate_intelligent_response(message: str, intent: Dict[str, Any]) -> Dict[str, Any]:
    """Génère une réponse intelligente basée sur l'intention détectée"""
    
    primary_intent = intent['primary_intent']
    entities = intent['entities']
    
    if primary_intent == 'greeting':
        return {
            'type': 'greeting',
            'message': "👋 Bonjour ! Je suis NOVA, votre assistant intelligent pour la génération de devis.\n\n💡 **Je peux vous aider à :**\n• Créer des devis automatiquement\n• Trouver des clients et produits\n• Valider des informations\n• Proposer des solutions intelligentes\n\n🚀 **Dites-moi simplement ce que vous voulez faire !**",
            'suggestions': [
                "Créer un nouveau devis",
                "Chercher un client",
                "Voir les produits disponibles"
            ],
            'quick_actions': [
                {'label': '📝 Nouveau Devis', 'action': 'new_quote'},
                {'label': '👥 Clients', 'action': 'show_clients'},
                {'label': '📦 Produits', 'action': 'show_products'}
            ]
        }
    
    elif primary_intent == 'create_quote':
        return handle_quote_creation_intent(message, entities)
    
    elif primary_intent == 'find_client':
        return handle_client_search_intent(message, entities)
    
    elif primary_intent == 'find_product':
        return handle_product_search_intent(message, entities)
    
    elif primary_intent == 'help':
        return {
            'type': 'help',
            'message': "🆘 **Guide d'utilisation NOVA**\n\n**Exemples de demandes :**\n• \"Créer un devis pour Edge Communications\"\n• \"Chercher le client Acme Corp\"\n• \"Produit A00025 disponible ?\"\n• \"Nouveau devis avec 10 ordinateurs\"\n\n**Fonctionnalités intelligentes :**\n✅ Correction automatique des noms\n✅ Suggestions proactives\n✅ Validation en temps réel\n✅ Détection des doublons",
            'suggestions': [
                "Créer un devis pour [nom client]",
                "Chercher le produit [référence]",
                "Voir mes devis en cours"
            ]
        }
    
    else:
        # Intention inconnue - Proposer des suggestions intelligentes
        return {
            'type': 'suggestion',
            'message': f"🤔 Je n'ai pas bien compris votre demande : \"{message}\"\n\n💡 **Voulez-vous peut-être :**",
            'suggestions': [
                "Créer un nouveau devis",
                "Rechercher un client ou produit",
                "Voir l'aide complète"
            ],
            'quick_actions': [
                {'label': '📝 Créer Devis', 'action': 'new_quote'},
                {'label': '🔍 Rechercher', 'action': 'search'},
                {'label': '❓ Aide', 'action': 'help'}
            ]
        }

def handle_quote_creation_intent(message: str, entities: Dict[str, Any]) -> Dict[str, Any]:
    """Gère l'intention de création de devis en utilisant le workflow existant"""
    
    try:
        # Importer le workflow de devis existant
        from workflow.devis_workflow import DevisWorkflow
        
        response = {
            'type': 'quote_creation',
            'message': "📝 **Création de devis intelligente**\n\n",
            'suggestions': [],
            'workflow_action': 'create_quote'
        }
        
        # Utiliser le workflow existant pour analyser le message
        workflow = DevisWorkflow(
            validation_enabled=True,
            draft_mode=False,
            force_production=True  # 🔥 FORCER LE MODE PRODUCTION
        )
        
        # Le workflow peut analyser le message directement
        response['message'] += f"🔍 **Analyse de votre demande :**\n"
        response['message'] += f"'{message}'\n\n"
        
        # Proposer d'utiliser le workflow complet
        response['message'] += "🚀 **Options disponibles :**\n"
        response['message'] += "1. 📝 Créer le devis avec le workflow complet\n"
        response['message'] += "2. 🔍 Analyser d'abord les informations\n"
        response['message'] += "3. 💼 Ouvrir l'interface classique\n\n"
        
        response['suggestions'] = [
            "Créer le devis maintenant",
            "Analyser les informations",
            "Interface classique"
        ]
        
        # Actions rapides pour le workflow
        response['quick_actions'] = [
            {'label': '🚀 Créer Devis', 'action': 'start_workflow', 'data': {'message': message}},
            {'label': '🔍 Analyser', 'action': 'analyze_request', 'data': {'message': message}},
            {'label': '💼 Interface', 'action': 'open_classic'}
        ]
        
        return response
        
    except ImportError as e:
        logger.error(f"Erreur import workflow: {e}")
        return {
            'type': 'error',
            'message': f"❌ **Erreur workflow**\n\nImpossible de charger le workflow de devis.\n\n💡 **Solution :** Utilisez l'interface classique pour créer vos devis.",
            'suggestions': ["Ouvrir l'interface classique", "Contacter le support"]
        }
    except Exception as e:
        logger.error(f"Erreur création devis: {e}")
        return {
            'type': 'error', 
            'message': f"❌ **Erreur inattendue**\n\n{str(e)}",
            'suggestions': ["Réessayer", "Interface classique"]
        }

def handle_client_search_intent(message: str, entities: Dict[str, Any]) -> Dict[str, Any]:
    """Gère l'intention de recherche de client avec recherche google-like"""
    
    client_names = entities.get('client_names', [])
    
    if not client_names:
        return {
            'type': 'client_search_prompt',
            'message': "🔍 **Recherche Google-Like Client**\n\n**Tapez le nom du client à rechercher :**\n\n💡 **Exemples :**\n• \"Microsoft\"\n• \"Orange\"\n• \"Air France\"\n\nJe rechercherai automatiquement et proposerai des suggestions.",
            'suggestions': [
                "Tous les clients",
                "Créer nouveau client"
            ],
            'enable_search_mode': True
        }
    
    # Recherche intelligente avec les vraies données
    try:
        search_term = client_names[0]
        logger.info(f"🔍 Recherche google-like pour client: '{search_term}'")
        
        # Appel HTTP interne à l'endpoint de recherche clients
        import httpx
        import asyncio
        
        async def search_real_clients():
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"http://localhost:8000/clients/search_clients_advanced",
                    params={"q": search_term, "limit": 10}
                )
                return response.json()
        
        # Exécuter la recherche
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        clients_data = loop.run_until_complete(search_real_clients())
        loop.close()
        
        response = {
            'type': 'client_search_results',
            'message': f"🔍 **Résultats pour '{search_term}'**\n\n",
            'suggestions': []
        }
        
        if clients_data.get('success') and clients_data.get('clients'):
            # Clients trouvés - affichage google-like
            found_clients = clients_data['clients'][:5]  # Max 5 résultats
            
            response['message'] += f"✅ **{len(found_clients)} résultat(s) trouvé(s) :**\n\n"
            
            for i, client in enumerate(found_clients, 1):
                client_name = client.get('name', 'Client sans nom')
                location = client.get('location_display', '')
                industry = client.get('industry', '')
                
                response['message'] += f"**{i}. {client_name}**\n"
                if location:
                    response['message'] += f"   📍 {location}\n"
                if industry:
                    response['message'] += f"   🏭 {industry}\n"
                response['message'] += f"   🆔 ID: {client.get('id', 'N/A')}\n\n"
            
            # Suggestions d'actions
            response['suggestions'] = [
                f"Utiliser {found_clients[0]['name']}",
                "Affiner la recherche",
                f"Créer '{search_term}'" if search_term.lower() not in [c['name'].lower() for c in found_clients] else "Nouveau client"
            ]
            
            if len(clients_data['clients']) > 5:
                response['message'] += f"... et {len(clients_data['clients']) - 5} autres résultats.\n\n"
                response['suggestions'].append("Voir tous les résultats")
                
        else:
            # Aucun client trouvé - proposer création
            response['message'] += f"❌ **Aucun client trouvé pour '{search_term}'**\n\n"
            response['message'] += "💡 **Que souhaitez-vous faire ?**\n\n"
            response['message'] += f"1. 🆕 **Créer le client '{search_term}'**\n"
            response['message'] += "2. 🔍 **Essayer une autre recherche**\n"
            response['message'] += "3. 👥 **Voir tous les clients disponibles**\n"
            
            response['suggestions'] = [
                f"Créer '{search_term}'",
                "Nouvelle recherche", 
                "Tous les clients"
            ]
            response['create_option'] = {
                'client_name': search_term,
                'action': 'create_client'
            }
        
        return response
        
    except Exception as e:
        logger.error(f"Erreur recherche client google-like: {e}")
        return {
            'type': 'error',
            'message': f"❌ **Erreur lors de la recherche**\n\n{str(e)}\n\nVoulez-vous essayer une recherche manuelle ?",
            'suggestions': [
                "Nouvelle recherche",
                "Tous les clients",
                f"Créer '{client_names[0] if client_names else 'nouveau client'}'"
            ]
        }

def handle_product_search_intent(message: str, entities: Dict[str, Any]) -> Dict[str, Any]:
    """Gère l'intention de recherche de produit avec recherche google-like"""
    
    product_refs = entities.get('product_refs', [])
    
    if not product_refs:
        return {
            'type': 'product_search_prompt',
            'message': "🔍 **Recherche Google-Like Produit**\n\n**Tapez la référence ou le nom du produit à rechercher :**\n\n💡 **Exemples :**\n• \"A00025\"\n• \"Connecteur USB\"\n• \"Cable HDMI\"\n\nJe rechercherai automatiquement et proposerai des suggestions.",
            'suggestions': [
                "Tous les produits",
                "Créer nouveau produit"
            ],
            'enable_search_mode': True
        }
    
    # Recherche intelligente avec les vraies données
    try:
        search_term = product_refs[0]
        logger.info(f"🔍 Recherche google-like pour produit: '{search_term}'")
        
        # Appel HTTP interne à l'endpoint de recherche produits
        import httpx
        import asyncio
        
        async def search_real_products():
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"http://localhost:8000/products/search_products_advanced",
                    params={"q": search_term, "limit": 10}
                )
                return response.json()
        
        # Exécuter la recherche
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        products_data = loop.run_until_complete(search_real_products())
        loop.close()
        
        response = {
            'type': 'product_search_results',
            'message': f"🔍 **Résultats pour '{search_term}'**\n\n",
            'suggestions': []
        }
        
        if products_data.get('success') and products_data.get('products'):
            # Produits trouvés - affichage google-like
            found_products = products_data['products'][:5]  # Max 5 résultats
            
            response['message'] += f"✅ **{len(found_products)} résultat(s) trouvé(s) :**\n\n"
            
            for i, product in enumerate(found_products, 1):
                product_code = product.get('ItemCode', 'Sans référence')
                product_name = product.get('ItemName', 'Sans nom')
                product_price = product.get('UnitPrice', 0)
                product_stock = product.get('StockQuantity', 0)
                
                response['message'] += f"**{i}. {product_code} - {product_name}**\n"
                if product_price > 0:
                    response['message'] += f"   💰 Prix: {product_price:.2f}€ HT\n"
                response['message'] += f"   📦 Stock: {product_stock} unités\n"
                response['message'] += f"   🆔 Code: {product_code}\n\n"
            
            # Suggestions d'actions
            best_product = found_products[0]
            response['suggestions'] = [
                f"Utiliser {best_product['ItemCode']}",
                "Affiner la recherche",
                f"Créer '{search_term}'" if search_term.upper() not in [p['ItemCode'].upper() for p in found_products] else "Nouveau produit"
            ]
            
            if len(products_data['products']) > 5:
                response['message'] += f"... et {len(products_data['products']) - 5} autres résultats.\n\n"
                response['suggestions'].append("Voir tous les résultats")
                
        else:
            # Aucun produit trouvé - proposer création
            response['message'] += f"❌ **Aucun produit trouvé pour '{search_term}'**\n\n"
            response['message'] += "💡 **Que souhaitez-vous faire ?**\n\n"
            response['message'] += f"1. 🆕 **Créer le produit '{search_term}'**\n"
            response['message'] += "2. 🔍 **Essayer une autre recherche**\n"
            response['message'] += "3. 📦 **Voir tous les produits disponibles**\n"
            response['message'] += "4. 📞 **Contacter le support pour vérifier la référence**\n"
            
            response['suggestions'] = [
                f"Créer '{search_term}'",
                "Nouvelle recherche", 
                "Tous les produits",
                "Contacter support"
            ]
            response['create_option'] = {
                'product_ref': search_term,
                'action': 'create_product'
            }
        
        return response
        
    except Exception as e:
        logger.error(f"Erreur recherche produit google-like: {e}")
        return {
            'type': 'error',
            'message': f"❌ **Erreur lors de la recherche**\n\n{str(e)}\n\nVoulez-vous essayer une recherche manuelle ?",
            'suggestions': [
                "Nouvelle recherche",
                "Tous les produits",
                f"Créer '{product_refs[0] if product_refs else 'nouveau produit'}'"
            ]
        }

@router.get('/suggestions/{suggestion_type}')
async def get_contextual_suggestions(suggestion_type: str):
    """Endpoint pour obtenir des suggestions contextuelles"""
    try:
        if suggestion_type == 'clients':
            clients_data = get_clients_data()
            return {
                'success': True,
                'suggestions': clients_data.get('clients', [])[:10]  # Top 10
            }
        
        elif suggestion_type == 'products':
            products_data = get_products_data()
            return {
                'success': True,
                'suggestions': products_data.get('products', [])[:10]  # Top 10
            }
        
        else:
            raise HTTPException(status_code=400, detail="Type de suggestion non supporté")
            
    except Exception as e:
        logger.error(f"Erreur suggestions contextuelles: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/conversation/history')
async def get_conversation_history():
    """Récupère l'historique de conversation"""
    return {
        'success': True,
        'history': conversation_manager.conversation_history[-10:]  # 10 derniers
    }

@router.post('/conversation/clear')
async def clear_conversation():
    """Efface l'historique de conversation"""
    conversation_manager.conversation_history.clear()
    conversation_manager.current_context.clear()
    
    return {
        'success': True,
        'message': 'Historique effacé'
    }

@router.post('/workflow/create_quote')
async def start_quote_workflow(message_data: ChatMessage):
    """Exécute le workflow de création de devis avec le message utilisateur"""
    try:
        from workflow.devis_workflow import DevisWorkflow
        import json
        
        # Créer une instance du workflow
        workflow = DevisWorkflow(validation_enabled=True, draft_mode=True, force_production=True)  # Mode draft pour éviter la création immédiate
        
        # Analyser le message pour extraire les informations
        message = message_data.message
        logger.info(f"Exécution du workflow pour: {message}")
        
        # Exécuter le workflow complet
        result = await workflow.process_prompt(message)
        workflow_status = result.get('workflow_status', 'completed')

        # Analyser les résultats pour créer une réponse intelligente
        response = {
            'success': result.get('success', False),
            'workflow_status': workflow_status,
            'message': '',
            'quote_data': result,
            'quick_actions': [],
            'warnings': [],
            'suggestions': []
        }
        
        # Construire le message de réponse
        if result.get('success'):
            response['message'] = "**Analyse de devis terminée**\n\n"
            
            # Informations client
            client_name = result.get('client_name', 'Client non identifié')
            response['message'] += f"**Client :** {client_name}\n"
            
            # Gestion des doublons
            duplicates = result.get('duplicate_analysis', {})
            if duplicates.get('action_required'):
                recent_count = len(duplicates.get('recent_quotes', []))
                draft_count = len(duplicates.get('draft_quotes', []))
                
                if recent_count > 0:
                    response['warnings'].append(f"{recent_count} devis récent(s) trouvé(s)")
                    response['message'] += f"⚠️ **{recent_count} devis récent(s)** trouvé(s) pour ce client\n"
                    
                if draft_count > 0:
                    response['warnings'].append(f"{draft_count} devis brouillon(s) existant(s)")
                    response['message'] += f"📝 **{draft_count} devis brouillon(s)** existant(s)\n"
                
                response['message'] += "\n**Actions recommandées :**\n"
                response['quick_actions'].extend([
                    {'action': 'view_duplicates', 'label': 'Voir les doublons', 'type': 'info'},
                    {'action': 'create_new', 'label': 'Créer nouveau devis', 'type': 'primary'},
                    {'action': 'update_existing', 'label': 'Modifier un existant', 'type': 'secondary'}
                ])
            else:
                response['message'] += "✅ **Aucun doublon détecté**\n"
                response['quick_actions'].append(
                    {'action': 'create_quote', 'label': 'Créer le devis', 'type': 'primary'}
                )
            
            # Aperçu du devis
            quote_preview = result.get('quote_preview', {})
            if quote_preview:
                total = quote_preview.get('total_amount', 0)
                currency = quote_preview.get('currency', 'EUR')
                response['message'] += f"\n**Montant estimé :** {total} {currency}\n"
                
                products = quote_preview.get('products', [])
                if products:
                    response['message'] += f"**Produits :** {len(products)} article(s)\n"
            
            # Actions rapides générales
            response['quick_actions'].extend([
                {'action': 'open_classic', 'label': 'Interface classique', 'type': 'secondary'},
                {'action': 'export_pdf', 'label': 'Exporter PDF', 'type': 'info'}
            ])
            
        else:
            if workflow_status in ["waiting_for_input", "configuring_quantities"]:
                response['message'] = result.get('message', '')
                response['quick_actions'] = result.get('quick_actions', [])
                response['suggestions'] = result.get('suggestions', []) if isinstance(result.get('suggestions'), list) else result.get('suggestions', {}).get('examples', [])
            else:
                response['success'] = False
                response['message'] = f"**Erreur lors de l'analyse**\n\n{result.get('error', 'Erreur inconnue')}"
                response['quick_actions'] = [
                    {'action': 'retry', 'label': 'Réessayer', 'type': 'primary'},
                    {'action': 'manual_entry', 'label': 'Saisie manuelle', 'type': 'secondary'}
                ]
        
        return response
        
    except ImportError as e:
        logger.error(f"Erreur import workflow: {e}")
        raise HTTPException(status_code=500, detail="Workflow de devis non disponible")
    except Exception as e:
        logger.error(f"Erreur exécution workflow: {e}")
        return {
            'success': False,
            'message': f"**Erreur technique**\n\n{str(e)}",
            'workflow_status': 'error',
            'quick_actions': [
                {'action': 'retry', 'label': 'Réessayer', 'type': 'primary'},
                {'action': 'contact_support', 'label': 'Contacter le support', 'type': 'info'}
            ]
        }

# Route pour servir l'interface intelligente
@router.get('/interface', response_class=HTMLResponse)
async def intelligent_interface():
    """Sert l'interface de l'assistant intelligent"""
    try:
        with open('templates/intelligent_assistant.html', 'r', encoding='utf-8') as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Interface non trouvée")

@router.get("/clients/list")
async def get_clients_list():
    """Endpoint pour récupérer la liste complète des clients"""
    try:
        # Récupération des clients via MCP
        clients_data = await get_clients_data_async()
        # Normaliser les clés pour l'interface
        for client in clients_data.get('clients', []):
            client['name'] = client.get('Name', client.get('name', ''))
            client['type'] = client.get('Type', client.get('type', ''))
            client['industry'] = client.get('Industry', client.get('industry', ''))
            client['phone'] = client.get('Phone', client.get('phone', ''))
        clients = clients_data.get('clients', [])
        
        # Formatage pour affichage
        formatted_clients = []
        for client in clients[:15]:  # Limiter à 15 pour l'affichage
            formatted_client = f"**{client.get('name', 'Client sans nom')}**"
            details = []
            if client.get('type'):
                details.append(f"Type: {client['type']}")
            if client.get('industry'):
                details.append(f"Secteur: {client['industry']}")
            if client.get('phone'):
                details.append(f"Tél: {client['phone']}")
            if client.get('city'):
                details.append(f"Ville: {client['city']}")
            if client.get('country'):
                details.append(f"Pays: {client['country']}")
            
            if details:
                formatted_client += f" - {' | '.join(details)}"
            formatted_clients.append(formatted_client)
        
        total_clients = len(clients)
        message = f"🔍 **{len(formatted_clients)} clients trouvés** (sur {total_clients} total)"
        
        return {
            "success": True,
            "clients": formatted_clients,
            "total": total_clients,
            "message": message
        }
        
    except Exception as e:
        logger.error(f"Erreur endpoint clients/list: {e}")
        return {
            "success": False,
            "clients": [],
            "total": 0,
            "message": f"❌ Erreur lors de la récupération des clients: {str(e)}"
        }

@router.get("/products/list")
async def get_products_list():
    """Récupère la liste complète des produits"""
    try:
        # Récupération des produits via MCP
        products_data = await get_products_data_async()
        products = products_data.get('products', [])
        
        # Formater les produits pour l'affichage
        formatted_products = []
        for product in products:
            formatted_product = {
                'code': product.get('code', product.get('Code', '')),
                'name': product.get('name', product.get('Name', 'Produit sans nom')),
                'description': product.get('description', product.get('Description', '')),
                'price': product.get('price', product.get('Price', 0)),
                'currency': product.get('currency', product.get('Currency', 'EUR')),
                'stock': product.get('stock', product.get('Stock', 0)),
                'category': product.get('category', product.get('Category', 'Général'))
            }
            formatted_products.append(formatted_product)
        
        return {
            'success': True,
            'products': formatted_products,
            'total': len(formatted_products),
            'message': f"🛍️ **{len(formatted_products)} produits trouvés** (sur {len(formatted_products)} total)"
        }
        
    except Exception as e:
        logger.error(f"Erreur récupération liste produits: {e}")
        return {
            'success': False,
            'products': [],
            'total': 0,
            'error': str(e),
            'message': "❌ **Erreur lors de la récupération des produits**"
        }
@router.post("/choice")
async def handle_user_choice(choice_data: Dict[str, Any]):
    """
    🔧 GESTION DES CHOIX UTILISATEUR DEPUIS L'INTERFACE
    """
    try:
        choice_type = choice_data.get("type")
        task_id = choice_data.get("task_id")

        if not task_id:
            raise HTTPException(status_code=400, detail="task_id manquant")

        # Récupérer le contexte du workflow
        workflow_context = await get_workflow_context(task_id)

        if choice_type == "client_choice":
            # Choix client depuis les suggestions
            workflow = DevisWorkflow(task_id=task_id, force_production=True)
            result = await workflow.handle_client_suggestions(choice_data, workflow_context)

        elif choice_type == "product_choice":
            # Choix produit depuis les alternatives
            workflow = DevisWorkflow(task_id=task_id, force_production=True)
            result = await workflow.apply_product_suggestions(choice_data.get("products", []), workflow_context)

        elif choice_type == "create_client":
            # Déclenchement création client
            workflow = DevisWorkflow(task_id=task_id, force_production=True)
            result = await workflow._handle_new_client_creation(
                choice_data.get("client_name", ""),
                workflow_context
            )

        else:
            raise HTTPException(status_code=400, detail=f"Type de choix '{choice_type}' non supporté")

        return result

    except Exception as e:
        logger.error(f"Erreur gestion choix utilisateur: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/choice")
async def handle_user_choice(choice_data: Dict[str, Any]):
    """
    🔧 GESTION DES CHOIX UTILISATEUR DEPUIS L'INTERFACE
    """
    try:
        choice_type = choice_data.get("type")
        task_id = choice_data.get("task_id")

        if not task_id:
            raise HTTPException(status_code=400, detail="task_id manquant")

        # Récupérer le contexte du workflow
        workflow_context = await get_workflow_context(task_id)

        if choice_type == "client_choice":
            # Choix client depuis les suggestions
            workflow = DevisWorkflow(task_id=task_id, force_production=True)
            result = await workflow.handle_client_suggestions(choice_data, workflow_context)

        elif choice_type == "product_choice":
            # Choix produit depuis les alternatives
            workflow = DevisWorkflow(task_id=task_id, force_production=True)
            result = await workflow.apply_product_suggestions(choice_data.get("products", []), workflow_context)

        elif choice_type == "create_client":
            # Déclenchement création client
            workflow = DevisWorkflow(task_id=task_id, force_production=True)
            result = await workflow._handle_new_client_creation(
                choice_data.get("client_name", ""),
                workflow_context
            )

        else:
            raise HTTPException(status_code=400, detail=f"Type de choix '{choice_type}' non supporté")

        return result

    except Exception as e:
        logger.error(f"Erreur gestion choix utilisateur: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Import du workflow de création de client
from workflow.client_creation_workflow import client_creation_workflow

# Modèles pour la création de client
class ClientSearchRequest(BaseModel):
    company_name: Optional[str] = None
    city: Optional[str] = None
    siret: Optional[str] = None

class ClientCreationRequest(BaseModel):
    siret: str
    additional_data: Optional[Dict[str, Any]] = {}

@router.post('/client/search')
async def search_companies(request: ClientSearchRequest):
    """
    🔍 Recherche d'entreprises par nom ou SIRET via INSEE/Pappers
    """
    try:
        logger.info(f"🔍 Recherche entreprise: {request.company_name or request.siret}")

        if request.siret:
            # Validation directe par SIRET
            result = await client_creation_workflow.validate_and_enrich_company(request.siret)
            if result.get("success"):
                return {
                    "success": True,
                    "companies": [result["company_data"]],
                    "search_method": "siret_validation",
                    "message": "Entreprise trouvée et validée"
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error"),
                    "message": result.get("message")
                }
        else:
            # Recherche par nom
            result = await client_creation_workflow.search_company_by_name(
                request.company_name,
                request.city
            )
            return result

    except Exception as e:
        logger.error(f"Erreur recherche entreprise: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": "Erreur lors de la recherche"
        }

@router.post('/client/create')
async def create_client(request: ClientCreationRequest):
    """
    🏢 Création d'un nouveau client dans Salesforce
    """
    try:
        logger.info(f"🏢 Création client SIRET: {request.siret}")

        # Valider et enrichir les données
        validation_result = await client_creation_workflow.validate_and_enrich_company(request.siret)

        if not validation_result.get("success"):
            return {
                "success": False,
                "error": validation_result.get("error"),
                "message": validation_result.get("message")
            }

        # Fusionner avec les données additionnelles
        company_data = validation_result["company_data"]
        company_data.update(request.additional_data)

        # Créer le client
        creation_result = await client_creation_workflow.create_client_in_salesforce(company_data)

        return creation_result

    except Exception as e:
        logger.error(f"Erreur création client: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": "Erreur lors de la création du client"
        }

@router.post('/client/workflow')
async def client_creation_workflow_endpoint(request: Dict[str, Any]):
    """
    🚀 Workflow complet de création de client
    """
    try:
        logger.info("🚀 Démarrage workflow création client")

        result = await client_creation_workflow.process_client_creation_request(request)
        return result

    except Exception as e:
        logger.error(f"Erreur workflow création client: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": "Erreur dans le workflow de création"
        }
    """
    🔧 GESTION DES CHOIX UTILISATEUR DEPUIS L'INTERFACE
    """
    try:
        choice_type = choice_data.get("type")
        task_id = choice_data.get("task_id")

        if not task_id:
            raise HTTPException(status_code=400, detail="task_id manquant")

        # Récupérer le contexte du workflow
        workflow_context = await get_workflow_context(task_id)

        if choice_type == "client_choice":
            # Choix client depuis les suggestions
            workflow = DevisWorkflow(task_id=task_id, force_production=True)
            result = await workflow.handle_client_suggestions(choice_data, workflow_context)

        elif choice_type == "product_choice":
            # Choix produit depuis les alternatives
            workflow = DevisWorkflow(task_id=task_id, force_production=True)
            result = await workflow.apply_product_suggestions(choice_data.get("products", []), workflow_context)

        elif choice_type == "create_client":
            # Déclenchement création client
            workflow = DevisWorkflow(task_id=task_id, force_production=True)
            result = await workflow._handle_new_client_creation(
                choice_data.get("client_name", ""),
                workflow_context
            )

        else:
            raise HTTPException(status_code=400, detail=f"Type de choix '{choice_type}' non supporté")

        return result

    except Exception as e:
        logger.error(f"Erreur gestion choix utilisateur: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Modèles pour la création de client
class ClientCreationRequest(BaseModel):
    company_name: str
    city: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None

class ClientCreationFromCompanyRequest(BaseModel):
    company_data: Dict[str, Any]
    contact_info: Optional[Dict[str, Any]] = None

@router.post('/create_client/search')
async def search_company_for_creation(request: ClientCreationRequest):
    """
    🔍 Recherche d'entreprise pour création de client
    """
    try:
        from workflow.client_creation_workflow import ClientCreationWorkflow

        workflow = ClientCreationWorkflow()

        # Rechercher les informations de l'entreprise
        search_results = await workflow.search_company_info(
            request.company_name,
            request.city
        )

        return {
            'success': True,
            'company_name': request.company_name,
            'city': request.city,
            'contact_name': request.contact_name,
            'search_results': search_results['search_results'],
            'recommended': search_results.get('recommended'),
            'sources': search_results.get('sources', []),
            'message': f"Trouvé {len(search_results['search_results'])} résultat(s) pour '{request.company_name}'"
        }

    except Exception as e:
        logger.error(f"Erreur recherche entreprise: {e}")
        return {
            'success': False,
            'error': str(e),
            'message': f"Erreur lors de la recherche: {str(e)}"
        }

@router.post('/create_client/confirm')
async def create_client_from_company(request: ClientCreationFromCompanyRequest):
    """
    ✅ Création de client à partir des données d'entreprise sélectionnées
    """
    try:
        from workflow.client_creation_workflow import ClientCreationWorkflow

        workflow = ClientCreationWorkflow()

        # Créer le client
        creation_result = await workflow.create_client_from_company_data(
            request.company_data,
            request.contact_info
        )

        return creation_result

    except Exception as e:
        logger.error(f"Erreur création client: {e}")
        return {
            'success': False,
            'error': str(e),
            'message': f"Erreur lors de la création: {str(e)}"
        }

@router.post('/create_client/from_text')
async def create_client_from_text(request: Dict[str, str]):
    """
    📝 Création de client à partir d'une demande en texte libre
    """
    try:
        from workflow.client_creation_workflow import ClientCreationWorkflow
        from services.llm_extractor import LLMExtractor

        workflow = ClientCreationWorkflow()

        # 🔧 CORRECTION: Extraire les informations structurées depuis le texte
        user_text = request.get('text', '').strip()

        if not user_text:
            return {
                'success': False,
                'error': 'Texte de demande requis',
                'message': 'Veuillez fournir une description du client à créer'
            }

        # Utiliser le LLM pour extraire les informations client
        llm_extractor = LLMExtractor()
        extracted_info = await llm_extractor.extract_client_info_from_text(user_text)

        if not extracted_info.get('success'):
            return {
                'success': False,
                'error': 'Extraction impossible',
                'message': 'Impossible d\'extraire les informations client du texte fourni',
                'details': extracted_info.get('error', 'Erreur inconnue')
            }

        # Traiter la demande avec les données structurées
        client_data = extracted_info.get('client_data', {})
        result = await workflow.process_client_creation_request(client_data)

        # 🆕 FALLBACK: Si l'API Sirene échoue, proposer la saisie manuelle
        if not result.get('success') and 'api' in result.get('error', '').lower():
            logger.warning("🔄 API Sirene indisponible - Activation du fallback saisie manuelle")

            # Retourner les données extraites pour saisie manuelle
            return {
                'success': False,
                'type': 'manual_input_required',
                'message': 'API de validation indisponible - Saisie manuelle requise',
                'extracted_data': client_data,
                'required_fields': [
                    {'name': 'company_name', 'label': 'Nom de l\'entreprise', 'type': 'text', 'required': True, 'value': client_data.get('company_name', '')},
                    {'name': 'contact_name', 'label': 'Nom du contact', 'type': 'text', 'required': False, 'value': client_data.get('contact_name', '')},
                    {'name': 'email', 'label': 'Email', 'type': 'email', 'required': False, 'value': client_data.get('email', '')},
                    {'name': 'phone', 'label': 'Téléphone', 'type': 'tel', 'required': False, 'value': client_data.get('phone', '')},
                    {'name': 'address', 'label': 'Adresse', 'type': 'text', 'required': False, 'value': client_data.get('address', '')},
                    {'name': 'city', 'label': 'Ville', 'type': 'text', 'required': False, 'value': client_data.get('city', '')},
                    {'name': 'postal_code', 'label': 'Code postal', 'type': 'text', 'required': False, 'value': client_data.get('postal_code', '')},
                    {'name': 'siret', 'label': 'SIRET (optionnel)', 'type': 'text', 'required': False, 'value': client_data.get('siret', '')}
                ],
                'fallback_reason': 'API de validation des entreprises temporairement indisponible'
            }

        return result

    except Exception as e:
        logger.error(f"Erreur traitement demande création: {e}")

        # 🆕 FALLBACK GÉNÉRAL: En cas d'erreur système, proposer aussi la saisie manuelle
        if 'api' in str(e).lower() or 'timeout' in str(e).lower() or 'connection' in str(e).lower():
            return {
                'success': False,
                'type': 'manual_input_required',
                'message': 'Service de validation temporairement indisponible - Saisie manuelle requise',
                'extracted_data': {},
                'required_fields': [
                    {'name': 'company_name', 'label': 'Nom de l\'entreprise', 'type': 'text', 'required': True, 'value': ''},
                    {'name': 'contact_name', 'label': 'Nom du contact', 'type': 'text', 'required': False, 'value': ''},
                    {'name': 'email', 'label': 'Email', 'type': 'email', 'required': False, 'value': ''},
                    {'name': 'phone', 'label': 'Téléphone', 'type': 'tel', 'required': False, 'value': ''},
                    {'name': 'address', 'label': 'Adresse', 'type': 'text', 'required': False, 'value': ''},
                    {'name': 'city', 'label': 'Ville', 'type': 'text', 'required': False, 'value': ''},
                    {'name': 'postal_code', 'label': 'Code postal', 'type': 'text', 'required': False, 'value': ''},
                    {'name': 'siret', 'label': 'SIRET (optionnel)', 'type': 'text', 'required': False, 'value': ''}
                ],
                'fallback_reason': 'Erreur de connexion aux services de validation'
            }

        return {
            'success': False,
            'error': str(e),
            'message': f"Erreur lors du traitement: {str(e)}"
        }

@router.post('/create_client/manual')
async def create_client_manual(request: Dict[str, Any]):
    """
    📝 Création de client avec saisie manuelle (fallback API Sirene)
    """
    try:
        from workflow.client_creation_workflow import ClientCreationWorkflow

        workflow = ClientCreationWorkflow()
        client_data = request.get('client_data', {})

        # Validation des champs obligatoires
        if not client_data.get('company_name', '').strip():
            return {
                'success': False,
                'error': 'Nom d\'entreprise requis',
                'message': 'Le nom de l\'entreprise est obligatoire pour créer un client'
            }

        # Nettoyer et normaliser les données
        normalized_data = {
            'company_name': client_data.get('company_name', '').strip(),
            'contact_name': client_data.get('contact_name', '').strip(),
            'email': client_data.get('email', '').strip(),
            'phone': client_data.get('phone', '').strip(),
            'address': client_data.get('address', '').strip(),
            'city': client_data.get('city', '').strip(),
            'postal_code': client_data.get('postal_code', '').strip(),
            'siret': client_data.get('siret', '').strip(),
            'country': 'FR',  # Par défaut France
            'source': 'manual_input',
            'validation_bypassed': True  # Indique que la validation API a été contournée
        }

        # Validation basique locale (sans API externe)
        validation_errors = []

        # Validation email basique
        if normalized_data['email']:
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, normalized_data['email']):
                validation_errors.append("Format d'email invalide")

        # Validation téléphone basique
        if normalized_data['phone']:
            phone_clean = re.sub(r'[^\d+]', '', normalized_data['phone'])
            if len(phone_clean) < 8:
                validation_errors.append("Numéro de téléphone trop court")

        # Validation SIRET basique
        if normalized_data['siret']:
            siret_clean = re.sub(r'[^\d]', '', normalized_data['siret'])
            if len(siret_clean) != 14:
                validation_errors.append("Le SIRET doit contenir exactement 14 chiffres")

        if validation_errors:
            return {
                'success': False,
                'error': 'Données invalides',
                'message': 'Veuillez corriger les erreurs suivantes',
                'validation_errors': validation_errors
            }

        # Créer le client directement dans Salesforce (bypass de la recherche API)
        creation_result = await workflow.create_client_in_salesforce(normalized_data)

        if creation_result.get('success'):
            return {
                'success': True,
                'type': 'client_created_manual',
                'message': 'Client créé avec succès (saisie manuelle)',
                'client_data': normalized_data,
                'client_id': creation_result.get('client_id'),
                'account_number': creation_result.get('account_number'),
                'validation_note': 'Client créé sans validation API externe'
            }
        else:
            return {
                'success': False,
                'error': creation_result.get('error', 'Erreur inconnue'),
                'message': creation_result.get('message', 'Erreur lors de la création du client')
            }

    except Exception as e:
        logger.error(f"Erreur création client manuelle: {e}")
        return {
            'success': False,
            'error': str(e),
            'message': f"Erreur lors de la création manuelle: {str(e)}"
        }

def detect_workflow_request(message: str) -> bool:
    """Détecte si un message nécessite le workflow (devis OU recherche produit)"""
    message_lower = message.lower()
    
    # Mots-clés pour les DEVIS
    quote_triggers = [
        'devis pour', 'créer un devis', 'faire un devis', 'je veux un devis',
        'quote for', 'create quote', 'quotation for',
        'commande pour', 'commander', 'acheter',
        'prix pour', 'tarif pour'
    ]
    
    # 🆕 NOUVEAUX : Mots-clés pour RECHERCHE PRODUIT
    search_triggers = [
        'je cherche', 'recherche', 'trouve', 'trouver',
        'imprimante', 'ordinateur', 'scanner', 'écran',
        'laser', 'jet d\'encre', 'recto-verso', 'réseau',
        'ppm', 'caractéristiques', 'spécifications'
    ]
    
    # Vérifier si le message contient une demande
    has_quote_trigger = any(trigger in message_lower for trigger in quote_triggers)
    has_search_trigger = any(trigger in message_lower for trigger in search_triggers)
    
    # Vérifier qu'il y a du contexte
    has_context = any(keyword in message_lower for keyword in [
        'avec', 'pour', 'de', 'ref', 'prod', 'article', 'quantité', 'unité', 
        'corp', 'company', 'client', 'laser', 'réseau', 'ppm'
    ])
    
    return (has_quote_trigger or has_search_trigger) and has_context
@router.post("/assistant/continue_workflow")
async def continue_workflow_with_choice(request: Request):
    """Continuer workflow après choix utilisateur"""

    data = await request.json()
    task_id = data.get("task_id")
    choice_type = data.get("choice_type")

    # Récupérer contexte workflow
    context = get_workflow_context(task_id)
    workflow = DevisWorkflow(task_id=task_id, force_production=True)

    if choice_type == "client_selected":
        client_data = data.get("client_data")
        return await workflow.handle_client_selection_and_continue(client_data, context)

    elif choice_type == "product_selected":
        product_choices = data.get("products")
        return await workflow.apply_product_choices(product_choices, context)

# Modèle pour la compatibilité avec le frontend existant
class GenerateQuoteRequest(BaseModel):
    prompt: str
    draft_mode: Optional[bool] = False
    force_production: Optional[bool] = False  # Nouveau paramètre pour forcer la production

class GenerateQuoteResponse(BaseModel):
    status: Optional[str] = None
    success: Optional[bool] = None
    client: Optional[Dict[str, Any]] = None
    products: Optional[List[Dict[str, Any]]] = None
    total_amount: Optional[float] = None
    quote_id: Optional[str] = None
    stock_info: Optional[str] = None
    error: Optional[str] = None
    message: Optional[str] = None
    similar_clients: Optional[List[Dict[str, Any]]] = None

@router.post('/generate_quote', response_model=GenerateQuoteResponse)
async def generate_quote_endpoint(request: GenerateQuoteRequest):
    """
    🎯 Endpoint de compatibilité pour le frontend existant
    Transforme les demandes de devis en format compatible avec l'interface
    """
    try:
        user_message = request.prompt.strip()

        if not user_message:
            return GenerateQuoteResponse(
                success=False,
                error="Message vide"
            )

        logger.info(f"🎯 Demande de devis via /generate_quote: {user_message}")

        # Utiliser la logique existante du workflow
        from workflow.devis_workflow import DevisWorkflow

        # Mode draft ou production selon la demande
        workflow = DevisWorkflow(
            validation_enabled=True,
            draft_mode=request.draft_mode,
            force_production=request.force_production  # Utiliser le paramètre de la requête
        )

        # Exécuter le workflow avec le message complet
        workflow_result = await workflow.process_prompt(user_message)

        if workflow_result.get('success'):
            # Extraire les données pour le format frontend
            client_data = workflow_result.get('client', {})
            products_data = workflow_result.get('products', [])

            # Formater les produits pour le frontend
            formatted_products = []
            for product in products_data:
                formatted_products.append({
                    'item_code': product.get('code', product.get('item_code', '')),
                    'code': product.get('code', product.get('item_code', '')),
                    'item_name': product.get('name', product.get('item_name', '')),
                    'name': product.get('name', product.get('item_name', '')),
                    'quantity': product.get('quantity', 1),
                    'unit_price': product.get('price', product.get('unit_price', 0)),
                    'line_total': product.get('line_total', product.get('quantity', 1) * product.get('price', product.get('unit_price', 0)))
                })

            return GenerateQuoteResponse(
                status='success',
                success=True,
                client={
                    'name': client_data.get('name', 'Client non spécifié'),
                    'account_number': client_data.get('account_number', client_data.get('id', ''))
                },
                products=formatted_products,
                total_amount=workflow_result.get('total_amount', 0),
                quote_id=workflow_result.get('quote_id', 'N/A'),
                stock_info=workflow_result.get('stock_info'),
                similar_clients=workflow_result.get('similar_clients', [])
            )
        else:
            # En cas d'échec, retourner les détails de l'erreur
            error_message = workflow_result.get('message', 'Erreur lors de la génération du devis')

            # Si des clients similaires ont été trouvés, les inclure dans la réponse
            similar_clients = workflow_result.get('similar_clients', [])

            return GenerateQuoteResponse(
                success=False,
                error=error_message,
                message=error_message,
                similar_clients=similar_clients
            )

    except Exception as e:
        logger.error(f"Erreur dans generate_quote_endpoint: {e}")
        return GenerateQuoteResponse(
            success=False,
            error=f"Erreur interne: {str(e)}"
        )
