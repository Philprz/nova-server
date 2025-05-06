# main.py
from fastapi import FastAPI
from routes.routes_claude import router as claude_router
from routes.routes_salesforce import router as salesforce_router
from routes.routes_sap import router as sap_router
from routes.routes_clients import router as clients_router
from routes.routes_utilisateurs import router as utilisateurs_router
from routes.routes_tickets import router as tickets_router
from routes.routes_llm import router as llm_router
from routes.routes_factures import router as factures_router

app = FastAPI()

# Inclusion des routers
app.include_router(claude_router)
app.include_router(salesforce_router)
app.include_router(sap_router)
app.include_router(clients_router)
app.include_router(utilisateurs_router)
app.include_router(tickets_router)
app.include_router(llm_router)
app.include_router(factures_router)

@app.get("/")
def root():
    return {"message": "Middleware LLM opérationnel"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
