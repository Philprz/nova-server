param(
    [switch]$MCP,
    [switch]$All
)

# Définir l'encodage de sortie à UTF-8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# Fonction d'affichage des messages de log
function Write-LogMessage {
    param (
        [string]$Message,
        [string]$Type = "INFO"
    )
    
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    
    switch ($Type) {
        "SUCCESS" { $color = "Green" }
        "ERROR"   { $color = "Red" }
        "WARNING" { $color = "Yellow" }
        "INFO"    { $color = "Cyan" }
        "DEBUG"   { $color = "Gray" }
        default   { $color = "White" }
    }
    
    Write-Host "[$timestamp] [$Type] $Message" -ForegroundColor $color
}

# Définir le répertoire du projet
$projectDir = $PSScriptRoot

# Activer l'environnement virtuel
$venvPath = Join-Path -Path $projectDir -ChildPath "venv\Scripts\Activate.ps1"
if (Test-Path $venvPath) {
    Write-LogMessage "Activation de l'environnement virtuel..." -Type "INFO"
    . $venvPath
} else {
    Write-LogMessage "Environnement virtuel non trouvé à $venvPath" -Type "ERROR"
    Write-LogMessage "Création d'un nouvel environnement virtuel..." -Type "INFO"
    try {
        python -m venv venv
        . $venvPath
        Write-LogMessage "Installation des dépendances..." -Type "INFO"
        pip install fastapi uvicorn simple-salesforce python-dotenv httpx
        Write-LogMessage "Dépendances installées" -Type "SUCCESS"
    } catch {
        Write-LogMessage "Erreur lors de la création de l'environnement virtuel: $_" -Type "ERROR"
        exit 1
    }
}

# Démarrer FastAPI
try {
    # Vérifier si uvicorn est déjà en cours d'exécution
    $uvicornProcess = Get-Process -Name "python*" -ErrorAction SilentlyContinue | Where-Object {
        $processInfo = $_
        try {
            $cmdLine = (Get-WmiObject -Class Win32_Process -Filter "ProcessId = '$($processInfo.Id)'").CommandLine
            return $cmdLine -match "uvicorn"
        } catch {
            return $false
        }
    }
    
    if ($uvicornProcess) {
        Write-LogMessage "FastAPI (uvicorn) est déjà en cours d'exécution (PID: $($uvicornProcess.Id))" -Type "WARNING"
    } else {
        Write-LogMessage "Démarrage du serveur FastAPI..." -Type "INFO"
        
        $startInfo = New-Object System.Diagnostics.ProcessStartInfo
        $startInfo.FileName = "python"
        $startInfo.Arguments = "-m uvicorn main:app --reload --host 0.0.0.0 --port 8000"
        $startInfo.WorkingDirectory = $projectDir
        $startInfo.UseShellExecute = $true
        
        $process = [System.Diagnostics.Process]::Start($startInfo)
        Write-LogMessage "FastAPI démarré (PID: $($process.Id))" -Type "SUCCESS"
    }
} catch {
    Write-LogMessage "Erreur lors du démarrage de FastAPI: $_" -Type "ERROR"
}

if ($MCP -or $All) {
    # Démarrer les serveurs MCP (Salesforce et principal)
    try {
        # Vérifier si un serveur MCP est déjà en cours d'exécution
        $mcpProcess = Get-Process -Name "python*" -ErrorAction SilentlyContinue | Where-Object {
            $processInfo = $_
            try {
                $cmdLine = (Get-WmiObject -Class Win32_Process -Filter "ProcessId = '$($processInfo.Id)'").CommandLine
                return $cmdLine -match "server_mcp\.py"
            } catch {
                return $false
            }
        }
        
        if ($mcpProcess) {
            Write-LogMessage "Un serveur MCP est déjà en cours d'exécution" -Type "WARNING"
        } else {
            # Démarrer les serveurs MCP dans des fenêtres distinctes
            
            # 1. MCP principal (server_mcp.py)
            Write-LogMessage "Démarrage du serveur MCP principal..." -Type "INFO"
            $mcpMainStartInfo = New-Object System.Diagnostics.ProcessStartInfo
            $mcpMainStartInfo.FileName = "powershell"
            $mcpMainStartInfo.Arguments = "-NoExit -Command `"[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Set-Location '$projectDir'; . .\venv\Scripts\Activate.ps1; python server_mcp.py`""
            $mcpMainStartInfo.UseShellExecute = $true
            [System.Diagnostics.Process]::Start($mcpMainStartInfo)
            Write-LogMessage "Serveur MCP principal démarré" -Type "SUCCESS"
            
            # 2. MCP Salesforce
            Write-LogMessage "Démarrage du serveur MCP Salesforce..." -Type "INFO"
            $mcpSalesforceStartInfo = New-Object System.Diagnostics.ProcessStartInfo
            $mcpSalesforceStartInfo.FileName = "powershell"
            $mcpSalesforceStartInfo.Arguments = "-NoExit -Command `"[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Set-Location '$projectDir'; . .\venv\Scripts\Activate.ps1; python salesforce_mcp.py`""
            $mcpSalesforceStartInfo.UseShellExecute = $true
            [System.Diagnostics.Process]::Start($mcpSalesforceStartInfo)
            Write-LogMessage "Serveur MCP Salesforce démarré" -Type "SUCCESS"
            
            # Attendre un peu pour laisser les serveurs démarrer
            Start-Sleep -Seconds 3
        }
    } catch {
        Write-LogMessage "Erreur lors du démarrage des serveurs MCP: $_" -Type "ERROR"
    }

    # Vérifier si Claude Desktop est installé
    $claudeDesktopPath = Join-Path -Path $env:LOCALAPPDATA -ChildPath "Programs\Claude Desktop\Claude Desktop.exe"

    if (Test-Path $claudeDesktopPath) {
        Write-LogMessage "Claude Desktop est installé" -Type "SUCCESS"
        
        # Vérifier si le fichier de configuration Claude Desktop existe
        $configDir = Join-Path -Path $env:APPDATA -ChildPath "Claude"
        
        if (-not (Test-Path $configDir)) {
            Write-LogMessage "Création du répertoire de configuration Claude..." -Type "INFO"
            New-Item -Path $configDir -ItemType Directory -Force | Out-Null
        }
        
        # Installation du MCP dans Claude Desktop
        Write-LogMessage "Configuration automatique du MCP dans Claude Desktop..." -Type "INFO"
        
        try {
            # S'assurer que le package mcp est installé
            pip install -q mcp[cli] | Out-Null
            
            $output = & python -m mcp install server_mcp.py --name nova_middleware -f .env 2>&1
            Write-LogMessage "Installation MCP: $output" -Type "SUCCESS"
            
            # Ajouter aussi le MCP Salesforce
            $output = & python -m mcp install salesforce_mcp.py --name salesforce_mcp -f .env 2>&1
            Write-LogMessage "Installation MCP Salesforce: $output" -Type "SUCCESS"
        } catch {
            Write-LogMessage "Erreur lors de l'installation MCP: $_" -Type "ERROR"
            Write-LogMessage "Vous devrez installer le MCP manuellement" -Type "WARNING"
        }
        
        # Lancer Claude Desktop
        $claudeProcess = Get-Process -Name "Claude Desktop" -ErrorAction SilentlyContinue
        
        if ($claudeProcess) {
            Write-LogMessage "Claude Desktop est déjà en cours d'exécution" -Type "WARNING"
        } else {
            Write-LogMessage "Démarrage de Claude Desktop..." -Type "INFO"
            Start-Process -FilePath $claudeDesktopPath
            Write-LogMessage "Claude Desktop démarré" -Type "SUCCESS"
        }
    } else {
        Write-LogMessage "Claude Desktop n'est pas installé à l'emplacement $claudeDesktopPath" -Type "WARNING"
        Write-LogMessage "Veuillez installer Claude Desktop et configurer le MCP manuellement" -Type "INFO"
    }
}

# Test de connexion Salesforce
Write-LogMessage "Test de la connexion Salesforce..." -Type "INFO"

try {
    $testScriptPath = Join-Path -Path $projectDir -ChildPath "test_salesforce_connection.py"

    # Créer le script de test s'il n'existe pas ou le remplacer
    $testScript = @"
# test_salesforce_connection.py
import os
import sys
from dotenv import load_dotenv
from simple_salesforce import Salesforce

# Forcer l'encodage de sortie à UTF-8
sys.stdout.reconfigure(encoding='utf-8')

# Charger les variables d'environnement
load_dotenv()

def test_connection():
    try:
        # Récupérer les informations de connexion
        username = os.getenv("SALESFORCE_USERNAME")
        password = os.getenv("SALESFORCE_PASSWORD")
        security_token = os.getenv("SALESFORCE_SECURITY_TOKEN")
        domain = os.getenv("SALESFORCE_DOMAIN", "login")
        
        print(f"Connexion avec {username} sur {domain}...")
        
        # Tenter la connexion
        sf = Salesforce(
            username=username,
            password=password,
            security_token=security_token,
            domain=domain
        )
        
        # Tester une requête simple
        result = sf.query("SELECT Id, Name FROM Account LIMIT 5")
        
        print("Connexion reussie!")
        print(f"Comptes trouves: {len(result['records'])}")
        
        for record in result['records']:
            print(f" - {record['Name']} ({record['Id']})")
        
        return True
    except Exception as e:
        print(f"Erreur: {str(e)}")
        return False

if __name__ == "__main__":
    test_connection()
"@
    # Utiliser UTF-8 sans BOM pour éviter les problèmes d'encodage
    [System.IO.File]::WriteAllLines($testScriptPath, $testScript)
    Write-LogMessage "Script de test créé à $testScriptPath" -Type "DEBUG"

    # Exécuter le test avec un encodage approprié
    $env:PYTHONIOENCODING = "utf-8"
    
    # Utiliser .NET Process directement pour avoir un meilleur contrôle sur l'encodage
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "python"
    $psi.Arguments = $testScriptPath
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8
    
    $process = [System.Diagnostics.Process]::Start($psi)
    $output = $process.StandardOutput.ReadToEnd()
    $error_output = $process.StandardError.ReadToEnd()
    $process.WaitForExit()
    
    # Combiner la sortie
    $combinedOutput = $output
    if ($error_output) {
        $combinedOutput += "`n" + $error_output
    }

    if ($output -match "Connexion reussie") {
        Write-LogMessage "Test de connexion Salesforce réussi" -Type "SUCCESS"
        # Afficher les détails de la connexion
        $outputLines = $output -split "`n"
        foreach ($line in $outputLines) {
            if ($line -match "Comptes trouves|Connexion avec") {
                Write-LogMessage $line -Type "INFO"
            } elseif ($line -match " - ") {
                Write-LogMessage $line -Type "INFO"
            }
        }
    } else {
        Write-LogMessage "Échec du test de connexion Salesforce" -Type "ERROR"
        Write-LogMessage "Détails:" -Type "ERROR"
        Write-Host $combinedOutput
    }
} catch {
    Write-LogMessage "Erreur lors du test de connexion Salesforce: $_" -Type "ERROR"
}

# Afficher un résumé
Write-LogMessage "===== RÉSUMÉ DES SERVICES NOVA =====" -Type "INFO"
Write-LogMessage "FastAPI   : http://localhost:8000/" -Type "INFO"
Write-LogMessage "MCP       : nova_middleware" -Type "INFO"
Write-LogMessage "MCP Sales : salesforce_mcp" -Type "INFO"
Write-LogMessage "=================================" -Type "INFO"
Write-LogMessage "Pour l'utiliser dans Claude Desktop:" -Type "INFO"
Write-LogMessage "1. Ouvrez Claude Desktop" -Type "INFO"
Write-LogMessage "2. Cliquez sur '+' et choisissez 'nova_middleware' ou 'salesforce_mcp'" -Type "INFO"
Write-LogMessage "3. Testez avec la commande 'ping' ou 'salesforce.query(\"SELECT Id, Name FROM Account LIMIT 5\")'" -Type "INFO"