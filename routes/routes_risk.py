"""
Route de vérification risque client — admin/debug uniquement.

GET /api/risk-check?company_name=XXX&siren=YYY
"""

from fastapi import APIRouter, Depends, Query
from auth.dependencies import get_current_user
from services.risk_check_service import get_company_risk

router = APIRouter(
    prefix="/api",
    tags=["Risk Check"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/risk-check")
async def risk_check(
    company_name: str = Query(None, description="Nom de l'entreprise"),
    siren: str = Query(None, description="SIREN (9 chiffres, prioritaire)"),
):
    """
    Vérifie le risque financier d'une entreprise via Pappers.

    Retourne :
      - status : OK | WARNING | BLOCKED | UNKNOWN
      - reason : explication lisible
      - source : pappers
      - raw    : données brutes Pappers
    """
    if not company_name and not siren:
        return {"status": "UNKNOWN", "reason": "Paramètre company_name ou siren requis", "source": "pappers", "raw": {}}

    return await get_company_risk(company_name=company_name, siren=siren)
