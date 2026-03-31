"""
Hardware abstraction: WS2812 button LED (rpi_ws281x) + momentary button (gpiozero).

LED states:
  idle    — off
  working — slow white pulse (~0.5 Hz)
  success — 3× fast green flashes
  error   — 5× fast red flashes

The LED runs in a background thread driven by an event loop so the main
thread can block on USB/network I/O without disrupting the animation.

Button is read via gpiozero with internal pull-up; wired NO→GPIO, C→GND.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

log = logging.getLogger("aina.hardware")

# Colour helpers
_OFF = (0, 0, 0)
_WHITE = (255, 255, 255)
_GREEN = (0, 255, 0)
_RED = (255, 0, 0)


class _MockLED:
    """Fallback when rpi_ws281x is not available (development on non-Pi)."""

    def __init__(self, pin: int, brightness: int):
        log.warning("rpi_ws281x not available — LED is simulated (pin %d)", pin)

    def set_color(self, r: int, g: int, b: int, brightness: int) -> None:
        pass

    def clear(self) -> None:
        pass

    def cleanup(self) -> None:
        pass


class _WS2812LED:
    def __init__(self, pin: int, brightness: int):
        from rpi_ws281x import PixelStrip, Color  # type: ignore
        self._Color = Color
        self._brightness = brightness
        self._strip = PixelStrip(1, pin, 800000, 5, False, brightness, 0)
        self._strip.begin()

    def set_color(self, r: int, g: int, b: int, brightness: Optional[int] = None) -> None:
        if brightness is not None:
            self._strip.setBrightness(brightness)
        self._strip.setPixelColor(0, self._Color(r, g, b))
        self._strip.show()

    def clear(self) -> None:
        self.set_color(0, 0, 0)

    def cleanup(self) -> None:
        self.clear()


class _MockButton:
    """Fallback button for non-Pi development — never fires."""

    def __init__(self, pin: int):
        log.warning("gpiozero not available — button is simulated (pin %d, never fires)", pin)
        self._cb: Optional[Callable] = None

    def when_pressed(self, cb: Callable) -> None:
        self._cb = cb

    def close(self) -> None:
        pass


class _GPIOButton:
    def __init__(self, pin: int):
        from gpiozero import Button  # type: ignore
        self._btn = Button(pin, pull_up=True, bounce_time=0.05)

    def when_pressed(self, cb: Callable) -> None:
        self._btn.when_pressed = cb

    def close(self) -> None:
        self._btn.close()


# ---------------------------------------------------------------------------
# LED controller (background thread)
# ---------------------------------------------------------------------------

class LEDController:
    """Thread-safe WS2812 LED state machine."""

    def __init__(self, pin: int, brightness: int):
        try:
            self._led: _WS2812LED | _MockLED = _WS2812LED(pin, brightness)
        except Exception:
            self._led = _MockLED(pin, brightness)
        self._brightness = brightness
        self._state = "idle"
        self._stop = threading.Event()
        self._change = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    # Public API

    def idle(self) -> None:
        self._set_state("idle")

    def working(self) -> None:
        self._set_state("working")

    def success(self) -> None:
        self._set_state("success")

    def error(self) -> None:
        self._set_state("error")

    def shutdown(self) -> None:
        self._stop.set()
        self._change.set()
        self._thread.join(timeout=2)
        self._led.cleanup()

    # Internal

    def _set_state(self, state: str) -> None:
        self._state = state
        self._change.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            state = self._state
            self._change.clear()

            if state == "idle":
                self._led.clear()
                self._change.wait()

            elif state == "working":
                self._pulse_white()

            elif state == "success":
                self._flash(_GREEN, count=3, on=0.12, off=0.1)
                self._led.clear()
                self._set_state("idle")

            elif state == "error":
                self._flash(_RED, count=5, on=0.08, off=0.08)
                self._led.clear()
                self._set_state("idle")

    def _pulse_white(self) -> None:
        """Sine-wave brightness pulse. Runs until state changes."""
        import math
        step = 0
        steps = 60  # full cycle
        while self._state == "working" and not self._stop.is_set():
            t = step / steps
            # sin goes 0→1→0 over one cycle
            bright = int(self._brightness * (0.5 - 0.5 * math.cos(2 * math.pi * t)))
            r, g, b = _WHITE
            self._led.set_color(r, g, b, bright)
            time.sleep(1.0 / steps / 0.5)  # period = 2 s
            step = (step + 1) % steps

    def _flash(self, color: tuple, count: int, on: float, off: float) -> None:
        r, g, b = color
        for _ in range(count):
            if self._stop.is_set():
                break
            self._led.set_color(r, g, b, self._brightness)
            time.sleep(on)
            self._led.clear()
            time.sleep(off)


# ---------------------------------------------------------------------------
# Button controller
# ---------------------------------------------------------------------------

class ButtonController:
    def __init__(self, pin: int):
        try:
            self._btn: _GPIOButton | _MockButton = _GPIOButton(pin)
        except Exception:
            self._btn = _MockButton(pin)

    def on_press(self, callback: Callable) -> None:
        self._btn.when_pressed(callback)

    def close(self) -> None:
        self._btn.close()
