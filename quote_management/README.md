# Gestionnaire de Devis SAP/Salesforce

## 🎯 Objectif

Ce module permet de gérer et synchroniser les devis entre SAP Business One et Salesforce. Il offre une vue unifiée des devis présents dans les deux systèmes et permet de détecter et corriger les incohérences.

## ✨ Fonctionnalités

- **Vue unifiée** : Affichage des devis présents dans SAP et/ou Salesforce
- **Détection des différences** : Identification des incohérences entre les deux systèmes
- **Suppression en masse** : Possibilité de supprimer plusieurs devis à la fois
- **Filtrage intelligent** : Filtrage par période et statut
- **Statistiques en temps réel** : Vue d'ensemble des devis par statut

## 📁 Structure du module

```
quote_management/
├── quote_manager.py          # Logique métier principale
├── api_routes.py            # Routes API FastAPI
├── quote_management_interface.html  # Interface web
├── setup_integration.py     # Script d'aide à l'intégration
└── README.md               # Ce fichier
```

## 🚀 Installation

### 1. Intégration dans l'application principale

Ajouter dans `main.py` :

```python
# Import des routes
from quote_management.api_routes import router as quote_management_router

# Ajouter le router
app.include_router(quote_management_router)

# Route pour l'interface
@app.get("/quote-management")
async def quote_management_interface():
    return FileResponse("quote_management/quote_management_interface.html")
```

### 2. Ajouter la fonction de suppression dans Salesforce

Dans `salesforce_mcp.py`, ajouter :

```python
@mcp.tool(name="salesforce_delete_record")
async def salesforce_delete_record(sobject: str, record_id: str) -> Dict[str, Any]:
    """
    Supprime un enregistrement Salesforce
    """
    try:
        sf_client = get_salesforce_client()
        
        # Effectuer la suppression
        result = getattr(sf_client, sobject).delete(record_id)
        
        return {
            "success": True,
            "message": f"Enregistrement {record_id} supprimé avec succès"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Erreur lors de la suppression: {str(e)}"
        }
```

## 🖥️ Utilisation

### Interface Web

Accéder à : `http://localhost:8000/quote-management`

### API REST

#### Lister les devis
```bash
GET /api/quote-management/quotes?days_back=30&status_filter=only_sap
```

#### Supprimer des devis
```bash
POST /api/quote-management/quotes/delete
{
    "quotes": [
        {"sap_doc_entry": "123", "sf_opportunity_id": "456"}
    ]
}
```

#### Statistiques
```bash
GET /api/quote-management/quotes/stats?days_back=30
```

## 📊 Statuts des devis

- **Synchronisé** (vert) : Présent dans les deux systèmes et cohérent
- **SAP uniquement** (orange) : Présent uniquement dans SAP
- **Salesforce uniquement** (bleu) : Présent uniquement dans Salesforce
- **Avec différences** (rouge) : Présent dans les deux mais avec des incohérences

## ⚙️ Configuration

Le module utilise les configurations existantes de `MCPConnector` pour se connecter à SAP et Salesforce.

## ⚠️ Notes importantes

1. **Suppression SAP** : Dans SAP B1, les devis ne peuvent pas être supprimés mais seulement annulés
2. **Permissions** : Assurez-vous que les utilisateurs API ont les permissions de suppression
3. **Sauvegarde** : Il est recommandé de faire des sauvegardes avant les suppressions en masse

## 🐛 Dépannage

### Les devis ne se chargent pas
- Vérifier que les services MCP SAP et Salesforce sont actifs
- Vérifier les logs dans la console du serveur

### Erreur lors de la suppression
- Vérifier les permissions de l'utilisateur API
- Vérifier que le devis n'est pas lié à d'autres documents

## 📝 Améliorations futures

- [ ] Export CSV/Excel des devis
- [ ] Historique des suppressions
- [ ] Synchronisation automatique programmée
- [ ] Notifications des incohérences
- [ ] Restauration des devis supprimés