"""
Attachment Storage Service - NOVA-SERVER
Télécharge et stocke localement les pièces jointes des emails Office365.

Objectif : rendre les PJ accessibles sans dépendance à Microsoft Graph au moment
de la consultation (fiabilité + vitesse). Le téléchargement est déclenché
automatiquement lors de l'analyse d'un email.

Stockage : data/attachments/{safe_email_id}/{attachment_id}_{filename}
Base de données : email_analysis.db (table stored_attachments)
"""

import os
import re
import logging
import sqlite3
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# ============================================================
# CONSTANTES
# ============================================================

MAX_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB par pièce jointe
STORAGE_BASE = Path(__file__).parent.parent / "data" / "attachments"

# Types MIME supportés (autres types sont stockés aussi mais sans preview)
PREVIEWABLE_TYPES = {
    "application/pdf",
    "image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp",
    "text/plain", "text/html", "text/csv",
}


# ============================================================
# MODÈLE
# ============================================================

class StoredAttachment:
    """Métadonnées d'une pièce jointe stockée localement."""
    __slots__ = ("id", "email_id", "attachment_id", "filename",
                 "content_type", "size", "local_path", "downloaded_at")

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "email_id": self.email_id,
            "attachment_id": self.attachment_id,
            "filename": self.filename,
            "content_type": self.content_type,
            "size": self.size,
            "local_path": str(self.local_path),
            "downloaded_at": self.downloaded_at,
            "is_previewable": self.content_type in PREVIEWABLE_TYPES if self.content_type else False,
        }


# ============================================================
# SERVICE
# ============================================================

class AttachmentStorageService:
    """
    Service de stockage local des pièces jointes email.

    Workflow :
    1. download_and_store_all(email_id, message_id, graph_service)
       → télécharge toutes les PJ, les écrit sur disque, enregistre en DB
    2. get_stored_attachments(email_id)
       → liste les PJ disponibles
    3. get_attachment_path(email_id, attachment_id)
       → retourne le chemin disque pour FileResponse
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = str(Path(__file__).parent.parent / "email_analysis.db")
        self.db_path = db_path
        self._ensure_table()
        STORAGE_BASE.mkdir(parents=True, exist_ok=True)

    def _ensure_table(self):
        """Crée la table stored_attachments si elle n'existe pas."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stored_attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email_id TEXT NOT NULL,
                attachment_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                content_type TEXT,
                size INTEGER,
                local_path TEXT NOT NULL,
                downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(email_id, attachment_id)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_sa_email_id
            ON stored_attachments(email_id)
        """)
        conn.commit()
        conn.close()

    # ----------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------

    @staticmethod
    def _safe_email_dir(email_id: str) -> str:
        """Convertit un email_id en nom de répertoire safe (remplace car. spéciaux)."""
        # SHA256 court pour rester lisible et éviter les collisions sur chemins longs
        short_hash = hashlib.sha256(email_id.encode()).hexdigest()[:16]
        return short_hash

    @staticmethod
    def _safe_filename(filename: str) -> str:
        """Sanitise un nom de fichier."""
        safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', filename)
        return safe[:200]  # Limite longueur

    def _get_storage_dir(self, email_id: str) -> Path:
        dir_name = self._safe_email_dir(email_id)
        path = STORAGE_BASE / dir_name
        path.mkdir(parents=True, exist_ok=True)
        return path

    # ----------------------------------------------------------
    # Téléchargement
    # ----------------------------------------------------------

    async def download_and_store_all(
        self,
        email_id: str,
        message_id: str,
        graph_service,
    ) -> List[StoredAttachment]:
        """
        Télécharge et stocke toutes les PJ d'un email.

        Args:
            email_id: ID canonique de l'email (peut différer du message_id)
            message_id: ID Microsoft Graph du message
            graph_service: Instance de GraphService

        Returns:
            Liste des StoredAttachment téléchargés (peut être vide)
        """
        try:
            # Lister les PJ via Graph API
            attachments = await graph_service.get_attachments(message_id)
        except Exception as exc:
            logger.error("Erreur listage PJ pour email %s: %s", email_id[:30], exc)
            return []

        if not attachments:
            logger.info("Email %s: aucune pièce jointe", email_id[:30])
            return []

        results = []
        storage_dir = self._get_storage_dir(email_id)

        for att in attachments:
            try:
                stored = await self._download_one(
                    email_id=email_id,
                    message_id=message_id,
                    att=att,
                    storage_dir=storage_dir,
                    graph_service=graph_service,
                )
                if stored:
                    results.append(stored)
            except Exception as exc:
                logger.warning(
                    "Erreur téléchargement PJ '%s' pour email %s: %s",
                    att.name, email_id[:30], exc
                )

        logger.info(
            "Email %s: %d/%d pièces jointes stockées",
            email_id[:30], len(results), len(attachments)
        )
        return results

    async def _download_one(
        self,
        email_id: str,
        message_id: str,
        att,
        storage_dir: Path,
        graph_service,
    ) -> Optional[StoredAttachment]:
        """Télécharge une seule PJ et la stocke."""
        # Vérifier si déjà stockée
        existing = self._get_from_db(email_id, att.id)
        if existing and Path(existing.local_path).exists():
            logger.debug("PJ '%s' déjà stockée pour email %s", att.name, email_id[:30])
            return existing

        # Vérifier taille avant téléchargement
        if att.size and att.size > MAX_SIZE_BYTES:
            logger.warning(
                "PJ '%s' trop lourde (%d bytes > %d max) — ignorée",
                att.name, att.size, MAX_SIZE_BYTES
            )
            return None

        # Télécharger le contenu
        logger.info("Téléchargement PJ '%s' (%d bytes)...", att.name, att.size or 0)
        content = await graph_service.get_attachment_content(message_id, att.id)

        if not content:
            logger.warning("PJ '%s': contenu vide", att.name)
            return None

        # Vérification taille après téléchargement
        if len(content) > MAX_SIZE_BYTES:
            logger.warning(
                "PJ '%s': contenu %d bytes > limite %d — ignorée",
                att.name, len(content), MAX_SIZE_BYTES
            )
            return None

        # Écrire sur disque
        safe_att_id = re.sub(r'[^a-zA-Z0-9_-]', '_', att.id)[:40]
        safe_name = self._safe_filename(att.name)
        filename = f"{safe_att_id}_{safe_name}"
        local_path = storage_dir / filename

        local_path.write_bytes(content)
        logger.info("PJ '%s' stockée: %s", att.name, local_path)

        # Enregistrer en DB
        stored = self._save_to_db(
            email_id=email_id,
            attachment_id=att.id,
            filename=att.name,
            content_type=att.content_type,
            size=len(content),
            local_path=str(local_path),
        )
        return stored

    # ----------------------------------------------------------
    # Lecture
    # ----------------------------------------------------------

    def get_stored_attachments(self, email_id: str) -> List[StoredAttachment]:
        """Retourne la liste des PJ stockées pour un email."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM stored_attachments WHERE email_id = ? ORDER BY id",
            (email_id,)
        ).fetchall()
        conn.close()

        result = []
        for row in rows:
            att = StoredAttachment(
                id=row["id"],
                email_id=row["email_id"],
                attachment_id=row["attachment_id"],
                filename=row["filename"],
                content_type=row["content_type"],
                size=row["size"],
                local_path=row["local_path"],
                downloaded_at=row["downloaded_at"],
            )
            # Vérifier que le fichier existe encore
            if Path(att.local_path).exists():
                result.append(att)
            else:
                logger.warning("Fichier PJ manquant: %s", att.local_path)

        return result

    def get_attachment_path(self, email_id: str, attachment_id: str) -> Optional[Path]:
        """Retourne le chemin disque d'une PJ, ou None si non trouvée."""
        att = self._get_from_db(email_id, attachment_id)
        if att is None:
            return None
        path = Path(att.local_path)
        return path if path.exists() else None

    def has_stored_attachments(self, email_id: str) -> bool:
        """True si des PJ sont déjà stockées pour cet email."""
        conn = sqlite3.connect(self.db_path)
        count = conn.execute(
            "SELECT COUNT(*) FROM stored_attachments WHERE email_id = ?",
            (email_id,)
        ).fetchone()[0]
        conn.close()
        return count > 0

    # ----------------------------------------------------------
    # DB helpers
    # ----------------------------------------------------------

    def _get_from_db(self, email_id: str, attachment_id: str) -> Optional[StoredAttachment]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM stored_attachments WHERE email_id = ? AND attachment_id = ?",
            (email_id, attachment_id)
        ).fetchone()
        conn.close()
        if not row:
            return None
        return StoredAttachment(
            id=row["id"],
            email_id=row["email_id"],
            attachment_id=row["attachment_id"],
            filename=row["filename"],
            content_type=row["content_type"],
            size=row["size"],
            local_path=row["local_path"],
            downloaded_at=row["downloaded_at"],
        )

    def _save_to_db(
        self, email_id: str, attachment_id: str, filename: str,
        content_type: Optional[str], size: int, local_path: str
    ) -> StoredAttachment:
        now = datetime.now().isoformat()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            """
            INSERT OR REPLACE INTO stored_attachments
            (email_id, attachment_id, filename, content_type, size, local_path, downloaded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (email_id, attachment_id, filename, content_type, size, local_path, now)
        )
        row_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return StoredAttachment(
            id=row_id,
            email_id=email_id,
            attachment_id=attachment_id,
            filename=filename,
            content_type=content_type,
            size=size,
            local_path=local_path,
            downloaded_at=now,
        )

    # ----------------------------------------------------------
    # Nettoyage
    # ----------------------------------------------------------

    def cleanup_old_attachments(self, days: int = 30):
        """Supprime les PJ plus vieilles que `days` jours."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT local_path FROM stored_attachments WHERE downloaded_at < ?",
            (cutoff,)
        ).fetchall()

        deleted_files = 0
        for (path_str,) in rows:
            path = Path(path_str)
            if path.exists():
                path.unlink()
                deleted_files += 1

        conn.execute(
            "DELETE FROM stored_attachments WHERE downloaded_at < ?",
            (cutoff,)
        )
        conn.commit()
        conn.close()
        logger.info("Nettoyage PJ: %d fichiers supprimés (> %d jours)", deleted_files, days)


# ============================================================
# SINGLETON
# ============================================================

_attachment_storage: Optional[AttachmentStorageService] = None


def get_attachment_storage() -> AttachmentStorageService:
    """Retourne l'instance singleton du service de stockage des PJ."""
    global _attachment_storage
    if _attachment_storage is None:
        _attachment_storage = AttachmentStorageService()
        logger.info("AttachmentStorageService singleton créé (base: %s)", STORAGE_BASE)
    return _attachment_storage
