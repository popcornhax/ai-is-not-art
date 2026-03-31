"""
Config loader for ai-is-not-art.
Reads config.toml, provides typed access with sane defaults.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore


@dataclass
class OpenAIConfig:
    api_key: str = ""
    model: str = "gpt-image-1"
    size: str = "1024x1024"
    timeout_s: int = 120
    retry_count: int = 2
    stickers_per_run: int = 3
    min_stickers_to_print: int = 1


@dataclass
class GPIOConfig:
    button_pin: int = 17
    led_pin: int = 18
    led_brightness: int = 128


@dataclass
class PixcutConfig:
    app_path: str = "/home/sticker/pixcut-app"
    log_dir: str = "/home/sticker/ai-is-not-art/run-logs"
    dpi: int = 300
    margin_mm: float = 2.0
    padding_mm: float = 3.0
    left_margin_mm: float = 3.0
    kp: int = 42


@dataclass
class AppConfig:
    tmp_dir: str = "/tmp/ai-is-not-art"
    log_file: str = "/home/sticker/ai-is-not-art/app.log"
    prompt_history_window: int = 10
    debug_mode: bool = False
    kiosk_url: str = "http://localhost:8000"


@dataclass
class PromptConfig:
    styles: List[str] = field(default_factory=lambda: [
        "punk zine collage",
        "protest poster",
        "vintage comic",
        "children's illustration",
        "corporate safety poster parody",
        "graffiti style",
        "screenprint poster",
        "faux museum label",
        "technical diagram parody",
        "handmade outsider-art",
        "crude digital aesthetic",
    ])
    compositions: List[str] = field(default_factory=lambda: [
        "emblem", "badge", "banner", "protest sign",
        "collage", "icon cluster", "warning label",
        "certification seal", "single subject", "symbolic object",
    ])
    tones: List[str] = field(default_factory=lambda: [
        "playful", "rebellious", "absurd", "corporate",
        "satirical", "snarky", "wholesome",
    ])
    concepts: List[str] = field(default_factory=lambda: [
        "robot making art",
        "art tools protesting",
        "fake museum label",
        "fake product packaging",
        "compliance warning label",
        "printer printing itself",
        "human vs machine contrast",
        "parody certification",
        "gallery rejection scene",
    ])


@dataclass
class Config:
    openai: OpenAIConfig = field(default_factory=OpenAIConfig)
    gpio: GPIOConfig = field(default_factory=GPIOConfig)
    pixcut: PixcutConfig = field(default_factory=PixcutConfig)
    app: AppConfig = field(default_factory=AppConfig)
    prompts: PromptConfig = field(default_factory=PromptConfig)


def _apply(dc, data: dict):
    """Shallow-apply dict values onto a dataclass instance."""
    for key, val in data.items():
        if hasattr(dc, key):
            setattr(dc, key, val)


def load(path: Path = Path("config.toml")) -> Config:
    cfg = Config()
    if not path.exists():
        return cfg
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    if "openai" in raw:
        _apply(cfg.openai, raw["openai"])
    if "gpio" in raw:
        _apply(cfg.gpio, raw["gpio"])
    if "pixcut" in raw:
        _apply(cfg.pixcut, raw["pixcut"])
    if "app" in raw:
        _apply(cfg.app, raw["app"])
    if "prompts" in raw:
        _apply(cfg.prompts, raw["prompts"])
    return cfg
