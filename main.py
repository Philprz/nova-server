# main.py
from fastapi import FastAPI
from routes.routes_claude import router as claude_router
from routes.routes_salesforce import router as salesforce_router
from routes.routes_sap import router as sap_router

app = FastAPI()

# Inclusion des routers
app.include_router(claude_router)
app.include_router(salesforce_router)
app.include_router(sap_router)

@app.get("/")
def root():
    return {"message": "Middleware LLM opérationnel"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
