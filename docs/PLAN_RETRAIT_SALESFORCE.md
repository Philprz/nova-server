# Plan de retrait Salesforce — NOVA (RONDOT = SAP only)

> **Tableau de bord d'exécution.** RONDOT n'utilise que SAP. Le flux devis est
> **SAP-first, Salesforce-optionnel** (mode dégradé déjà en place via
> `call_salesforce_mcp` → `salesforce_unavailable` / `fallback_mode`). Le retrait
> se fait par **lots à risque croissant** : on commence par ce qui est mort ou
> purement cosmétique (observabilité), on termine par le socle technique
> (connecteur + subprocess MCP).

## Décisions structurantes

- **Ordre = risque croissant.** Observabilité (aucun impact métier) → routes de
  lecture/enrichissement → workflow de génération → socle connecteur/MCP →
  nettoyage dépendances/env.
- **On ne casse jamais un contrat de route** pendant un lot. Les `id` d'étapes de
  progression émis par le workflow sont conservés tant que l'émetteur n'est pas
  retiré (évite les `Étape inconnue`).
- **Mode dégradé déjà tolérant.** Le connecteur renvoie déjà `fallback_mode` quand
  SF est indisponible ; retirer SF revient donc, côté métier, à forcer ce chemin
  déjà éprouvé.
- **Commits atomiques + push par unité logique.** `git add` ciblé (jamais `-A`).
  Relecture du code réel + re-vérification des numéros de ligne avant chaque édition.
- **Le socle SF n'est PAS touché avant le Lot 5.** `call_salesforce_mcp`,
  `salesforce_login`, `_init_salesforce`, les 9 wrappers SF et `salesforce_mcp.py`
  restent intacts jusque-là (preuve de non-débordement : `grep def call_salesforce_mcp`).

## Hypothèses

- Baseline de tests avant Lot 1 : **523 passed / 0 failed / 29 skipped** (dénominateur
  ajusté après retrait des sondes SF ; `test_sap_product_real.py` déselectionné si le
  serveur tourne — conflit session SAP 305).
- Les tests `@pytest.mark.integration` (`test_integration_workflow.py`) exigent des
  connexions réelles et ne font pas partie de la baseline unitaire.
- `/health` reste `healthy` à ≥ 80 % ; après retrait des 2 sondes SF le dénominateur
  passe de 9 à 7 tests.

## Les 6 lots

| Lot | Périmètre | Risque | Portée | Statut |
|-----|-----------|--------|--------|--------|
| **1** | **Observabilité / santé / config** — sondes `/health` SF, helpers d'observabilité du connecteur, préfixe `SALESFORCE_` du masquage admin, étapes de progression SF jamais émises | Faible (aucun chemin métier) | `services/health_checker.py`, `services/mcp_connector.py` (observabilité only), `routes/routes_admin.py` + test, `services/progress_tracker.py` | **En cours** |
| **2** | **Routes clients** — branches SF de recherche/création/enrichissement client (`routes_clients`, `client_lister`) | Moyen | routes + lister clients | À venir |
| **3** | **Workflow devis** — retrait de la synchronisation SF (`sync_external_systems`, création d'opportunité), bascule SAP-only dans `devis_workflow.py` | Élevé (cœur métier) | `workflow/devis_workflow.py` | À venir |
| **4** | **Routes devis & assistant** — affichage/enrichissement SF dans `routes_devis`, `routes_quote_details`, `routes_intelligent_assistant` | Moyen/Élevé | routes devis + assistant | À venir |
| **5** | **Socle connecteur + subprocess MCP** — `call_salesforce_mcp`, `salesforce_login`, `_init_salesforce`, les 9 wrappers SF, `salesforce_mcp.py` | Élevé (technique) | `services/mcp_connector.py` (socle), `salesforce_mcp.py` | À venir |
| **6** | **Nettoyage final** — dépendance `simple_salesforce`, variables `SALESFORCE_*` (env/coffre), docs & tests résiduels | Faible | déps / env / docs | À venir |

## Détail Lot 1 (exécuté ici)

1. **`services/health_checker.py`** — retire les 2 sondes SF de la liste `tests`
   (`salesforce_connection`, `salesforce_data_retrieval`), supprime les méthodes
   `_test_salesforce_connection` / `_test_salesforce_data_retrieval` et leurs branches
   dans `_generate_recommendations`. Dénominateur du score : 9 → 7.
2. **`services/mcp_connector.py` (observabilité UNIQUEMENT)** — retire les clés SF de
   `get_timeout_for_action` et `routes_availability`, le bloc SF de
   `test_mcp_connections_with_progress` (+ `overall_status` recalculé sur SAP seul), et
   la clé `"salesforce"` de `connection_status` à l'init. **INTERDIT** : socle SF (Lot 5).
3. **`routes/routes_admin.py` + `tests/test_admin_config.py`** — retire la tuple
   `("SALESFORCE_", "Salesforce")` de `_CATEGORY_PREFIXES` ; le masquage des secrets
   reste assuré par les fragments génériques `TOKEN`/`PASSWORD`/`SECRET`/`KEY`. Tests
   ajustés (assertions SF).
4. **`services/progress_tracker.py`** — supprime les étapes SF jamais émises
   (`sync_salesforce`, `sync_to_salesforce`), relabel `sync_external_systems`
   `💾 Synchronisation SAP & Salesforce` → `💾 Synchronisation SAP` **sans changer l'id**
   (émis par `devis_workflow.py:6496` jusqu'au Lot 3).
