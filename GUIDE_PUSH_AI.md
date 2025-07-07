# Guide d'utilisation - Push Both AI

## Vue d'ensemble

Le script `push_both_ai.ps1` est une version avancée du script de push qui génère des messages de commit extrêmement détaillés et précis en analysant en profondeur les changements de code.

## Fonctionnalités principales

### 1. Analyse approfondie du code
- **Analyse contextuelle** : Identifie dans quelle fonction/classe chaque changement a été fait
- **Détection du but** : Comprend pourquoi chaque ligne a été ajoutée/supprimée
- **Classification intelligente** : Catégorise les changements (bug fix, nouvelle fonctionnalité, refactoring, etc.)
- **Analyse d'impact** : Évalue l'impact sur différentes parties du système

### 2. Support d'IA (optionnel)
- **OpenAI GPT-4** : Pour une analyse ultra-précise
- **Claude AI** : Alternative à OpenAI
- **Mode local** : Analyse sophistiquée sans API externe

## Utilisation

### Mode basique (analyse locale)
```powershell
.\push_both_ai.ps1
```

### Avec message personnalisé
```powershell
.\push_both_ai.ps1 "fix: correction du bug de validation des emails"
```

### Avec IA OpenAI
```powershell
# Avec clé API directe
.\push_both_ai.ps1 -UseAI -AIProvider OpenAI -APIKey "sk-..."

# Avec clé API dans l'environnement
$env:OPENAI_API_KEY = "sk-..."
.\push_both_ai.ps1 -UseAI -AIProvider OpenAI
```

### Avec IA Claude
```powershell
# Avec clé API directe
.\push_both_ai.ps1 -UseAI -AIProvider Claude -APIKey "sk-ant-..."

# Avec clé API dans l'environnement
$env:ANTHROPIC_API_KEY = "sk-ant-..."
.\push_both_ai.ps1 -UseAI -AIProvider Claude
```

## Format des messages générés

Le script génère des messages au format Conventional Commits avec :

### Structure du message
```
<type>(<scope>): <description courte>

CHANGEMENTS EFFECTUÉS:
📁 fichier1.py:
  Added:
    - Définition de fonction 'validate_email' avec paramètres: email
    - Validation/vérification in function validate_email
  Removed:
    - Ancienne validation simple

📁 api/routes.py:
  Added:
    - Nouvel endpoint API in function register_user

RAISONS DES MODIFICATIONS:
- Pour résoudre un problème existant
  → Correction de la validation des emails
- Pour ajouter une nouvelle capacité au système
  → Ajout d'un nouvel endpoint API

IMPACT:
- [High] Backend/Logic: Modifications de la logique métier
- [Medium] Configuration: Modifications de configuration

DÉTAILS TECHNIQUES:
- Lignes ajoutées: +47
- Lignes supprimées: -12
- Fonctions modifiées: validate_email, register_user
- Classes modifiées: UserValidator
```

## Configuration des clés API

### Variables d'environnement permanentes (recommandé)

#### Windows PowerShell
```powershell
# Ajouter à votre profil PowerShell
[System.Environment]::SetEnvironmentVariable("OPENAI_API_KEY", "votre-clé", "User")
[System.Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "votre-clé", "User")
```

#### Linux/Mac
```bash
# Ajouter à ~/.bashrc ou ~/.zshrc
export OPENAI_API_KEY="votre-clé"
export ANTHROPIC_API_KEY="votre-clé"
```

## Exemples de messages générés

### Exemple 1 : Correction de bug
```
fix(auth): correction de la vulnérabilité XSS dans la validation des emails

CHANGEMENTS EFFECTUÉS:
📁 auth/validators.py:
  Added:
    - Import de dépendance: html
    - Validation/vérification in function validate_email
    - Security/authentification in function sanitize_input
  Removed:
    - Ancienne regex non sécurisée

RAISONS DES MODIFICATIONS:
- Pour résoudre un problème existant
  → Correction de la vulnérabilité XSS

IMPACT:
- [Critical] Security: Amélioration de la sécurité
- [High] Backend/Logic: Modifications de la logique métier

DÉTAILS TECHNIQUES:
- Lignes ajoutées: +23
- Lignes supprimées: -8
- Fonctions modifiées: validate_email, sanitize_input
```

### Exemple 2 : Nouvelle fonctionnalité
```
feat(api): ajout endpoint de génération de rapports avec cache Redis

CHANGEMENTS EFFECTUÉS:
📁 api/reports.py:
  Added:
    - Définition de fonction 'generate_report' avec paramètres: user_id, date_range
    - Import de dépendance: redis
    - Appel API/HTTP in function fetch_data
    
📁 config/redis.json:
  Added:
    - Donnée de configuration

RAISONS DES MODIFICATIONS:
- Pour ajouter une nouvelle capacité au système
  → Ajout d'un nouvel endpoint API
- Pour optimiser les performances du système
  → Ajout de cache Redis

IMPACT:
- [High] Backend/Logic: Modifications de la logique métier
- [Medium] Configuration: Modifications de configuration
- [High] Performance: Amélioration des temps de réponse

DÉTAILS TECHNIQUES:
- Lignes ajoutées: +156
- Lignes supprimées: -0
- Fonctions modifiées: generate_report, cache_report, get_cached_report
- Classes modifiées: ReportGenerator
```

## Avantages de l'analyse détaillée

1. **Traçabilité complète** : Chaque changement est documenté avec son contexte
2. **Compréhension rapide** : Les nouveaux développeurs comprennent immédiatement l'historique
3. **Revue de code facilitée** : Les reviewers voient exactement ce qui a changé et pourquoi
4. **Documentation automatique** : L'historique Git devient une documentation vivante
5. **Détection d'impacts** : Identifie les zones du système affectées

## Résolution de problèmes

### Le script est trop lent
- L'analyse locale est rapide (< 5 secondes)
- L'API IA ajoute 5-10 secondes
- Pour des commits rapides, utilisez le mode local

### Messages trop détaillés
- Vous pouvez toujours éditer le message suggéré
- Ou fournir votre propre message avec `-CommitMessage`

### Erreur d'API
- Vérifiez votre connexion Internet
- Vérifiez la validité de votre clé API
- Le script bascule automatiquement en mode local si l'API échoue

## Comparaison des modes

| Caractéristique | Local | OpenAI | Claude |
|-----------------|-------|---------|---------|
| Précision | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Vitesse | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| Coût | Gratuit | ~$0.01/commit | ~$0.01/commit |
| Dépendance Internet | Non | Oui | Oui |
| Qualité linguistique | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |