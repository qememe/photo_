# Photo Sorterovka / Фото Сортеровка

**EN** | [RU](#ru)

A powerful Python utility for organizing photos and videos by year with GPS location tracking and CSV reporting.

## Features / Возможности

- 📁 **Automatic Organization**: Sorts media files by year into organized folders
- 📍 **GPS Location Extraction**: Extracts and reports GPS coordinates from EXIF/metadata
- 📊 **CSV Reports**: Generates detailed CSV reports for each year folder
- 🎯 **Progress Tracking**: Real-time progress bars using Rich library with colored output
- 🛡️ **Error Handling**: Comprehensive error handling with detailed logging
- 🔍 **Metadata Extraction**: Supports images (JPEG, PNG, HEIC) and videos (MP4, MOV, AVI, etc.)
- 🌈 **Professional UI**: Beautiful terminal interface with colored messages

## Requirements / Требования

### Arch Linux / Gentoo Linux

```bash
# Install system dependencies
sudo pacman -S python python-pip python-venv

# Optional: Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

**Note for Arch Linux users**: If you encounter issues with `python-pip`, you may need to install `python-pip` separately:
```bash
sudo pacman -S python-pip
```

For Gentoo Linux users, install dependencies via `emerge`:
```bash
emerge -av dev-lang/python dev-python/pip
```

### Windows

```bash
# Install Python 3.8+ from python.org
# Then install dependencies:
pip install -r requirements.txt
```

## Installation / Установка

1. Clone the repository:
```bash
git clone https://github.com/qememe/photo_.git
cd Photo_sorterovka
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the script:
```bash
python main.py
```

Or use the provided scripts:
- Linux: `./run.sh`
- Windows: `run.bat`

## Usage / Использование

1. Run the application: `python main.py`
2. Enter the source directory containing your photos/videos
3. Enter the destination directory where sorted files will be placed
4. Enable/disable location verification (GPS extraction)
5. Confirm and let the tool organize your files

### Output Structure / Структура вывода

```
destination/
├── 2023/
│   ├── report.csv
│   ├── photo1.jpg
│   └── video1.mp4
├── 2024/
│   ├── report.csv
│   └── photo2.jpg
└── ...
```

### CSV Report Format / Формат CSV отчета

The `report.csv` in each year folder contains:
- `filename`: Name of the file
- `format`: File extension
- `date`: Date in YYYY-MM-DD format
- `time`: Time in HH:MM:SS format
- `Location`: GPS coordinates in Decimal Degrees format (e.g., "55.7558, 37.6173") or "Нет данных" if GPS data is missing

**Example CSV row:**
```csv
filename,format,date,time,Location
IMG_001.jpg,.jpg,2023-05-15,14:30:00,55.755800, 37.617300
VID_002.mp4,.mp4,2023-06-20,10:15:00,Нет данных
```

## Project Structure / Структура проекта

```
Photo_sorterovka/
├── main.py                 # Main entry point
├── utils/
│   ├── __init__.py
│   ├── file_handler.py     # File operations
│   ├── metadata_extractor.py  # EXIF/metadata extraction
│   ├── report_generator.py    # CSV report generation
│   └── error_handler.py       # Error handling utilities
├── resources/              # Resource files
├── requirements.txt        # Python dependencies
├── .gitignore
├── README.md
└── guide.txt              # Git setup guide
```

## Error Handling / Обработка ошибок

The tool automatically handles:
- `PermissionError`: Files that cannot be accessed
- `FileExistsError`: Duplicate file names (auto-renamed with index, e.g., `image_1.jpg`)
- `CorruptedMetadataError`: Files with corrupted metadata

All skipped files are logged to `skipped_files.log` in the root directory.

**Safety Features:**
- Infinite loop protection in filename generation (max 100,000 attempts)
- Graceful error handling with detailed logging
- Automatic directory creation

## Logging / Логирование

- Application logs: `media_sorter.log`
- Skipped files: `skipped_files.log`

## Technical Details / Технические детали

### Code Localization
- All complex logic blocks have detailed Russian comments
- Docstrings remain in English (international standards) with Russian summaries
- All CLI messages, prompts, and console outputs are in Russian
- Professional terminal output using Rich library with colors

### GPS Location Handling
- GPS coordinates are extracted from EXIF data (images) and video metadata
- Coordinates are converted from degrees/minutes/seconds to Decimal Degrees
- Missing GPS data is displayed as "Нет данных" in CSV reports
- Location verification can be enabled/disabled during sorting

### File Renaming Logic
- Automatic unique filename generation prevents overwrites
- Format: `original_name_counter.ext` (e.g., `photo_1.jpg`, `photo_2.jpg`)
- Maximum 100,000 attempts to prevent infinite loops
- Safe handling of edge cases

## License / Лицензия

This project is open source and available for personal use.

---

# RU

Мощная утилита на Python для организации фотографий и видео по годам с отслеживанием GPS-координат и генерацией CSV-отчетов.

## Возможности

- 📁 **Автоматическая организация**: Сортирует медиафайлы по годам в организованные папки
- 📍 **Извлечение GPS-координат**: Извлекает и отображает GPS-координаты из EXIF/метаданных
- 📊 **CSV-отчеты**: Генерирует детальные CSV-отчеты для каждой папки года
- 🎯 **Отслеживание прогресса**: Индикаторы прогресса в реальном времени с использованием библиотеки Rich и цветным выводом
- 🛡️ **Обработка ошибок**: Комплексная обработка ошибок с детальным логированием
- 🔍 **Извлечение метаданных**: Поддержка изображений (JPEG, PNG, HEIC) и видео (MP4, MOV, AVI и др.)
- 🌈 **Профессиональный интерфейс**: Красивый интерфейс терминала с цветными сообщениями

## Требования

### Arch Linux / Gentoo Linux

```bash
# Установка системных зависимостей
sudo pacman -S python python-pip python-venv

# Опционально: Создание виртуального окружения (рекомендуется)
python -m venv venv
source venv/bin/activate

# Установка Python-зависимостей
pip install -r requirements.txt
```

**Примечание для пользователей Arch Linux**: Если возникают проблемы с `python-pip`, может потребоваться установить `python-pip` отдельно:
```bash
sudo pacman -S python-pip
```

Для пользователей Gentoo Linux установите зависимости через `emerge`:
```bash
emerge -av dev-lang/python dev-python/pip
```

**Советы для Arch Linux:**
- Используйте `python-venv` для создания изолированного окружения
- Если `python-pip` недоступен, используйте `pip` через `python -m pip`
- Для установки зависимостей можно использовать `pip install --user -r requirements.txt` для установки в домашнюю директорию

### Windows

```bash
# Установите Python 3.8+ с python.org
# Затем установите зависимости:
pip install -r requirements.txt
```

## Установка

1. Клонируйте репозиторий:
```bash
git clone https://github.com/qememe/photo_.git
cd Photo_sorterovka
```

2. Установите зависимости:
```bash
pip install -r requirements.txt
```

3. Запустите скрипт:
```bash
python main.py
```

Или используйте предоставленные скрипты:
- Linux: `./run.sh`
- Windows: `run.bat`

## Использование

1. Запустите приложение: `python main.py`
2. Введите исходную директорию с вашими фотографиями/видео
3. Введите целевую директорию, куда будут помещены отсортированные файлы
4. Включите/выключите проверку местоположения (извлечение GPS)
5. Подтвердите и позвольте инструменту организовать ваши файлы

### Структура вывода

```
destination/
├── 2023/
│   ├── report.csv
│   ├── photo1.jpg
│   └── video1.mp4
├── 2024/
│   ├── report.csv
│   └── photo2.jpg
└── ...
```

### Формат CSV-отчета

Файл `report.csv` в каждой папке года содержит:
- `filename`: Имя файла
- `format`: Расширение файла
- `date`: Дата в формате YYYY-MM-DD
- `time`: Время в формате HH:MM:SS
- `Location`: GPS-координаты в формате десятичных градусов (например, "55.7558, 37.6173") или "Нет данных", если GPS-данные отсутствуют

**Пример строки CSV:**
```csv
filename,format,date,time,Location
IMG_001.jpg,.jpg,2023-05-15,14:30:00,55.755800, 37.617300
VID_002.mp4,.mp4,2023-06-20,10:15:00,Нет данных
```

## Структура проекта

```
Photo_sorterovka/
├── main.py                 # Точка входа
├── utils/
│   ├── __init__.py
│   ├── file_handler.py     # Операции с файлами
│   ├── metadata_extractor.py  # Извлечение EXIF/метаданных
│   ├── report_generator.py    # Генерация CSV-отчетов
│   └── error_handler.py       # Утилиты обработки ошибок
├── resources/              # Файлы ресурсов
├── requirements.txt        # Python-зависимости
├── .gitignore
├── README.md
└── guide.txt              # Руководство по настройке Git
```

## Обработка ошибок

Инструмент автоматически обрабатывает:
- `PermissionError`: Файлы, к которым нет доступа
- `FileExistsError`: Дублирующиеся имена файлов (автоматически переименовываются с индексом, например, `image_1.jpg`)
- `CorruptedMetadataError`: Файлы с поврежденными метаданными

Все пропущенные файлы логируются в `skipped_files.log` в корневой директории.

**Функции безопасности:**
- Защита от бесконечных циклов при генерации имен файлов (максимум 100,000 попыток)
- Корректная обработка ошибок с детальным логированием
- Автоматическое создание директорий

## Логирование

- Логи приложения: `media_sorter.log`
- Пропущенные файлы: `skipped_files.log`

## Технические детали

### Локализация кода
- Все сложные блоки логики имеют подробные русские комментарии
- Docstrings остаются на английском (международные стандарты) с русскими краткими описаниями
- Все CLI-сообщения, промпты и вывод в консоль на русском языке
- Профессиональный вывод в терминал с использованием библиотеки Rich с цветами

### Обработка GPS-координат
- GPS-координаты извлекаются из EXIF-данных (изображения) и метаданных видео
- Координаты преобразуются из формата градусы/минуты/секунды в десятичные градусы
- Отсутствующие GPS-данные отображаются как "Нет данных" в CSV-отчетах
- Проверку местоположения можно включить/выключить во время сортировки

### Логика переименования файлов
- Автоматическая генерация уникальных имен файлов предотвращает перезапись
- Формат: `исходное_имя_счетчик.расширение` (например, `photo_1.jpg`, `photo_2.jpg`)
- Максимум 100,000 попыток для предотвращения бесконечных циклов
- Безопасная обработка граничных случаев

## Лицензия

Этот проект с открытым исходным кодом и доступен для личного использования.
