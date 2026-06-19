# Spécification de livraison — Déploiement RONDOT SAS

Référence devis : **D-2026-682** (signé « Bon pour accord » le 16/06/2026 par Hervé HUAN)
CGV applicables : IT SPIRIT du 12/06/2026, Titre II (Applications métier en abonnement)
Base de référence du code : clone local, commit `47d2ad4`

---

## MISSION (à exécuter)

Tu dois **implémenter** dans ce repository les trois lots décrits ci-dessous (Lot A, Lot B, Lot C).
Il ne s'agit PAS de seulement lister ou décrire les corrections : tu dois **appliquer les modifications directement dans les fichiers**, puis tester.

Le « format strict de correction » des instructions projet ne s'applique pas ici : il décrit comment présenter une correction, alors que la présente mission demande une mise en œuvre complète.

Procédure imposée pour chaque lot :

1. Ouvrir et analyser le code réel concerné (les numéros de ligne ci-dessous viennent du commit `47d2ad4` et doivent être re-vérifiés).
2. Vérifier qu'aucune fonction/classe à créer n'existe déjà sous un autre nom.
3. Appliquer les modifications dans les fichiers, sans renommer l'existant.
4. Lancer/écrire les tests, vérifier les incidences, corriger.
5. Faire un commit par lot avec un message explicite.

Traiter les lots dans l'ordre A → B → C. S'arrêter et demander un arbitrage uniquement sur les points marqués « à confirmer ».

## Avertissements à claude-code (serveur Server 2019)

- Les numéros de ligne ci-dessous proviennent du clone `47d2ad4`. **Re-vérifier chaque ancre** sur la copie serveur avant édition.
- **Ne renommer aucune** fonction, classe ou variable existante.
- **Pas d'emojis** dans le code (source d'erreur).
- Données réelles SAP / Salesforce uniquement (pas de mock, pas de mode démo).
- Tester chaque lot isolément et vérifier les incidences avant de passer au suivant.

---

## Lot A — Modèle IA : Mistral principal, Anthropic fallback, OpenAI exclu

Conformité devis : « Modèle IA utilisé au déploiement : Mistral AI ou Anthropic ».
Le routage LLM est dynamique en base PostgreSQL (`services/llm_router.py`), donc l'essentiel est de la configuration, pas du code.

### A.1 — Configuration en base (interface admin LLM)

Interface : `templates/admin_llm.html` (URL admin `nova-ctl-oox3euxg`).

- Créer/activer un provider **Mistral** :
  - `api_format = openai`
  - `base_url = https://api.mistral.ai/v1`
  - modèle = `mistral-large-latest` (résout `mistral-large-2512`, présent dans `services/llm_pricing.py`)
  - **priorité 0** (principal)
- Provider **Anthropic** : modèle `claude-sonnet-4-6`, **priorité 1** (fallback)
- Tout provider **OpenAI** : `is_active = false`

### A.2 — Variables d'environnement (.env serveur Rondot)

- **Supprimer / ne pas renseigner** `OPENAI_API_KEY` (raison ci-dessous).
- Ajouter `MISTRAL_API_KEY=...` et `MISTRAL_MODEL=mistral-large-latest`.
- Conserver `ANTHROPIC_API_KEY` et `ANTHROPIC_MODEL=claude-sonnet-4-6`.
- Documenter `MISTRAL_API_KEY` / `MISTRAL_MODEL` dans `.env.example` (zone lignes 18-25).

### A.3 — Durcissement du filet de secours (recommandé, à confirmer)

`services/llm_router.py::_load_chain_from_env` (l.102-127) ne s'active que si la config base est vide. Il construit aujourd'hui Anthropic(prio 0) puis OpenAI(prio 1) à partir des clés `.env`. Sans `OPENAI_API_KEY`, ce secours se réduit à Anthropic seul — déjà conforme au devis.

Option recommandée : réécrire `_load_chain_from_env` en **Mistral(prio 0) → Anthropic(prio 1)** (lecture de `MISTRAL_API_KEY` / `MISTRAL_MODEL`), pour que même le secours respecte « Mistral principal ». **Décision à confirmer** avant inclusion dans ce lot.

---

## Lot B — Compteur 50 devis / mois calendaire, blocage dur

Conformité devis : « Tarif pour 1 utilisateur / 50 devis ». CGV art. 16.3 : compteurs intégrés à l'Application faisant foi.

### B.1 — Table PostgreSQL

Dans `models/database_models.py` (modèle SQLAlchemy, `Base = declarative_base()` l.13) :

- Classe `QuoteUsageCounter(Base)`, `__tablename__ = 'quote_usage_counter'`
- Colonnes : `id` (PK), `society_id`, `period` (texte `'YYYY-MM'`), `count` (int, défaut 0), `max_quota` (int, défaut 50), `updated_at`
- Contrainte unique `(society_id, period)`
- Migration Alembic dans `alembic/versions`

### B.2 — Service partagé

Nouveau fichier `services/quote_quota_service.py` :

- `check_quota(society)` : lit/crée la ligne du mois courant ; si `count >= max_quota` → lève `QuotaDevisDepasse`.
- `increment(society)` : `count += 1` en transaction.

### B.3 — Branchement sur les deux chemins de création SAP

Appeler `check_quota` **avant** création, `increment` **après** obtention du `doc_entry` :

- `services/sap_quotation_service.py::SAPQuotationService.create_sales_quotation` (l.306) — flux principal `POST /api/sap/quotation`
- `services/sap_business_service.py::create_quotation` (l.646) — flux `routes/routes_sap_business.py`

### B.4 — Règles

- Comptage **uniquement sur création SAP réussie**. La prévisualisation `POST /api/sap/quotation/preview` (`routes/routes_sap_quotation.py`) n'est **pas** comptée.
- Code d'erreur `QUOTA_DEVIS_DEPASSE` renvoyé au front et affiché (ex. `mail-to-biz/src/components/QuoteValidation.tsx`).
- La `society` courante doit être dérivée de la session authentifiée (SAP company DB). Vérifier comment la propager jusqu'aux deux services.

---

## Lot C — Utilisateur(s) autorisé(s) : capacité + session unique

Conformité devis : « 1 utilisateur ». Licence nominative (CGV art. 12.2 « utilisateurs nommés »).
Principe : ne pas coder « exactement 1 » en dur, mais une **capacité paramétrable** d'utilisateurs autorisés par société. Pour RONDOT, capacité = 1.

### C.1 — Capacité d'utilisateurs autorisés (par société)

- Ajouter une capacité `max_users` par société (colonne sur la table `societies` de `auth/auth_db.py`, l.32, défaut 1 ; ou paramètre de configuration par société).
- `create_user` (`auth/auth_db.py` l.156) : avant l'INSERT, compter les `nova_users` actifs (`is_active = 1`) de la `society_id` ; si le total atteint `max_users` → refuser (exception / HTTP).
- `update_user` (l.200) : même garde lors d'une réactivation (`is_active = 1`) si la capacité est déjà atteinte.
- Seuls les utilisateurs **provisionnés et actifs** (présents dans `nova_users`) peuvent se connecter — déjà le cas via `auth/dependencies.py` l.77 (vérifier).

### C.2 — Session unique avec éviction (par utilisateur)

Au login (route appelant `auth/sap_session/store.py::create_session`, l.50) :

- Utiliser `count_active_sessions()` (`store.py` l.131, déjà existant).
- Si une session active existe déjà pour cet utilisateur → **évincer l'ancienne** via `delete_session` (`store.py` l.98), puis créer la nouvelle. (UX souple : la connexion la plus récente l'emporte.)
- Vérifier le point d'appel exact de `create_session` (`auth/sap_session/sap_auth_service.py` ou la route de login) sur le serveur.

---

## Récapitulatif des décisions validées

| Sujet | Décision |
|---|---|
| Modèle IA principal | Mistral (`mistral-large-latest`) |
| Modèle IA fallback | Anthropic (`claude-sonnet-4-6`) |
| OpenAI / GPT-4.1 | Exclu pour Rondot |
| Secours `_load_chain_from_env` | Réécriture Mistral→Anthropic recommandée, à confirmer |
| Compteur devis | 50 / mois calendaire, blocage dur au 51e |
| Comptage | Création SAP réussie uniquement (preview exclu) |
| Utilisateurs autorisés | Capacité paramétrable/société (RONDOT = 1) + session unique par utilisateur (éviction de l'ancienne) |
