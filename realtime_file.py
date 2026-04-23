from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

import numpy as np
import pybase64
import soundfile as sf
import websockets
from websockets.asyncio.client import ClientConnection

BASE_URL = "http://120.55.162.96:18000/v1"
API_KEY = "Ljd@1234"
MODEL = "./Qwen3-ASR-1.7B"
SAMPLE_RATE = 16_000
# Send audio in 100ms chunks to simulate real-time streaming
REALTIME_CHUNK_DURATION = 0.1  # 100ms per chunk
CONTROL_PREFIX_PATTERN = re.compile(r"(?:language\s+\w+\s*)?<asr_text>")
PROGRESS_BAR_WIDTH = 30


class TerminalUI:
    """Manages two-line terminal output: progress bar + transcript."""

    def __init__(self, total_seconds: float) -> None:
        self.total_seconds = total_seconds
        self.current_seconds = 0.0
        self.transcript = ""

    def _format_progress(self) -> str:
        if self.total_seconds <= 0:
            ratio = 1.0
        else:
            ratio = min(self.current_seconds / self.total_seconds, 1.0)
        filled = int(PROGRESS_BAR_WIDTH * ratio)
        empty = PROGRESS_BAR_WIDTH - filled
        bar = "█" * filled + "░" * empty
        return f"[{bar}] {self.current_seconds:.1f}s / {self.total_seconds:.1f}s"

    def init_display(self) -> None:
        sys.stdout.write("\n\n")
        self._write_progress()
        sys.stdout.write("\n")
        sys.stdout.flush()

    def _write_progress(self) -> None:
        sys.stdout.write("\033[1F\033[2K")
        sys.stdout.write(self._format_progress())
        sys.stdout.write("\033[1E")

    def update_progress(self, seconds: float) -> None:
        self.current_seconds = seconds
        self._write_progress()
        sys.stdout.flush()

    def update_transcript(self, text: str) -> None:
        if text == self.transcript:
            return
        new_part = text[len(self.transcript) :]
        self.transcript = text
        sys.stdout.write(new_part)
        sys.stdout.flush()

    def finish(self, final_text: str) -> None:
        self.current_seconds = self.total_seconds
        self._write_progress()
        sys.stdout.write("\033[2K\r")
        sys.stdout.write(final_text)
        sys.stdout.write("\n")
        sys.stdout.flush()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="vLLM realtime file transcription client")
    parser.add_argument("audio_paths", nargs="*", help="Audio files to transcribe")
    parser.add_argument("--base-url", default=BASE_URL, help="OpenAI-compatible base URL")
    parser.add_argument("--api-key", default=API_KEY, help="API key for authentication")
    parser.add_argument("--model", default=MODEL, help="Realtime ASR model name")
    return parser.parse_args()


def resolve_audio_paths(audio_args: list[str]) -> list[Path]:
    if audio_args:
        audio_paths = [Path(arg).expanduser().resolve() for arg in audio_args]
    else:
        audio_paths = sorted(Path.cwd().glob("*.wav"))

    if not audio_paths:
        raise FileNotFoundError("No audio files found. Pass one or more files explicitly.")

    missing_paths = [path for path in audio_paths if not path.exists()]
    if missing_paths:
        joined = ", ".join(str(path) for path in missing_paths)
        raise FileNotFoundError(f"Audio files not found: {joined}")
    return [path.resolve() for path in audio_paths]


def build_ws_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    netloc = parsed.netloc
    path = parsed.path.rstrip("/")
    if path.endswith("/v1"):
        path = path[:-3]
    return f"{scheme}://{netloc}{path}/v1/realtime"


def load_audio_as_pcm16(audio_path: Path) -> tuple[bytes, float]:
    audio, sample_rate = sf.read(str(audio_path), dtype="float32", always_2d=False)

    if isinstance(audio, np.ndarray) and audio.ndim > 1:
        audio = audio.mean(axis=1)

    mono_audio = np.asarray(audio, dtype=np.float32)
    if sample_rate != SAMPLE_RATE:
        mono_audio = resample_audio(mono_audio, sample_rate, SAMPLE_RATE)

    mono_audio = np.clip(mono_audio, -1.0, 1.0)
    pcm16 = (mono_audio * 32767.0).astype(np.int16)
    duration = len(mono_audio) / SAMPLE_RATE
    return pcm16.tobytes(), duration


def resample_audio(audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if len(audio) == 0 or source_rate == target_rate:
        return audio

    duration = len(audio) / source_rate
    target_length = max(1, int(round(duration * target_rate)))
    source_positions = np.linspace(0.0, len(audio) - 1, num=len(audio), dtype=np.float32)
    target_positions = np.linspace(0.0, len(audio) - 1, num=target_length, dtype=np.float32)
    return np.interp(target_positions, source_positions, audio).astype(np.float32)


async def wait_for_session_created(ws: ClientConnection) -> None:
    raw_message = await ws.recv()
    data = parse_json_message(raw_message)
    if data.get("type") != "session.created":
        raise RuntimeError(f"Expected session.created, got: {data}")


async def configure_session(ws: ClientConnection, model: str) -> None:
    await ws.send(json.dumps({"type": "session.update", "model": model}))
    await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))


async def send_audio_realtime(
    ws: ClientConnection, audio_bytes: bytes, duration: float, ui: TerminalUI
) -> None:
    """Send audio in real-time chunks, simulating live microphone input.

    Each chunk represents REALTIME_CHUNK_DURATION seconds of audio.
    We sleep between chunks to match the real audio timeline.
    """
    # Calculate bytes per chunk (PCM16 = 2 bytes per sample)
    bytes_per_second = SAMPLE_RATE * 2
    chunk_size = int(bytes_per_second * REALTIME_CHUNK_DURATION)

    total_bytes = len(audio_bytes)
    start_time = time.monotonic()

    for offset in range(0, total_bytes, chunk_size):
        chunk = audio_bytes[offset : offset + chunk_size]
        await ws.send(
            json.dumps(
                {
                    "type": "input_audio_buffer.append",
                    "audio": pybase64.b64encode(chunk).decode("utf-8"),
                }
            )
        )

        # Update progress based on actual elapsed time
        current_seconds = (offset / total_bytes) * duration
        ui.update_progress(current_seconds)

        # Calculate when we should send the next chunk
        elapsed = time.monotonic() - start_time
        target_time = (offset + chunk_size) / bytes_per_second
        sleep_time = target_time - elapsed

        if sleep_time > 0:
            await asyncio.sleep(sleep_time)

    await ws.send(json.dumps({"type": "input_audio_buffer.commit", "final": True}))
    ui.update_progress(duration)


async def receive_transcription(ws: ClientConnection, ui: TerminalUI) -> str:
    final_text = ""
    rendered_text = ""

    async for raw_message in ws:
        data = parse_json_message(raw_message)
        event_type = data.get("type")

        if event_type == "transcription.delta":
            delta = data.get("delta", "")
            if isinstance(delta, str) and delta:
                if is_control_delta(delta):
                    continue
                candidate_text = clean_chunk_text(rendered_text + delta)
                if not candidate_text.startswith(rendered_text):
                    rendered_text = candidate_text
                    ui.update_transcript(candidate_text)
                    continue
                new_text = candidate_text[len(rendered_text) :]
                if new_text:
                    rendered_text = candidate_text
                    ui.update_transcript(candidate_text)
        elif event_type == "transcription.done":
            text = data.get("text", "")
            if isinstance(text, str):
                final_text = clean_chunk_text(text)
                if final_text and final_text != rendered_text:
                    ui.update_transcript(final_text)
            return final_text
        elif event_type == "error":
            raise RuntimeError(f"Realtime API error: {data}")

    raise RuntimeError("WebSocket closed before transcription.done was received")


async def realtime_transcribe(audio_path: Path, ws_url: str, api_key: str, model: str) -> str:
    print(f"Using audio file: {audio_path.name}")
    print(f"Realtime endpoint: {ws_url}")

    audio_bytes, duration = load_audio_as_pcm16(audio_path)
    headers = {"Authorization": f"Bearer {api_key}"}
    ui = TerminalUI(duration)
    ui.init_display()

    async with websockets.connect(ws_url, additional_headers=headers, proxy=None) as ws:
        await wait_for_session_created(cast(ClientConnection, ws))
        await configure_session(cast(ClientConnection, ws), model)
        await send_audio_realtime(cast(ClientConnection, ws), audio_bytes, duration, ui)
        final_text = await receive_transcription(cast(ClientConnection, ws), ui)
        ui.finish(final_text)
        return final_text


def parse_json_message(raw_message: Any) -> dict[str, Any]:
    if isinstance(raw_message, bytes):
        decoded = raw_message.decode("utf-8")
    elif isinstance(raw_message, str):
        decoded = raw_message
    else:
        raise TypeError(f"Unexpected websocket message type: {type(raw_message)!r}")

    payload = json.loads(decoded)
    if not isinstance(payload, dict):
        raise TypeError(f"Unexpected websocket payload type: {type(payload)!r}")
    return payload


def clean_chunk_text(text: str) -> str:
    stripped = text
    for marker in ("language English", "language Chinese", "<asr_text>"):
        stripped = stripped.replace(marker, "")
    stripped = stripped.replace("language", "")
    stripped = CONTROL_PREFIX_PATTERN.sub("", stripped)
    return stripped.strip()


def is_control_delta(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return True
    return normalized in {
        "language",
        "English",
        "Chinese",
        "language English",
        "language Chinese",
        "<asr_text>",
    }


async def run() -> None:
    args = parse_args()
    ws_url = build_ws_url(args.base_url)
    audio_paths = resolve_audio_paths(args.audio_paths)

    for index, audio_path in enumerate(audio_paths):
        if index > 0:
            print("-" * 60)
        try:
            await realtime_transcribe(audio_path, ws_url, args.api_key, args.model)
        except Exception as exc:
            print(f"Realtime transcription failed for {audio_path.name}: {exc}")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
