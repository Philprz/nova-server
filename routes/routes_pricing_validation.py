"""
routes/routes_pricing_validation.py
Routes API pour le workflow de validation commerciale
"""

import logging
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional

from services.quote_validator import get_quote_validator
from services.validation_models import (
    ValidationRequest,
    ValidationDecision,
    ValidationResult,
    ValidationStatus,
    ValidationPriority,
    ValidationListFilter,
    ValidationStatistics,
    ValidationBulkAction,
    PriceUpdateRequest,
    PriceUpdateResult
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/pending", response_model=List[ValidationRequest])
async def get_pending_validations(
    priority: Optional[str] = Query(None, description="Filtrer par priorité (low, medium, high, urgent)"),
    item_code: Optional[str] = Query(None, description="Filtrer par code article"),
    card_code: Optional[str] = Query(None, description="Filtrer par code client"),
    limit: int = Query(50, le=200, description="Nombre de résultats"),
    offset: int = Query(0, ge=0, description="Offset pour pagination")
):
    """
    Récupère la liste des validations en attente
    """
    try:
        validator = get_quote_validator()

        filters = ValidationListFilter(
            priority=ValidationPriority(priority) if priority else None,
            item_code=item_code,
            card_code=card_code,
            limit=limit,
            offset=offset
        )

        validations = validator.list_pending_validations(filters)

        logger.info(f"✓ {len(validations)} validation(s) en attente récupérée(s)")
        return validations

    except Exception as e:
        logger.error(f"Erreur récupération validations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{validation_id}", response_model=ValidationRequest)
async def get_validation_details(validation_id: str):
    """
    Récupère les détails d'une validation par ID
    """
    try:
        validator = get_quote_validator()
        validation = validator.get_validation_request(validation_id)

        if not validation:
            raise HTTPException(status_code=404, detail=f"Validation non trouvée: {validation_id}")

        return validation

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur récupération validation {validation_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{validation_id}/approve", response_model=ValidationResult)
async def approve_validation(
    validation_id: str,
    approved_price: Optional[float] = Query(None, description="Prix approuvé (si différent du calculé)"),
    approved_margin: Optional[float] = Query(None, description="Marge approuvée"),
    comment: Optional[str] = Query(None, description="Commentaire du validateur"),
    validated_by: str = Query(..., description="Email/username du validateur")
):
    """
    Approuve une demande de validation
    """
    try:
        validator = get_quote_validator()

        decision = ValidationDecision(
            validation_id=validation_id,
            status=ValidationStatus.APPROVED if not approved_price else ValidationStatus.MODIFIED,
            approved_price=approved_price,
            approved_margin=approved_margin,
            validator_comment=comment,
            validated_by=validated_by
        )

        result = validator.validate_request(validation_id, decision)

        logger.info(f"✓ Validation approuvée: {validation_id} par {validated_by}")
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Erreur approbation validation {validation_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{validation_id}/reject", response_model=ValidationResult)
async def reject_validation(
    validation_id: str,
    rejection_reason: str = Query(..., description="Raison du rejet"),
    validated_by: str = Query(..., description="Email/username du validateur")
):
    """
    Rejette une demande de validation
    """
    try:
        validator = get_quote_validator()

        decision = ValidationDecision(
            validation_id=validation_id,
            status=ValidationStatus.REJECTED,
            rejection_reason=rejection_reason,
            validated_by=validated_by
        )

        result = validator.validate_request(validation_id, decision)

        logger.info(f"✓ Validation rejetée: {validation_id} par {validated_by}")
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Erreur rejet validation {validation_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bulk-approve")
async def bulk_approve_validations(action: ValidationBulkAction):
    """
    Approuve plusieurs validations en masse
    """
    try:
        validator = get_quote_validator()
        results = []

        for validation_id in action.validation_ids:
            try:
                decision = ValidationDecision(
                    validation_id=validation_id,
                    status=ValidationStatus.APPROVED,
                    validator_comment=action.comment,
                    validated_by=action.validated_by
                )

                result = validator.validate_request(validation_id, decision)
                results.append({
                    "validation_id": validation_id,
                    "success": True,
                    "result": result
                })

            except Exception as e:
                logger.error(f"Erreur approbation {validation_id}: {e}")
                results.append({
                    "validation_id": validation_id,
                    "success": False,
                    "error": str(e)
                })

        success_count = sum(1 for r in results if r["success"])
        logger.info(f"✓ Approbation en masse: {success_count}/{len(action.validation_ids)} réussies")

        return {
            "total": len(action.validation_ids),
            "success": success_count,
            "failed": len(action.validation_ids) - success_count,
            "results": results
        }

    except Exception as e:
        logger.error(f"Erreur approbation en masse: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics/summary", response_model=ValidationStatistics)
async def get_validation_statistics(
    days: int = Query(30, ge=1, le=365, description="Nombre de jours pour les statistiques")
):
    """
    Récupère les statistiques de validation
    """
    try:
        validator = get_quote_validator()
        stats = validator.get_statistics(days=days)

        logger.info(f"✓ Statistiques validation calculées ({days} jours)")
        return stats

    except Exception as e:
        logger.error(f"Erreur calcul statistiques: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/expire-old")
async def expire_old_validations():
    """
    Expire les validations trop anciennes
    """
    try:
        validator = get_quote_validator()
        expired_count = validator.expire_old_validations()

        return {
            "success": True,
            "expired_count": expired_count,
            "message": f"{expired_count} validation(s) expirée(s)"
        }

    except Exception as e:
        logger.error(f"Erreur expiration validations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/urgent/count")
async def get_urgent_validations_count():
    """
    Compte les validations urgentes en attente
    """
    try:
        validator = get_quote_validator()

        filters = ValidationListFilter(
            priority=ValidationPriority.URGENT,
            limit=1000
        )

        validations = validator.list_pending_validations(filters)

        return {
            "urgent_count": len(validations),
            "validations": validations
        }

    except Exception as e:
        logger.error(f"Erreur comptage validations urgentes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/by-priority/{priority}")
async def get_validations_by_priority(
    priority: str,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0)
):
    """
    Récupère les validations par priorité
    """
    try:
        # Valider la priorité
        try:
            priority_enum = ValidationPriority(priority.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Priorité invalide. Valeurs possibles: {[p.value for p in ValidationPriority]}"
            )

        validator = get_quote_validator()

        filters = ValidationListFilter(
            priority=priority_enum,
            limit=limit,
            offset=offset
        )

        validations = validator.list_pending_validations(filters)

        return {
            "priority": priority,
            "count": len(validations),
            "validations": validations
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur récupération validations par priorité: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/by-case-type/{case_type}")
async def get_validations_by_case_type(
    case_type: str,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0)
):
    """
    Récupère les validations par type de CAS pricing
    """
    try:
        validator = get_quote_validator()

        # Recherche validations avec ce case_type
        import sqlite3

        conn = sqlite3.connect(validator.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM validation_requests
            WHERE status = ? AND case_type = ?
            ORDER BY priority DESC, requested_at ASC
            LIMIT ? OFFSET ?
        """, (ValidationStatus.PENDING.value, case_type, limit, offset))

        rows = cursor.fetchall()
        conn.close()

        import json
        from datetime import datetime

        validations = []
        for row in rows:
            validations.append({
                "validation_id": row["validation_id"],
                "priority": row["priority"],
                "item_code": row["item_code"],
                "item_name": row["item_name"],
                "card_code": row["card_code"],
                "card_name": row["card_name"],
                "calculated_price": row["calculated_price"],
                "case_type": row["case_type"],
                "justification": row["justification"],
                "requested_at": row["requested_at"]
            })

        return {
            "case_type": case_type,
            "count": len(validations),
            "validations": validations
        }

    except Exception as e:
        logger.error(f"Erreur récupération validations par CAS: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/summary")
async def get_validation_dashboard():
    """
    Récupère un résumé complet pour le dashboard de validation
    """
    try:
        validator = get_quote_validator()

        # Statistiques globales
        stats = validator.get_statistics(days=30)

        # Validations urgentes
        urgent_filters = ValidationListFilter(priority=ValidationPriority.URGENT, limit=100)
        urgent = validator.list_pending_validations(urgent_filters)

        # Validations haute priorité
        high_filters = ValidationListFilter(priority=ValidationPriority.HIGH, limit=100)
        high = validator.list_pending_validations(high_filters)

        # Totaux en attente
        all_pending = validator.list_pending_validations(ValidationListFilter(limit=1000))

        return {
            "statistics": stats,
            "pending_summary": {
                "total": len(all_pending),
                "urgent": len(urgent),
                "high": len(high),
                "medium": len([v for v in all_pending if v.priority == ValidationPriority.MEDIUM]),
                "low": len([v for v in all_pending if v.priority == ValidationPriority.LOW])
            },
            "urgent_validations": urgent[:10],  # Top 10 urgentes
            "high_priority_validations": high[:10],  # Top 10 haute priorité
            "validation_rate": {
                "approval_rate": stats.approval_rate,
                "rejection_rate": stats.rejection_rate,
                "avg_time_minutes": stats.avg_validation_time_minutes
            }
        }

    except Exception as e:
        logger.error(f"Erreur récupération dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/decisions/{decision_id}/update-price", response_model=PriceUpdateResult)
async def update_decision_price(
    decision_id: str,
    request: PriceUpdateRequest
):
    """
    ✨ NOUVEAU : Modification manuelle du prix d'une décision pricing

    Permet à l'utilisateur d'ajuster le prix proposé par le moteur de pricing.
    La modification est tracée avec raison et utilisateur.

    Args:
        decision_id: ID de la décision pricing à modifier
        request: Nouveau prix + raison + utilisateur

    Returns:
        Résultat de la modification avec anciens/nouveaux prix et marge
    """
    try:
        import services.pricing_audit_db as pricing_audit_db

        # 1. Récupérer la décision originale depuis la base d'audit
        decision = pricing_audit_db.get_decision_by_id(decision_id)

        if not decision:
            raise HTTPException(
                status_code=404,
                detail=f"Décision pricing {decision_id} introuvable"
            )

        old_price = decision.get('calculated_price')
        supplier_price = decision.get('supplier_price')

        if not old_price:
            raise HTTPException(
                status_code=400,
                detail="Prix original introuvable dans la décision"
            )

        # 2. Calculer la nouvelle marge
        new_margin = 0.0
        if supplier_price and supplier_price > 0:
            new_margin = ((request.new_price - supplier_price) / supplier_price) * 100

        # 3. Mettre à jour la décision dans la base d'audit
        update_data = {
            'calculated_price': request.new_price,
            'line_total': request.new_price * decision.get('quantity', 1),
            'margin_applied': new_margin,
            'case_type': 'CAS_MANUAL',  # Marquer comme modification manuelle
            'modification_reason': request.modification_reason or "Prix ajusté manuellement",
            'modified_by': request.modified_by or "unknown",
            'modified_at': datetime.now().isoformat()
        }

        success = pricing_audit_db.update_pricing_decision(decision_id, update_data)

        if not success:
            raise HTTPException(
                status_code=500,
                detail="Erreur lors de la mise à jour de la décision"
            )

        logger.info(
            f"✓ Prix modifié : {decision_id} → {old_price:.2f} EUR → {request.new_price:.2f} EUR "
            f"(marge {new_margin:.1f}%) par {request.modified_by}"
        )

        return PriceUpdateResult(
            success=True,
            decision_id=decision_id,
            old_price=old_price,
            new_price=request.new_price,
            margin_applied=round(new_margin, 2),
            message=f"Prix modifié avec succès (marge: {new_margin:.1f}%)"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"✗ Erreur modification prix {decision_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
