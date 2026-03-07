#!/usr/bin/env python3
"""
Быстрый мониторинг загрузки CPU в WSL
Использование:
    python wsl_cpu_monitor.py [--distro Ubuntu-24.04] [--mode instant|avg|top] [--watch] [--interval 1]
"""

import subprocess
import sys
import time
import argparse


def get_cpu_usage_instant(distro: str) -> float:
    """Мгновенное значение CPU (самый быстрый метод)"""
    script = """
    cpu_line=$(grep '^cpu ' /proc/stat)
    set -- $cpu_line
    user=$2
    nice=$3
    system=$4
    idle=$5
    iowait=$6
    irq=$7
    softirq=$8
    total=$((user + nice + system + idle + iowait + irq + softirq))
    used=$((user + nice + system + iowait + irq + softirq))
    if [ $total -gt 0 ]; then
        echo $((used * 100 / total))
    else
        echo 0
    fi
    """
    try:
        result = subprocess.run(
            ["wsl", "-d", distro, "--", "bash", "-c", script],
            capture_output=True,
            text=True,
            timeout=2
        )
        return float(result.stdout.strip())
    except Exception as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        return 0.0


def get_cpu_usage_avg(distro: str) -> float:
    """Средняя загрузка за последнюю секунду (более точный)"""
    script = """
    cpu1=$(grep '^cpu ' /proc/stat | awk '{print $2+$3+$4+$5+$6+$7+$8}')
    idle1=$(grep '^cpu ' /proc/stat | awk '{print $5}')
    sleep 1
    cpu2=$(grep '^cpu ' /proc/stat | awk '{print $2+$3+$4+$5+$6+$7+$8}')
    idle2=$(grep '^cpu ' /proc/stat | awk '{print $5}')
    cpu_diff=$((cpu2 - cpu1))
    idle_diff=$((idle2 - idle1))
    if [ $cpu_diff -gt 0 ]; then
        echo $((100 * (cpu_diff - idle_diff) / cpu_diff))
    else
        echo 0
    fi
    """
    try:
        result = subprocess.run(
            ["wsl", "-d", distro, "--", "bash", "-c", script],
            capture_output=True,
            text=True,
            timeout=3
        )
        return float(result.stdout.strip())
    except Exception as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        return 0.0


def get_cpu_usage_top(distro: str) -> float:
    """Использование top (простой, но медленнее)"""
    script = "top -bn1 | grep 'Cpu(s)' | awk '{print $2}' | sed 's/%us,//'"
    try:
        result = subprocess.run(
            ["wsl", "-d", distro, "--", "bash", "-c", script],
            capture_output=True,
            text=True,
            timeout=3
        )
        return float(result.stdout.strip())
    except Exception as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        return 0.0


def main():
    parser = argparse.ArgumentParser(
        description="Мониторинг загрузки CPU в WSL",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  python wsl_cpu_monitor.py
  python wsl_cpu_monitor.py --mode avg
  python wsl_cpu_monitor.py --watch --interval 2
  python wsl_cpu_monitor.py --distro Ubuntu-24.04 --mode instant --watch
        """
    )
    parser.add_argument(
        "--distro",
        default="Ubuntu-24.04",
        help="Название WSL дистрибутива (по умолчанию: Ubuntu-24.04)"
    )
    parser.add_argument(
        "--mode",
        choices=["instant", "avg", "top"],
        default="instant",
        help="Режим измерения: instant (быстро), avg (точнее), top (через top)"
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Непрерывный мониторинг"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=1,
        help="Интервал обновления в секундах (для --watch)"
    )

    args = parser.parse_args()

    # Выбор функции в зависимости от режима
    if args.mode == "avg":
        get_cpu = lambda: get_cpu_usage_avg(args.distro)
    elif args.mode == "top":
        get_cpu = lambda: get_cpu_usage_top(args.distro)
    else:
        get_cpu = lambda: get_cpu_usage_instant(args.distro)

    if args.watch:
        print(f"Мониторинг CPU в WSL ({args.distro}). Нажмите Ctrl+C для выхода.")
        print("-" * 50)
        try:
            while True:
                cpu = get_cpu()
                timestamp = time.strftime("%H:%M:%S")
                print(f"[{timestamp}] CPU: {cpu:.1f}%")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nМониторинг остановлен.")
    else:
        cpu = get_cpu()
        print(f"CPU Usage: {cpu:.1f}%")


if __name__ == "__main__":
    main()
