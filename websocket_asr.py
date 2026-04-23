from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Callable

import pybase64
import websockets
from websockets.asyncio.client import ClientConnection

CONTROL_PREFIX_PATTERN = re.compile(r"(?:language\s+\w+\s*)?<asr_text>")


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


class WebSocketASRClient:
    """Reusable WebSocket client for vLLM realtime ASR."""

    def __init__(
        self,
        ws_url: str,
        api_key: str,
        model: str,
        on_delta: Callable[[str], None] | None = None,
        on_done: Callable[[str], None] | None = None,
        on_error: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.ws_url = ws_url
        self.api_key = api_key
        self.model = model
        self.on_delta = on_delta
        self.on_done = on_done
        self.on_error = on_error
        self.ws: ClientConnection | None = None
        self._session_ready = asyncio.Event()

    async def connect(self) -> None:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        self.ws = await websockets.connect(self.ws_url, additional_headers=headers, proxy=None)
        raw_message = await self.ws.recv()
        data = self._parse_message(raw_message)
        if data.get("type") != "session.created":
            raise RuntimeError(f"Expected session.created, got: {data}")
        await self.ws.send(json.dumps({"type": "session.update", "model": self.model}))
        await self.ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
        self._session_ready.set()

    async def send_audio_chunk(self, pcm16_bytes: bytes) -> None:
        await self._session_ready.wait()
        if self.ws is None:
            raise RuntimeError("WebSocket not connected")
        await self.ws.send(
            json.dumps(
                {
                    "type": "input_audio_buffer.append",
                    "audio": pybase64.b64encode(pcm16_bytes).decode("utf-8"),
                }
            )
        )

    async def commit(self) -> None:
        await self._session_ready.wait()
        if self.ws is None:
            raise RuntimeError("WebSocket not connected")
        await self.ws.send(json.dumps({"type": "input_audio_buffer.commit", "final": True}))

    async def receive(self) -> str:
        if self.ws is None:
            raise RuntimeError("WebSocket not connected")

        final_text = ""
        rendered_text = ""

        async for raw_message in self.ws:
            data = self._parse_message(raw_message)
            event_type = data.get("type")

            if event_type == "transcription.delta":
                delta = data.get("delta", "")
                if isinstance(delta, str) and delta:
                    if is_control_delta(delta):
                        continue
                    candidate_text = clean_chunk_text(rendered_text + delta)
                    if not candidate_text.startswith(rendered_text):
                        rendered_text = candidate_text
                        if self.on_delta:
                            self.on_delta(candidate_text)
                        continue
                    new_text = candidate_text[len(rendered_text) :]
                    if new_text:
                        rendered_text = candidate_text
                        if self.on_delta:
                            self.on_delta(candidate_text)
            elif event_type == "transcription.done":
                text = data.get("text", "")
                if isinstance(text, str):
                    final_text = clean_chunk_text(text)
                    if final_text and final_text != rendered_text:
                        if self.on_delta:
                            self.on_delta(final_text)
                if self.on_done:
                    self.on_done(final_text)
                return final_text
            elif event_type == "error":
                if self.on_error:
                    self.on_error(data)
                raise RuntimeError(f"Realtime API error: {data}")

        raise RuntimeError("WebSocket closed before transcription.done was received")

    async def close(self) -> None:
        if self.ws is not None:
            await self.ws.close()
            self.ws = None

    @staticmethod
    def _parse_message(raw_message: Any) -> dict[str, Any]:
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
