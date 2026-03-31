"""
Parallel OpenAI image generation.

Fires N concurrent requests, retries individual failures, validates
each result is a transparent PNG. Returns a list of Path | None —
None for any image that ultimately failed.
"""
from __future__ import annotations

import asyncio
import base64
import logging
from pathlib import Path
from typing import List, Optional

from config import Config

log = logging.getLogger("aina.image_gen")


async def generate_all(
    prompts: List[str],
    cfg: Config,
    tmp_dir: Path,
) -> List[Optional[Path]]:
    """Fire all prompts in parallel; return one Path (or None) per prompt."""
    tasks = [
        _generate_one(prompt, idx, cfg, tmp_dir)
        for idx, prompt in enumerate(prompts)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    successes = sum(1 for r in results if r is not None)
    log.info("Image generation complete: %d/%d succeeded", successes, len(prompts))
    return list(results)


async def _generate_one(
    prompt: str,
    idx: int,
    cfg: Config,
    tmp_dir: Path,
) -> Optional[Path]:
    """Generate one image with retry. Returns Path on success, None on failure."""
    import openai  # imported here so the module loads on non-Pi without the dep
    client = openai.AsyncOpenAI(api_key=cfg.openai.api_key)

    out_path = tmp_dir / f"sticker_{idx}.png"
    last_exc: Optional[Exception] = None

    for attempt in range(1, cfg.openai.retry_count + 2):  # 1 initial + retries
        try:
            log.info("Image %d attempt %d — calling API", idx + 1, attempt)
            response = await asyncio.wait_for(
                client.images.generate(
                    model=cfg.openai.model,
                    prompt=prompt,
                    n=1,
                    size=cfg.openai.size,
                    background="transparent",
                    output_format="png",
                ),
                timeout=cfg.openai.timeout_s,
            )
            image_data = response.data[0]

            # The API may return b64_json or a URL depending on the model.
            if image_data.b64_json:
                png_bytes = base64.b64decode(image_data.b64_json)
            elif image_data.url:
                import httpx
                async with httpx.AsyncClient() as http:
                    r = await http.get(image_data.url, timeout=cfg.openai.timeout_s)
                    r.raise_for_status()
                    png_bytes = r.content
            else:
                raise ValueError("API returned neither b64_json nor url")

            _validate_png(png_bytes, idx)
            out_path.write_bytes(png_bytes)
            log.info("Image %d saved → %s (%d bytes)", idx + 1, out_path, len(png_bytes))
            return out_path

        except asyncio.TimeoutError:
            log.warning("Image %d attempt %d timed out after %ds", idx + 1, attempt, cfg.openai.timeout_s)
            last_exc = asyncio.TimeoutError()
        except Exception as exc:
            log.warning("Image %d attempt %d failed: %s", idx + 1, attempt, exc)
            last_exc = exc

        if attempt <= cfg.openai.retry_count:
            await asyncio.sleep(1.5 * attempt)  # brief back-off before retry

    log.error("Image %d failed after %d attempts: %s", idx + 1, cfg.openai.retry_count + 1, last_exc)
    return None


def _validate_png(data: bytes, idx: int) -> None:
    """Raise ValueError if data is not a valid PNG with an alpha channel."""
    if len(data) < 8 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Image {idx + 1}: response is not a PNG")

    # Check for alpha channel by reading the colour type byte from the IHDR chunk.
    # PNG IHDR is at byte 16 after the PNG signature (8) + length (4) + 'IHDR' (4).
    # Colour type byte is at offset 25.
    if len(data) < 26:
        raise ValueError(f"Image {idx + 1}: PNG too short to contain IHDR")

    color_type = data[25]
    # PNG colour types with alpha: 4 (greyscale+alpha), 6 (RGBA).
    if color_type not in (4, 6):
        raise ValueError(
            f"Image {idx + 1}: PNG colour type {color_type} has no alpha channel"
        )

    if len(data) < 100:
        raise ValueError(f"Image {idx + 1}: PNG suspiciously small ({len(data)} bytes)")
