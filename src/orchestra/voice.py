from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SAMPLE_RATE = 16000
DEFAULT_MLX_MODEL = os.environ.get("ORCHESTRA_WHISPER_MODEL", "mlx-community/whisper-base.en-mlx")
FASTER_MODEL = os.environ.get("ORCHESTRA_FASTER_WHISPER_MODEL", "base.en")
MIN_PEAK = 4.0


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


def match_input_device(devices: list[dict], spec: str) -> int | None:
    spec = spec.strip()
    if not spec:
        return None
    inputs = [(index, device) for index, device in enumerate(devices) if int(device.get("max_input_channels", 0)) > 0]
    if spec.isdigit():
        wanted = int(spec)
        for index, _ in inputs:
            if index == wanted:
                return index
        return None
    lowered = spec.lower()
    for index, device in inputs:
        if lowered in str(device.get("name", "")).lower():
            return index
    return None


@dataclass
class VoiceStatus:
    available: bool
    reason: str


class VoiceInput:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.recording = False
        self.last_peak = 0.0
        self.device_name = ""
        self._stream: Any = None
        self._frames: list = []
        self._rate = SAMPLE_RATE
        self._channels = 1
        self._faster_model: Any = None
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
                bits.append("install the voice extra (mlx-whisper or faster-whisper)")
            return VoiceStatus(False, "voice off (" + "; ".join(bits) + ")")
        return VoiceStatus(True, f"voice ready ({backend})")

    def _resolve_device(self, sd) -> int | None:
        spec = os.environ.get("ORCHESTRA_INPUT_DEVICE", "")
        if not spec:
            return None
        index = match_input_device(list(sd.query_devices()), spec)
        if index is None:
            raise RuntimeError(f"no input device matches ORCHESTRA_INPUT_DEVICE={spec!r}")
        return index

    def start(self) -> None:
        if self.recording:
            return
        import sounddevice as sd

        device = self._resolve_device(sd)
        info = sd.query_devices(device) if device is not None else sd.query_devices(kind="input")
        if int(info.get("max_input_channels") or 0) < 1:
            raise RuntimeError(f"'{info.get('name', 'device')}' has no input channels")
        rate = int(info.get("default_samplerate") or SAMPLE_RATE)
        channels = max(1, min(2, int(info.get("max_input_channels") or 1)))
        attempts = list(dict.fromkeys([(rate, channels), (48000, 1), (16000, 1), (44100, 1)]))
        last_error: Exception | None = None
        for attempt_rate, attempt_channels in attempts:
            self._frames = []
            try:
                stream = sd.InputStream(
                    samplerate=attempt_rate,
                    channels=attempt_channels,
                    dtype="int16",
                    device=device,
                    callback=self._callback,
                )
                stream.start()
            except Exception as exc:
                last_error = exc
                continue
            self._stream = stream
            self._rate = attempt_rate
            self._channels = attempt_channels
            self.device_name = str(info.get("name") or "default input")
            self.recording = True
            return
        hint = ""
        if sys.platform == "win32":
            hint = " On Windows, check Settings > Privacy & security > Microphone and allow desktop apps."
        raise RuntimeError(f"could not open the microphone: {last_error}.{hint}")

    def _callback(self, indata, frames, timing, status):
        self._frames.append(indata.copy())

    def stop(self) -> Path | None:
        if not self.recording:
            return None
        stream = self._stream
        self._stream = None
        self.recording = False
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        if not self._frames:
            return None
        import numpy as np

        audio = np.concatenate(self._frames, axis=0)
        self.last_peak = float(np.abs(audio).max()) if audio.size else 0.0
        if audio.shape[0] < self._rate * 0.3:
            return None
        self._tmp_dir.mkdir(parents=True, exist_ok=True)
        path = self._tmp_dir / f"voice-{int(time.time() * 1000)}.wav"
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(self._channels)
            handle.setsampwidth(2)
            handle.setframerate(self._rate)
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

        if self._faster_model is None:
            self._faster_model = WhisperModel(FASTER_MODEL, device="cpu", compute_type="int8")
        segments, _ = self._faster_model.transcribe(str(path))
        return " ".join(segment.text.strip() for segment in segments).strip()


def voice_diagnostics() -> int:
    print(f"platform: {sys.platform}")
    print(f"python: {sys.version.split()[0]}")
    try:
        import sounddevice as sd
    except Exception as exc:
        print(f"sounddevice: NOT INSTALLED ({exc})")
        print("install the voice extra: pip install -e '.[voice]'")
        return 1
    print(f"sounddevice: {sd.__version__}")
    try:
        devices = sd.query_devices()
    except Exception as exc:
        print(f"query_devices failed: {exc}")
        return 1
    print("input devices:")
    for index, device in enumerate(devices):
        if int(device.get("max_input_channels") or 0) > 0:
            print(
                f"  [{index}] {device.get('name')} "
                f"({device.get('max_input_channels')}ch @ {float(device.get('default_samplerate') or 0):.0f}Hz)"
            )
    try:
        default = sd.query_devices(kind="input")
        print(
            f"default input: {default.get('name')} "
            f"({default.get('max_input_channels')}ch @ {float(default.get('default_samplerate') or 0):.0f}Hz)"
        )
    except Exception as exc:
        print(f"no default input device: {exc}")

    voice = VoiceInput()
    print(f"backend: {voice.status.reason}")
    if not voice.status.available:
        return 1

    try:
        input("press enter to record 3 seconds from the microphone... ")
    except EOFError:
        pass
    try:
        voice.start()
    except Exception as exc:
        print(f"microphone failed: {exc}")
        return 1
    time.sleep(3)
    path = voice.stop()
    if path is None:
        print("no audio captured (recording too short or stream failed)")
        return 1
    print(f"recorded {path.name}: peak level {voice.last_peak:.0f}/32767 from '{voice.device_name}'")
    if voice.last_peak < MIN_PEAK:
        print("WARNING: essentially no signal — check microphone permissions, mute, or pick another device")
        if sys.platform == "win32":
            print("Windows: Settings > Privacy & security > Microphone > allow desktop apps.")
        print("Select a specific device with ORCHESTRA_INPUT_DEVICE=<index or name>.")
        return 1
    try:
        text = asyncio.run(voice.transcribe(path))
    except Exception as exc:
        print(f"transcription failed: {exc}")
        return 1
    print(f"transcript: {text!r}")
    if not text:
        print("WARNING: transcription was empty — try speaking longer or installing a bigger model")
    return 0
