# SYNTHÈSE - Développement POC Création de Clients avec Contrôle de Doublons

## CONTEXTE PROJET
**POC d'intégration LLM (Claude) - Salesforce - SAP**
- Objectif : Génération automatique de devis via langage naturel
- Workflow : Extraction besoins → Validation client → Récupération produits SAP → Création devis Salesforce
- **Problématique identifiée** : Besoin de créer des clients quand ils n'existent pas dans la base

## PÉRIMÈTRE GÉOGRAPHIQUE VALIDÉ
- **Marchés principaux** : France (🇫🇷) et USA (🇺🇸)
- **Marchés secondaires** : Royaume-Uni, Singapour
- **Focus développement** : France + USA prioritaires

## SPÉCIFICATIONS FONCTIONNELLES VALIDÉES

### **FRANCE 🇫🇷**
- ✅ **SIRET obligatoire** (contrôle unicité absolu)
- ✅ **API INSEE Sirene** pour validation + enrichissement
- ✅ **API Adresse gouv.fr** pour normalisation adresses
- ✅ **Enrichissement automatique** : secteur, adresse officielle, statut

### **USA 🇺🇸**
- ✅ **Nom + État + Code postal obligatoires**
- ✅ **EIN optionnel** (si disponible)
- ✅ **Pas d'API officielle** → Validation manuelle renforcée
- ✅ **Contrôle doublons par similarité**

### **CONTRÔLE DE DOUBLONS**
- ✅ **Seuil de similarité** : 80%
- ✅ **Algorithme** : Recherche floue nom + adresse
- ✅ **Action si doublon détecté** : Proposer mise à jour de l'existant
- ✅ **Ne pas créer de nouveau client** si doublon confirmé

## ARCHITECTURE TECHNIQUE À DÉVELOPPER

### **1. Services de base requis**
```
services/client_validator.py     # Validation SIRET + EIN
services/address_normalizer.py  # API Adresse gouv.fr
services/duplicate_detector.py  # Détection similarité 80%
services/client_enricher.py     # Enrichissement INSEE
```

### **2. Routes API à créer**
```
routes/routes_clients.py:
- POST /validate_client_data    # Validation avant création
- POST /create_client          # Création avec contrôles
- GET /search_clients          # Recherche + similarité
- PUT /update_client           # Mise à jour proposée
- GET /client_requirements     # Exigences par pays
```

### **3. Workflow technique validé**

**FRANCE :**
```
1. SIRET saisi → Validation API INSEE
2. Si valide → Enrichissement automatique
3. Normalisation adresse → API gouv.fr
4. Vérification doublons → Base existante
5. Si doublon > 80% → Proposition mise à jour
6. Validation utilisateur → Création/Mise à jour
```

**USA :**
```
1. Nom + État + CP → Validation format
2. Recherche similarité → Base existante  
3. Si similaire > 80% → Proposition mise à jour
4. EIN optionnel → Validation si fourni
5. Choix utilisateur → Création/Mise à jour
```

## INTÉGRATION DANS LE WORKFLOW EXISTANT

### **Point d'intégration**
- **Déclencheur** : Client non trouvé dans `workflow/devis_workflow.py`
- **Méthode existante** : `_validate_client()` 
- **Nouvelle logique** : Si client non trouvé → Processus création guidée

### **Expérience utilisateur**
```
Utilisateur saisit : "devis pour ABC Industries"
→ Client non trouvé
→ "Voulez-vous créer ce client ?"
→ Si France : "Quel est le SIRET ?"
→ Si USA : "Dans quel État ?"
→ Validation + proposition mise à jour si doublon
→ Création confirmée → Reprise workflow devis
```

## APIS EXTERNES À INTÉGRER

### **APIs officielles gratuites**
- **INSEE Sirene** : `api.insee.fr/entreprises/sirene/V3`
- **API Adresse** : `api-adresse.data.gouv.fr`

### **APIs optionnelles (enrichissement)**
- **Pappers.fr** : Données entreprises françaises enrichies
- **OpenCorporates** : Données internationales (payant)

## DÉPENDANCES TECHNIQUES
```python
# Nouvelles dépendances à ajouter
requirements.txt:
+ email-validator      # Validation emails
+ python-multipart    # Formulaires
+ fuzzywuzzy          # Similarité chaînes
+ python-Levenshtein  # Algorithme distance
+ requests-cache      # Cache API calls
```

## ORDRE DE DÉVELOPPEMENT RECOMMANDÉ

### **Phase 1 - Services de base**
1. `services/client_validator.py` → Validation SIRET
2. `services/address_normalizer.py` → API Adresse gouv.fr
3. Tests unitaires des services

### **Phase 2 - Détection doublons**
1. `services/duplicate_detector.py` → Algorithme similarité
2. Intégration avec bases Salesforce + SAP
3. Tests avec données réelles

### **Phase 3 - Routes et intégration**
1. `routes/routes_clients.py` → API complète
2. Intégration dans `workflow/devis_workflow.py`
3. Tests bout-en-bout

### **Phase 4 - Interface utilisateur**
1. Formulaires de création guidée
2. Interface validation doublons
3. Tests utilisateur final

---

**🎯 OBJECTIF FINAL** : Lors de la génération d'un devis, si le client n'existe pas, le système guide l'utilisateur pour créer proprement le client (France avec SIRET, USA avec validation renforcée) tout en évitant les doublons grâce au contrôle à 80% de similarité.

---

## Actions Complémentaires pour la Finalisation et l'Amélioration du POC

En complément du développement de la fonctionnalité de création de clients, voici d'autres actions identifiées pour stabiliser, améliorer et documenter le POC NOVA. Ces points sont principalement issus du document `Maj_PlanDetaillePoc.md`.

### 1. Stabilisation des Fondations
*   **Gestion de la Base de Données avec Alembic (MID-2)**:
    *   Objectif : S'assurer qu'Alembic est correctement synchronisé avec la base de données `nova_mcp_local` et gère le schéma.
    *   Actions :
        *   Vérifier l'état actuel des migrations et du schéma (par exemple, via `python tests/diagnostic_db.py`).
        *   Si nécessaire, générer une nouvelle migration (`python -m alembic revision --autogenerate -m "nom_migration"`) et l'appliquer (`python -m alembic upgrade head`), ou utiliser `python -m alembic stamp head` si la base est déjà à jour manuellement.
    *   *Note : Le README indique qu'Alembic est "stabilisé". Cette action vise à confirmer et formaliser cet état.*

### 2. Amélioration de la Robustesse et de la Maintenabilité
*   **Mise à Jour du README.md**:
    *   Objectif : Maintenir une documentation d'accueil précise et à jour.
    *   Actions :
        *   Confirmer que le README reflète bien votre rôle unique sur le projet (Philippe PEREZ, seul responsable).
        *   Vérifier l'exactitude des instructions d'installation et de démarrage, notamment concernant la base de données et Alembic.
        *   Ajuster la section "Statut global" et "Roadmap" du projet si besoin.
    *   *Note : Des modifications récentes ont été apportées au README.*

*   **Renforcement des Tests Unitaires (MID-8)**:
    *   Objectif : Augmenter la couverture de test pour fiabiliser les composants clés.
    *   Actions :
        *   Identifier les modules critiques nécessitant une meilleure couverture (ex: `services/llm_extractor.py`, `services/client_validator.py`, fonctions spécifiques dans `sap_mcp.py` et `salesforce_mcp.py`).
        *   Rédiger des tests unitaires pour ces composants, couvrant les cas d'usage principaux et les cas limites.
        *   Envisager l'utilisation de `pytest` pour une gestion optimisée des tests.

*   **Complétion de la Documentation Technique (CONNECT-8, LLM-5)**:
    *   Objectif : Fournir une documentation suffisante pour la compréhension et la maintenance des intégrations.
    *   Actions :
        *   **CONNECT-8 (Schémas SAP/Salesforce)**: Finaliser la documentation listant les principaux champs/objets SAP et Salesforce utilisés, leur mapping et leur rôle (état actuel: "En cours / À compléter").
        *   **LLM-5 (Prompts Claude)**: Documenter les prompts clés utilisés avec Claude, ainsi que la structure des données attendues et reçues.

*   **Homogénéisation de la Gestion des Erreurs (MID-7)**:
    *   Objectif : Simplifier le débogage et améliorer la prévisibilité des erreurs.
    *   Actions :
        *   Analyser la gestion actuelle des erreurs à travers le middleware.
        *   Standardiser les formats des réponses d'erreur des API.
        *   Uniformiser la manière dont les exceptions sont capturées et loguées.

### 3. Perspectives et Évolutions
*   **Planification des Aspects Infrastructure (INFRA-3, INFRA-5, INFRA-6)**:
    *   Objectif : Préparer le terrain pour un déploiement ou une évolution plus opérationnelle du POC.
    *   Actions (à planifier/exécuter) :
        *   **INFRA-3 (Déploiement MCP)**: Documenter précisément les étapes de déploiement de l'application sur le serveur OVH (état actuel: "À faire").
        *   **INFRA-5 (Monitoring)**: Définir et mettre en place des stratégies de monitoring de base pour l'application (état actuel: "À faire").
        *   **INFRA-6 (Sécurité Réseau)**: Réfléchir et implémenter des mesures de sécurité réseau de base pour l'environnement de déploiement (état actuel: "À faire").

---