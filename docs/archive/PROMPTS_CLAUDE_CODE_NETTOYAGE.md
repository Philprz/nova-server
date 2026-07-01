# Prompts Claude Code — Allègement du projet NOVA (à exécuter dans l'ordre)

Coller un bloc à la fois dans Claude Code, dans le repo NOVA.
Contexte : préparation de la livraison compilée RONDOT (voir `SPEC_COMPILATION_RONDOT.md`, Lot 6).

> AVERTISSEMENT DE BASE DE RÉFÉRENCE
> Les pistes ci-dessous ont d'abord été repérées par analyse statique sur le commit `47d2ad4`
> (29/05). Le repo a évolué depuis (ajout de `package_deploy.ps1`, `.deployignore`, `dist/` ;
> suppression de scripts de debug ; etc.). **En cas de conflit, le code réel courant fait foi,
> pas cette liste.** Re-prouver chaque élément sur l'état actuel du repo avant d'agir.

## Clause anti-régression (s'applique à TOUTES les étapes)

> Contrainte permanente : ne casser aucune fonctionnalité existante.
> AVANT toute modification : exécuter la suite de tests (`tests/`) et vérifier que l'application démarre (`main.py`) — noter cet état de référence.
> APRÈS modification : relancer les tests et le démarrage, vérifier les imports, confirmer qu'aucun comportement existant n'a régressé.
> Ne renommer aucune fonction, classe ou variable existante. Ne créer aucune fonction sans avoir vérifié qu'elle n'existe pas déjà.
> Travailler sur une branche dédiée et faire un commit par étape, message explicite. En cas de doute, demander un arbitrage au lieu de supposer.

---

## Décisions d'architecture validées (Philippe)

- **Packaging compilé : script dédié.** Créer `scripts/package_compiled.ps1` qui part de la
  **sortie de build Cython** (les `.pyd`, non suivis par git) et réutilise les motifs de
  `.deployignore` pour les exclusions de non-code. NE PAS étendre `package_deploy.ps1` (qui
  part de `git ls-files` et ne voit pas les `.pyd`) : le conserver tel quel pour la livraison
  source/debug. Source de vérité unique des exclusions = `.deployignore`.
- **Secrets : on reste sur `.env` pour l'instant.** Le coffre chiffré `secrets.enc` appartient
  au Lot 1 de `SPEC_COMPILATION_RONDOT.md` (pas encore implémenté). Le packaging référence `.env`
  aujourd'hui ; bascule vers `secrets.enc` quand le coffre existera.
- **Sync SAP↔Salesforce : suppression de la paire** `routes/routes_sync.py` +
  `sync_clients.py` (feature jamais montée dans `main.py`), après preuve qu'aucun module vivant
  ne les appelle (voir Étape 2).

---

## ÉTAPE 1 — Manifeste d'exclusion de livraison (risque nul, ne supprime rien)

```
Mission : définir ce qui NE doit PAS être livré ni compilé pour la production RONDOT, sans
rien supprimer du repo. Objectif : alléger la livraison compilée Cython.

Contexte : SPEC_COMPILATION_RONDOT.md, Lot 6 (hygiène de livraison).

Procédure :
1. Pars de .deployignore existant comme source de vérité des exclusions. Établis l'inventaire
   COURANT (état réel du repo, pas une liste fournie) des fichiers présents mais inutiles en
   production, classés et justifiés un par un. Vérifie notamment, et n'inclus que ceux qui
   existent encore ET ne sont pas importés par l'application :
   - tests/ (déjà dans .deployignore) ;
   - mail-to-biz/ (sources front, build déjà servi dans frontend/ — déjà dans .deployignore) ;
   - utilitaires one-shot lancés à la main et non importés par l'app : install_pg_trgm.py,
     list_sap_products.py, get_user_id.py, scripts/seed_rondot.py,
     scripts/migrate_to_local_search.py, scripts/sync_sap_products.py
     (sync_sap_products n'est importé que par migrate_to_local_search, lui-même exclu) ;
   - documentation : *.md de la racine, docs/, cloudflare/*.md ;
   - outils de build/dev front : build-front.bat, dev-front.bat, cloudflare/setup-windows.ps1.
   NE PAS exclure : register_webhook.py, renew_webhook.py (renouvellement de webhook Graph
   planifié, nécessaire en prod) ; main.py, sap_mcp.py, salesforce_mcp.py ; le code métier ;
   templates/, static/, frontend/, alembic/ ; requirements.txt, .env.example, et les .bat
   d'exploitation (start-nova.bat, restart_server.bat, nova-setup-tache.bat).
2. Mets à jour .deployignore avec les exclusions manquantes, et écris scripts/package_compiled.ps1
   qui : compile le code métier en .pyd, puis assemble la livraison à partir des .pyd + des
   fichiers non-code retenus, en appliquant .deployignore. Ne PAS modifier package_deploy.ps1.
3. Présente-moi la liste finale + le script, et ATTENDS ma validation avant de créer/modifier
   quoi que ce soit.

Aucune suppression de fichier du repo à cette étape. Applique la clause anti-régression.
```

---

## ÉTAPE 2 — Suppression du code mort (validation fichier par fichier)

```
Mission : retirer du repo le code réellement mort, APRÈS l'avoir prouvé sur le code COURANT et
après ma validation explicite, un fichier à la fois.

IMPORTANT : ne te fie pas à une liste pré-établie. Construis toi-même la liste des candidats à
partir de l'état actuel du repo :
 - routes définissant des endpoints mais jamais montées dans main.py (aucun include_router) ;
 - modules jamais importés nulle part (ni statiquement, ni par chaîne dynamique).

Suppression DÉJÀ ARBITRÉE (à prouver puis exécuter) :
 - La paire routes/routes_sync.py + sync_clients.py : feature de sync SAP<->Salesforce jamais
   montée dans main.py. Prouve qu'aucun module VIVANT (monté/importé par l'app) ne les appelle.
   sync_clients.py n'est importé que par routes_sync.py (try/except, l.20) : une fois routes_sync
   retiré, sync_clients devient orphelin -> supprimer les deux ensemble.

CAS PARTICULIERS à arbitrer (ne supprime qu'après preuve + mon accord) :
 - routes/routes_sap_session.py : vérifie s'il est remplacé par le module auth/sap_session/
   (qui est câblé). Ne le retire que si confirmé obsolète.
 - Tout autre orphelin que TON analyse du repo courant remonte (ex. routes non montées,
   modules non importés). Attention : des éléments que je citais auparavant ont changé de statut
   (ex. utils/sap_product_utils.py serait utilisé) — ne te base que sur ta vérification actuelle.

Procédure pour CHAQUE fichier :
1. Prouve qu'il est mort : montre les résultats de recherche (import, from ... import, usage
   dynamique par chaîne, include_router) dans tout le repo hors le fichier lui-même.
2. Si la moindre référence vivante existe, classe INCERTAIN et ne propose pas la suppression.
3. Présente le bilan (MORT confirmé / INCERTAIN) et ATTENDS ma validation.
4. Après validation : supprime, vérifie le démarrage + les tests. Commit clair par suppression.

Ne touche pas aux fichiers de services/ référencés. Applique la clause anti-régression.
```

---

## ÉTAPE 3 — Contrôle final d'allègement

```
Mission : vérifier qu'après les étapes 1 et 2 le projet est cohérent et plus léger, sans
régression.

1. Relance la suite de tests complète et le démarrage de main.py : tout doit passer.
2. Vérifie qu'aucun import ne pointe vers un fichier supprimé (pas de ModuleNotFoundError).
3. Donne-moi un avant/après chiffré : nombre de fichiers .py avant / après suppression, et
   nombre de fichiers réellement livrés en prod via scripts/package_compiled.ps1 (.deployignore
   appliqué).
4. Liste ce qui reste classé INCERTAIN et nécessite encore mon arbitrage.

Applique la clause anti-régression.
```
