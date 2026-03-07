#!/bin/bash
# Скрипт установки всех зависимостей и запуска spliter3

set -e  # Остановка при ошибке

echo "=========================================="
echo "  УСТАНОВКА ЗАВИСИМОСТЕЙ И ЗАПУСК SPLITER3"
echo "=========================================="
echo ""

# Шаг 1: Обновление списка пакетов
echo "[1/5] Обновление списка пакетов..."
sudo apt-get update
echo "✓ Список пакетов обновлен"
echo ""

# Шаг 2: Установка pip и venv
echo "[2/5] Установка python3-pip и python3-venv..."
sudo apt-get install -y python3-pip python3-venv
echo "✓ pip и venv установлены"
echo ""

# Шаг 3: Переход в директорию проекта
echo "[3/5] Переход в директорию проекта..."
cd /mnt/d/AiChess/spliter3/spliter
echo "✓ Директория: $(pwd)"
echo ""

# Шаг 4: Установка Python зависимостей
echo "[4/5] Установка Python зависимостей из requirements.txt..."
echo "Это может занять 2-5 минут..."
pip3 install --user -r requirements.txt
echo "✓ Все зависимости установлены"
echo ""

# Шаг 5: Запуск программы
echo "[5/5] Запуск spliter3..."
echo "=========================================="
echo ""
python3 main.py --defaults
