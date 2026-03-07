# Open Ubuntu terminal quickly
Write-Host "Opening Ubuntu 24.04 terminal..." -ForegroundColor Green
Write-Host "If this is first launch, you may need to create a user account." -ForegroundColor Yellow
Write-Host ""

# Try to start WSL in new window
Start-Process wsl.exe -ArgumentList "-d", "Ubuntu-24.04"

Write-Host "Ubuntu terminal should open in a new window." -ForegroundColor Cyan
Write-Host "If it doesn't open, try:" -ForegroundColor Yellow
Write-Host "  1. Find 'Ubuntu 24.04' in Windows Start menu" -ForegroundColor White
Write-Host "  2. Or run: wsl -d Ubuntu-24.04" -ForegroundColor White
