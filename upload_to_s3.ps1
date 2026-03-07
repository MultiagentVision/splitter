# PowerShell скрипт для загрузки файлов в S3
# Использование: .\upload_to_s3.ps1

Write-Host "=== Загрузка файлов в S3 ===" -ForegroundColor Cyan
Write-Host ""

# Проверяем наличие credentials
$accessKey = $env:AWS_ACCESS_KEY_ID
$secretKey = $env:AWS_SECRET_ACCESS_KEY

if (-not $accessKey -or -not $secretKey) {
    Write-Host "AWS credentials не найдены в переменных окружения." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Для загрузки файлов необходимо установить credentials:" -ForegroundColor Yellow
    Write-Host "  `$env:AWS_ACCESS_KEY_ID = 'ваш_access_key'" -ForegroundColor Gray
    Write-Host "  `$env:AWS_SECRET_ACCESS_KEY = 'ваш_secret_key'" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Или запустите этот скрипт с параметрами:" -ForegroundColor Yellow
    Write-Host "  .\upload_to_s3.ps1 -AccessKey 'your_key' -SecretKey 'your_secret'" -ForegroundColor Gray
    Write-Host ""
    
    # Пробуем запросить интерактивно
    $accessKey = Read-Host "Введите AWS Access Key ID (или нажмите Enter для выхода)"
    if (-not $accessKey) {
        Write-Host "Отменено пользователем." -ForegroundColor Red
        exit 1
    }
    
    $secretKey = Read-Host "Введите AWS Secret Access Key"
    if (-not $secretKey) {
        Write-Host "Отменено пользователем." -ForegroundColor Red
        exit 1
    }
    
    # Устанавливаем переменные окружения для текущей сессии
    $env:AWS_ACCESS_KEY_ID = $accessKey
    $env:AWS_SECRET_ACCESS_KEY = $secretKey
}

# Опционально можно задать endpoint
if ($env:S3_ENDPOINT_URL) {
    Write-Host "Используется endpoint: $env:S3_ENDPOINT_URL" -ForegroundColor Green
}

Write-Host ""
Write-Host "Запуск Python скрипта для загрузки..." -ForegroundColor Cyan
Write-Host ""

# Запускаем Python скрипт
python upload_to_s3.py

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Загрузка завершена успешно!" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "Произошла ошибка при загрузке." -ForegroundColor Red
    exit $LASTEXITCODE
}
