"""
services/dashboard_service.py
Service de métriques temps réel pour le dashboard pricing et validation
"""

import logging
import sqlite3
import os
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from collections import defaultdict

from services.pricing_audit_db import get_database_path
from services.quote_validator import get_quote_validator

logger = logging.getLogger(__name__)


class DashboardService:
    """Service de métriques et statistiques pour le dashboard"""

    def __init__(self):
        self.db_path = get_database_path()
        self.validator = get_quote_validator()

    def get_pricing_overview(self, days: int = 30) -> Dict[str, Any]:
        """
        Récupère une vue d'ensemble du pricing intelligent
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()

        # Total décisions par CAS
        cursor.execute("""
            SELECT
                case_type,
                COUNT(*) as count,
                AVG(calculated_price) as avg_price,
                AVG(margin_applied) as avg_margin,
                AVG(confidence_score) as avg_confidence,
                SUM(CASE WHEN requires_validation = 1 THEN 1 ELSE 0 END) as validation_required_count
            FROM pricing_decisions
            WHERE DATE(created_at) >= DATE(?)
            GROUP BY case_type
        """, (cutoff_date,))

        cases_stats = {}
        total_decisions = 0
        total_requiring_validation = 0

        for row in cursor.fetchall():
            case_type = row["case_type"]
            count = row["count"]
            total_decisions += count
            total_requiring_validation += row["validation_required_count"]

            cases_stats[case_type] = {
                "count": count,
                "avg_price": round(row["avg_price"], 2) if row["avg_price"] else 0,
                "avg_margin": round(row["avg_margin"], 2) if row["avg_margin"] else 0,
                "avg_confidence": round(row["avg_confidence"], 2) if row["avg_confidence"] else 0,
                "validation_required": row["validation_required_count"],
                "percentage": 0  # Calculé après
            }

        # Calculer pourcentages
        if total_decisions > 0:
            for stats in cases_stats.values():
                stats["percentage"] = round((stats["count"] / total_decisions) * 100, 1)

        # Décisions récentes (dernières 24h)
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM pricing_decisions
            WHERE created_at >= datetime('now', '-24 hours')
        """)
        recent_decisions = cursor.fetchone()["count"]

        # Temps de traitement moyen
        cursor.execute("""
            SELECT AVG(processing_time_ms) as avg_processing_time
            FROM pricing_decisions
            WHERE DATE(created_at) >= DATE(?)
        """, (cutoff_date,))

        avg_processing = cursor.fetchone()["avg_processing_time"]

        conn.close()

        return {
            "period_days": days,
            "total_decisions": total_decisions,
            "decisions_last_24h": recent_decisions,
            "requiring_validation": total_requiring_validation,
            "requiring_validation_percent": round((total_requiring_validation / total_decisions) * 100, 1) if total_decisions > 0 else 0,
            "avg_processing_time_ms": round(avg_processing, 2) if avg_processing else 0,
            "by_case_type": cases_stats
        }

    def get_validation_overview(self, days: int = 30) -> Dict[str, Any]:
        """
        Récupère une vue d'ensemble des validations
        """
        stats = self.validator.get_statistics(days=days)

        # Validations urgentes en attente
        from services.validation_models import ValidationListFilter, ValidationPriority

        urgent_pending = self.validator.list_pending_validations(
            ValidationListFilter(priority=ValidationPriority.URGENT, limit=1000)
        )

        high_pending = self.validator.list_pending_validations(
            ValidationListFilter(priority=ValidationPriority.HIGH, limit=1000)
        )

        return {
            "period_days": days,
            "total_validations": stats.total_validations,
            "pending": stats.pending_count,
            "approved": stats.approved_count,
            "rejected": stats.rejected_count,
            "modified": stats.modified_count,
            "expired": stats.expired_count,
            "urgent_pending": len(urgent_pending),
            "high_priority_pending": len(high_pending),
            "approval_rate": stats.approval_rate,
            "rejection_rate": stats.rejection_rate,
            "avg_validation_time_minutes": stats.avg_validation_time_minutes,
            "by_priority": stats.by_priority,
            "by_case_type": stats.by_case_type
        }

    def get_daily_trend(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        Récupère la tendance quotidienne des décisions pricing
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cutoff_date = (datetime.utcnow() - timedelta(days=days)).date().isoformat()

        cursor.execute("""
            SELECT
                DATE(created_at) as date,
                case_type,
                COUNT(*) as count
            FROM pricing_decisions
            WHERE DATE(created_at) >= DATE(?)
            GROUP BY DATE(created_at), case_type
            ORDER BY DATE(created_at) ASC
        """, (cutoff_date,))

        # Regrouper par date
        daily_data = defaultdict(lambda: {"date": None, "total": 0, "by_case": {}})

        for row in cursor.fetchall():
            date = row["date"]
            case_type = row["case_type"]
            count = row["count"]

            daily_data[date]["date"] = date
            daily_data[date]["total"] += count
            daily_data[date]["by_case"][case_type] = count

        conn.close()

        return list(daily_data.values())

    def get_top_items_requiring_validation(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Récupère les articles nécessitant le plus souvent une validation
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                item_code,
                item_name,
                COUNT(*) as validation_count,
                AVG(calculated_price) as avg_price,
                AVG(margin_applied) as avg_margin
            FROM pricing_decisions
            WHERE requires_validation = 1
            AND DATE(created_at) >= DATE('now', '-30 days')
            GROUP BY item_code, item_name
            ORDER BY validation_count DESC
            LIMIT ?
        """, (limit,))

        items = []
        for row in cursor.fetchall():
            items.append({
                "item_code": row["item_code"],
                "item_name": row["item_name"],
                "validation_count": row["validation_count"],
                "avg_price": round(row["avg_price"], 2) if row["avg_price"] else 0,
                "avg_margin": round(row["avg_margin"], 2) if row["avg_margin"] else 0
            })

        conn.close()

        return items

    def get_top_clients_requiring_validation(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Récupère les clients nécessitant le plus souvent une validation
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                card_code,
                card_name,
                COUNT(*) as validation_count,
                AVG(calculated_price) as avg_price,
                COUNT(DISTINCT item_code) as distinct_items
            FROM pricing_decisions
            WHERE requires_validation = 1
            AND DATE(created_at) >= DATE('now', '-30 days')
            GROUP BY card_code, card_name
            ORDER BY validation_count DESC
            LIMIT ?
        """, (limit,))

        clients = []
        for row in cursor.fetchall():
            clients.append({
                "card_code": row["card_code"],
                "card_name": row["card_name"],
                "validation_count": row["validation_count"],
                "avg_price": round(row["avg_price"], 2) if row["avg_price"] else 0,
                "distinct_items": row["distinct_items"]
            })

        conn.close()

        return clients

    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Récupère les métriques de performance du système
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Temps de traitement moyen par CAS
        cursor.execute("""
            SELECT
                case_type,
                AVG(processing_time_ms) as avg_time,
                MIN(processing_time_ms) as min_time,
                MAX(processing_time_ms) as max_time
            FROM pricing_decisions
            WHERE DATE(created_at) >= DATE('now', '-7 days')
            GROUP BY case_type
        """)

        processing_times = {}
        for row in cursor.fetchall():
            case_type = row[0]
            processing_times[case_type] = {
                "avg_ms": round(row[1], 2) if row[1] else 0,
                "min_ms": round(row[2], 2) if row[2] else 0,
                "max_ms": round(row[3], 2) if row[3] else 0
            }

        # Taux de succès pricing
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN confidence_score >= 0.9 THEN 1 ELSE 0 END) as high_confidence
            FROM pricing_decisions
            WHERE DATE(created_at) >= DATE('now', '-7 days')
        """)

        row = cursor.fetchone()
        total = row[0]
        high_confidence = row[1]

        conn.close()

        return {
            "processing_times_by_case": processing_times,
            "high_confidence_rate": round((high_confidence / total) * 100, 1) if total > 0 else 0,
            "total_decisions_7d": total
        }

    def get_complete_dashboard(self, days: int = 30) -> Dict[str, Any]:
        """
        Récupère toutes les données pour un dashboard complet
        """
        return {
            "pricing_overview": self.get_pricing_overview(days),
            "validation_overview": self.get_validation_overview(days),
            "daily_trend": self.get_daily_trend(days),
            "top_items_requiring_validation": self.get_top_items_requiring_validation(),
            "top_clients_requiring_validation": self.get_top_clients_requiring_validation(),
            "performance_metrics": self.get_performance_metrics(),
            "generated_at": datetime.utcnow().isoformat(),
            "period_days": days
        }


# Singleton
_dashboard_service = None


def get_dashboard_service() -> DashboardService:
    """Retourne l'instance singleton du service dashboard"""
    global _dashboard_service
    if _dashboard_service is None:
        _dashboard_service = DashboardService()
    return _dashboard_service
