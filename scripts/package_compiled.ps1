<#
.SYNOPSIS
    Construit le package de déploiement COMPILÉ (Cython .pyd) de NOVA-SERVER.

.DESCRIPTION
    Contrairement à package_deploy.ps1 (livraison SOURCE depuis `git ls-files`),
    ce packager part de la SORTIE DE BUILD Cython (.pyd, gitignorés donc invisibles
    à git ls-files). Il assemble une livraison contenant uniquement :
      - les modules métier compilés (.pyd),
      - le non-code requis (templates/, static/, frontend/, alembic/),
      - le lanceur (run.py — Lot 3), requirements.txt, le coffre/secret, les .bat runtime.

    Frontière de responsabilité : ce script fait UNIQUEMENT l'ASSEMBLAGE. La
    compilation Cython (cythonize + MSVC + verrouillage CPython 3.10.10 x64) est le
    Lot 5 et reste hors de ce script ; on consomme ici son résultat via -BuildDir.

    `.deployignore` reste la source de vérité UNIQUE des exclusions (réutilisée ici).
    package_deploy.ps1 est conservé tel quel (livraison source/debug).

    Garde-fou : aucune source métier .py / .c / .pyx / __pycache__ / *.pyc ne peut
    fuiter dans le package (échec dur si détecté), hormis l'allowlist .py explicite
    (run.py, register/renew_webhook.py et alembic/**).

    EXPOSITION CONNUE ASSUMÉE (validée Philippe, Lot 5 "à trancher") :
    register_webhook.py / renew_webhook.py sont livrés en SOURCE .py. Ils contiennent
    de la logique d'appel Graph/SAP et lisent des secrets ; un .pyd ne se lançant pas
    via `python renew_webhook.py`, le planificateur en a besoin en .py. C'est une
    exposition mineure assumée, pas un oubli. Pour zéro source : les compiler + un
    lanceur mince chacun.

.PARAMETER BuildDir
    Dossier contenant l'arbre compilé (.pyd) produit par le build Cython (Lot 5).
    Défaut : <repo>\build\compiled

.PARAMETER OutDir
    Dossier de sortie du zip. Défaut : <repo>\dist

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\package_compiled.ps1 -BuildDir build\compiled
#>
[CmdletBinding()]
param(
    [string]$BuildDir,
    [string]$OutDir
)

$ErrorActionPreference = "Stop"

# Repo root = dossier parent de scripts\
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if (-not $BuildDir) { $BuildDir = Join-Path $RepoRoot "build\compiled" }
if (-not $OutDir)   { $OutDir   = Join-Path $RepoRoot "dist" }

if (-not (Test-Path $BuildDir)) {
    throw "BuildDir introuvable : $BuildDir. Lance d'abord le build Cython (Lot 5)."
}

# Normaliser BuildDir en chemin ABSOLU. Le calcul du chemin relatif (3a) fait
# $_.FullName.Substring($BuildDir.Length), or FullName est TOUJOURS absolu. Si
# -BuildDir est passe en relatif (ex. 'build/compiled', 14 car.), le Substring
# tronque 14 car. du chemin absolu et niche tous les .pyd sous un faux dossier
# (ex. 'OVA-SERVER/build/compiled/...'). On resout donc en absolu d'abord.
$BuildDir = (Resolve-Path -LiteralPath $BuildDir).Path

# ------------------------------------------------------------------
# 1. Allowlist : ce qui PEUT entrer dans la livraison compilée
# ------------------------------------------------------------------

# Dossiers non-code livrés intégralement (filtrés ensuite par .deployignore)
$IncludeDirs = @('templates', 'static', 'frontend', 'alembic')

# Fichiers racine explicitement livrés.
# Coffre chiffré (Lot 1) prioritaire ; tant qu'il n'existe pas, on livre .env.example
# comme gabarit (le .env réel se crée sur le serveur). JAMAIS le .env réel.
$IncludeFiles = @('requirements.txt')
if (Test-Path (Join-Path $RepoRoot 'secrets.enc')) {
    $IncludeFiles += 'secrets.enc'
} else {
    Write-Warning "secrets.enc absent (Lot 1 non implémenté) -> livraison de .env.example comme gabarit."
    $IncludeFiles += '.env.example'
}

# Lanceur mince (Lot 3). Tant que run.py n'existe pas, avertir.
if (Test-Path (Join-Path $RepoRoot 'run.py')) {
    $IncludeFiles += 'run.py'
} else {
    Write-Warning "run.py absent (Lot 3 non implémenté) -> un .pyd ne se lance pas via 'python main.pyd'."
}

# Config Alembic (Lot 4). Requis par run.py (_run_migrations_if_enabled lit
# <pkgroot>/alembic.ini). Le sqlalchemy.url qui y figure est un placeholder
# localhost INERTE au runtime : alembic/env.py l'ecrase par DATABASE_URL (.env).
$IncludeFiles += @('alembic.ini')

# .bat d'exploitation runtime
$IncludeFiles += @('start-nova.bat', 'restart_server.bat', 'nova-setup-tache.bat')

# Scripts autonomes planifiés livrés en .py (exposition connue assumée, cf. .DESCRIPTION)
$IncludeFiles += @('register_webhook.py', 'renew_webhook.py')

# Shim de compat Cython<->Pydantic (Lot 5). OBLIGATOIRE en runtime compilé :
# main.pyd exécute `sys.path.insert(0, <pkgroot>/scripts)` puis `import
# cython_pydantic_compat` (cf. main.py / run.py, tête de module). Le shim reste
# en .py PUR (jamais compilé) — aucun secret, aucune logique métier : seulement
# le monkeypatch des ignored_types Pydantic. On le livre donc sous scripts/ pour
# que le chemin matche exactement le sys.path.insert de main.pyd.
$IncludeFiles += @('scripts/cython_pydantic_compat.py')

# Sources .py TOLÉRÉES dans la sortie (le garde-fou les laisse passer) :
#   - run.py (lanceur), register/renew_webhook (scheduler), alembic/** (migrations Lot 4),
#   - scripts/cython_pydantic_compat.py (shim de compat, requis par main.pyd).
# NOTE (Lot 2/2b) : _vault_key.py n'est VOLONTAIREMENT PAS dans cette allowlist.
# La cle maitre embarquee ne doit ship QUE compilee (_vault_key.pyd, copié en 3a
# depuis BuildDir). Si _vault_key.py fuitait dans le stage, le garde-fou (§4) le
# détecterait comme source non autorisée et ferait échouer le packaging.
$AllowedSourcePy = @('run.py', 'register_webhook.py', 'renew_webhook.py', 'cython_pydantic_compat.py')

# ------------------------------------------------------------------
# 2. Motifs .deployignore (source de vérité des exclusions)
# ------------------------------------------------------------------
$ignoreFile = Join-Path $RepoRoot ".deployignore"
$patterns = @()
if (Test-Path $ignoreFile) {
    $patterns = Get-Content $ignoreFile |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ -and -not $_.StartsWith("#") }
}

function Test-Excluded([string]$path, [string[]]$pats) {
    foreach ($p in $pats) {
        if ($p.EndsWith("/")) {
            # Préfixe de dossier
            if ($path.StartsWith($p)) { return $true }
        }
        elseif ($p -like "*[*?]*") {
            # Motif glob (ex. *.md)
            if ($path -like $p) { return $true }
            if ((Split-Path $path -Leaf) -like $p) { return $true }
        }
        else {
            # Chemin exact
            if ($path -eq $p) { return $true }
        }
    }
    return $false
}

# Toujours bannis, quel que soit .deployignore (hygiène Lot 6)
function Test-ForbiddenArtifact([string]$rel) {
    if ($rel -match '(^|/)__pycache__(/|$)') { return $true }
    if ($rel -like '*.pyc') { return $true }
    if ($rel -like '*.pyo') { return $true }
    if ($rel -like '*.c')   { return $true }
    if ($rel -like '*.pyx') { return $true }
    return $false
}

# ------------------------------------------------------------------
# 3. Staging
# ------------------------------------------------------------------
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$stageName = "nova-compiled-$stamp"
$stageDir  = Join-Path $env:TEMP $stageName
if (Test-Path $stageDir) { Remove-Item $stageDir -Recurse -Force }
New-Item -ItemType Directory -Path $stageDir | Out-Null

function Copy-Into([string]$absSrc, [string]$rel) {
    $relUnix = $rel -replace '\\', '/'
    if (Test-ForbiddenArtifact $relUnix) { return $false }
    if (Test-Excluded $relUnix $patterns) { return $false }
    $dst = Join-Path $stageDir $rel
    $dstParent = Split-Path $dst -Parent
    if (-not (Test-Path $dstParent)) { New-Item -ItemType Directory -Path $dstParent -Force | Out-Null }
    Copy-Item $absSrc $dst -Force
    return $true
}

$copied = 0

# 3a. Arbre compilé (.pyd) depuis BuildDir
Get-ChildItem -Path $BuildDir -Recurse -File | ForEach-Object {
    $rel = $_.FullName.Substring($BuildDir.Length).TrimStart('\', '/')
    if (Copy-Into $_.FullName $rel) { $copied++ }
}

# 3b. Dossiers non-code (depuis le repo)
foreach ($d in $IncludeDirs) {
    $absD = Join-Path $RepoRoot $d
    if (-not (Test-Path $absD)) { Write-Warning "Dossier non-code absent : $d"; continue }
    Get-ChildItem -Path $absD -Recurse -File | ForEach-Object {
        $rel = $_.FullName.Substring($RepoRoot.Length).TrimStart('\', '/')
        if (Copy-Into $_.FullName $rel) { $copied++ }
    }
}

# 3c. Fichiers racine explicites (l'allowlist prime : pas de filtre .deployignore)
foreach ($f in $IncludeFiles) {
    $absF = Join-Path $RepoRoot $f
    if (-not (Test-Path $absF)) { Write-Warning "Fichier attendu absent : $f"; continue }
    if (Test-ForbiddenArtifact ($f -replace '\\', '/')) { continue }
    $dst = Join-Path $stageDir $f
    $dstParent = Split-Path $dst -Parent
    if (-not (Test-Path $dstParent)) { New-Item -ItemType Directory -Path $dstParent -Force | Out-Null }
    Copy-Item $absF $dst -Force
    $copied++
}

# ------------------------------------------------------------------
# 4. Garde-fou dur : aucune source métier ne doit avoir fui
# ------------------------------------------------------------------
$leaks = @()
Get-ChildItem -Path $stageDir -Recurse -File | ForEach-Object {
    $rel = $_.FullName.Substring($stageDir.Length).TrimStart('\', '/') -replace '\\', '/'
    if (Test-ForbiddenArtifact $rel) { $leaks += $rel; return }
    if ($rel -like '*.py') {
        $leafAllowed = $AllowedSourcePy -contains (Split-Path $rel -Leaf)
        $isAlembic   = $rel -like 'alembic/*'      # migrations + env.py + __init__ : .py légitimes (Lot 4)
        if (-not ($leafAllowed -or $isAlembic)) { $leaks += $rel }
    }
}
if ($leaks.Count -gt 0) {
    Remove-Item $stageDir -Recurse -Force
    throw "FUITE DE SOURCE détectée dans la livraison compilée :`n  $($leaks -join "`n  ")"
}

# ------------------------------------------------------------------
# 5. Zip
# ------------------------------------------------------------------
if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir | Out-Null }
$zipPath = Join-Path $OutDir "$stageName.zip"
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Compress-Archive -Path (Join-Path $stageDir "*") -DestinationPath $zipPath -Force
Remove-Item $stageDir -Recurse -Force

Write-Host "[package-compiled] fichiers inclus : $copied"
Write-Host "[package-compiled] package créé    : $zipPath"
Write-Host "[package-compiled] rappel : sur le serveur cible, fournir secrets.enc (ou .env),"
Write-Host "[package-compiled]          puis le lanceur enchaîne alembic upgrade head -> uvicorn."
