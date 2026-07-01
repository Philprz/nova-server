# RAPPORT D'AUDIT NOVA — Pré-production (lecture seule)

**Base de l'audit :** branche `main`, HEAD `135c001c` (tag `broken-routes-fixed`), working tree propre hormis `.claude/settings.local.json` (config locale de l'outil, hors projet). 353 fichiers trackés par git. Aucune modification effectuée. Aucun patch, aucun commit.

**Convention :** `[CERTAIN]` = prouvé par le code ; `[HYPOTHÈSE]` = à confirmer. Principe appliqué partout : en cas de doute → CONSERVER.

## 1. Architecture globale (flux réel)

Point d'entrée prod : service Windows NSSM `NOVA-Backend` → `run.py` (et non `main.py` directement).

`run.py` : (1) charge le coffre chiffré si présent (`secrets.enc` + `NOVA_VAULT_KEY`) sinon repli `.env` ; (2) migrations Alembic optionnelles (`NOVA_AUTO_MIGRATE`) ; (3) `from main import app` + uvicorn sur port 8001. Le shim Cython `scripts/cython_pydantic_compat.py` s'exécute avant tout import Pydantic (`run.py:36-37`, `main.py:11-12`).

**Flux devis (chemin « assistant ») :** `routes_intelligent_assistant` / `routes_devis` → `workflow/devis_workflow.py` (`DevisWorkflow`) → `LLMExtractor` (LLM) + `MCPConnector` (SAP/Salesforce) → `price_engine.PriceEngineService` + `SequentialValidator` → création devis SAP. Progression temps réel via `progress_tracker` + WebSocket.

**Flux mail-to-biz (chemin « graph/mail ») :** webhook Microsoft Graph → `routes_webhooks`/`routes_graph` → `services/mail_processor` + `email_analyzer` → `pricing_engine` (4 CAS HC/HCM/HA/NP) → `routes_sap_business`/`routes_sap_quotation` (création devis SAP B1). Front React `frontend/` servi sur `/mail-to-biz`.

**Serveurs MCP :** `sap_mcp.py` et `salesforce_mcp.py` (racine) lancés en subprocess (ne pas classer inactifs).

**Front servi en prod :** `frontend/` (build Vite), monté `main.py:294` + `main.py:463-469`. `mail-to-biz/` en est la source (`vite.config.ts` → `build.outDir: "../frontend"`), exclue du package.

## 2. Dépendances (requirements.txt)

Sur 29 paquets : 26 nécessaires (prod / transitive / dev), 3 candidats de nettoyage.

| Constat | Preuve | Certitude | Impact | Risque régression | Difficulté | Bénéfice prod | Test avant action |
|---|---|---|---|---|---|---|---|
| `openai` jamais importé — la stack LLM passe par `LLMRouter` en HTTP direct (httpx) | Aucun import `openai` dans le code app ; seul code SDK = `_call_openai_DEPRECATED` | [CERTAIN] | Bas (taille build) | Bas | Basse | Image/venv plus léger | Boot serveur + 1 devis LLM de bout en bout |
| `pandas` jamais importé | 0 occurrence `import pandas` | [CERTAIN] absence / [HYPOTHÈSE] transitive | Bas | Bas-Moyen | Basse | Retire une grosse dépendance | `pip show pandas` (Required-by) avant retrait |
| `pytest-asyncio` : pas d'import explicite (dev) | Activé par config pytest | [HYPOTHÈSE] | Bas | Moyen (tests async) | Basse | Aucun (dev) | Lancer la suite de tests |

**Pièges levés (à conserver, imports lazy/transitifs) :** `psycopg2-binary` (driver PostgreSQL de SQLAlchemy), `anyio` (transitive), `pyodbc`/`simple-salesforce`/`fitz`/`PIL`/`pytesseract` (imports dans fonctions).

## 3. Code mort (niveau module)

| Constat | Preuve | Certitude | Impact | Risque régression | Difficulté | Bénéfice prod | Test avant action |
|---|---|---|---|---|---|---|---|
| Trio QWE mort en prod : `quote_workflow_engine.py` + ses 2 dépendances exclusives `transport_calculator.py` et `supplier_discounts_db.py` | Aucun importeur hors tests ; transport prod réel = `services/transport/` + `routes_shipping` monté `main.py:316` | [CERTAIN] | Moyen (3 modules) | Bas en prod / casse 2 tests | Moyenne | ~3 modules + tests retirés | Décision produit : abandonne-t-on la « machine à états devis » QWE ? Les 3 tombent ensemble |

**Faux positifs levés (VIVANTS) :** `company_agent` (import relatif), `sap_client` (via `retry_service`→`routes_mail`), `sap_sql`/`history`/`currency`/`quote_validator` (via `pricing_engine`). [CERTAIN]

**Doublons de moteurs — AUCUN à supprimer (3 paires suspectes, toutes légitimes multi-couches) :**
- Pricing : `price_engine.py` (workflow devis + MCP) et `pricing_engine.py` (flux mail/graph, 4 CAS) → deux chemins d'appel distincts. [CERTAIN]
- SAP : `sap.py` (REST bas niveau) / `sap_client.py` (wrapper traçable) / `sap_business_service.py` (service métier, 10+ importeurs). [CERTAIN]
- Recherche produit : `product_search_engine` / `local_product_search` / `product_mapping_db` → 3 responsabilités distinctes. [CERTAIN]

## 4. Routes inutilisées / cassées

| Constat | Preuve | Certitude | Impact | Risque régression | Difficulté | Bénéfice prod | Test avant action |
|---|---|---|---|---|---|---|---|
| 0 route cassée subsiste : les 11 cas de `AUDIT_ROUTES_CASSEES.md` sont tous corrigés | ex. `cancel_task` `[progress_tracker.py:476]`, `search_company_by_name` `[routes_intelligent_assistant.py:1595]` | [CERTAIN] | — | — | — | — | — |
| `AUDIT_ROUTES_CASSEES.md` périmé (état pré-fix, 30/06 avant merges Lot 1/2/3) | daté branche `prod/fix-broken-routes` | [CERTAIN] | Bas | Bas | Basse | Doc à jour | Archiver, ne plus l'utiliser comme référence |
| `routes_products.py` : router non monté mais `search_products_advanced` importée en vif `[routes_intelligent_assistant.py:1148]` | grep | [CERTAIN] | Bas | Haut si fichier retiré | — | Aucun | CONSERVER (piège du grep) |
| `routes_sap_session.py` : router non monté (seulement dans tests) | 0 `include_router` en prod | [CERTAIN] | Bas | Moyen | — | Aucun | CONSERVER jusqu'à arbitrage auth SAP |
| Routes debug/alias : `/api/assistant/interface` (« temporaire de débogage » `[main.py:436]`), collision potentielle avec `[routes_intelligent_assistant.py:1266]` ; `get_progress_stats` défini 2× `[routes_progress.py:655/938]` | main.py + grep | [CERTAIN] / collision [HYPOTHÈSE] | Bas | Moyen | Basse | Surface réduite | Tester chaque endpoint (200) avant tout retrait |

## 5. Front-ends & assets

| Constat | Preuve | Certitude | Impact | Risque régression | Difficulté | Bénéfice | Test avant action |
|---|---|---|---|---|---|---|---|
| `mail-to-biz/dist/` = ancien build (25/02) jamais servi ; `frontend/` (28/05) est le build vivant | hashes différents ; main.py ne pointe que `frontend/` | [CERTAIN]/[HYP. forte] | Bas | Nul (hors package) | Basse | Nettoyage source | — |
| `templates/nova_interface_final.html` = ancien front IT Spirit encore servi (`/interface/itspirit`, `/edit-quote`, `/api/assistant/interface`) | `[main.py:400/443/437]` | [CERTAIN] | Moyen | Haut | — | — | CONSERVER (legacy vivant) |
| 9 assets sans aucune référence : `static/{Covia_bann,Logo,covia,covia_clair}.png`, `static/progress_styles.css`, racine `NOVA Devis dark*.png`, `Éléments identité visuelle IT Spirit.pdf` (2,6 Mo) | grep = 0 réf | [CERTAIN] absence | Bas | Bas | Basse | Repo plus propre | CONSERVER par doute ; retrait possible après confirmation visuelle |
| `mail-to-biz/src/integrations/` vide ; `context/` vs `contexts/` = 2 modules distincts actifs (pas un doublon) | find + `App.tsx:6-7` | [CERTAIN] | Bas | — | — | — | Ne pas fusionner sans refactor imports |

## 6. Tests, build, docs

| Constat | Preuve | Certitude | Impact | Risque | Recommandation |
|---|---|---|---|---|---|
| `tests/` (19 fichiers) déjà exclus du package | `.deployignore:16` | [CERTAIN] | — | — | CONSERVER pour CI/dev |
| `logs/` = 361 Mo sur disque, sans rotation visible (hors git) | `du -sh logs` | [CERTAIN] | Hygiène | — | Purge sûre (aucun risque code) |
| `build/` = 323 Mo, `dist/*.zip` = artefacts locaux non trackés | `git ls-files` vides | [CERTAIN] | Hygiène | — | RAS (non livrés) |
| Docs : 5 rapports d'étape périmés (`AUDIT_14e00679`, `AUDIT_ROUTES_CASSEES`, `RAPPORT_PILOTE_CYTHON_LOT5*`, `PROMPTS_CLAUDE_CODE_NETTOYAGE`) ; README 124 Ko ; `cloudflare/…md` mentionne port 8000 (cible 8001) | fichiers | [CERTAIN] | Bas | — | Archiver rapports, scinder README, corriger port |

## 7. Risques techniques

| Risque | Preuve | Certitude | Gravité |
|---|---|---|---|
| Bases `.db` dupliquées racine vs `data/` avec tailles divergentes et split (`nova_auth.db` seulement dans `data/`, `supplier_tariffs.db` 4,7 Mo racine vs 2,6 Mo `data/`) | `ls` | [CERTAIN] fait / [HYPOTHÈSE] laquelle fait foi | Moyen — clarifier la source de vérité avant prod |
| Host SAP en dur `https://51.91.130.136:50000/b1s/v1` comme défaut | `price_engine.py:13` | [CERTAIN] | Faible-Moyen (overridable via `SAP_REST_BASE_URL`) ; item connu du backlog |
| `secrets.enc` non amorcé dans cet environnement | `find *.enc` vide | [CERTAIN] | Normal, mais bloquant si non généré (`provision_secrets.py`) au déploiement |

**Points forts :** aucun secret/clé/.pyd/.db/log tracké ; `_vault_key.py`, `.env`, `secrets.enc` gitignorés ; aucun credential en dur. [CERTAIN]

## (a) Quick wins sûrs (impact utile, risque bas)

1. Retirer `pandas` et `openai` de `requirements.txt` après `pip show pandas` — 0 import prouvé, allège venv/build. Test : boot + 1 devis LLM.
2. Purger `logs/` (361 Mo) et poser une rotation — hors git, aucun risque code.
3. Archiver les 5 rapports d'étape périmés + marquer `AUDIT_ROUTES_CASSEES.md` obsolète — clarté doc.
4. Corriger le port 8000→8001 dans `cloudflare/DEPLOYMENT_WINDOWS_CLOUDFLARE.md`.
5. Supprimer `mail-to-biz/dist/` (ancien build mort, non servi).

## (b) À confirmer avec Philippe avant tout

1. Trio QWE (`quote_workflow_engine` + `transport_calculator` + `supplier_discounts_db`) : abandonne-t-on définitivement la « machine à états devis » ? Si oui, les 3 + leurs tests partent ensemble.
2. `routes_sap_session.py` (auth SAP alternative non montée) : dette à garder ou à retirer ?
3. Bases `.db` racine vs `data/` : quelle est la source de vérité ? (config à trancher avant prod).
4. 9 assets sans référence (visuels Covia/IT Spirit + PDF 2,6 Mo) : confirmés inutilisés → suppression ?
5. `templates/nova_interface_final.html` (front legacy IT Spirit) : encore utilisé fonctionnellement via `/edit-quote` ? Sinon candidat au retrait (3 routes à déposer avec).

## (c) Questions ouvertes

1. Où est planifié `renew_webhook.py` (Task Scheduler Windows hors repo) ? Le renouvellement runtime est déjà couvert par APScheduler — le script est-il un simple filet manuel ?
2. `mail-to-biz/.env` et `build/runtime_check/.env` (non trackés) : contiennent-ils des secrets à ne jamais joindre à un zip manuel ?
3. Faut-il déplacer le host SAP de `price_engine.py:13` vers l'env sans défaut avant la livraison source (non compilée) ?
