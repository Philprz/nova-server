# Outils de diagnostic et liste des produits SAP

Ce dossier contient des utilitaires pour lister et analyser les produits dans SAP Business One.

## Fichiers disponibles

### 1. `list_sap_products.py`
Script principal pour lister tous les produits SAP avec analyse détaillée des champs.

**Usage:**
```bash
# Lister 100 produits (par défaut)
python list_sap_products.py

# Lister 500 produits
python list_sap_products.py --limit 500

# Chercher des imprimantes
python list_sap_products.py --search "printer"

# Exporter en JSON
python list_sap_products.py --limit 1000 --format json --output produits.json

# Exporter en CSV
python list_sap_products.py --limit 1000 --format csv --output produits.csv
```

**Fonctionnalités:**
- Liste tous les produits avec leurs champs
- Analyse statistique des champs (taux de remplissage, types, exemples)
- Export en JSON ou CSV
- Recherche par terme

### 2. `utils/sap_product_utils.py`
Module Python avec fonctions utilitaires pour une utilisation dans des scripts ou notebooks.

**Usage dans Python/Notebook:**
```python
from utils.sap_product_utils import get_sap_products, analyze_sap_catalog

# Récupérer 50 produits
df = get_sap_products(50)
print(df)

# Chercher des produits
df = get_sap_products(search="printer")

# Voir tous les champs
df = get_sap_products(20, all_fields=True)

# Analyser le catalogue
analysis = analyze_sap_catalog(limit=200)
```

**Fonctionnalités:**
- Retourne un DataFrame pandas
- Recherche multi-champs
- Analyse statistique des champs
- Wrappers synchrones pour faciliter l'utilisation

### 3. `diagnostic_sap_products.py`
Script de diagnostic pour identifier pourquoi certains produits ne sont pas trouvés.

**Usage:**
```bash
python diagnostic_sap_products.py
```

**Fonctionnalités:**
- Test de connexion SAP
- Analyse de la structure des produits
- Recherche avec différentes stratégies
- Identification des groupes de produits
- Recommandations pour améliorer les recherches

## Exemples de problèmes résolus

### Problème : "Imprimante 20 ppm" non trouvée

Le diagnostic a identifié plusieurs causes possibles :

1. **Nom exact différent** : Le produit pourrait s'appeler différemment dans SAP (ex: "Printer 20ppm", "Imprimante laser 20 ppm", etc.)

2. **Champs de recherche** : La recherche standard ne cherche que dans certains champs. Le produit pourrait avoir ces infos dans d'autres champs.

3. **Groupes de produits** : Les imprimantes pourraient être dans un groupe spécifique qu'il faut identifier.

### Solutions recommandées

1. **Utiliser le script de diagnostic** pour identifier les noms exacts :
   ```bash
   python diagnostic_sap_products.py
   ```

2. **Lister tous les produits** et filtrer manuellement :
   ```bash
   python list_sap_products.py --limit 1000 --format csv --output all_products.csv
   ```
   Puis ouvrir dans Excel et chercher "ppm", "print", etc.

3. **Recherche par groupe** si vous connaissez le code groupe :
   ```python
   from utils.sap_product_utils import get_sap_products
   df = get_sap_products(1000)
   # Filtrer par groupe
   printers = df[df['ItemsGroupCode'] == '105']  # Exemple
   ```

## Champs SAP importants

D'après l'analyse, voici les champs clés pour les produits :

- `ItemCode` : Code unique du produit
- `ItemName` : Nom du produit
- `U_Description` : Description détaillée (champ personnalisé)
- `U_PrixCatalogue` : Prix catalogue
- `QuantityOnStock` / `OnHand` : Stock disponible
- `ItemsGroupCode` : Code du groupe de produits
- `BarCode` : Code-barres
- `Manufacturer` : Fabricant

## Notes importantes

1. La connexion SAP doit être configurée correctement (variables d'environnement)
2. Les champs personnalisés (U_*) varient selon l'installation SAP
3. La recherche est sensible à la casse sauf si spécifié autrement
4. Certains produits peuvent être inactifs (vérifier le champ `Valid`)