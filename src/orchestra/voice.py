from __future__ import annotations

import asyncio
import importlib.util
import os
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SAMPLE_RATE = 16000
DEFAULT_MLX_MODEL = os.environ.get("ORCHESTRA_WHISPER_MODEL", "mlx-community/whisper-base.en-mlx")
FASTER_MODEL = os.environ.get("ORCHESTRA_FASTER_WHISPER_MODEL", "base.en")


def _load_wav(path: Path):
    import numpy as np

    with wave.open(str(path), "rb") as handle:
        frames = handle.readframes(handle.getnframes())
        rate = handle.getframerate()
        width = handle.getsampwidth()
        channels = handle.getnchannels()
    dtype = {1: np.uint8, 2: np.int16, 4: np.int32}.get(width, np.int16)
    audio = np.frombuffer(frames, dtype=dtype).astype(np.float32)
    if width == 2:
        audio = audio / 32768.0
    elif width == 4:
        audio = audio / 2147483648.0
    elif width == 1:
        audio = (audio - 128.0) / 128.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    if rate != SAMPLE_RATE:
        count = int(audio.shape[0] * SAMPLE_RATE / rate)
        audio = np.interp(
            np.linspace(0.0, audio.shape[0], count, endpoint=False),
            np.arange(audio.shape[0]),
            audio,
        ).astype(np.float32)
    return audio


@dataclass
class VoiceStatus:
    available: bool
    reason: str


class VoiceInput:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.recording = False
        self._stream: Any = None
        self._frames: list = []
        self._tmp_dir = Path(os.environ.get("ORCHESTRA_HOME", Path.home() / ".orchestra")) / "voice"
        self.status = self._probe()

    def _probe(self) -> VoiceStatus:
        if not self.enabled:
            return VoiceStatus(False, "voice disabled")
        missing = [name for name in ("sounddevice", "numpy") if importlib.util.find_spec(name) is None]
        backend = None
        if importlib.util.find_spec("mlx_whisper") is not None:
            backend = "mlx-whisper"
        elif importlib.util.find_spec("faster_whisper") is not None:
            backend = "faster-whisper"
        if missing or backend is None:
            bits = []
            if missing:
                bits.append("pip install " + " ".join(missing))
            if backend is None:
                bits.append("pip install mlx-whisper")
            return VoiceStatus(False, "voice off (" + "; ".join(bits) + ")")
        return VoiceStatus(True, f"voice ready ({backend})")

    def start(self) -> None:
        if self.recording:
            return
        import sounddevice as sd

        self._frames = []

        def callback(indata, frames, timing, status):
            self._frames.append(indata.copy())

        self._stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", callback=callback)
        self._stream.start()
        self.recording = True

    def stop(self) -> Path | None:
        if not self.recording:
            return None
        stream = self._stream
        self._stream = None
        self.recording = False
        if stream is not None:
            stream.stop()
            stream.close()
        if not self._frames:
            return None
        import numpy as np

        audio = np.concatenate(self._frames, axis=0)
        if audio.shape[0] < SAMPLE_RATE * 0.3:
            return None
        self._tmp_dir.mkdir(parents=True, exist_ok=True)
        path = self._tmp_dir / f"voice-{int(time.time() * 1000)}.wav"
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(SAMPLE_RATE)
            handle.writeframes(audio.tobytes())
        return path

    async def transcribe(self, path: Path) -> str:
        if importlib.util.find_spec("mlx_whisper") is not None:
            return await asyncio.to_thread(self._transcribe_mlx, path)
        return await asyncio.to_thread(self._transcribe_faster, path)

    def _transcribe_mlx(self, path: Path) -> str:
        os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
        os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
        import mlx_whisper

        audio = _load_wav(path)
        result = mlx_whisper.transcribe(
            audio,
            path_or_hf_repo=DEFAULT_MLX_MODEL,
            verbose=None,
        )
        return str(result.get("text", "")).strip()

    def _transcribe_faster(self, path: Path) -> str:
        from faster_whisper import WhisperModel

        model = WhisperModel(FASTER_MODEL, device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(path))
        return " ".join(segment.text.strip() for segment in segments).strip()
