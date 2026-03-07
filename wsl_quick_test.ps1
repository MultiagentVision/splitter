# Quick WSL diagnostic
Write-Host "Checking WSL status..." -ForegroundColor Yellow
wsl --status

Write-Host "`nDistributions list:" -ForegroundColor Yellow
wsl -l -v

Write-Host "`nTrying simple command with timeout..." -ForegroundColor Yellow
try {
    $job = Start-Job -ScriptBlock {
        wsl -d Ubuntu-24.04 -- whoami
    }
    
    $result = Wait-Job -Job $job -Timeout 5
    if ($result) {
        $output = Receive-Job -Job $job
        Write-Host "Success! Output: $output" -ForegroundColor Green
    } else {
        Write-Host "Timeout! WSL may require interactive login." -ForegroundColor Red
        Stop-Job -Job $job
        Remove-Job -Job $job
    }
} catch {
    Write-Host "Error: $_" -ForegroundColor Red
}

Write-Host "`nTo open Ubuntu terminal, run:" -ForegroundColor Cyan
Write-Host "  wsl -d Ubuntu-24.04" -ForegroundColor White
Write-Host "`nOr find Ubuntu 24.04 in Windows Start menu" -ForegroundColor Cyan
