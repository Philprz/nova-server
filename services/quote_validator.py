"""
services/quote_validator.py
Service de validation commerciale pour les devis et décisions pricing
"""

import os
import sqlite3
import logging
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from pathlib import Path

from services.validation_models import (
    ValidationRequest,
    ValidationDecision,
    ValidationResult,
    ValidationStatus,
    ValidationPriority,
    ValidationType,
    ValidationStatistics,
    ValidationListFilter,
    ValidationWorkflowConfig,
    ValidationNotification
)
from services.pricing_models import PricingDecision, PricingCaseType


logger = logging.getLogger(__name__)


class QuoteValidator:
    """Service de validation commerciale"""

    def __init__(self, db_path: str = "data/supplier_tariffs.db"):
        self.db_path = db_path
        self.config = self._load_config()
        self._init_database()

    def _load_config(self) -> ValidationWorkflowConfig:
        """Charge la configuration depuis les variables d'environnement"""
        return ValidationWorkflowConfig(
            auto_approve_threshold_percent=float(os.getenv("VALIDATION_AUTO_APPROVE_THRESHOLD", "3.0")),
            auto_reject_threshold_percent=float(os.getenv("VALIDATION_AUTO_REJECT_THRESHOLD", "50.0")),
            default_expiration_hours=int(os.getenv("VALIDATION_EXPIRATION_HOURS", "48")),
            urgent_expiration_hours=int(os.getenv("VALIDATION_URGENT_EXPIRATION_HOURS", "4")),
            notify_on_creation=os.getenv("VALIDATION_NOTIFY_ON_CREATION", "true").lower() == "true",
            notification_email=os.getenv("VALIDATION_EMAIL", "validation@rondot-sas.fr"),
            high_priority_threshold_percent=float(os.getenv("VALIDATION_HIGH_PRIORITY_THRESHOLD", "10.0")),
            urgent_priority_threshold_percent=float(os.getenv("VALIDATION_URGENT_PRIORITY_THRESHOLD", "20.0")),
            default_validators=os.getenv("VALIDATION_DEFAULT_VALIDATORS", "").split(",") if os.getenv("VALIDATION_DEFAULT_VALIDATORS") else []
        )

    def _init_database(self):
        """Initialise les tables de validation"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Table des demandes de validation
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS validation_requests (
                validation_id TEXT PRIMARY KEY,
                validation_type TEXT NOT NULL,
                priority TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',

                -- Pricing context
                decision_id TEXT,
                item_code TEXT NOT NULL,
                item_name TEXT,
                card_code TEXT,
                card_name TEXT,
                quantity REAL NOT NULL,

                -- Prix et marges
                calculated_price REAL NOT NULL,
                supplier_price REAL,
                margin_applied REAL,

                -- Contexte décisionnel
                case_type TEXT,
                justification TEXT NOT NULL,
                alerts_json TEXT,

                -- Historique
                last_sale_price REAL,
                last_sale_date TEXT,
                price_variation_percent REAL,

                -- Métadonnées
                requested_by TEXT NOT NULL,
                requested_at TEXT NOT NULL,
                expires_at TEXT,

                -- Email source
                email_id TEXT,
                email_subject TEXT,

                -- Timestamps
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Table des décisions de validation
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS validation_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                validation_id TEXT NOT NULL,
                status TEXT NOT NULL,

                -- Décision
                approved_price REAL,
                approved_margin REAL,

                -- Justification
                validator_comment TEXT,
                rejection_reason TEXT,

                -- Validateur
                validated_by TEXT NOT NULL,
                validated_at TEXT NOT NULL,

                -- Timestamps
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (validation_id) REFERENCES validation_requests(validation_id)
            )
        """)

        # Table des notifications
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS validation_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                validation_id TEXT NOT NULL,
                notification_type TEXT NOT NULL,
                recipient TEXT NOT NULL,
                subject TEXT NOT NULL,
                message TEXT NOT NULL,
                sent_at TEXT,

                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (validation_id) REFERENCES validation_requests(validation_id)
            )
        """)

        # Index pour performance
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_validation_requests_status
            ON validation_requests(status)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_validation_requests_item
            ON validation_requests(item_code)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_validation_requests_client
            ON validation_requests(card_code)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_validation_requests_priority
            ON validation_requests(priority, status)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_validation_requests_expires
            ON validation_requests(expires_at, status)
        """)

        conn.commit()
        conn.close()

        logger.info("✓ Tables de validation initialisées")

    def create_validation_request(
        self,
        pricing_decision: PricingDecision,
        email_id: Optional[str] = None,
        email_subject: Optional[str] = None
    ) -> ValidationRequest:
        """
        Crée une demande de validation à partir d'une décision pricing
        """
        validation_id = f"val_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        # Déterminer la priorité basée sur la variation de prix
        priority = self._determine_priority(pricing_decision)

        # Calculer la date d'expiration
        expiration_hours = (
            self.config.urgent_expiration_hours
            if priority == ValidationPriority.URGENT
            else self.config.default_expiration_hours
        )
        expires_at = datetime.utcnow() + timedelta(hours=expiration_hours)

        # Créer la demande de validation
        validation_request = ValidationRequest(
            validation_id=validation_id,
            validation_type=ValidationType.PRICING,
            priority=priority,
            decision_id=pricing_decision.decision_id,
            item_code=pricing_decision.item_code,
            item_name=pricing_decision.item_name,
            card_code=pricing_decision.card_code,
            card_name=pricing_decision.card_name,
            quantity=pricing_decision.quantity,
            calculated_price=pricing_decision.calculated_price,
            supplier_price=pricing_decision.supplier_price,
            margin_applied=pricing_decision.margin_applied,
            case_type=pricing_decision.case_type.value if pricing_decision.case_type else None,
            justification=pricing_decision.justification,
            alerts=pricing_decision.alerts,
            last_sale_price=pricing_decision.last_sale_price,
            last_sale_date=pricing_decision.last_sale_date,
            price_variation_percent=pricing_decision.price_variation_percent,
            requested_by="pricing_engine",
            expires_at=expires_at,
            email_id=email_id,
            email_subject=email_subject
        )

        # Sauvegarder dans la base de données
        self._save_validation_request(validation_request)

        # Créer notification si configuré
        if self.config.notify_on_creation:
            self._create_notification(validation_request, "created")

        logger.info(f"✓ Validation créée: {validation_id} (priorité: {priority.value})")

        return validation_request

    def _determine_priority(self, pricing_decision: PricingDecision) -> ValidationPriority:
        """Détermine la priorité basée sur la décision pricing"""
        variation = abs(pricing_decision.price_variation_percent or 0)

        if variation >= self.config.urgent_priority_threshold_percent:
            return ValidationPriority.URGENT
        elif variation >= self.config.high_priority_threshold_percent:
            return ValidationPriority.HIGH
        elif pricing_decision.case_type == PricingCaseType.CAS_4_NP:
            return ValidationPriority.MEDIUM  # Nouveau produit = priorité moyenne
        else:
            return ValidationPriority.LOW

    def _save_validation_request(self, request: ValidationRequest):
        """Sauvegarde une demande de validation"""
        import json

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO validation_requests (
                validation_id, validation_type, priority, status,
                decision_id, item_code, item_name, card_code, card_name, quantity,
                calculated_price, supplier_price, margin_applied,
                case_type, justification, alerts_json,
                last_sale_price, last_sale_date, price_variation_percent,
                requested_by, requested_at, expires_at,
                email_id, email_subject
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            request.validation_id,
            request.validation_type.value,
            request.priority.value,
            ValidationStatus.PENDING.value,
            request.decision_id,
            request.item_code,
            request.item_name,
            request.card_code,
            request.card_name,
            request.quantity,
            request.calculated_price,
            request.supplier_price,
            request.margin_applied,
            request.case_type,
            request.justification,
            json.dumps(request.alerts),
            request.last_sale_price,
            request.last_sale_date,
            request.price_variation_percent,
            request.requested_by,
            request.requested_at.isoformat(),
            request.expires_at.isoformat() if request.expires_at else None,
            request.email_id,
            request.email_subject
        ))

        conn.commit()
        conn.close()

    def validate_request(
        self,
        validation_id: str,
        decision: ValidationDecision
    ) -> ValidationResult:
        """
        Valide ou rejette une demande de validation
        """
        # Récupérer la demande
        request = self.get_validation_request(validation_id)
        if not request:
            raise ValueError(f"Validation non trouvée: {validation_id}")

        if request.status != ValidationStatus.PENDING:
            raise ValueError(f"Validation déjà traitée: {request.status}")

        # Sauvegarder la décision
        self._save_validation_decision(decision)

        # Mettre à jour le statut de la demande
        self._update_validation_status(validation_id, decision.status)

        # Calculer le temps de validation
        validation_time = (datetime.utcnow() - request.requested_at).total_seconds()

        result = ValidationResult(
            request=request,
            decision=decision,
            status=decision.status,
            is_validated=True,
            validation_time_seconds=int(validation_time)
        )

        # Créer notification
        self._create_notification(request, decision.status.value)

        logger.info(f"✓ Validation traitée: {validation_id} → {decision.status.value}")

        return result

    def _save_validation_decision(self, decision: ValidationDecision):
        """Sauvegarde une décision de validation"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO validation_decisions (
                validation_id, status,
                approved_price, approved_margin,
                validator_comment, rejection_reason,
                validated_by, validated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            decision.validation_id,
            decision.status.value,
            decision.approved_price,
            decision.approved_margin,
            decision.validator_comment,
            decision.rejection_reason,
            decision.validated_by,
            decision.validated_at.isoformat()
        ))

        conn.commit()
        conn.close()

    def _update_validation_status(self, validation_id: str, status: ValidationStatus):
        """Met à jour le statut d'une validation"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE validation_requests
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE validation_id = ?
        """, (status.value, validation_id))

        conn.commit()
        conn.close()

    def get_validation_request(self, validation_id: str) -> Optional[ValidationRequest]:
        """Récupère une demande de validation par ID"""
        import json

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM validation_requests
            WHERE validation_id = ?
        """, (validation_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return ValidationRequest(
            validation_id=row["validation_id"],
            validation_type=ValidationType(row["validation_type"]),
            priority=ValidationPriority(row["priority"]),
            decision_id=row["decision_id"],
            item_code=row["item_code"],
            item_name=row["item_name"],
            card_code=row["card_code"],
            card_name=row["card_name"],
            quantity=row["quantity"],
            calculated_price=row["calculated_price"],
            supplier_price=row["supplier_price"],
            margin_applied=row["margin_applied"],
            case_type=row["case_type"],
            justification=row["justification"],
            alerts=json.loads(row["alerts_json"]) if row["alerts_json"] else [],
            last_sale_price=row["last_sale_price"],
            last_sale_date=row["last_sale_date"],
            price_variation_percent=row["price_variation_percent"],
            requested_by=row["requested_by"],
            requested_at=datetime.fromisoformat(row["requested_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
            email_id=row["email_id"],
            email_subject=row["email_subject"]
        )

    def list_pending_validations(
        self,
        filters: Optional[ValidationListFilter] = None
    ) -> List[ValidationRequest]:
        """Liste les validations en attente"""
        import json

        filters = filters or ValidationListFilter()

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Construire la requête
        query = "SELECT * FROM validation_requests WHERE status = ?"
        params = [ValidationStatus.PENDING.value]

        if filters.priority:
            query += " AND priority = ?"
            params.append(filters.priority.value)

        if filters.item_code:
            query += " AND item_code = ?"
            params.append(filters.item_code)

        if filters.card_code:
            query += " AND card_code = ?"
            params.append(filters.card_code)

        query += " ORDER BY priority DESC, requested_at ASC LIMIT ? OFFSET ?"
        params.extend([filters.limit, filters.offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        validations = []
        for row in rows:
            validations.append(ValidationRequest(
                validation_id=row["validation_id"],
                validation_type=ValidationType(row["validation_type"]),
                priority=ValidationPriority(row["priority"]),
                decision_id=row["decision_id"],
                item_code=row["item_code"],
                item_name=row["item_name"],
                card_code=row["card_code"],
                card_name=row["card_name"],
                quantity=row["quantity"],
                calculated_price=row["calculated_price"],
                supplier_price=row["supplier_price"],
                margin_applied=row["margin_applied"],
                case_type=row["case_type"],
                justification=row["justification"],
                alerts=json.loads(row["alerts_json"]) if row["alerts_json"] else [],
                last_sale_price=row["last_sale_price"],
                last_sale_date=row["last_sale_date"],
                price_variation_percent=row["price_variation_percent"],
                requested_by=row["requested_by"],
                requested_at=datetime.fromisoformat(row["requested_at"]),
                expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
                email_id=row["email_id"],
                email_subject=row["email_subject"]
            ))

        return validations

    def get_statistics(
        self,
        days: int = 30
    ) -> ValidationStatistics:
        """Calcule les statistiques de validation"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()

        # Totaux par statut
        cursor.execute("""
            SELECT status, COUNT(*) as count
            FROM validation_requests
            WHERE requested_at >= ?
            GROUP BY status
        """, (cutoff_date,))

        status_counts = dict(cursor.fetchall())

        # Temps moyen de validation
        cursor.execute("""
            SELECT
                AVG((julianday(vd.validated_at) - julianday(vr.requested_at)) * 24 * 60) as avg_minutes,
                COUNT(*) as count
            FROM validation_requests vr
            JOIN validation_decisions vd ON vr.validation_id = vd.validation_id
            WHERE vr.requested_at >= ?
            AND vr.status IN ('approved', 'rejected', 'modified')
        """, (cutoff_date,))

        time_stats = cursor.fetchone()
        avg_minutes = time_stats[0] if time_stats[0] else None

        # Répartition par type
        cursor.execute("""
            SELECT validation_type, COUNT(*) as count
            FROM validation_requests
            WHERE requested_at >= ?
            GROUP BY validation_type
        """, (cutoff_date,))

        by_type = dict(cursor.fetchall())

        # Répartition par priorité
        cursor.execute("""
            SELECT priority, COUNT(*) as count
            FROM validation_requests
            WHERE requested_at >= ?
            GROUP BY priority
        """, (cutoff_date,))

        by_priority = dict(cursor.fetchall())

        # Répartition par CAS
        cursor.execute("""
            SELECT case_type, COUNT(*) as count
            FROM validation_requests
            WHERE requested_at >= ?
            AND case_type IS NOT NULL
            GROUP BY case_type
        """, (cutoff_date,))

        by_case_type = dict(cursor.fetchall())

        conn.close()

        total = sum(status_counts.values())
        approved = status_counts.get("approved", 0)
        rejected = status_counts.get("rejected", 0)

        return ValidationStatistics(
            total_validations=total,
            pending_count=status_counts.get("pending", 0),
            approved_count=approved,
            rejected_count=rejected,
            modified_count=status_counts.get("modified", 0),
            expired_count=status_counts.get("expired", 0),
            avg_validation_time_minutes=avg_minutes,
            by_validation_type=by_type,
            by_priority=by_priority,
            by_case_type=by_case_type,
            approval_rate=(approved / total * 100) if total > 0 else None,
            rejection_rate=(rejected / total * 100) if total > 0 else None
        )

    def expire_old_validations(self) -> int:
        """Expire les validations trop anciennes"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        now = datetime.utcnow().isoformat()

        cursor.execute("""
            UPDATE validation_requests
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE status = ?
            AND expires_at < ?
        """, (ValidationStatus.EXPIRED.value, ValidationStatus.PENDING.value, now))

        expired_count = cursor.rowcount
        conn.commit()
        conn.close()

        if expired_count > 0:
            logger.info(f"✓ {expired_count} validation(s) expirée(s)")

        return expired_count

    def _create_notification(
        self,
        request: ValidationRequest,
        notification_type: str
    ):
        """Crée une notification pour la validation"""
        subject = self._format_notification_subject(request, notification_type)
        message = self._format_notification_message(request, notification_type)

        notification = ValidationNotification(
            validation_id=request.validation_id,
            notification_type=notification_type,
            recipient=self.config.notification_email,
            subject=subject,
            message=message
        )

        # Sauvegarder la notification
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO validation_notifications (
                validation_id, notification_type, recipient, subject, message
            ) VALUES (?, ?, ?, ?, ?)
        """, (
            notification.validation_id,
            notification.notification_type,
            notification.recipient,
            notification.subject,
            notification.message
        ))

        conn.commit()
        conn.close()

        logger.info(f"✓ Notification créée: {notification_type} pour {request.validation_id}")

    def _format_notification_subject(self, request: ValidationRequest, notification_type: str) -> str:
        """Formate le sujet de notification"""
        priority_emoji = {
            ValidationPriority.LOW: "ℹ️",
            ValidationPriority.MEDIUM: "⚠️",
            ValidationPriority.HIGH: "🔴",
            ValidationPriority.URGENT: "🚨"
        }

        emoji = priority_emoji.get(request.priority, "ℹ️")

        if notification_type == "created":
            return f"{emoji} Validation requise: {request.item_code} ({request.priority.value})"
        elif notification_type == "approved":
            return f"✅ Validation approuvée: {request.item_code}"
        elif notification_type == "rejected":
            return f"❌ Validation rejetée: {request.item_code}"
        else:
            return f"Validation {notification_type}: {request.item_code}"

    def _format_notification_message(self, request: ValidationRequest, notification_type: str) -> str:
        """Formate le message de notification"""
        if notification_type == "created":
            return f"""
Nouvelle demande de validation de pricing

Article: {request.item_code} - {request.item_name or 'N/A'}
Client: {request.card_code} - {request.card_name or 'N/A'}
Quantité: {request.quantity}

Prix calculé: {request.calculated_price:.2f} EUR
Prix fournisseur: {request.supplier_price:.2f} EUR (marge: {request.margin_applied:.1f}%)
CAS: {request.case_type}

{request.justification}

Alertes:
{chr(10).join('- ' + alert for alert in request.alerts)}

Expire le: {request.expires_at.strftime('%d/%m/%Y %H:%M') if request.expires_at else 'N/A'}
ID validation: {request.validation_id}
"""
        else:
            return f"Validation {notification_type} pour {request.item_code}"


# Singleton
_validator_instance = None


def get_quote_validator() -> QuoteValidator:
    """Retourne l'instance singleton du validateur"""
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = QuoteValidator()
    return _validator_instance
