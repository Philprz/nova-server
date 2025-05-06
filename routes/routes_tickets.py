from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from db.models import Ticket
from db.session import get_db

router = APIRouter()

class TicketCreate(BaseModel):
    titre: str
    description: str | None = None
    statut: str = "nouveau"
    client_id: int

@router.post("/tickets")
def create_ticket(ticket: TicketCreate, db: Session = Depends(get_db)):
    db_ticket = Ticket(**ticket.dict())
    db.add(db_ticket)
    db.commit()
    return {"id": db_ticket.id}

@router.get("/tickets")
def list_tickets(db: Session = Depends(get_db)):
    return db.query(Ticket).all()
