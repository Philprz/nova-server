
# Documentation des outils MCP NOVA

Cette documentation décrit les outils MCP (Model Context Protocol) disponibles dans le projet NOVA. Ces outils permettent à Claude d'interagir avec Salesforce et SAP Business One pour récupérer ou manipuler des données.

## Outils Salesforce

### `ping`
Test simple de disponibilité du serveur MCP Salesforce.

```bash
ping
```

### `salesforce.query`
Exécute une requête SOQL sur Salesforce.

```bash
salesforce.query("SELECT Id, Name FROM Account LIMIT 5")
```

### `salesforce.inspect`
Liste les objets et champs Salesforce depuis le cache.

```bash
salesforce.inspect()         # Liste tous les objets
salesforce.inspect("Account")  # Détails d'un objet spécifique
```

### `salesforce.refresh_metadata`
Force la mise à jour des métadonnées Salesforce.

```bash
salesforce.refresh_metadata()  # Rafraîchit tous les objets
salesforce.refresh_metadata(["Account", "Contact"])  # Rafraîchit des objets spécifiques
```

## Outils SAP

### `ping`
Test simple de disponibilité du serveur MCP SAP.

```bash
ping
```

### `sap.read`
Lecture de données SAP B1 via l'API REST.

```bash
sap.read("/Items")  # Liste des articles
sap.read("/BusinessPartners")  # Liste des partenaires commerciaux
sap.read("/Items('A1001')")  # Détails d'un article spécifique
```

### `sap.inspect`
Liste les endpoints SAP disponibles depuis le cache.

```bash
sap.inspect()
```

### `sap.refresh_metadata`
Force la mise à jour des endpoints SAP.

```bash
sap.refresh_metadata()
```

### `sap.search`
Recherche dans SAP.

```bash
sap.search("Laptop", "Items", 5)  # Recherche "Laptop" dans les articles, limite à 5 résultats
```

### `sap.get_product_details`
Récupère les détails d'un produit.

```bash
sap.get_product_details("A1001")
```

### `sap.check_product_availability`
Vérifie la disponibilité d'un produit.

```bash
sap.check_product_availability("A1001", 10)  # Vérifie si 10 unités sont disponibles
```

### `sap.find_alternatives`
Trouve des produits alternatifs pour un produit donné.

```bash
sap.find_alternatives("A1001")
```

### `sap.create_draft_order`
Crée un brouillon de commande dans SAP.

```bash
sap.create_draft_order("C1001", [
  {"ItemCode": "A1001", "Quantity": 5, "Price": 100},
  {"ItemCode": "A1002", "Quantity": 2, "Price": 150}
])
```

## Exemples d'utilisation combinée

### Création d'un devis à partir d'une description en langage naturel

1. Extraire les informations clés (client, produits, quantités).
2. Vérifier l'existence du client avec `salesforce.query()`.
3. Vérifier la disponibilité des produits avec `sap.check_product_availability()`.
4. Proposer des alternatives si nécessaire avec `sap.find_alternatives()`.
5. Créer un brouillon de commande avec `sap.create_draft_order()`.
6. Créer l'opportunité dans Salesforce avec `salesforce.query()`.
