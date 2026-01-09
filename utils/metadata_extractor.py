"""Metadata extraction for images and videos."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

try:
    from exif import Image as ExifImage
except ImportError:
    ExifImage = None
    logging.warning("Библиотека exif недоступна")

try:
    from mutagen import File as MutagenFile
    from mutagen.mp4 import MP4
    from mutagen.quicktime import QuickTime
except ImportError:
    MutagenFile = None
    MP4 = None
    QuickTime = None
    logging.warning("Библиотека mutagen недоступна")

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


def extract_image_metadata(file_path: Path) -> Optional[Dict[str, Any]]:
    """
    Extract EXIF metadata from image file.
    
    Краткое описание: Извлекает EXIF-метаданные из файла изображения,
    включая дату/время создания и GPS-координаты.

    Args:
        file_path: Path to image file

    Returns:
        Dictionary with metadata or None if extraction fails
    """
    if not ExifImage:
        logger.warning("Библиотека exif не установлена, невозможно извлечь метаданные изображения")
        return None

    try:
        # Открытие файла в бинарном режиме для чтения EXIF
        with open(file_path, 'rb') as image_file:
            exif_image = ExifImage(image_file)

        if not exif_image.has_exif:
            logger.debug(f"Нет EXIF-данных в {file_path.name}")
            return None

        metadata = {}

        # Извлечение даты и времени создания (datetime_original)
        if hasattr(exif_image, 'datetime_original'):
            try:
                dt_str = exif_image.datetime_original
                metadata['datetime_original'] = datetime.strptime(
                    dt_str, '%Y:%m:%d %H:%M:%S'
                )
            except (ValueError, AttributeError) as e:
                logger.debug(f"Не удалось распарсить datetime_original: {e}")

        # Извлечение других полезных полей (datetime)
        if hasattr(exif_image, 'datetime'):
            try:
                dt_str = exif_image.datetime
                metadata['datetime'] = datetime.strptime(
                    dt_str, '%Y:%m:%d %H:%M:%S'
                )
            except (ValueError, AttributeError):
                pass

        # Извлечение GPS-координат
        gps_coords = extract_gps_from_image(exif_image)
        if gps_coords:
            metadata['gps_coordinates'] = gps_coords

        logger.debug(f"Извлечены метаданные из {file_path.name}")
        return metadata

    except Exception as e:
        logger.error(f"Ошибка извлечения EXIF из {file_path}: {e}")
        return None


def extract_video_metadata(file_path: Path) -> Optional[Dict[str, Any]]:
    """
    Extract metadata from video file using mutagen.
    
    Краткое описание: Извлекает метаданные из видеофайла с помощью библиотеки mutagen,
    включая дату создания и GPS-координаты (если доступны).

    Args:
        file_path: Path to video file

    Returns:
        Dictionary with metadata or None if extraction fails
    """
    if not MutagenFile:
        logger.warning("Библиотека mutagen не установлена, невозможно извлечь метаданные видео")
        return None

    try:
        # Загрузка метаданных через mutagen
        video_file = MutagenFile(str(file_path))
        if not video_file:
            logger.debug(f"Не удалось загрузить метаданные для {file_path.name}")
            return None

        metadata = {}

        # Извлечение даты создания для MP4 файлов
        if isinstance(video_file, MP4):
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
                                    metadata['datetime_original'] = datetime.strptime(
                                        date_str_clean, fmt[:-1]
                                    )
                                else:
                                    metadata['datetime_original'] = datetime.strptime(
                                        date_str, fmt
                                    )
                                break
                            except ValueError:
                                continue
                        if 'datetime_original' in metadata:
                            break
                    except (ValueError, IndexError, AttributeError) as e:
                        logger.debug(f"Ошибка парсинга даты из {key}: {e}")

        # Извлечение даты создания для QuickTime (MOV) файлов
        elif isinstance(video_file, QuickTime):
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
                                    metadata['datetime_original'] = datetime.strptime(
                                        date_str_clean, fmt[:-1]
                                    )
                                else:
                                    metadata['datetime_original'] = datetime.strptime(
                                        date_str, fmt
                                    )
                                break
                            except ValueError:
                                continue
                        if 'datetime_original' in metadata:
                            break
                    except (ValueError, IndexError, AttributeError) as e:
                        logger.debug(f"Ошибка парсинга даты из {key}: {e}")

        # Для других форматов пытаемся найти общие ключи
        else:
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
                                    metadata['datetime_original'] = datetime.strptime(
                                        date_str_clean, fmt[:-1]
                                    )
                                else:
                                    metadata['datetime_original'] = datetime.strptime(
                                        date_str, fmt
                                    )
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

        if metadata:
            logger.debug(f"Извлечены метаданные из {file_path.name}")
            return metadata
        else:
            logger.debug(f"Метаданные не найдены в {file_path.name}")
            return None

    except Exception as e:
        logger.error(f"Ошибка извлечения метаданных видео из {file_path}: {e}")
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


def get_file_creation_time(file_path: Path) -> datetime:
    """
    Get file system creation time as fallback.
    
    Краткое описание: Получает время создания файла из файловой системы
    как резервный вариант, если метаданные недоступны.

    Args:
        file_path: Path to file

    Returns:
        datetime object
    """
    try:
        stat = file_path.stat()
        # Использование st_birthtime, если доступно (macOS, некоторые Linux), иначе st_mtime
        timestamp = getattr(stat, 'st_birthtime', stat.st_mtime)
        return datetime.fromtimestamp(timestamp)
    except OSError as e:
        logger.error(f"Ошибка получения времени создания файла для {file_path}: {e}")
        return datetime.now()


def get_best_timestamp(file_path: Path, metadata: Optional[Dict[str, Any]] = None) -> Optional[datetime]:
    """
    Получить лучшую (самую раннюю) временную метку из всех доступных источников.
    
    Краткое описание: Собирает все доступные даты из метаданных (EXIF для фото,
    заголовки медиа для видео) и файловой системы, фильтрует их по порогу 2004 года
    (чтобы отсечь системные значения по умолчанию типа 1970 или 1900) и возвращает
    самую раннюю валидную дату.
    
    Порог 2004 года выбран для фильтрации "мусорных" дат, которые могут появиться
    при сбое часов камеры или системных настройках по умолчанию.

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
    MIN_DATE = datetime(2004, 1, 1)
    
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
    
    # Добавление всех временных меток из файловой системы
    filesystem_timestamps = get_all_file_timestamps(file_path)
    all_dates.extend(filesystem_timestamps)
    
    # Фильтрация: только даты после 2004-01-01 и не None
    valid_dates = [
        dt for dt in all_dates 
        if dt is not None and isinstance(dt, datetime) and dt >= MIN_DATE
    ]
    
    # Возврат самой ранней даты или None
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
    с фильтрацией по порогу 2004 года.

    Args:
        file_path: Path to media file

    Returns:
        Dictionary with metadata including datetime_original (best date found, or None)
    """
    file_path = Path(file_path)
    suffix_lower = file_path.suffix.lower()

    metadata = {}

    # Извлечение метаданных в зависимости от типа файла
    if suffix_lower in IMAGE_EXTENSIONS:
        metadata = extract_image_metadata(file_path) or {}
    elif suffix_lower in VIDEO_EXTENSIONS:
        metadata = extract_video_metadata(file_path) or {}

    # Использование get_best_timestamp для выбора лучшей даты
    # (собирает все даты из метаданных и файловой системы, фильтрует по 2004 году)
    best_timestamp = get_best_timestamp(file_path, metadata)
    if best_timestamp:
        metadata['datetime_original'] = best_timestamp
    # Если best_timestamp == None, не устанавливаем datetime_original
    # Это позволит generate_target_path использовать fallback на "Unknown_Year"

    return metadata

