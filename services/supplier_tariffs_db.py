"""
Module de gestion de la base SQLite pour les tarifs fournisseurs.
Stocke les données indexées des fichiers de tarifs.
"""

import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Optional, Any
from pathlib import Path
import logging
import json

logger = logging.getLogger(__name__)

# Chemin de la base de données
DB_PATH = Path(__file__).parent.parent / "data" / "supplier_tariffs.db"


def get_connection() -> sqlite3.Connection:
    """Crée une connexion à la base SQLite."""
    # Créer le dossier data s'il n'existe pas
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """Initialise la base de données avec les tables nécessaires."""
    conn = get_connection()
    cursor = conn.cursor()

    # Table des fichiers indexés
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS indexed_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT UNIQUE NOT NULL,
            file_name TEXT NOT NULL,
            file_type TEXT NOT NULL,
            file_size INTEGER,
            last_modified TIMESTAMP,
            indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'indexed',
            error_message TEXT,
            items_count INTEGER DEFAULT 0
        )
    """)

    # Table des produits/tarifs extraits
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS supplier_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            supplier_reference TEXT,
            designation TEXT,
            unit_price REAL,
            currency TEXT DEFAULT 'EUR',
            delivery_time TEXT,
            supplier_name TEXT,
            category TEXT,
            brand TEXT,
            min_quantity INTEGER,
            additional_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            -- Nouveaux champs pour métadonnées enrichies
            delivery_days INTEGER,
            transport_cost REAL,
            transport_days INTEGER,
            weight REAL,
            dimensions TEXT,
            technical_specs TEXT,
            stock_availability TEXT,
            supplier_code TEXT,

            FOREIGN KEY (file_id) REFERENCES indexed_files(id) ON DELETE CASCADE
        )
    """)

    # Migration : Ajouter les nouvelles colonnes si elles n'existent pas déjà
    try:
        cursor.execute("SELECT delivery_days FROM supplier_products LIMIT 1")
    except sqlite3.OperationalError:
        # Les colonnes n'existent pas, les ajouter
        logger.info("Migration: Ajout des nouvelles colonnes métadonnées")
        cursor.execute("ALTER TABLE supplier_products ADD COLUMN delivery_days INTEGER")
        cursor.execute("ALTER TABLE supplier_products ADD COLUMN transport_cost REAL")
        cursor.execute("ALTER TABLE supplier_products ADD COLUMN transport_days INTEGER")
        cursor.execute("ALTER TABLE supplier_products ADD COLUMN weight REAL")
        cursor.execute("ALTER TABLE supplier_products ADD COLUMN dimensions TEXT")
        cursor.execute("ALTER TABLE supplier_products ADD COLUMN technical_specs TEXT")
        cursor.execute("ALTER TABLE supplier_products ADD COLUMN stock_availability TEXT")
        cursor.execute("ALTER TABLE supplier_products ADD COLUMN supplier_code TEXT")

    # Table de configuration de l'indexation
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS indexation_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Table d'historique des indexations
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS indexation_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            status TEXT DEFAULT 'running',
            files_processed INTEGER DEFAULT 0,
            files_success INTEGER DEFAULT 0,
            files_error INTEGER DEFAULT 0,
            items_extracted INTEGER DEFAULT 0,
            error_message TEXT
        )
    """)

    # Index pour améliorer les performances de recherche
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_supplier_products_reference
        ON supplier_products(supplier_reference)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_supplier_products_designation
        ON supplier_products(designation)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_supplier_products_supplier
        ON supplier_products(supplier_name)
    """)

    conn.commit()
    conn.close()
    logger.info(f"Base de données initialisée: {DB_PATH}")


def add_indexed_file(file_path: str, file_name: str, file_type: str,
                     file_size: int, last_modified: datetime) -> int:
    """Ajoute ou met à jour un fichier indexé."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO indexed_files (file_path, file_name, file_type, file_size, last_modified, indexed_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(file_path) DO UPDATE SET
            file_name = excluded.file_name,
            file_type = excluded.file_type,
            file_size = excluded.file_size,
            last_modified = excluded.last_modified,
            indexed_at = CURRENT_TIMESTAMP,
            status = 'indexed',
            error_message = NULL
    """, (file_path, file_name, file_type, file_size, last_modified, datetime.now()))

    file_id = cursor.lastrowid
    if file_id == 0:
        cursor.execute("SELECT id FROM indexed_files WHERE file_path = ?", (file_path,))
        file_id = cursor.fetchone()[0]

    conn.commit()
    conn.close()
    return file_id


def update_file_status(file_id: int, status: str, error_message: str = None, items_count: int = 0):
    """Met à jour le statut d'un fichier indexé."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE indexed_files
        SET status = ?, error_message = ?, items_count = ?
        WHERE id = ?
    """, (status, error_message, items_count, file_id))

    conn.commit()
    conn.close()


def add_supplier_product(file_id: int, product_data: Dict[str, Any]) -> int:
    """Ajoute un produit fournisseur extrait avec métadonnées enrichies."""
    conn = get_connection()
    cursor = conn.cursor()

    additional_data = json.dumps(product_data.get('additional_data', {})) if product_data.get('additional_data') else None

    cursor.execute("""
        INSERT INTO supplier_products
        (file_id, supplier_reference, designation, unit_price, currency,
         delivery_time, supplier_name, category, brand, min_quantity, additional_data,
         delivery_days, transport_cost, transport_days, weight, dimensions,
         technical_specs, stock_availability, supplier_code)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        file_id,
        product_data.get('supplier_reference'),
        product_data.get('designation'),
        product_data.get('unit_price'),
        product_data.get('currency', 'EUR'),
        product_data.get('delivery_time'),
        product_data.get('supplier_name'),
        product_data.get('category'),
        product_data.get('brand'),
        product_data.get('min_quantity'),
        additional_data,
        # Nouveaux champs métadonnées
        product_data.get('delivery_days'),
        product_data.get('transport_cost'),
        product_data.get('transport_days'),
        product_data.get('weight'),
        product_data.get('dimensions'),
        product_data.get('technical_specs'),
        product_data.get('stock_availability'),
        product_data.get('supplier_code')
    ))

    product_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return product_id


def add_supplier_products_batch(file_id: int, products: List[Dict[str, Any]]) -> int:
    """Ajoute plusieurs produits en une seule transaction avec métadonnées enrichies."""
    conn = get_connection()
    cursor = conn.cursor()

    # Supprimer les anciens produits de ce fichier
    cursor.execute("DELETE FROM supplier_products WHERE file_id = ?", (file_id,))

    for product in products:
        additional_data = json.dumps(product.get('additional_data', {})) if product.get('additional_data') else None

        cursor.execute("""
            INSERT INTO supplier_products
            (file_id, supplier_reference, designation, unit_price, currency,
             delivery_time, supplier_name, category, brand, min_quantity, additional_data,
             delivery_days, transport_cost, transport_days, weight, dimensions,
             technical_specs, stock_availability, supplier_code)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            file_id,
            product.get('supplier_reference'),
            product.get('designation'),
            product.get('unit_price'),
            product.get('currency', 'EUR'),
            product.get('delivery_time'),
            product.get('supplier_name'),
            product.get('category'),
            product.get('brand'),
            product.get('min_quantity'),
            additional_data,
            # Nouveaux champs métadonnées
            product.get('delivery_days'),
            product.get('transport_cost'),
            product.get('transport_days'),
            product.get('weight'),
            product.get('dimensions'),
            product.get('technical_specs'),
            product.get('stock_availability'),
            product.get('supplier_code')
        ))

    conn.commit()
    conn.close()
    return len(products)


def search_products(query: str, limit: int = 50) -> List[Dict]:
    """Recherche des produits par référence ou désignation."""
    conn = get_connection()
    cursor = conn.cursor()

    search_term = f"%{query}%"
    cursor.execute("""
        SELECT sp.*, if.file_name, if.file_path
        FROM supplier_products sp
        JOIN indexed_files if ON sp.file_id = if.id
        WHERE sp.supplier_reference LIKE ?
           OR sp.designation LIKE ?
           OR sp.supplier_name LIKE ?
        LIMIT ?
    """, (search_term, search_term, search_term, limit))

    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def get_all_products(limit: int = 1000, offset: int = 0) -> List[Dict]:
    """Récupère tous les produits indexés."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT sp.*, if.file_name, if.file_path
        FROM supplier_products sp
        JOIN indexed_files if ON sp.file_id = if.id
        ORDER BY sp.created_at DESC
        LIMIT ? OFFSET ?
    """, (limit, offset))

    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def get_indexed_files() -> List[Dict]:
    """Récupère la liste des fichiers indexés."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM indexed_files ORDER BY indexed_at DESC
    """)

    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def get_indexation_stats() -> Dict:
    """Récupère les statistiques d'indexation."""
    conn = get_connection()
    cursor = conn.cursor()

    # Nombre total de fichiers
    cursor.execute("SELECT COUNT(*) as count FROM indexed_files")
    total_files = cursor.fetchone()['count']

    # Fichiers par statut
    cursor.execute("""
        SELECT status, COUNT(*) as count
        FROM indexed_files
        GROUP BY status
    """)
    files_by_status = {row['status']: row['count'] for row in cursor.fetchall()}

    # Nombre total de produits
    cursor.execute("SELECT COUNT(*) as count FROM supplier_products")
    total_products = cursor.fetchone()['count']

    # Dernière indexation
    cursor.execute("""
        SELECT * FROM indexation_history
        ORDER BY started_at DESC LIMIT 1
    """)
    last_indexation = cursor.fetchone()

    conn.close()

    return {
        'total_files': total_files,
        'files_by_status': files_by_status,
        'total_products': total_products,
        'last_indexation': dict(last_indexation) if last_indexation else None
    }


def start_indexation() -> int:
    """Démarre une nouvelle session d'indexation."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO indexation_history (started_at, status)
        VALUES (?, 'running')
    """, (datetime.now(),))

    session_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return session_id


def update_indexation_session(session_id: int, status: str,
                               files_processed: int = 0, files_success: int = 0,
                               files_error: int = 0, items_extracted: int = 0,
                               error_message: str = None):
    """Met à jour une session d'indexation."""
    conn = get_connection()
    cursor = conn.cursor()

    completed_at = datetime.now() if status in ['completed', 'error'] else None

    cursor.execute("""
        UPDATE indexation_history
        SET status = ?, completed_at = ?, files_processed = ?,
            files_success = ?, files_error = ?, items_extracted = ?,
            error_message = ?
        WHERE id = ?
    """, (status, completed_at, files_processed, files_success,
          files_error, items_extracted, error_message, session_id))

    conn.commit()
    conn.close()


def clear_all_data():
    """Supprime toutes les données indexées (pour réindexation complète)."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM supplier_products")
    cursor.execute("DELETE FROM indexed_files")

    conn.commit()
    conn.close()
    logger.info("Toutes les données indexées ont été supprimées")


# Initialiser la base au chargement du module
init_database()
