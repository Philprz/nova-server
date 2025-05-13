# Outils MCP NOVA

## Salesforce
- `ping` - Test simple de disponibilité
- `salesforce.query(query: str)` - Exécute une requête SOQL
  Exemple: `salesforce.query("SELECT Id, Name FROM Account LIMIT 5")`
- `salesforce.inspect(object_name: str)` - Liste les champs d'un objet
  Exemple: `salesforce.inspect("Account")`

## SAP
- `ping` - Test simple de disponibilité 
- `sap.read(endpoint: str)` - Lit des données SAP via API REST
  Exemple: `sap.read("/Items")`