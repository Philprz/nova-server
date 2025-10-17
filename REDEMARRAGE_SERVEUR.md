# 🔄 Redémarrage du Serveur NOVA

## ⚠️ IMPORTANT

Les nouvelles routes `/auth/login` ont été ajoutées mais **nécessitent un redémarrage du serveur** pour être actives.

## 📋 Procédure de redémarrage

### Étape 1 : Arrêter le serveur actuel

Dans le terminal où le serveur tourne, appuyez sur :
```
CTRL + C
```

Vous devriez voir :
```
INFO:     Shutting down
INFO:     Finished server process
```

### Étape 2 : Relancer le serveur

```bash
python main.py
```

### Étape 3 : Vérifier que les nouvelles routes sont chargées

Le serveur devrait afficher :
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8200 (Press CTRL+C to quit)
```

### Étape 4 : Tester la nouvelle route

Ouvrir dans le navigateur :
```
http://localhost:8200/docs
```

Vous devriez voir une nouvelle section **"Authentification"** avec :
- `POST /auth/login` - Connexion (1er facteur)
- `POST /auth/login/oauth2` - OAuth2 pour Swagger
- `POST /auth/logout` - Déconnexion
- `GET /auth/me` - Infos utilisateur

## ✅ Vérification rapide

Testez que l'endpoint fonctionne :

```bash
curl -X POST "http://localhost:8200/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"p.perez@it-spirit.com","password":"31021225"}'
```

**Réponse attendue** (si le compte existe) :
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "mfa_required": true,
  "mfa_stage": "pending",
  "user_id": 1,
  "email": "p.perez@it-spirit.com"
}
```

## 🐛 Si ça ne marche toujours pas

### Vérifier que le fichier est bien importé

```bash
python -c "from routes.auth import router; print('✅ OK')"
```

### Vérifier que la route est enregistrée dans main.py

Ouvrir [main.py](main.py:172-174) et vérifier que ces lignes sont présentes :
```python
from routes.auth import router as auth_router
app.include_router(auth_router, prefix="/auth", tags=["Authentification"])
```

## 🎯 Après le redémarrage

Relancez la démo :

```bash
python demo_2fa_visual.py
```

Ou ouvrez l'interface web :
```
http://localhost:8200/demo/2fa
```

---

**Note** : Le serveur doit être redémarré à chaque fois qu'on modifie :
- Les routes (fichiers dans `/routes`)
- Les modèles (fichiers dans `/models`)
- La configuration (fichiers dans `/core`)
- Le fichier `main.py`
