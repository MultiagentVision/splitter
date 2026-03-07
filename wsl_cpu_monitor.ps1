# PowerShell скрипт для быстрого мониторинга CPU в WSL
# Использование: .\wsl_cpu_monitor.ps1 [Ubuntu-24.04] [mode]
# mode: instant (по умолчанию), avg, top, watch

param(
    [string]$Distro = "Ubuntu-24.04",
    [string]$Mode = "instant",
    [int]$Interval = 1,
    [switch]$Watch
)

# Функция для получения загрузки CPU
function Get-WslCpuUsage {
    param([string]$Mode)
    
    $script = @"
#!/bin/bash
if [ "$Mode" == "avg" ]; then
    cpu1=`$(grep '^cpu ' /proc/stat | awk '{print `$2+`$3+`$4+`$5+`$6+`$7+`$8}')
    idle1=`$(grep '^cpu ' /proc/stat | awk '{print `$5}')
    sleep 1
    cpu2=`$(grep '^cpu ' /proc/stat | awk '{print `$2+`$3+`$4+`$5+`$6+`$7+`$8}')
    idle2=`$(grep '^cpu ' /proc/stat | awk '{print `$5}')
    cpu_diff=`$((cpu2 - cpu1))
    idle_diff=`$((idle2 - idle1))
    if [ `$cpu_diff -gt 0 ]; then
        usage=`$((100 * (cpu_diff - idle_diff) / cpu_diff))
        echo "`${usage}%"
    else
        echo "0%"
    fi
elif [ "$Mode" == "top" ]; then
    top -bn1 | grep "Cpu(s)" | awk '{print `$2}' | sed 's/%us,//'
else
    cpu_line=`$(grep '^cpu ' /proc/stat)
    set -- `$cpu_line
    user=`$2
    nice=`$3
    system=`$4
    idle=`$5
    iowait=`$6
    irq=`$7
    softirq=`$8
    total=`$((user + nice + system + idle + iowait + irq + softirq))
    used=`$((user + nice + system + iowait + irq + softirq))
    if [ `$total -gt 0 ]; then
        usage=`$((used * 100 / total))
        echo "`${usage}%"
    else
        echo "0%"
    fi
fi
"@
    
    $result = wsl -d $Distro -- bash -c $script
    return $result.Trim()
}

# Режим watch (непрерывный мониторинг)
if ($Watch) {
    Write-Host "Мониторинг CPU в WSL ($Distro). Нажмите Ctrl+C для выхода." -ForegroundColor Green
    Write-Host ("-" * 50)
    
    while ($true) {
        $timestamp = Get-Date -Format "HH:mm:ss"
        $cpu = Get-WslCpuUsage -Mode $Mode
        Write-Host "[$timestamp] CPU: $cpu" -ForegroundColor Cyan
        Start-Sleep -Seconds $Interval
    }
} else {
    # Однократное измерение
    $cpu = Get-WslCpuUsage -Mode $Mode
    Write-Host "CPU Usage: $cpu" -ForegroundColor Green
}
