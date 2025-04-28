from fastapi import FastAPI, WebSocket, Request, Header, HTTPException, Depends
from pydantic import BaseModel
import os
import json
import requests
from dotenv import load_dotenv
from simple_salesforce import Salesforce
from typing import Optional
import httpx
import datetime
import logging

"""Pour arrêter et lancer le docker 
docker-compose down
docker-compose up --build
"""
logging.basicConfig(
    filename="server.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)
# Chargement des variables d'environnement
load_dotenv()

# Initialisation FastAPI
app = FastAPI()
API_KEY = os.getenv("API_KEY")

async def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")
# Connexion Salesforce
sf = Salesforce(
    username=os.getenv("SALESFORCE_USERNAME"),
    password=os.getenv("SALESFORCE_PASSWORD"),
    security_token=os.getenv("SALESFORCE_SECURITY_TOKEN"),
    domain=os.getenv("SALESFORCE_DOMAIN", "login")
)

# -------------------------------
# ✉️ Pydantic models
# -------------------------------
class MessageRequest(BaseModel):
    prompt: str

# -------------------------------
# 🌐 Routes HTTP classiques
# -------------------------------

@app.get("/")
def hello():
    return {"message": "Middleware LLM opérationnel"}

@app.post("/claude", dependencies=[Depends(verify_api_key)])
def ask_claude(request: MessageRequest):
    try:
        ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
        ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
        
        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        data = {
            "model": "claude-3-sonnet-20240229",
            "max_tokens": 512,
            "messages": [
                {"role": "user", "content": request.prompt}
            ]
        }

        response = requests.post(ANTHROPIC_API_URL, headers=headers, json=data)

        logger.info(f"Request to /claude: {request.prompt}")
        logger.info(f"Response from Claude: {response.status_code}")

        return response.json()

    except Exception as e:
        logger.error(f"Error in /claude endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="Error communicating with Claude API")



@app.post("/salesforce_query", dependencies=[Depends(verify_api_key)])
async def salesforce_query(request: Request):
    try:
        body = await request.json()
        query = body.get("query")
        result = sf.query(query)
        logger.info(f"Received request: {request.json()}")
        logger.error(f"Error: {str(e)}")
        
        return result
    except Exception as e:
        return {"error": str(e)}

# -------------------------------
# 🔌 WebSocket pour MCP
# -------------------------------

@app.websocket("/mcp")
async def mcp_endpoint(websocket: WebSocket):
    await websocket.accept()

    # Lecture de l'header x-api-key
    token = websocket.headers.get('x-api-key')

    if token != API_KEY:
        await websocket.close(code=1008)  # Policy Violation
        return

    capabilities = {
        "server_info": {"name": "Custom MCP Server", "version": "1.0"},
        "tools": {
            "salesforce": {"description": "Salesforce access", "operations": ["query"]},
            "sap": {"description": "SAP access", "operations": ["read"]}
        }
    }
    await websocket.send_json({"type": "capabilities", "data": capabilities})

    try:
        while True:
            msg = await websocket.receive_text()
            request = json.loads(msg)
            response = await handle_mcp_request(request["data"])
            await websocket.send_json({"type": "response", "data": response})
    except Exception:
        await websocket.close()


async def handle_mcp_request(data):
    action = data.get("action")
    if action == "salesforce.query":
        return {"result": sf.query(data["parameters"]["query"])}
    elif action == "sap.read":
        return {"result": await sap_read(data["parameters"])}
    return {"error": "Unknown action"}

async def sap_read(params):
    try:
        endpoint = params.get("endpoint")
        method = params.get("method", "GET").upper()
        payload = params.get("payload", None)
        return await call_sap(endpoint, method, payload)
    except Exception as e:
        return {"error": str(e)}

@app.post("/salesforce_create_account", dependencies=[Depends(verify_api_key)])
def create_account():
    try:
        result = sf.Account.create({"Name": "Test Middleware Account"})


        return {"result": result}
    except Exception as e:
        return {"error": str(e)}

sap_session = {
    "cookies": None,
    "expires": None
}

async def login_sap():
    url = os.getenv("SAP_REST_BASE_URL") + "/Login"
    auth_payload = {
        "UserName": os.getenv("SAP_USER"),
        "Password": os.getenv("SAP_PASSWORD"),
        "CompanyDB": os.getenv("SAP_CLIENT")  # pour B1 : SBODemoFR par exemple
    }

    async with httpx.AsyncClient(verify=False) as client:
        response = await client.post(url, json=auth_payload)
        response.raise_for_status()
        sap_session["cookies"] = response.cookies
        sap_session["expires"] = datetime.utcnow().timestamp() + 60 * 20  # Timeout par défaut : 20 min

async def call_sap(endpoint: str, method="GET", payload: Optional[dict] = None):
    base_url = os.getenv("SAP_REST_BASE_URL")
    if not sap_session["cookies"] or datetime.utcnow().timestamp() > sap_session["expires"]:
        await login_sap()

    async with httpx.AsyncClient(cookies=sap_session["cookies"], verify=False) as client:
        url = base_url + endpoint
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
@app.post("/sap_query", dependencies=[Depends(verify_api_key)])
async def sap_query(request: Request):
    try:
        body = await request.json()
        endpoint = body.get("endpoint")
        method = body.get("method", "GET").upper()
        payload = body.get("payload", None)
        result = await call_sap(endpoint, method, payload)
        logger.info(f"Received request: {request.json()}")
        logger.error(f"Error: {str(e)}")

        return result
    except Exception as e:
        return {"error": str(e)}
