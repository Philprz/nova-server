# routes/routes_sync.py
"""
Routes API pour la synchronisation bidirectionnelle des clients entre SAP et Salesforce
"""

import os
import sys
import logging
from datetime import datetime
from typing import Dict, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from enum import Enum

# Ajouter le répertoire parent pour l'import du script de sync
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import du module de synchronisation
try:
    from sync_clients import (
        run_sync, 
        get_sap_customers, 
        get_salesforce_accounts,
        sync_sap_to_salesforce,
        sync_salesforce_to_sap,
        test_connections
    )
    SYNC_MODULE_AVAILABLE = True
except ImportError as e:
    logging.error(f"Impossible d'importer sync_clients: {e}")
    # Fallback pour éviter l'erreur au démarrage
    run_sync = None
    get_sap_customers = None
    get_salesforce_accounts = None
    sync_sap_to_salesforce = None
    sync_salesforce_to_sap = None
    test_connections = None
    SYNC_MODULE_AVAILABLE = False

router = APIRouter()

# Modèles Pydantic
class SyncDirection(str, Enum):
    SAP_TO_SF = "sap2sf"
    SF_TO_SAP = "sf2sap"
    BOTH = "both"

class SyncRequest(BaseModel):
    direction: SyncDirection
    dry_run: bool = False

class SyncStatus(BaseModel):
    id: str
    direction: str
    status: str  # "running", "completed", "failed"
    start_time: datetime
    end_time: Optional[datetime] = None
    progress: Dict[str, int]
    message: str
    error: Optional[str] = None

# Stockage en mémoire des tâches de synchronisation
sync_tasks: Dict[str, SyncStatus] = {}

# === ENDPOINTS PRINCIPAUX ===

@router.post("/start_sync")
async def start_sync(request: SyncRequest, background_tasks: BackgroundTasks):
    """
    Lance une synchronisation en arrière-plan
    """
    if not SYNC_MODULE_AVAILABLE:
        raise HTTPException(status_code=500, detail="Module de synchronisation non disponible")
    
    # Générer un ID unique pour cette tâche
    task_id = f"sync_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{request.direction.value}"
    
    # Créer l'entrée de statut
    sync_status = SyncStatus(
        id=task_id,
        direction=request.direction.value,
        status="running",
        start_time=datetime.now(),
        progress={"created": 0, "updated": 0, "failed": 0, "skipped": 0},
        message="Synchronisation démarrée"
    )
    
    sync_tasks[task_id] = sync_status
    
    # Lancer la tâche en arrière-plan
    background_tasks.add_task(
        execute_sync_task, 
        task_id, 
        request.direction.value, 
        request.dry_run
    )
    
    return {
        "task_id": task_id,
        "message": "Synchronisation démarrée en arrière-plan",
        "status": "running"
    }

@router.get("/sync_status/{task_id}")
async def get_sync_status(task_id: str):
    """
    Récupère le statut d'une tâche de synchronisation
    """
    if task_id not in sync_tasks:
        raise HTTPException(status_code=404, detail="Tâche de synchronisation non trouvée")
    
    return sync_tasks[task_id]

@router.get("/sync_history")
async def get_sync_history(limit: int = 10):
    """
    Récupère l'historique des synchronisations
    """
    # Trier par date de début décroissante
    sorted_tasks = sorted(
        sync_tasks.values(), 
        key=lambda x: x.start_time, 
        reverse=True
    )
    
    return {
        "total": len(sorted_tasks),
        "tasks": sorted_tasks[:limit]
    }

@router.get("/sync_stats")
async def get_sync_stats():
    """
    Récupère les statistiques globales de synchronisation
    """
    if not SYNC_MODULE_AVAILABLE:
        raise HTTPException(status_code=500, detail="Module de synchronisation non disponible")
    
    try:
        # Compter les clients dans chaque système
        sap_customers = await get_sap_customers()
        sf_accounts = await get_salesforce_accounts()
        
        # Calculer les statistiques
        total_sap = len(sap_customers)
        total_sf = len(sf_accounts)
        
        # Compter les clients avec AccountNumber (synchronisés)
        sf_with_account_number = len([acc for acc in sf_accounts if acc.get("AccountNumber")])
        
        # Statistiques des tâches
        total_tasks = len(sync_tasks)
        completed_tasks = len([t for t in sync_tasks.values() if t.status == "completed"])
        failed_tasks = len([t for t in sync_tasks.values() if t.status == "failed"])
        
        return {
            "clients": {
                "sap_total": total_sap,
                "salesforce_total": total_sf,
                "salesforce_with_account_number": sf_with_account_number,
                "sync_coverage": round((sf_with_account_number / total_sf * 100), 2) if total_sf > 0 else 0
            },
            "synchronizations": {
                "total_tasks": total_tasks,
                "completed": completed_tasks,
                "failed": failed_tasks,
                "success_rate": round((completed_tasks / total_tasks * 100), 2) if total_tasks > 0 else 0
            },
            "last_sync": max([t.start_time for t in sync_tasks.values()]) if sync_tasks else None
        }
        
    except Exception as e:
        logging.error(f"Erreur lors du calcul des statistiques: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors du calcul des statistiques: {str(e)}")

@router.delete("/clear_sync_history")
async def clear_sync_history():
    """
    Vide l'historique des synchronisations
    """
    global sync_tasks
    
    # Garder seulement les tâches en cours
    running_tasks = {k: v for k, v in sync_tasks.items() if v.status == "running"}
    sync_tasks = running_tasks
    
    return {
        "message": "Historique vidé",
        "remaining_tasks": len(sync_tasks)
    }

# === FONCTIONS UTILITAIRES ===

async def execute_sync_task(task_id: str, direction: str, dry_run: bool):
    """
    Exécute une tâche de synchronisation en arrière-plan
    """
    try:
        # Mettre à jour le statut
        sync_tasks[task_id].message = f"Exécution de la synchronisation {direction}"
        
        # Capturer les logs de synchronisation
        import io
        
        # Rediriger temporairement les logs
        log_capture = io.StringIO()
        
        # Exécuter la synchronisation
        if direction == "sap2sf":
            result = await sync_sap_to_salesforce(dry_run)
        elif direction == "sf2sap":
            result = await sync_salesforce_to_sap(dry_run)
        elif direction == "both":
            # Exécuter les deux directions
            result_sf = await sync_sap_to_salesforce(dry_run)
            result_sap = await sync_salesforce_to_sap(dry_run)
            
            # Combiner les résultats
            result = {
                "created": result_sf.get("created", 0) + result_sap.get("created", 0),
                "updated": result_sf.get("updated", 0) + result_sap.get("updated", 0),
                "failed": result_sf.get("failed", 0) + result_sap.get("failed", 0),
                "skipped": result_sf.get("skipped", 0) + result_sap.get("skipped", 0)
            }
        else:
            raise ValueError(f"Direction non supportée: {direction}")
        
        # Mise à jour du statut final
        sync_tasks[task_id].status = "completed"
        sync_tasks[task_id].end_time = datetime.now()
        sync_tasks[task_id].progress = result
        sync_tasks[task_id].message = "Synchronisation terminée avec succès"
        
        # Calculer la durée
        duration = (sync_tasks[task_id].end_time - sync_tasks[task_id].start_time).total_seconds()
        sync_tasks[task_id].message += f" en {duration:.1f}s"
        
    except Exception as e:
        # Mise à jour du statut d'erreur
        sync_tasks[task_id].status = "failed"
        sync_tasks[task_id].end_time = datetime.now()
        sync_tasks[task_id].error = str(e)
        sync_tasks[task_id].message = f"Erreur lors de la synchronisation: {str(e)}"
        
        logging.error(f"Erreur dans la tâche de sync {task_id}: {e}")

# === ENDPOINTS DE DIAGNOSTIC ===

@router.get("/test_connections")
async def test_sync_connections():
    """
    Test les connexions SAP et Salesforce pour la synchronisation
    """
    if not SYNC_MODULE_AVAILABLE:
        raise HTTPException(status_code=500, detail="Module de synchronisation non disponible")
    
    try:
        result = await test_connections()
        
        return {
            "connections_ok": result,
            "message": "Connexions testées avec succès" if result else "Échec du test des connexions"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors du test des connexions: {str(e)}")

@router.get("/preview_sync/{direction}")
async def preview_sync(direction: SyncDirection, limit: int = 5):
    """
    Aperçu des données qui seraient synchronisées (mode dry-run)
    """
    try:
        if direction == SyncDirection.SAP_TO_SF:
            sap_customers = await get_sap_customers()
            sf_accounts = await get_salesforce_accounts()
            
            # Simuler quels clients SAP seraient créés dans SF
            sf_accounts_by_number = {acc.get("AccountNumber"): acc for acc in sf_accounts if acc.get("AccountNumber")}
            
            would_create = []
            would_update = []
            
            for customer in sap_customers[:limit]:
                card_code = customer.get("CardCode")
                if card_code not in sf_accounts_by_number:
                    would_create.append({
                        "sap_code": card_code,
                        "sap_name": customer.get("CardName"),
                        "action": "create_in_salesforce"
                    })
                else:
                    would_update.append({
                        "sap_code": card_code,
                        "sap_name": customer.get("CardName"),
                        "sf_id": sf_accounts_by_number[card_code].get("Id"),
                        "action": "update_in_salesforce"
                    })
            
            return {
                "direction": "SAP → Salesforce",
                "would_create": would_create,
                "would_update": would_update,
                "total_sap_customers": len(sap_customers)
            }
            
        elif direction == SyncDirection.SF_TO_SAP:
            sf_accounts = await get_salesforce_accounts()
            sap_customers = await get_sap_customers()
            
            # Simuler quels comptes SF seraient créés dans SAP
            sap_by_code = {c.get("CardCode"): c for c in sap_customers if c.get("CardCode")}
            
            would_create = []
            would_skip = []
            
            for account in sf_accounts[:limit]:
                account_number = account.get("AccountNumber")
                if not account_number:
                    would_create.append({
                        "sf_id": account.get("Id"),
                        "sf_name": account.get("Name"),
                        "action": "create_in_sap"
                    })
                elif account_number in sap_by_code:
                    would_skip.append({
                        "sf_id": account.get("Id"),
                        "sf_name": account.get("Name"),
                        "sap_code": account_number,
                        "action": "skip_exists_in_sap"
                    })
            
            return {
                "direction": "Salesforce → SAP",
                "would_create": would_create,
                "would_skip": would_skip,
                "total_sf_accounts": len(sf_accounts)
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'aperçu: {str(e)}")