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
    get_skipped_files_size,
    move_file,
    scan_directory_integrity,
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

# Создание директории для логов
logs_dir = Path('logs')
logs_dir.mkdir(exist_ok=True)

# Конфигурация основного логирования (без вывода ошибок в консоль)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('media_sorter.log', encoding='utf-8'),
        # Убираем StreamHandler для основного логгера - консоль должна быть чистой
    ],
)

# Отдельный логгер для ошибок процесса (только в файл, не в консоль)
error_logger = logging.getLogger('process_errors')
error_logger.setLevel(logging.ERROR)
error_file_handler = logging.FileHandler(logs_dir / 'process_errors.log', encoding='utf-8')
error_file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
error_logger.addHandler(error_file_handler)
error_logger.propagate = False  # Не передавать в родительские логгеры

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


def collect_media_files(source_dir: Path, show_progress: bool = True) -> tuple[List[MediaFile], int, int]:
    """
    Collect all media files from source directory and calculate totals.
    
    Краткое описание: Собирает все медиафайлы из исходной директории,
    извлекает метаданные и создает объекты MediaFile. Одновременно подсчитывает
    общее количество файлов и общий размер для контроля целостности.
    Сканирование выполняется ОДИН РАЗ.

    Args:
        source_dir: Source directory path
        show_progress: Whether to show progress bar

    Returns:
        Tuple of (List of MediaFile objects, total_file_count, total_size_bytes)
    """
    # Объединение всех поддерживаемых расширений
    all_extensions = IMAGE_EXTENSIONS + VIDEO_EXTENSIONS
    file_paths = get_files_by_extension(source_dir, all_extensions)

    media_files = []
    total_file_count = 0
    total_size = 0
    
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
                    # Подсчет файлов и размера во время сканирования
                    if file_path.is_file():
                        total_file_count += 1
                        try:
                            total_size += file_path.stat().st_size
                        except OSError:
                            pass  # Размер не критичен, продолжаем
                    
                    # Обработка ошибок файла с помощью контекстного менеджера
                    with handle_file_errors(file_path):
                        metadata = extract_metadata(file_path)
                        media_files.append(MediaFile(file_path, metadata=metadata))
                except (CorruptedMetadataError, Exception) as e:
                    # Ошибки логируются в файл через error_logger в extract_metadata
                    pass  # Не выводим в консоль
                finally:
                    progress.update(task, advance=1)
    else:
        # Обработка без индикатора прогресса
        for file_path in file_paths:
            try:
                # Подсчет файлов и размера во время сканирования
                if file_path.is_file():
                    total_file_count += 1
                    try:
                        total_size += file_path.stat().st_size
                    except OSError:
                        pass  # Размер не критичен, продолжаем
                
                with handle_file_errors(file_path):
                    metadata = extract_metadata(file_path)
                    media_files.append(MediaFile(file_path, metadata=metadata))
            except (CorruptedMetadataError, Exception) as e:
                # Ошибки логируются в файл через error_logger в extract_metadata
                pass  # Не выводим в консоль

    return (media_files, total_file_count, total_size)


def generate_target_path(
    media_file: MediaFile, destination: Path, year: Optional[int] = None, iphone_mode: bool = False
) -> Path:
    """
    Generate target path for media file based on year and iPhone Mode.
    
    Проверка на 2004 год и уход от использования текущей даты.
    
    Краткое описание: Генерирует целевой путь для медиафайла на основе года,
    извлеченного из метаданных с использованием стратегии выбора самой ранней даты.
    Если iPhone Mode включен, сортирует только файлы с Apple устройств по годам.
    Если год не найден (extracted date is None), используется папка "Unknown_Year"
    вместо текущего года. Это гарантирует, что файлы с нулевыми метаданными
    группируются отдельно для ручной проверки, вместо смешивания с файлами 2026 года.
    Принудительное использование папки Unknown_Year для файлов без метаданных.

    Args:
        media_file: MediaFile instance
        destination: Destination root directory
        year: Year for sorting (extracted from metadata if not provided)
        iphone_mode: If True, only Apple devices are sorted by year

    Returns:
        Target path
    """
    from utils.file_handler import get_target_path as get_target_path_handler
    return get_target_path_handler(media_file, destination, iphone_mode)


def sort_media_files(
    source_dir: Path, 
    destination_dir: Path, 
    verify_location: bool = True,
    show_progress: bool = True,
    iphone_mode: bool = False
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
    media_files, total_count, total_size = collect_media_files(source_dir, show_progress=show_progress)
    logger.info(f"Найдено {len(media_files)} медиафайлов")

    # Инициализация статистики
    stats = {
        'total': len(media_files),
        'moved': 0,
        'failed': 0,
        'skipped': 0,
        'unknown_year_count': 0,  # Счетчик файлов, перемещенных в Unknown_Year
        'non_iphone_count': 0,  # Счетчик файлов не с Apple устройств (только для iPhone Mode)
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

            # Генерация целевого пути на основе года и iPhone Mode
            target_path = generate_target_path(media_file, destination_dir, iphone_mode=iphone_mode)
            media_file.target_path = target_path

            # СИНХРОННОЕ перемещение файла (shutil операции блокирующие)
            if move_file(media_file, verify_location):
                stats['moved'] += 1
                moved_files.append(media_file)
                
                # Подсчет файлов, перемещенных в Unknown_Year
                # Принудительное использование папки Unknown_Year для файлов без метаданных
                if media_file.target_path and media_file.target_path.parent.name == 'Unknown_Year':
                    stats['unknown_year_count'] += 1
                
                # Подсчет файлов не с Apple устройств (только для iPhone Mode)
                if iphone_mode and media_file.target_path:
                    # Проверка, что файл попал в Other_Devices
                    if 'Other_Devices' in str(media_file.target_path):
                        stats['non_iphone_count'] += 1
                
                # СИНХРОННАЯ запись в CSV-отчет сразу после успешного перемещения
                # Программа ждет завершения записи перед переходом к следующему файлу
                append_to_csv_report(media_file, include_location=verify_location)
            else:
                stats['failed'] += 1

        except Exception as e:
            # Ошибки логируются в файл через error_logger
            error_logger.error(f"Ошибка сортировки {media_file.source_path}: {e}", exc_info=False)
            stats['failed'] += 1

    stats['moved_files'] = moved_files
    return stats


def count_skipped_files(log_file: Path = Path("skipped_files.log")) -> int:
    """
    Подсчитать количество пропущенных файлов из лог-файла.
    
    Краткое описание: Читает skipped_files.log и подсчитывает количество
    уникальных файлов, которые были пропущены во время обработки.

    Args:
        log_file: Путь к лог-файлу пропущенных файлов

    Returns:
        Количество пропущенных файлов
    """
    skipped_count = 0
    if log_file.exists():
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                # Каждая строка содержит путь к файлу до символа |
                seen_files = set()
                for line in f:
                    line = line.strip()
                    if line:
                        # Извлекаем путь к файлу (до символа |)
                        file_path = line.split('|')[0].strip()
                        if file_path and file_path not in seen_files:
                            seen_files.add(file_path)
                            skipped_count += 1
        except Exception as e:
            logger.warning(f"Не удалось прочитать skipped_files.log: {e}")
    
    return skipped_count


def validate_integrity(
    source_dir: Path,
    destination_dir: Path,
    initial_file_count: int,
    initial_total_size: int,
    extensions: tuple
) -> dict:
    """
    Валидация целостности данных после сортировки.
    
    Краткое описание: Сканирует целевую директорию после сортировки и сравнивает
    результаты с начальными данными. Учитывает пропущенные файлы из лог-файла.
    Проверка выполняется ПОСЛЕ завершения всех синхронных операций перемещения.

    Args:
        source_dir: Исходная директория
        destination_dir: Целевая директория
        initial_file_count: Начальное количество файлов
        initial_total_size: Начальный общий размер в байтах
        extensions: Кортеж расширений файлов

    Returns:
        Словарь с результатами валидации
    """
    logger.info("Начало валидации целостности данных...")
    
    # Сканирование целевой директории (после завершения всех перемещений)
    processed_file_count, processed_total_size = scan_directory_integrity(
        destination_dir, extensions
    )
    
    # Подсчет пропущенных файлов и их размера
    skipped_count = count_skipped_files()
    skipped_files_size = get_skipped_files_size()
    
    # Расчет ожидаемых значений (с учетом пропущенных файлов)
    # Source Size == (Destination Size + Skipped Files Size)
    expected_file_count = initial_file_count - skipped_count
    expected_total_size = initial_total_size - skipped_files_size
    
    # Проверка целостности
    files_match = processed_file_count == expected_file_count
    size_match = processed_total_size == expected_total_size
    
    integrity_result = {
        'initial_file_count': initial_file_count,
        'initial_total_size': initial_total_size,
        'processed_file_count': processed_file_count,
        'processed_total_size': processed_total_size,
        'skipped_count': skipped_count,
        'skipped_files_size': skipped_files_size,
        'expected_file_count': expected_file_count,
        'expected_total_size': expected_total_size,
        'files_match': files_match,
        'size_match': size_match,
        'is_valid': files_match and size_match
    }
    
    return integrity_result


def format_size(size_bytes: int) -> str:
    """
    Форматировать размер в байтах в читаемый формат.
    
    Args:
        size_bytes: Размер в байтах
        
    Returns:
        Отформатированная строка с размером
    """
    size_gb = size_bytes / (1024 ** 3)
    size_mb = size_bytes / (1024 ** 2)
    if size_gb >= 1:
        return f"{size_gb:.2f} ГБ ({size_bytes:,} байт)"
    else:
        return f"{size_mb:.2f} МБ ({size_bytes:,} байт)"


def display_integrity_report(integrity_result: dict) -> None:
    """
    Отобразить отчет о целостности данных с использованием rich форматирования.
    
    Краткое описание: Выводит финальный отчет о целостности данных с подсветкой
    предупреждений, если обнаружены несоответствия.

    Args:
        integrity_result: Словарь с результатами валидации целостности
    """
    initial_size_str = format_size(integrity_result['initial_total_size'])
    processed_size_str = format_size(integrity_result['processed_total_size'])
    
    if RICH_AVAILABLE:
        from rich.table import Table
        
        console = Console()
        console.print("\n" + "=" * 70, style="bold blue")
        console.print("ОТЧЕТ О ЦЕЛОСТНОСТИ ДАННЫХ", style="bold blue")
        console.print("=" * 70, style="bold blue")
        
        # Создание таблицы
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Параметр", style="cyan", width=30)
        table.add_column("Значение", style="white", width=40)
        
        table.add_row("Файлов обнаружено", str(integrity_result['initial_file_count']))
        table.add_row("Файлов обработано", str(integrity_result['processed_file_count']))
        table.add_row("Файлов пропущено", str(integrity_result['skipped_count']))
        
        # Подсветка несоответствий
        files_status = "✓ Соответствует" if integrity_result['files_match'] else "⚠ НЕ СООТВЕТСТВУЕТ"
        files_style = "green" if integrity_result['files_match'] else "bold red"
        table.add_row("Проверка файлов", files_status, style=files_style)
        
        table.add_row("", "")  # Пустая строка для разделения
        
        table.add_row("Общий размер (исходный)", initial_size_str)
        table.add_row("Общий размер (обработанный)", processed_size_str)
        
        size_status = "✓ Соответствует" if integrity_result['size_match'] else "⚠ НЕ СООТВЕТСТВУЕТ"
        size_style = "green" if integrity_result['size_match'] else "bold red"
        table.add_row("Проверка размера", size_status, style=size_style)
        
        console.print(table)
        
        # Предупреждения о несоответствиях
        if not integrity_result['is_valid']:
            console.print("\n⚠ ПРЕДУПРЕЖДЕНИЕ: Обнаружены несоответствия!", style="bold yellow")
            if not integrity_result['files_match']:
                diff = integrity_result['expected_file_count'] - integrity_result['processed_file_count']
                console.print(
                    f"   • Разница в количестве файлов: {abs(diff)} "
                    f"({'недостает' if diff > 0 else 'лишних'})",
                    style="yellow"
                )
            if not integrity_result['size_match']:
                size_diff = integrity_result['expected_total_size'] - integrity_result['processed_total_size']
                console.print(
                    f"   • Разница в размере: {format_size(abs(size_diff))} "
                    f"({'недостает' if size_diff > 0 else 'лишних'})",
                    style="yellow"
                )
            console.print("   Проверьте логи для деталей.", style="yellow")
        else:
            console.print("\n✓ Целостность данных подтверждена", style="bold green")
        
        console.print("=" * 70 + "\n", style="bold blue")
    else:
        safe_print("\n" + "=" * 70)
        safe_print("ОТЧЕТ О ЦЕЛОСТНОСТИ ДАННЫХ")
        safe_print("=" * 70)
        safe_print(f"Файлов обнаружено:        {integrity_result['initial_file_count']}")
        safe_print(f"Файлов обработано:       {integrity_result['processed_file_count']}")
        safe_print(f"Файлов пропущено:        {integrity_result['skipped_count']}")
        safe_print(f"Проверка файлов:         {'✓ Соответствует' if integrity_result['files_match'] else '⚠ НЕ СООТВЕТСТВУЕТ'}")
        safe_print("")
        safe_print(f"Общий размер (исходный):  {initial_size_str}")
        safe_print(f"Общий размер (обработанный): {processed_size_str}")
        safe_print(f"Проверка размера:         {'✓ Соответствует' if integrity_result['size_match'] else '⚠ НЕ СООТВЕТСТВУЕТ'}")
        
        if not integrity_result['is_valid']:
            safe_print("\n⚠ ПРЕДУПРЕЖДЕНИЕ: Обнаружены несоответствия!")
            if not integrity_result['files_match']:
                diff = integrity_result['expected_file_count'] - integrity_result['processed_file_count']
                safe_print(f"   • Разница в количестве файлов: {abs(diff)}")
            if not integrity_result['size_match']:
                size_diff = integrity_result['expected_total_size'] - integrity_result['processed_total_size']
                safe_print(f"   • Разница в размере: {format_size(abs(size_diff))}")
        else:
            safe_print("\n✓ Целостность данных подтверждена")
        
        safe_print("=" * 70 + "\n")


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


def print_summary(
    source: Path, 
    destination: Path, 
    verify: bool, 
    file_count: int,
    total_size: int
):
    """
    Print confirmation summary before starting with integrity check data.
    
    Краткое описание: Выводит сводку подтверждения перед началом сортировки,
    включая данные контроля целостности (количество файлов и общий размер).

    Args:
        source: Source directory
        destination: Destination directory
        verify: Location verification flag (ready for GPS data integration)
        file_count: Number of files to process
        total_size: Total size of files in bytes
    """
    # Форматирование размера для отображения
    size_str = format_size(total_size)
    
    if RICH_AVAILABLE:
        console = Console()
        console.print("\n" + "=" * 60, style="bold cyan")
        console.print("СВОДКА СОРТИРОВКИ МЕДИАФАЙЛОВ", style="bold cyan")
        console.print("=" * 60, style="bold cyan")
        console.print(f"Исходная директория:      {source}", style="white")
        console.print(f"Целевая директория:       {destination}", style="white")
        console.print(f"Проверка местоположения:  {'Да' if verify else 'Нет'} (GPS данные готовы)", style="green" if verify else "yellow")
        console.print(f"Файлов к обработке:       {file_count}", style="white")
        console.print(f"Общий размер:             {size_str}", style="white")
        console.print("=" * 60 + "\n", style="bold cyan")
    else:
        safe_print("\n" + "=" * 60)
        safe_print("СВОДКА СОРТИРОВКИ МЕДИАФАЙЛОВ")
        safe_print("=" * 60)
        safe_print(f"Исходная директория:      {source}")
        safe_print(f"Целевая директория:       {destination}")
        safe_print(f"Проверка местоположения:  {'Да' if verify else 'Нет'} (GPS данные готовы)")
        safe_print(f"Файлов к обработке:       {file_count}")
        safe_print(f"Общий размер:             {size_str}")
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

    # Получение настройки iPhone Mode
    iphone_mode = get_boolean_input(
        "Включить iPhone Mode? (Сортировать только фото с Apple устройств, остальное в Unknown)", default=False
    )
    
    # Получение настройки проверки местоположения
    # Этот переключатель готов для работы с GPS-данными
    verify_location = get_boolean_input(
        "Включить проверку местоположения (GPS данные готовы)", default=True
    )

    # Сбор файлов для предпросмотра (ОДИН РАЗ - с подсчетом totals)
    if RICH_AVAILABLE and console:
        console.print("\nСканирование исходной директории...", style="yellow")
    else:
        safe_print("\nСканирование исходной директории...")
    media_files, initial_file_count, initial_total_size = collect_media_files(source)
    file_count = len(media_files)

    if file_count == 0:
        if RICH_AVAILABLE and console:
            console.print("Медиафайлы не найдены в исходной директории.", style="bold red")
        else:
            safe_print("Медиафайлы не найдены в исходной директории.")
        sys.exit(0)
    
    # Показ сводки с данными о целостности (totals уже рассчитаны в collect_media_files)
    print_summary(source, destination, verify_location, file_count, initial_total_size)
    
    # Показ информации о iPhone Mode
    if iphone_mode:
        if RICH_AVAILABLE and console:
            console.print(f"iPhone Mode: ВКЛЮЧЕН (только фото с Apple устройств будут отсортированы по годам)", style="bold yellow")
        else:
            safe_print(f"iPhone Mode: ВКЛЮЧЕН (только фото с Apple устройств будут отсортированы по годам)")

    # Подтверждение
    if not get_boolean_input("Продолжить сортировку?", default=True):
        if RICH_AVAILABLE and console:
            console.print("Операция отменена.", style="yellow")
        else:
            safe_print("Операция отменена.")
        sys.exit(0)

    # Выполнение сортировки (синхронная обработка с инкрементальной записью в CSV)
    # CSV-отчеты создаются инкрементально после каждого перемещенного файла
    # ВАЖНО: Все файлы обрабатываются синхронно, один за другим
    stats = sort_media_files(source, destination, verify_location, show_progress=True, iphone_mode=iphone_mode)
    
    # Валидация выполняется ПОСЛЕ завершения всех синхронных операций перемещения

    # Вывод результатов сортировки
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
    
    # Вывод предупреждения о файлах в Unknown_Year
    # Принудительное использование папки Unknown_Year для файлов без метаданных
    if stats.get('unknown_year_count', 0) > 0:
        unknown_count = stats['unknown_year_count']
        warning_msg = f"Внимание: {unknown_count} файлов перемещено в папку 'Unknown_Year', так как дату съемки определить не удалось."
        if RICH_AVAILABLE and console:
            console.print(warning_msg, style="bold yellow")
        else:
            safe_print(warning_msg)
    
    # Вывод информации о файлах не с Apple устройств (только для iPhone Mode)
    if iphone_mode and stats.get('non_iphone_count', 0) > 0:
        non_iphone_count = stats['non_iphone_count']
        info_msg = f"iPhone Mode: {non_iphone_count} файлов не с Apple устройств перемещено в 'Unknown_Year/Other_Devices/'."
        if RICH_AVAILABLE and console:
            console.print(info_msg, style="bold cyan")
        else:
            safe_print(info_msg)

    # Контроль целостности данных: пост-обработка валидация
    # Сравнение результатов после сортировки с начальными данными
    # Выполняется ПОСЛЕ завершения всех синхронных операций перемещения
    all_extensions = IMAGE_EXTENSIONS + VIDEO_EXTENSIONS
    integrity_result = validate_integrity(
        source,
        destination,
        initial_file_count,
        initial_total_size,
        all_extensions
    )
    
    # Отображение финального отчета о целостности данных
    display_integrity_report(integrity_result)


if __name__ == "__main__":
    main()

