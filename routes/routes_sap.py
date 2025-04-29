# routes/routes_sap.py
from fastapi import APIRouter, Request, Depends, HTTPException, Header
from services.sap import call_sap, login_sap
import os
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()
API_KEY = os.getenv("API_KEY")

def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")

@router.post("/sap_query", dependencies=[Depends(verify_api_key)])
async def sap_query(request: Request):
    try:
        body = await request.json()
        endpoint = body.get("endpoint")
        method = body.get("method", "GET").upper()
        payload = body.get("payload", None)
        result = await call_sap(endpoint, method, payload)
        return result
    except Exception as e:
        return {"error": str(e)}

@router.get("/sap_login_test", dependencies=[Depends(verify_api_key)])
async def sap_login_test():
    try:
        await login_sap()
        return {"status": "success", "message": "Connexion SAP OK ✅"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# services/salesforce.py
import os
from dotenv import load_dotenv
from simple_salesforce import Salesforce

load_dotenv()

sf = Salesforce(
    username=os.getenv("SALESFORCE_USERNAME"),
    password=os.getenv("SALESFORCE_PASSWORD"),
    security_token=os.getenv("SALESFORCE_SECURITY_TOKEN"),
    domain=os.getenv("SALESFORCE_DOMAIN", "login")
)
