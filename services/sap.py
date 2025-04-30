# services/sap.py
import os
import httpx
from dotenv import load_dotenv
import datetime
from typing import Optional
import json
import logging

load_dotenv()

SAP_BASE_URL = os.getenv("SAP_REST_BASE_URL")

sap_session = {
    "cookies": None,
    "expires": None
}
# Activer le mode debug complet de httpx
httpx_log = logging.getLogger("httpx")
httpx_log.setLevel(logging.DEBUG)
httpx_log.addHandler(logging.StreamHandler())

async def login_sap():
    url = SAP_BASE_URL + "/Login"
    auth_payload = {
        "UserName": os.getenv("SAP_USER"),
        "Password": os.getenv("SAP_CLIENT_PASSWORD"),
        "CompanyDB": os.getenv("SAP_CLIENT")
    }
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "curl/8.5.0"  # On imite le comportement de curl (très important)
    }
    data = json.dumps(auth_payload)

    async with httpx.AsyncClient(verify=False, http2=False, headers=headers) as client:
        print("----> LOGIN SAP - Envoi du payload:")
        print(data)
        response = await client.post(url, content=data)
        response.raise_for_status()
        sap_session["cookies"] = response.cookies
        sap_session["expires"] = datetime.datetime.utcnow().timestamp() + 60 * 20

async def call_sap(endpoint: str, method="GET", payload: Optional[dict] = None):
    if not sap_session["cookies"] or datetime.datetime.utcnow().timestamp() > sap_session["expires"]:
        await login_sap()

    async with httpx.AsyncClient(cookies=sap_session["cookies"], verify=False) as client:
        url = SAP_BASE_URL + endpoint
        try:
            if method == "GET":
                response = await client.get(url)
            else:
                response = await client.post(url, json=payload or {})
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                await login_sap()
                return await call_sap(endpoint, method, payload)
            raise