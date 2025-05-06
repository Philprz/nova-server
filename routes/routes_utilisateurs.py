from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from db.models import Utilisateur
from db.session import get_db

router = APIRouter()

class UtilisateurCreate(BaseModel):
    nom: str
    role: str
    actif: bool = True

@router.post("/utilisateurs")
def create_utilisateur(utilisateur: UtilisateurCreate, db: Session = Depends(get_db)):
    db_user = Utilisateur(**utilisateur.dict())
    db.add(db_user)
    db.commit()
    return {"id": db_user.id}

@router.get("/utilisateurs")
def list_utilisateurs(db: Session = Depends(get_db)):
    return db.query(Utilisateur).all()
