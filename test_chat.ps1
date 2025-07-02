# test_chat.ps1
Write-Host "Test API Chat NOVA" -ForegroundColor Green

# Test avec Invoke-RestMethod
$body = @{
    message = "Bonjour NOVA"
} | ConvertTo-Json

try {
    $response = Invoke-RestMethod -Uri "http://localhost:8000/api/assistant/chat" `
        -Method POST `
        -ContentType "application/json" `
        -Body $body
    
    Write-Host "✅ Chat API fonctionne!" -ForegroundColor Green
    $response | ConvertTo-Json -Depth 10
} catch {
    Write-Host "❌ Erreur API Chat:" -ForegroundColor Red
    Write-Host $_.Exception.Message
}