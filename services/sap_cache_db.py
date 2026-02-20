"""
Service de cache local SQLite pour les données SAP (clients + articles)
Synchronisation quotidienne automatique au démarrage
"""

import os
import sqlite3
import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Chemin de la base de données (même répertoire que supplier_tariffs.db)
DB_PATH = Path(__file__).parent.parent / "supplier_tariffs.db"


class SAPCacheDB:
    """
    Gestion du cache local SQLite pour les données SAP.
    Permet un accès ultra-rapide aux clients et articles sans appels API.
    """

    def __init__(self, db_path: str = str(DB_PATH)):
        self.db_path = db_path
        self._init_database()
        logger.info(f"✓ SAPCacheDB initialisé - Base: {db_path}")

    def _init_database(self):
        """Crée les tables si elles n'existent pas."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Table des clients SAP
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sap_clients (
                CardCode TEXT PRIMARY KEY,
                CardName TEXT NOT NULL,
                EmailAddress TEXT,
                Phone1 TEXT,
                City TEXT,
                Country TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Index pour recherche rapide par nom
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_clients_name
            ON sap_clients(CardName COLLATE NOCASE)
        """)

        # Index pour recherche rapide par email
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_clients_email
            ON sap_clients(EmailAddress COLLATE NOCASE)
        """)

        # Table des articles SAP
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sap_items (
                ItemCode TEXT PRIMARY KEY,
                ItemName TEXT NOT NULL,
                ItemGroup INTEGER,
                Price REAL,
                Currency TEXT DEFAULT 'EUR',
                SupplierPrice REAL,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Index pour recherche rapide par nom
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_items_name
            ON sap_items(ItemName COLLATE NOCASE)
        """)

        # Migration : Ajouter colonnes prix si elles n'existent pas (pour bases existantes)
        try:
            cursor.execute("ALTER TABLE sap_items ADD COLUMN Price REAL")
            logger.info("✅ Colonne Price ajoutée à sap_items")
        except sqlite3.OperationalError:
            pass  # Colonne déjà existante

        try:
            cursor.execute("ALTER TABLE sap_items ADD COLUMN Currency TEXT DEFAULT 'EUR'")
            logger.info("✅ Colonne Currency ajoutée à sap_items")
        except sqlite3.OperationalError:
            pass  # Colonne déjà existante

        try:
            cursor.execute("ALTER TABLE sap_items ADD COLUMN SupplierPrice REAL")
            logger.info("✅ Colonne SupplierPrice ajoutée à sap_items")
        except sqlite3.OperationalError:
            pass  # Colonne déjà existante

        # Table de métadonnées de synchronisation
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sap_sync_metadata (
                sync_type TEXT PRIMARY KEY,  -- 'clients' ou 'items'
                last_sync TIMESTAMP,
                total_records INTEGER,
                status TEXT,  -- 'success', 'in_progress', 'failed'
                error_message TEXT
            )
        """)

        conn.commit()
        conn.close()

    def get_last_sync_time(self, sync_type: str) -> Optional[datetime]:
        """Récupère la date de dernière synchronisation."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT last_sync FROM sap_sync_metadata
            WHERE sync_type = ? AND status = 'success'
        """, (sync_type,))

        row = cursor.fetchone()
        conn.close()

        if row and row[0]:
            return datetime.fromisoformat(row[0])
        return None

    def needs_sync(self, sync_type: str, max_age_hours: int = 24) -> bool:
        """Vérifie si une synchronisation est nécessaire."""
        last_sync = self.get_last_sync_time(sync_type)

        if last_sync is None:
            logger.info(f"📋 Sync {sync_type} requise : Aucune donnée en cache")
            return True

        age = datetime.now() - last_sync
        needs_update = age > timedelta(hours=max_age_hours)

        if needs_update:
            logger.info(f"📋 Sync {sync_type} requise : Données datant de {age.total_seconds() / 3600:.1f}h")
        else:
            logger.info(f"✓ Cache {sync_type} à jour : Dernière sync il y a {age.total_seconds() / 3600:.1f}h")

        return needs_update

    async def sync_clients_from_sap(self, sap_service) -> Dict[str, Any]:
        """
        Synchronise les clients depuis SAP vers la base locale.

        Args:
            sap_service: Instance de SAPBusinessService

        Returns:
            Dict avec le statut de la synchronisation
        """
        sync_type = "clients"
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Marquer le début de la sync
            cursor.execute("""
                INSERT OR REPLACE INTO sap_sync_metadata
                (sync_type, last_sync, status, total_records, error_message)
                VALUES (?, ?, 'in_progress', 0, NULL)
            """, (sync_type, datetime.now().isoformat()))
            conn.commit()

            logger.info("🔄 Synchronisation clients SAP → SQLite...")

            # Récupérer tous les clients SAP (avec pagination)
            # IMPORTANT: SAP B1 limite à 20 résultats max par requête (testé avec $top=20/50/100/200)
            all_clients = []
            skip = 0
            batch_size = 20

            while True:
                clients_batch = await sap_service._call_sap("/BusinessPartners", params={
                    "$select": "CardCode,CardName,EmailAddress,Phone1,City,Country",
                    "$filter": "CardType eq 'cCustomer'",  # Seulement les clients (pas les fournisseurs)
                    "$top": batch_size,
                    "$skip": skip,
                    "$orderby": "CardCode"
                })

                batch = clients_batch.get("value", [])
                if not batch:
                    break

                all_clients.extend(batch)
                skip += batch_size

                if len(batch) < batch_size:
                    break

            # Insérer/mettre à jour dans la base locale
            cursor.execute("DELETE FROM sap_clients")  # Nettoyage complet

            for client in all_clients:
                # Gérer les CardName NULL en utilisant CardCode comme fallback
                card_name = client.get("CardName") or client.get("CardCode") or "Unknown"

                cursor.execute("""
                    INSERT INTO sap_clients
                    (CardCode, CardName, EmailAddress, Phone1, City, Country, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    client.get("CardCode"),
                    card_name,
                    client.get("EmailAddress"),
                    client.get("Phone1"),
                    client.get("City"),
                    client.get("Country"),
                    datetime.now().isoformat()
                ))

            # Marquer la fin de la sync
            cursor.execute("""
                UPDATE sap_sync_metadata
                SET last_sync = ?, status = 'success', total_records = ?
                WHERE sync_type = ?
            """, (datetime.now().isoformat(), len(all_clients), sync_type))

            conn.commit()

            logger.info(f"✅ Sync clients terminée : {len(all_clients)} clients importés")

            return {
                "success": True,
                "total_records": len(all_clients),
                "sync_time": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"❌ Erreur sync clients : {e}")

            cursor.execute("""
                UPDATE sap_sync_metadata
                SET status = 'failed', error_message = ?
                WHERE sync_type = ?
            """, (str(e), sync_type))
            conn.commit()

            return {
                "success": False,
                "error": str(e)
            }

        finally:
            conn.close()

    async def sync_items_from_sap(self, sap_service) -> Dict[str, Any]:
        """
        Synchronise les articles depuis SAP vers la base locale.

        Args:
            sap_service: Instance de SAPBusinessService

        Returns:
            Dict avec le statut de la synchronisation
        """
        sync_type = "items"
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Marquer le début de la sync
            cursor.execute("""
                INSERT OR REPLACE INTO sap_sync_metadata
                (sync_type, last_sync, status, total_records, error_message)
                VALUES (?, ?, 'in_progress', 0, NULL)
            """, (sync_type, datetime.now().isoformat()))
            conn.commit()

            logger.info("🔄 Synchronisation articles SAP → SQLite...")
            logger.info("   Filtre: Articles actifs uniquement (Valid=Y, Frozen=N)")

            # Récupérer tous les articles SAP actifs (avec pagination)
            # IMPORTANT: SAP B1 limite à 20 résultats max par requête
            all_items = []
            skip = 0
            batch_size = 20

            while True:
                items_batch = await sap_service._call_sap("/Items", params={
                    "$select": "ItemCode,ItemName,ItemsGroupCode,AvgStdPrice",
                    "$filter": "Valid eq 'Y' and Frozen eq 'N'",  # Seulement articles actifs
                    "$top": batch_size,
                    "$skip": skip,
                    "$orderby": "ItemCode"
                })

                batch = items_batch.get("value", [])
                if not batch:
                    break

                all_items.extend(batch)
                skip += batch_size

                # Pause toutes les 50 requêtes pour ne pas bloquer l'event loop
                if skip % 1000 == 0:
                    logger.info(f"   Progress: {len(all_items)} articles récupérés...")
                    await asyncio.sleep(0)  # Yield control to event loop

                if len(batch) < batch_size:
                    break

            # Insérer/mettre à jour dans la base locale
            cursor.execute("DELETE FROM sap_items")  # Nettoyage complet

            for item in all_items:
                # Gérer les ItemName NULL en utilisant ItemCode comme fallback
                item_name = item.get("ItemName") or item.get("ItemCode") or "Unknown"

                # Récupérer le prix (AvgStdPrice = prix moyen standard)
                price = item.get("AvgStdPrice")
                currency = item.get("PurchaseCurrency") or "EUR"

                cursor.execute("""
                    INSERT INTO sap_items
                    (ItemCode, ItemName, ItemGroup, Price, Currency, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    item.get("ItemCode"),
                    item_name,
                    item.get("ItemsGroupCode"),
                    price,
                    currency,
                    datetime.now().isoformat()
                ))

            # Marquer la fin de la sync
            cursor.execute("""
                UPDATE sap_sync_metadata
                SET last_sync = ?, status = 'success', total_records = ?
                WHERE sync_type = ?
            """, (datetime.now().isoformat(), len(all_items), sync_type))

            conn.commit()

            logger.info(f"✅ Sync articles terminée : {len(all_items)} articles importés")

            return {
                "success": True,
                "total_records": len(all_items),
                "sync_time": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"❌ Erreur sync articles : {e}")

            cursor.execute("""
                UPDATE sap_sync_metadata
                SET status = 'failed', error_message = ?
                WHERE sync_type = ?
            """, (str(e), sync_type))
            conn.commit()

            return {
                "success": False,
                "error": str(e)
            }

        finally:
            conn.close()

    def get_all_clients(self) -> List[Dict[str, Any]]:
        """Récupère tous les clients depuis le cache local."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM sap_clients")
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_all_items(self) -> List[Dict[str, Any]]:
        """Récupère tous les articles depuis le cache local."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM sap_items")
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def search_clients(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Recherche de clients par nom ou email (fuzzy).

        Args:
            query: Terme de recherche
            limit: Nombre max de résultats

        Returns:
            Liste de clients matchés
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Recherche LIKE sur CardName ou EmailAddress
        cursor.execute("""
            SELECT * FROM sap_clients
            WHERE CardName LIKE ? OR EmailAddress LIKE ?
            LIMIT ?
        """, (f"%{query}%", f"%{query}%", limit))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def search_items(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Recherche d'articles par code ou nom.

        Args:
            query: Terme de recherche
            limit: Nombre max de résultats

        Returns:
            Liste d'articles matchés
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Recherche LIKE sur ItemCode ou ItemName
        cursor.execute("""
            SELECT * FROM sap_items
            WHERE ItemCode LIKE ? OR ItemName LIKE ?
            LIMIT ?
        """, (f"%{query}%", f"%{query}%", limit))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_client_by_code(self, card_code: str) -> Optional[Dict[str, Any]]:
        """Récupère un client par son CardCode."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM sap_clients WHERE CardCode = ?", (card_code,))
        row = cursor.fetchone()
        conn.close()

        return dict(row) if row else None

    def get_item_by_code(self, item_code: str) -> Optional[Dict[str, Any]]:
        """Récupère un article par son ItemCode."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM sap_items WHERE ItemCode = ?", (item_code,))
        row = cursor.fetchone()
        conn.close()

        return dict(row) if row else None

    def get_cache_stats(self) -> Dict[str, Any]:
        """Récupère les statistiques du cache."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Compter clients
        cursor.execute("SELECT COUNT(*) FROM sap_clients")
        total_clients = cursor.fetchone()[0]

        # Compter articles
        cursor.execute("SELECT COUNT(*) FROM sap_items")
        total_items = cursor.fetchone()[0]

        # Récupérer metadata sync
        cursor.execute("SELECT * FROM sap_sync_metadata")
        sync_data = {row[0]: dict(zip(["sync_type", "last_sync", "total_records", "status", "error_message"], row))
                     for row in cursor.fetchall()}

        conn.close()

        return {
            "total_clients": total_clients,
            "total_items": total_items,
            "clients_sync": sync_data.get("clients"),
            "items_sync": sync_data.get("items")
        }


# Singleton
_sap_cache_db: Optional[SAPCacheDB] = None


def get_sap_cache_db() -> SAPCacheDB:
    """Retourne l'instance singleton du cache SAP."""
    global _sap_cache_db
    if _sap_cache_db is None:
        _sap_cache_db = SAPCacheDB()
    return _sap_cache_db
