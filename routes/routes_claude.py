# routes/routes_claude.py
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
import os
import requests
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()
API_KEY = os.getenv("API_KEY")

class MessageRequest(BaseModel):
    prompt: str

def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")

@router.post("/claude", dependencies=[Depends(verify_api_key)])
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
        return response.json()

    except Exception as e:
        raise HTTPException(status_code=500, detail="Error communicating with Claude API")