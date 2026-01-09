"""File handling operations using pathlib."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from utils.error_handler import CorruptedMetadataError, handle_file_errors

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


def ensure_directory(path: Path) -> None:
    """
    Create directory if it doesn't exist.
    
    Краткое описание: Создает директорию, если она не существует.
    Создает все родительские директории при необходимости.

    Args:
        path: Directory path to create
    """
    try:
        # Создание директории с родительскими директориями, если нужно
        path.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Директория обеспечена: {path}")
    except OSError as e:
        logger.error(f"Не удалось создать директорию {path}: {e}")
        raise


def get_unique_filename(target_dir: Path, filename: str) -> Path:
    """
    Generate unique filename if duplicate exists (synchronous check).
    
    Краткое описание: Генерирует уникальное имя файла, добавляя суффикс с номером,
    если файл с таким именем уже существует. Защищено от бесконечных циклов.
    
    ВАЖНО: Эта функция выполняется СИНХРОННО перед копированием/перемещением файла.
    Проверка существования файла происходит ДО операции перемещения, что гарантирует
    отсутствие конфликтов при синхронной обработке файлов.

    Args:
        target_dir: Target directory path
        filename: Original filename

    Returns:
        Unique file path
    """
    target_path = target_dir / filename

    # СИНХРОННАЯ проверка: если файл не существует, возвращаем исходное имя
    # Эта проверка выполняется ДО операции копирования/перемещения
    if not target_path.exists():
        return target_path

    # Извлекаем имя без расширения и само расширение
    stem = target_path.stem
    suffix = target_path.suffix
    counter = 1
    # Максимальное количество попыток для предотвращения бесконечного цикла
    MAX_ATTEMPTS = 100000

    # СИНХРОННЫЙ поиск уникального имени: проверяем существование и инкрементируем индекс
    # Только после нахождения уникального имени будет выполнена операция перемещения
    while target_path.exists() and counter < MAX_ATTEMPTS:
        new_name = f"{stem}_{counter}{suffix}"
        target_path = target_dir / new_name
        counter += 1

    # Проверка на достижение лимита попыток
    if counter >= MAX_ATTEMPTS:
        logger.error(f"Превышен лимит попыток поиска уникального имени для {filename}")
        raise OSError(f"Не удалось найти уникальное имя файла после {MAX_ATTEMPTS} попыток")

    logger.debug(f"Дубликат обнаружен, используется: {target_path.name}")
    return target_path


def move_file(media_file: MediaFile, verify_location: bool = True) -> bool:
    """
    Move file from source to target location (synchronous operation).
    
    Краткое описание: Перемещает файл из исходного местоположения в целевое.
    Обеспечивает уникальность имени файла и создает директории при необходимости.
    
    ВАЖНО: Операция строго СИНХРОННАЯ. Используется shutil.rename() (через pathlib),
    который блокирует выполнение до завершения перемещения. Никаких потоков,
    процессов или асинхронных операций не используется.

    Args:
        media_file: MediaFile instance to move
        verify_location: Verify target directory exists before moving

    Returns:
        True if successful, False otherwise
    """
    if not media_file.exists:
        logger.error(f"Исходный файл не существует: {media_file.source_path}")
        return False

    if not media_file.target_path:
        logger.error(f"Целевой путь не указан для {media_file.source_path}")
        return False

    try:
        # Обработка ошибок файла с помощью контекстного менеджера
        with handle_file_errors(media_file.source_path):
            # Создание целевой директории, если включена проверка местоположения
            if verify_location:
                ensure_directory(media_file.target_path.parent)

            # СИНХРОННАЯ проверка и обеспечение уникальности имени файла ПЕРЕД перемещением
            # Функция get_unique_filename проверяет существование файла и инкрементирует индекс
            # только после нахождения уникального имени выполняется операция перемещения
            media_file.target_path = get_unique_filename(
                media_file.target_path.parent, media_file.target_path.name
            )

            # СИНХРОННОЕ переименование (перемещение) файла
            # pathlib.Path.rename() - блокирующая операция, программа ждет завершения
            media_file.source_path.rename(media_file.target_path)
            logger.info(f"Перемещено: {media_file.source_path} -> {media_file.target_path}")
            return True

    except (PermissionError, FileExistsError, OSError) as e:
        logger.error(f"Не удалось переместить {media_file.source_path}: {e}")
        return False


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

