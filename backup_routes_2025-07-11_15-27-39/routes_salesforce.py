# routes/routes_salesforce.py
from fastapi import APIRouter, Request, HTTPException, Depends, Header
from services.salesforce import sf
import os
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()
API_KEY = os.getenv("API_KEY")

def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")

@router.post("/salesforce_query", dependencies=[Depends(verify_api_key)])
async def salesforce_query(request: Request):
    try:
        body = await request.json()
        query = body.get("query")
        result = sf.query(query)
        return result
    except Exception as e:
        return {"error": str(e)}

@router.post("/salesforce_create_account", dependencies=[Depends(verify_api_key)])
def create_account():
    try:
        result = sf.Account.create({"Name": "Test Middleware Account"})
        return {"result": result}
    except Exception as e:
        return {"error": str(e)}