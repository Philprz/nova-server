# Middleware UTF-8 pour NOVA
# À ajouter dans main.py après la création de l'app FastAPI

from fastapi import Request
from fastapi.responses import HTMLResponse

@app.middleware("http")
async def force_utf8_html_middleware(request: Request, call_next):
    """Middleware pour forcer UTF-8 sur toutes les réponses HTML"""
    response = await call_next(request)
    
    # Si c'est une réponse HTML, s'assurer que charset=utf-8 est présent
    if isinstance(response, HTMLResponse) or (
        hasattr(response, 'media_type') and 
        response.media_type and 
        'text/html' in response.media_type
    ):
        # Forcer le charset UTF-8
        if 'charset' not in response.media_type:
            response.media_type = "text/html; charset=utf-8"
        
        # S'assurer que l'en-tête Content-Type est correct
        response.headers["Content-Type"] = "text/html; charset=utf-8"
    
    return response
