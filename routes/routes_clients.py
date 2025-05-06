# routes/routes_clients.py

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from db.models import Client
from db.session import get_db

router = APIRouter()

# Pydantic schema
class ClientCreate(BaseModel):
    name: str
    email: str | None = None
    erp_type: str | None = None

@router.post("/clients", response_model=dict)
def create_client(client: ClientCreate, db: Session = Depends(get_db)):
    db_client = Client(**client.dict())
    db.add(db_client)
    db.commit()
    db.refresh(db_client)
    return {"id": db_client.id}

@router.get("/clients", response_model=list[dict])
def list_clients(db: Session = Depends(get_db)):
    return [{"id": c.id, "name": c.name, "email": c.email} for c in db.query(Client).all()]
