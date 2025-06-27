# db/models.py

from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

Base = declarative_base()

# Table Client
class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String)
    erp_type = Column(String)  # ex: 'SAP', 'Salesforce'

    tickets = relationship("Ticket", back_populates="client")

# Table Utilisateur
class Utilisateur(Base):
    __tablename__ = "utilisateurs"

    id = Column(Integer, primary_key=True)
    nom = Column(String, nullable=False)
    role = Column(String, nullable=False)
    actif = Column(Boolean, default=True)

# Table Ticket
class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True)
    titre = Column(String, nullable=False)
    description = Column(Text)
    statut = Column(String, default="nouveau")  # ex: 'nouveau', 'en cours', 'clos'
    date_creation = Column(DateTime, server_default=func.now())
    client_id = Column(Integer, ForeignKey("clients.id"))

    client = relationship("Client", back_populates="tickets")

# Table Facture
class Facture(Base):
    __tablename__ = "factures"

    id = Column(Integer, primary_key=True)
    numero = Column(String, nullable=False, unique=True)
    client_id = Column(Integer, ForeignKey("clients.id"))
    montant = Column(Integer)
    date_emission = Column(DateTime, server_default=func.now())
    statut = Column(String, default="en attente")  # ex: 'payée', 'en attente'

# Table Logs GPT
class InteractionLLM(Base):
    __tablename__ = "interactions_llm"

    id = Column(Integer, primary_key=True)
    prompt = Column(Text, nullable=False)
    reponse = Column(Text)
    modele = Column(String)  # ex: 'Claude', 'GPT-4'
    date_appel = Column(DateTime, server_default=func.now())
