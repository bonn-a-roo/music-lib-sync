import ctypes
import os
import sys
import threading
import time
from pathlib import Path

import pytest
from yt_dlp import YoutubeDL

from downloaders import ytdlp
from downloaders.ytdlp import YoutubeDownloader, _CommandResult
from model.song import Song
from utils import metadatautils
from utils.fileutils import song_filename

pytestmark = pytest.mark.unit


@pytest.fixture
def song():
    return Song(artist='Artist', name='Title', track_id='abc123',
                url='https://open.spotify.com/track/abc123', duration_ms=200000)


@pytest.fixture
def downloader():
    return YoutubeDownloader(workers=2, audio_format='mp3')


@pytest.mark.parametrize('title', ['a/b', '%(title)s', '50%(foo)s', '日本語 café', 'trailing.', 'x' * 300])
def test_literal_flat_template_round_trip(tmp_path, title, downloader):
    directory = tmp_path / '50%(foo)s music'
    expected = directory / song_filename('A/B', title, 'abc123')
    template = downloader._output_template(str(expected))
    with YoutubeDL({'outtmpl': template, 'quiet': True}) as ydl:
        actual = ydl.prepare_filename({'id': 'other', 'title': 'wrong', 'ext': 'mp3'})
    assert Path(actual) == expected
    assert Path(actual).parent == directory


@pytest.mark.parametrize('audio_format', ['mp3', 'flac', 'm4a', 'opus', 'ogg', 'wav'])
def test_configured_output_format(tmp_path, song, monkeypatch, audio_format):
    monkeypatch.setattr(ytdlp.configutils, 'get_audio_format', lambda: audio_format)
    d = YoutubeDownloader()
    install_download(monkeypatch, d, song, tmp_path, [200])
    monkeypatch.setattr(metadatautils, 'embed_metadata', lambda *a, **kw: True)
    result = d.download([song], str(tmp_path))
    assert result.success_count == 1
    assert (tmp_path / song_filename(song.artist, song.name, song.track_id, ext=audio_format)).exists()


def install_download(monkeypatch, d, song, directory, durations):
    attempts = []
    final = directory / song_filename(song.artist, song.name, song.track_id, ext=d.audio_format)
    values = iter(durations)
    current = [None]
    def run(cmd):
        if '--flat-playlist' in cmd:
            return _CommandResult(entries=[{'url': 'https://example.invalid/audio', 'duration': 200}])
        # Real on-disk result is deliberately independent of the success exit code.
        assert cmd[cmd.index('--audio-format') + 1] == ('vorbis' if d.audio_format == 'ogg' else d.audio_format)
        attempts.append(cmd)
        current[0] = next(values)
        final.write_bytes(b'new audio')
        return _CommandResult(reason='Maximum number of downloads reached')
    monkeypatch.setattr(d, '_run_cmd', run)
    monkeypatch.setattr(metadatautils, 'read_duration', lambda p: current[0], raising=False)
    return final, attempts


@pytest.mark.parametrize('raise_tagging', [False, True])
def test_wrong_duration_deleted_then_next_strategy_and_tagging(tmp_path, song, downloader, monkeypatch, raise_tagging):
    final, attempts = install_download(monkeypatch, downloader, song, tmp_path, [30, 200])
    tagged = []
    def embed(path, item, embed_art):
        assert Path(path).exists()
        assert metadatautils.read_duration(path) == 200
        tagged.append((path, embed_art))
        if raise_tagging:
            raise OSError('tagging failed')
        return False
    monkeypatch.setattr(metadatautils, 'embed_metadata', embed)
    original = downloader._run_cmd
    def run(cmd):
        if '--flat-playlist' in cmd and attempts:
            assert not final.exists()
        return original(cmd)
    monkeypatch.setattr(downloader, '_run_cmd', run)
    result = downloader.download([song], str(tmp_path))
    assert result.success_count == 1 and result.failure_count == 0
    assert len(attempts) == 2
    assert tagged == [(str(final), True)]


def test_all_wrong_files_deleted_one_duration_failure(tmp_path, song, downloader, monkeypatch):
    final, attempts = install_download(monkeypatch, downloader, song, tmp_path, [30, 1000, None])
    def no_tag(*args, **kwargs):
        pytest.fail('Unverified file must never be tagged')
    monkeypatch.setattr(metadatautils, 'embed_metadata', no_tag)
    result = downloader.download([song], str(tmp_path))
    assert len(attempts) == 3
    assert not final.exists()
    assert result.failure_count == 1
    assert result.errors[0].error_message == 'no candidate matched duration 180-220s'
    assert result.errors[0].item_url == song.url


def test_candidate_filter_and_missing_duration_resolution(tmp_path, song, downloader, monkeypatch):
    final = tmp_path / song_filename(song.artist, song.name, song.track_id)
    downloaded = []
    def run(cmd):
        if '--flat-playlist' in cmd:
            return _CommandResult(entries=[{'url': 'https://bad', 'duration': 30}, {'url': 'https://unknown'}])
        if '--skip-download' in cmd:
            assert cmd[-1] == 'https://unknown'
            return _CommandResult(entries=[{'duration': 200}])
        downloaded.append(cmd[-1])
        final.write_bytes(b'audio')
        return _CommandResult()
    monkeypatch.setattr(downloader, '_run_cmd', run)
    monkeypatch.setattr(metadatautils, 'read_duration', lambda p: 200, raising=False)
    monkeypatch.setattr(metadatautils, 'embed_metadata', lambda *a, **kw: True)
    assert downloader.download([song], str(tmp_path)).success_count == 1
    assert downloaded == ['https://unknown']


def test_unknown_expected_duration_accepts_short_audio(tmp_path, song, downloader, monkeypatch):
    song.duration_ms = None
    install_download(monkeypatch, downloader, song, tmp_path, [20])
    downloader.embed_metadata = False
    monkeypatch.setattr(metadatautils, 'embed_metadata', lambda *a, **kw: pytest.fail('disabled'))
    assert downloader.download([song], str(tmp_path)).success_count == 1


def test_orphan_sweep_preserves_unmarked_and_existing_audio(tmp_path, downloader):
    removed = ['A [orphan].mp3.part', 'A [orphan].ytdl', 'A [orphan].temp.mp4', 'A [orphan].webm']
    kept = ['personal.part', 'personal.mp4', 'A [done].mp3', 'A [done].webm', 'A [format].opus']
    for name in removed + kept:
        (tmp_path / name).write_bytes(b'original')
    downloader._sweep(tmp_path)
    assert {p.name for p in tmp_path.iterdir()} == set(kept)


def test_partial_cleanup_between_attempts(tmp_path, song, downloader, monkeypatch):
    final = tmp_path / song_filename(song.artist, song.name, song.track_id)
    partial = Path(str(final.with_suffix('.webm')) + '.part')
    attempts = []
    def run(cmd):
        if '--flat-playlist' in cmd:
            assert not partial.exists()
            return _CommandResult(entries=[{'url': 'https://example.invalid', 'duration': 200}])
        assert not partial.exists()
        partial.write_bytes(b'partial')
        attempts.append(cmd)
        return _CommandResult(reason='download failed')
    monkeypatch.setattr(downloader, '_run_cmd', run)
    assert downloader.download([song], str(tmp_path)).failure_count == 1
    assert len(attempts) == 3
    assert not partial.exists()


def test_existing_wrong_audio_is_not_deleted_or_overwritten(tmp_path, song, downloader, monkeypatch):
    final = tmp_path / song_filename(song.artist, song.name, song.track_id)
    final.write_bytes(b'user original')
    monkeypatch.setattr(metadatautils, 'read_duration', lambda p: 30, raising=False)
    monkeypatch.setattr(downloader, '_run_cmd', lambda *a: pytest.fail('existing audio must not be overwritten'))
    assert downloader.download([song], str(tmp_path)).failure_count == 1
    assert final.read_bytes() == b'user original'


def test_progress_order_and_empty(tmp_path, song, downloader, monkeypatch):
    calls = []
    assert downloader.download([], str(tmp_path), lambda *a: calls.append(a)).total == 0
    assert calls == []
    songs = [song, Song(artist='Other', name='Second', track_id='two')]
    def finish(item, path, result):
        if item is song:
            time.sleep(0.05)
        result.add_failure(str(item), item.url, 'offline')
    monkeypatch.setattr(downloader, '_download_song', finish)
    result = downloader.download(songs, str(tmp_path), lambda *a: calls.append(a))
    assert result.failure_count == 2
    assert calls == [(0, 2, ''), (1, 2, 'Other - Second'), (2, 2, 'Artist - Title')]


def test_preflight_all_problem_sources(tmp_path, downloader, monkeypatch):
    monkeypatch.setattr(ytdlp.shutil, 'which', lambda name: None)
    monkeypatch.setattr(ytdlp.Path, 'home', lambda: tmp_path)
    monkeypatch.setenv('APPDATA', str(tmp_path))
    downloader.cookies_file = str(tmp_path / 'missing.txt')
    problems = downloader.preflight()
    assert any('FFmpeg' in p for p in problems)
    assert any('Node.js' in p for p in problems)
    assert any('Cookies file' in p for p in problems)
    downloader.cookies_file = None
    assert any('Firefox profile' in p for p in downloader.preflight())
    (tmp_path / '.spotdl').mkdir()
    bundled = tmp_path / '.spotdl' / 'ffmpeg.exe'
    bundled.write_bytes(b'ffmpeg')
    assert downloader._find_ffmpeg() == str(bundled)


def process_alive(pid):
    if os.name == 'nt':
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        handle = kernel.OpenProcess(0x00100000, False, pid)
        if not handle:
            return False
        try:
            return kernel.WaitForSingleObject(ctypes.c_void_p(handle), 0) == 258
        finally:
            kernel.CloseHandle(ctypes.c_void_p(handle))
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    stat = Path(f'/proc/{pid}/stat')
    return not (stat.exists() and stat.read_text().split()[2] == 'Z')


@pytest.mark.parametrize('cancel', [False, True])
def test_real_process_tree_timeout_and_cancel(tmp_path, song, downloader, monkeypatch, cancel):
    script = ("import subprocess,sys,time; "
              "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(120)']); "
              "print(p.pid,flush=True); time.sleep(120)")
    pids = []
    ready = threading.Event()
    def log(line):
        if line.isdigit():
            pids.append(int(line))
            ready.set()
    downloader.log_callback = log
    monkeypatch.setattr(ytdlp, 'ATTEMPT_TIMEOUT', 5 if cancel else 1)
    command = [sys.executable, '-u', '-c', script]
    if cancel:
        original = downloader._run_cmd
        monkeypatch.setattr(downloader, '_run_cmd', lambda cmd: original(command))
        holder = []
        thread = threading.Thread(target=lambda: holder.append(downloader.download([song], str(tmp_path))))
        thread.start()
        try:
            assert ready.wait(4), 'Child process did not start'
            downloader.cancel()
            thread.join(8)
            assert not thread.is_alive()
            assert holder[0].cancelled
            assert holder[0].failure_count == 0
        finally:
            downloader.cancel()
            thread.join(8)
    else:
        result = downloader._run_cmd(command)
        assert result.reason == 'timed out after 1s'
    assert pids
    deadline = time.monotonic() + 3
    while any(process_alive(pid) for pid in pids) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not any(process_alive(pid) for pid in pids)


def test_output_stream_and_last_error(downloader):
    lines = []
    downloader.log_callback = lines.append
    script = "print('ERROR: first'); print('working'); print('ERROR: precise cause'); raise SystemExit(1)"
    result = downloader._run_cmd([sys.executable, '-u', '-c', script])
    assert result.reason == 'precise cause'
    assert lines == ['ERROR: first', 'working', 'ERROR: precise cause']


def test_failing_log_callback_does_not_leak_process(downloader):
    def broken_callback(line):
        raise RuntimeError('UI log pane closed')
    downloader.log_callback = broken_callback
    result = downloader._run_cmd([sys.executable, '-u', '-c', "print('ERROR: genuine failure'); raise SystemExit(1)"])
    assert result.reason == 'genuine failure'
    assert not downloader._running_processes
