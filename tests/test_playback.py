import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import shutil
import subprocess
import time
import wave
from pathlib import Path

import pytest
from PyQt5.QtWidgets import QApplication

from model.library_state import CollectionKey
from ui.playback import PlaybackController, PlaybackEntry

pytestmark = pytest.mark.unit
app = QApplication.instance() or QApplication([])


_ENCODERS = {
    'mp3': ['-c:a', 'libmp3lame'],
    'flac': ['-c:a', 'flac'],
    'm4a': ['-c:a', 'aac', '-f', 'ipod'],
    'opus': ['-c:a', 'libopus'],
    'ogg': ['-c:a', 'libvorbis'],
    'wav': ['-c:a', 'pcm_s16le'],
}


def _tone(ffmpeg, path):
    subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi',
                    '-i', 'sine=frequency=440:duration=2', *_ENCODERS[path.suffix[1:]], str(path)],
                   check=True, capture_output=True, timeout=30)


def _wait_for_decode(controller, timeout=6):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if ((controller.player.duration() > 0
             and controller.player.state() == controller.player.PlayingState)
                or controller.player.error() != controller.player.NoError):
            break
        time.sleep(.01)
    app.processEvents()


@pytest.mark.parametrize('extension', ['mp3', 'flac', 'm4a', 'opus', 'ogg', 'wav'])
def test_local_playback_handles_all_supported_formats(tmp_path, extension):
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        pytest.skip('FFmpeg is required for temporary playback fixtures')
    path = tmp_path / f'tone.{extension}'
    _tone(ffmpeg, path)
    player = PlaybackController(ffmpeg_path=ffmpeg)
    errors = []
    player.error_occurred.connect(errors.append)
    player.play_queue([PlaybackEntry(CollectionKey('account', 'saved'), 'tone123', str(path),
                                    'Tone', 'Test Artist', 0)])
    _wait_for_decode(player)
    try:
        assert not errors, f'{extension} playback failed: {errors}'
        assert player.player.duration() > 0
        assert player.player.state() == player.player.PlayingState
        if extension in ('mp3', 'flac', 'm4a', 'opus', 'ogg'):
            assert player._current_temp and Path(player._current_temp).suffix == '.wav'
            assert Path(player._current_temp).is_file()
        else:
            assert player._current_temp is None
        assert path.is_file()
    finally:
        player.close()
        app.processEvents()


def test_mp3_is_decoded_before_playback_unless_the_wav_would_be_too_large(tmp_path, monkeypatch):
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        pytest.skip('FFmpeg is required for temporary playback fixtures')
    paths = {}
    for name, options in (('cbr', ['-b:a', '128k']), ('vbr', ['-q:a', '2'])):
        paths[name] = tmp_path / f'{name}.mp3'
        subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi',
                        '-i', 'sine=frequency=440:duration=2', '-c:a', 'libmp3lame', *options,
                        str(paths[name])], check=True, capture_output=True, timeout=30)
    garbage = tmp_path / 'garbage.mp3'
    garbage.write_bytes(b'not audio' * 100)
    # DirectShow mis-times VBR and artwork-tagged CBR MP3s alike, so both decode.
    assert PlaybackController._decode_first(str(paths['cbr']))
    assert PlaybackController._decode_first(str(paths['vbr']))
    assert not PlaybackController._decode_first(str(garbage))  # Qt's error triggers the fallback
    assert not PlaybackController._decode_first(str(tmp_path / 'missing.mp3'))
    assert not PlaybackController._decode_first(str(tmp_path / 'tone.wav'))
    assert PlaybackController._decode_first(str(tmp_path / 'tone.FLAC'))
    # A 2 s MP3 needs about 350 KB of WAV; over the cap it plays natively instead of failing.
    monkeypatch.setattr(PlaybackController, 'MAX_TEMP_WAV_BYTES', 100_000)
    assert not PlaybackController._decode_first(str(paths['cbr']))


def test_vbr_mp3_reports_real_duration_seeks_accurately_and_releases_file(tmp_path):
    # Live finding: Qt's Windows DirectShow backend estimated VBR MP3 length from the
    # first frames (a 7:04 track showed 27:48) and seeked to the wrong audio, so MP3s
    # are decoded to a temporary WAV like the formats Qt cannot play.
    from mutagen.mp3 import MP3

    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        pytest.skip('FFmpeg is required for temporary playback fixtures')
    path = tmp_path / 'vbr.mp3'
    # A silent intro makes the first VBR frames tiny, which is what misleads DirectShow.
    subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y',
                    '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=stereo:d=4',
                    '-f', 'lavfi', '-i', 'anoisesrc=d=16:c=pink:r=44100:a=0.5',
                    '-filter_complex', '[1:a]aformat=channel_layouts=stereo[n];[0:a][n]concat=n=2:v=0:a=1',
                    '-c:a', 'libmp3lame', '-q:a', '0', str(path)],
                   check=True, capture_output=True, timeout=30)
    real_ms = MP3(str(path)).info.length * 1000
    player = PlaybackController(ffmpeg_path=ffmpeg)
    player.set_volume(0)
    errors = []
    player.error_occurred.connect(errors.append)
    player.play_queue([PlaybackEntry(CollectionKey('account', 'saved'), 'vbr123', str(path),
                                    'VBR', 'Artist', 0)])
    _wait_for_decode(player)
    try:
        assert not errors
        assert player._current_temp and Path(player._current_temp).suffix == '.wav'
        assert abs(player.duration - real_ms) < 1000, (player.duration, real_ms)
        player.seek(int(real_ms) - 1500)
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline and player.current_entry is not None:
            app.processEvents()
            time.sleep(.01)
        assert player.current_entry is None, 'seeking near the end did not reach the end of the track'
        player.quiesce()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and not player.is_quiesced:
            app.processEvents()
            time.sleep(.01)
        assert player.is_quiesced
        path.rename(tmp_path / 'moved.mp3')  # Repair can move the file once playback releases it
    finally:
        player.close()
        app.processEvents()


def test_quiesce_waits_for_ffmpeg_and_qt_to_release_playback_files(tmp_path):
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        pytest.skip('FFmpeg is required for temporary playback fixtures')
    source = tmp_path / 'long.flac'
    subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi',
                    '-i', 'sine=frequency=220:duration=30', '-c:a', 'flac', str(source)],
                   check=True, capture_output=True, timeout=30)
    player = PlaybackController(ffmpeg_path=ffmpeg)
    released = []
    player.quiesced.connect(lambda: released.append(True))
    player.play_queue([PlaybackEntry(CollectionKey('account', 'saved'), 'long123',
                                     str(source), 'Long', 'Artist', 0)])
    assert player._decode_process is not None
    player.quiesce()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not player.is_quiesced:
        app.processEvents()
        time.sleep(.01)
    app.processEvents()
    try:
        assert player.is_quiesced
        assert released
        assert player.current_entry is None
        assert not player._pending_processes
    finally:
        player.close()
        app.processEvents()


def test_quiesce_waits_for_qt_to_release_native_playback(tmp_path):
    path = tmp_path / 'tone.wav'
    with wave.open(str(path), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(bytes(8000 * 2 * 10))
    player = PlaybackController()
    released = []
    player.quiesced.connect(lambda: released.append(True))
    player.play_queue([PlaybackEntry(CollectionKey('account', 'saved'), 'native123',
                                    str(path), 'Tone', 'Artist', 0)])
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and player.player.duration() <= 0:
        app.processEvents()
        time.sleep(.01)
    assert player.player.duration() > 0
    player.quiesce()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and not player.is_quiesced:
        app.processEvents()
        time.sleep(.01)
    app.processEvents()
    try:
        assert player.is_quiesced and released
        assert player.current_entry is None
    finally:
        player.close()
        app.processEvents()


def test_local_playback_pause_seek_and_volume_controls(tmp_path):
    path = tmp_path / 'controls.wav'
    with wave.open(str(path), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(bytes(8000 * 2 * 10))
    player = PlaybackController()
    player.play_queue([PlaybackEntry(CollectionKey('account', 'saved'), 'controls123',
                                    str(path), 'Controls', 'Artist', 0)])
    _wait_for_decode(player)
    try:
        assert player.player.state() == player.player.PlayingState
        player.toggle()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and player.player.state() != player.player.PausedState:
            app.processEvents()
            time.sleep(.01)
        assert player.player.state() == player.player.PausedState
        player.seek(2000)
        player.set_volume(23)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and abs(player.position - 2000) >= 500:
            app.processEvents()
            time.sleep(.01)
        assert abs(player.position - 2000) < 500
        assert player.player.volume() == 23
        player.toggle()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and player.player.state() != player.player.PlayingState:
            app.processEvents()
            time.sleep(.01)
        assert player.player.state() == player.player.PlayingState
    finally:
        player.close()
        app.processEvents()


def test_corrupt_audio_reports_a_short_actionable_message(tmp_path):
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        pytest.skip('FFmpeg is required for the decoder-failure path')
    path = tmp_path / 'Broken Track [broken99].mp3'
    path.write_bytes(b'this is not audio' * 50)
    player = PlaybackController(ffmpeg_path=ffmpeg)
    errors = []
    player.error_occurred.connect(errors.append)
    player.play_queue([PlaybackEntry(CollectionKey('account', 'saved'), 'broken99', str(path),
                                    'Broken', 'Artist', 0)])
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline and not errors:
        app.processEvents()
        time.sleep(.01)
    try:
        assert errors, 'a damaged file must report an error'
        assert 'Broken Track [broken99].mp3' in errors[0]
        assert 'damaged' in errors[0] and len(errors[0]) < 200
        assert '[mp3 @' not in errors[0] and str(tmp_path) not in errors[0]
        assert path.read_bytes() == b'this is not audio' * 50
    finally:
        player.close()
        app.processEvents()


def test_playback_queue_retains_duplicate_track_occurrences_and_scope(tmp_path):
    path = tmp_path / 'silence.wav'
    with wave.open(str(path), 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(bytes(8000 * 2 * 10))
    key = CollectionKey('account', 'playlist')
    entries = (
        PlaybackEntry(key, 'same123', str(path), 'Repeated', 'Artist', 3),
        PlaybackEntry(key, 'same123', str(path), 'Repeated', 'Artist', 8),
    )
    player = PlaybackController()
    player.play_queue(entries, start_index=1)
    try:
        assert player.current_entry == entries[1]
        assert player.queue == entries
        player.previous()
        assert player.current_entry == entries[0]
        player.next()
        assert player.current_entry == entries[1]
    finally:
        player.close()
        app.processEvents()
