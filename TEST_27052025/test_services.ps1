# Test des services NOVA maintenant que FastAPI fonctionne

Write-Host "=== TEST DES SERVICES NOVA ===" -ForegroundColor Cyan

# Test 1: Page d'accueil
Write-Host "`n1. Test page d'accueil..." -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "http://localhost:8000/" -Method GET
    Write-Host "   ✅ Accueil OK:" -ForegroundColor Green
    Write-Host "      Message: $($response.message)" -ForegroundColor Gray
    Write-Host "      Version: $($response.version)" -ForegroundColor Gray
    Write-Host "      Modules disponibles:" -ForegroundColor Gray
    $response.modules.PSObject.Properties | ForEach-Object {
        $status = if ($_.Value) { "✅" } else { "❌" }
        Write-Host "        - $($_.Name): $status" -ForegroundColor Gray
    }
} catch {
    Write-Host "   ❌ Erreur: $($_.Exception.Message)" -ForegroundColor Red
}

# Test 2: Health check
Write-Host "`n2. Test health check..." -ForegroundColor Yellow
try {
    $health = Invoke-RestMethod -Uri "http://localhost:8000/health" -Method GET
    Write-Host "   ✅ Health OK:" -ForegroundColor Green
    Write-Host "      Status: $($health.status)" -ForegroundColor Gray
    Write-Host "      Services:" -ForegroundColor Gray
    $health.services.PSObject.Properties | ForEach-Object {
        $status = if ($_.Value -eq "available") { "✅" } else { "❌" }
        Write-Host "        - $($_.Name): $status $($_.Value)" -ForegroundColor Gray
    }
} catch {
    Write-Host "   ❌ Erreur: $($_.Exception.Message)" -ForegroundColor Red
}

# Test 3: Documentation Swagger
Write-Host "`n3. Test documentation Swagger..." -ForegroundColor Yellow
try {
    $docs = Invoke-WebRequest -Uri "http://localhost:8000/docs" -Method GET
    if ($docs.StatusCode -eq 200) {
        Write-Host "   ✅ Documentation accessible" -ForegroundColor Green
    }
} catch {
    Write-Host "   ❌ Documentation inaccessible: $($_.Exception.Message)" -ForegroundColor Red
}

# Test 4: Démo devis (si existe)
Write-Host "`n4. Test démo devis..." -ForegroundColor Yellow
try {
    $demo = Invoke-WebRequest -Uri "http://localhost:8000/static/demo_devis.html" -Method GET
    if ($demo.StatusCode -eq 200) {
        Write-Host "   ✅ Démo devis accessible" -ForegroundColor Green
    }
} catch {
    Write-Host "   ❌ Démo devis inaccessible: $($_.Exception.Message)" -ForegroundColor Red
}

# Test 5: Endpoint Claude (simple)
Write-Host "`n5. Test endpoint Claude..." -ForegroundColor Yellow
try {
    $headers = @{"Content-Type" = "application/json"}
    $body = @{
        prompt = "Bonjour, ceci est un test"
        with_tools = $false
    } | ConvertTo-Json
    
    $claude = Invoke-RestMethod -Uri "http://localhost:8000/ask" -Method POST -Body $body -Headers $headers
    Write-Host "   ✅ Claude endpoint répond" -ForegroundColor Green
    if ($claude.content) {
        Write-Host "      Réponse reçue (longueur: $($claude.content[0].text.Length) caractères)" -ForegroundColor Gray
    }
} catch {
    Write-Host "   ❌ Claude endpoint erreur: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`n=== RÉSUMÉ ===" -ForegroundColor Cyan
Write-Host "🌐 URLs d'accès:" -ForegroundColor White
Write-Host "   - Accueil:        http://localhost:8000/" -ForegroundColor Gray
Write-Host "   - Health:         http://localhost:8000/health" -ForegroundColor Gray
Write-Host "   - Documentation:  http://localhost:8000/docs" -ForegroundColor Gray
Write-Host "   - Démo devis:     http://localhost:8000/static/demo_devis.html" -ForegroundColor Gray

Write-Host "`n🧪 Pour tester le workflow complet:" -ForegroundColor White
Write-Host "   python tests\test_devis_generique.py" -ForegroundColor Gray

Write-Host "`n=== TEST TERMINÉ ===" -ForegroundColor Cyan