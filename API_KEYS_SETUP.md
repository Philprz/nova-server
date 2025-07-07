# Configuration des clés API pour push_both_ai.ps1

## Configuration des clés API

Pour utiliser les fonctionnalités IA du script `push_both_ai.ps1`, vous devez configurer vos clés API.

### Option 1 : Variables d'environnement (Recommandé)

#### Windows PowerShell
```powershell
# Temporaire (session actuelle uniquement)
$env:OPENAI_API_KEY = "sk-..."
$env:ANTHROPIC_API_KEY = "sk-ant-..."

# Permanent (toutes les sessions futures)
[System.Environment]::SetEnvironmentVariable("OPENAI_API_KEY", "sk-...", "User")
[System.Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "sk-ant-...", "User")
```

#### Linux/Mac
```bash
# Ajouter à ~/.bashrc ou ~/.zshrc
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
```

### Option 2 : Fichier de configuration local

Créez un fichier `.env.local` à la racine du projet :

```
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

**Note** : Ce fichier est ignoré par Git pour votre sécurité.

### Option 3 : Paramètre direct

```powershell
.\push_both_ai.ps1 -UseAI -AIProvider OpenAI -APIKey "sk-..."
```

## Obtenir des clés API

### OpenAI
1. Créez un compte sur https://platform.openai.com
2. Allez dans API Keys
3. Créez une nouvelle clé
4. Coût approximatif : $0.01 par commit

### Claude (Anthropic)
1. Créez un compte sur https://console.anthropic.com
2. Allez dans API Keys
3. Créez une nouvelle clé
4. Coût approximatif : $0.01 par commit

## Sécurité

- **Ne commitez jamais vos clés API**
- Les fichiers `.env.local` et `*.apikey` sont dans `.gitignore`
- Utilisez des clés avec des limites de dépenses
- Révoquez les clés compromises immédiatement

## Test de configuration

Pour vérifier que vos clés sont bien configurées :

```powershell
# Test OpenAI
if ($env:OPENAI_API_KEY) { 
    Write-Host "✓ Clé OpenAI configurée" -ForegroundColor Green 
} else { 
    Write-Host "✗ Clé OpenAI manquante" -ForegroundColor Red 
}

# Test Claude
if ($env:ANTHROPIC_API_KEY) { 
    Write-Host "✓ Clé Claude configurée" -ForegroundColor Green 
} else { 
    Write-Host "✗ Clé Claude manquante" -ForegroundColor Red 
}
```