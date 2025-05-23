# main.py (mise à jour)
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from routes.routes_claude import router as claude_router
from routes.routes_salesforce import router as salesforce_router
from routes.routes_sap import router as sap_router
from routes.routes_clients import router as clients_router
from routes.routes_utilisateurs import router as utilisateurs_router
from routes.routes_tickets import router as tickets_router
from routes.routes_llm import router as llm_router
from routes.routes_factures import router as factures_router
from routes.routes_devis import router as devis_router  # Nouvelle route

app = FastAPI()
# Monter le dossier static pour servir les fichiers statiques
app.mount("/static", StaticFiles(directory="static"), name="static")

# Inclusion des routers
app.include_router(claude_router)
app.include_router(salesforce_router)
app.include_router(sap_router)
app.include_router(clients_router)
app.include_router(utilisateurs_router)
app.include_router(tickets_router)
app.include_router(llm_router)
app.include_router(factures_router)
app.include_router(devis_router)  # Nouvelle route

@app.get("/")
def root():
    return {"message": "Middleware LLM opérationnel"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)