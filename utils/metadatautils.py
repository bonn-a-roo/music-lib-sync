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
from typing import Optional

try:
    import mutagen.mp3
    from mutagen.id3 import ID3, TIT2, TPE1, TALB, TRCK, TPOS, TDRC, TSRC, TCON, TYER, TPUB, TCOP, APIC
    import mutagen.id3
except ImportError:
    # mutagen not installed - will be handled at runtime
    mutagen = None

import requests
from utils.logutils import get_logger

logger = get_logger(__name__)


def embed_metadata(file_path: str, song, embed_art: bool = False) -> bool:
    """
    Embed song metadata into an MP3 file as ID3 tags.

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
        # Load the MP3 file
        audio = mutagen.mp3.MP3(file_path)

        # Add ID3 tag if it doesn't exist
        if audio.tags is None:
            audio.tags = mutagen.id3.ID3()

        # Basic metadata
        metadata = song.to_metadata_dict()

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
        elif metadata.get('date'):
            # Also add TYER for older players
            audio.tags.add(TYER(encoding=3, text=str(metadata['date'][:4])))
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
                response = requests.get(metadata['album_art_url'], timeout=10)
                if response.status_code == 200:
                    # Remove existing APIC frames
                    audio.tags.delall("APIC")
                    # Add new album art
                    audio.tags.add(APIC(
                        encoding=3,
                        mime='image/jpeg',
                        type=3,  # Cover front
                        desc='Cover',
                        data=response.content
                    ))
                    logger.debug(f"Embedded album art for {song.name}")
            except Exception as e:
                logger.warning(f"Failed to download album art for {song.name}: {e}")

        # Save the changes
        audio.save()
        logger.debug(f"Embedded metadata for {song.name} into {file_path}")
        return True

    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
        return False
    except Exception as e:
        logger.error(f"Failed to embed metadata in {file_path}: {e}")
        return False


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
        audio = mutagen.mp3.MP3(file_path)
        metadata = {}

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
                        value = int(value.split('/')[0]) if '/' in value else int(value)
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
        # Create JSON path by replacing .mp3 with .json
        json_path = mp3_path.rsplit('.mp3', 1)[0] + '.json'

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

        json_path = os.path.join(download_path, f"{sanitize_filename(playlist.name)}.json")

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


def sanitize_filename(name: str) -> str:
    """
    Sanitize a filename by removing/replacing invalid characters.

    Args:
        name: Original filename or string

    Returns:
        Sanitized string safe for filenames
    """
    # Replace invalid characters with underscore
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        name = name.replace(char, '_')
    return name
