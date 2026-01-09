#!/usr/bin/env python3
"""Main entry point for media sorting utility."""

# Стандартные библиотеки
import logging
import os
import platform
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# Локальные модули
from utils.error_handler import CorruptedMetadataError, handle_file_errors
from utils.file_handler import (
    MediaFile,
    get_files_by_extension,
    move_file,
)
from utils.metadata_extractor import (
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    extract_metadata,
)
from utils.report_generator import append_to_csv_report

# Попытка импорта библиотеки rich для красивого вывода в терминале
try:
    from rich.console import Console
    from rich.progress import (
        BarColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeElapsedColumn,
    )
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    logging.warning("Библиотека rich недоступна, индикаторы прогресса отключены")

# Настройка кодировки для совместимости с Windows
def setup_encoding():
    """
    Setup proper encoding for Windows CMD/PowerShell.
    
    Краткое описание: Настраивает кодировку UTF-8 для stdout и stderr,
    чтобы корректно обрабатывать Unicode-символы на системах Windows.

    Configures stdout and stderr to use UTF-8 encoding to handle
    Unicode characters properly on Windows systems.
    """
    if platform.system() == 'Windows':
        # Установка кодировки UTF-8 для stdout/stderr, если она еще не установлена
        if sys.stdout.encoding != 'utf-8':
            try:
                # Попытка переконфигурировать stdout с UTF-8
                if hasattr(sys.stdout, 'reconfigure'):
                    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
                if hasattr(sys.stderr, 'reconfigure'):
                    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
            except (AttributeError, ValueError):
                # Резервный вариант: обернуть stdout/stderr с кодировкой UTF-8
                import io
                sys.stdout = io.TextIOWrapper(
                    sys.stdout.buffer, encoding='utf-8', errors='replace'
                )
                sys.stderr = io.TextIOWrapper(
                    sys.stderr.buffer, encoding='utf-8', errors='replace'
                )


def clear_screen():
    """
    Clear screen based on operating system.
    
    Краткое описание: Очищает экран терминала в зависимости от операционной системы.

    Uses 'cls' command on Windows and 'clear' command on Unix-like systems.
    """
    if platform.system() == 'Windows':
        os.system('cls')
    else:
        os.system('clear')


# Настройка кодировки перед конфигурацией логирования
setup_encoding()

# Конфигурация логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('media_sorter.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)


def get_user_input(prompt: str, default: Optional[str] = None) -> str:
    """
    Get user input with optional default value.
    
    Краткое описание: Получает ввод от пользователя с опциональным значением по умолчанию.
    Обрабатывает проблемы с кодировкой на Windows.

    Args:
        prompt: Prompt message
        default: Default value if user presses Enter

    Returns:
        User input or default value
    """
    if default:
        full_prompt = f"{prompt} [{default}]: "
    else:
        full_prompt = f"{prompt}: "

    try:
        # Обеспечение безопасной кодировки промпта
        safe_prompt = full_prompt.encode(sys.stdout.encoding or 'utf-8', errors='replace').decode(sys.stdout.encoding or 'utf-8')
        user_input = input(safe_prompt).strip()
        return user_input if user_input else (default or "")
    except (EOFError, KeyboardInterrupt):
        logger.info("Операция отменена пользователем")
        sys.exit(0)
    except UnicodeEncodeError:
        # Резервный вариант для проблем с кодировкой
        try:
            user_input = input(full_prompt.encode('ascii', errors='replace').decode('ascii')).strip()
            return user_input if user_input else (default or "")
        except Exception:
            logger.error("Ошибка кодировки в промпте ввода")
            sys.exit(1)


def get_boolean_input(prompt: str, default: bool = True) -> bool:
    """
    Get boolean input from user.
    
    Краткое описание: Получает булево значение от пользователя (да/нет).

    Args:
        prompt: Prompt message
        default: Default value

    Returns:
        Boolean value
    """
    default_str = "Д/н" if default else "д/Н"
    response = get_user_input(f"{prompt} ({default_str})", "Д" if default else "Н")
    return response.upper().startswith("Д") or response.upper().startswith("Y")


def validate_path(path_str: str, must_exist: bool = True) -> Optional[Path]:
    """
    Validate and return Path object.
    
    Краткое описание: Валидирует и возвращает объект Path.
    Кроссплатформенная обработка путей (буквы дисков Windows, прямые/обратные слеши).

    Args:
        path_str: Path string
        must_exist: Whether path must exist

    Returns:
        Path object or None if invalid
    """
    if not path_str:
        return None

    try:
        # pathlib автоматически обрабатывает пути Windows (C:\, обратные слеши и т.д.)
        path = Path(path_str).expanduser().resolve()
        
        if must_exist and not path.exists():
            logger.error(f"Путь не существует: {path}")
            return None

        return path
    except (OSError, ValueError) as e:
        logger.error(f"Неверный путь '{path_str}': {e}")
        return None


def collect_media_files(source_dir: Path, show_progress: bool = True) -> List[MediaFile]:
    """
    Collect all media files from source directory.
    
    Краткое описание: Собирает все медиафайлы из исходной директории,
    извлекает метаданные и создает объекты MediaFile.

    Args:
        source_dir: Source directory path
        show_progress: Whether to show progress bar

    Returns:
        List of MediaFile objects
    """
    # Объединение всех поддерживаемых расширений
    all_extensions = IMAGE_EXTENSIONS + VIDEO_EXTENSIONS
    file_paths = get_files_by_extension(source_dir, all_extensions)

    media_files = []
    
    # Обработка с индикатором прогресса, если доступна библиотека rich
    if show_progress and RICH_AVAILABLE:
        console = Console()
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console
        ) as progress:
            task = progress.add_task("Сканирование файлов...", total=len(file_paths))
            for file_path in file_paths:
                try:
                    # Обработка ошибок файла с помощью контекстного менеджера
                    with handle_file_errors(file_path):
                        metadata = extract_metadata(file_path)
                        media_files.append(MediaFile(file_path, metadata=metadata))
                except (CorruptedMetadataError, Exception) as e:
                    logger.error(f"Ошибка обработки {file_path}: {e}")
                finally:
                    progress.update(task, advance=1)
    else:
        # Обработка без индикатора прогресса
        for file_path in file_paths:
            try:
                with handle_file_errors(file_path):
                    metadata = extract_metadata(file_path)
                    media_files.append(MediaFile(file_path, metadata=metadata))
            except (CorruptedMetadataError, Exception) as e:
                logger.error(f"Ошибка обработки {file_path}: {e}")

    return media_files


def generate_target_path(
    media_file: MediaFile, destination: Path, year: Optional[int] = None
) -> Path:
    """
    Generate target path for media file based on year.
    
    Краткое описание: Генерирует целевой путь для медиафайла на основе года,
    извлеченного из метаданных или текущего года.

    Args:
        media_file: MediaFile instance
        destination: Destination root directory
        year: Year for sorting (extracted from metadata if not provided)

    Returns:
        Target path
    """
    # Извлечение года из метаданных, если не указан явно
    if not year:
        dt = media_file.metadata.get('datetime_original')
        if isinstance(dt, datetime):
            year = dt.year
        else:
            # Использование текущего года, если метаданные отсутствуют
            year = datetime.now().year

    # Формирование пути: destination/год/имя_файла
    target_dir = destination / str(year)
    target_path = target_dir / media_file.source_path.name

    return target_path


def sort_media_files(
    source_dir: Path, 
    destination_dir: Path, 
    verify_location: bool = True,
    show_progress: bool = True
) -> dict:
    """
    Sort media files from source to destination by year (synchronous processing).
    
    Краткое описание: Сортирует медиафайлы из исходной директории в целевую по годам.
    Обработка строго синхронная: каждый файл полностью копируется/перемещается,
    его запись добавляется в CSV-отчет, и только затем начинается обработка следующего файла.
    Никаких потоков, процессов или асинхронных операций не используется.

    Args:
        source_dir: Source directory
        destination_dir: Destination directory
        verify_location: Verify target location before moving (enables GPS extraction)
        show_progress: Whether to show progress messages

    Returns:
        Dictionary with statistics and list of moved media files
    """
    logger.info(f"Начало сортировки медиафайлов: {source_dir} -> {destination_dir}")

    # Сбор всех медиафайлов из исходной директории
    media_files = collect_media_files(source_dir, show_progress=show_progress)
    logger.info(f"Найдено {len(media_files)} медиафайлов")

    # Инициализация статистики
    stats = {
        'total': len(media_files),
        'moved': 0,
        'failed': 0,
        'skipped': 0,
    }
    
    moved_files = []

    # Инициализация консоли для вывода прогресса
    console = Console() if (show_progress and RICH_AVAILABLE) else None

    # СИНХРОННАЯ обработка файлов: один за другим, без потоков/процессов/async
    for index, media_file in enumerate(media_files, start=1):
        try:
            # Вывод прогресса: "Processing file X of Y..."
            if show_progress:
                progress_msg = f"Обработка файла {index} из {len(media_files)}: {media_file.source_path.name}"
                if console:
                    console.print(progress_msg, style="cyan")
                else:
                    safe_print(progress_msg)

            # Генерация целевого пути на основе года
            target_path = generate_target_path(media_file, destination_dir)
            media_file.target_path = target_path

            # СИНХРОННОЕ перемещение файла (shutil операции блокирующие)
            if move_file(media_file, verify_location):
                stats['moved'] += 1
                moved_files.append(media_file)
                
                # СИНХРОННАЯ запись в CSV-отчет сразу после успешного перемещения
                # Программа ждет завершения записи перед переходом к следующему файлу
                append_to_csv_report(media_file, include_location=verify_location)
            else:
                stats['failed'] += 1

        except Exception as e:
            logger.error(f"Ошибка сортировки {media_file.source_path}: {e}")
            stats['failed'] += 1

    stats['moved_files'] = moved_files
    return stats


def safe_print(text: str) -> None:
    """
    Safely print text handling encoding issues on Windows.
    
    Краткое описание: Безопасный вывод текста с обработкой проблем кодировки на Windows.

    Args:
        text: Text to print
    """
    try:
        print(text)
    except UnicodeEncodeError:
        # Резервный вариант: кодирование в ASCII с заменой проблемных символов
        safe_text = text.encode('ascii', errors='replace').decode('ascii')
        print(safe_text)


def print_summary(source: Path, destination: Path, verify: bool, file_count: int):
    """
    Print confirmation summary before starting.
    
    Краткое описание: Выводит сводку подтверждения перед началом сортировки.

    Args:
        source: Source directory
        destination: Destination directory
        verify: Location verification flag (ready for GPS data integration)
        file_count: Number of files to process
    """
    if RICH_AVAILABLE:
        console = Console()
        console.print("\n" + "=" * 60, style="bold cyan")
        console.print("СВОДКА СОРТИРОВКИ МЕДИАФАЙЛОВ", style="bold cyan")
        console.print("=" * 60, style="bold cyan")
        console.print(f"Исходная директория:      {source}", style="white")
        console.print(f"Целевая директория:       {destination}", style="white")
        console.print(f"Проверка местоположения:  {'Да' if verify else 'Нет'} (GPS данные готовы)", style="green" if verify else "yellow")
        console.print(f"Файлов к обработке:       {file_count}", style="white")
        console.print("=" * 60 + "\n", style="bold cyan")
    else:
        safe_print("\n" + "=" * 60)
        safe_print("СВОДКА СОРТИРОВКИ МЕДИАФАЙЛОВ")
        safe_print("=" * 60)
        safe_print(f"Исходная директория:      {source}")
        safe_print(f"Целевая директория:       {destination}")
        safe_print(f"Проверка местоположения:  {'Да' if verify else 'Нет'} (GPS данные готовы)")
        safe_print(f"Файлов к обработке:       {file_count}")
        safe_print("=" * 60 + "\n")


def main():
    """
    Main CLI entry point.
    
    Краткое описание: Главная точка входа CLI-приложения для сортировки медиафайлов.
    """
    # Очистка экрана при запуске (опционально, можно удалить если не нужно)
    # clear_screen()
    
    # Инициализация консоли для rich (если доступна)
    console = Console() if RICH_AVAILABLE else None
    
    # Приветственное сообщение с использованием rich для красивого вывода
    if RICH_AVAILABLE and console:
        console.print("=" * 60, style="bold blue")
        console.print("УТИЛИТА СОРТИРОВКИ МЕДИАФАЙЛОВ", style="bold blue")
        console.print("=" * 60, style="bold blue")
        console.print()
    else:
        safe_print("=" * 60)
        safe_print("УТИЛИТА СОРТИРОВКИ МЕДИАФАЙЛОВ")
        safe_print("=" * 60)
        safe_print()

    # Получение исходной директории
    while True:
        source_str = get_user_input("Введите путь к исходной директории")
        source = validate_path(source_str, must_exist=True)
        if source and source.is_dir():
            break
        if RICH_AVAILABLE and console:
            console.print("Неверная исходная директория. Попробуйте снова.", style="bold red")
        else:
            safe_print("Неверная исходная директория. Попробуйте снова.")

    # Получение целевой директории
    while True:
        dest_str = get_user_input("Введите путь к целевой директории")
        destination = validate_path(dest_str, must_exist=False)
        if destination:
            break
        if RICH_AVAILABLE and console:
            console.print("Неверный путь к целевой директории. Попробуйте снова.", style="bold red")
        else:
            safe_print("Неверный путь к целевой директории. Попробуйте снова.")

    # Получение настройки проверки местоположения
    # Этот переключатель готов для работы с GPS-данными
    verify_location = get_boolean_input(
        "Включить проверку местоположения (GPS данные готовы)", default=True
    )

    # Сбор файлов для предпросмотра
    if RICH_AVAILABLE and console:
        console.print("\nСканирование исходной директории...", style="yellow")
    else:
        safe_print("\nСканирование исходной директории...")
    media_files = collect_media_files(source)
    file_count = len(media_files)

    if file_count == 0:
        if RICH_AVAILABLE and console:
            console.print("Медиафайлы не найдены в исходной директории.", style="bold red")
        else:
            safe_print("Медиафайлы не найдены в исходной директории.")
        sys.exit(0)

    # Показ сводки
    print_summary(source, destination, verify_location, file_count)

    # Подтверждение
    if not get_boolean_input("Продолжить сортировку?", default=True):
        if RICH_AVAILABLE and console:
            console.print("Операция отменена.", style="yellow")
        else:
            safe_print("Операция отменена.")
        sys.exit(0)

    # Выполнение сортировки (синхронная обработка с инкрементальной записью в CSV)
    # CSV-отчеты создаются инкрементально после каждого перемещенного файла
    stats = sort_media_files(source, destination, verify_location, show_progress=True)

    # Вывод результатов
    if RICH_AVAILABLE and console:
        console.print("\n" + "=" * 60, style="bold green")
        console.print("СОРТИРОВКА ЗАВЕРШЕНА", style="bold green")
        console.print("=" * 60, style="bold green")
        console.print(f"Всего файлов:        {stats['total']}", style="white")
        console.print(f"Успешно перемещено:  {stats['moved']}", style="green")
        console.print(f"Ошибок:              {stats['failed']}", style="red" if stats['failed'] > 0 else "white")
        console.print("=" * 60 + "\n", style="bold green")
    else:
        safe_print("\n" + "=" * 60)
        safe_print("СОРТИРОВКА ЗАВЕРШЕНА")
        safe_print("=" * 60)
        safe_print(f"Всего файлов:        {stats['total']}")
        safe_print(f"Успешно перемещено:  {stats['moved']}")
        safe_print(f"Ошибок:              {stats['failed']}")
        safe_print("=" * 60 + "\n")


if __name__ == "__main__":
    main()

