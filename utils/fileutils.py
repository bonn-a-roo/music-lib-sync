import os
import re

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WHITESPACE = re.compile(r'\s+')
_RESERVED_NAMES = frozenset(
    {'CON', 'PRN', 'AUX', 'NUL'}
    | {f'COM{i}' for i in range(1, 10)}
    | {f'LPT{i}' for i in range(1, 10)}
)

# Track IDs are recognised across every supported output format.
AUDIO_FORMATS = ('mp3', 'flac', 'm4a', 'opus', 'ogg', 'wav')
TRACK_FILE_RE = re.compile(r'\[([A-Za-z0-9]+)\](?i:\.(?:mp3|flac|m4a|opus|ogg|wav))$')


def create_directory(directory):
    os.makedirs(directory, exist_ok=True)


def sanitize_path_component(name, max_len: int = 120) -> str:
    """Make ``name`` safe to use as ONE file or directory name on Windows/POSIX.

    Path separators and Windows-forbidden characters become ``_`` so a title
    like "Tombo in 7/4" can never create a sub-directory. Trailing dots/spaces
    (silently stripped by Windows) are removed, reserved device names (CON,
    NUL, ...) are prefixed, and the result is never empty.
    """
    text = _INVALID_CHARS.sub('_', '' if name is None else str(name))
    text = _WHITESPACE.sub(' ', text).strip(' .')
    if text.split('.')[0].upper() in _RESERVED_NAMES:
        text = '_' + text
    text = text[:max_len].rstrip(' .')
    return text or '_'


def song_filename(artist, name, track_id, ext: str = 'mp3', max_len: int = 200) -> str:
    """Return ``"<artist> - <name> [<track_id>].<ext>"`` as a single safe file name.

    Only the "<artist> - <name>" part is truncated, so the trailing
    ``[track_id].ext`` (needed for dedupe) is always preserved.
    """
    suffix = f" [{track_id}].{ext}"
    stem = sanitize_path_component(
        f"{artist or 'Unknown Artist'} - {name or 'Unknown Title'}",
        max_len=max(1, max_len - len(suffix)),
    )
    return stem + suffix


def track_id_from_filename(filename: str):
    """Return the Spotify track id embedded in ``filename`` or None."""
    match = TRACK_FILE_RE.search(filename)
    return match.group(1) if match else None
