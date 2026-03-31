"""
PixCut-App integration: lay out sticker PNGs and send to printer.

Normal mode:  layout → print via USB.
Debug mode:   layout → copy PNGs into kiosk stickers dir → load into kiosk
              canvas via REST API → log preview URL. No physical printing.

Imports PixCut-App's Python API directly via sys.path.
No changes to PixCut-App required.
"""
from __future__ import annotations

import logging
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
import json
from pathlib import Path
from typing import List

from config import Config

log = logging.getLogger("aina.printer")

# Prefix used for sticker filenames copied into the kiosk stickers dir.
_DEBUG_PREFIX = "ai_gen_"


def layout_and_print(img_paths: List[Path], cfg: Config) -> bool:
    """
    Lay out img_paths and either print (normal) or preview in kiosk (debug).
    Returns True on success, False on failure.
    """
    if cfg.app.debug_mode:
        return _debug_preview(img_paths, cfg)
    return _do_print(img_paths, cfg)


# ---------------------------------------------------------------------------
# Normal mode: layout + USB print
# ---------------------------------------------------------------------------

def _do_print(img_paths: List[Path], cfg: Config) -> bool:
    _inject_pixcut_path(cfg.pixcut.app_path)

    try:
        from pixcut.image_to_cut import process_images  # type: ignore
    except ImportError as exc:
        log.error("Cannot import pixcut.image_to_cut from %s: %s", cfg.pixcut.app_path, exc)
        return False

    result = _layout(img_paths, cfg)
    if result is None:
        return False

    tmp = Path(cfg.app.tmp_dir)
    jpg_path = tmp / "layout.jpg"
    plt_path = tmp / "layout.plt"
    if not _save_layout(result, jpg_path, plt_path):
        return False

    try:
        from pixcut.transport import discover_pixcut, USBTransport  # type: ignore
        from pixcut.logging_utils import SessionLogger               # type: ignore
        from pixcut.orchestrator import JobConfig, run_job_session   # type: ignore
    except ImportError as exc:
        log.error("Cannot import pixcut transport/orchestrator: %s", exc)
        return False

    log.info("Connecting to printer…")
    try:
        transport = USBTransport(discover_pixcut())
    except Exception as exc:
        log.error("Printer not found: %s", exc)
        return False

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


# ---------------------------------------------------------------------------
# Debug mode: copy PNGs into kiosk stickers dir, load into canvas via API
# ---------------------------------------------------------------------------

def _debug_preview(img_paths: List[Path], cfg: Config) -> bool:
    """
    Copy generated images into the PixCut kiosk stickers directory and
    load them into the canvas via the kiosk REST API so they can be
    previewed at http://<host>:8000 without touching the printer.
    """
    log.info("[DEBUG] Skipping USB print — loading into kiosk canvas instead")

    stickers_dir = Path(cfg.pixcut.app_path) / "stickers"
    if not stickers_dir.is_dir():
        log.error("[DEBUG] Kiosk stickers dir not found: %s", stickers_dir)
        return False

    # Remove any leftover ai_gen_* files from a previous debug run.
    for old in stickers_dir.glob(f"{_DEBUG_PREFIX}*.png"):
        old.unlink(missing_ok=True)

    # Copy generated PNGs in with a recognisable prefix.
    copied: List[str] = []
    for i, src in enumerate(img_paths):
        dest_name = f"{_DEBUG_PREFIX}{i:02d}_{src.name}"
        dest = stickers_dir / dest_name
        shutil.copy2(src, dest)
        copied.append(dest_name)
        log.info("[DEBUG] Copied %s → %s", src.name, dest_name)

    if not copied:
        log.error("[DEBUG] No images to load into kiosk")
        return False

    base = cfg.app.kiosk_url.rstrip("/")

    # Clear whatever is currently on the canvas.
    if not _kiosk_post(base, "/api/canvas/clear", {}):
        log.warning("[DEBUG] Could not clear kiosk canvas — continuing anyway")

    # Add each sticker to the canvas.
    loaded = 0
    for name in copied:
        if _kiosk_post(base, "/api/canvas/add", {"name": name, "count": 1, "scale": 1.0}):
            log.info("[DEBUG] Added %s to canvas", name)
            loaded += 1
        else:
            log.warning("[DEBUG] Failed to add %s to canvas", name)

    if loaded == 0:
        log.error("[DEBUG] Could not load any stickers into kiosk canvas")
        return False

    log.info("[DEBUG] Preview ready at %s  (%d sticker(s) on canvas)", base, loaded)
    log.info("[DEBUG] Tip: open the URL in a browser to see the layout and manually trigger print")
    return True


def _kiosk_post(base: str, path: str, data: dict) -> bool:
    """POST JSON to the kiosk API. Returns True on HTTP 2xx."""
    url = base + path
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return 200 <= resp.status < 300
    except Exception as exc:
        log.debug("Kiosk API call %s failed: %s", path, exc)
        return False


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _layout(img_paths: List[Path], cfg: Config):
    """Run PixCut-App layout. Returns LayoutResult or None on failure."""
    _inject_pixcut_path(cfg.pixcut.app_path)
    try:
        from pixcut.image_to_cut import process_images  # type: ignore
    except ImportError as exc:
        log.error("Cannot import pixcut.image_to_cut: %s", exc)
        return None

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
        return None

    if not results or not results[0].placed:
        log.error("Layout produced no placed stickers (images may be too large for the sheet)")
        return None

    log.info("Layout placed %d sticker(s) on sheet", len(results[0].placed))
    return results[0]


def _save_layout(result, jpg_path: Path, plt_path: Path) -> bool:
    try:
        result.composite.save(str(jpg_path), "JPEG", quality=95)
        plt_path.write_text(result.cut_plt, encoding="ascii")
        log.info("Layout files written: %s, %s", jpg_path, plt_path)
        return True
    except Exception as exc:
        log.error("Failed to write layout files: %s", exc)
        return False


def _inject_pixcut_path(app_path: str) -> None:
    if app_path not in sys.path:
        sys.path.insert(0, app_path)
