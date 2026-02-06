"""
Routes API pour la gestion des tarifs fournisseurs.
- Configuration du dossier source
- Indexation des fichiers
- Recherche dans les produits indexés
"""

import os
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv, set_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/supplier-tariffs", tags=["Supplier Tariffs"])

# Chemin du fichier .env
ENV_FILE = Path(__file__).parent.parent / ".env"

# Variable pour suivre l'état de l'indexation
indexation_state = {
    "running": False,
    "progress": 0,
    "current_file": None,
    "session_id": None
}


class FolderConfig(BaseModel):
    """Configuration du dossier tarifs fournisseurs."""
    folder_path: str


class IndexationOptions(BaseModel):
    """Options d'indexation."""
    clear_existing: bool = False
    recursive: bool = True


# ==================== CONFIGURATION DU DOSSIER ====================

@router.get("/folder")
async def get_supplier_folder():
    """Récupère le chemin du dossier tarifs fournisseurs configuré."""
    load_dotenv(ENV_FILE, override=True)
    folder_path = os.getenv("SUPPLIER_TARIFF_FOLDER", "")

    return {
        "folder_path": folder_path,
        "exists": Path(folder_path).exists() if folder_path else False,
        "configured": bool(folder_path)
    }


@router.post("/folder")
async def set_supplier_folder(config: FolderConfig):
    """Configure le chemin du dossier tarifs fournisseurs."""
    folder_path = config.folder_path.strip()

    # Vérifier que le dossier existe
    if not Path(folder_path).exists():
        raise HTTPException(
            status_code=400,
            detail=f"Le dossier n'existe pas: {folder_path}"
        )

    if not Path(folder_path).is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"Le chemin n'est pas un dossier: {folder_path}"
        )

    # Sauvegarder dans le fichier .env
    try:
        set_key(str(ENV_FILE), "SUPPLIER_TARIFF_FOLDER", folder_path)
        logger.info(f"Dossier tarifs fournisseurs configuré: {folder_path}")

        return {
            "success": True,
            "folder_path": folder_path,
            "message": "Dossier configuré avec succès"
        }

    except Exception as e:
        logger.error(f"Erreur sauvegarde config: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la sauvegarde: {str(e)}"
        )


@router.get("/browse")
async def browse_folder(start_path: str = "C:\\"):
    """
    Ouvre un dialogue Windows pour sélectionner un dossier.
    Retourne le chemin sélectionné.
    """
    import sys

    if sys.platform != "win32":
        raise HTTPException(
            status_code=400,
            detail="Cette fonctionnalité est uniquement disponible sur Windows"
        )

    try:
        import tkinter as tk
        from tkinter import filedialog

        # Créer une fenêtre cachée
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)

        # Ouvrir le dialogue de sélection de dossier
        folder_path = filedialog.askdirectory(
            initialdir=start_path,
            title="Sélectionner le dossier des tarifs fournisseurs"
        )

        root.destroy()

        if folder_path:
            # Convertir en chemin Windows
            folder_path = str(Path(folder_path))

            return {
                "success": True,
                "folder_path": folder_path,
                "exists": True
            }
        else:
            return {
                "success": False,
                "folder_path": None,
                "message": "Aucun dossier sélectionné"
            }

    except Exception as e:
        logger.error(f"Erreur dialogue dossier: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de l'ouverture du dialogue: {str(e)}"
        )


@router.get("/folder/contents")
async def get_folder_contents():
    """Récupère la liste des fichiers dans le dossier configuré."""
    load_dotenv(ENV_FILE, override=True)
    folder_path = os.getenv("SUPPLIER_TARIFF_FOLDER", "")

    if not folder_path:
        raise HTTPException(
            status_code=400,
            detail="Aucun dossier configuré"
        )

    if not Path(folder_path).exists():
        raise HTTPException(
            status_code=400,
            detail=f"Le dossier n'existe pas: {folder_path}"
        )

    try:
        from services.file_parsers import scan_folder

        files = scan_folder(folder_path, recursive=True)

        # Statistiques par type
        stats = {}
        for f in files:
            ftype = f['type']
            stats[ftype] = stats.get(ftype, 0) + 1

        return {
            "folder_path": folder_path,
            "total_files": len(files),
            "files_by_type": stats,
            "files": files[:100]  # Limiter à 100 fichiers pour l'affichage
        }

    except Exception as e:
        logger.error(f"Erreur lecture dossier: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la lecture du dossier: {str(e)}"
        )


# ==================== INDEXATION ====================

@router.get("/status")
async def get_indexation_status():
    """Récupère le statut actuel de l'indexation."""
    from services.supplier_tariffs_db import get_indexation_stats

    stats = get_indexation_stats()

    return {
        "indexation_running": indexation_state["running"],
        "progress": indexation_state["progress"],
        "current_file": indexation_state["current_file"],
        "stats": stats
    }


@router.post("/index")
async def start_indexation(
    options: IndexationOptions,
    background_tasks: BackgroundTasks
):
    """Lance l'indexation des fichiers du dossier configuré."""
    global indexation_state

    if indexation_state["running"]:
        raise HTTPException(
            status_code=409,
            detail="Une indexation est déjà en cours"
        )

    load_dotenv(ENV_FILE, override=True)
    folder_path = os.getenv("SUPPLIER_TARIFF_FOLDER", "")

    if not folder_path:
        raise HTTPException(
            status_code=400,
            detail="Aucun dossier configuré. Veuillez d'abord configurer le dossier."
        )

    if not Path(folder_path).exists():
        raise HTTPException(
            status_code=400,
            detail=f"Le dossier n'existe pas: {folder_path}"
        )

    # Lancer l'indexation en arrière-plan
    background_tasks.add_task(
        run_indexation,
        folder_path,
        options.clear_existing,
        options.recursive
    )

    return {
        "success": True,
        "message": "Indexation démarrée en arrière-plan",
        "folder_path": folder_path
    }


async def run_indexation(folder_path: str, clear_existing: bool, recursive: bool):
    """Exécute l'indexation des fichiers."""
    global indexation_state

    from services.supplier_tariffs_db import (
        start_indexation, update_indexation_session,
        add_indexed_file, add_supplier_products_batch,
        update_file_status, clear_all_data
    )
    from services.file_parsers import scan_folder, parse_file

    indexation_state["running"] = True
    indexation_state["progress"] = 0
    indexation_state["current_file"] = None

    session_id = start_indexation()
    indexation_state["session_id"] = session_id

    files_processed = 0
    files_success = 0
    files_error = 0
    total_items = 0

    try:
        # Optionnel: effacer les données existantes
        if clear_existing:
            clear_all_data()
            logger.info("Données existantes effacées")

        # Scanner le dossier
        files = scan_folder(folder_path, recursive=recursive)
        total_files = len(files)

        logger.info(f"Indexation de {total_files} fichiers depuis {folder_path}")

        for i, file_info in enumerate(files):
            file_path = file_info['path']
            indexation_state["current_file"] = file_info['name']
            indexation_state["progress"] = int((i / total_files) * 100)

            try:
                # Ajouter le fichier à la base
                file_id = add_indexed_file(
                    file_path=file_path,
                    file_name=file_info['name'],
                    file_type=file_info['type'],
                    file_size=file_info['size'],
                    last_modified=file_info['modified']
                )

                # Parser le fichier
                products = parse_file(file_path)

                if products:
                    # Ajouter les produits
                    count = add_supplier_products_batch(file_id, products)
                    update_file_status(file_id, 'indexed', items_count=count)
                    total_items += count
                    files_success += 1
                    logger.info(f"Indexé: {file_info['name']} - {count} produits")
                else:
                    update_file_status(file_id, 'empty', error_message="Aucun produit extrait")
                    files_success += 1  # Fichier traité sans erreur

            except Exception as e:
                logger.error(f"Erreur indexation {file_path}: {e}")
                files_error += 1
                try:
                    file_id = add_indexed_file(
                        file_path=file_path,
                        file_name=file_info['name'],
                        file_type=file_info['type'],
                        file_size=file_info['size'],
                        last_modified=file_info['modified']
                    )
                    update_file_status(file_id, 'error', error_message=str(e))
                except:
                    pass

            files_processed += 1

        # Mise à jour finale
        update_indexation_session(
            session_id,
            status='completed',
            files_processed=files_processed,
            files_success=files_success,
            files_error=files_error,
            items_extracted=total_items
        )

        logger.info(f"Indexation terminée: {files_success} réussis, {files_error} erreurs, {total_items} produits")

    except Exception as e:
        logger.error(f"Erreur indexation globale: {e}")
        update_indexation_session(
            session_id,
            status='error',
            files_processed=files_processed,
            files_success=files_success,
            files_error=files_error,
            items_extracted=total_items,
            error_message=str(e)
        )

    finally:
        indexation_state["running"] = False
        indexation_state["progress"] = 100
        indexation_state["current_file"] = None


@router.post("/index/stop")
async def stop_indexation():
    """Arrête l'indexation en cours."""
    global indexation_state

    if not indexation_state["running"]:
        return {"success": False, "message": "Aucune indexation en cours"}

    # Note: L'arrêt réel nécessiterait un mécanisme de signal
    # Pour l'instant on marque juste comme non running
    indexation_state["running"] = False

    return {"success": True, "message": "Demande d'arrêt envoyée"}


# ==================== RECHERCHE ====================

@router.get("/search")
async def search_products(q: str, limit: int = 50):
    """Recherche des produits dans les tarifs indexés."""
    if not q or len(q) < 2:
        raise HTTPException(
            status_code=400,
            detail="La recherche doit contenir au moins 2 caractères"
        )

    from services.supplier_tariffs_db import search_products as db_search

    results = db_search(q, limit=limit)

    return {
        "query": q,
        "count": len(results),
        "results": results
    }


@router.get("/products")
async def get_products(limit: int = 100, offset: int = 0):
    """Récupère la liste des produits indexés."""
    from services.supplier_tariffs_db import get_all_products

    products = get_all_products(limit=limit, offset=offset)

    return {
        "count": len(products),
        "limit": limit,
        "offset": offset,
        "products": products
    }


@router.get("/files")
async def get_indexed_files():
    """Récupère la liste des fichiers indexés."""
    from services.supplier_tariffs_db import get_indexed_files as db_get_files

    files = db_get_files()

    return {
        "count": len(files),
        "files": files
    }
