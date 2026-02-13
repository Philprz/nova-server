#!/bin/bash
# ============================================
#  NOVA-SERVER - Script de demarrage complet
#  Lance Backend (FastAPI) + Frontend (React)
# ============================================

echo ""
echo "========================================"
echo "  NOVA-SERVER v2.3.0"
echo "  Demarrage Backend + Frontend"
echo "========================================"
echo ""

# Verifier Python
if ! command -v python3 &> /dev/null; then
    echo "[ERREUR] Python3 non trouve. Veuillez installer Python 3.9+"
    exit 1
fi

echo "[OK] Python detecte: $(python3 --version)"
echo ""

# Fonction pour arreter les processus au CTRL+C
cleanup() {
    echo ""
    echo "Arret des services NOVA..."
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    exit 0
}

trap cleanup INT TERM

# Demarrer Backend FastAPI
echo "========================================"
echo "  1/2 - Demarrage Backend FastAPI"
echo "========================================"
echo ""
echo "Demarrage serveur FastAPI sur http://localhost:8001..."
python3 main.py &
BACKEND_PID=$!

# Attendre que le backend demarre
sleep 5

# Verifier si Node.js est installe
if ! command -v node &> /dev/null; then
    echo ""
    echo "[INFO] Node.js non trouve - Frontend deja compile"
    echo "Le frontend sera servi par FastAPI sur http://localhost:8001/mail-to-biz"
    echo ""

    echo ""
    echo "========================================"
    echo "  NOVA DEMARRE (Backend uniquement)"
    echo "========================================"
    echo ""
    echo "Backend FastAPI : http://localhost:8001"
    echo "Mail-to-Biz : http://localhost:8001/mail-to-biz"
    echo "NOVA Assistant : http://localhost:8001/interface/itspirit"
    echo "API Docs : http://localhost:8001/docs"
    echo ""
    echo "Appuyez sur CTRL+C pour arreter..."

    wait $BACKEND_PID
    exit 0
fi

# Verifier si le frontend source existe
if [ ! -d "mail-to-biz/src" ]; then
    echo ""
    echo "[INFO] Frontend source non trouve - Utilisation du build"
    echo "Le frontend sera servi par FastAPI sur http://localhost:8001/mail-to-biz"
    echo ""

    echo ""
    echo "========================================"
    echo "  NOVA DEMARRE (Backend uniquement)"
    echo "========================================"
    echo ""
    echo "Backend FastAPI : http://localhost:8001"
    echo "Mail-to-Biz : http://localhost:8001/mail-to-biz"
    echo "NOVA Assistant : http://localhost:8001/interface/itspirit"
    echo "API Docs : http://localhost:8001/docs"
    echo ""
    echo "Appuyez sur CTRL+C pour arreter..."

    wait $BACKEND_PID
    exit 0
fi

# Demarrer Frontend React Dev Server
echo ""
echo "========================================"
echo "  2/2 - Demarrage Frontend React Dev"
echo "========================================"
echo ""
echo "Demarrage React Dev Server..."
cd mail-to-biz
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "========================================"
echo "  NOVA DEMARRE AVEC SUCCES!"
echo "========================================"
echo ""
echo "Backend FastAPI : http://localhost:8001"
echo "Frontend React Dev : http://localhost:5173"
echo "Mail-to-Biz : http://localhost:8001/mail-to-biz"
echo "NOVA Assistant : http://localhost:8001/interface/itspirit"
echo "API Docs : http://localhost:8001/docs"
echo ""
echo "Appuyez sur CTRL+C pour arreter tous les services..."

# Attendre les processus
wait $BACKEND_PID $FRONTEND_PID
