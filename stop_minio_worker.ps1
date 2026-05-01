# Останавливает процессы Python, в командной строке которых есть minio_worker.py
$procs = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'minio_worker' }
if (-not $procs) {
    Write-Host "Процессы minio_worker не найдены."
    exit 0
}
$procs | ForEach-Object {
    Write-Host "Останавливаю PID $($_.ProcessId)"
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}
Write-Host "Готово."
