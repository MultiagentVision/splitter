#!/bin/bash
# Быстрый мониторинг загрузки CPU в WSL

# Вариант 1: Мгновенное значение CPU (самый быстрый)
get_cpu_usage() {
    # Читаем статистику CPU из /proc/stat
    cpu_line=$(grep '^cpu ' /proc/stat)
    
    # Парсим значения
    set -- $cpu_line
    user=$2
    nice=$3
    system=$4
    idle=$5
    iowait=$6
    irq=$7
    softirq=$8
    
    # Вычисляем общее время
    total=$((user + nice + system + idle + iowait + irq + softirq))
    
    # Вычисляем использование (не idle)
    used=$((user + nice + system + iowait + irq + softirq))
    
    # Процент использования
    if [ $total -gt 0 ]; then
        usage=$((used * 100 / total))
        echo "CPU Usage: ${usage}%"
    else
        echo "CPU Usage: 0%"
    fi
}

# Вариант 2: Средняя загрузка за последнюю секунду (более точный)
get_cpu_usage_avg() {
    # Первое измерение
    cpu1=$(grep '^cpu ' /proc/stat | awk '{print $2+$3+$4+$5+$6+$7+$8}')
    idle1=$(grep '^cpu ' /proc/stat | awk '{print $5}')
    sleep 1
    # Второе измерение
    cpu2=$(grep '^cpu ' /proc/stat | awk '{print $2+$3+$4+$5+$6+$7+$8}')
    idle2=$(grep '^cpu ' /proc/stat | awk '{print $5}')
    
    # Вычисляем разницу
    cpu_diff=$((cpu2 - cpu1))
    idle_diff=$((idle2 - idle1))
    
    if [ $cpu_diff -gt 0 ]; then
        usage=$((100 * (cpu_diff - idle_diff) / cpu_diff))
        echo "CPU Usage (avg 1s): ${usage}%"
    else
        echo "CPU Usage: 0%"
    fi
}

# Вариант 3: Использование top (самый простой, но медленнее)
get_cpu_top() {
    top -bn1 | grep "Cpu(s)" | awk '{print $2}' | sed 's/%us,//'
}

# Основная функция
if [ "$1" == "avg" ]; then
    get_cpu_usage_avg
elif [ "$1" == "top" ]; then
    get_cpu_top
else
    get_cpu_usage
fi
