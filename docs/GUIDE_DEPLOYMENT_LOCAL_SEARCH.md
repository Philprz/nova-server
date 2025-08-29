# GUIDE_DEPLOYMENT_LOCAL_SEARCH.md
# Déploiement Système Pré-indexation Produits SAP

## OBJECTIF
Remplacement de la recherche SAP temps réel par une base locale pré-indexée pour éliminer les boucles infinies et améliorer les performances (< 500ms).

## PRÉREQUIS
- PostgreSQL 17 fonctionnel
- Variables d'environnement .env configurées
- Connexion SAP opérationnelle
- Python 3.10.10 avec venv activé

## PROCÉDURE DE DÉPLOIEMENT

### ÉTAPE 1: Création table PostgreSQL
```bash
# Application migration Alembic
alembic upgrade head