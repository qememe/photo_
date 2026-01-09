import os
import sys
from datetime import datetime
from pathlib import Path

def inspect_file_simple(file_path):
    path = Path(file_path).expanduser().resolve()
    if not path.exists():
        print(f"❌ Ошибка: Файл не найден по пути: {file_path}")
        return

    print(f"\n{'='*60}")
    print(f"АНАЛИЗ СВОЙСТВ ФАЙЛА (Метод отца)")
    print(f"{'='*60}")
    print(f"Путь: {path}")
    
    stats = path.stat()
    
    # В Linux ctime — это время изменения метаданных, 
    # а не всегда создания, поэтому смотрим оба значения
    ctime = datetime.fromtimestamp(stats.st_ctime)
    mtime = datetime.fromtimestamp(stats.st_mtime)
    
    print(f"\n[Системные метки времени]")
    print(f"  - Дата изменения (mtime):   {mtime}")
    print(f"  - Дата создания/статуса (ctime): {ctime}")
    
    earliest = min(ctime, mtime)
    print(f"\nРезультат: Самая ранняя дата — {earliest}")
    print(f"Год для сортировки: {earliest.year}")
    
    if earliest.year == 2026:
        print("\n⚠️ ВНИМАНИЕ: Система считает, что файл из 2026 года.")
        print("Это значит, что оригинальные метаданные стерты при копировании.")
    
    print(f"{'='*60}\n")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        inspect_file_simple(sys.argv[1])
    else:
        p = input("Введите путь к файлу: ").strip().replace("'", "").replace('"', "")
        inspect_file_simple(p)
