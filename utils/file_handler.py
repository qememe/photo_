"""File handling operations using pathlib."""

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from utils.error_handler import CorruptedMetadataError, handle_file_errors
from utils.metadata_extractor import get_best_timestamp

logger = logging.getLogger(__name__)


class MediaFile:
    """
    Represents a media file with source, target, and metadata.
    
    Краткое описание: Представляет медиафайл с исходным путем, целевым путем и метаданными.
    """

    def __init__(
        self,
        source_path: Path,
        target_path: Optional[Path] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize MediaFile.
        
        Краткое описание: Инициализирует объект MediaFile с исходным путем,
        опциональным целевым путем и метаданными.

        Args:
            source_path: Original file path
            target_path: Destination path after sorting
            metadata: Extracted metadata dictionary
        """
        self.source_path = Path(source_path)
        self.target_path = target_path
        self.metadata = metadata or {}

    def __repr__(self) -> str:
        return f"MediaFile(source={self.source_path}, target={self.target_path})"

    @property
    def exists(self) -> bool:
        """Check if source file exists."""
        return self.source_path.exists()

    @property
    def size(self) -> int:
        """Get file size in bytes."""
        return self.source_path.stat().st_size if self.exists else 0

    def get_earliest_timestamp(self) -> Optional[datetime]:
        """
        Получить самую раннюю временную метку из всех доступных источников.
        
        Краткое описание: Использует get_best_timestamp для получения самой ранней
        валидной даты с фильтрацией по порогу 2004 года. Собирает все даты из
        метаданных (EXIF, медиа заголовки) и файловой системы.

        Returns:
            datetime объект с самой ранней валидной датой или None, если не найдено
            ни одной валидной даты после 2004-01-01
        """
        return get_best_timestamp(self.source_path, self.metadata)


def ensure_directory(path: Path) -> None:
    """
    Create directory if it doesn't exist (safe mode: APPEND, not RECREATE).
    
    Краткое описание: Создает директорию, если она не существует.
    Создает все родительские директории при необходимости.
    Использует pathlib.mkdir(parents=True, exist_ok=True) для безопасности:
    если папка уже существует, просто использует её (режим APPEND).

    Args:
        path: Directory path to create
    """
    try:
        # Создание директории с родительскими директориями, если нужно
        # exist_ok=True гарантирует, что если папка уже существует, она просто используется
        path.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Директория обеспечена: {path}")
    except OSError as e:
        logger.error(f"Не удалось создать директорию {path}: {e}")
        raise


def compare_files(file1: Path, file2: Path) -> bool:
    """
    Compare two files by size to check if they are identical.
    
    Краткое описание: Сравнивает два файла по размеру для проверки идентичности.
    Если размеры совпадают, файлы считаются идентичными.

    Args:
        file1: First file path
        file2: Second file path

    Returns:
        True if files have same size (identical), False otherwise
    """
    try:
        if not file1.exists() or not file2.exists():
            return False
        return file1.stat().st_size == file2.stat().st_size
    except OSError:
        return False


def get_unique_filename(target_dir: Path, filename: str, source_file: Optional[Path] = None) -> Tuple[Path, bool]:
    """
    Generate unique filename if duplicate exists, with file comparison.
    
    Краткое описание: Генерирует уникальное имя файла, добавляя суффикс с номером,
    если файл с таким именем уже существует. Сравнивает файлы по размеру - если
    идентичны, возвращает флаг skip=True. Защищено от бесконечных циклов.
    
    ВАЖНО: Эта функция выполняется СИНХРОННО перед копированием/перемещением файла.
    Проверка существования файла происходит ДО операции перемещения, что гарантирует
    отсутствие конфликтов при синхронной обработке файлов.

    Args:
        target_dir: Target directory path
        filename: Original filename
        source_file: Source file path for comparison (optional)

    Returns:
        Tuple of (unique file path, skip_flag) where skip_flag=True if file already exists and is identical
    """
    target_path = target_dir / filename

    # СИНХРОННАЯ проверка: если файл не существует, возвращаем исходное имя
    # Эта проверка выполняется ДО операции копирования/перемещения
    if not target_path.exists():
        return (target_path, False)

    # Если файл существует и есть source_file для сравнения, проверяем идентичность
    if source_file and source_file.exists():
        if compare_files(source_file, target_path):
            logger.info(f"Файл уже существует (идентичен), пропускаем: {target_path.name}")
            return (target_path, True)

    # Извлекаем имя без расширения и само расширение
    stem = target_path.stem
    suffix = target_path.suffix
    counter = 1
    # Максимальное количество попыток для предотвращения бесконечного цикла
    MAX_ATTEMPTS = 100000

    # СИНХРОННЫЙ поиск уникального имени: проверяем существование и инкрементируем индекс
    # Только после нахождения уникального имени будет выполнена операция перемещения
    while target_path.exists() and counter < MAX_ATTEMPTS:
        # Если есть source_file, проверяем идентичность перед переименованием
        if source_file and source_file.exists():
            if compare_files(source_file, target_path):
                logger.info(f"Файл уже существует (идентичен), пропускаем: {target_path.name}")
                return (target_path, True)
        new_name = f"{stem}_copy_{counter}{suffix}"
        target_path = target_dir / new_name
        counter += 1

    # Проверка на достижение лимита попыток
    if counter >= MAX_ATTEMPTS:
        logger.error(f"Превышен лимит попыток поиска уникального имени для {filename}")
        raise OSError(f"Не удалось найти уникальное имя файла после {MAX_ATTEMPTS} попыток")

    logger.debug(f"Дубликат обнаружен, используется: {target_path.name}")
    return (target_path, False)


def move_file(media_file: MediaFile, verify_location: bool = True) -> Tuple[bool, bool]:
    """
    Move file from source to target location using safe copy+verify+delete pattern.
    
    Краткое описание: Безопасно перемещает файл из исходного местоположения в целевое
    используя паттерн копирование+проверка+удаление. НИКОГДА не перезаписывает существующие файлы.
    Если файл с таким именем уже существует и идентичен (по размеру), пропускает перемещение.
    Если файл существует но отличается, переименовывает новый файл с суффиксом _copy_N.
    
    ВАЖНО: Операция строго СИНХРОННАЯ. Используется shutil.copy2() для копирования,
    затем проверка существования целевого файла, и только после успешной проверки
    удаляется исходный файл. Никаких потоков, процессов или асинхронных операций не используется.
    
    КРИТИЧНО: 
    - Директория создается ПЕРЕД копированием файла для предотвращения WinError 3
    - Режим APPEND: существующие файлы и папки остаются нетронутыми
    - Удаление исходного файла происходит ТОЛЬКО после успешного копирования и проверки

    Args:
        media_file: MediaFile instance to move
        verify_location: Verify target directory exists before moving

    Returns:
        Tuple of (success: bool, skipped: bool) where skipped=True if file was skipped as duplicate
    """
    # Проверка существования исходного файла перед перемещением
    if not media_file.source_path.exists():
        logger.error(f"Исходный файл не существует: {media_file.source_path}")
        return (False, False)

    if not media_file.target_path:
        logger.error(f"Целевой путь не указан для {media_file.source_path}")
        return (False, False)

    try:
        # Обработка ошибок файла с помощью контекстного менеджера
        with handle_file_errors(media_file.source_path):
            # КРИТИЧНО: Создание целевой директории ПЕРЕД любой операцией
            # Используем pathlib.Path.mkdir(parents=True, exist_ok=True) для безопасности
            # Если папка уже существует, просто используем её (режим APPEND)
            media_file.target_path.parent.mkdir(parents=True, exist_ok=True)

            # СИНХРОННАЯ проверка и обеспечение уникальности имени файла ПЕРЕД копированием
            # Функция get_unique_filename проверяет существование файла, сравнивает размеры
            # и возвращает флаг skip=True если файл идентичен
            unique_path, should_skip = get_unique_filename(
                media_file.target_path.parent, 
                media_file.target_path.name,
                source_file=media_file.source_path
            )
            
            # Если файл уже существует и идентичен, пропускаем перемещение
            if should_skip:
                logger.info(f"Файл уже существует (идентичен), пропускаем: {media_file.source_path.name}")
                return (True, True)
            
            # Обновляем целевой путь на уникальное имя (если было переименование)
            media_file.target_path = unique_path

            # БЕЗОПАСНОЕ КОПИРОВАНИЕ: используем shutil.copy2() для сохранения метаданных
            # Это НЕ перезаписывает существующие файлы (get_unique_filename уже проверил)
            shutil.copy2(media_file.source_path, media_file.target_path)
            
            # КРИТИЧНО: Проверка существования целевого файла после копирования
            if not media_file.target_path.exists():
                logger.error(f"Целевой файл не найден после копирования: {media_file.target_path}")
                return (False, False)
            
            # Проверка размера для дополнительной безопасности
            source_size = media_file.source_path.stat().st_size
            target_size = media_file.target_path.stat().st_size
            if source_size != target_size:
                logger.error(f"Размеры файлов не совпадают после копирования: {source_size} != {target_size}")
                # Удаляем неполный целевой файл
                try:
                    media_file.target_path.unlink()
                except OSError:
                    pass
                return (False, False)
            
            # ТОЛЬКО ПОСЛЕ УСПЕШНОГО КОПИРОВАНИЯ И ПРОВЕРКИ: удаляем исходный файл
            media_file.source_path.unlink()
            
            logger.info(f"Перемещено: {media_file.source_path} -> {media_file.target_path}")
            return (True, False)

    except (PermissionError, FileExistsError, OSError) as e:
        logger.error(f"Не удалось переместить {media_file.source_path}: {e}")
        return (False, False)


def get_files_by_extension(directory: Path, extensions: tuple) -> list[Path]:
    """
    Get all files with specified extensions from directory.
    
    Краткое описание: Получает все файлы с указанными расширениями из директории
    и всех поддиректорий. Ищет как строчные, так и прописные варианты расширений.

    Args:
        directory: Directory to search
        extensions: Tuple of extensions (e.g., ('.jpg', '.png'))

    Returns:
        List of file paths
    """
    files = []
    try:
        # Поиск файлов с указанными расширениями (строчные и прописные)
        for ext in extensions:
            files.extend(directory.rglob(f"*{ext}"))
            files.extend(directory.rglob(f"*{ext.upper()}"))
        logger.debug(f"Найдено {len(files)} файлов с расширениями {extensions}")
    except OSError as e:
        logger.error(f"Ошибка сканирования директории {directory}: {e}")

    return files


def scan_directory_integrity(directory: Path, extensions: tuple) -> Tuple[int, int]:
    """
    Сканировать директорию для контроля целостности данных.
    
    Краткое описание: Сканирует директорию и все поддиректории, подсчитывает количество
    медиафайлов с указанными расширениями и вычисляет общий размер всех файлов в байтах.
    Используется для контроля целостности данных до и после сортировки.
    Использует pathlib для всех операций с размерами.

    Args:
        directory: Директория для сканирования
        extensions: Кортеж расширений файлов (например, ('.jpg', '.png', '.mp4'))

    Returns:
        Кортеж (количество_файлов, общий_размер_в_байтах)
    """
    file_count = 0
    total_size = 0
    
    try:
        if not directory.exists():
            logger.warning(f"Директория не существует: {directory}")
            return (0, 0)
        
        # Получение всех файлов с указанными расширениями
        files = get_files_by_extension(directory, extensions)
        
        # Подсчет файлов и суммирование размеров используя pathlib
        for file_path in files:
            try:
                if file_path.is_file():
                    file_count += 1
                    # Использование pathlib для получения размера
                    stat_info = file_path.stat()
                    total_size += stat_info.st_size
            except OSError as e:
                logger.warning(f"Не удалось получить размер файла {file_path}: {e}")
                # Продолжаем обработку других файлов
        
        logger.info(
            f"Сканирование целостности {directory}: найдено {file_count} файлов, "
            f"общий размер {total_size:,} байт ({total_size / (1024**2):.2f} МБ)"
        )
        
    except Exception as e:
        logger.error(f"Ошибка сканирования директории для контроля целостности {directory}: {e}")
    
    return (file_count, total_size)


def get_target_path(media_file: MediaFile, destination: Path, iphone_mode: bool = False) -> Path:
    """
    Get target path for media file based on extracted date and iPhone Mode.
    
    Краткое описание: Генерирует целевой путь для медиафайла на основе года,
    извлеченного из метаданных. Если iPhone Mode включен, сортирует только файлы
    с Apple устройств по годам, остальные перемещает в Unknown_Year/Other_Devices/.
    Если iPhone Mode выключен, использует стандартную логику сортировки по годам.

    Args:
        media_file: MediaFile instance
        destination: Destination root directory
        iphone_mode: If True, only Apple devices are sorted by year, others go to Unknown_Year/Other_Devices/

    Returns:
        Target path
    """
    # iPhone Mode filtering
    if iphone_mode:
        # Check if file is from Apple device
        make = media_file.metadata.get('make', '').strip()
        is_apple = make.lower() == 'apple'
        
        # Safety: PNG files or screenshots without Apple metadata go to Unknown_Year
        # Also check file extension for PNG
        is_png = media_file.source_path.suffix.lower() == '.png'
        
        # If not Apple device, or PNG without Apple metadata -> go to Other_Devices
        if not is_apple:
            # Non-Apple devices go to Unknown_Year/Other_Devices/
            target_dir = destination / "Unknown_Year" / "Other_Devices"
            target_path = target_dir / media_file.source_path.name
            return target_path
    
    # Standard logic: Extract year from metadata
    best_dt = media_file.get_earliest_timestamp()
    if best_dt:
        year = best_dt.year
    else:
        year = None
    
    # Use exact logic: if year is None -> "Unknown_Year", else use str(year)
    if year is None:
        target_year_folder = "Unknown_Year"
    else:
        target_year_folder = str(year)

    # Form path: destination/target_year_folder/filename
    target_dir = destination / target_year_folder
    target_path = target_dir / media_file.source_path.name

    return target_path


def get_skipped_files_size(log_file: Path = Path("skipped_files.log")) -> int:
    """
    Подсчитать общий размер пропущенных файлов из лог-файла.
    
    Краткое описание: Читает skipped_files.log и подсчитывает общий размер
    всех пропущенных файлов.

    Args:
        log_file: Путь к лог-файлу пропущенных файлов

    Returns:
        Общий размер пропущенных файлов в байтах
    """
    total_size = 0
    if log_file.exists():
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                seen_files = set()
                for line in f:
                    line = line.strip()
                    if line:
                        # Извлекаем путь к файлу (до символа |)
                        file_path_str = line.split('|')[0].strip()
                        if file_path_str and file_path_str not in seen_files:
                            seen_files.add(file_path_str)
                            try:
                                file_path = Path(file_path_str)
                                if file_path.exists() and file_path.is_file():
                                    total_size += file_path.stat().st_size
                            except (OSError, ValueError):
                                # Файл может быть удален или путь невалиден
                                pass
        except Exception as e:
            logger.warning(f"Не удалось прочитать размеры из skipped_files.log: {e}")
    
    return total_size

