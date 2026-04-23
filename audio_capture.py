from __future__ import annotations

import threading
from typing import Any

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16_000


class AudioCapture:
    """Real-time microphone audio capture with start/stop control."""

    def __init__(self) -> None:
        self._recording = False
        self._audio_buffer: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()

    def _callback(self, indata: np.ndarray, frames: int, _time: Any, _status: Any) -> None:
        with self._lock:
            if self._recording:
                self._audio_buffer.append(indata.copy())

    def start(self) -> None:
        """Start recording from microphone."""
        with self._lock:
            self._recording = True
            self._audio_buffer = []

        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype=np.int16,
            blocksize=int(SAMPLE_RATE * 0.1),  # 100ms blocks
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> bytes:
        """Stop recording and return accumulated PCM16 audio bytes."""
        with self._lock:
            self._recording = False

        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        with self._lock:
            if not self._audio_buffer:
                return b""
            audio = np.concatenate(self._audio_buffer)
            self._audio_buffer = []
            return audio.tobytes()

    def is_recording(self) -> bool:
        with self._lock:
            return self._recording
