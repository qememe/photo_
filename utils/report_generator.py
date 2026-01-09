"""CSV report generation for sorted media files."""

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.file_handler import MediaFile

logger = logging.getLogger(__name__)


def format_location(gps_coords: Optional[tuple]) -> str:
    """
    Format GPS coordinates as Decimal Degrees string.
    
    Краткое описание: Форматирует GPS-координаты в строку десятичных градусов.
    При отсутствии данных возвращает "Нет данных".

    Args:
        gps_coords: Tuple of (latitude, longitude) or None

    Returns:
        Formatted string like "55.7558, 37.6173" or "Нет данных" if missing
    """
    # Проверка наличия GPS-координат
    if not gps_coords or len(gps_coords) != 2:
        return "Нет данных"

    try:
        # Преобразование координат в формат десятичных градусов
        lat, lon = gps_coords
        return f"{lat:.6f}, {lon:.6f}"
    except (ValueError, TypeError):
        # В случае ошибки преобразования возвращаем "Нет данных"
        return "Нет данных"


def generate_csv_report(
    year_dir: Path,
    media_files: List[MediaFile],
    include_location: bool = True
) -> bool:
    """
    Generate CSV report for a year directory.
    
    Краткое описание: Генерирует CSV-отчет для директории года со списком
    всех медиафайлов, их датами и GPS-координатами (если доступны).

    Args:
        year_dir: Year directory path (e.g., /path/to/2023/)
        media_files: List of MediaFile objects in this year
        include_location: Whether to include Location column

    Returns:
        True if successful, False otherwise
    """
    if not year_dir.exists():
        logger.warning(f"Директория года не существует: {year_dir}")
        return False

    csv_path = year_dir / "report.csv"

    try:
        # Определение колонок CSV-файла
        fieldnames = ['filename', 'format', 'date', 'time']
        if include_location:
            fieldnames.append('Location')

        with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for media_file in media_files:
                # Проверка принадлежности файла к этой директории года
                if media_file.target_path:
                    # Проверка соответствия целевого пути директории года
                    if media_file.target_path.parent != year_dir:
                        continue
                else:
                    # Если нет target_path, пропускаем (файл не был перемещен)
                    continue

                # Построение строки CSV и запись
                row = _build_csv_row(media_file, include_location)
                if row:
                    writer.writerow(row)

        logger.info(f"Сгенерирован CSV-отчет: {csv_path}")
        return True

    except Exception as e:
        logger.error(f"Ошибка генерации CSV-отчета {csv_path}: {e}")
        return False


def _build_csv_row(media_file: MediaFile, include_location: bool) -> Optional[Dict[str, str]]:
    """
    Build a CSV row from MediaFile.
    
    Краткое описание: Строит строку CSV из объекта MediaFile, извлекая
    имя файла, формат, дату, время и GPS-координаты.

    Args:
        media_file: MediaFile instance
        include_location: Whether to include location

    Returns:
        Dictionary with CSV row data or None
    """
    try:
        # Получение имени файла
        filename = media_file.source_path.name if media_file.source_path else "неизвестно"

        # Получение формата (расширения)
        format_ext = media_file.source_path.suffix.lower() if media_file.source_path else ""

        # Получение даты и времени из метаданных
        date_str = ""
        time_str = ""
        dt = media_file.metadata.get('datetime_original')
        if isinstance(dt, datetime):
            date_str = dt.strftime('%Y-%m-%d')
            time_str = dt.strftime('%H:%M:%S')

        row = {
            'filename': filename,
            'format': format_ext,
            'date': date_str,
            'time': time_str,
        }

        # Добавление GPS-координат, если включено
        if include_location:
            gps_coords = media_file.metadata.get('gps_coordinates')
            row['Location'] = format_location(gps_coords)

        return row

    except Exception as e:
        logger.error(f"Ошибка построения CSV-строки для {media_file.source_path}: {e}")
        return None


def append_to_csv_report(
    media_file: MediaFile,
    include_location: bool = True
) -> bool:
    """
    Добавить запись о медиафайле в CSV-отчет года (инкрементальная запись).
    
    Краткое описание: Добавляет одну запись о перемещенном медиафайле в CSV-отчет
    соответствующего года. Создает файл и заголовок, если файл не существует.
    Используется для синхронной записи после каждого перемещенного файла.

    Args:
        media_file: MediaFile instance that was moved
        include_location: Whether to include Location column

    Returns:
        True if successful, False otherwise
    """
    if not media_file.target_path:
        return False

    year_dir = media_file.target_path.parent
    csv_path = year_dir / "report.csv"

    try:
        # Определение колонок CSV-файла
        fieldnames = ['filename', 'format', 'date', 'time']
        if include_location:
            fieldnames.append('Location')

        # Проверка существования файла для определения режима записи
        file_exists = csv_path.exists()

        # Открытие файла в режиме добавления (если существует) или создания (если нет)
        with open(csv_path, 'a', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            # Запись заголовка, если файл только что создан
            if not file_exists:
                writer.writeheader()

            # Построение и запись строки CSV
            row = _build_csv_row(media_file, include_location)
            if row:
                writer.writerow(row)

        logger.debug(f"Добавлена запись в CSV-отчет: {csv_path}")
        return True

    except Exception as e:
        logger.error(f"Ошибка добавления записи в CSV-отчет {csv_path}: {e}")
        return False


def generate_reports_for_all_years(
    destination_dir: Path,
    all_media_files: List[MediaFile],
    include_location: bool = True
) -> None:
    """
    Generate CSV reports for all year directories.
    
    Краткое описание: Генерирует CSV-отчеты для всех директорий годов,
    группируя файлы по годам и создавая отчет для каждого года.

    Args:
        destination_dir: Root destination directory
        all_media_files: List of all MediaFile objects
        include_location: Whether to include Location column
    """
    # Группировка файлов по годам
    files_by_year: Dict[int, List[MediaFile]] = {}

    for media_file in all_media_files:
        if not media_file.target_path:
            continue

        year_dir = media_file.target_path.parent
        # Проверка, что директория года находится в корневой целевой директории
        if year_dir.parent != destination_dir:
            continue

        try:
            # Извлечение года из имени директории
            year = int(year_dir.name)
            if year not in files_by_year:
                files_by_year[year] = []
            files_by_year[year].append(media_file)
        except ValueError:
            logger.warning(f"Неверное имя директории года: {year_dir.name}")
            continue

    # Генерация отчета для каждого года
    for year, files in files_by_year.items():
        year_dir = destination_dir / str(year)
        generate_csv_report(year_dir, files, include_location)

