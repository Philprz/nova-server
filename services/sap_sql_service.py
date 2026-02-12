"""
Service pour exécuter des requêtes SQL directes sur SAP B1
Nécessaire pour appeler les fonctions SQL personnalisées comme fn_ITS_GetPriceAnalysis
"""

import os
import logging
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Vérifier si pyodbc est disponible
try:
    import pyodbc
    PYODBC_AVAILABLE = True
except ImportError:
    PYODBC_AVAILABLE = False
    logger.warning("⚠️ pyodbc non installé - Fonctions SQL SAP non disponibles")


class SAPSQLService:
    """
    Service pour exécuter des requêtes SQL directes sur la base SAP B1
    Utilisé pour appeler des fonctions SQL personnalisées
    """

    def __init__(self):
        self.server = os.getenv("SAP_SQL_SERVER")  # Ex: "localhost\\SQLEXPRESS"
        self.database = os.getenv("SAP_SQL_DATABASE", os.getenv("SAP_CLIENT_RONDOT", os.getenv("SAP_CLIENT")))
        self.username = os.getenv("SAP_SQL_USER", os.getenv("SAP_USER_RONDOT", os.getenv("SAP_USER")))
        self.password = os.getenv("SAP_SQL_PASSWORD", os.getenv("SAP_CLIENT_PASSWORD_RONDOT", os.getenv("SAP_CLIENT_PASSWORD")))

        self._connection = None

        if not PYODBC_AVAILABLE:
            logger.error("❌ pyodbc non disponible - Les fonctions SQL SAP ne fonctionneront pas")
            logger.info("   Installer avec: pip install pyodbc")

        logger.info(f"SAP SQL Service initialized - Server: {self.server}, DB: {self.database}")

    def _get_connection(self):
        """Obtenir ou créer une connexion à la base SAP"""
        if not PYODBC_AVAILABLE:
            raise RuntimeError("pyodbc n'est pas installé. Exécuter: pip install pyodbc")

        if self._connection is None:
            try:
                # Connection string pour SQL Server
                conn_str = (
                    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                    f"SERVER={self.server};"
                    f"DATABASE={self.database};"
                    f"UID={self.username};"
                    f"PWD={self.password};"
                    f"TrustServerCertificate=yes;"
                )

                self._connection = pyodbc.connect(conn_str, timeout=30)
                logger.info(f"✓ Connexion SQL Server établie - Base: {self.database}")

            except Exception as e:
                logger.error(f"❌ Erreur connexion SQL Server: {str(e)}")
                raise

        return self._connection

    def execute_query(self, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        """
        Exécuter une requête SQL et retourner les résultats

        Args:
            query: Requête SQL (avec ? pour les paramètres)
            params: Tuple de paramètres pour la requête

        Returns:
            Liste de dictionnaires représentant les lignes
        """
        if not PYODBC_AVAILABLE:
            logger.warning("⚠️ pyodbc non disponible - Requête ignorée")
            return []

        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            # Récupérer les noms de colonnes
            columns = [column[0] for column in cursor.description] if cursor.description else []

            # Récupérer toutes les lignes
            rows = cursor.fetchall()

            # Convertir en liste de dictionnaires
            results = []
            for row in rows:
                results.append(dict(zip(columns, row)))

            cursor.close()

            logger.debug(f"✓ Requête SQL exécutée - {len(results)} ligne(s) retournée(s)")
            return results

        except Exception as e:
            logger.error(f"❌ Erreur exécution SQL: {str(e)}")
            logger.error(f"   Query: {query}")
            logger.error(f"   Params: {params}")
            raise

    def get_price_analysis(self, item_code: str, card_code: str) -> Optional[Dict[str, Any]]:
        """
        Appeler la fonction SAP fn_ITS_GetPriceAnalysis

        Args:
            item_code: Code article (ItemCode)
            card_code: Code client (CardCode)

        Returns:
            Dictionnaire avec l'analyse de prix, ou None si erreur

        Exemple retour:
            {
                'ItemCode': 'A05161',
                'CardCode': 'C0110',
                'RecommendedPrice': 123.45,
                'LastSalePrice': 120.00,
                'AveragePrice': 121.50,
                'CostPrice': 85.00,
                'Margin': 45.2,
                ...
            }
        """
        if not PYODBC_AVAILABLE:
            logger.warning(f"⚠️ pyodbc non disponible - Prix analysis ignorée pour {item_code}/{card_code}")
            return None

        try:
            # Appeler la fonction SQL
            query = "SELECT * FROM dbo.fn_ITS_GetPriceAnalysis(?, ?)"
            results = self.execute_query(query, (item_code, card_code))

            if results:
                result = results[0]
                logger.info(f"✓ Prix analysis SAP - {item_code}/{card_code} → {result}")
                return result
            else:
                logger.warning(f"⚠️ Aucun résultat de fn_ITS_GetPriceAnalysis pour {item_code}/{card_code}")
                return None

        except Exception as e:
            logger.error(f"❌ Erreur appel fn_ITS_GetPriceAnalysis({item_code}, {card_code}): {str(e)}")
            return None

    def close(self):
        """Fermer la connexion"""
        if self._connection:
            try:
                self._connection.close()
                self._connection = None
                logger.info("✓ Connexion SQL Server fermée")
            except Exception as e:
                logger.error(f"❌ Erreur fermeture connexion: {str(e)}")


# Singleton
_sap_sql_service: Optional[SAPSQLService] = None


def get_sap_sql_service() -> SAPSQLService:
    """Retourner l'instance singleton du service SQL SAP"""
    global _sap_sql_service
    if _sap_sql_service is None:
        _sap_sql_service = SAPSQLService()
    return _sap_sql_service
