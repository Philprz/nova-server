"""
Service de cache local SQLite pour les données SAP (clients + articles)
Synchronisation quotidienne automatique au démarrage
"""

import os
import json
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
                Street TEXT,
                City TEXT,
                Country TEXT,
                ZipCode TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Migration : ajouter ZipCode si absent (DB existante)
        try:
            cursor.execute("ALTER TABLE sap_clients ADD COLUMN ZipCode TEXT")
        except Exception:
            pass  # Colonne déjà présente
        # Migration : ajouter Street si absent (DB existante)
        try:
            cursor.execute("ALTER TABLE sap_clients ADD COLUMN Street TEXT")
        except Exception:
            pass  # Colonne déjà présente
        # Migration : ajouter CardType si absent ('C'=client, 'S'=fournisseur)
        try:
            cursor.execute("ALTER TABLE sap_clients ADD COLUMN CardType TEXT DEFAULT 'C'")
        except Exception:
            pass  # Colonne déjà présente

        # Migration : ajouter contact_emails si absent (DB existante)
        # Stocke les emails de ContactEmployees SAP (JSON list) pour le matching domaine
        try:
            cursor.execute("ALTER TABLE sap_clients ADD COLUMN contact_emails TEXT")
        except Exception:
            pass  # Colonne déjà présente

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

        try:
            cursor.execute("ALTER TABLE sap_items ADD COLUMN weight_unit_value REAL")
            logger.info("✅ Colonne weight_unit_value ajoutée à sap_items")
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

            logger.info("🔄 Synchronisation clients + fournisseurs SAP → SQLite...")

            async def _fetch_all(card_filter: str) -> list:
                """Récupère tous les BP d'un type donné avec pagination."""
                records, skip, batch_count = [], 0, 0
                while True:
                    if batch_count > 0 and batch_count % 2 == 0:
                        await sap_service.login()
                    batch_data = await sap_service._call_sap("/BusinessPartners", params={
                        "$select": "CardCode,CardName,EmailAddress,Phone1,Address,City,Country,ZipCode",
                        "$filter": card_filter,
                        "$top": 20,
                        "$skip": skip,
                        "$orderby": "CardCode"
                    })
                    batch = batch_data.get("value", [])
                    if not batch:
                        break
                    records.extend(batch)
                    skip += 20
                    batch_count += 1
                    await asyncio.sleep(0.3)
                    if len(batch) < 20:
                        break
                return records

            all_customers = await _fetch_all("CardType eq 'cCustomer'")
            logger.info(f"  → {len(all_customers)} clients récupérés")
            all_suppliers = await _fetch_all("CardType eq 'cSupplier'")
            logger.info(f"  → {len(all_suppliers)} fournisseurs récupérés")

            # ── Insertion atomique ────────────────────────────────────────────
            cursor.execute("SAVEPOINT sync_clients_sp")
            try:
                cursor.execute("DELETE FROM sap_clients")
                now_iso = datetime.now().isoformat()

                def _insert(client: dict, card_type: str):
                    card_name = client.get("CardName") or client.get("CardCode") or "Unknown"
                    contacts = client.get("ContactEmployees") or []
                    seen_ce: set = set()
                    contact_email_list = []
                    for contact in contacts:
                        ce = (contact.get("E_Mail") or "").strip().lower()
                        if ce and "@" in ce and ce not in seen_ce:
                            contact_email_list.append(ce)
                            seen_ce.add(ce)
                    cursor.execute("""
                        INSERT INTO sap_clients
                        (CardCode, CardName, EmailAddress, Phone1, Street, City, Country, ZipCode,
                         CardType, contact_emails, last_updated)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        client.get("CardCode"), card_name,
                        client.get("EmailAddress"), client.get("Phone1"),
                        client.get("Address"), client.get("City"),
                        client.get("Country"), client.get("ZipCode"),
                        card_type,
                        json.dumps(contact_email_list) if contact_email_list else None,
                        now_iso,
                    ))

                for c in all_customers:
                    _insert(c, 'C')
                for s in all_suppliers:
                    _insert(s, 'S')

                cursor.execute("RELEASE SAVEPOINT sync_clients_sp")
            except Exception:
                cursor.execute("ROLLBACK TO SAVEPOINT sync_clients_sp")
                raise

            total = len(all_customers) + len(all_suppliers)
            cursor.execute("""
                UPDATE sap_sync_metadata
                SET last_sync = ?, status = 'success', total_records = ?
                WHERE sync_type = ?
            """, (datetime.now().isoformat(), total, sync_type))
            conn.commit()

            logger.info(f"✅ Sync terminée : {len(all_customers)} clients + {len(all_suppliers)} fournisseurs")

            return {
                "success": True,
                "total_records": total,
                "customers": len(all_customers),
                "suppliers": len(all_suppliers),
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
            batch_count = 0
            sync_complete = False  # Flag : sync complète ou partielle

            while True:
                # Reconnexion proactive toutes les 2 requêtes (même raison que sync clients)
                if batch_count > 0 and batch_count % 2 == 0:
                    await sap_service.login()

                # Retry jusqu'à 3 fois en cas d'erreur transitoire (500 SAP au démarrage)
                items_batch = None
                for attempt in range(3):
                    try:
                        items_batch = await sap_service._call_sap("/Items", params={
                            "$select": "ItemCode,ItemName,ItemsGroupCode,AvgStdPrice,SalesUnitWeight",
                            "$filter": "Valid eq 'Y' and Frozen eq 'N'",  # Seulement articles actifs
                            "$top": batch_size,
                            "$skip": skip,
                            "$orderby": "ItemCode"
                        })
                        break  # Succès
                    except Exception as e:
                        if attempt < 2:
                            logger.warning(f"Erreur batch items skip={skip} (tentative {attempt+1}/3) : {e} — retry dans 5s")
                            await asyncio.sleep(5)
                            await sap_service.login()
                        else:
                            logger.error(f"Échec batch items skip={skip} après 3 tentatives : {e} — sync partielle avec {len(all_items)} articles")
                            items_batch = None

                if items_batch is None:
                    break  # Sync partielle : stopper sans supprimer le cache existant

                batch = items_batch.get("value", [])
                if not batch:
                    sync_complete = True
                    break

                all_items.extend(batch)
                skip += batch_size
                batch_count += 1

                await asyncio.sleep(0.3)

                if len(all_items) % 1000 == 0:
                    logger.info(f"   Progress: {len(all_items)} articles récupérés...")

                if len(batch) < batch_size:
                    sync_complete = True
                    break

            if not all_items:
                logger.warning("Aucun article récupéré — conservation du cache existant")
                return {"success": False, "total_records": 0, "error": "Aucun article récupéré depuis SAP"}

            # Sync complète : remplacer entièrement le cache
            # Sync partielle : upsert uniquement les articles récupérés (préserver le reste)
            if sync_complete:
                logger.info(f"Sync complète ({len(all_items)} articles) — remplacement du cache")
                cursor.execute("DELETE FROM sap_items")
            else:
                logger.warning(f"Sync partielle ({len(all_items)} articles) — upsert sans supprimer le cache existant")

            for item in all_items:
                # Gérer les ItemName NULL en utilisant ItemCode comme fallback
                item_name = item.get("ItemName") or item.get("ItemCode") or "Unknown"

                # Récupérer le prix (AvgStdPrice = prix moyen standard)
                price = item.get("AvgStdPrice")
                currency = item.get("PurchaseCurrency") or "EUR"

                # Poids unitaire vente (SalesUnitWeight en kg dans SAP B1, unité SalesWeightUnit=3=kg)
                weight = item.get("SalesUnitWeight")
                weight = weight if weight and weight > 0 else None

                cursor.execute("""
                    INSERT OR REPLACE INTO sap_items
                    (ItemCode, ItemName, ItemGroup, Price, Currency, weight_unit_value, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    item.get("ItemCode"),
                    item_name,
                    item.get("ItemsGroupCode"),
                    price,
                    currency,
                    weight,
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

        # Recherche LIKE sur CardName ou EmailAddress — clients uniquement (CardType='C' ou NULL héritage)
        cursor.execute("""
            SELECT * FROM sap_clients
            WHERE (CardName LIKE ? OR EmailAddress LIKE ?)
              AND (CardType = 'C' OR CardType IS NULL)
            LIMIT ?
        """, (f"%{query}%", f"%{query}%", limit))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def search_ship_to(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Recherche adresse de livraison : clients ET fournisseurs SAP."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT CardCode, CardName, Street, City, Country, ZipCode, CardType
            FROM sap_clients
            WHERE CardName LIKE ?
            ORDER BY CardType, CardName
            LIMIT ?
        """, (f"%{query}%", limit))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_client_by_code(self, card_code: str) -> Optional[Dict[str, Any]]:
        """Récupère un client par son CardCode exact (avec adresse complète)."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT CardCode, CardName, EmailAddress, Phone1, Street, City, Country, ZipCode FROM sap_clients WHERE CardCode = ?",
            (card_code,)
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

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

    def search_items_multitoken(self, query: str, min_word_len: int = 4, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Recherche multi-tokens avec stratégie AND → OR de secours.

        Stratégie (du plus précis au plus large) :
          1. AND des 2 tokens les plus longs (très précis, peu de résultats)
          2. AND du token le plus long seul (si étape 1 vide)
          3. OR de tous les tokens (filet de sécurité, limit 50)

        Utilisé pour pré-filtrer les candidats avant le scoring thefuzz.

        Args:
            query       : description produit (ex: "HANDY VII PREMIUM STATION DE CHARGE")
            min_word_len: longueur minimale d'un token (défaut 4)
            limit       : max résultats SQL (défaut 50)
        """
        import re as _re
        import unicodedata as _ud

        # Normalisation légère (minuscules, sans accents, sans ponctuation)
        q = query.lower()
        q = _ud.normalize('NFD', q)
        q = ''.join(c for c in q if _ud.category(c) != 'Mn')
        q = _re.sub(r'[^\w\s]', ' ', q)

        tokens_raw = [w for w in _re.findall(r'\b\w+\b', q) if len(w) >= min_word_len]
        # Déduplique et trie par longueur décroissante (tokens longs = plus discriminants)
        tokens = list(dict.fromkeys(sorted(tokens_raw, key=len, reverse=True)))

        logger.debug("[SEARCH_QUERY] multi-token tokens=%s limit=%d", tokens[:5], limit)

        if not tokens:
            return self.search_items(query, limit=limit)

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        def _run(conditions: str, params: list) -> list:
            cursor.execute(
                f"SELECT * FROM sap_items WHERE {conditions} LIMIT ?",
                params + [limit],
            )
            return [dict(r) for r in cursor.fetchall()]

        results: list = []

        # Étape 1 : AND des 2 tokens les plus longs (haute précision)
        top2 = tokens[:2]
        if len(top2) == 2:
            cond = " AND ".join(["ItemName LIKE ?" for _ in top2])
            results = _run(cond, [f"%{t}%" for t in top2])
            logger.debug("[SQL_RESULTS] AND top-2 %s → %d résultats", top2, len(results))

        # Étape 2 : AND du seul token le plus long (si étape 1 vide)
        if not results and tokens:
            cond = "ItemName LIKE ?"
            results = _run(cond, [f"%{tokens[0]}%"])
            logger.debug("[SQL_RESULTS] AND top-1 '%s' → %d résultats", tokens[0], len(results))

        # Étape 3 : OR de tous les tokens (filet de sécurité)
        if not results:
            all_tok = tokens[:5]
            cond = " OR ".join(["ItemName LIKE ?" for _ in all_tok])
            results = _run(cond, [f"%{t}%" for t in all_tok])
            logger.debug("[SQL_RESULTS] OR all %s → %d résultats", all_tok, len(results))

        conn.close()
        logger.debug("[SQL_RESULTS] total %d candidats pour tokens=%s", len(results), tokens[:5])
        return results

    def search_items_normalized(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Recherche d'articles avec normalisation des codes (suppression tirets et espaces).
        Permet de trouver C391-15LM-SPARE depuis C391-15-LM, ou C315-6305 RS depuis C315-6305RS.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Normaliser la requête : supprimer tirets et espaces
        query_normalized = query.replace('-', '').replace(' ', '').upper()

        # Cherche dans ItemCode ET ItemName normalisés (les refs fournisseur sont souvent dans ItemName)
        # Note: on supprime aussi les parenthèses pour matcher "523-5135 (2-3)" depuis "523-5135-2-3"
        cursor.execute("""
            SELECT * FROM sap_items
            WHERE REPLACE(REPLACE(REPLACE(REPLACE(UPPER(ItemCode), '-', ''), ' ', ''), '(', ''), ')', '') LIKE ?
               OR REPLACE(REPLACE(REPLACE(REPLACE(UPPER(ItemName), '-', ''), ' ', ''), '(', ''), ')', '') LIKE ?
            LIMIT ?
        """, (f"%{query_normalized}%", f"%{query_normalized}%", limit))

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
