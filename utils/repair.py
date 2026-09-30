"""Non-destructive repairs for old nested downloads and rejected audio."""
import os
from pathlib import Path

from utils.fileutils import TRACK_FILE_RE, sanitize_path_component, track_id_from_filename


def _move_unique(path, directory, name):
    """Reserve the destination exclusively so an existing file is never replaced."""
    stem, extension = os.path.splitext(name)
    match = TRACK_FILE_RE.search(name)
    if match:
        stem, extension = name[:match.start()].rstrip(), ' ' + name[match.start():]
    index = 0
    while True:
        candidate = os.path.join(directory, name if index == 0 else f'{stem} ({index}){extension}')
        try:
            fd = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            index += 1
            continue
        os.close(fd)
        try:
            # Destination is our own reservation, not another user's file.
            os.replace(path, candidate)
        except Exception:
            os.unlink(candidate)
            raise
        return candidate


def flatten_nested_tracks(directory) -> int:
    root = Path(directory)
    if not root.is_dir():
        return 0
    known = {track_id_from_filename(entry.name) for entry in root.iterdir() if entry.is_file()}
    moved = 0
    visited = []
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(name for name in dirs if name.casefold() != '_rejected' and not Path(current, name).is_symlink())
        folder = Path(current)
        if folder == root:
            continue
        visited.append(folder)
        for name in sorted(files):
            source = folder / name
            track_id = track_id_from_filename(name)
            if not track_id or track_id in known or source.is_symlink():
                continue
            relative = source.relative_to(root)
            match = TRACK_FILE_RE.search(name)
            suffix = ' ' + name[match.start():]
            stem_parts = list(relative.parts[:-1]) + [name[:match.start()].rstrip()]
            stem = sanitize_path_component('_'.join(stem_parts), max_len=max(1, 200 - len(suffix)))
            _move_unique(source, root, stem + suffix)
            known.add(track_id)
            moved += 1
    for folder in reversed(visited):
        try:
            folder.rmdir()
        except OSError:
            pass  # Only remove empty directories, never other files.
    return moved


def quarantine(path, directory) -> str:
    rejected = os.path.join(directory, '_rejected')
    os.makedirs(rejected, exist_ok=True)
    return _move_unique(path, rejected, os.path.basename(path))
