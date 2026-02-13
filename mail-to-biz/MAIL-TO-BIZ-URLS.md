# Une seule interface mail-to-biz : pourquoi 2 URLs et comment n'en garder qu'une

## Pourquoi vous aviez 2 formulaires différents

L'app mail-to-biz peut être servie de **deux façons** :

| URL | Serveur | Contenu servi |
|-----|--------|----------------|
| **http://localhost:8001/mail-to-biz/** | Backend FastAPI (NOVA-SERVER) | Dossier **`frontend/`** (build compilé, à mettre à jour à la main) |
| **http://localhost:8080/mail-to-biz/** (ou **8082**) | Serveur de dev Vite | Sources **`mail-to-biz/src/`** en direct → **toujours à jour** |

- **8001** = ce qui a été buildé puis copié dans `frontend/` (souvent ancien si vous ne refaites pas le build).
- **8080 / 8082** = dernière version du code, avec hot reload.

Si le build dans `frontend/` n'est pas à jour, les deux URLs affichent deux versions différentes (d'où 2 formulaires).

---

## Recommandation : utiliser le serveur de dev (8082 ou 8080)

**Le plus simple est d'utiliser l'URL du serveur de dev**, qui est **toujours à jour** sans avoir à lancer `npm run build` ni à copier dans `frontend/`.

1. Lancer le **backend** sur **8001** (comme d'habitude).
2. Lancer le frontend en dev : `cd mail-to-biz && npm run dev` (port 8080 dans la config, ou 8082 chez vous si configuré ainsi).
3. Ouvrir **uniquement** : **http://localhost:8082/mail-to-biz/** (ou 8080 selon votre port).

Les appels API (`/api/*`) sont déjà proxifiés vers le backend 8001 dans `vite.config.ts`.

---

## Alternative : tout via le backend (8001)

Si vous préférez n'utiliser que **http://localhost:8001/mail-to-biz/**, il faut à chaque modification du frontend :

```bash
cd mail-to-biz
npm run build
# Puis (PowerShell) :
Copy-Item -Path dist\* -Destination ..\frontend\ -Recurse -Force
```

---

## Récap

- **Recommandé** : une seule URL = **serveur de dev (8082 ou 8080)** → toujours à jour, pas de build/copie.
- **Alternative** : 8001 en mettant à jour `frontend/` après chaque build.
