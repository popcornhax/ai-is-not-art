"""
PixCut-App integration: lay out sticker PNGs and send to printer.

Imports PixCut-App's Python API directly via sys.path — no subprocess,
no changes to PixCut-App required.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import List

from config import Config

log = logging.getLogger("aina.printer")


def layout_and_print(img_paths: List[Path], cfg: Config) -> bool:
    """
    Lay out img_paths onto a 4×7" sheet and send the job to the PixCut printer.
    Returns True on success, False on any failure.
    """
    _inject_pixcut_path(cfg.pixcut.app_path)

    # --- Layout ---
    try:
        from pixcut.image_to_cut import process_images  # type: ignore
    except ImportError as exc:
        log.error("Cannot import pixcut.image_to_cut from %s: %s", cfg.pixcut.app_path, exc)
        return False

    log.info("Laying out %d sticker(s)…", len(img_paths))
    try:
        results = process_images(
            img_paths,
            dpi=cfg.pixcut.dpi,
            margin_mm=cfg.pixcut.margin_mm,
            padding_mm=cfg.pixcut.padding_mm,
            left_margin_mm=cfg.pixcut.left_margin_mm,
            kp=cfg.pixcut.kp,
            paginate=False,
            bg_white=False,
        )
    except Exception as exc:
        log.error("Layout failed: %s", exc)
        return False

    if not results:
        log.error("Layout produced no output (all stickers too large?)")
        return False

    result = results[0]
    if not result.placed:
        log.error("No stickers fit on the canvas")
        return False

    log.info("Layout placed %d sticker(s) on sheet", len(result.placed))

    # --- Save layout files to tmp dir ---
    tmp = Path(cfg.app.tmp_dir)
    tmp.mkdir(parents=True, exist_ok=True)
    jpg_path = tmp / "layout.jpg"
    plt_path = tmp / "layout.plt"

    try:
        result.composite.save(str(jpg_path), "JPEG", quality=95)
        plt_path.write_text(result.cut_plt, encoding="ascii")
        log.info("Layout written: %s, %s", jpg_path, plt_path)
    except Exception as exc:
        log.error("Failed to write layout files: %s", exc)
        return False

    # --- Print ---
    try:
        from pixcut.transport import discover_pixcut, USBTransport  # type: ignore
        from pixcut.logging_utils import SessionLogger               # type: ignore
        from pixcut.orchestrator import JobConfig, run_job_session   # type: ignore
    except ImportError as exc:
        log.error("Cannot import pixcut transport/orchestrator: %s", exc)
        return False

    log.info("Connecting to printer…")
    try:
        usb_cfg = discover_pixcut()
        transport = USBTransport(usb_cfg)
    except Exception as exc:
        log.error("Printer not found: %s", exc)
        return False

    log.dir = Path(cfg.pixcut.log_dir)
    Path(cfg.pixcut.log_dir).mkdir(parents=True, exist_ok=True)
    logger = SessionLogger(Path(cfg.pixcut.log_dir))

    log.info("Submitting print job…")
    try:
        job_result = run_job_session(
            transport=transport,
            logger=logger,
            jpg_path=jpg_path,
            plt_path=plt_path,
            job_cfg=JobConfig(kp=cfg.pixcut.kp),
            mode="combo",
        )
    except Exception as exc:
        log.error("Print job raised an exception: %s", exc)
        return False

    if job_result.get("error"):
        log.error("Print job failed: %s", job_result.get("error"))
        return False

    log.info("Print job complete (job_id=%s)", job_result.get("job_id"))
    return True


def _inject_pixcut_path(app_path: str) -> None:
    if app_path not in sys.path:
        sys.path.insert(0, app_path)
