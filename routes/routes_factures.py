from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from db.models import Facture
from db.session import get_db

router = APIRouter()

class FactureCreate(BaseModel):
    numero: str
    client_id: int
    montant: int
    statut: str = "en attente"

@router.post("/factures")
def create_facture(facture: FactureCreate, db: Session = Depends(get_db)):
    db_facture = Facture(**facture.dict())
    db.add(db_facture)
    db.commit()
    return {"id": db_facture.id}

@router.get("/factures")
def list_factures(db: Session = Depends(get_db)):
    return db.query(Facture).all()
