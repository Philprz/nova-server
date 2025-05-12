# automated_start.ps1

# Débloquer l'exécution des scripts
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force

# Activer l'environnement virtuel
$projectPath = "C:\Users\PPZ\NOVA"
Set-Location -Path $projectPath
if (Test-Path .\venv\Scripts\Activate.ps1) {
    . .\venv\Scripts\Activate.ps1
} else {
    Write-Host "❌ Environnement virtuel non trouvé!" -ForegroundColor Red
    exit 1
}

# Vérifier les dépendances critiques
Write-Host "🔍 Vérification des dépendances critiques..." -ForegroundColor Yellow
$missingDeps = $false

# Vérifier uvicorn
if (-not (Get-Command "uvicorn" -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Uvicorn manquant. Installez avec: pip install uvicorn[standard]" -ForegroundColor Red
    $missingDeps = $true
}

# Vérifier mcp
if (-not (Get-Command "mcp" -ErrorAction SilentlyContinue)) {
    Write-Host "❌ MCP manquant. Installez avec: pip install 'mcp[cli]>=0.4.0'" -ForegroundColor Red
    $missingDeps = $true
}

if ($missingDeps) {
    Write-Host "⚠️ Des dépendances sont manquantes. Installation..." -ForegroundColor Yellow
    pip install -r requirements.txt
}

# Vérifier la connexion à la base de données
try {
    python -c "from db.session import engine; engine.connect()"
    Write-Host "✅ Connexion PostgreSQL OK" -ForegroundColor Green
} catch {
    Write-Host "❌ Erreur de connexion PostgreSQL. Vérifiez les informations de connexion dans .env" -ForegroundColor Red
    Write-Host "   Message d'erreur: $_" -ForegroundColor Red
}

# Vérifier si les serveurs sont déjà en cours d'exécution
$uvicornRunning = Get-Process -Name "uvicorn" -ErrorAction SilentlyContinue
$pythonMcpRunning = Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {$_.CommandLine -like "*server_mcp.py*"}

if ($uvicornRunning) {
    Write-Host "ℹ️ Serveur FastAPI déjà en cours d'exécution (PID: $($uvicornRunning.Id))" -ForegroundColor Cyan
} else {
    # Démarrer le serveur FastAPI
    Write-Host "🚀 Démarrage du serveur FastAPI..." -ForegroundColor Yellow
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force; Set-Location -Path '$projectPath'; .\venv\Scripts\Activate.ps1; uvicorn main:app --reload"
    
    # Attendre que le serveur soit prêt
    $fastApiReady = $false
    $retries = 0
    
    while (-not $fastApiReady -and $retries -lt 10) {
        Start-Sleep -Seconds 2
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:8000/" -UseBasicParsing -ErrorAction SilentlyContinue
            if ($response.StatusCode -eq 200) {
                $fastApiReady = $true
                Write-Host "✅ Serveur FastAPI opérationnel sur http://localhost:8000/" -ForegroundColor Green
            }
        } catch {
            $retries++
            Write-Host "⏳ En attente du démarrage du serveur FastAPI (tentative $retries/10)..." -ForegroundColor Yellow
        }
    }
    
    if (-not $fastApiReady) {
        Write-Host "⚠️ Impossible de confirmer que le serveur FastAPI est opérationnel. Vérifiez manuellement." -ForegroundColor Yellow
    }
}

if ($pythonMcpRunning) {
    Write-Host "ℹ️ Serveur MCP déjà en cours d'exécution (PID: $($pythonMcpRunning.Id))" -ForegroundColor Cyan
} else {
    # Démarrer le serveur MCP
    Write-Host "🚀 Démarrage du serveur MCP..." -ForegroundColor Yellow
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force; Set-Location -Path '$projectPath'; .\venv\Scripts\Activate.ps1; mcp run server_mcp.py"
    Start-Sleep -Seconds 3
    Write-Host "ℹ️ Serveur MCP démarré. Impossible de vérifier automatiquement s'il est opérationnel." -ForegroundColor Cyan
}

# Vérifier si MCP est installé dans Claude Desktop
$claudeConfigPath = "$env:LOCALAPPDATA\Claude Desktop\Claude Desktop\claude_desktop_config.json"
if (Test-Path $claudeConfigPath) {
    $config = Get-Content $claudeConfigPath -Raw | ConvertFrom-Json
    if ($config.mcpServers.nova_middleware) {
        Write-Host "✅ nova_middleware est déjà installé dans Claude Desktop" -ForegroundColor Green
    } else {
        Write-Host "ℹ️ Installation de nova_middleware dans Claude Desktop..." -ForegroundColor Cyan
        mcp install server_mcp.py --name nova_middleware -f .env
        Write-Host "✅ nova_middleware installé. Redémarrez Claude Desktop pour l'utiliser." -ForegroundColor Green
    }
} else {
    Write-Host "⚠️ Configuration Claude Desktop introuvable. Installation manuelle de MCP requise:" -ForegroundColor Yellow
    Write-Host "   mcp install server_mcp.py --name nova_middleware -f .env" -ForegroundColor Yellow
}

# Afficher un récapitulatif
Write-Host "`n🎯 Récapitulatif des services NOVA Middleware:" -ForegroundColor Cyan
Write-Host "--------------------------------------" -ForegroundColor Cyan
Write-Host "FastAPI: http://localhost:8000/" -ForegroundColor Green
Write-Host "MCP: nova_middleware" -ForegroundColor Green
Write-Host "Base de données: PostgreSQL (voir .env)" -ForegroundColor Green
Write-Host "--------------------------------------" -ForegroundColor Cyan
Write-Host "✨ Pour utiliser NOVA Middleware dans Claude Desktop:"
Write-Host "1. Redémarrez Claude Desktop (si nécessaire)"
Write-Host "2. Cliquez sur le bouton + et sélectionnez 'nova_middleware'"
Write-Host "3. Testez avec la commande 'ping()'"