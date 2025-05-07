# dans routes/routes_claude.py
import os
import requests
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

class PromptRequest(BaseModel):
    prompt: str
    with_tools: bool = False  # Option pour inclure ou non les outils

@router.post("/ask")
async def ask_claude(request: PromptRequest):
    """Point d'entrée pour interroger Claude avec ou sans outils."""
    try:
        ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
        
        # Préparer les outils si nécessaires
        tools = None
        if request.with_tools:
            tools = [
                {
                    "name": "salesforce_query",
                    "description": "Exécute une requête SOQL sur Salesforce",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"}
                        },
                        "required": ["query"]
                    }
                },
                {
                    "name": "sap_read",
                    "description": "Lit des données SAP via API REST",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "endpoint": {"type": "string"},
                            "method": {"type": "string"},
                            "payload": {"type": "object"}
                        },
                        "required": ["endpoint"]
                    }
                }
            ]
        
        # Construire la requête API
        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
        body = {
            "model": "claude-3-sonnet-20240229",
            "max_tokens": 4096,
            "messages": [
                {"role": "user", "content": request.prompt}
            ]
        }
        
        if tools:
            body["tools"] = tools
        
        # Appeler l'API Claude
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=body
        )
        
        return response.json()
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur API Claude: {str(e)}")