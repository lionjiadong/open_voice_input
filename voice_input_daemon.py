from __future__ import annotations

import asyncio
import threading

import rumps

from audio_capture import AudioCapture
from global_hotkey import GlobalHotkey
from keyboard_injector import KeyboardInjector
from websocket_asr import WebSocketASRClient


class VoiceInputApp(rumps.App):
    """macOS menu bar application for voice input."""

    def __init__(
        self,
        ws_url: str,
        api_key: str,
        model: str,
    ) -> None:
        super().__init__(
            "VoiceInput",
            title="🎤",
            quit_button="Quit",
        )
        self.ws_url = ws_url
        self.api_key = api_key
        self.model = model

        self.audio_capture = AudioCapture()
        self.keyboard = KeyboardInjector()
        self.asr_client: WebSocketASRClient | None = None

        self._recording = False
        self._processing = False

        # Menu items
        self.menu = [
            rumps.MenuItem("Status: Ready"),
            None,
            rumps.MenuItem("Start Recording", callback=self._manual_start),
            rumps.MenuItem("Stop Recording", callback=self._manual_stop),
            None,
        ]

        # Setup global hotkey
        self.hotkey = GlobalHotkey(
            on_press=self._on_hotkey_press,
            on_release=self._on_hotkey_release,
            threshold_ms=300.0,
        )

    def run(self) -> None:
        self.hotkey.start()
        super().run()

    def _update_status(self, status: str) -> None:
        """Update menu bar status text."""
        for item in self.menu:
            if isinstance(item, rumps.MenuItem) and item.title.startswith("Status:"):
                item.title = f"Status: {status}"
                break

    def _on_hotkey_press(self) -> None:
        """Called when Ctrl is held for threshold duration."""
        if self._recording or self._processing:
            return
        self._recording = True
        self.title = "🔴"
        self._update_status("Recording...")
        self.audio_capture.start()

    def _on_hotkey_release(self) -> None:
        """Called when Ctrl is released after being held."""
        if not self._recording:
            return
        self._recording = False
        self.title = "🟡"
        self._update_status("Processing...")

        # Stop recording and get audio
        audio_bytes = self.audio_capture.stop()
        if not audio_bytes:
            self.title = "🎤"
            self._update_status("Ready")
            return

        # Process in background thread
        threading.Thread(target=self._process_audio, args=(audio_bytes,), daemon=True).start()

    def _process_audio(self, audio_bytes: bytes) -> None:
        """Send audio to ASR and type result."""
        self._processing = True

        try:
            # Run async ASR in sync context
            result = asyncio.run(self._transcribe(audio_bytes))
            if result:
                self.keyboard.type_text(result)
        except Exception as exc:
            rumps.notification(
                "Voice Input Error",
                "Transcription failed",
                str(exc),
            )
        finally:
            self._processing = False
            self.title = "🎤"
            self._update_status("Ready")

    async def _transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe audio using WebSocket ASR."""
        client = WebSocketASRClient(
            ws_url=self.ws_url,
            api_key=self.api_key,
            model=self.model,
        )

        try:
            await client.connect()
            await client.send_audio_chunk(audio_bytes)
            await client.commit()
            return await client.receive()
        finally:
            await client.close()

    def _manual_start(self, _sender) -> None:
        """Menu item callback to start recording."""
        self._on_hotkey_press()

    def _manual_stop(self, _sender) -> None:
        """Menu item callback to stop recording."""
        self._on_hotkey_release()
