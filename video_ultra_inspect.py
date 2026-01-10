import os
import sys
from datetime import datetime
from pathlib import Path

# Попробуем импортировать всё, что может помочь
try: import hachoir.parser, hachoir.metadata; HACHOIR_OK = True
except ImportError: HACHOIR_OK = False

try: from enzyme import read_metadata; ENZYME_OK = True
except ImportError: ENZYME_OK = False

try: import pymediainfo; MEDIAINFO_OK = True
except ImportError: MEDIAINFO_OK = False

def ultra_inspect(file_path):
    path = Path(file_path).resolve()
    print(f"\n{'='*80}")
    print(f"УЛЬТРА-АНАЛИЗ ВИДЕО: {path.name}")
    print(f"{'='*80}")

    # 1. Hachoir (то, что мы пытались внедрить)
    if HACHOIR_OK:
        print("\n[1] Проверка через Hachoir...")
        try:
            parser = hachoir.parser.createParser(str(path))
            metadata = hachoir.metadata.extractMetadata(parser)
            if metadata:
                for line in metadata.exportPlaintext():
                    if 'date' in line.lower() or 'creation' in line.lower():
                        print(f"  ✅ Найдено: {line}")
            else: print("  - Метаданные не извлечены.")
        except Exception as e: print(f"  - Ошибка Hachoir: {e}")
    else: print("\n[1] Hachoir не установлен.")

    # 2. PyMediaInfo (считается самым мощным, обертка над MediaInfo)
    if MEDIAINFO_OK:
        print("\n[2] Проверка через MediaInfo...")
        try:
            mi = pymediainfo.MediaInfo.parse(str(path))
            found = False
            for track in mi.tracks:
                for key, val in track.to_data().items():
                    if any(d in key.lower() for d in ['date', 'time', 'encoded']):
                        print(f"  ✅ {key}: {val}")
                        found = True
            if not found: print("  - Никаких дат не найдено.")
        except Exception as e: print(f"  - Ошибка MediaInfo: {e}")
    else: print("\n[2] PyMediaInfo не установлен (нужна утилита mediainfo в системе).")

    # 3. Enzyme (специально для MP4/MKV)
    if ENZYME_OK:
        print("\n[3] Проверка через Enzyme...")
        try:
            with open(path, 'rb') as f:
                meta = read_metadata(f)
                print(f"  ✅ Свойства: {meta}")
        except Exception as e: print(f"  - Ошибка Enzyme: {e}")

    # 4. Проверка на "Атомы" Apple (ручной поиск в бинарнике)
    print("\n[4] Поиск скрытых Apple-меток (бинарный поиск)...")
    try:
        with open(path, 'rb') as f:
            chunk = f.read(1024 * 512) # Первые 512 КБ
            import re
            # Ищем даты в формате 2021:08:18 или 2021-08-18
            pattern = re.compile(b'(\d{4}[:\-]\d{2}[:\-]\d{2})')
            matches = pattern.findall(chunk)
            if matches:
                for m in set(matches): print(f"  🔍 Найдена подозрительная строка: {m.decode(errors='ignore')}")
            else: print("  - Бинарных совпадений не найдено.")
    except Exception as e: print(f"  - Ошибка бинарного поиска: {e}")

    # 5. Свойства ОС
    print("\n[5] Свойства файловой системы:")
    print(f"  - mtime (изменение): {datetime.fromtimestamp(path.stat().st_mtime)}")
    print(f"  - ctime (создание/статус): {datetime.fromtimestamp(path.stat().st_ctime)}")

    print(f"\n{'='*80}\n")

if __name__ == "__main__":
    file_to_test = input("Путь к видео-файлу: ").strip('"').strip("'")
    ultra_inspect(file_to_test)
