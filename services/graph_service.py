# services/graph_service.py
"""
Service Microsoft Graph pour la gestion des emails Office 365.
Token caching au niveau module avec expiration automatique.
"""

import os
import time
import logging
import httpx
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Cache du token au niveau module
_token_cache = {
    "access_token": None,
    "expires_at": 0
}


class GraphAttachment(BaseModel):
    id: str
    name: str
    content_type: str
    size: int
    content_bytes: Optional[str] = None


class GraphEmailAddress(BaseModel):
    name: str
    address: str


class GraphEmail(BaseModel):
    id: str
    subject: str
    from_name: str
    from_address: str
    received_datetime: str
    body_preview: str
    body_content: Optional[str] = None
    body_content_type: Optional[str] = None
    has_attachments: bool
    is_read: bool
    attachments: List[GraphAttachment] = []


class GraphEmailsResponse(BaseModel):
    emails: List[GraphEmail]
    total_count: int
    next_link: Optional[str] = None


class GraphService:
    """Service centralisé pour Microsoft Graph API."""

    def __init__(self):
        self.tenant_id = os.getenv("MS_TENANT_ID")
        self.client_id = os.getenv("MS_CLIENT_ID")
        self.client_secret = os.getenv("MS_CLIENT_SECRET")
        self.mailbox_address = os.getenv("MS_MAILBOX_ADDRESS")
        self.graph_base_url = "https://graph.microsoft.com/v1.0"

    def is_configured(self) -> bool:
        """Vérifie si les credentials sont configurés."""
        return all([
            self.tenant_id,
            self.client_id,
            self.client_secret,
            self.mailbox_address
        ])

    async def get_access_token(self) -> str:
        """
        Récupère un token d'accès avec cache.
        Le token est mis en cache avec un buffer de 5 minutes avant expiration.
        """
        global _token_cache

        # Vérifier si le token en cache est encore valide (avec 5 min de marge)
        if _token_cache["access_token"] and time.time() < _token_cache["expires_at"] - 300:
            logger.debug("Using cached access token")
            return _token_cache["access_token"]

        logger.info("Acquiring new access token...")

        if not self.is_configured():
            raise ValueError("Microsoft Graph credentials not configured")

        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        token_data = {
            "client_id": self.client_id,
            "scope": "https://graph.microsoft.com/.default",
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                token_url,
                data=token_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )

            if response.status_code != 200:
                error_data = response.json()
                error_msg = error_data.get("error_description", f"Token acquisition failed ({response.status_code})")
                logger.error(f"Token acquisition error: {error_msg}")
                raise Exception(error_msg)

            token_json = response.json()
            access_token = token_json.get("access_token")
            expires_in = token_json.get("expires_in", 3600)

            # Mettre en cache
            _token_cache["access_token"] = access_token
            _token_cache["expires_at"] = time.time() + expires_in

            logger.info(f"Token acquired, expires in {expires_in}s")
            return access_token

    async def _make_graph_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Effectue une requête vers Microsoft Graph API."""
        token = await self.get_access_token()

        url = f"{self.graph_base_url}{endpoint}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                }
            )

            if response.status_code == 401:
                # Token expiré, invalider le cache et réessayer
                global _token_cache
                _token_cache["access_token"] = None
                _token_cache["expires_at"] = 0
                token = await self.get_access_token()

                response = await client.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json"
                    }
                )

            if response.status_code >= 400:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get("error", {}).get("message", f"Graph API error ({response.status_code})")
                logger.error(f"Graph API error: {error_msg}")
                raise Exception(error_msg)

            return response.json() if response.content else {}

    async def _make_graph_request_raw(self, endpoint: str) -> bytes:
        """Effectue une requête et retourne les bytes bruts (pour les pièces jointes)."""
        token = await self.get_access_token()

        url = f"{self.graph_base_url}{endpoint}"

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {token}"}
            )

            if response.status_code >= 400:
                raise Exception(f"Graph API error ({response.status_code})")

            return response.content

    async def get_emails(
        self,
        top: int = 50,
        skip: int = 0,
        unread_only: bool = False,
        folder: str = "Inbox"
    ) -> GraphEmailsResponse:
        """
        Récupère les emails de la boîte de réception.

        Args:
            top: Nombre d'emails à récupérer (max 50)
            skip: Nombre d'emails à sauter (pagination)
            unread_only: Filtrer uniquement les non-lus
            folder: Dossier à consulter (défaut: Inbox)
        """
        params = {
            "$top": min(top, 50),
            "$skip": skip,
            "$orderby": "receivedDateTime desc",
            "$select": "id,subject,from,receivedDateTime,bodyPreview,hasAttachments,isRead"
        }

        if unread_only:
            params["$filter"] = "isRead eq false"

        endpoint = f"/users/{self.mailbox_address}/mailFolders/{folder}/messages"

        data = await self._make_graph_request("GET", endpoint, params=params)

        emails = []
        for msg in data.get("value", []):
            from_data = msg.get("from", {}).get("emailAddress", {})
            emails.append(GraphEmail(
                id=msg.get("id", ""),
                subject=msg.get("subject", "(Sans objet)"),
                from_name=from_data.get("name", ""),
                from_address=from_data.get("address", ""),
                received_datetime=msg.get("receivedDateTime", ""),
                body_preview=msg.get("bodyPreview", ""),
                has_attachments=msg.get("hasAttachments", False),
                is_read=msg.get("isRead", False)
            ))

        return GraphEmailsResponse(
            emails=emails,
            total_count=len(emails),
            next_link=data.get("@odata.nextLink")
        )

    async def get_email(self, message_id: str, include_attachments: bool = True) -> GraphEmail:
        """
        Récupère un email complet avec son body et optionnellement ses pièces jointes.

        Args:
            message_id: ID du message
            include_attachments: Inclure les métadonnées des pièces jointes
        """
        endpoint = f"/users/{self.mailbox_address}/messages/{message_id}"
        params = {
            "$select": "id,subject,from,receivedDateTime,bodyPreview,body,hasAttachments,isRead"
        }

        if include_attachments:
            params["$expand"] = "attachments($select=id,name,contentType,size)"

        data = await self._make_graph_request("GET", endpoint, params=params)

        from_data = data.get("from", {}).get("emailAddress", {})
        body_data = data.get("body", {})

        attachments = []
        for att in data.get("attachments", []):
            attachments.append(GraphAttachment(
                id=att.get("id", ""),
                name=att.get("name", ""),
                content_type=att.get("contentType", ""),
                size=att.get("size", 0)
            ))

        return GraphEmail(
            id=data.get("id", ""),
            subject=data.get("subject", "(Sans objet)"),
            from_name=from_data.get("name", ""),
            from_address=from_data.get("address", ""),
            received_datetime=data.get("receivedDateTime", ""),
            body_preview=data.get("bodyPreview", ""),
            body_content=body_data.get("content", ""),
            body_content_type=body_data.get("contentType", "text"),
            has_attachments=data.get("hasAttachments", False),
            is_read=data.get("isRead", False),
            attachments=attachments
        )

    async def get_attachments(self, message_id: str) -> List[GraphAttachment]:
        """Récupère la liste des pièces jointes d'un email."""
        endpoint = f"/users/{self.mailbox_address}/messages/{message_id}/attachments"
        params = {"$select": "id,name,contentType,size"}

        data = await self._make_graph_request("GET", endpoint, params=params)

        attachments = []
        for att in data.get("value", []):
            attachments.append(GraphAttachment(
                id=att.get("id", ""),
                name=att.get("name", ""),
                content_type=att.get("contentType", ""),
                size=att.get("size", 0)
            ))

        return attachments

    async def get_attachment_content(self, message_id: str, attachment_id: str) -> bytes:
        """
        Récupère le contenu d'une pièce jointe.

        Pour les pièces jointes < 4MB, utilise l'endpoint standard.
        Pour les pièces jointes > 4MB, utilise $value.
        """
        # D'abord, récupérer les métadonnées pour vérifier la taille
        endpoint = f"/users/{self.mailbox_address}/messages/{message_id}/attachments/{attachment_id}"

        try:
            # Essayer de récupérer avec contentBytes (petites pièces jointes)
            data = await self._make_graph_request("GET", endpoint)

            if "contentBytes" in data:
                import base64
                return base64.b64decode(data["contentBytes"])

        except Exception:
            pass

        # Fallback: récupérer directement les bytes
        endpoint_raw = f"/users/{self.mailbox_address}/messages/{message_id}/attachments/{attachment_id}/$value"
        return await self._make_graph_request_raw(endpoint_raw)

    async def mark_as_read(self, message_id: str) -> bool:
        """Marque un email comme lu."""
        endpoint = f"/users/{self.mailbox_address}/messages/{message_id}"
        try:
            await self._make_graph_request("PATCH", endpoint, json_data={"isRead": True})
            return True
        except Exception as e:
            logger.error(f"Failed to mark email as read: {e}")
            return False


# Instance singleton
_graph_service: Optional[GraphService] = None


def get_graph_service() -> GraphService:
    """Factory pattern pour obtenir l'instance du service Graph."""
    global _graph_service
    if _graph_service is None:
        _graph_service = GraphService()
        logger.info("GraphService instance created")
    return _graph_service
