# Configuration des Dépôts Git pour NOVA POC

## Vue d'ensemble

Ce projet utilise deux dépôts Git pour maintenir le code :

1. **Dépôt Principal** (`origin`) : https://github.com/Philprz/nova-server
   - C'est le dépôt principal de développement
   - Toutes les modifications sont d'abord poussées ici

2. **Dépôt Secondaire** (`secondary`) : https://github.com/www-it-spirit-com/NOVAPOC
   - C'est le dépôt de l'entreprise www-it-spirit-com
   - Les modifications sont synchronisées ici après le push principal

## Configuration

### Vérifier la configuration actuelle

```bash
git remote -v
```

### Configuration manuelle des remotes

Si les remotes ne sont pas configurés correctement :

```bash
# Configurer le dépôt principal
git remote add origin https://github.com/Philprz/nova-server.git
# ou si origin existe déjà
git remote set-url origin https://github.com/Philprz/nova-server.git

# Configurer le dépôt secondaire
git remote add secondary https://github.com/www-it-spirit-com/NOVAPOC.git
# ou si secondary existe déjà
git remote set-url secondary https://github.com/www-it-spirit-com/NOVAPOC.git
```

### Script de vérification automatique

Utilisez le script `verify_remotes.ps1` pour vérifier et corriger automatiquement la configuration :

```powershell
.\verify_remotes.ps1
```

## Utilisation

### Push vers les deux dépôts

Utilisez le script `push_both.ps1` pour pousser automatiquement vers les deux dépôts :

```powershell
# Avec un message de commit
.\push_both.ps1 "feat: nouvelle fonctionnalité"

# Sans message (sera demandé interactivement)
.\push_both.ps1
```

Le script :
1. Vérifie s'il y a des changements
2. Propose un message de commit intelligent basé sur l'analyse du code
3. Commit les changements
4. Pousse vers le dépôt principal (origin)
5. Pousse vers le dépôt secondaire (secondary)

## Résolution de problèmes

### Erreur d'authentification

Si vous rencontrez des erreurs d'authentification :

1. Vérifiez que vous avez accès aux deux dépôts
2. Configurez vos credentials Git :
   ```bash
   git config --global user.name "Votre Nom"
   git config --global user.email "votre.email@example.com"
   ```
3. Pour GitHub, utilisez un Personal Access Token au lieu du mot de passe

### Le dépôt secondaire n'est pas accessible

Si le push vers le dépôt secondaire échoue :
- Vérifiez que vous avez les permissions sur https://github.com/www-it-spirit-com/NOVAPOC
- Le script continuera même si le push secondaire échoue

### Branches divergentes

Si les branches ont divergé :
```bash
# Pour le dépôt principal
git pull origin main --rebase

# Pour le dépôt secondaire
git pull secondary main --rebase
```