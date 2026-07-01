> OBSOLÈTE — état pré-fix (30/06). Toutes les routes citées sont corrigées depuis. Ne plus utiliser comme référence. Voir docs/AUDIT_PREPROD_2026-07.md.

# AUDIT — Routes montées cassées (symbole inexistant / crash garanti)

**Branche** : `prod/fix-broken-routes` · **Date** : 2026-06-30 · **Mode** : LECTURE SEULE (aucune correction)
**Périmètre** : les 24 routers montés via `include_router` dans `main.py` (lignes 297-332).
**Méthode** : lecture intégrale des 24 fichiers `routes/*.py`, énumération de chaque endpoint, résolution
repo-wide (`grep "def <nom>"` / `class` / import / assignation) de chaque appel de code applicatif
`obj.method(...)` et `name(...)`. Un symbole est déclaré CASSÉ uniquement si **aucune** définition
n'existe nulle part dans le dépôt.

> ⚠️ Hors périmètre (non montés dans `main.py`, donc non audités comme routes) : `routes/routes_products.py`,
> `routes/routes_sap_session.py`. `routes_products` est néanmoins importé indirectement (helpers) et ses
> symboles utilisés (`search_products_advanced`, etc.) ont été vérifiés présents.

---

## Réponse à la question « le scan a-t-il trouvé PLUS que les 3 cas connus ? »

**OUI.** Au-delà des 3 cas connus (`generate_devis`, `search_company_info`,
`create_client_from_company_data`), le scan a identifié **8 cassures supplémentaires à symbole inexistant**
(routes_devis ×1, routes_intelligent_assistant ×1, routes_progress ×3, routes_graph ×1, routes_sap_creation ×1,
routes_sap_business ×1), soit **11 cassures « symbole absent » au total**.
S'y ajoutent **1 finding adjacent** (TypeError garanti par mauvaise signature `call_sap(params=...)`, symbole
existant mais appel non valide — strictement hors « symbole inexistant » mais crash garanti sur chemin
atteignable) et **4 branches déjà neutralisées en 501** (rappelées mais non recomptées).

---

## Tableau de synthèse

| # | Classement | Route HTTP | Fichier:ligne | Symbole manquant | Objet/Classe | 500 réel ? |
|---|---|---|---|---|---|---|
| 1 | RENOMMAGE TRIVIAL | POST /api/devis/resolve_duplicates | routes_devis.py:150 | `generate_devis` | DevisWorkflow | Non (avalé → 200) |
| 2 | RENOMMAGE TRIVIAL | GET /api/sap/products/check-exists/{item_code} | routes_sap_creation.py:185 | `get_sap_service` (import) | module `services.sap` | Oui (500) |
| 3 | À VALIDER | POST /api/assistant/create_client/search | routes_intelligent_assistant.py:1595 | `search_company_info` | ClientCreationWorkflow | Non (avalé → 200) |
| 4 | À VALIDER | POST /api/assistant/create_client/confirm | routes_intelligent_assistant.py:1629 | `create_client_from_company_data` | ClientCreationWorkflow | Non (avalé → 200) |
| 5 | À VALIDER | POST /api/devis/api/quote/confirm | routes_devis.py:202/205 | `get_task_result` (import) | module `services.progress_tracker` | Non (avalé → 200) |
| 6 | À VALIDER | POST /api/assistant/search_clients | routes_intelligent_assistant.py:2028 | `search_contacts` | MCPConnector | Non (avalé → 200) |
| 7 | À VALIDER | GET /progress/tasks/active | routes_progress.py:131 | `get_active_tasks` | ProgressTracker | **Oui (500)** |
| 8 | À VALIDER | DELETE /progress/task/{task_id} | routes_progress.py:147 | `cancel_task` | ProgressTracker | **Oui (500)** |
| 9 | À VALIDER | GET /progress/stats | routes_progress.py:655 | `get_global_stats` | ProgressTracker | **Oui (500)** |
| 10 | À VALIDER | POST /api/graph/emails/{message_id}/products/{item_code}/manual-code | routes_graph.py:2317 | `add_mapping` | ProductMappingDB | Non (try/except, feature morte) |
| 11 | À VALIDER | POST /api/sap/quotations/from-email | routes_sap_business.py:577 | `ClientValidator.validate_and_enrich` | ClientValidator | Non (try/except, enrichissement mort) |
| A | ADJACENT (TypeError) | GET /api/sap/clients/check-exists/{card_name} + products/check-exists | routes_sap_creation.py:91,190 | `call_sap(params=...)` (signature) | module `services.sap` | Oui (500) |

> **Nuance importante** : 8 des 11 cassures sont avalées par un `try/except Exception` large et renvoient
> HTTP **200** `{"success": false, "error": "...<symbole>..."}`. La fonctionnalité est néanmoins
> **systématiquement non opérationnelle**. Seules #7/#8/#9 (routes_progress) et #2 + #A (routes_sap_creation)
> produisent un vrai HTTP **500**.

---

# DOSSIERS PAR CAS

## 🟢 RENOMMAGE TRIVIAL (méthode candidate à signature identique → quasi certain)

### Cas 1 — `generate_devis` → `process_prompt`  *(cas connu)*
- **Route** : `POST /api/devis/resolve_duplicates` (handler `resolve_duplicates`)
- **Appel cassé** : `routes/routes_devis.py:150` — `result = await workflow.generate_devis(original_prompt)`
- **Chaîne** : `resolve_duplicates` → branche `action == "create_new"` → `workflow = DevisWorkflow()` (l.146) → `workflow.generate_devis(original_prompt)`
- **Symbole manquant** : `generate_devis` (0 `def` repo-wide ; seule occurrence = ce site)
- **Candidate** : `async def process_prompt(self, user_prompt: str, task_id: str = None)` — `workflow/devis_workflow.py:1036`. **Signature compatible** (1 arg positionnel = le prompt). C'est le point d'entrée standard utilisé partout ailleurs.
- **Contrat consommateur** : `return {"success": True, "action": "created", "result": result}` — `result` est réemballé tel quel, **aucun champ lu** → bascule transparente.
- **Source de vérité** : tous les autres appels du workflow utilisent `process_prompt`.
- **❓ QUESTION** : Confirmer que `process_prompt(original_prompt)` est bien l'entrée voulue ici (le commentaire l.147-148 « désactiver la vérif doublons » via `workflow.skip_duplicate_check = True` est-il honoré par `process_prompt` ?).
- **Recommandation** : remplacer `generate_devis` → `process_prompt`. Quasi certain.

### Cas 2 — `get_sap_service` (import mort) → retrait du nom
- **Route** : `GET /api/sap/products/check-exists/{item_code}` (handler `check_product_exists`) — **et** propagé à `POST /api/sap/workflow/check-and-create-if-needed` (branche produit, l.337)
- **Appel cassé** : `routes/routes_sap_creation.py:185` — `from services.sap import get_sap_service, call_sap` puis `sap = get_sap_service()` (l.187)
- **Symbole manquant** : `get_sap_service` (`services/sap.py` ne définit QUE `login_sap` et `call_sap` ; 0 `def get_sap_service` repo-wide)
- **Candidate** : aucune nécessaire — `sap` (l.187) est **lié puis jamais utilisé** ; seul `call_sap(...)` (l.190) est réellement appelé.
- **Contrat consommateur** : néant (variable morte).
- **❓ QUESTION** : Confirmer que `sap = get_sap_service()` est bien du code mort (aucun usage de `sap` dans le handler) → simple suppression du nom dans l'import.
- **Recommandation** : `from services.sap import call_sap`. Fix d'un token. ⚠️ Attention : même après ce fix, la route reste cassée par le **Cas A** (`call_sap(params=...)`) — voir ci-dessous.

---

## 🟠 À VALIDER (contrat / arité / forme de retour à confirmer)

### Cas 3 — `search_company_info` sur ClientCreationWorkflow  *(cas connu)*
- **Route** : `POST /api/assistant/create_client/search` (handler `search_company_for_creation`)
- **Appel cassé** : `routes/routes_intelligent_assistant.py:1595` — `await workflow.search_company_info(request.company_name, request.city)` (`workflow = ClientCreationWorkflow()`, l.1592)
- **Symbole manquant** : `search_company_info` (0 `def` sur `ClientCreationWorkflow`). ⚠️ **Piège** : `_search_company_info` (avec underscore) existe mais sur **`DevisWorkflow`** (`devis_workflow.py:8454`), classe différente.
- **Candidate** : `async def search_company_by_name(self, company_name: str, city: str = None)` — `workflow/client_creation_workflow.py:29`. **Signature d'appel compatible** (company_name, city).
- **Contrat consommateur (chemin succès, l.1605-1608)** :
  ```python
  'search_results': search_results['search_results'],   # accès dur → KeyError si absent
  'recommended':    search_results.get('recommended'),
  'sources':        search_results.get('sources', []),
  len(search_results['search_results'])
  ```
- **MISMATCH DE FORME** : `search_company_by_name` **retourne** `{"success", "companies", "search_method", "message", "api_error"}` (vérifié `client_creation_workflow.py:35-79`). Il **n'y a ni `search_results`, ni `recommended`, ni `sources`**. Donc un simple renommage produit une **2ᵉ cassure** (`KeyError: 'search_results'` à la l.1605).
- **Source de vérité de la forme attendue** : aucune méthode du repo ne renvoie `{search_results, recommended, sources}`. La route sœur `/client/search` (l.1429) utilise le même backend `search_company_by_name` mais via le **singleton module** `client_creation_workflow` et renvoie `companies` directement.
- **❓ QUESTION** : Le client front attend-il la forme `{search_results, recommended, sources}` ou peut-on aligner la route sur `{companies, ...}` (comme `/client/search`) ? Faut-il (a) renommer + ré-écrire le mapping de sortie de la route, ou (b) créer un vrai `search_company_info` qui produit `{search_results, recommended, sources}` ?
- **Recommandation** : NE PAS faire un renommage sec. Décider du contrat de sortie d'abord (option a recommandée : réutiliser `search_company_by_name` et remapper `companies` → `search_results`).

### Cas 4 — `create_client_from_company_data` sur ClientCreationWorkflow  *(cas connu)*
- **Route** : `POST /api/assistant/create_client/confirm` (handler `create_client_from_company`)
- **Appel cassé** : `routes/routes_intelligent_assistant.py:1629` — `await workflow.create_client_from_company_data(request.company_data, request.contact_info)` (2 args)
- **Symbole manquant** : `create_client_from_company_data` (0 `def` repo-wide)
- **Candidates sur `ClientCreationWorkflow`** :
  - `async def create_client_in_salesforce(self, client_data: Dict)` (`:193`) — **arité 1** (le site passe **2** args : `company_data` + `contact_info`).
  - `async def process_client_creation_request(self, request_data: Dict)` (`:232`) — arité 1.
- **Contrat consommateur** : `return creation_result` brut (l.1634) → aucun champ lu côté route, transparent.
- **MISMATCH D'ARITÉ** : 2 args appelés vs 1 sur toutes les candidates. Que devient `contact_info` ? (fusion dans `company_data` ? ignoré ?)
- **❓ QUESTION** : `contact_info` doit-il être fusionné dans `company_data` avant `create_client_in_salesforce(client_data)`, ou faut-il une nouvelle méthode acceptant les 2 ? Le `company_data` issu du front est-il déjà au format attendu par `create_client_in_salesforce` ?
- **Recommandation** : probable `create_client_in_salesforce` après fusion `{**company_data, **(contact_info or {})}`, mais à confirmer (sémantique de `contact_info`).

### Cas 5 — `get_task_result` (import inexistant) — NOUVEAU
- **Route** : `POST /api/devis/api/quote/confirm` (handler `confirm_quote`) — chemin = préfixe `/api/devis` + path décoré `/api/quote/confirm`
- **Appel cassé** : `routes/routes_devis.py:202` (`from services.progress_tracker import get_task_result`) puis l.205 (`task_result = await get_task_result(request.task_id)`)
- **Symbole manquant** : `get_task_result` (les fonctions module-level de `progress_tracker.py` sont **uniquement** `get_or_create_task`:568, `track_workflow_step`:585, `get_workflow_progress`:606 ; 0 `get_task_result`)
- **Portée** : l'import est en tête de `try`, **avant** le branchement sur `request.action` → **les 3 actions** (`confirm`/`modify`/`cancel`) du endpoint sont cassées, même celles n'utilisant pas le tracker.
- **Candidates** :
  - `get_workflow_progress(task_id) -> Optional[Dict]` (module-level) — renvoie une vue progression, **pas garanti** d'exposer `context`.
  - `progress_tracker.get_task(task_id) -> Optional[QuoteTask]` — renvoie un **objet** `QuoteTask`, or le consommateur fait `task_result.get("context", {})` (l.218) → `QuoteTask` n'a pas `.get` → **2ᵉ cassure** si substitution naïve.
- **Contrat consommateur** : `if not task_result: erreur` (l.207-211) ; sinon action `confirm` → `workflow.context = task_result.get("context", {})` (l.218) puis `await workflow.create_quote_with_confirmation(confirmed=True)` (l.222, **méthode existante** `devis_workflow.py:1740`).
- **❓ QUESTION** : Quelle est la source du `context` d'une tâche confirmée — un dict persistant (clé `context`) ou l'objet `QuoteTask` ? Faut-il (a) ajouter `get_task_result(task_id)` renvoyant un dict `{context: ...}`, ou (b) remplacer par `get_task()` + lire `task.context` (attribut) au lieu de `.get("context")` ?
- **Recommandation** : pas de candidate de forme identique → définir le contrat avant fix. Probable option (b) avec adaptation du consommateur.

### Cas 6 — `search_contacts` sur MCPConnector — NOUVEAU
- **Route** : `POST /api/assistant/search_clients` (handler `search_clients_direct`)
- **Appel cassé** : `routes/routes_intelligent_assistant.py:2028` — `clients = await mcp.search_contacts(client_name)` (`mcp = MCPConnector()`, l.2022)
- **Symbole manquant** : `search_contacts` (0 `def` repo-wide ; seule occurrence = ce site)
- **Atteignabilité** : conditionnelle — précédé de `await mcp.test_connections()` (l.2024, existante) ; l'appel cassé n'est atteint que si `overall_status == "OK"`. Sur le chemin nominal « connexions OK » la cassure est **garantie**.
- **Candidates** :
  - `async def search_salesforce_accounts(self, query: str)` (`mcp_connector.py:834`) — la plus proche (client = Account).
  - `async def search_sap_items(self, query: str)` (`:911`), `search_salesforce_opportunities(filters)` (`:857`).
- **Contrat consommateur** : `if clients:` → `{"success": True, "requires_selection": True, "clients": clients, "message": f"{len(clients)} client(s)..."}`. `clients` est traité comme une **séquence** (`len`, truthiness). Or `search_salesforce_accounts` renvoie un **Dict** (vraisemblablement `{records: [...]}`) → `len()` compterait les clés → sémantique fausse, adaptation requise (`clients = result.get("records", [])`).
- **❓ QUESTION** : Le besoin est-il de chercher des comptes Salesforce (Accounts) ? Si oui, la sortie de `search_salesforce_accounts` expose-t-elle `records` (liste) à passer au front, ou faut-il un autre format ?
- **Recommandation** : `search_salesforce_accounts` + extraire la liste (`records`) avant `len()`/retour. À valider (forme du retour).

### Cas 7 — `progress_tracker.get_active_tasks()` — NOUVEAU
- **Route** : `GET /progress/tasks/active` (handler `get_active_tasks`)
- **Appel cassé** : `routes/routes_progress.py:131`
- **Symbole manquant** : `get_active_tasks` sur `ProgressTracker` (`services/progress_tracker.py:338`). Pas de `__getattr__` → AttributeError ; `except` re-lève **HTTP 500**.
- **Candidate** : `def get_all_active_tasks(self) -> List[Dict[str, Any]]` (`:476`). **MAIS** elle renvoie déjà une **liste de dicts** (= `task.get_overall_progress()` par tâche), alors que le consommateur fait `[task.get_overall_progress() for task in active_tasks]` (l.134) → sur un dict, `.get_overall_progress()` → **2ᵉ crash**.
- **Contrat consommateur** : `{"count": len(active_tasks), "tasks": [task.get_overall_progress() for task in active_tasks]}`.
- **❓ QUESTION** : Renommer `get_active_tasks`→`get_all_active_tasks` **et** supprimer la compréhension (renvoyer la liste directement sous `tasks`) — confirmer que `get_all_active_tasks()` produit déjà la forme par-tâche attendue par le front ?
- **Recommandation** : renommer + retirer le `.get_overall_progress()` aval (`"tasks": active_tasks`). Pas un renommage sec.

### Cas 8 — `progress_tracker.cancel_task(task_id)` — NOUVEAU
- **Route** : `DELETE /progress/task/{task_id}` (handler `cancel_task`)
- **Appel cassé** : `routes/routes_progress.py:147` — `success = progress_tracker.cancel_task(task_id)`
- **Symbole manquant** : `cancel_task` sur `ProgressTracker` (0 `def`). AttributeError → **HTTP 500**.
- **Candidate** : pas de méthode « cancel » bool. La plus proche `fail_task(self, task_id, error)` (`:444`) **renvoie `None`** → `if not success:` toujours vrai → **404 permanent** même après renommage ; sémantique = FAILED, pas CANCELLED.
- **Référence** : l'endpoint sœur `DELETE /progress/cancel_quote/{task_id}` (l.848) fait, lui, `progress_tracker.fail_task(task_id, "Annulé par l'utilisateur")` après contrôle de `task.status` — pattern fonctionnel à imiter.
- **Contrat consommateur** : `if not success: 404` ; sinon `{"success": True, "message": ...}` → attend un **booléen**.
- **❓ QUESTION** : Cet endpoint fait-il doublon avec `/progress/cancel_quote/{task_id}` (à retirer/rediriger), ou faut-il une vraie méthode `cancel_task` renvoyant un bool (s'appuyant sur `get_task` + `fail_task`) ?
- **Recommandation** : soit aligner sur le pattern `cancel_quote` (get_task → fail_task → bool), soit retirer le endpoint s'il est redondant. À valider.

### Cas 9 — `progress_tracker.get_global_stats()` — NOUVEAU
- **Route** : `GET /progress/stats` (handler `get_progress_stats`)
- **Appel cassé** : `routes/routes_progress.py:655` — `stats = progress_tracker.get_global_stats()`
- **Symbole manquant** : `get_global_stats` (0 `def`). AttributeError → **HTTP 500**.
- **Candidate** : `def get_task_statistics(self) -> Dict` (`:510`). Renvoie `{active_tasks, completed_tasks, successful_tasks, failed_tasks, success_rate, total_tasks_processed}`.
- **Contrat consommateur** : lit `active_tasks`, `completed_tasks`, `failed_tasks`, `total_tasks`, `average_duration`, `success_rate`. → **`total_tasks`** absent (réel : `total_tasks_processed`) et **`average_duration`** non produit → après renommage, ces 2 `.get(...)` retournent 0 silencieusement (données fausses, pas de crash).
- **Note** : il existe un endpoint distinct fonctionnel `GET /progress/progress_stats` (l.930) qui calcule les stats en ligne sans le tracker (doublon de nom de fonction `get_progress_stats`, la 2ᵉ def écrase la 1ʳᵉ à l'import mais les 2 routes coexistent sur des paths différents).
- **❓ QUESTION** : Faut-il (a) renommer vers `get_task_statistics` + mapper les clés (`total_tasks_processed`→`total_tasks`, ajouter `average_duration`), ou (b) retirer `/progress/stats` au profit de `/progress/progress_stats` ?
- **Recommandation** : décider entre mapping de clés ou retrait du doublon. À valider.

### Cas 10 — `ProductMappingDB.add_mapping(...)` — NOUVEAU (avalé, feature morte)
- **Route** : `POST /api/graph/emails/{message_id}/products/{item_code}/manual-code` (handler `set_manual_product_code`)
- **Appel cassé** : `routes/routes_graph.py:2317` — `mapping_db.add_mapping(external_code=..., sap_code=..., source="manual_user_input", confidence=1.0)`
- **Symbole manquant** : `add_mapping` sur `ProductMappingDB` (`services/product_mapping_db.py:15`). 0 `def` repo-wide.
- **Atteignabilité** : reachable (toute soumission de code manuel validé SAP) **mais enveloppé** dans `try: ... except Exception as e: logger.warning("Could not save mapping (non-critical)")` (l.2314-2325). L'AttributeError est avalé → **pas de 500** ; la route renvoie 200.
- **Candidate** : `def save_mapping(self, external_code, external_description, supplier_card_code, matched_item_code=None, match_method="PENDING", confidence_score=0.0, status="PENDING")` (`:144`). **Signature très différente** : le site passe `sap_code=`, `source=`, `confidence=` (kwargs inexistants) et omet les requis `external_description`, `supplier_card_code` → un renommage sec lèverait un `TypeError`.
- **Contrat consommateur** : aucune valeur de retour lue (effet de bord « apprentissage » du mapping). ⚠️ Le champ `mapping_saved: True` de la réponse 200 (l.2404) est donc **toujours mensonger** (le mapping n'est jamais enregistré).
- **Sources de vérité** : `save_mapping` est le seul point d'insertion. Mapping requis : `sap_code`→`matched_item_code`, `confidence`(0-1.0)→`confidence_score`(0-100 ?), `source`→`match_method`/`status`, fournir `external_description` + `supplier_card_code`.
- **❓ QUESTION** : Quelles valeurs pour `external_description` et `supplier_card_code` (non disponibles au site d'appel ?) et quelle échelle pour `confidence_score` (0-1 ou 0-100) ? Préfère-t-on ajouter un vrai `add_mapping` (wrapper) ou adapter l'appel à `save_mapping` ?
- **Recommandation** : adapter vers `save_mapping` avec remappage d'arguments (ou wrapper `add_mapping`). À valider (champs requis manquants). Priorité moindre (pas d'outage), mais corrige le `mapping_saved` mensonger.

### Cas 11 — `ClientValidator.validate_and_enrich(...)` — NOUVEAU (avalé)
- **Route** : `POST /api/sap/quotations/from-email` (handler `create_quotation_from_email`)
- **Appel cassé** : `routes/routes_sap_business.py:577` — `validation_result = await validator.validate_and_enrich(client_data_for_validation)` (`validator = ClientValidator()`, l.573)
- **Symbole manquant** : `validate_and_enrich` sur `ClientValidator` (`services/client_validator.py:45`). 0 `def` repo-wide.
- **Atteignabilité** : **conditionnelle** — seulement si (a) client absent (`search_business_partner` vide) ET (b) `extracted_data["siret"]` truthy. Atteint → AttributeError, mais **avalé** par `try/except` (l.572/591 « continuant avec données partielles ») → pas de 500, enrichissement silencieusement sauté.
- **Candidates (signature = 1 arg, compatible)** :
  - `async def validate_client_data_enriched(self, client_data: Dict)` (`:766`) — nom/intention les plus proches.
  - `async def validate_complete(self, client_data: Dict, country: str = "FR")` (`:178`).
- **Contrat consommateur (l.579-608)** : `validation_result.get("valid")` puis `validation_result.get("enriched_data", {})` → champs `numero_tva_intra`, `forme_juridique`, `denomination`, `telephone`, `siret`, `adresse_ligne_1`, `ville`, `code_postal`, `code_pays`, `capital`.
- **❓ QUESTION** : Laquelle de `validate_client_data_enriched` / `validate_complete` renvoie bien un dict exposant `valid` **et** `enriched_data{...}` avec ces clés exactes ? (à confirmer en lisant le `return` de la candidate retenue).
- **Recommandation** : probable `validate_client_data_enriched` (arité compatible), mais **vérifier la forme de retour** (`valid` + `enriched_data` + clés) avant de trancher renommage vs adaptation. → À valider.

---

## 🔵 ADJACENT — crash garanti hors « symbole inexistant » (TypeError de signature)

### Cas A — `call_sap(..., params=...)` : kwarg inexistant
- **Routes** : `GET /api/sap/clients/check-exists/{card_name}` (handler `check_client_exists`, appel l.91-98) **et** `GET /api/sap/products/check-exists/{item_code}` (handler `check_product_exists`, appel l.190-193) ; propagé à `POST /api/sap/workflow/check-and-create-if-needed` (branches client l.309 / produit l.337).
- **Problème** : appels `await call_sap(endpoint=..., params={...})` alors que `services/sap.py:46` définit `async def call_sap(endpoint, method="GET", payload=None)` — **aucun paramètre `params`**, pas de `**kwargs` → `TypeError: call_sap() got an unexpected keyword argument 'params'` → avalé par `except Exception` → **HTTP 500**.
- **Statut** : le symbole `call_sap` **existe** (donc hors inventaire « symbole inexistant »), mais l'appel est garanti-crash sur chemin atteignable. À traiter en même temps que le Cas 2 (même fichier/mêmes routes).
- **❓ QUESTION** : `call_sap` doit-il apprendre à passer des query params (modifier la fonction), ou les routes `check-exists` doivent-elles construire l'endpoint avec la query string en dur ? Existe-t-il déjà une API SAP de lecture filtrée à privilégier (`get_sap_business_service` ?) ?
- **Recommandation** : décider du backend de lecture SAP filtrée. `check_client_exists` n'a, en l'état, **aucun** appel SAP fonctionnel.

---

## ⚪ BRANCHES DÉJÀ NEUTRALISÉES EN 501 (rappel — NON recomptées, NE PAS retraiter)

Ces branches référencent des méthodes inexistantes (`handle_client_suggestions`,
`handle_client_selection_and_continue`, `apply_product_choices` — confirmé 0 `def` repo-wide) mais lèvent
`HTTPException(501)` **avant** tout appel ; elles sont donc déjà sûres (« chantier séparé » documenté).

| Route | Ligne 501 | Branche | Symbole visé (absent) |
|---|---|---|---|
| POST /api/assistant/choice | routes_intelligent_assistant.py:1385 | `client_choice` | `handle_client_suggestions` |
| POST /api/assistant/client/workflow/choice | routes_intelligent_assistant.py:1539 | `client_choice` | `handle_client_suggestions` |
| POST /api/assistant/assistant/continue_workflow | routes_intelligent_assistant.py:1870 | `client_selected` | `handle_client_selection_and_continue` |
| POST /api/assistant/assistant/continue_workflow | routes_intelligent_assistant.py:1882 | `product_selected` | `apply_product_choices` |

> Les autres branches de ces mêmes routes (`product_choice`, `create_client`) appellent
> `apply_product_suggestions` (`devis_workflow.py:1604`) et `_handle_new_client_creation`
> (`devis_workflow.py:5632`), **toutes deux existantes** → saines.

---

## Fichiers audités SANS aucune cassure

`routes_admin.py` (+ `llm_admin_router`), `routes_quote_details.py`, `routes_clients.py`,
`routes_supplier_tariffs.py`, `routes_pricing_validation.py`, `routes_sap_quotation.py`,
`routes_product_validation.py`, `routes_mail.py`, `routes_webhooks.py`, `routes_packing.py`,
`routes_shipping.py`, `routes_auth.py`, `routes_client_listing.py`, `routes_websocket.py`,
`routes_export_json.py`, `routes_export_json_v2.py`, `routes_sap_rondot.py`, `routes_risk.py`.

> Note de vérification (faux-positif écarté) : `routes_quote_details.py:222/228` appelle
> `connector.call_sap_mcp("get_quotation_details", ...)` — `get_quotation_details` est une **action MCP
> (chaîne)** dispatchée par `call_sap_mcp` (méthode réelle, `mcp_connector.py:361`), **pas** un attribut
> Python ; un `try/except` bascule de plus sur `sap_read`. Aucun AttributeError → non cassé.

---

## Bilan & priorisation suggérée (pour l'étape de correction, hors périmètre de cet audit)

1. **Outages HTTP 500 réels** (priorité haute) : Cas 2 + Cas A (routes_sap_creation, check-exists), Cas 7/8/9 (routes_progress).
2. **Fonctionnalités 100 % mortes mais avalées en 200** (priorité moyenne) : Cas 1, 3, 4, 5, 6, 11.
3. **Feature morte + réponse mensongère** (priorité moyenne, faible risque) : Cas 10 (`mapping_saved` faux).
4. **Renommages quasi sûrs** : Cas 1 (`process_prompt`), Cas 2 (retrait import) — mais Cas 2 reste bloqué par Cas A.

**Aucun** cas nouveau ne relève d'un pur **501/RETRAIT** : tous ont une cible candidate plausible (d'où le
classement RENOMMAGE TRIVIAL / À VALIDER). Les seuls 501 légitimes sont les 4 branches déjà neutralisées.
