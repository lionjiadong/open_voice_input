from __future__ import annotations

import time

from pynput.keyboard import Controller, Key


class KeyboardInjector:
    """Simulates keyboard input on macOS.

    Uses pynput to type text character by character into the currently
    focused application.
    """

    def __init__(self, typing_delay: float = 0.01) -> None:
        self.controller = Controller()
        self.typing_delay = typing_delay

    def type_text(self, text: str) -> None:
        """Type the given text as if a user were typing."""
        for char in text:
            self.controller.type(char)
            if self.typing_delay > 0:
                time.sleep(self.typing_delay)

    def press_enter(self) -> None:
        """Press the Enter/Return key."""
        self.controller.press(Key.enter)
        self.controller.release(Key.enter)

    def press_space(self) -> None:
        """Press the Space key."""
        self.controller.press(Key.space)
        self.controller.release(Key.space)
