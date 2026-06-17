<#
.SYNOPSIS
    Build a NOVA-SERVER deployment package (zip) ready for production.

.DESCRIPTION
    The package is built from git-tracked files (git ls-files), so everything
    gitignored (.env, .venv/, *.db, *.pyc, node_modules/, logs/,
    alembic/versions/*) is excluded automatically and no secret is shipped.

    Extra patterns listed in .deployignore (repo root) are then removed -
    notably tests/ and mail-to-biz/ (frontend sources; the served build is
    already under frontend/).

    The produced zip contains NO secret: on the target server, copy
    .env.example -> .env and fill the values (see docs/PRODUCTION_DEPLOYMENT.md).

.PARAMETER OutDir
    Output folder for the zip. Default: <repo>\dist

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\package_deploy.ps1
#>
[CmdletBinding()]
param(
    [string]$OutDir
)

$ErrorActionPreference = "Stop"

# Repo root = parent folder of scripts\
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if (-not $OutDir) { $OutDir = Join-Path $RepoRoot "dist" }

# 1. Load .deployignore patterns (skip comments / blank lines)
$ignoreFile = Join-Path $RepoRoot ".deployignore"
$patterns = @()
if (Test-Path $ignoreFile) {
    $patterns = Get-Content $ignoreFile |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ -and -not $_.StartsWith("#") }
}
Write-Host "[package] .deployignore patterns: $($patterns -join ', ')"

# 2. Git-tracked files (relative paths, '/' separator)
$tracked = git ls-files
if ($LASTEXITCODE -ne 0) { throw "git ls-files failed - are you inside a git repo?" }

# 3. Filter against .deployignore
function Test-Excluded([string]$path, [string[]]$pats) {
    foreach ($p in $pats) {
        if ($p.EndsWith("/")) {
            # Directory prefix
            if ($path.StartsWith($p)) { return $true }
        }
        elseif ($p -like "*[*?]*") {
            # Glob pattern (e.g. *.md)
            if ($path -like $p) { return $true }
            if ((Split-Path $path -Leaf) -like $p) { return $true }
        }
        else {
            # Exact path
            if ($path -eq $p) { return $true }
        }
    }
    return $false
}

$included = $tracked | Where-Object { -not (Test-Excluded $_ $patterns) }
$excludedCount = $tracked.Count - $included.Count
Write-Host "[package] tracked: $($tracked.Count) | included: $($included.Count) | excluded: $excludedCount"

# 4. Staging
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$stageName = "nova-deploy-$stamp"
$stageDir = Join-Path $env:TEMP $stageName
if (Test-Path $stageDir) { Remove-Item $stageDir -Recurse -Force }
New-Item -ItemType Directory -Path $stageDir | Out-Null

foreach ($rel in $included) {
    $src = Join-Path $RepoRoot $rel
    $dst = Join-Path $stageDir $rel
    $dstParent = Split-Path $dst -Parent
    if (-not (Test-Path $dstParent)) { New-Item -ItemType Directory -Path $dstParent -Force | Out-Null }
    Copy-Item $src $dst -Force
}

# 5. Zip
if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir | Out-Null }
$zipPath = Join-Path $OutDir "$stageName.zip"
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Compress-Archive -Path (Join-Path $stageDir "*") -DestinationPath $zipPath -Force

Remove-Item $stageDir -Recurse -Force

Write-Host "[package] package created: $zipPath"
Write-Host "[package] reminder: on the target server, copy .env.example -> .env,"
Write-Host "[package]           then apply migrations: alembic upgrade head"
