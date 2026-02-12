# Système de Cache SAP Local - Documentation

## Architecture implémentée

### Problème résolu

**AVANT** : Chargement API à chaque démarrage (lent, timeout, instable)
```
Démarrage → Appels API SAP (30-60s) → Données en RAM → Matching
❌ Lent au démarrage
❌ Données perdues à chaque restart
❌ Timeout fréquents
```

**APRÈS** : Base SQLite locale avec sync quotidienne (instantané)
```
Démarrage → Lecture SQLite (<1s) → Matching ultra-rapide
✅ Démarrage instantané
✅ Données persistantes
✅ Sync intelligente (1x/24h)
```

## Fichiers créés

### 1. `services/sap_cache_db.py` (~520 lignes)

**Service de gestion du cache SQLite local.**

#### Tables créées

```sql
-- Clients SAP
CREATE TABLE sap_clients (
    CardCode TEXT PRIMARY KEY,
    CardName TEXT NOT NULL,
    EmailAddress TEXT,
    Phone1 TEXT,
    City TEXT,
    Country TEXT,
    last_updated TIMESTAMP
);

-- Articles SAP
CREATE TABLE sap_items (
    ItemCode TEXT PRIMARY KEY,
    ItemName TEXT NOT NULL,
    ItemGroup INTEGER,
    last_updated TIMESTAMP
);

-- Métadonnées synchronisation
CREATE TABLE sap_sync_metadata (
    sync_type TEXT PRIMARY KEY,  -- 'clients' ou 'items'
    last_sync TIMESTAMP,
    total_records INTEGER,
    status TEXT,  -- 'success', 'in_progress', 'failed'
    error_message TEXT
);
```

#### Index pour recherche rapide

```sql
CREATE INDEX idx_clients_name ON sap_clients(CardName COLLATE NOCASE);
CREATE INDEX idx_clients_email ON sap_clients(EmailAddress COLLATE NOCASE);
CREATE INDEX idx_items_name ON sap_items(ItemName COLLATE NOCASE);
```

#### Méthodes principales

| Méthode | Description |
|---------|-------------|
| `needs_sync(sync_type, max_age_hours=24)` | Vérifie si sync nécessaire |
| `sync_clients_from_sap(sap_service)` | Synchronise clients SAP → SQLite |
| `sync_items_from_sap(sap_service)` | Synchronise articles SAP → SQLite |
| `get_all_clients()` | Récupère tous les clients (local) |
| `get_all_items()` | Récupère tous les articles (local) |
| `search_clients(query, limit=10)` | Recherche fuzzy clients |
| `search_items(query, limit=10)` | Recherche fuzzy articles |
| `get_client_by_code(card_code)` | Lookup direct client |
| `get_item_by_code(item_code)` | Lookup direct article |
| `get_cache_stats()` | Statistiques du cache |

### 2. `services/sap_sync_startup.py` (~50 lignes)

**Script de synchronisation automatique au démarrage.**

```python
async def sync_sap_data_if_needed():
    """Synchronise si données > 24h"""
    cache_db = get_sap_cache_db()
    sap_service = get_sap_business_service()

    # Sync clients si besoin
    if cache_db.needs_sync("clients", max_age_hours=24):
        result = await cache_db.sync_clients_from_sap(sap_service)
        # ...

    # Sync articles si besoin
    if cache_db.needs_sync("items", max_age_hours=24):
        result = await cache_db.sync_items_from_sap(sap_service)
        # ...
```

### 3. Modification `main.py`

**Intégration dans le lifespan event :**

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... health checks ...

    # Synchronisation cache SAP (si nécessaire)
    try:
        from services.sap_sync_startup import sync_sap_data_if_needed
        await sync_sap_data_if_needed()
    except Exception as e:
        logger.error(f"❌ Erreur synchronisation cache SAP: {e}")

    yield
```

## Workflow de synchronisation

```
┌─────────────────────────────────────────┐
│  Démarrage Backend (main.py)            │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│  sap_sync_startup.py                    │
│  - Vérifier last_sync                   │
│  - Si > 24h → Sync clients              │
│  - Si > 24h → Sync items                │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│  sap_cache_db.py                        │
│  - Appels API SAP (pagination 100)     │
│  - INSERT INTO sap_clients              │
│  - INSERT INTO sap_items                │
│  - UPDATE sap_sync_metadata             │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│  Base SQLite prête                      │
│  - ~1000 clients                        │
│  - ~10000 articles                      │
│  - Accès instantané (<10ms)             │
└─────────────────────────────────────────┘
```

## Prochaines étapes (TODO)

### ✅ Fait

1. Service cache SQLite créé
2. Script de synchronisation créé
3. Intégration au démarrage

### 🔄 En cours

4. **Adapter `email_matcher.py`** pour utiliser SQLite au lieu de RAM
   - Remplacer `self._clients_cache` par `cache_db.get_all_clients()`
   - Remplacer `self._items_cache[code]` par `cache_db.get_item_by_code(code)`
   - Supprimer `_load_reference_data()`

### ⏳ À faire

5. **Créer endpoint API** pour statistiques cache
   ```python
   @router.get("/api/sap/cache/stats")
   async def get_cache_stats():
       cache_db = get_sap_cache_db()
       return cache_db.get_cache_stats()
   ```

6. **Créer endpoint API** pour forcer resync
   ```python
   @router.post("/api/sap/cache/sync")
   async def force_sync():
       # Force la resynchronisation même si < 24h
       pass
   ```

7. **Dashboard frontend** pour visualiser le cache
   - Dernière sync
   - Nombre de clients/articles
   - Bouton "Forcer sync"

## Performance attendue

| Métrique | Avant (API) | Après (SQLite) | Gain |
|----------|------------|----------------|------|
| Démarrage backend | 30-60s | < 2s | **30x** |
| Lookup client | 50-100ms | < 10ms | **10x** |
| Lookup article | 50-100ms | < 5ms | **20x** |
| Search fuzzy | N/A | < 50ms | ∞ |
| Stabilité | ❌ Timeout | ✅ Local | ∞ |

## Configuration

### Variables d'environnement

Aucune nouvelle variable nécessaire. Utilise la même connexion SAP que `SAPBusinessService`.

### Chemin base de données

```python
DB_PATH = "C:/Users/PPZ/NOVA-SERVER/supplier_tariffs.db"
```

Les tables `sap_clients`, `sap_items` et `sap_sync_metadata` sont ajoutées à la base existante.

## Tests manuels

### 1. Vérifier la base de données

```bash
sqlite3 supplier_tariffs.db "SELECT COUNT(*) FROM sap_clients;"
sqlite3 supplier_tariffs.db "SELECT COUNT(*) FROM sap_items;"
sqlite3 supplier_tariffs.db "SELECT * FROM sap_sync_metadata;"
```

### 2. Tester la synchronisation

```bash
# Redémarrer le backend et surveiller les logs
python main.py

# Devrait afficher :
# [INFO] === Vérification cache SAP ===
# [INFO] 🔄 Synchronisation clients SAP...
# [INFO] ✅ Clients synchronisés : 921 clients importés
# [INFO] 🔄 Synchronisation articles SAP...
# [INFO] ✅ Articles synchronisés : 1547 articles importés
```

### 3. Tester le matching

```python
from services.sap_cache_db import get_sap_cache_db

cache_db = get_sap_cache_db()

# Rechercher SAVERGLASS
clients = cache_db.search_clients("SAVERGLASS", limit=5)
print(clients)

# Rechercher un article
items = cache_db.search_items("2323060165", limit=5)
print(items)

# Stats
stats = cache_db.get_cache_stats()
print(stats)
```

## Maintenance

### Forcer une resynchronisation

```bash
# Supprimer les métadonnées de sync
sqlite3 supplier_tariffs.db "DELETE FROM sap_sync_metadata;"

# Redémarrer le backend → force resync complète
python main.py
```

### Nettoyer le cache

```bash
# Supprimer toutes les données SAP
sqlite3 supplier_tariffs.db "DELETE FROM sap_clients;"
sqlite3 supplier_tariffs.db "DELETE FROM sap_items;"
sqlite3 supplier_tariffs.db "DELETE FROM sap_sync_metadata;"
```

## Notes importantes

1. **Première synchronisation** : La première sync peut prendre 1-2 minutes (chargement initial complet)
2. **Syncs suivantes** : Instantanées si données < 24h
3. **Données en temps réel** : Pour un besoin de données 100% à jour, diminuer `max_age_hours` dans les appels
4. **Base de données** : Taille estimée ~10 MB pour 1000 clients + 10000 articles

## Version

**NOVA-SERVER v2.4.0** - Cache SAP Local (Build 2026-02-11)

---

**Développé pour RONDOT-SAS** | Matching email ultra-rapide avec données SAP locales
