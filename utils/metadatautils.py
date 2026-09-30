"""
Utilities for embedding, reading, and verifying metadata in MP3 files.

This module provides functions for:
- Embedding ID3 tags into MP3 files using mutagen
- Reading existing metadata from MP3 files
- Verifying metadata completeness
- Exporting/importing metadata as JSON
- Batch processing operations
"""
import json
import os
from collections import OrderedDict
import threading
from typing import Optional

try:
    import mutagen.mp3
    from mutagen.id3 import ID3, TIT2, TPE1, TALB, TRCK, TPOS, TDRC, TSRC, TCON, TPUB, TCOP, APIC
    import mutagen.id3
    from mutagen.mp4 import MP4, MP4Cover
    from mutagen.flac import FLAC, Picture
    import base64
except ImportError:
    # mutagen not installed - will be handled at runtime
    mutagen = None

import requests
from utils.logutils import get_logger
from utils.fileutils import sanitize_path_component

logger = get_logger(__name__)

_art_cache = OrderedDict()
_art_cache_lock = threading.Lock()
_ART_CACHE_LIMIT = 64


def _get_album_art(url):
    """Fetch each cached URL once, including concurrent requests for one album."""
    with _art_cache_lock:
        if url in _art_cache:
            _art_cache.move_to_end(url)
            return _art_cache[url]
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.content
        if data.startswith(b'\x89PNG\r\n\x1a\n'):
            mime = 'image/png'
        elif data.startswith(b'\xff\xd8\xff'):
            mime = 'image/jpeg'
        else:
            mime = response.headers.get('Content-Type', '').split(';')[0].strip().lower()
            if mime not in ('image/jpeg', 'image/png'):
                return None
        _art_cache[url] = (data, mime)
        if len(_art_cache) > _ART_CACHE_LIMIT:
            _art_cache.popitem(last=False)
        return data, mime


def read_duration(file_path: str) -> float | None:
    """Return audio duration in seconds, or None for unreadable audio."""
    if mutagen is None:
        return None
    try:
        return float(mutagen.File(file_path).info.length)
    except Exception:
        return None


def has_basic_tags(file_path: str) -> bool:
    """True iff the file has title and artist tags in its native tag format."""
    if mutagen is None:
        return False
    try:
        audio = mutagen.File(file_path)
        tags = audio.tags
        keys = ('TIT2', 'TPE1') if isinstance(tags, ID3) else (
            ('\xa9nam', '\xa9ART') if isinstance(audio, MP4) else ('title', 'artist'))
        return tags is not None and all(key in tags for key in keys)
    except Exception:
        return False


def embed_metadata(file_path: str, song, embed_art: bool = False) -> bool:
    """
    Embed song metadata into supported audio files in their native tag format.

    Args:
        file_path: Path to the MP3 file
        song: Song object with metadata
        embed_art: Whether to download and embed album art

    Returns:
        True if successful, False otherwise
    """
    if mutagen is None:
        logger.error("mutagen library is not installed. Cannot embed metadata.")
        return False

    try:
        audio = mutagen.File(file_path)
        if audio is None:
            raise ValueError("Unrecognised audio file")
        if audio.tags is None:
            audio.add_tags()

        # Basic metadata
        metadata = song.to_metadata_dict()
        if not isinstance(audio.tags, ID3):
            return _embed_native_metadata(audio, metadata, embed_art, song)

        if metadata.get('title'):
            audio.tags.add(TIT2(encoding=3, text=metadata['title']))
        if metadata.get('artist'):
            audio.tags.add(TPE1(encoding=3, text=metadata['artist']))
        if metadata.get('album'):
            audio.tags.add(TALB(encoding=3, text=metadata['album']))
        if metadata.get('track_number'):
            track_str = str(metadata['track_number'])
            audio.tags.add(TRCK(encoding=3, text=track_str))
        if metadata.get('disc_number'):
            disc_str = str(metadata['disc_number'])
            audio.tags.add(TPOS(encoding=3, text=disc_str))
        if metadata.get('date'):
            audio.tags.add(TDRC(encoding=3, text=metadata['date']))
        if metadata.get('isrc'):
            audio.tags.add(TSRC(encoding=3, text=metadata['isrc']))
        if metadata.get('genres'):
            genres = metadata['genres']
            if genres:
                audio.tags.add(TCON(encoding=3, text=genres[0]))
        if metadata.get('label'):
            audio.tags.add(TPUB(encoding=3, text=metadata['label']))
        if metadata.get('copyright'):
            audio.tags.add(TCOP(encoding=3, text=metadata['copyright']))

        # Embed album art if requested and URL is available
        if embed_art and metadata.get('album_art_url'):
            try:
                art = _get_album_art(metadata['album_art_url'])
                if art is not None:
                    data, mime = art
                    audio.tags.delall("APIC")
                    audio.tags.add(APIC(
                        encoding=3, mime=mime, type=3, desc='Cover', data=data
                    ))
                    logger.debug(f"Embedded album art for {song.name}")
            except Exception as e:
                logger.warning(f"Failed to download album art for {song.name}: {e}")

        # Save the changes
        audio.save(v2_version=3)
        logger.debug(f"Embedded metadata for {song.name} into {file_path}")
        return True

    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
        return False
    except Exception as e:
        logger.error(f"Failed to embed metadata in {file_path}: {e}")
        return False


_NATIVE_KEYS = {
    'title': ('title', '\xa9nam'), 'artist': ('artist', '\xa9ART'),
    'album': ('album', '\xa9alb'), 'date': ('date', '\xa9day'),
    'track_number': ('tracknumber', 'trkn'), 'disc_number': ('discnumber', 'disk'),
    'isrc': ('isrc', '----:com.apple.iTunes:ISRC'),
    'genre': ('genre', '\xa9gen'), 'label': ('label', '----:com.apple.iTunes:LABEL'),
    'copyright': ('copyright', 'cprt'),
}


def _embed_native_metadata(audio, metadata, embed_art, song):
    mp4 = isinstance(audio, MP4)
    for field, keys in _NATIVE_KEYS.items():
        value = metadata.get('genres') if field == 'genre' else metadata.get(field)
        if not value:
            continue
        key = keys[1 if mp4 else 0]
        if mp4 and field in ('track_number', 'disc_number'):
            audio.tags[key] = [(int(value), 0)]
        elif mp4 and key.startswith('----:'):
            audio.tags[key] = [str(value).encode('utf-8')]
        else:
            audio.tags[key] = [str(item) for item in value] if isinstance(value, list) else [str(value)]
    if embed_art and metadata.get('album_art_url'):
        try:
            art = _get_album_art(metadata['album_art_url'])
            if art is not None:
                data, mime = art
                if mp4:
                    imageformat = MP4Cover.FORMAT_PNG if mime == 'image/png' else MP4Cover.FORMAT_JPEG
                    audio.tags['covr'] = [MP4Cover(data, imageformat=imageformat)]
                else:
                    picture = Picture()
                    picture.type, picture.mime, picture.desc, picture.data = 3, mime, 'Cover', data
                    if isinstance(audio, FLAC):
                        audio.clear_pictures()
                        audio.add_picture(picture)
                    else:
                        audio.tags['metadata_block_picture'] = [
                            base64.b64encode(picture.write()).decode('ascii')]
        except Exception as error:
            logger.warning(f"Failed to download album art for {song.name}: {error}")
    audio.save()
    return True


def _read_native_metadata(audio):
    metadata = {}
    if audio.tags is None:
        return metadata
    mp4 = isinstance(audio, MP4)
    for field, keys in _NATIVE_KEYS.items():
        values = audio.tags.get(keys[1 if mp4 else 0])
        if not values:
            continue
        value = values[0]
        if field in ('track_number', 'disc_number'):
            try:
                value = int(value[0] if isinstance(value, tuple) else str(value).split('/')[0])
            except (ValueError, TypeError, IndexError):
                continue
        else:
            value = value.decode('utf-8', errors='replace') if isinstance(value, bytes) else str(value)
        metadata[field] = value
    return metadata


def read_metadata(file_path: str) -> dict:
    """
    Read ID3 metadata from an MP3 file.

    Args:
        file_path: Path to the MP3 file

    Returns:
        Dictionary containing the metadata fields
    """
    if mutagen is None:
        logger.error("mutagen library is not installed. Cannot read metadata.")
        return {}

    try:
        audio = mutagen.File(file_path)
        if audio is None:
            return {}
        metadata = {}
        if not isinstance(audio.tags, ID3):
            return _read_native_metadata(audio)

        if audio.tags:
            # Map ID3 frames to metadata keys
            frame_mapping = {
                'TIT2': 'title',
                'TPE1': 'artist',
                'TALB': 'album',
                'TRCK': 'track_number',
                'TPOS': 'disc_number',
                'TDRC': 'date',
                'TSRC': 'isrc',
                'TCON': 'genre',
                'TPUB': 'label',
                'TCOP': 'copyright',
            }

            for frame_id, key in frame_mapping.items():
                frame = audio.tags.get(frame_id)
                if frame:
                    # Handle track_number format (e.g., "5/12")
                    value = str(frame.text[0])
                    if key in ('track_number', 'disc_number'):
                        try:
                            value = int(value.split('/')[0])
                        except (ValueError, TypeError):
                            continue
                    metadata[key] = value

        return metadata

    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
        return {}
    except Exception as e:
        logger.error(f"Failed to read metadata from {file_path}: {e}")
        return {}


def verify_metadata(file_path: str, song) -> tuple[bool, list]:
    """
    Verify that an MP3 file has all expected metadata from the Song object.

    Args:
        file_path: Path to the MP3 file
        song: Song object with expected metadata

    Returns:
        Tuple of (is_complete, missing_fields)
    """
    file_metadata = read_metadata(file_path)
    expected = song.to_metadata_dict()

    # Key fields to verify (optional fields like album art excluded)
    required_fields = ['title', 'artist', 'album']
    optional_fields = ['track_number', 'disc_number', 'date', 'isrc']

    missing = []

    for field in required_fields:
        if expected.get(field) and field not in file_metadata:
            missing.append(field)

    for field in optional_fields:
        if expected.get(field) and field not in file_metadata:
            missing.append(field)

    is_complete = len(missing) == 0
    return is_complete, missing


def export_metadata_to_json(song, mp3_path: str) -> bool:
    """
    Export song metadata to a JSON sidecar file.

    Args:
        song: Song object with metadata
        mp3_path: Path to the MP3 file (JSON will be named similarly)

    Returns:
        True if successful, False otherwise
    """
    try:
        json_path = os.path.splitext(mp3_path)[0] + '.json'

        metadata = {
            'name': song.name,
            'artist': song.artist,
            'url': song.url,
            'track_id': song.track_id,
            'album': song.album,
            'album_art_url': song.album_art_url,
            'release_date': song.release_date,
            'duration_ms': song.duration_ms,
            'track_number': song.track_number,
            'disc_number': song.disc_number,
            'isrc': song.isrc,
            'explicit': song.explicit,
            'popularity': song.popularity,
            'all_artists': song.all_artists,
            'genres': song.genres,
            'album_id': song.album_id,
            'album_type': song.album_type,
            'label': song.label,
            'copyright_text': song.copyright_text,
        }

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        logger.debug(f"Exported metadata to {json_path}")
        return True

    except Exception as e:
        logger.error(f"Failed to export metadata to JSON: {e}")
        return False


def export_playlist_metadata(playlist, download_path: str) -> bool:
    """
    Export entire playlist metadata to a JSON file.

    Args:
        playlist: Playlist object
        download_path: Directory where JSON will be saved

    Returns:
        True if successful, False otherwise
    """
    try:
        playlist_data = {
            'name': playlist.name,
            'url': playlist.url,
            'songs': []
        }

        for song in playlist.songs:
            song_data = {
                'name': song.name,
                'artist': song.artist,
                'url': song.url,
                'track_id': song.track_id,
                'album': song.album,
                'release_date': song.release_date,
                'duration_ms': song.duration_ms,
                'track_number': song.track_number,
                'isrc': song.isrc,
            }
            playlist_data['songs'].append(song_data)

        json_path = os.path.join(download_path, f"{sanitize_path_component(playlist.name)}.json")

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(playlist_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Exported playlist metadata to {json_path}")
        return True

    except Exception as e:
        logger.error(f"Failed to export playlist metadata: {e}")
        return False


def import_metadata_from_json(json_path: str) -> Optional['Song']:
    """
    Import song metadata from a JSON file and create a Song object.

    Args:
        json_path: Path to the JSON metadata file

    Returns:
        Song object or None if import fails
    """
    from model.song import Song

    if not os.path.exists(json_path):
        logger.error(f"JSON file not found: {json_path}")
        return None

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)

        song = Song(
            name=metadata.get('name'),
            artist=metadata.get('artist'),
            url=metadata.get('url'),
            track_id=metadata.get('track_id'),
            album=metadata.get('album'),
            album_art_url=metadata.get('album_art_url'),
            release_date=metadata.get('release_date'),
            duration_ms=metadata.get('duration_ms'),
            track_number=metadata.get('track_number'),
            disc_number=metadata.get('disc_number'),
            isrc=metadata.get('isrc'),
            explicit=metadata.get('explicit'),
            popularity=metadata.get('popularity'),
            all_artists=metadata.get('all_artists'),
            genres=metadata.get('genres'),
            album_id=metadata.get('album_id'),
            album_type=metadata.get('album_type'),
            label=metadata.get('label'),
            copyright_text=metadata.get('copyright_text'),
        )

        logger.debug(f"Imported metadata from {json_path}")
        return song

    except Exception as e:
        logger.error(f"Failed to import metadata from {json_path}: {e}")
        return None


def batch_embed_metadata(songs: list, file_mappings: dict[str, str], embed_art: bool = False) -> dict:
    """
    Embed metadata for multiple songs.

    Args:
        songs: List of Song objects
        file_mappings: Dictionary mapping track_id to file path
        embed_art: Whether to embed album art

    Returns:
        Dictionary with 'success', 'failed', and 'errors' keys
    """
    results = {'success': 0, 'failed': 0, 'errors': []}

    for song in songs:
        if song.track_id and song.track_id in file_mappings:
            file_path = file_mappings[song.track_id]
            if embed_metadata(file_path, song, embed_art=embed_art):
                results['success'] += 1
            else:
                results['failed'] += 1
                results['errors'].append(f"{song.name}: Failed to embed metadata")
        else:
            results['failed'] += 1
            results['errors'].append(f"{song.name}: No file path mapping found")

    return results


def batch_verify_metadata(songs: list, directory: str) -> dict:
    """
    Verify metadata for multiple songs in a directory.

    Args:
        songs: List of Song objects
        directory: Directory containing MP3 files

    Returns:
        Dictionary with 'complete', 'incomplete', and 'missing_fields' keys
    """
    results = {'complete': 0, 'incomplete': 0, 'missing_fields': {}}

    for song in songs:
        # Try to find the file
        file_path = None
        if os.path.exists(directory):
            # Look for file matching pattern
            for filename in os.listdir(directory):
                if song.track_id and song.track_id in filename:
                    file_path = os.path.join(directory, filename)
                    break

        if file_path:
            is_complete, missing = verify_metadata(file_path, song)
            if is_complete:
                results['complete'] += 1
            else:
                results['incomplete'] += 1
                results['missing_fields'][song.name] = missing
        else:
            results['incomplete'] += 1
            results['missing_fields'][song.name] = ['File not found']

    return results


