#!/usr/bin/env python3
"""
AI Is Not Art — Sticker Printer
================================
Waits for a button press, generates anti-AI-art sticker images via OpenAI,
lays them out, prints them on the PixCut S1, and deletes the temp files.

Wiring:
  Button: NO → GPIO 17 (BCM),  C → GND
  LED:    DIN → GPIO 18 (BCM), VDD → 5V, GND → GND
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import signal
import threading
import time
from pathlib import Path
from typing import List, Optional

import config as cfg_module
from config import Config
from hardware import ButtonController, LEDController
from image_gen import generate_all
from printer import layout_and_print
from prompt_gen import PromptGenerator

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------


def _setup_logging(cfg: Config) -> None:
    Path(cfg.app.log_file).parent.mkdir(parents=True, exist_ok=True)
    handlers = [
        logging.StreamHandler(),
        logging.FileHandler(cfg.app.log_file),
    ]
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        handlers=handlers,
    )


log = logging.getLogger("aina.main")

# ---------------------------------------------------------------------------
# Application state machine
# ---------------------------------------------------------------------------


class App:
    def __init__(self, cfg: Config):
        self._cfg = cfg
        self._led = LEDController(cfg.gpio.led_pin, cfg.gpio.led_brightness)
        self._button = ButtonController(cfg.gpio.button_pin)
        self._prompt_gen = PromptGenerator(cfg)
        self._busy = threading.Lock()  # non-blocking: tryacquire guards re-entry
        self._shutdown = threading.Event()

    def run(self) -> None:
        log.info("AI Is Not Art starting up")
        log.info(
            "Button GPIO %d, LED GPIO %d, stickers/run=%d",
            self._cfg.gpio.button_pin,
            self._cfg.gpio.led_pin,
            self._cfg.openai.stickers_per_run,
        )

        # Clear temp dir on startup.
        self._clear_tmp()

        # Wire button.
        self._button.on_press(self._on_button_press)

        # Handle Ctrl+C / SIGTERM gracefully.
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        log.info("Idle — waiting for button press")
        self._led.idle()

        # Block main thread until shutdown.
        self._shutdown.wait()
        log.info("Shutting down")
        self._led.shutdown()
        self._button.close()

    # ------------------------------------------------------------------
    # Button handler (called from gpiozero's background thread)
    # ------------------------------------------------------------------

    def _on_button_press(self) -> None:
        if not self._busy.acquire(blocking=False):
            log.debug("Button press ignored — already processing")
            return
        # Run the workflow in a separate thread so we don't block
        # gpiozero's internal event thread.
        t = threading.Thread(target=self._workflow, daemon=True)
        t.start()

    # ------------------------------------------------------------------
    # Main workflow
    # ------------------------------------------------------------------

    def _workflow(self) -> None:
        try:
            log.info("=== Run started ===")
            self._led.working()
            success = self._run()
            if success:
                log.info("=== Run succeeded ===")
                self._led.success()
            else:
                log.warning("=== Run failed ===")
                self._led.error()
        except Exception:
            log.exception("Unhandled exception in workflow")
            self._led.error()
        finally:
            self._clear_tmp()
            self._led.idle()
            self._busy.release()
            log.info("Idle — waiting for button press")

    def _run(self) -> bool:
        cfg = self._cfg
        n = cfg.openai.stickers_per_run
        tmp = Path(cfg.app.tmp_dir)
        tmp.mkdir(parents=True, exist_ok=True)

        # 1. Generate prompts.
        log.info("Generating %d prompt(s)…", n)
        prompts = self._prompt_gen.generate(n)

        # 2. Call OpenAI in parallel.
        log.info("Calling OpenAI image API (%d parallel requests)…", n)
        paths: List[Optional[Path]] = asyncio.run(
            generate_all(prompts, cfg, tmp)
        )

        # 3. Collect successes.
        good = [p for p in paths if p is not None]
        log.info("%d/%d images generated successfully", len(good), n)

        if len(good) < cfg.openai.min_stickers_to_print:
            log.error(
                "Only %d image(s) succeeded; need at least %d — aborting",
                len(good), cfg.openai.min_stickers_to_print,
            )
            return False

        # 4. Layout + print via PixCut-App.
        log.info("Sending %d sticker(s) to PixCut-App…", len(good))
        ok = layout_and_print(good, cfg)

        # 5. Delete generated sticker files (layout files cleaned by _clear_tmp).
        for p in good:
            try:
                p.unlink()
                log.debug("Deleted %s", p)
            except Exception as exc:
                log.warning("Could not delete %s: %s", p, exc)

        return ok

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _clear_tmp(self) -> None:
        tmp = Path(self._cfg.app.tmp_dir)
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
            log.debug("Cleared %s", tmp)

    def _handle_signal(self, signum, frame) -> None:
        log.info("Signal %d received — shutting down", signum)
        self._shutdown.set()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    cfg = cfg_module.load(Path("config.toml"))
    _setup_logging(cfg)
    App(cfg).run()


if __name__ == "__main__":
    main()
