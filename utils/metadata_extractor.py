"""Metadata extraction for images and videos."""

import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Setup error logger (separate from main logger)
# Handler will be configured in main.py, but we set up the logger here
_error_logger = logging.getLogger('process_errors')
_error_logger.setLevel(logging.ERROR)
# Prevent propagation to root logger to avoid console output
_error_logger.propagate = False

try:
    from exif import Image as ExifImage
except ImportError:
    ExifImage = None

try:
    from mutagen import File as MutagenFile
    from mutagen.mp4 import MP4
    from mutagen.quicktime import QuickTime
    MUTAGEN_AVAILABLE = True
except ImportError:
    MutagenFile = None
    MP4 = None
    QuickTime = None
    MUTAGEN_AVAILABLE = False

try:
    from PIL import Image as PILImage
    from PIL.ExifTags import TAGS
    PILLOW_AVAILABLE = True
except ImportError:
    PILImage = None
    TAGS = None
    PILLOW_AVAILABLE = False

logger = logging.getLogger(__name__)

# Supported image formats
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.tiff', '.tif', '.heic', '.heif')
# Supported video formats
VIDEO_EXTENSIONS = ('.mp4', '.mov', '.avi', '.mkv', '.m4v', '.3gp', '.webm')


def convert_gps_coordinates(gps_latitude: tuple, gps_longitude: tuple, 
                            latitude_ref: str, longitude_ref: str) -> Optional[Tuple[float, float]]:
    """
    Convert GPS coordinates from EXIF format to Decimal Degrees.
    
    Краткое описание: Преобразует GPS-координаты из формата EXIF (градусы, минуты, секунды)
    в десятичные градусы с учетом направления (N/S, E/W).

    Args:
        gps_latitude: Tuple of (degrees, minutes, seconds) for latitude
        gps_longitude: Tuple of (degrees, minutes, seconds) for longitude
        latitude_ref: Reference direction ('N' or 'S')
        longitude_ref: Reference direction ('E' or 'W')

    Returns:
        Tuple of (latitude, longitude) in Decimal Degrees, or None if conversion fails
    """
    try:
        # Преобразование широты из формата градусы/минуты/секунды в десятичные градусы
        lat_deg, lat_min, lat_sec = gps_latitude
        latitude = lat_deg + (lat_min / 60.0) + (lat_sec / 3600.0)
        # Отрицательное значение для южного полушария
        if latitude_ref.upper() == 'S':
            latitude = -latitude

        # Преобразование долготы из формата градусы/минуты/секунды в десятичные градусы
        lon_deg, lon_min, lon_sec = gps_longitude
        longitude = lon_deg + (lon_min / 60.0) + (lon_sec / 3600.0)
        # Отрицательное значение для западного полушария
        if longitude_ref.upper() == 'W':
            longitude = -longitude

        return (latitude, longitude)
    except (ValueError, TypeError, AttributeError) as e:
        logger.debug(f"Ошибка преобразования GPS-координат: {e}")
        return None


def extract_gps_from_image(exif_image: ExifImage) -> Optional[Tuple[float, float]]:
    """
    Extract GPS coordinates from EXIF image.
    
    Краткое описание: Извлекает GPS-координаты из EXIF-данных изображения
    и преобразует их в формат десятичных градусов.

    Args:
        exif_image: ExifImage object

    Returns:
        Tuple of (latitude, longitude) in Decimal Degrees, or None
    """
    try:
        # Проверка наличия GPS-данных в EXIF
        if not hasattr(exif_image, 'gps_latitude') or not hasattr(exif_image, 'gps_longitude'):
            return None

        # Извлечение координат и направлений
        gps_latitude = exif_image.gps_latitude
        gps_longitude = exif_image.gps_longitude
        latitude_ref = getattr(exif_image, 'gps_latitude_ref', 'N')
        longitude_ref = getattr(exif_image, 'gps_longitude_ref', 'E')

        # Преобразование в десятичные градусы
        return convert_gps_coordinates(gps_latitude, gps_longitude, latitude_ref, longitude_ref)
    except Exception as e:
        logger.debug(f"Ошибка извлечения GPS из изображения: {e}")
        return None


def extract_image_metadata_with_pillow(file_path: Path) -> Optional[Dict[str, Any]]:
    """
    Extract metadata from image using Pillow as fallback.
    
    Args:
        file_path: Path to image file
        
    Returns:
        Dictionary with metadata or None if extraction fails or date is invalid
    """
    if not PILLOW_AVAILABLE:
        return None
    
    # Порог 2004-01-01 для фильтрации системных значений по умолчанию
    # Обновлен фильтр дат: теперь разрешен 2026 год для актуальных файлов
    MIN_DATE = datetime(2004, 1, 1)
    MAX_YEAR = 2026
    
    try:
        with PILImage.open(file_path) as img:
            metadata = {}
            
            # Проверка img.info для строк типа 'creation_time' или 'date:create'
            if hasattr(img, 'info') and img.info:
                for key, value in img.info.items():
                    if isinstance(key, str) and isinstance(value, str):
                        key_lower = key.lower()
                        # Проверка на ключи, связанные с датой создания
                        if any(term in key_lower for term in ['creation_time', 'date:create', 'date', 'time']):
                            try:
                                # Попытка парсинга различных форматов даты
                                for fmt in ['%Y:%m:%d %H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d']:
                                    try:
                                        parsed_date = datetime.strptime(str(value), fmt)
                                        # Filter: before 2004 or after 2026 -> discard
                                        if parsed_date >= MIN_DATE and parsed_date.year <= MAX_YEAR:
                                            if 'datetime_original' not in metadata:
                                                metadata['datetime_original'] = parsed_date
                                            break
                                    except ValueError:
                                        continue
                            except (ValueError, TypeError, AttributeError):
                                pass
            
            # Проверка img.getexif() если доступно
            try:
                exifdata = img.getexif()
                if exifdata:
                    for tag_id, value in exifdata.items():
                        tag = TAGS.get(tag_id, tag_id)
                        if tag == 'DateTimeOriginal' and value:
                            try:
                                parsed_date = datetime.strptime(
                                    str(value), '%Y:%m:%d %H:%M:%S'
                                )
                                # Filter: before 2004 or after 2026 -> discard
                                if parsed_date >= MIN_DATE and parsed_date.year <= MAX_YEAR:
                                    metadata['datetime_original'] = parsed_date
                            except (ValueError, TypeError):
                                pass
                        elif tag == 'DateTime' and value and 'datetime_original' not in metadata:
                            try:
                                parsed_date = datetime.strptime(
                                    str(value), '%Y:%m:%d %H:%M:%S'
                                )
                                # Filter: before 2004 or after 2026 -> discard
                                if parsed_date >= MIN_DATE and parsed_date.year <= MAX_YEAR:
                                    metadata['datetime'] = parsed_date
                            except (ValueError, TypeError):
                                pass
                        elif tag == 'Make' and value:
                            try:
                                metadata['make'] = str(value).strip()
                            except (ValueError, TypeError):
                                pass
            except (AttributeError, Exception):
                # getexif() может быть недоступен или вызвать ошибку
                pass
            
            return metadata if metadata else None
    except Exception as e:
        _error_logger.error(f"Pillow extraction failed for {file_path}: {e}", exc_info=False)
        return None


def extract_image_metadata(file_path: Path) -> Optional[Dict[str, Any]]:
    """
    Extract EXIF metadata from image file with robust error handling.
    
    Проверка на 2004 год и уход от использования текущей даты.
    Обновлен фильтр дат: теперь разрешен 2026 год для актуальных файлов.
    
    Краткое описание: Извлекает EXIF-метаданные из файла изображения,
    включая дату/время создания и GPS-координаты. Использует строгую иерархию:
    1. EXIF (для JPG) - библиотека exif (PNG файлы обходят эту библиотеку)
    2. Pillow (для PNG и fallback) - проверка img.info и img.getexif()
    3. Системные статистики (финальный fallback) - минимальное из getmtime/getctime
    Если дата найдена, но вне диапазона 2004-2026, она отбрасывается.

    Args:
        file_path: Path to image file

    Returns:
        Dictionary with metadata or None if extraction fails or date is before 2004
    """
    # Порог 2004-01-01 для фильтрации системных значений по умолчанию
    # Обновлен фильтр дат: теперь разрешен 2026 год для актуальных файлов
    MIN_DATE = datetime(2004, 1, 1)
    MAX_YEAR = 2026
    metadata = {}
    
    # PNG файлы обходят библиотеку exif для предотвращения ошибок TiffByteOrder
    suffix_lower = file_path.suffix.lower()
    skip_exif = (suffix_lower == '.png')
    
    # Log PNG skip as INFO, not ERROR
    if skip_exif:
        logger.info(f"PNG file detected, skipping EXIF, using Pillow/System stats: {file_path.name}")
    
    # Шаг 1: Попытка извлечения через библиотеку exif (для JPG, не для PNG)
    if ExifImage and not skip_exif:
        try:
            with open(file_path, 'rb') as image_file:
                exif_image = ExifImage(image_file)

            if exif_image.has_exif:
                # Extract datetime_original
                if hasattr(exif_image, 'datetime_original'):
                    try:
                        dt_str = exif_image.datetime_original
                        parsed_date = datetime.strptime(dt_str, '%Y:%m:%d %H:%M:%S')
                        # Filter: before 2004 or after 2026 -> discard
                        if parsed_date >= MIN_DATE and parsed_date.year <= MAX_YEAR:
                            metadata['datetime_original'] = parsed_date
                    except (ValueError, AttributeError):
                        pass

                # Extract datetime
                if hasattr(exif_image, 'datetime'):
                    try:
                        dt_str = exif_image.datetime
                        parsed_date = datetime.strptime(dt_str, '%Y:%m:%d %H:%M:%S')
                        # Filter: before 2004 or after 2026 -> discard
                        if parsed_date >= MIN_DATE and parsed_date.year <= MAX_YEAR:
                            if 'datetime_original' not in metadata:
                                metadata['datetime_original'] = parsed_date
                            else:
                                metadata['datetime'] = parsed_date
                    except (ValueError, AttributeError):
                        pass

                # Extract GPS coordinates
                gps_coords = extract_gps_from_image(exif_image)
                if gps_coords:
                    metadata['gps_coordinates'] = gps_coords
                
                # Extract make (manufacturer) field
                if hasattr(exif_image, 'make'):
                    try:
                        make_value = exif_image.make
                        if make_value:
                            metadata['make'] = str(make_value).strip()
                    except (ValueError, AttributeError):
                        pass
                    
                # Если найдена валидная дата (после 2004 и до 2026), возвращаем метаданные
                if 'datetime_original' in metadata or 'datetime' in metadata:
                    return metadata
        except ValueError as e:
            # TIFF byte order errors and similar - log to file, not console
            _error_logger.error(f"EXIF extraction failed for {file_path}: {e}", exc_info=False)
        except Exception as e:
            # Other exif errors - log to file
            _error_logger.error(f"EXIF extraction error for {file_path}: {e}", exc_info=False)
    
    # Шаг 2: Fallback на Pillow (для PNG и других форматов)
    if not metadata and PILLOW_AVAILABLE:
        pillow_metadata = extract_image_metadata_with_pillow(file_path)
        if pillow_metadata:
            # Filter dates from Pillow
            filtered_metadata = {}
            for key, value in pillow_metadata.items():
                if isinstance(value, datetime):
                    if value >= MIN_DATE and value.year <= MAX_YEAR:
                        filtered_metadata[key] = value
                else:
                    filtered_metadata[key] = value
            if filtered_metadata:
                metadata.update(filtered_metadata)
                # Если найдена валидная дата, возвращаем метаданные
                if 'datetime_original' in metadata or 'datetime' in metadata:
                    return metadata
    
    # Шаг 3: XMP Brute Force (Deep Scan - Linux Style)
    # This MUST take priority over system stats if it finds a valid date
    xmp_date = get_xmp_brute_force_date(file_path)
    if xmp_date:
        metadata['datetime_original'] = xmp_date
        return metadata
    
    # Шаг 4: Системные статистики (финальный fallback)
    system_date = get_system_fallback_date(file_path)
    if system_date:
        metadata['datetime_original'] = system_date
        return metadata
    
    # iPhone Mode: Search for "Apple" in binary data if Make tag is missing
    if 'make' not in metadata:
        try:
            with open(file_path, 'rb') as f:
                # Read first 512KB to search for Apple identifier
                data = f.read(524288)
                if b'Apple' in data:
                    metadata['make'] = 'Apple'
                    logger.debug(f"Found Apple identifier in binary data for {file_path.name}")
        except Exception:
            pass
    
    # Если все методы извлечения не нашли валидную дату, возвращаем None
    return None


def extract_video_metadata(file_path: Path) -> Optional[Dict[str, Any]]:
    """
    Extract metadata from video file using mutagen with graceful handling.
    
    Краткое описание: Извлекает метаданные из видеофайла с помощью библиотеки mutagen,
    включая дату создания и GPS-координаты (если доступны).
    Проверяет creation_time в заголовках метаданных перед fallback на системные статистики.

    Args:
        file_path: Path to video file

    Returns:
        Dictionary with metadata or None if extraction fails or date is invalid
    """
    # Обновлен фильтр дат: теперь разрешен 2026 год для актуальных файлов
    MIN_DATE = datetime(2004, 1, 1)
    MAX_YEAR = 2026
    
    if not MUTAGEN_AVAILABLE:
        # Fallback на системные статистики только если дата в допустимом диапазоне
        system_date = get_system_fallback_date(file_path)
        if system_date:
            return {'datetime_original': system_date}
        return None

    try:
        # Загрузка метаданных через mutagen
        video_file = MutagenFile(str(file_path))
        if not video_file:
            logger.debug(f"Не удалось загрузить метаданные для {file_path.name}")
            # Fallback на системные статистики только если дата в допустимом диапазоне
            system_date = get_system_fallback_date(file_path)
            if system_date:
                return {'datetime_original': system_date}
            return None

        metadata = {}
        
        # Приоритетная проверка creation_time в заголовках метаданных
        creation_time_keys = ['creation_time', 'creationdate', 'created', 'date_created']
        for key in creation_time_keys:
            if key in video_file:
                try:
                    date_str = str(video_file[key][0] if isinstance(video_file[key], list) else video_file[key])
                    for fmt in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%d', '%Y:%m:%d %H:%M:%S', '%Y-%m-%d %H:%M:%S']:
                        try:
                            if fmt.endswith('Z'):
                                date_str_clean = date_str.rstrip('Z')
                                parsed_date = datetime.strptime(date_str_clean, fmt[:-1])
                            else:
                                parsed_date = datetime.strptime(date_str, fmt)
                            # Фильтр: дата должна быть в диапазоне 2004-2026
                            if parsed_date >= MIN_DATE and parsed_date.year <= MAX_YEAR:
                                metadata['datetime_original'] = parsed_date
                                break
                        except ValueError:
                            continue
                    if 'datetime_original' in metadata:
                        break
                except (ValueError, IndexError, AttributeError, TypeError):
                    continue

        # Извлечение даты создания для MP4 файлов
        if 'datetime_original' not in metadata and isinstance(video_file, MP4):
            # MP4 использует ключи '©day' или '\xa9day' для даты создания
            date_keys = ['©day', '\xa9day', '©DAY', '\xa9DAY']
            for key in date_keys:
                if key in video_file:
                    try:
                        date_str = str(video_file[key][0])
                        # Формат обычно: "2023-12-25T10:30:00Z" или "2023-12-25"
                        for fmt in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%d']:
                            try:
                                if fmt.endswith('Z'):
                                    date_str_clean = date_str.rstrip('Z')
                                    parsed_date = datetime.strptime(date_str_clean, fmt[:-1])
                                else:
                                    parsed_date = datetime.strptime(date_str, fmt)
                                # Фильтр: дата должна быть в диапазоне 2004-2026
                                if parsed_date >= MIN_DATE and parsed_date.year <= MAX_YEAR:
                                    metadata['datetime_original'] = parsed_date
                                    break
                            except ValueError:
                                continue
                        if 'datetime_original' in metadata:
                            break
                    except (ValueError, IndexError, AttributeError) as e:
                        logger.debug(f"Ошибка парсинга даты из {key}: {e}")

        # Извлечение даты создания для QuickTime (MOV) файлов
        if 'datetime_original' not in metadata and isinstance(video_file, QuickTime):
            # QuickTime использует ключи '©day' или '\xa9day'
            date_keys = ['©day', '\xa9day', '©DAY', '\xa9DAY']
            for key in date_keys:
                if key in video_file:
                    try:
                        date_str = str(video_file[key][0])
                        for fmt in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%d']:
                            try:
                                if fmt.endswith('Z'):
                                    date_str_clean = date_str.rstrip('Z')
                                    parsed_date = datetime.strptime(date_str_clean, fmt[:-1])
                                else:
                                    parsed_date = datetime.strptime(date_str, fmt)
                                # Фильтр: дата должна быть в диапазоне 2004-2026
                                if parsed_date >= MIN_DATE and parsed_date.year <= MAX_YEAR:
                                    metadata['datetime_original'] = parsed_date
                                    break
                            except ValueError:
                                continue
                        if 'datetime_original' in metadata:
                            break
                    except (ValueError, IndexError, AttributeError) as e:
                        logger.debug(f"Ошибка парсинга даты из {key}: {e}")

        # Для других форматов пытаемся найти общие ключи
        if 'datetime_original' not in metadata:
            # Попытка найти дату в общих тегах
            common_date_keys = ['date', 'creation_date', '©day', '\xa9day']
            for key in common_date_keys:
                if key in video_file:
                    try:
                        date_str = str(video_file[key][0] if isinstance(video_file[key], list) else video_file[key])
                        for fmt in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%d', '%Y:%m:%d %H:%M:%S']:
                            try:
                                if fmt.endswith('Z'):
                                    date_str_clean = date_str.rstrip('Z')
                                    parsed_date = datetime.strptime(date_str_clean, fmt[:-1])
                                else:
                                    parsed_date = datetime.strptime(date_str, fmt)
                                # Фильтр: дата должна быть в диапазоне 2004-2026
                                if parsed_date >= MIN_DATE and parsed_date.year <= MAX_YEAR:
                                    metadata['datetime_original'] = parsed_date
                                    break
                            except ValueError:
                                continue
                        if 'datetime_original' in metadata:
                            break
                    except (ValueError, IndexError, AttributeError, TypeError) as e:
                        logger.debug(f"Ошибка парсинга даты из {key}: {e}")

        # Попытка извлечения GPS-координат (редко встречается в видео)
        # MP4 может хранить GPS в ключах '©xyz' или '\xa9xyz'
        gps_keys = ['©xyz', '\xa9xyz', 'location', 'gps']
        for key in gps_keys:
            if key in video_file:
                try:
                    gps_data = video_file[key][0] if isinstance(video_file[key], list) else video_file[key]
                    # Формат может быть разным, пытаемся распарсить
                    if isinstance(gps_data, str):
                        # Может быть в формате "lat,lon" или "+lat+lon"
                        parts = gps_data.replace('+', '').split(',')
                        if len(parts) >= 2:
                            try:
                                lat = float(parts[0])
                                lon = float(parts[1])
                                metadata['gps_coordinates'] = (lat, lon)
                                break
                            except ValueError:
                                pass
                except (ValueError, IndexError, AttributeError, TypeError):
                    pass
        
        # Extract make (manufacturer) from video metadata
        # MP4/QuickTime may store make in '©mak' or '\xa9mak'
        make_keys = ['©mak', '\xa9mak', '©MAK', '\xa9MAK', 'make', 'Make', 'manufacturer']
        for key in make_keys:
            if key in video_file:
                try:
                    make_value = video_file[key][0] if isinstance(video_file[key], list) else video_file[key]
                    if make_value:
                        metadata['make'] = str(make_value).strip()
                        break
                except (ValueError, IndexError, AttributeError, TypeError):
                    pass

        # Если не найдена дата в метаданных, fallback на системные статистики
        if 'datetime_original' not in metadata:
            system_date = get_system_fallback_date(file_path)
            if system_date:
                metadata['datetime_original'] = system_date
        
        if metadata:
            return metadata
        else:
            return None

    except Exception as e:
        _error_logger.error(f"Video metadata extraction error for {file_path}: {e}", exc_info=False)
        # Fallback на системные статистики при ошибке, только если дата в допустимом диапазоне
        system_date = get_system_fallback_date(file_path)
        if system_date:
            return {'datetime_original': system_date}
        return None


def get_all_file_timestamps(file_path: Path) -> list[datetime]:
    """
    Получить все доступные временные метки файла из файловой системы.
    
    Краткое описание: Извлекает все доступные временные метки из файловой системы:
    - st_ctime (время изменения статуса/создания)
    - st_mtime (время модификации)
    - st_birthtime (время создания, если доступно на системе)
    
    Args:
        file_path: Path to file

    Returns:
        List of datetime objects (may be empty if stat fails)
    """
    timestamps = []
    try:
        stat = file_path.stat()
        # st_ctime - время последнего изменения статуса файла (на Linux это время создания inode)
        timestamps.append(datetime.fromtimestamp(stat.st_ctime))
        # st_mtime - время последней модификации содержимого файла
        timestamps.append(datetime.fromtimestamp(stat.st_mtime))
        # st_birthtime - время создания файла (доступно на macOS и некоторых Linux FS)
        if hasattr(stat, 'st_birthtime'):
            timestamps.append(datetime.fromtimestamp(stat.st_birthtime))
    except OSError as e:
        logger.error(f"Ошибка получения временных меток файла для {file_path}: {e}")
    
    return timestamps


def get_xmp_brute_force_date(file_path: Path) -> Optional[datetime]:
    """
    Deep scan for XMP dates using brute force binary search (Linux Style).
    
    Opens file in binary mode, reads first 512KB, and searches for date patterns
    using regex. This method finds hidden XMP dates that standard libraries miss.
    Использует pathlib.Path объекты для кроссплатформенной совместимости.
    
    Args:
        file_path: Path to image file (pathlib.Path object)
        
    Returns:
        datetime object or None if no valid date found or date is outside 2004-2026 range
    """
    MIN_DATE = datetime(2004, 1, 1)
    MAX_YEAR = 2026
    
    try:
        # Использование pathlib.Path объекта для открытия файла
        with open(file_path, 'rb') as f:
            # Read first 512KB (524288 bytes)
            data = f.read(524288)
        
        # Regex pattern for dates: YYYY:MM:DD or YYYY-MM-DD, with time
        # Pattern: (\d{4}[:\-](\d{2})[:\-](\d{2})[ T](\d{2})[:](\d{2})[:](\d{2}))
        pattern = rb'(\d{4}[:\-](\d{2})[:\-](\d{2})[ T](\d{2})[:](\d{2})[:](\d{2}))'
        
        # Use search to find first match (findall returns tuples with groups)
        match = re.search(pattern, data)
        if not match:
            return None
        
        # Extract the full match (group 0)
        date_str_bytes = match.group(0)
        
        # Convert bytes to string, handling both : and - separators
        date_str = date_str_bytes.decode('utf-8', errors='ignore')
        
        # Try different formats
        formats = [
            '%Y:%m:%d %H:%M:%S',
            '%Y-%m-%d %H:%M:%S',
            '%Y:%m:%dT%H:%M:%S',
            '%Y-%m-%dT%H:%M:%S'
        ]
        
        for fmt in formats:
            try:
                parsed_date = datetime.strptime(date_str, fmt)
                # Apply 2004-2026 year filter
                if parsed_date >= MIN_DATE and parsed_date.year <= MAX_YEAR:
                    logger.debug(f"XMP brute force found date: {parsed_date} in {file_path.name}")
                    return parsed_date
            except ValueError:
                continue
        
        return None
    except Exception as e:
        logger.debug(f"XMP brute force scan failed for {file_path}: {e}")
        return None


def get_system_fallback_date(file_path: Path) -> Optional[datetime]:
    """
    Get system fallback date using only os.path.getmtime and os.path.getctime.
    
    Args:
        file_path: Path to file
        
    Returns:
        datetime object or None if date is before 2004 or after 2026, or extraction fails
    """
    # Обновлен фильтр дат: теперь разрешен 2026 год для актуальных файлов
    MIN_DATE = datetime(2004, 1, 1)
    MAX_YEAR = 2026
    
    try:
        mtime = os.path.getmtime(str(file_path))
        ctime = os.path.getctime(str(file_path))
        system_date = datetime.fromtimestamp(min(mtime, ctime))
        
        # Filter: before 2004 or after 2026 -> return None
        if system_date < MIN_DATE or system_date.year > MAX_YEAR:
            return None
            
        return system_date
    except (OSError, ValueError) as e:
        logger.debug(f"System fallback date extraction failed for {file_path}: {e}")
        return None


def get_file_creation_time(file_path: Path) -> Optional[datetime]:
    """
    Get file creation time with updated extraction hierarchy.
    
    Extraction priority:
    1. Standard EXIF (for JPGs)
    2. Pillow Info (for PNG/General)
    3. XMP Brute Force (Deep Scan - Linux Style)
    4. System Fallback (min of ctime/mtime) - only as last resort
    
    All dates are filtered: before 2004 or after 2026 -> None.
    Обновлен фильтр дат: теперь разрешен 2026 год для актуальных файлов.
    
    IMPORTANT: If XMP scan finds 2021 and system stats say 2026, XMP date MUST win.

    Args:
        file_path: Path to file

    Returns:
        datetime object or None if date is invalid or extraction fails
    """
    # Обновлен фильтр дат: теперь разрешен 2026 год для актуальных файлов
    MIN_DATE = datetime(2004, 1, 1)
    MAX_YEAR = 2026
    
    # Priority 1: Standard EXIF extraction (for JPGs, not PNG)
    suffix_lower = file_path.suffix.lower()
    skip_exif = (suffix_lower == '.png')
    
    if ExifImage and not skip_exif:
        try:
            with open(file_path, 'rb') as image_file:
                exif_image = ExifImage(image_file)
            
            if exif_image.has_exif:
                # Try datetime_original
                if hasattr(exif_image, 'datetime_original'):
                    try:
                        dt_str = exif_image.datetime_original
                        parsed_date = datetime.strptime(dt_str, '%Y:%m:%d %H:%M:%S')
                        if parsed_date >= MIN_DATE and parsed_date.year <= MAX_YEAR:
                            return parsed_date
                    except (ValueError, AttributeError):
                        pass
                
                # Try datetime
                if hasattr(exif_image, 'datetime'):
                    try:
                        dt_str = exif_image.datetime
                        parsed_date = datetime.strptime(dt_str, '%Y:%m:%d %H:%M:%S')
                        if parsed_date >= MIN_DATE and parsed_date.year <= MAX_YEAR:
                            return parsed_date
                    except (ValueError, AttributeError):
                        pass
        except (ValueError, Exception):
            # EXIF errors are logged silently
            pass
    
    # Priority 2: Pillow Info (for PNG/General)
    if PILLOW_AVAILABLE:
        try:
            with PILImage.open(file_path) as img:
                # Check img.info
                if hasattr(img, 'info') and img.info:
                    for key, value in img.info.items():
                        if isinstance(key, str) and isinstance(value, str):
                            key_lower = key.lower()
                            if any(term in key_lower for term in ['creation_time', 'date:create', 'date', 'time']):
                                for fmt in ['%Y:%m:%d %H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d']:
                                    try:
                                        parsed_date = datetime.strptime(str(value), fmt)
                                        if parsed_date >= MIN_DATE and parsed_date.year <= MAX_YEAR:
                                            return parsed_date
                                    except ValueError:
                                        continue
                
                # Check getexif()
                try:
                    exifdata = img.getexif()
                    if exifdata:
                        for tag_id, value in exifdata.items():
                            tag = TAGS.get(tag_id, tag_id)
                            if tag == 'DateTimeOriginal' and value:
                                try:
                                    parsed_date = datetime.strptime(str(value), '%Y:%m:%d %H:%M:%S')
                                    if parsed_date >= MIN_DATE and parsed_date.year <= MAX_YEAR:
                                        return parsed_date
                                except (ValueError, TypeError):
                                    pass
                except (AttributeError, Exception):
                    pass
        except Exception:
            pass
    
    # Priority 3: XMP Brute Force (Deep Scan - Linux Style)
    # This MUST take priority over system stats if it finds a valid date
    xmp_date = get_xmp_brute_force_date(file_path)
    if xmp_date:
        return xmp_date
    
    # Priority 4: System Fallback (only as last resort)
    return get_system_fallback_date(file_path)


def get_best_timestamp(file_path: Path, metadata: Optional[Dict[str, Any]] = None) -> Optional[datetime]:
    """
    Получить лучшую (самую раннюю) временную метку из всех доступных источников.
    
    Проверка на 2004 год и уход от использования текущей даты.
    
    Краткое описание: Собирает все доступные даты из метаданных (EXIF для фото,
    заголовки медиа для видео) и файловой системы, фильтрует их по порогу 2004 года
    (чтобы отсечь системные значения по умолчанию типа 1970 или 1900) и возвращает
    самую раннюю валидную дату.
    
    Порог 2004 года выбран для фильтрации "мусорных" дат, которые могут появиться
    при сбое часов камеры или системных настройках по умолчанию.
    Обновлен фильтр дат: теперь разрешен 2026 год для актуальных файлов.
    
    ВАЖНО: НЕ использует datetime.now() или текущий год как fallback.
    Если не найдено валидной даты, возвращает None.

    Args:
        file_path: Путь к медиафайлу
        metadata: Опциональный словарь метаданных (если None, будет извлечен автоматически)

    Returns:
        datetime объект с самой ранней валидной датой или None, если не найдено ни одной
        валидной даты после 2004-01-01
    """
    file_path = Path(file_path)
    suffix_lower = file_path.suffix.lower()
    
    # Порог 2004-01-01 для фильтрации системных значений по умолчанию
    # Обновлен фильтр дат: теперь разрешен 2026 год для актуальных файлов
    MIN_DATE = datetime(2004, 1, 1)
    MAX_YEAR = 2026
    
    all_dates = []
    
    # Извлечение метаданных, если не предоставлены
    if metadata is None:
        if suffix_lower in IMAGE_EXTENSIONS:
            metadata = extract_image_metadata(file_path) or {}
        elif suffix_lower in VIDEO_EXTENSIONS:
            metadata = extract_video_metadata(file_path) or {}
        else:
            metadata = {}
    
    # Сбор всех дат из метаданных
    if 'datetime_original' in metadata and isinstance(metadata['datetime_original'], datetime):
        all_dates.append(metadata['datetime_original'])
    if 'datetime' in metadata and isinstance(metadata['datetime'], datetime):
        all_dates.append(metadata['datetime'])
    
    # Добавление системных временных меток (используем минимальное из getmtime и getctime)
    system_date = get_system_fallback_date(file_path)
    if system_date:
        all_dates.append(system_date)
    
    # Фильтрация: только даты после 2004-01-01 и до 2026 года включительно
    valid_dates = [
        dt for dt in all_dates 
        if dt is not None and isinstance(dt, datetime) and dt >= MIN_DATE and dt.year <= MAX_YEAR
    ]
    
    # Возврат самой ранней даты или None (НЕ используем datetime.now())
    if valid_dates:
        best_date = min(valid_dates)
        logger.debug(
            f"Найдена лучшая дата для {file_path.name}: {best_date.strftime('%Y-%m-%d %H:%M:%S')} "
            f"(отфильтровано {len(valid_dates)} из {len(all_dates)} временных меток)"
        )
        return best_date
    else:
        logger.warning(
            f"Не найдено валидных дат после 2004-01-01 для {file_path.name} "
            f"(найдено {len(all_dates)} временных меток, все отфильтрованы)"
        )
        return None


def extract_metadata(file_path: Path) -> Dict[str, Any]:
    """
    Extract metadata from media file (image or video) with oldest date strategy.
    
    Краткое описание: Извлекает метаданные из медиафайла (изображение или видео).
    Использует функцию get_best_timestamp для выбора самой ранней валидной даты
    с фильтрацией по порогу 2004 года. Все ошибки обрабатываются тихо, без вывода в консоль.

    Args:
        file_path: Path to media file

    Returns:
        Dictionary with metadata including datetime_original (best date found, or None)
    """
    file_path = Path(file_path)
    suffix_lower = file_path.suffix.lower()

    metadata = {}

    # Извлечение метаданных в зависимости от типа файла
    # Все ошибки обрабатываются внутри функций и логируются в файл
    try:
        if suffix_lower in IMAGE_EXTENSIONS:
            metadata = extract_image_metadata(file_path) or {}
        elif suffix_lower in VIDEO_EXTENSIONS:
            metadata = extract_video_metadata(file_path) or {}
    except Exception as e:
        # Дополнительная защита - любые неожиданные ошибки логируются в файл
        _error_logger.error(f"Metadata extraction failed for {file_path}: {e}", exc_info=False)
        metadata = {}

    # Использование get_best_timestamp для выбора лучшей даты
    # (собирает все даты из метаданных и файловой системы, фильтрует по 2004 году)
    # Если метаданные не извлечены, get_best_timestamp использует st_ctime как fallback
    try:
        best_timestamp = get_best_timestamp(file_path, metadata)
        if best_timestamp:
            metadata['datetime_original'] = best_timestamp
    except Exception as e:
        # Ошибки в get_best_timestamp также логируются тихо
        _error_logger.error(f"get_best_timestamp failed for {file_path}: {e}", exc_info=False)
    
    # Если best_timestamp == None, не устанавливаем datetime_original
    # Это позволит generate_target_path использовать fallback на "Unknown_Year"

    return metadata

