# Configuration Redis pour NOVA

## Statut Actuel

✅ **Redis opérationnel et configuré**

## Informations du Serveur

- **Version Redis** : 3.0.504
- **Port** : 6379
- **Base de données utilisée** : DB 1
- **Chemin d'installation** : `C:\Program Files\Redis\`
- **Fichier de configuration** : `C:\Program Files\Redis\redis.windows-service.conf`

## Configuration du Service Windows

```powershell
SERVICE_NAME: Redis
TYPE: WIN32_OWN_PROCESS
STATE: RUNNING
START_TYPE: AUTO_START (démarrage automatique)
SERVICE_START_NAME: NT AUTHORITY\NETWORKSERVICE
```

## Module Python

- **Package** : `redis 6.4.0`
- **Installation** : `pip install redis`

## Configuration NOVA

### Fichier .env

```env
REDIS_URL=redis://localhost:6379/1
```

### Utilisation dans le code

```python
from services.cache_manager import RedisCacheManager

# Initialisation
cache = RedisCacheManager(redis_url='redis://localhost:6379/1')

# Écriture
await cache.cache_data('ma_cle', {'data': 'valeur'}, ttl=3600)

# Lecture
data = await cache.get_cached_data('ma_cle')
```

## Tests de Validation

### Test 1 : Connexion basique
```bash
python -c "import redis; r = redis.Redis(host='localhost', port=6379, db=1); print('Redis OK' if r.ping() else 'ERREUR')"
```

### Test 2 : Cache NOVA
```bash
python -c "
from services.cache_manager import RedisCacheManager
import asyncio

async def test():
    cache = RedisCacheManager(redis_url='redis://localhost:6379/1')
    await cache.cache_data('test', {'status': 'ok'})
    data = await cache.get_cached_data('test')
    print('Test:', 'REUSSI' if data else 'ECHOUE')

asyncio.run(test())
"
```

## Commandes de Gestion

### Vérifier le statut du service
```powershell
sc query Redis
```

### Redémarrer le service
```powershell
net stop Redis
net start Redis
```

### Arrêter/Démarrer manuellement
```powershell
# Arrêt
sc stop Redis

# Démarrage
sc start Redis
```

## Monitoring

### Vérifier les connexions actives
```powershell
netstat -an | findstr ":6379"
```

### Logs Redis
Les logs du service Windows sont disponibles dans l'Observateur d'événements Windows sous "Services".

## Performance

- **TTL par défaut** : 3600 secondes (1 heure)
- **Fallback** : Cache mémoire activé si Redis indisponible
- **Persistance** : Redis utilise RDB (snapshots périodiques)

## Résolution de Problèmes

### Problème : "Redis non disponible"
1. Vérifier que le service tourne : `sc query Redis`
2. Vérifier le port : `netstat -an | findstr ":6379"`
3. Tester la connexion : `python -c "import redis; redis.Redis(host='localhost', port=6379).ping()"`

### Problème : "Module redis not found"
```bash
pip install redis
```

### Problème : Timeout de connexion
Vérifier le fichier de configuration Redis :
```
C:\Program Files\Redis\redis.windows-service.conf
```

S'assurer que `bind 127.0.0.1` ou `bind 0.0.0.0` est configuré.

## Sécurité

⚠️ **IMPORTANT** : Redis écoute actuellement sans authentification.

Pour sécuriser en production :

1. Éditer `redis.windows-service.conf`
2. Ajouter : `requirepass VotreMotDePasseSecurise`
3. Redémarrer le service
4. Mettre à jour `.env` : `REDIS_URL=redis://:VotreMotDePasseSecurise@localhost:6379/1`

## Maintenance

### Nettoyer le cache manuellement
```python
import redis
r = redis.Redis(host='localhost', port=6379, db=1)
r.flushdb()  # Vide la DB 1 uniquement
```

### Voir les clés stockées
```python
import redis
r = redis.Redis(host='localhost', port=6379, db=1, decode_responses=True)
keys = r.keys('*')
print(f"Nombre de clés : {len(keys)}")
for key in keys:
    print(f"  - {key}")
```

---

**Dernière mise à jour** : 2025-10-09
**Responsable** : Équipe NOVA
**Statut** : ✅ Opérationnel
