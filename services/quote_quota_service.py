"""
Quote Quota Service - NOVA-SERVER
Compteur de devis : 50 par mois calendaire, blocage dur (RONDOT).

Règle métier :
- Au plus `max_quota` (défaut 50) devis créés par mois calendaire et par société.
- La société est une clé LOGIQUE (env QUOTA_SOCIETY_ID, défaut "RONDOT") : chez
  RONDOT, deux bases SAP distinctes partagent le MÊME quota, donc les deux
  chemins de création SAP convergent sur la même ligne du compteur.
- Le compteur ne s'incrémente QUE sur une création SAP réellement réussie.

Usage (depuis les services de création SAP) :
    from services.quote_quota_service import get_quote_quota_service, QuotaDevisDepasse

    quota = get_quote_quota_service()
    quota.check_quota()          # AVANT l'appel SAP — lève QuotaDevisDepasse si plein
    ...                          # création SAP, obtention du doc_entry
    quota.increment()            # APRÈS succès SAP — incrément atomique
"""

import os
import logging
from datetime import datetime
from typing import Optional, Callable

from sqlalchemy.exc import IntegrityError

from models.database_models import SessionLocal, QuoteUsageCounter

logger = logging.getLogger(__name__)


# ============================================================
# EXCEPTION TYPÉE
# ============================================================


class QuotaDevisDepasse(Exception):
    """Levée quand le quota mensuel de devis est atteint (blocage dur).

    Portée jusqu'aux routes HTTP, où elle est convertie en réponse 4xx avec
    le code d'erreur QUOTA_DEVIS_DEPASSE.
    """

    error_code = "QUOTA_DEVIS_DEPASSE"

    def __init__(self, society_id: str, period: str, count: int, max_quota: int):
        self.society_id = society_id
        self.period = period
        self.count = count
        self.max_quota = max_quota
        super().__init__(
            f"Quota de devis atteint pour la société '{society_id}' sur {period} : "
            f"{count}/{max_quota}. Création bloquée."
        )


# ============================================================
# SERVICE
# ============================================================


def _current_period() -> str:
    """Période mois calendaire courante au format 'YYYY-MM'."""
    return datetime.now().strftime("%Y-%m")


class QuoteQuotaService:
    """Gestion du compteur de devis (quota mensuel calendaire, blocage dur)."""

    def __init__(
        self,
        session_factory: Optional[Callable] = None,
        default_society: Optional[str] = None,
        default_max_quota: Optional[int] = None,
    ):
        self._session_factory = session_factory or SessionLocal
        self.default_society = default_society or os.getenv("QUOTA_SOCIETY_ID", "RONDOT")
        self.default_max_quota = int(
            default_max_quota if default_max_quota is not None
            else os.getenv("QUOTA_DEVIS_MAX", "50")
        )

    # ----------------------------------------------------------
    # Helpers internes
    # ----------------------------------------------------------

    def _resolve_society(self, society: Optional[str]) -> str:
        return society or self.default_society

    def _get_or_create_row(self, session, society: str, period: str) -> QuoteUsageCounter:
        """Récupère la ligne (society, period) ou la crée à 0.

        Gère la course concurrente sur la création via la contrainte d'unicité :
        en cas d'IntegrityError, on relit la ligne créée par l'autre transaction.
        """
        row = (
            session.query(QuoteUsageCounter)
            .filter_by(society_id=society, period=period)
            .first()
        )
        if row is not None:
            return row

        row = QuoteUsageCounter(
            society_id=society,
            period=period,
            count=0,
            max_quota=self.default_max_quota,
        )
        session.add(row)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            row = (
                session.query(QuoteUsageCounter)
                .filter_by(society_id=society, period=period)
                .first()
            )
        return row

    # ----------------------------------------------------------
    # API publique
    # ----------------------------------------------------------

    def check_quota(
        self, society: Optional[str] = None, period: Optional[str] = None
    ) -> int:
        """Vérifie le quota AVANT création SAP.

        Lit (ou crée à 0) la ligne du mois courant. Si count >= max_quota,
        lève QuotaDevisDepasse. Sinon retourne le nombre de devis restants.
        """
        society = self._resolve_society(society)
        period = period or _current_period()

        with self._session_factory() as session:
            row = self._get_or_create_row(session, society, period)
            if row.count >= row.max_quota:
                logger.warning(
                    "🚫 Quota devis atteint | société=%s | %s | %d/%d",
                    society, period, row.count, row.max_quota,
                )
                raise QuotaDevisDepasse(society, period, row.count, row.max_quota)
            remaining = row.max_quota - row.count
            logger.info(
                "✓ Quota devis OK | société=%s | %s | %d/%d (restant=%d)",
                society, period, row.count, row.max_quota, remaining,
            )
            return remaining

    def increment(
        self, society: Optional[str] = None, period: Optional[str] = None
    ) -> int:
        """Incrémente le compteur APRÈS création SAP réussie, de façon ATOMIQUE.

        Utilise un verrou de ligne (SELECT ... FOR UPDATE sur PostgreSQL) pour
        sérialiser les incréments concurrents et éviter toute perte de mise à
        jour. Retourne le nouveau compteur.
        """
        society = self._resolve_society(society)
        period = period or _current_period()

        with self._session_factory() as session:
            # Garantir l'existence de la ligne (création hors verrou si absente)
            self._get_or_create_row(session, society, period)

            query = session.query(QuoteUsageCounter).filter_by(
                society_id=society, period=period
            )
            # Verrou de ligne sur les SGBD qui le supportent (PostgreSQL).
            # SQLite (tests) ignore/ne supporte pas FOR UPDATE : on s'en passe.
            try:
                dialect = session.bind.dialect.name
            except Exception:
                dialect = ""
            if dialect == "postgresql":
                query = query.with_for_update()

            row = query.first()
            row.count += 1
            row.updated_at = datetime.now()
            session.commit()
            new_count = row.count

        logger.info(
            "➕ Compteur devis incrémenté | société=%s | %s | nouveau=%d/%d",
            society, period, new_count, self.default_max_quota,
        )
        return new_count


# ============================================================
# SINGLETON
# ============================================================

_quote_quota_service: Optional[QuoteQuotaService] = None


def get_quote_quota_service() -> QuoteQuotaService:
    """Retourne l'instance singleton du service de quota de devis."""
    global _quote_quota_service
    if _quote_quota_service is None:
        _quote_quota_service = QuoteQuotaService()
        logger.info("QuoteQuotaService singleton créé")
    return _quote_quota_service
