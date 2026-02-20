"""
Base de données SQLite pour audit des décisions pricing
Extension de supplier_tariffs.db
"""

import sqlite3
import json
import logging
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Optional
from services.pricing_models import PricingDecision, PricingCaseType

logger = logging.getLogger(__name__)

# Utiliser la même base que supplier_tariffs
DB_PATH = Path(__file__).parent.parent / "data" / "supplier_tariffs.db"


def get_database_path() -> str:
    """Retourne le chemin de la base de données"""
    return str(DB_PATH)


def get_connection() -> sqlite3.Connection:
    """Crée une connexion à la base SQLite"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_pricing_audit_tables():
    """Initialise les tables d'audit pricing dans la base existante"""
    conn = get_connection()
    cursor = conn.cursor()

    # Table principale : décisions pricing
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pricing_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            decision_id TEXT UNIQUE NOT NULL,
            item_code TEXT NOT NULL,
            card_code TEXT NOT NULL,
            quantity REAL NOT NULL,

            -- CAS appliqué
            case_type TEXT NOT NULL,
            case_description TEXT,

            -- Prix
            calculated_price REAL NOT NULL,
            line_total REAL NOT NULL,
            currency TEXT DEFAULT 'EUR',

            -- Justification
            justification TEXT,
            confidence_score REAL DEFAULT 1.0,

            -- Sources
            supplier_price REAL,
            margin_applied REAL,

            -- Historique référence
            last_sale_date DATE,
            last_sale_price REAL,
            last_sale_doc_num INTEGER,

            -- Variation prix
            price_variation_json TEXT,

            -- Prix moyen autres (CAS 3)
            average_price_others REAL,
            reference_sales_count INTEGER,

            -- Validation
            requires_validation BOOLEAN DEFAULT 0,
            validation_reason TEXT,
            validated_by TEXT,
            validated_at TIMESTAMP,

            -- Alertes
            alerts_json TEXT,

            -- Métadonnées
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT DEFAULT 'pricing_engine',

            -- Intégration devis
            used_in_quote_doc_entry INTEGER,
            used_in_quote_doc_num INTEGER
        )
    """)

    # Index pour recherches
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_pricing_item_code
        ON pricing_decisions(item_code)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_pricing_card_code
        ON pricing_decisions(card_code)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_pricing_case_type
        ON pricing_decisions(case_type)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_pricing_created_at
        ON pricing_decisions(created_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_pricing_requires_validation
        ON pricing_decisions(requires_validation)
    """)

    # Table statistiques pricing (vue matérialisée)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pricing_statistics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE NOT NULL UNIQUE,
            total_decisions INTEGER DEFAULT 0,
            cas_1_count INTEGER DEFAULT 0,
            cas_2_count INTEGER DEFAULT 0,
            cas_3_count INTEGER DEFAULT 0,
            cas_4_count INTEGER DEFAULT 0,
            requiring_validation INTEGER DEFAULT 0,
            avg_margin REAL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()
    logger.info(f"Tables audit pricing initialisées : {DB_PATH}")


def save_pricing_decision(decision: PricingDecision) -> int:
    """
    Sauvegarde une décision pricing dans la base d'audit

    Args:
        decision: Décision de pricing à sauvegarder

    Returns:
        ID de la décision sauvegardée
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Sérialiser objets complexes
        price_variation_json = None
        if decision.price_variation:
            price_variation_json = json.dumps(decision.price_variation.model_dump())

        alerts_json = json.dumps(decision.alerts) if decision.alerts else None

        cursor.execute("""
            INSERT INTO pricing_decisions (
                decision_id, item_code, card_code, quantity,
                case_type, case_description,
                calculated_price, line_total, currency,
                justification, confidence_score,
                supplier_price, margin_applied,
                last_sale_date, last_sale_price, last_sale_doc_num,
                price_variation_json,
                average_price_others, reference_sales_count,
                requires_validation, validation_reason,
                alerts_json,
                created_at, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            decision.decision_id,
            decision.item_code,
            decision.card_code,
            decision.quantity,
            decision.case_type.value,
            decision.case_description,
            decision.calculated_price,
            decision.line_total,
            decision.currency,
            decision.justification,
            decision.confidence_score,
            decision.supplier_price,
            decision.margin_applied,
            decision.last_sale_date,
            decision.last_sale_price,
            decision.last_sale_doc_num,
            price_variation_json,
            decision.average_price_others,
            decision.reference_sales_count,
            decision.requires_validation,
            decision.validation_reason,
            alerts_json,
            decision.created_at,
            decision.created_by
        ))

        decision_id = cursor.lastrowid
        conn.commit()

        # Mettre à jour statistiques
        update_daily_statistics()

        logger.info(f"✓ Décision pricing sauvegardée : {decision.decision_id} ({decision.case_type})")
        return decision_id

    except Exception as e:
        logger.error(f"✗ Erreur sauvegarde décision : {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def get_decision_by_id(decision_id: str) -> Optional[Dict]:
    """Récupère une décision par son ID"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM pricing_decisions WHERE decision_id = ?
    """, (decision_id,))

    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None


def get_pending_validations() -> List[Dict]:
    """Récupère les décisions en attente de validation commerciale"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM pricing_decisions
        WHERE requires_validation = 1
        AND validated_at IS NULL
        ORDER BY created_at DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def mark_decision_validated(decision_id: str, validated_by: str):
    """Marque une décision comme validée"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE pricing_decisions
        SET validated_at = ?, validated_by = ?
        WHERE decision_id = ?
    """, (datetime.now(), validated_by, decision_id))

    conn.commit()
    conn.close()
    logger.info(f"✓ Décision {decision_id} validée par {validated_by}")


def link_decision_to_quote(decision_id: str, doc_entry: int, doc_num: int):
    """Lie une décision pricing à un devis SAP"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE pricing_decisions
        SET used_in_quote_doc_entry = ?, used_in_quote_doc_num = ?
        WHERE decision_id = ?
    """, (doc_entry, doc_num, decision_id))

    conn.commit()
    conn.close()
    logger.info(f"✓ Décision {decision_id} liée au devis {doc_num}")


def update_pricing_decision(decision_id: str, update_data: dict) -> bool:
    """
    ✨ NOUVEAU : Met à jour une décision pricing avec de nouvelles valeurs

    Args:
        decision_id: ID de la décision à mettre à jour
        update_data: Dictionnaire des champs à mettre à jour

    Returns:
        True si succès, False sinon
    """
    if not update_data:
        logger.warning(f"Aucune donnée à mettre à jour pour {decision_id}")
        return False

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Construire la requête UPDATE dynamiquement
        set_clauses = []
        values = []

        for key, value in update_data.items():
            set_clauses.append(f"{key} = ?")
            values.append(value)

        values.append(decision_id)  # Pour le WHERE

        query = f"""
            UPDATE pricing_decisions
            SET {', '.join(set_clauses)}
            WHERE decision_id = ?
        """

        cursor.execute(query, values)
        conn.commit()

        rows_affected = cursor.rowcount
        conn.close()

        if rows_affected > 0:
            logger.info(f"✓ Décision {decision_id} mise à jour ({len(update_data)} champ(s))")
            return True
        else:
            logger.warning(f"⚠ Décision {decision_id} introuvable pour mise à jour")
            return False

    except Exception as e:
        logger.error(f"✗ Erreur mise à jour décision {decision_id}: {e}")
        return False


def update_daily_statistics():
    """Met à jour les statistiques quotidiennes"""
    conn = get_connection()
    cursor = conn.cursor()

    today = date.today()

    cursor.execute("""
        INSERT INTO pricing_statistics (
            date, total_decisions,
            cas_1_count, cas_2_count, cas_3_count, cas_4_count,
            requiring_validation, avg_margin
        )
        SELECT
            DATE(created_at) as date,
            COUNT(*) as total_decisions,
            SUM(CASE WHEN case_type = 'CAS_1_HC' THEN 1 ELSE 0 END) as cas_1_count,
            SUM(CASE WHEN case_type = 'CAS_2_HCM' THEN 1 ELSE 0 END) as cas_2_count,
            SUM(CASE WHEN case_type = 'CAS_3_HA' THEN 1 ELSE 0 END) as cas_3_count,
            SUM(CASE WHEN case_type = 'CAS_4_NP' THEN 1 ELSE 0 END) as cas_4_count,
            SUM(CASE WHEN requires_validation = 1 THEN 1 ELSE 0 END) as requiring_validation,
            AVG(margin_applied) as avg_margin
        FROM pricing_decisions
        WHERE DATE(created_at) = ?
        GROUP BY DATE(created_at)
        ON CONFLICT(date) DO UPDATE SET
            total_decisions = excluded.total_decisions,
            cas_1_count = excluded.cas_1_count,
            cas_2_count = excluded.cas_2_count,
            cas_3_count = excluded.cas_3_count,
            cas_4_count = excluded.cas_4_count,
            requiring_validation = excluded.requiring_validation,
            avg_margin = excluded.avg_margin,
            updated_at = CURRENT_TIMESTAMP
    """, (today,))

    conn.commit()
    conn.close()


def get_statistics(days_back: int = 30) -> List[Dict]:
    """Récupère les statistiques des N derniers jours"""
    conn = get_connection()
    cursor = conn.cursor()

    from_date = date.today().replace(day=1) if days_back > 30 else date.today()

    cursor.execute("""
        SELECT * FROM pricing_statistics
        WHERE date >= ?
        ORDER BY date DESC
        LIMIT ?
    """, (from_date, days_back))

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_decisions_by_case_type(case_type: PricingCaseType, limit: int = 50) -> List[Dict]:
    """Récupère les décisions par type de CAS"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM pricing_decisions
        WHERE case_type = ?
        ORDER BY created_at DESC
        LIMIT ?
    """, (case_type.value, limit))

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


# Initialiser les tables au chargement du module
init_pricing_audit_tables()
