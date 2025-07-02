#!/usr/bin/env python3
"""
Script pour corriger automatiquement les problèmes d'affichage dans l'interface NOVA
"""

import re
import shutil
from datetime import datetime

def apply_fixes():
    """Appliquer les corrections à routes_intelligent_assistant.py"""
    
    file_path = "routes/routes_intelligent_assistant.py"
    backup_path = f"routes/routes_intelligent_assistant.py.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # Faire une sauvegarde
    print(f"📁 Création de la sauvegarde : {backup_path}")
    shutil.copy2(file_path, backup_path)
    
    # Lire le fichier
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Correction 1: loadClientsList
    print("🔧 Correction de loadClientsList...")
    
    # Pattern pour trouver la fonction loadClientsList
    pattern_clients = r'async function loadClientsList\(\) \{[\s\S]*?\n\s*\}'
    
    new_clients_function = '''async function loadClientsList() {
    addMessage('user', 'Voir tous les clients');
    showTypingIndicator();
    
    try {
        const response = await fetch('/api/assistant/clients/list');
        const data = await response.json();
        
        hideTypingIndicator();
        
        if (data.success && data.clients && data.clients.length > 0) {
            let clientsMessage = data.message + '\\n\\n';
            
            data.clients.slice(0, 15).forEach((client, index) => {
                // Utiliser Name avec majuscule (format Salesforce)
                const clientName = client.Name || client.name || 'Client sans nom';
                clientsMessage += `**${index + 1}. ${clientName}**\\n`;
                if (client.Type) clientsMessage += `   🏢 Type: ${client.Type}\\n`;
                if (client.Industry) clientsMessage += `   🏭 Secteur: ${client.Industry}\\n`;
                if (client.Phone) clientsMessage += `   📞 Tél: ${client.Phone}\\n`;
                clientsMessage += `\\n`;
            });
            
            if (data.clients.length > 15) {
                clientsMessage += `... et ${data.clients.length - 15} autres clients.\\n\\n`;
            }
            
            clientsMessage += `💡 **Astuce**: Tapez le nom d'un client pour le rechercher spécifiquement.`;
            
            addMessage('nova', clientsMessage);
            
            const clientActions = [
                { label: '🔍 Rechercher client', action: 'search_client', type: 'primary' },
                { label: '➕ Nouveau client', action: 'new_client', type: 'secondary' },
                { label: '📋 Créer devis', action: 'start_workflow', type: 'info' }
            ];
            
            addMessage('nova', '🎯 **Actions disponibles :**', [], clientActions);
            
        } else {
            addMessage('nova', data.message || '👥 Aucun client trouvé dans la base de données.');
        }
        
    } catch (error) {
        hideTypingIndicator();
        addMessage('nova', '❌ Erreur lors du chargement des clients. Veuillez réessayer.');
        console.error('Erreur chargement clients:', error);
    }
}'''
    
    # Remplacer la fonction
    if re.search(pattern_clients, content):
        content = re.sub(pattern_clients, new_clients_function, content)
        print("✅ loadClientsList corrigée")
    else:
        print("⚠️ Pattern loadClientsList non trouvé")
    
    # Correction 2: loadProductsList
    print("🔧 Correction de loadProductsList...")
    
    pattern_products = r'async function loadProductsList\(\) \{[\s\S]*?\n\s*\}'
    
    new_products_function = '''async function loadProductsList() {
    addMessage('user', 'Voir tous les produits');
    showTypingIndicator();
    
    try {
        const response = await fetch('/api/assistant/products/list');
        const data = await response.json();
        
        hideTypingIndicator();
        
        if (data.success && data.products && data.products.length > 0) {
            let productsMessage = data.message + '\\n\\n';
            
            data.products.slice(0, 10).forEach((product, index) => {
                // Utiliser item_code et item_name (format SAP)
                const productCode = product.item_code || product.ItemCode || '';
                const productName = product.item_name || product.ItemName || 'Sans nom';
                const stock = product.stock || 0;
                const price = product.price || 0;
                
                productsMessage += `**${index + 1}. ${productCode} - ${productName}**\\n`;
                productsMessage += `   📦 Stock: ${stock} unités\\n`;
                productsMessage += `   💰 Prix: ${price}€ HT\\n\\n`;
            });
            
            if (data.products.length > 10) {
                productsMessage += `... et ${data.products.length - 10} autres produits.\\n\\n`;
            }
            
            productsMessage += `💡 **Astuce**: Tapez le nom ou la référence d'un produit pour le rechercher spécifiquement.`;
            
            addMessage('nova', productsMessage);
        } else {
            addMessage('nova', '📦 Aucun produit trouvé dans le catalogue.');
        }
        
    } catch (error) {
        hideTypingIndicator();
        addMessage('nova', '❌ Erreur lors de la recherche de produits. Veuillez réessayer.');
        console.error('Erreur recherche produits:', error);
    }
}'''
    
    # Remplacer la fonction
    if re.search(pattern_products, content):
        content = re.sub(pattern_products, new_products_function, content)
        print("✅ loadProductsList corrigée")
    else:
        print("⚠️ Pattern loadProductsList non trouvé")
    
    # Sauvegarder les modifications
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("\n✅ Corrections appliquées avec succès !")
    print("📌 Sauvegarde créée : " + backup_path)
    print("\n🔄 Redémarrez le serveur pour appliquer les changements :")
    print("   uvicorn main:app --reload --host 0.0.0.0 --port 8000")

if __name__ == "__main__":
    try:
        apply_fixes()
    except Exception as e:
        print(f"❌ Erreur : {str(e)}")
        print("\n💡 Appliquez les corrections manuellement dans routes/routes_intelligent_assistant.py")