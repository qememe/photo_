"""Error handling decorators and context managers for file operations."""

import logging
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class CorruptedMetadataError(Exception):
    """
    Raised when metadata extraction fails due to corruption.
    
    Краткое описание: Исключение, возникающее при неудачном извлечении метаданных
    из-за их повреждения.
    """

    pass


@contextmanager
def handle_file_errors(file_path: Optional[Path] = None, log_file: Optional[Path] = None):
    """
    Context manager to handle file operation errors.
    
    Краткое описание: Контекстный менеджер для обработки ошибок операций с файлами.
    Логирует все ошибки и записывает пропущенные файлы в лог-файл.

    Args:
        file_path: Path to the file being processed (for logging)
        log_file: Path to log file for skipped files

    Yields:
        None

    Raises:
        PermissionError: If permission denied
        FileExistsError: If file already exists
        CorruptedMetadataError: If metadata is corrupted
    """
    skipped_log = log_file or Path("skipped_files.log")
    try:
        yield
    except PermissionError as e:
        # Обработка ошибки доступа (нет прав)
        error_msg = f"Доступ запрещен: {file_path or 'неизвестно'}"
        logger.error(error_msg)
        _log_skipped_file(skipped_log, file_path, str(e))
        raise
    except FileExistsError as e:
        # Обработка ошибки существующего файла
        error_msg = f"Файл уже существует: {file_path or 'неизвестно'}"
        logger.error(error_msg)
        _log_skipped_file(skipped_log, file_path, str(e))
        raise
    except CorruptedMetadataError as e:
        # Обработка ошибки поврежденных метаданных
        error_msg = f"Поврежденные метаданные: {file_path or 'неизвестно'}"
        logger.error(error_msg)
        _log_skipped_file(skipped_log, file_path, str(e))
        raise
    except OSError as e:
        # Обработка системных ошибок ОС
        error_msg = f"Ошибка ОС: {file_path or 'неизвестно'}: {e}"
        logger.error(error_msg)
        _log_skipped_file(skipped_log, file_path, str(e))
        raise
    except Exception as e:
        # Обработка неожиданных ошибок
        error_msg = f"Неожиданная ошибка: {file_path or 'неизвестно'}: {e}"
        logger.error(error_msg)
        _log_skipped_file(skipped_log, file_path, str(e))
        raise


def safe_file_operation(log_file: Optional[Path] = None):
    """
    Decorator to handle file operation errors.
    
    Краткое описание: Декоратор для обработки ошибок операций с файлами.
    Автоматически извлекает путь к файлу из аргументов функции.

    Args:
        log_file: Path to log file for skipped files

    Returns:
        Decorated function
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            file_path = None
            # Попытка извлечения file_path из аргументов или ключевых слов
            for arg in args:
                if isinstance(arg, Path):
                    file_path = arg
                    break
                elif hasattr(arg, 'source_path'):
                    file_path = arg.source_path
                    break

            if 'file_path' in kwargs:
                file_path = kwargs['file_path']
            elif 'media_file' in kwargs:
                file_path = kwargs['media_file'].source_path

            with handle_file_errors(file_path, log_file):
                return func(*args, **kwargs)

        return wrapper

    return decorator


def _log_skipped_file(log_file: Path, file_path: Optional[Path], error: str) -> None:
    """
    Log skipped file to log file.
    
    Краткое описание: Записывает информацию о пропущенном файле в лог-файл.

    Args:
        log_file: Path to log file
        file_path: Path to skipped file
        error: Error message
    """
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            file_str = str(file_path) if file_path else "неизвестно"
            f.write(f"{file_str} | {error}\n")
    except Exception as e:
        logger.error(f"Не удалось записать в skipped_files.log: {e}")

