# routes/routes_graph.py
"""
Routes API pour Microsoft Graph (connexion Office 365 / emails)
"""

import os
import logging
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)
router = APIRouter()


class ConnectionTestDetails(BaseModel):
    tenantId: bool = False
    clientId: bool = False
    clientSecret: bool = False
    mailboxAddress: bool = False
    tokenAcquired: bool = False
    mailboxAccessible: bool = False


class MailboxInfo(BaseModel):
    displayName: str
    mail: str


class ConnectionTestResult(BaseModel):
    success: bool
    step: str
    details: ConnectionTestDetails
    error: Optional[str] = None
    mailboxInfo: Optional[MailboxInfo] = None


class GraphCredentials(BaseModel):
    tenantId: Optional[str] = None
    clientId: Optional[str] = None
    clientSecret: Optional[str] = None
    mailboxAddress: Optional[str] = None


@router.get("/test-connection", response_model=ConnectionTestResult)
async def test_graph_connection():
    """
    Teste la connexion Microsoft Graph avec les credentials du .env
    """
    tenant_id = os.getenv("MS_TENANT_ID")
    client_id = os.getenv("MS_CLIENT_ID")
    client_secret = os.getenv("MS_CLIENT_SECRET")
    mailbox_address = os.getenv("MS_MAILBOX_ADDRESS")

    result = ConnectionTestResult(
        success=False,
        step="checking_credentials",
        details=ConnectionTestDetails(
            tenantId=bool(tenant_id),
            clientId=bool(client_id),
            clientSecret=bool(client_secret),
            mailboxAddress=bool(mailbox_address),
        )
    )

    # Step 1: Check all credentials are present
    if not all([tenant_id, client_id, client_secret, mailbox_address]):
        missing = []
        if not tenant_id:
            missing.append("MS_TENANT_ID")
        if not client_id:
            missing.append("MS_CLIENT_ID")
        if not client_secret:
            missing.append("MS_CLIENT_SECRET")
        if not mailbox_address:
            missing.append("MS_MAILBOX_ADDRESS")
        result.error = f"Missing credentials: {', '.join(missing)}"
        return result

    # Step 2: Acquire access token
    result.step = "acquiring_token"
    logger.info("Testing token acquisition...")

    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    token_data = {
        "client_id": client_id,
        "scope": "https://graph.microsoft.com/.default",
        "client_secret": client_secret,
        "grant_type": "client_credentials",
    }

    try:
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                token_url,
                data=token_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )

            if token_response.status_code != 200:
                error_data = token_response.json()
                error_message = error_data.get("error_description", f"Token acquisition failed ({token_response.status_code})")
                result.error = error_message
                logger.error(f"Token error: {error_message}")
                return result

            token_json = token_response.json()
            access_token = token_json.get("access_token")
            result.details.tokenAcquired = True
            logger.info("Token acquired successfully")

            # Step 3: Test mailbox access
            result.step = "testing_mailbox"
            logger.info(f"Testing mailbox access for: {mailbox_address}")

            user_url = f"https://graph.microsoft.com/v1.0/users/{mailbox_address}"
            user_response = await client.get(
                user_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                }
            )

            if user_response.status_code != 200:
                error_data = user_response.json()
                error_message = error_data.get("error", {}).get("message", f"Mailbox access failed ({user_response.status_code})")
                result.error = error_message
                logger.error(f"Mailbox access error: {error_message}")
                return result

            user_data = user_response.json()
            result.details.mailboxAccessible = True
            result.mailboxInfo = MailboxInfo(
                displayName=user_data.get("displayName", "Unknown"),
                mail=user_data.get("mail", mailbox_address)
            )

            # All tests passed
            result.success = True
            result.step = "complete"
            logger.info(f"Connection test successful: {result.mailboxInfo}")

            return result

    except httpx.RequestError as e:
        result.error = f"Network error: {str(e)}"
        logger.error(f"Connection test error: {e}")
        return result
    except Exception as e:
        result.error = f"Unexpected error: {str(e)}"
        logger.error(f"Connection test error: {e}")
        return result


@router.post("/update-credentials")
async def update_credentials(credentials: GraphCredentials):
    """
    Met a jour les credentials Microsoft Graph dans le .env
    Note: Cette route met a jour le fichier .env mais necessite un redemarrage pour prendre effet
    """
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")

    try:
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        updates = {}
        if credentials.tenantId:
            updates["MS_TENANT_ID"] = credentials.tenantId
        if credentials.clientId:
            updates["MS_CLIENT_ID"] = credentials.clientId
        if credentials.clientSecret:
            updates["MS_CLIENT_SECRET"] = credentials.clientSecret
        if credentials.mailboxAddress:
            updates["MS_MAILBOX_ADDRESS"] = credentials.mailboxAddress

        new_lines = []
        updated_keys = set()

        for line in lines:
            key = line.split("=")[0].strip() if "=" in line else None
            if key in updates:
                new_lines.append(f"{key}={updates[key]}\n")
                updated_keys.add(key)
            else:
                new_lines.append(line)

        # Add any new keys that weren't in the file
        for key, value in updates.items():
            if key not in updated_keys:
                new_lines.append(f"{key}={value}\n")

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        # Reload environment variables
        load_dotenv(override=True)

        return {"success": True, "message": "Credentials updated. Restart may be required."}

    except Exception as e:
        logger.error(f"Failed to update credentials: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/credentials-status")
async def get_credentials_status():
    """
    Retourne le statut des credentials (configures ou non, sans les valeurs)
    """
    return {
        "tenantId": bool(os.getenv("MS_TENANT_ID")),
        "clientId": bool(os.getenv("MS_CLIENT_ID")),
        "clientSecret": bool(os.getenv("MS_CLIENT_SECRET")),
        "mailboxAddress": bool(os.getenv("MS_MAILBOX_ADDRESS")),
        "mailboxAddressValue": os.getenv("MS_MAILBOX_ADDRESS", "")
    }
