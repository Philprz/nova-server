# Transport & Colisage NOVA

## Architecture

```
services/
  packing/
    __init__.py
    box_catalog.py          # Catalogue des 4 types de colis
    packing_algorithm.py    # Algorithme First Fit Decreasing (FFD)
    packing_service.py      # Service principal + enrichissement DB

  transport/
    __init__.py
    carrier_interface.py    # Interface abstraite CarrierAdapter
    transport_service.py    # Orchestrateur multi-carrier

    carriers/
      __init__.py
      dhl_adapter.py        # Adapter DHL Express (MyDHL API)

routes/
  routes_packing.py         # POST /api/packing/calculate
  routes_shipping.py        # POST /api/shipping/quote

tests/unit/
  test_packing.py
  test_dhl_api.py
```

---

## Pipeline métier

```
Produits (item_code, quantité, dimensions)
        ↓
PackingService.suggest_packages()
  → Résolution dimensions depuis supplier_tariffs.db
  → Algorithme FFD
        ↓
PackingResponse
  → packages[] (colis calculés)
  → dhl_packages[] (payload DHL prêt)
  → summary (texte lisible)
        ↓
[Validation utilisateur : Valider | Modifier]
        ↓
TransportService.calculate_shipping()
  → DHLCarrierAdapter.get_rate()
  → Cache TTL 5 min
        ↓
ShippingResponse
  → rates[] (tous les services DHL)
  → best_rate (tarif le moins cher)
  → delivery_days
        ↓
Prix final devis = coût_produits + marge + transport
```

---

## Algorithme de colisage — First Fit Decreasing

### Principe

1. **Développer** les articles (quantité > 1 → N unités individuelles)
2. **Trier** par volume décroissant (plus grand en premier)
3. Pour chaque article : **premier colis ouvert** qui peut l'accueillir
4. Si aucun ne convient : **ouvrir un nouveau colis** (le plus petit adapté)

### Catalogue des boîtes

| Type    | L × W × H (cm)   | Poids max | Volume      |
|---------|-------------------|-----------|-------------|
| S       | 30 × 20 × 20      | 10 kg     | 12 000 cm³  |
| M       | 60 × 40 × 40      | 25 kg     | 96 000 cm³  |
| L       | 80 × 60 × 60      | 40 kg     | 288 000 cm³ |
| PALLET  | 120 × 80 × 150    | 500 kg    | 1 440 000 cm³ |

### Marge de sécurité

Le volume utilisable est limité à **85 %** du volume du colis (calage, emballage de protection).

### Comportement avec dimensions inconnues

Si les dimensions d'un article ne sont pas fournies dans la requête, le service tente
de les résupérer depuis `supplier_tariffs.db` (`supplier_products.dimensions` en JSON,
`supplier_products.weight`).

Valeurs par défaut si toujours absentes :
- Poids : 1 kg
- Dimensions : 20 × 15 × 10 cm (colis S garanti)

---

## API DHL Express

### Authentification

```
Basic Auth
Username : rondotFR
Password : H$3xI$7rU@1kB^9z
Compte   : 220294850
```

### Endpoints

```
TEST : https://express.api.dhl.com/mydhlapi/test/rates
PROD : https://express.api.dhl.com/mydhlapi/rates
```

L'environnement par défaut est **TEST**. Pour basculer :

```http
POST /api/shipping/dhl/switch-env?use_production=true
```

Ou via variable d'environnement :

```env
DHL_USE_TEST_ENV=false
```

### Expéditeur par défaut

```
Rondot SAS — Marseille
postalCode : 13002
cityName   : MARSEILLE
countryCode: FR
```

### Exemple de payload DHL généré

```json
{
  "customerDetails": {
    "shipperDetails": {
      "postalCode": "13002",
      "cityName": "MARSEILLE",
      "countryCode": "FR"
    },
    "receiverDetails": {
      "postalCode": "DUBAI",
      "cityName": "DUBAI",
      "countryCode": "AE"
    }
  },
  "accounts": [{"typeCode": "shipper", "number": "220294850"}],
  "plannedShippingDateAndTime": "2026-03-05T16:00:00GMT+00:00",
  "unitOfMeasurement": "metric",
  "isCustomsDeclarable": true,
  "monetaryAmount": [{"typeCode": "declaredValue", "value": 500, "currency": "EUR"}],
  "requestAllValueAddedServices": false,
  "returnStandardProductsOnly": true,
  "nextBusinessDay": true,
  "packages": [
    {"weight": 10.0, "dimensions": {"length": 60, "width": 40, "height": 40}}
  ]
}
```

### Cache

- TTL : 5 minutes
- Clé : hash(destination + poids_total + volume_total)
- Taille max : 100 entrées (FIFO)

### Retry

- Max 2 tentatives sur timeout HTTP
- Pas de retry sur erreurs 4xx (erreur payload ou auth)

---

## Endpoints API

### POST /api/packing/calculate

Calcule le colisage pour une liste d'articles.

**Requête** :
```json
{
  "items": [
    {
      "item_code": "REF-001",
      "quantity": 3,
      "weight_kg": 2.0,
      "length_cm": 25.0,
      "width_cm": 18.0,
      "height_cm": 12.0
    }
  ]
}
```

**Réponse** :
```json
{
  "success": true,
  "packages": [...],
  "total_weight_kg": 6.0,
  "total_volume_m3": 0.0162,
  "box_count": 1,
  "summary": "Suggestion colisage :\n  • 1 × Colis S\n  Poids total : 6.00 kg",
  "warnings": [],
  "dhl_packages": [
    {"weight": 6.0, "dimensions": {"length": 30, "width": 20, "height": 20}}
  ]
}
```

### GET /api/packing/box-types

Retourne le catalogue des colis.

### POST /api/packing/calculate-and-ship

Enchaîne colisage + tarif DHL en une seule requête.

**Query params** :
- `destination_postal_code`
- `destination_city`
- `destination_country` (défaut: FR)
- `declared_value` (défaut: 100.0)

### POST /api/shipping/quote

Calcule le tarif transport pour des colis déjà calculés.

**Requête** :
```json
{
  "packages": [
    {"weight": 10.0, "dimensions": {"length": 60, "width": 40, "height": 40}}
  ],
  "destination": {
    "postal_code": "75001",
    "city_name": "PARIS",
    "country_code": "FR"
  },
  "declared_value": 500.0,
  "currency": "EUR"
}
```

### POST /api/shipping/dhl/test

Teste la connectivité DHL avec un colis factice (Marseille → Paris).

### GET /api/carriers

Liste les transporteurs disponibles.

---

## Ajouter un nouveau transporteur

1. Créer `services/transport/carriers/<nom>_adapter.py`

```python
from services.transport.carrier_interface import CarrierAdapter, ShippingRate

class ChronopostAdapter(CarrierAdapter):
    @property
    def carrier_name(self) -> str:
        return "Chronopost"

    def is_available(self) -> bool:
        return bool(os.getenv("CHRONOPOST_API_KEY"))

    async def get_rate(self, packages, destination, shipper=None, ...) -> List[ShippingRate]:
        # Appel API Chronopost
        ...
```

2. L'enregistrer dans `TransportService._register_default_carriers()` :

```python
from .carriers.chronopost_adapter import ChronopostAdapter
self._carriers["chronopost"] = ChronopostAdapter()
```

3. L'appeler avec `carrier="chronopost"` ou `carrier="all"`.

---

## Variables d'environnement

```env
# DHL Express
DHL_USERNAME=rondotFR
DHL_PASSWORD=H$3xI$7rU@1kB^9z
DHL_ACCOUNT_NUMBER=220294850
DHL_SHIPPER_POSTAL=13002
DHL_SHIPPER_CITY=MARSEILLE
DHL_SHIPPER_COUNTRY=FR
DHL_USE_TEST_ENV=true          # false = production
DHL_TIMEOUT_SECONDS=15
DHL_CACHE_TTL_SECONDS=300
DHL_MAX_RETRIES=2
```

---

## Exécution des tests

```bash
# Tests unitaires uniquement (sans appel réseau)
pytest tests/unit/test_packing.py -v
pytest tests/unit/test_dhl_api.py -v -k "not integration"

# Tests d'intégration (réseau + API DHL TEST requis)
pytest tests/unit/test_dhl_api.py -v -m integration
```
