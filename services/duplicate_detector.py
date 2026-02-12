"""
Duplicate Detector Service - NOVA-SERVER
Détecte les doublons de demandes de devis pour éviter les traitements multiples.
"""

import sqlite3
import logging
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class DuplicateType(str, Enum):
    """Types de doublons détectés."""
    STRICT = "strict"          # Email ID identique
    PROBABLE = "probable"      # Même client + produits similaires (48h)
    POSSIBLE = "possible"      # Même expéditeur + sujet similaire (24h)
    NONE = "none"              # Pas de doublon


class QuoteStatus(str, Enum):
    """Statuts de traitement des devis."""
    PENDING = "pending"        # En attente validation
    COMPLETED = "completed"    # Devis créé dans SAP
    REJECTED = "rejected"      # Rejeté par utilisateur
    CANCELLED = "cancelled"    # Annulé


@dataclass
class ExistingQuote:
    """Référence à un devis existant."""
    quote_id: str
    email_id: str
    processed_at: str
    status: str
    client_card_code: Optional[str]
    product_codes: List[str]
    sender_email: str
    subject: str


@dataclass
class DuplicateCheckResult:
    """Résultat de la vérification de doublon."""
    is_duplicate: bool
    duplicate_type: DuplicateType
    existing_quote: Optional[ExistingQuote]
    confidence: float  # 0.0 à 1.0


class DuplicateDetector:
    """Service de détection des doublons de demandes de devis."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialise le détecteur de doublons."""
        if db_path is None:
            # Utiliser la même base que supplier_tariffs
            db_path = str(Path(__file__).parent.parent / "supplier_tariffs.db")

        self.db_path = db_path
        self._init_database()
        logger.info(f"DuplicateDetector initialisé avec DB: {db_path}")

    def _init_database(self):
        """Crée la table processed_emails si elle n'existe pas."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()

            # Table principale des emails traités
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS processed_emails (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email_id TEXT UNIQUE NOT NULL,
                    email_subject TEXT,
                    sender_email TEXT NOT NULL,
                    client_card_code TEXT,
                    client_name TEXT,
                    product_codes TEXT,
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    quote_id TEXT,
                    status TEXT DEFAULT 'pending',
                    sap_doc_entry INTEGER,
                    notes TEXT,
                    UNIQUE(email_id)
                )
            """)

            # Index pour recherches rapides
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_processed_emails_sender
                ON processed_emails(sender_email, processed_at DESC)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_processed_emails_client
                ON processed_emails(client_card_code, processed_at DESC)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_processed_emails_status
                ON processed_emails(status, processed_at DESC)
            """)

            conn.commit()
            logger.info("Table processed_emails créée avec succès")

        except Exception as e:
            logger.error(f"Erreur création table processed_emails: {e}")
            raise
        finally:
            conn.close()

    def check_duplicate(
        self,
        email_id: str,
        sender_email: str,
        subject: str,
        client_card_code: Optional[str] = None,
        product_codes: Optional[List[str]] = None
    ) -> DuplicateCheckResult:
        """
        Vérifie si un email est un doublon.

        Args:
            email_id: ID unique du message email
            sender_email: Adresse email de l'expéditeur
            subject: Sujet de l'email
            client_card_code: Code client SAP (si identifié)
            product_codes: Liste des codes produits (si identifiés)

        Returns:
            DuplicateCheckResult avec type de doublon et référence existante
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        try:
            cursor = conn.cursor()

            # 1. VÉRIFICATION STRICTE : Email ID identique
            cursor.execute("""
                SELECT * FROM processed_emails
                WHERE email_id = ?
            """, (email_id,))

            existing = cursor.fetchone()
            if existing:
                return DuplicateCheckResult(
                    is_duplicate=True,
                    duplicate_type=DuplicateType.STRICT,
                    existing_quote=self._row_to_quote(existing),
                    confidence=1.0
                )

            # 2. VÉRIFICATION PROBABLE : Même client + produits similaires (30 jours)
            if client_card_code and product_codes:
                cutoff_time = (datetime.now() - timedelta(days=30)).isoformat()

                cursor.execute("""
                    SELECT * FROM processed_emails
                    WHERE client_card_code = ?
                    AND processed_at > ?
                    AND status IN ('pending', 'completed')
                    ORDER BY processed_at DESC
                    LIMIT 10
                """, (client_card_code, cutoff_time))

                candidates = cursor.fetchall()
                for candidate in candidates:
                    existing_products = json.loads(candidate['product_codes'] or '[]')
                    similarity = self._calculate_product_similarity(
                        product_codes, existing_products
                    )

                    if similarity >= 0.7:  # 70% de produits communs
                        return DuplicateCheckResult(
                            is_duplicate=True,
                            duplicate_type=DuplicateType.PROBABLE,
                            existing_quote=self._row_to_quote(candidate),
                            confidence=similarity
                        )

            # 3. VÉRIFICATION POSSIBLE : Même expéditeur + sujet similaire (30 jours)
            cutoff_time = (datetime.now() - timedelta(days=30)).isoformat()

            cursor.execute("""
                SELECT * FROM processed_emails
                WHERE sender_email = ?
                AND processed_at > ?
                AND status IN ('pending', 'completed')
                ORDER BY processed_at DESC
                LIMIT 10
            """, (sender_email, cutoff_time))

            candidates = cursor.fetchall()
            for candidate in candidates:
                subject_similarity = self._calculate_text_similarity(
                    subject, candidate['email_subject'] or ""
                )

                if subject_similarity >= 0.8:  # 80% de similarité de sujet
                    return DuplicateCheckResult(
                        is_duplicate=True,
                        duplicate_type=DuplicateType.POSSIBLE,
                        existing_quote=self._row_to_quote(candidate),
                        confidence=subject_similarity
                    )

            # Aucun doublon détecté
            return DuplicateCheckResult(
                is_duplicate=False,
                duplicate_type=DuplicateType.NONE,
                existing_quote=None,
                confidence=0.0
            )

        except Exception as e:
            logger.error(f"Erreur vérification doublon: {e}")
            # En cas d'erreur, ne pas bloquer le traitement
            return DuplicateCheckResult(
                is_duplicate=False,
                duplicate_type=DuplicateType.NONE,
                existing_quote=None,
                confidence=0.0
            )
        finally:
            conn.close()

    def register_email(
        self,
        email_id: str,
        sender_email: str,
        subject: str,
        client_card_code: Optional[str] = None,
        client_name: Optional[str] = None,
        product_codes: Optional[List[str]] = None,
        status: QuoteStatus = QuoteStatus.PENDING,
        quote_id: Optional[str] = None,
        notes: Optional[str] = None
    ) -> bool:
        """
        Enregistre un email traité dans la base.

        Returns:
            True si enregistrement réussi, False sinon
        """
        conn = sqlite3.connect(self.db_path)

        try:
            cursor = conn.cursor()

            product_codes_json = json.dumps(product_codes or [])

            cursor.execute("""
                INSERT OR REPLACE INTO processed_emails
                (email_id, email_subject, sender_email, client_card_code,
                 client_name, product_codes, status, quote_id, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                email_id,
                subject,
                sender_email,
                client_card_code,
                client_name,
                product_codes_json,
                status.value,
                quote_id,
                notes
            ))

            conn.commit()
            logger.info(f"Email {email_id} enregistré avec status {status.value}")
            return True

        except Exception as e:
            logger.error(f"Erreur enregistrement email: {e}")
            return False
        finally:
            conn.close()

    def update_quote_status(
        self,
        email_id: str,
        status: QuoteStatus,
        quote_id: Optional[str] = None,
        sap_doc_entry: Optional[int] = None
    ) -> bool:
        """Met à jour le statut d'un devis."""
        conn = sqlite3.connect(self.db_path)

        try:
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE processed_emails
                SET status = ?, quote_id = ?, sap_doc_entry = ?
                WHERE email_id = ?
            """, (status.value, quote_id, sap_doc_entry, email_id))

            conn.commit()
            logger.info(f"Status mis à jour pour {email_id}: {status.value}")
            return True

        except Exception as e:
            logger.error(f"Erreur mise à jour status: {e}")
            return False
        finally:
            conn.close()

    def get_statistics(self) -> Dict[str, Any]:
        """Retourne des statistiques sur les emails traités."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        try:
            cursor = conn.cursor()

            # Total par statut
            cursor.execute("""
                SELECT status, COUNT(*) as count
                FROM processed_emails
                GROUP BY status
            """)
            status_counts = {row['status']: row['count'] for row in cursor.fetchall()}

            # Doublons détectés (approximation)
            cursor.execute("""
                SELECT COUNT(*) as count FROM (
                    SELECT sender_email, DATE(processed_at) as day, COUNT(*) as cnt
                    FROM processed_emails
                    GROUP BY sender_email, day
                    HAVING cnt > 1
                )
            """)
            duplicates_detected = cursor.fetchone()['count']

            # Total emails traités
            cursor.execute("SELECT COUNT(*) as count FROM processed_emails")
            total = cursor.fetchone()['count']

            return {
                "total_emails": total,
                "by_status": status_counts,
                "duplicates_prevented": duplicates_detected,
                "success_rate": round(
                    status_counts.get('completed', 0) / max(total, 1) * 100, 2
                )
            }

        except Exception as e:
            logger.error(f"Erreur récupération statistiques: {e}")
            return {}
        finally:
            conn.close()

    # --- Méthodes privées ---

    def _row_to_quote(self, row: sqlite3.Row) -> ExistingQuote:
        """Convertit une ligne DB en objet ExistingQuote."""
        return ExistingQuote(
            quote_id=row['quote_id'] or f"EMAIL-{row['id']}",
            email_id=row['email_id'],
            processed_at=row['processed_at'],
            status=row['status'],
            client_card_code=row['client_card_code'],
            product_codes=json.loads(row['product_codes'] or '[]'),
            sender_email=row['sender_email'],
            subject=row['email_subject'] or ""
        )

    def _calculate_product_similarity(
        self,
        products1: List[str],
        products2: List[str]
    ) -> float:
        """Calcule la similarité entre deux listes de produits."""
        if not products1 or not products2:
            return 0.0

        set1 = set(products1)
        set2 = set(products2)

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        return intersection / union if union > 0 else 0.0

    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """Calcule la similarité entre deux textes (Jaccard sur mots)."""
        if not text1 or not text2:
            return 0.0

        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0


# --- Singleton ---

_duplicate_detector: Optional[DuplicateDetector] = None


def get_duplicate_detector() -> DuplicateDetector:
    """Retourne l'instance singleton du détecteur de doublons."""
    global _duplicate_detector
    if _duplicate_detector is None:
        _duplicate_detector = DuplicateDetector()
    return _duplicate_detector
