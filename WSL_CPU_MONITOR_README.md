# Мониторинг загрузки CPU в WSL

Быстрые скрипты для мониторинга загрузки CPU в WSL дистрибутиве.

## Быстрый старт

### Вариант 1: PowerShell (самый быстрый для Windows)

**Однократное измерение:**
```powershell
.\wsl_cpu_monitor.ps1
```

**С указанием дистрибутива:**
```powershell
.\wsl_cpu_monitor.ps1 -Distro Ubuntu-24.04
```

**Непрерывный мониторинг (watch режим):**
```powershell
.\wsl_cpu_monitor.ps1 -Watch -Interval 1
```

**Режимы измерения:**
- `instant` (по умолчанию) - мгновенное значение, самое быстрое
- `avg` - средняя загрузка за последнюю секунду (точнее)
- `top` - через команду top (медленнее, но показывает детали)

```powershell
.\wsl_cpu_monitor.ps1 -Mode avg
.\wsl_cpu_monitor.ps1 -Mode avg -Watch
```

### Вариант 2: Python скрипт (универсальный)

**Однократное измерение:**
```powershell
python wsl_cpu_monitor.py
```

**С параметрами:**
```powershell
python wsl_cpu_monitor.py --distro Ubuntu-24.04 --mode instant
python wsl_cpu_monitor.py --mode avg
python wsl_cpu_monitor.py --watch --interval 2
```

### Вариант 3: Bash скрипт (внутри WSL)

**Использование из Windows:**
```powershell
wsl -d Ubuntu-24.04 -- bash wsl_cpu_monitor.sh
wsl -d Ubuntu-24.04 -- bash wsl_cpu_monitor.sh avg
wsl -d Ubuntu-24.04 -- bash wsl_cpu_monitor.sh top
```

**Использование внутри WSL:**
```bash
chmod +x wsl_cpu_monitor.sh
./wsl_cpu_monitor.sh
./wsl_cpu_monitor.sh avg
./wsl_cpu_monitor.sh top
```

## Самый быстрый способ

Для максимальной скорости используйте PowerShell скрипт в режиме `instant`:

```powershell
.\wsl_cpu_monitor.ps1 -Distro Ubuntu-24.04 -Mode instant
```

Или создайте алиас в PowerShell профиле:

```powershell
# Добавьте в $PROFILE
function wsl-cpu { .\wsl_cpu_monitor.ps1 -Distro Ubuntu-24.04 -Mode instant }
```

Тогда можно просто вызывать:
```powershell
wsl-cpu
```

## Сравнение методов

| Метод | Скорость | Точность | Рекомендация |
|-------|----------|----------|--------------|
| `instant` | ⚡⚡⚡ Очень быстро | ⚠️ Мгновенное значение | Для быстрой проверки |
| `avg` | ⚡⚡ Быстро | ✅ Точное среднее | Для точных измерений |
| `top` | ⚡ Медленнее | ✅ Детальная информация | Для детального анализа |

## Примеры использования

### Мониторинг во время выполнения задачи

```powershell
# В одном терминале запустите задачу
wsl -d Ubuntu-24.04 -- python your_script.py

# В другом терминале мониторьте CPU
.\wsl_cpu_monitor.ps1 -Watch -Interval 1
```

### Быстрая проверка перед запуском тяжелой задачи

```powershell
.\wsl_cpu_monitor.ps1
# Если CPU < 50%, можно запускать
```

### Интеграция в скрипты

```powershell
$cpu = .\wsl_cpu_monitor.ps1 -Mode avg
if ([int]$cpu -gt 80) {
    Write-Host "CPU перегружен: $cpu%"
}
```

## Примечания

- Скрипты работают с любым WSL дистрибутивом
- Режим `instant` самый быстрый, но показывает мгновенное значение
- Режим `avg` точнее, но требует 1 секунду на измерение
- Для непрерывного мониторинга используйте `-Watch` флаг
