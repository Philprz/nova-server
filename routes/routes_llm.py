from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from db.models import InteractionLLM
from db.session import get_db

router = APIRouter()

class LLMLogCreate(BaseModel):
    prompt: str
    reponse: str
    modele: str

@router.post("/interactions_llm")
def log_interaction(interaction: LLMLogCreate, db: Session = Depends(get_db)):
    db_interaction = InteractionLLM(**interaction.dict())
    db.add(db_interaction)
    db.commit()
    return {"id": db_interaction.id}

@router.get("/interactions_llm")
def list_interactions(db: Session = Depends(get_db)):
    return db.query(InteractionLLM).all()
