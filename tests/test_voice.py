from __future__ import annotations

import wave
from pathlib import Path

import pytest

from orchestra.voice import _load_wav, match_input_device

DEVICES = [
    {"name": "Speakers", "max_input_channels": 0, "default_samplerate": 48000},
    {"name": "MacBook Microphone", "max_input_channels": 1, "default_samplerate": 48000},
    {"name": "USB Headset", "max_input_channels": 2, "default_samplerate": 44100},
]


def test_match_input_device_by_index():
    assert match_input_device(DEVICES, "2") == 2
    assert match_input_device(DEVICES, "0") is None


def test_match_input_device_by_name():
    assert match_input_device(DEVICES, "usb") == 2
    assert match_input_device(DEVICES, "microphone") == 1
    assert match_input_device(DEVICES, "speakers") is None


def test_match_input_device_empty_and_unknown():
    assert match_input_device(DEVICES, "") is None
    assert match_input_device(DEVICES, "nope") is None
    assert match_input_device(DEVICES, "99") is None


def test_load_wav_downmixes_and_resamples(tmp_path: Path):
    numpy = pytest.importorskip("numpy")
    path = tmp_path / "stereo48k.wav"
    frames = numpy.full((48000, 2), 16384, dtype=numpy.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(48000)
        handle.writeframes(frames.tobytes())
    audio = _load_wav(path)
    assert audio.ndim == 1
    assert abs(audio.shape[0] - 16000) <= 2
    assert float(numpy.abs(audio).mean()) == pytest.approx(0.5, abs=0.02)
