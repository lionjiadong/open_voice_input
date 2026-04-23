from __future__ import annotations

import time
from typing import Callable

from pynput import keyboard
from pynput.keyboard import Key


class GlobalHotkey:
    """Global hotkey listener for macOS.

    Uses pynput to listen for Ctrl key press/release events.
    Triggers callback when Ctrl is held for threshold_ms milliseconds.
    """

    def __init__(
        self,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
        threshold_ms: float = 300.0,
    ) -> None:
        self.on_press = on_press
        self.on_release = on_release
        self.threshold_ms = threshold_ms
        self._ctrl_pressed = False
        self._press_time: float | None = None
        self._triggered = False
        self._listener: keyboard.Listener | None = None

    def _on_key_press(self, key) -> None:
        if key == Key.ctrl or key == Key.ctrl_l or key == Key.ctrl_r:
            if not self._ctrl_pressed:
                self._ctrl_pressed = True
                self._press_time = time.monotonic()
                self._triggered = False

    def _on_key_release(self, key) -> None:
        if key == Key.ctrl or key == Key.ctrl_l or key == Key.ctrl_r:
            self._ctrl_pressed = False
            if self._triggered:
                self.on_release()
            self._press_time = None
            self._triggered = False

    def _check_threshold(self) -> None:
        """Called periodically to check if threshold is exceeded."""
        if self._ctrl_pressed and not self._triggered and self._press_time is not None:
            elapsed_ms = (time.monotonic() - self._press_time) * 1000
            if elapsed_ms >= self.threshold_ms:
                self._triggered = True
                self.on_press()

    def start(self) -> None:
        self._listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )
        self._listener.start()

        # Start periodic threshold checker
        self._schedule_check()

    def _schedule_check(self) -> None:
        """Schedule next threshold check."""
        if self._listener is not None and self._listener.is_alive():
            self._check_threshold()
            # Use threading.Timer for periodic check
            import threading

            threading.Timer(0.05, self._schedule_check).start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def is_alive(self) -> bool:
        return self._listener is not None and self._listener.is_alive()
