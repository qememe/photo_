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

try:
    from hachoir.parser import createParser
    from hachoir.metadata import extractMetadata
    HACHOIR_AVAILABLE = True
except ImportError:
    createParser = None
    extractMetadata = None
    HACHOIR_AVAILABLE = False

try:
    from pymediainfo import MediaInfo
    PYMEDIAINFO_AVAILABLE = True
except ImportError:
    MediaInfo = None
    PYMEDIAINFO_AVAILABLE = False

try:
    from dateutil import parser as dateutil_parser
    DATEUTIL_AVAILABLE = True
except ImportError:
    dateutil_parser = None
    DATEUTIL_AVAILABLE = False

logger = logging.getLogger(__name__)

# Supported image formats
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.tiff', '.tif', '.heic', '.heif')
# Supported video formats
VIDEO_EXTENSIONS = ('.mp4', '.mov', '.avi', '.mkv', '.m4v', '.3gp', '.webm')
# Formats that should use hachoir (videos and HEIC)
HACHOIR_FORMATS = ('.mov', '.mp4', '.heic', '.heif', '.m4v')

# Date validation constants
MIN_DATE = datetime(2004, 1, 1)
# STRICT: Maximum valid year is 2025 (not current year, not 2026)
MAX_VALID_YEAR = 2025
# Invalid dates to discard (common Unix/QuickTime bugs)
INVALID_YEARS = (1904, 1970)


def is_valid_year(year: int) -> bool:
    """
    STRICT year validator. Returns True only if year is between 2004 and 2025.
    
    CRITICAL: If year >= 2026 (or current year), it is a FALSE positive.
    This prevents system stat dates (mtime/ctime) from overriding real metadata.
    
    Args:
        year: Year to validate
        
    Returns:
        True if 2004 <= year <= 2025, False otherwise
    """
    if year is None:
        return False
    if year in INVALID_YEARS:
        return False
    if year < 2004:
        return False
    if year > MAX_VALID_YEAR:
        return False
    return True


def get_date_from_filename(filename: str) -> Optional[datetime]:
    """
    Extract date from filename using regex patterns.
    
    Looks for common patterns:
    - IMG_20210818_... (Apple format)
    - 2021-08-18... (ISO format)
    - WhatsApp Video 2021-08-18...
    - YYYYMMDD or YYYY-MM-DD patterns
    
    Args:
        filename: Filename to parse
        
    Returns:
        datetime object if valid date found (2004-2025), None otherwise
    """
    # Pattern 1: IMG_YYYYMMDD_... (Apple format)
    pattern1 = r'IMG_(\d{4})(\d{2})(\d{2})'
    match = re.search(pattern1, filename)
    if match:
        try:
            year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
            if is_valid_year(year) and 1 <= month <= 12 and 1 <= day <= 31:
                parsed_date = datetime(year, month, day)
                if parsed_date >= MIN_DATE:
                    logger.debug(f"Date found in filename (IMG_ pattern): {parsed_date} from {filename}")
                    return parsed_date
        except (ValueError, TypeError):
            pass
    
    # Pattern 2: YYYY-MM-DD (ISO format)
    pattern2 = r'(\d{4})-(\d{2})-(\d{2})'
    match = re.search(pattern2, filename)
    if match:
        try:
            year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
            if is_valid_year(year) and 1 <= month <= 12 and 1 <= day <= 31:
                parsed_date = datetime(year, month, day)
                if parsed_date >= MIN_DATE:
                    logger.debug(f"Date found in filename (YYYY-MM-DD pattern): {parsed_date} from {filename}")
                    return parsed_date
        except (ValueError, TypeError):
            pass
    
    # Pattern 3: YYYYMMDD (no separators)
    pattern3 = r'(\d{4})(\d{2})(\d{2})'
    match = re.search(pattern3, filename)
    if match:
        try:
            year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
            if is_valid_year(year) and 1 <= month <= 12 and 1 <= day <= 31:
                parsed_date = datetime(year, month, day)
                if parsed_date >= MIN_DATE:
                    logger.debug(f"Date found in filename (YYYYMMDD pattern): {parsed_date} from {filename}")
                    return parsed_date
        except (ValueError, TypeError):
            pass
    
    return None


def convert_gps_coordinates(gps_latitude: tuple, gps_longitude: tuple, 
                            latitude_ref: str, longitude_ref: str) -> Optional[Tuple[float, float]]:
    """
    Convert GPS coordinates from EXIF format to Decimal Degrees.
    """
    try:
        lat_deg, lat_min, lat_sec = gps_latitude
        latitude = lat_deg + (lat_min / 60.0) + (lat_sec / 3600.0)
        if latitude_ref.upper() == 'S':
            latitude = -latitude

        lon_deg, lon_min, lon_sec = gps_longitude
        longitude = lon_deg + (lon_min / 60.0) + (lon_sec / 3600.0)
        if longitude_ref.upper() == 'W':
            longitude = -longitude

        return (latitude, longitude)
    except (ValueError, TypeError, AttributeError) as e:
        logger.debug(f"Ошибка преобразования GPS-координат: {e}")
        return None


def extract_gps_from_image(exif_image: ExifImage) -> Optional[Tuple[float, float]]:
    """Extract GPS coordinates from EXIF image."""
    try:
        if not hasattr(exif_image, 'gps_latitude') or not hasattr(exif_image, 'gps_longitude'):
            return None
        gps_latitude = exif_image.gps_latitude
        gps_longitude = exif_image.gps_longitude
        latitude_ref = getattr(exif_image, 'gps_latitude_ref', 'N')
        longitude_ref = getattr(exif_image, 'gps_longitude_ref', 'E')
        return convert_gps_coordinates(gps_latitude, gps_longitude, latitude_ref, longitude_ref)
    except Exception as e:
        logger.debug(f"Ошибка извлечения GPS из изображения: {e}")
        return None


def _parse_mediainfo_date(date_str: str) -> Optional[datetime]:
    """
    Parse date string from MediaInfo using dateutil.parser or regex fallback.
    
    Args:
        date_str: Date string from MediaInfo (e.g., "2017-11-02T09:48:07+0300")
        
    Returns:
        datetime object or None if parsing fails
    """
    if not date_str:
        return None
    
    # Try dateutil.parser first (handles ISO 8601 with timezones)
    if DATEUTIL_AVAILABLE:
        try:
            parsed = dateutil_parser.parse(date_str)
            return parsed
        except (ValueError, TypeError, AttributeError):
            pass
    
    # Fallback: manual parsing for common formats
    date_str_clean = str(date_str).strip()
    
    # Remove timezone suffixes like Z, +00:00, -05:00, +0300
    if date_str_clean.endswith('Z'):
        date_str_clean = date_str_clean[:-1]
    
    # Handle timezone offsets
    if '+' in date_str_clean:
        date_str_clean = date_str_clean.split('+')[0]
    elif 'T' in date_str_clean and date_str_clean.count('-') > 2:
        # Format: YYYY-MM-DDTHH:MM:SS-XX:XX
        parts = date_str_clean.split('T')
        if len(parts) == 2:
            time_part = parts[1]
            # Remove timezone offset from time part
            if '-' in time_part:
                time_part = time_part.split('-')[0]
            date_str_clean = f"{parts[0]}T{time_part}"
    
    # Try multiple date formats
    formats = [
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d',
        '%Y:%m:%d %H:%M:%S',
        '%Y/%m/%d %H:%M:%S',
        '%Y-%m-%dT%H:%M:%S.%f',
        '%Y-%m-%d %H:%M:%S.%f'
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str_clean, fmt)
        except ValueError:
            continue
    
    return None


def _extract_apple_creationdate_binary(file_path: Path) -> Optional[datetime]:
    """
    Binary regex fallback: Search for com.apple.quicktime.creationdate in raw bytes.
    
    This is the NUCLEAR option when pymediainfo fails to parse the tag properly.
    
    CRITICAL: QuickTime files store metadata in the 'moov' atom which can be at the
    START or END of the file. We scan BOTH locations.
    
    Pattern: ISO date YYYY-MM-DDTHH:MM:SS near 'creationdate' tag.
    
    Args:
        file_path: Path to video file
        
    Returns:
        datetime object or None
    """
    import os
    
    def search_in_data(data: bytes, source: str) -> Optional[datetime]:
        """Search for creation date in binary data."""
        # Pattern 1: ISO date format YYYY-MM-DDTHH:MM:SS
        pattern = rb'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})'
        matches = re.findall(pattern, data)
        
        for match in matches:
            date_str = match.decode('utf-8', errors='ignore')
            parsed = _parse_mediainfo_date(date_str)
            if parsed and is_valid_year(parsed.year):
                logger.info(f"[BINARY REGEX] Found ISO date in {source}: {parsed} from {file_path.name}")
                return parsed
        
        return None
    
    try:
        file_size = os.path.getsize(str(file_path))
        
        # Strategy 1: Read first 5MB (metadata at start)
        with open(file_path, 'rb') as f:
            header_data = f.read(5 * 1024 * 1024)
        
        result = search_in_data(header_data, "header")
        if result:
            return result
        
        # Strategy 2: Read last 15MB (metadata at end - common for QuickTime)
        # This is where Apple stores the moov atom for large files
        if file_size > 15 * 1024 * 1024:
            with open(file_path, 'rb') as f:
                f.seek(max(0, file_size - 15 * 1024 * 1024))
                tail_data = f.read()
            
            result = search_in_data(tail_data, "tail")
            if result:
                return result
        
        return None
    except Exception as e:
        logger.debug(f"Binary regex scan failed for {file_path}: {e}")
        return None


def extract_metadata_with_pymediainfo(file_path: Path) -> Optional[Dict[str, Any]]:
    """
    Extract metadata from file using pymediainfo (PRIMARY tool for MOV/MP4).
    
    PRIORITY ORDER:
    1. comapplequicktimecreationdate (com.apple.quicktime.creationdate)
    2. encoded_date
    3. tagged_date
    4. Any other date field
    
    STRICT: Rejects any year >= 2026 or < 2004. Returns None to force Unknown_Year.
    
    Args:
        file_path: Path to media file
        
    Returns:
        Dictionary with metadata or None if extraction fails or date is invalid
    """
    metadata = {}
    is_apple_device = False
    
    # Try pymediainfo first
    if PYMEDIAINFO_AVAILABLE:
        try:
            media_info = MediaInfo.parse(str(file_path))
            if media_info:
                best_date = None
                tag_used = None
                
                for track in media_info.tracks:
                    # PRIORITY 1: comapplequicktimecreationdate (THE KEY TAG)
                    if not best_date:
                        for attr_name in ['comapplequicktimecreationdate', 'com_apple_quicktime_creationdate']:
                            date_str = getattr(track, attr_name, None)
                            if date_str:
                                parsed_date = _parse_mediainfo_date(str(date_str))
                                if parsed_date and is_valid_year(parsed_date.year):
                                    best_date = parsed_date
                                    tag_used = attr_name
                                    logger.info(f"[PYMEDIAINFO] comapplequicktimecreationdate: {parsed_date.year} from {file_path.name}")
                                    break
                    
                    # PRIORITY 2: encoded_date
                    if not best_date:
                        date_str = getattr(track, 'encoded_date', None)
                        if date_str:
                            # Skip "UTC" only strings
                            if str(date_str).strip().upper() == 'UTC':
                                continue
                            parsed_date = _parse_mediainfo_date(str(date_str))
                            if parsed_date and is_valid_year(parsed_date.year):
                                best_date = parsed_date
                                tag_used = 'encoded_date'
                                logger.info(f"[PYMEDIAINFO] encoded_date: {parsed_date.year} from {file_path.name}")
                    
                    # PRIORITY 3: tagged_date
                    if not best_date:
                        date_str = getattr(track, 'tagged_date', None)
                        if date_str:
                            if str(date_str).strip().upper() == 'UTC':
                                continue
                            parsed_date = _parse_mediainfo_date(str(date_str))
                            if parsed_date and is_valid_year(parsed_date.year):
                                best_date = parsed_date
                                tag_used = 'tagged_date'
                                logger.info(f"[PYMEDIAINFO] tagged_date: {parsed_date.year} from {file_path.name}")
                    
                    # PRIORITY 4: Any date-related attribute
                    if not best_date:
                        for attr_name in dir(track):
                            if 'date' in attr_name.lower() and not attr_name.startswith('_'):
                                try:
                                    date_str = getattr(track, attr_name, None)
                                    if date_str and isinstance(date_str, str):
                                        if date_str.strip().upper() == 'UTC':
                                            continue
                                        parsed_date = _parse_mediainfo_date(date_str)
                                        if parsed_date and is_valid_year(parsed_date.year):
                                            best_date = parsed_date
                                            tag_used = attr_name
                                            logger.info(f"[PYMEDIAINFO] {attr_name}: {parsed_date.year} from {file_path.name}")
                                            break
                                except (AttributeError, TypeError):
                                    continue
                    
                    if best_date:
                        break
                
                # Check for Apple device indicators
                for track in media_info.tracks:
                    for attr in ['make', 'comapplequicktimemake', 'com_apple_quicktime_make']:
                        make_value = getattr(track, attr, None)
                        if make_value and 'apple' in str(make_value).lower():
                            is_apple_device = True
                            metadata['make'] = 'Apple'
                            break
                    
                    model_value = getattr(track, 'model', None) or getattr(track, 'comapplequicktimemodel', None)
                    if model_value:
                        model_str = str(model_value).lower()
                        if any(x in model_str for x in ['iphone', 'ipad', 'ipod']):
                            is_apple_device = True
                            metadata['make'] = 'Apple'
                
                if best_date:
                    metadata['datetime_original'] = best_date
                    if is_apple_device:
                        metadata['make'] = 'Apple'
                    return metadata
                    
        except Exception as e:
            logger.debug(f"pymediainfo parse failed for {file_path}: {e}")
    
    # FALLBACK: Binary regex search for com.apple.quicktime.creationdate
    binary_date = _extract_apple_creationdate_binary(file_path)
    if binary_date:
        metadata['datetime_original'] = binary_date
        metadata['make'] = 'Apple'  # If we found Apple tag, it's Apple device
        return metadata
    
    return None


def extract_metadata_with_hachoir(file_path: Path) -> Optional[Dict[str, Any]]:
    """
    Extract metadata from file using hachoir (fallback for HEIC/HEIF).
    """
    if not HACHOIR_AVAILABLE:
        return None
    
    metadata = {}
    is_apple_device = False
    
    try:
        parser = createParser(str(file_path))
        if not parser:
            return None
        
        with parser:
            hachoir_metadata = extractMetadata(parser)
            if not hachoir_metadata:
                return None
        
            creation_date = None
            
            # Try direct attributes
            for attr in ['creation_date', 'date', 'date_creation', 'creation_time']:
                if hasattr(hachoir_metadata, attr):
                    try:
                        value = getattr(hachoir_metadata, attr)
                        if value:
                            if isinstance(value, datetime):
                                if is_valid_year(value.year):
                                    creation_date = value
                                    break
                            else:
                                parsed = _parse_mediainfo_date(str(value))
                                if parsed and is_valid_year(parsed.year):
                                    creation_date = parsed
                                    break
                    except (AttributeError, TypeError):
                        continue
            
            if creation_date:
                metadata['datetime_original'] = creation_date
                logger.info(f"[HACHOIR] creation_date: {creation_date.year} from {file_path.name}")
            
            # Check for Apple device
            suffix_lower = file_path.suffix.lower()
            if suffix_lower in ('.heic', '.heif', '.mov', '.m4v'):
                is_apple_device = True
            
            if is_apple_device:
                metadata['make'] = 'Apple'
        
        return metadata if metadata else None
        
    except Exception as e:
        _error_logger.error(f"Hachoir extraction failed for {file_path}: {e}", exc_info=False)
        return None


def extract_image_metadata_with_pillow(file_path: Path) -> Optional[Dict[str, Any]]:
    """Extract metadata from image using Pillow as fallback."""
    if not PILLOW_AVAILABLE:
        return None
    
    try:
        with PILImage.open(file_path) as img:
            metadata = {}
            
            # Check img.info
            if hasattr(img, 'info') and img.info:
                for key, value in img.info.items():
                    if isinstance(key, str) and isinstance(value, str):
                        key_lower = key.lower()
                        if any(term in key_lower for term in ['creation_time', 'date:create', 'date', 'time']):
                            try:
                                for fmt in ['%Y:%m:%d %H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d']:
                                    try:
                                        parsed_date = datetime.strptime(str(value), fmt)
                                        if is_valid_year(parsed_date.year):
                                            if 'datetime_original' not in metadata:
                                                metadata['datetime_original'] = parsed_date
                                                logger.info(f"Date found via: Pillow (img.info) - {parsed_date} from {file_path.name}")
                                            break
                                    except ValueError:
                                        continue
                            except (ValueError, TypeError, AttributeError):
                                pass
            
            # Check img.getexif()
            try:
                exifdata = img.getexif()
                if exifdata:
                    for tag_id, value in exifdata.items():
                        tag = TAGS.get(tag_id, tag_id)
                        if tag == 'DateTimeOriginal' and value:
                            try:
                                parsed_date = datetime.strptime(str(value), '%Y:%m:%d %H:%M:%S')
                                if is_valid_year(parsed_date.year):
                                    metadata['datetime_original'] = parsed_date
                            except (ValueError, TypeError):
                                pass
                        elif tag == 'DateTime' and value and 'datetime_original' not in metadata:
                            try:
                                parsed_date = datetime.strptime(str(value), '%Y:%m:%d %H:%M:%S')
                                if is_valid_year(parsed_date.year):
                                    metadata['datetime'] = parsed_date
                            except (ValueError, TypeError):
                                pass
                        elif tag == 'Make' and value:
                            try:
                                metadata['make'] = str(value).strip()
                            except (ValueError, TypeError):
                                pass
            except (AttributeError, Exception):
                pass
            
            return metadata if metadata else None
    except Exception as e:
        _error_logger.error(f"Pillow extraction failed for {file_path}: {e}", exc_info=False)
        return None


def extract_image_metadata(file_path: Path) -> Optional[Dict[str, Any]]:
    """
    Extract EXIF metadata from image file with robust error handling.
    
    Extraction priority:
    1. EXIF (for JPG)
    2. Pillow (for PNG and fallback)
    3. Filename parsing
    4. XMP Brute Force
    5. System stats (ONLY if valid year 2004-2025)
    """
    metadata = {}
    
    suffix_lower = file_path.suffix.lower()
    skip_exif = (suffix_lower == '.png')
    
    if skip_exif:
        logger.info(f"PNG file detected, skipping EXIF: {file_path.name}")
    
    # Step 1: EXIF extraction (for JPG, not PNG)
    if ExifImage and not skip_exif:
        try:
            with open(file_path, 'rb') as image_file:
                exif_image = ExifImage(image_file)

            if exif_image.has_exif:
                if hasattr(exif_image, 'datetime_original'):
                    try:
                        dt_str = exif_image.datetime_original
                        parsed_date = datetime.strptime(dt_str, '%Y:%m:%d %H:%M:%S')
                        if is_valid_year(parsed_date.year):
                            metadata['datetime_original'] = parsed_date
                            logger.info(f"Date found via: EXIF - {parsed_date} from {file_path.name}")
                    except (ValueError, AttributeError):
                        pass

                if hasattr(exif_image, 'datetime') and 'datetime_original' not in metadata:
                    try:
                        dt_str = exif_image.datetime
                        parsed_date = datetime.strptime(dt_str, '%Y:%m:%d %H:%M:%S')
                        if is_valid_year(parsed_date.year):
                            metadata['datetime_original'] = parsed_date
                    except (ValueError, AttributeError):
                        pass

                gps_coords = extract_gps_from_image(exif_image)
                if gps_coords:
                    metadata['gps_coordinates'] = gps_coords
                
                if hasattr(exif_image, 'make'):
                    try:
                        make_value = exif_image.make
                        if make_value:
                            metadata['make'] = str(make_value).strip()
                    except (ValueError, AttributeError):
                        pass
                    
                if 'datetime_original' in metadata:
                    return metadata
        except ValueError as e:
            error_str = str(e).lower()
            if 'tiff' in error_str or 'byte order' in error_str:
                logger.info(f"TiffByteOrder error, trying hachoir: {file_path.name}")
                hachoir_metadata = extract_metadata_with_hachoir(file_path)
                if hachoir_metadata:
                    return hachoir_metadata
            _error_logger.error(f"EXIF extraction failed for {file_path}: {e}", exc_info=False)
        except Exception as e:
            _error_logger.error(f"EXIF extraction error for {file_path}: {e}", exc_info=False)
    
    # Step 1.5: pymediainfo for MOV/MP4, hachoir for HEIC/HEIF
    if suffix_lower in ('.mov', '.mp4', '.m4v'):
        mediainfo_metadata = extract_metadata_with_pymediainfo(file_path)
        if mediainfo_metadata:
            return mediainfo_metadata
    elif suffix_lower in ('.heic', '.heif'):
        hachoir_metadata = extract_metadata_with_hachoir(file_path)
        if hachoir_metadata:
            return hachoir_metadata
    
    # Step 2: Pillow fallback
    if not metadata and PILLOW_AVAILABLE:
        pillow_metadata = extract_image_metadata_with_pillow(file_path)
        if pillow_metadata:
            for key, value in pillow_metadata.items():
                if isinstance(value, datetime):
                    if is_valid_year(value.year):
                        metadata[key] = value
                else:
                    metadata[key] = value
            if 'datetime_original' in metadata or 'datetime' in metadata:
                return metadata
    
    # Step 3: Filename parsing
    if 'datetime_original' not in metadata and 'datetime' not in metadata:
        filename_date = get_date_from_filename(file_path.name)
        if filename_date:
            metadata['datetime_original'] = filename_date
            logger.info(f"Date found via: Filename - {filename_date} from {file_path.name}")
            return metadata
    
    # Step 4: XMP Brute Force
    if 'datetime_original' not in metadata:
        xmp_date = get_xmp_brute_force_date(file_path)
        if xmp_date:
            metadata['datetime_original'] = xmp_date
            return metadata
    
    # Step 5: System stats (ONLY if valid year - NOT 2026)
    if 'datetime_original' not in metadata:
        system_date = get_system_fallback_date(file_path)
        if system_date:
            metadata['datetime_original'] = system_date
            return metadata
    
    # Binary Apple check
    if 'make' not in metadata:
        try:
            with open(file_path, 'rb') as f:
                data = f.read(524288)
                if b'Apple' in data:
                    metadata['make'] = 'Apple'
        except Exception:
            pass
    
    return None


def extract_video_metadata(file_path: Path) -> Optional[Dict[str, Any]]:
    """
    Extract metadata from video file.
    
    PRIMARY ENGINE: pymediainfo
    CRITICAL TAG: comapplequicktimecreationdate
    
    If pymediainfo fails, falls back to binary regex search.
    
    STRICT: If year >= 2026, returns None to force Unknown_Year.
    """
    suffix_lower = file_path.suffix.lower()
    
    # PRIMARY: pymediainfo for MOV/MP4 files
    if suffix_lower in ('.mov', '.mp4', '.m4v'):
        mediainfo_metadata = extract_metadata_with_pymediainfo(file_path)
        if mediainfo_metadata and 'datetime_original' in mediainfo_metadata:
            found_date = mediainfo_metadata['datetime_original']
            if isinstance(found_date, datetime) and is_valid_year(found_date.year):
                logger.info(f"Video metadata found! Year: {found_date.year} (via MediaInfo) from {file_path.name}")
                return mediainfo_metadata
    
    # Hachoir for HEIC/HEIF files
    if suffix_lower in ('.heic', '.heif') and HACHOIR_AVAILABLE:
        hachoir_metadata = extract_metadata_with_hachoir(file_path)
        if hachoir_metadata and 'datetime_original' in hachoir_metadata:
            found_date = hachoir_metadata['datetime_original']
            if isinstance(found_date, datetime) and is_valid_year(found_date.year):
                logger.info(f"Video metadata found! Year: {found_date.year} (via Hachoir) from {file_path.name}")
                return hachoir_metadata
    
    # Plan B: Binary regex for ISO pattern
    if suffix_lower in ('.mov', '.mp4', '.m4v', '.heic', '.heif'):
        iso_date = get_video_iso_binary_date(file_path)
        if iso_date and is_valid_year(iso_date.year):
            logger.info(f"Video metadata found! Year: {iso_date.year} (via ISO binary regex) from {file_path.name}")
            return {'datetime_original': iso_date, 'make': 'Apple'}
    
    # Mutagen fallback
    if MUTAGEN_AVAILABLE:
        try:
            video_file = MutagenFile(str(file_path))
            if video_file:
                metadata = {}
                
                # Check creation_time keys
                creation_time_keys = ['creation_time', 'creationdate', 'created', 'date_created']
                for key in creation_time_keys:
                    if key in video_file:
                        try:
                            date_str = str(video_file[key][0] if isinstance(video_file[key], list) else video_file[key])
                            for fmt in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%d', '%Y:%m:%d %H:%M:%S']:
                                try:
                                    date_str_clean = date_str.rstrip('Z')
                                    parsed_date = datetime.strptime(date_str_clean, fmt.rstrip('Z'))
                                    if is_valid_year(parsed_date.year):
                                        metadata['datetime_original'] = parsed_date
                                        logger.info(f"Date found via: Mutagen ({key}) - {parsed_date} from {file_path.name}")
                                        break
                                except ValueError:
                                    continue
                            if 'datetime_original' in metadata:
                                break
                        except (ValueError, IndexError, AttributeError, TypeError):
                            continue

                # MP4 date keys
                if 'datetime_original' not in metadata and isinstance(video_file, MP4):
                    date_keys = ['©day', '\xa9day']
                    for key in date_keys:
                        if key in video_file:
                            try:
                                date_str = str(video_file[key][0])
                                for fmt in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%d']:
                                    try:
                                        date_str_clean = date_str.rstrip('Z')
                                        parsed_date = datetime.strptime(date_str_clean, fmt.rstrip('Z'))
                                        if is_valid_year(parsed_date.year):
                                            metadata['datetime_original'] = parsed_date
                                            break
                                    except ValueError:
                                        continue
                                if 'datetime_original' in metadata:
                                    break
                            except (ValueError, IndexError, AttributeError):
                                pass

                if metadata:
                    return metadata
        except Exception as e:
            _error_logger.error(f"Mutagen extraction error for {file_path}: {e}", exc_info=False)
    
    # Binary scan fallback
    binary_date = get_video_binary_date(file_path)
    if binary_date and is_valid_year(binary_date.year):
        logger.info(f"Date found via: Video Binary Scan - {binary_date} from {file_path.name}")
        return {'datetime_original': binary_date}
    
    # Filename parsing
    filename_date = get_date_from_filename(file_path.name)
    if filename_date:
        logger.info(f"Date found via: Filename - {filename_date} from {file_path.name}")
        return {'datetime_original': filename_date}
    
    # System stats - ONLY if valid year (NOT 2026)
    system_date = get_system_fallback_date(file_path)
    if system_date and is_valid_year(system_date.year):
        logger.info(f"Date found via: System Stats - {system_date} from {file_path.name}")
        return {'datetime_original': system_date}
    
    # No valid date found - return None to force Unknown_Year
    logger.warning(f"No valid date (2004-2025) found for {file_path.name} - will use Unknown_Year")
    return None


def get_all_file_timestamps(file_path: Path) -> list[datetime]:
    """Get all available file timestamps from filesystem."""
    timestamps = []
    try:
        stat = file_path.stat()
        timestamps.append(datetime.fromtimestamp(stat.st_ctime))
        timestamps.append(datetime.fromtimestamp(stat.st_mtime))
        if hasattr(stat, 'st_birthtime'):
            timestamps.append(datetime.fromtimestamp(stat.st_birthtime))
    except OSError as e:
        logger.error(f"Ошибка получения временных меток файла для {file_path}: {e}")
    
    return timestamps


def get_xmp_brute_force_date(file_path: Path) -> Optional[datetime]:
    """
    Deep scan for XMP dates using brute force binary search.
    """
    try:
        with open(file_path, 'rb') as f:
            data = f.read(524288)
        
        pattern = rb'(\d{4}[:\-](\d{2})[:\-](\d{2})[ T](\d{2})[:](\d{2})[:](\d{2}))'
        match = re.search(pattern, data)
        if not match:
            return None
        
        date_str_bytes = match.group(0)
        date_str = date_str_bytes.decode('utf-8', errors='ignore')
        
        formats = [
            '%Y:%m:%d %H:%M:%S',
            '%Y-%m-%d %H:%M:%S',
            '%Y:%m:%dT%H:%M:%S',
            '%Y-%m-%dT%H:%M:%S'
        ]
        
        for fmt in formats:
            try:
                parsed_date = datetime.strptime(date_str, fmt)
                if is_valid_year(parsed_date.year):
                    logger.info(f"Date found via: XMP Brute Force - {parsed_date} from {file_path.name}")
                    return parsed_date
            except ValueError:
                continue
        
        return None
    except Exception as e:
        logger.debug(f"XMP brute force scan failed for {file_path}: {e}")
        return None


def get_video_iso_binary_date(file_path: Path) -> Optional[datetime]:
    """
    Regex fallback: Search binary for ISO pattern YYYY-MM-DDTHH:MM:SS.
    
    Scans BOTH start and end of file (QuickTime moov atom can be at either location).
    """
    import os
    
    def find_date_in_data(data: bytes) -> Optional[datetime]:
        pattern = rb'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})'
        matches = re.findall(pattern, data)
        
        for match in matches:
            date_str = match.decode('utf-8', errors='ignore')
            date_str_clean = date_str[:19]  # YYYY-MM-DDTHH:MM:SS
            
            try:
                parsed_date = datetime.strptime(date_str_clean, '%Y-%m-%dT%H:%M:%S')
                if is_valid_year(parsed_date.year):
                    return parsed_date
            except ValueError:
                continue
        return None
    
    try:
        file_size = os.path.getsize(str(file_path))
        
        # Read first 2MB
        with open(file_path, 'rb') as f:
            header_data = f.read(2 * 1024 * 1024)
        
        result = find_date_in_data(header_data)
        if result:
            logger.info(f"Date found via: ISO Binary Regex (header) - {result} from {file_path.name}")
            return result
        
        # Read last 15MB (for large files with moov at end)
        if file_size > 15 * 1024 * 1024:
            with open(file_path, 'rb') as f:
                f.seek(max(0, file_size - 15 * 1024 * 1024))
                tail_data = f.read()
            
            result = find_date_in_data(tail_data)
            if result:
                logger.info(f"Date found via: ISO Binary Regex (tail) - {result} from {file_path.name}")
                return result
        
        return None
    except Exception as e:
        logger.debug(f"ISO binary regex scan failed for {file_path}: {e}")
        return None


def get_video_binary_date(file_path: Path) -> Optional[datetime]:
    """
    Deep scan for video file dates using binary search.
    
    Scans BOTH start and end of file (QuickTime moov atom can be at either location).
    """
    import os
    
    def find_date_in_data(data: bytes) -> Optional[datetime]:
        # Pattern 1: Standard date format YYYY:MM:DD HH:MM:SS or YYYY-MM-DD HH:MM:SS
        pattern1 = rb'(\d{4}[:\-]\d{2}[:\-]\d{2}[ T]\d{2}:\d{2}:\d{2})'
        matches = re.findall(pattern1, data)
        
        formats = ['%Y:%m:%d %H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y:%m:%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S']
        
        for match in matches:
            date_str = match.decode('utf-8', errors='ignore')
            for fmt in formats:
                try:
                    parsed_date = datetime.strptime(date_str, fmt)
                    if is_valid_year(parsed_date.year):
                        return parsed_date
                except ValueError:
                    continue
        return None
    
    try:
        logger.info(f"Deep scanning video file for hidden timestamps: {file_path.name}")
        file_size = os.path.getsize(str(file_path))
        
        # Read first 2MB
        with open(file_path, 'rb') as f:
            header_data = f.read(2 * 1024 * 1024)
        
        result = find_date_in_data(header_data)
        if result:
            logger.info(f"Date found via: Video Binary Scan (header) - {result} from {file_path.name}")
            return result
        
        # Read last 15MB
        if file_size > 15 * 1024 * 1024:
            with open(file_path, 'rb') as f:
                f.seek(max(0, file_size - 15 * 1024 * 1024))
                tail_data = f.read()
            
            result = find_date_in_data(tail_data)
            if result:
                logger.info(f"Date found via: Video Binary Scan (tail) - {result} from {file_path.name}")
                return result
        
        return None
    except Exception as e:
        logger.debug(f"Video binary scan failed for {file_path}: {e}")
        return None


def get_system_fallback_date(file_path: Path) -> Optional[datetime]:
    """
    Get system fallback date using only os.path.getmtime and os.path.getctime.
    
    STRICT: If year >= 2026, returns None (not valid).
    """
    try:
        mtime = os.path.getmtime(str(file_path))
        ctime = os.path.getctime(str(file_path))
        system_date = datetime.fromtimestamp(min(mtime, ctime))
        
        # STRICT: Only return if year is valid (2004-2025)
        if is_valid_year(system_date.year):
            return system_date
        else:
            logger.debug(f"System date rejected (year {system_date.year} not in 2004-2025): {file_path.name}")
            return None
    except (OSError, ValueError) as e:
        logger.debug(f"System fallback date extraction failed for {file_path}: {e}")
        return None


def get_file_creation_time(file_path: Path) -> Optional[datetime]:
    """
    Get file creation time with updated extraction hierarchy.
    """
    suffix_lower = file_path.suffix.lower()
    skip_exif = (suffix_lower == '.png')
    
    if ExifImage and not skip_exif:
        try:
            with open(file_path, 'rb') as image_file:
                exif_image = ExifImage(image_file)
            
            if exif_image.has_exif:
                if hasattr(exif_image, 'datetime_original'):
                    try:
                        dt_str = exif_image.datetime_original
                        parsed_date = datetime.strptime(dt_str, '%Y:%m:%d %H:%M:%S')
                        if is_valid_year(parsed_date.year):
                            return parsed_date
                    except (ValueError, AttributeError):
                        pass
                
                if hasattr(exif_image, 'datetime'):
                    try:
                        dt_str = exif_image.datetime
                        parsed_date = datetime.strptime(dt_str, '%Y:%m:%d %H:%M:%S')
                        if is_valid_year(parsed_date.year):
                            return parsed_date
                    except (ValueError, AttributeError):
                        pass
        except (ValueError, Exception):
            pass
    
    if PILLOW_AVAILABLE:
        try:
            with PILImage.open(file_path) as img:
                if hasattr(img, 'info') and img.info:
                    for key, value in img.info.items():
                        if isinstance(key, str) and isinstance(value, str):
                            key_lower = key.lower()
                            if any(term in key_lower for term in ['creation_time', 'date:create', 'date', 'time']):
                                for fmt in ['%Y:%m:%d %H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d']:
                                    try:
                                        parsed_date = datetime.strptime(str(value), fmt)
                                        if is_valid_year(parsed_date.year):
                                            return parsed_date
                                    except ValueError:
                                        continue
                
                try:
                    exifdata = img.getexif()
                    if exifdata:
                        for tag_id, value in exifdata.items():
                            tag = TAGS.get(tag_id, tag_id)
                            if tag == 'DateTimeOriginal' and value:
                                try:
                                    parsed_date = datetime.strptime(str(value), '%Y:%m:%d %H:%M:%S')
                                    if is_valid_year(parsed_date.year):
                                        return parsed_date
                                except (ValueError, TypeError):
                                    pass
                except (AttributeError, Exception):
                    pass
        except Exception:
            pass
    
    xmp_date = get_xmp_brute_force_date(file_path)
    if xmp_date:
        return xmp_date
    
    return get_system_fallback_date(file_path)


def get_best_timestamp(file_path: Path, metadata: Optional[Dict[str, Any]] = None) -> Optional[datetime]:
    """
    Get best (earliest) timestamp from all available sources.
    
    STRICT: Only accepts years 2004-2025. Returns None for invalid years.
    """
    file_path = Path(file_path)
    suffix_lower = file_path.suffix.lower()
    
    all_dates = []
    
    if metadata is None:
        if suffix_lower in IMAGE_EXTENSIONS:
            metadata = extract_image_metadata(file_path) or {}
        elif suffix_lower in VIDEO_EXTENSIONS:
            metadata = extract_video_metadata(file_path) or {}
        else:
            metadata = {}
    
    if 'datetime_original' in metadata and isinstance(metadata['datetime_original'], datetime):
        all_dates.append(metadata['datetime_original'])
    if 'datetime' in metadata and isinstance(metadata['datetime'], datetime):
        all_dates.append(metadata['datetime'])
    
    system_date = get_system_fallback_date(file_path)
    if system_date:
        all_dates.append(system_date)
    
    # STRICT filter: only 2004-2025
    valid_dates = [dt for dt in all_dates if dt and is_valid_year(dt.year)]
    
    if valid_dates:
        best_date = min(valid_dates)
        logger.debug(f"Best date for {file_path.name}: {best_date.strftime('%Y-%m-%d %H:%M:%S')}")
        return best_date
    else:
        logger.warning(f"No valid dates (2004-2025) found for {file_path.name}")
        return None


def extract_metadata(file_path: Path) -> Dict[str, Any]:
    """
    Extract metadata from media file (image or video) with oldest date strategy.
    
    Returns dictionary with metadata. If no valid date found, datetime_original
    will be None or missing, which will cause the file to go to Unknown_Year.
    """
    file_path = Path(file_path)
    suffix_lower = file_path.suffix.lower()

    metadata = {}

    try:
        if suffix_lower in IMAGE_EXTENSIONS:
            metadata = extract_image_metadata(file_path) or {}
        elif suffix_lower in VIDEO_EXTENSIONS:
            metadata = extract_video_metadata(file_path) or {}
    except Exception as e:
        _error_logger.error(f"Metadata extraction failed for {file_path}: {e}", exc_info=False)
        metadata = {}

    try:
        best_timestamp = get_best_timestamp(file_path, metadata)
        if best_timestamp:
            metadata['datetime_original'] = best_timestamp
    except Exception as e:
        _error_logger.error(f"get_best_timestamp failed for {file_path}: {e}", exc_info=False)

    return metadata
