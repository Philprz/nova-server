
# Synthèse - Intégration MCP dans le projet NOVA Middleware

## 1. Rôle principal du MCP

- MCP (Model Context Protocol) est une **interface standardisée** pour exposer des fonctions Python comme **outils utilisables par Claude Desktop**.
- Il permet à Claude d'exécuter dynamiquement du code métier (`@tool`) en réponse à des prompts, sans intervention manuelle.
- Il agit comme un **pont sécurisé** entre Claude et ton code, sans gérer la logique métier lui-même.

---

## 2. Fonctionnement dans NOVA

- Le fichier `server_mcp.py` lance le serveur MCP avec `FastMCP` (via `stdio`).
- Les outils exposés (dans `tools.py` ou `exploration_*.py`) sont automatiquement détectés grâce à `server.yaml`.
- Claude peut appeler :
  - `salesforce.query` : requêtes SOQL
  - `sap.read` : lecture REST SAP B1
  - `sap.inspect`, `sap.refresh_metadata`
  - `salesforce.inspect`, `salesforce.refresh_metadata`

---

## 3. Exemple concret

**Prompt utilisateur Claude** :
> "Quels sont les 5 clients les plus récents et les produits SAP qu’ils ont commandés ?"

**Claude exécute** :
1. `salesforce.query(...)` pour récupérer les comptes récents
2. `sap.read(...)` pour lire les commandes liées à ces comptes
3. Synthèse automatique de la réponse

Cela se fait **sans code manuel**, Claude utilise les fonctions Python comme des plugins.

---

## 4. Découverte des champs SAP

Claude **ne connaît pas nativement** les champs SAP comme `ItemCode`, `ItemName`, etc.  
Il faut lui fournir des outils pour **découvrir dynamiquement la structure des données** :

- `sap.inspect()` → lit le cache `metadata_sap.json`
- `sap.refresh_metadata()` → appelle `/metadata` ou fallback manuel (`/Items`, `/Orders`, etc.)
- Pareil pour Salesforce avec `salesforce.inspect()` et `salesforce.refresh_metadata()`

Cela permet à Claude d’être **autonome dans la construction des requêtes**.

---

## 5. Connexion à JIRA, Zendesk, Confluence (à implémenter)

Tu peux appliquer la même logique pour enrichir Claude :

- Exposer des outils MCP :
  - `jira.search`, `jira.stats`, `jira.create_ticket`
  - `zendesk.query`
  - `confluence.search`, `confluence.get_page`
- Claude pourra :
  - explorer l’historique des tickets,
  - croiser avec la documentation technique,
  - fournir des solutions ou créer des tâches automatiquement.

---

## 6. Bénéfices globaux

- Tu rends Claude **intelligent et opérationnel dans ton contexte métier**.
- Tu construis un **assistant autonome** capable de :
  - Lire de la data (Salesforce, SAP, JIRA…)
  - Diagnostiquer des problèmes
  - Rechercher dans des bases de connaissances
  - Proposer ou exécuter des actions

---

## Prochaines étapes recommandées

- Ajouter les outils MCP pour JIRA, Zendesk et Confluence
- Connecter Qdrant pour intégrer la documentation (SAP Help, guides internes)
- Uniformiser les outils d’exploration (`.inspect`, `.refresh_metadata`) sur toutes les sources
