"""
🤖 Routes pour l'Assistant Intelligent NOVA
==========================================

API conversationnelle qui transforme NOVA en collègue intelligent
capable de comprendre les demandes en langage naturel et proposer
des solutions proactives.
"""

from fastapi import APIRouter, HTTPException
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
try:
    from routes.routes_clients import get_clients_data
except ImportError:
    def get_clients_data():
        return {'clients': []}

try:
    from routes.routes_products import get_products_data
except ImportError:
    def get_products_data():
        return {'products': []}

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
        """Analyse l'intention de l'utilisateur"""
        message_lower = user_message.lower()
        
        # Patterns d'intention
        intent_patterns = {
            'create_quote': ['devis', 'créer', 'nouveau', 'génération', 'quote'],
            'find_client': ['client', 'chercher', 'trouver', 'recherche'],
            'find_product': ['produit', 'référence', 'article', 'stock'],
            'help': ['aide', 'help', 'comment', 'expliquer'],
            'status': ['statut', 'état', 'progression', 'avancement'],
            'greeting': ['bonjour', 'salut', 'hello', 'bonsoir']
        }
        
        detected_intents = []
        for intent, keywords in intent_patterns.items():
            if any(keyword in message_lower for keyword in keywords):
                detected_intents.append(intent)
        
        return {
            'primary_intent': detected_intents[0] if detected_intents else 'unknown',
            'all_intents': detected_intents,
            'confidence': 0.8 if detected_intents else 0.2,
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
    
    Analyse le message utilisateur et génère une réponse intelligente
    avec des suggestions proactives.
    """
    try:
        user_message = message_data.message.strip()
        
        if not user_message:
            raise HTTPException(status_code=400, detail="Message vide")
        
        # Analyser l'intention
        intent_analysis = conversation_manager.analyze_intent(user_message)
        
        # Générer la réponse selon l'intention
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
        workflow = DevisWorkflow(validation_enabled=True, draft_mode=False)
        
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
    """Gère l'intention de recherche de client"""
    
    client_names = entities.get('client_names', [])
    
    if not client_names:
        return {
            'type': 'client_search',
            'message': "🔍 **Recherche de client**\n\nPour quelle entreprise cherchez-vous ?\n\n💡 **Exemples :**\n• \"Chercher Edge Communications\"\n• \"Client Acme Corp\"\n• \"Entreprise Microsoft\"",
            'suggestions': [
                "Voir tous les clients",
                "Créer un nouveau client"
            ]
        }
    
    # Rechercher le client avec suggestions intelligentes
    try:
        clients_data = get_clients_data()
        if clients_data and 'clients' in clients_data:
            available_clients = clients_data['clients']
            
            search_results = []
            for client_name in client_names:
                suggestion_result = suggestion_engine.suggest_client(
                    client_name, available_clients
                )
                search_results.append({
                    'query': client_name,
                    'result': suggestion_result.to_dict()
                })
            
            # Construire la réponse
            response = {
                'type': 'client_search_results',
                'message': f"🔍 **Résultats pour '{client_names[0]}'**\n\n",
                'search_results': search_results,
                'suggestions': []
            }
            
            best_result = search_results[0]['result']
            if best_result['has_suggestions']:
                primary = best_result['primary_suggestion']
                response['message'] += f"✅ **Trouvé :** {primary['suggested_value']}\n"
                response['message'] += f"💡 {primary['explanation']}\n\n"
                
                # Ajouter les alternatives
                if best_result['all_suggestions']:
                    response['message'] += "🔄 **Autres options :**\n"
                    for i, alt in enumerate(best_result['all_suggestions'][:3], 1):
                        response['message'] += f"{i}. {alt['suggested_value']} (score: {alt['score']:.0%})\n"
                
                response['suggestions'] = [
                    f"Utiliser {primary['suggested_value']}",
                    "Voir toutes les options",
                    "Créer un nouveau devis"
                ]
            else:
                response['message'] += f"❌ **Client '{client_names[0]}' non trouvé**\n\n"
                response['message'] += "💡 **Options disponibles :**\n"
                response['message'] += f"1. Créer le client '{client_names[0]}'\n"
                response['message'] += "2. Voir tous les clients\n"
                response['message'] += "3. Essayer une autre recherche"
                
                response['suggestions'] = [
                    f"Créer {client_names[0]}",
                    "Voir tous les clients",
                    "Nouvelle recherche"
                ]
            
            return response
            
    except Exception as e:
        logger.error(f"Erreur recherche client: {e}")
        return {
            'type': 'error',
            'message': f"❌ **Erreur lors de la recherche**\n\n{str(e)}",
            'suggestions': ["Réessayer", "Voir tous les clients"]
        }

def handle_product_search_intent(message: str, entities: Dict[str, Any]) -> Dict[str, Any]:
    """Gère l'intention de recherche de produit"""
    
    product_refs = entities.get('product_refs', [])
    
    if not product_refs:
        return {
            'type': 'product_search',
            'message': "🔍 **Recherche de produit**\n\nQuelle référence cherchez-vous ?\n\n💡 **Exemples :**\n• \"Produit A00025\"\n• \"Référence B00150\"\n• \"Article C00300\"",
            'suggestions': [
                "Voir tous les produits",
                "Recherche par catégorie"
            ]
        }
    
    # Rechercher le produit avec suggestions intelligentes
    try:
        products_data = get_products_data()
        if products_data and 'products' in products_data:
            available_products = products_data['products']
            
            search_results = []
            for product_ref in product_refs:
                suggestion_result = suggestion_engine.suggest_product(
                    product_ref, available_products
                )
                search_results.append({
                    'query': product_ref,
                    'result': suggestion_result.to_dict()
                })
            
            # Construire la réponse
            response = {
                'type': 'product_search_results',
                'message': f"🔍 **Résultats pour '{product_refs[0]}'**\n\n",
                'search_results': search_results,
                'suggestions': []
            }
            
            best_result = search_results[0]['result']
            if best_result['has_suggestions']:
                primary = best_result['primary_suggestion']
                response['message'] += f"✅ **Trouvé :** {primary['suggested_value']}\n"
                response['message'] += f"💡 {primary['explanation']}\n\n"
                
                # Informations produit si disponibles
                if 'metadata' in primary and primary['metadata']:
                    metadata = primary['metadata']
                    if 'stock' in metadata:
                        response['message'] += f"📊 **Stock :** {metadata['stock']} unités\n"
                    if 'price' in metadata:
                        response['message'] += f"💰 **Prix :** {metadata['price']}€\n"
                
                response['suggestions'] = [
                    f"Ajouter {primary['suggested_value']} au devis",
                    "Voir les détails complets",
                    "Chercher des produits similaires"
                ]
            else:
                response['message'] += f"❌ **Produit '{product_refs[0]}' non trouvé**\n\n"
                response['message'] += "💡 **Suggestions :**\n"
                response['message'] += "1. Vérifier la référence\n"
                response['message'] += "2. Voir tous les produits\n"
                response['message'] += "3. Recherche par catégorie"
                
                response['suggestions'] = [
                    "Voir tous les produits",
                    "Recherche par nom",
                    "Aide sur les références"
                ]
            
            return response
            
    except Exception as e:
        logger.error(f"Erreur recherche produit: {e}")
        return {
            'type': 'error',
            'message': f"❌ **Erreur lors de la recherche**\n\n{str(e)}",
            'suggestions': ["Réessayer", "Voir tous les produits"]
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
        workflow = DevisWorkflow(validation_enabled=True, draft_mode=True)  # Mode draft pour éviter la création immédiate
        
        # Analyser le message pour extraire les informations
        message = message_data.message
        logger.info(f"Exécution du workflow pour: {message}")
        
        # Exécuter le workflow complet
        result = await workflow.process_prompt(message)
        
        # Analyser les résultats pour créer une réponse intelligente
        response = {
            'success': True,
            'workflow_status': 'completed',
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
