"""
Helpers de sécurité pour les interpolations dans les requêtes SOQL (Salesforce)
et OData (SAP Business One). À importer partout où une variable utilisateur
est interpolée dans une requête.
"""


def escape_soql(value: str) -> str:
    """Échappe une valeur pour interpolation dans une clause SOQL.
    Ordre critique : backslashes en premier, puis apostrophes."""
    if value is None:
        return ""
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


def escape_odata(value: str) -> str:
    """Échappe une valeur pour interpolation dans un filtre OData SAP B1.
    Doublement de l'apostrophe selon la spec OData v4."""
    if value is None:
        return ""
    return str(value).replace("'", "''")


def safe_int(value, default: int = 0, max_value: int = 1000) -> int:
    """Cast int avec borne haute pour les paramètres LIMIT/TOP/SKIP.
    Protège contre les injections via paramètres numériques."""
    try:
        v = int(value)
        return min(max(v, 0), max_value)
    except (ValueError, TypeError):
        return default
