"""
Prompt generation with diversity and anti-repeat logic.

For each button press we generate N prompts. Each prompt independently
samples one item from each pool (style, composition, tone, concept).
Within a single run we sample without replacement across prompts so
all three get different styles, compositions, etc.

A rolling history window prevents the same items from appearing in
consecutive runs.
"""
from __future__ import annotations

import logging
import random
from collections import deque
from typing import Deque, List

from config import Config

log = logging.getLogger("aina.prompt")

PROMPT_TEMPLATE = """\
{style} sticker design. {composition} composition. {tone} tone. Concept: {concept}.

VISUAL REQUIREMENTS — make this striking and memorable:
- Bold, high-contrast colors. Strong graphic impact. Not flat or boring.
- Rich detail inside the sticker: texture, depth, dramatic lighting or shading are encouraged.
- Visually interesting and energetic — this should look great as a physical sticker.
- The text "AI is not art" must appear prominently and be clearly legible.
- The subtext "AI generated image" must also appear, smaller but readable.

CUTLINE REQUIREMENTS — critical for physical die-cutting:
- Transparent background. Absolutely no color, fill, or gradient outside the sticker boundary.
- Single unified silhouette with one continuous hard outer edge.
- The outer edge must be fully opaque — no feathering, anti-aliasing halos, or semi-transparent pixels at the boundary.
- No drop shadows, outer glow, or any effect that extends outside the sticker shape.
- No detached floating elements. No internal transparent islands. One solid shape.
- All artwork, text, and decoration contained entirely within the sticker silhouette.\
"""


class PromptGenerator:
    def __init__(self, cfg: Config):
        self._pools = {
            "style": list(cfg.prompts.styles),
            "composition": list(cfg.prompts.compositions),
            "tone": list(cfg.prompts.tones),
            "concept": list(cfg.prompts.concepts),
        }
        window = cfg.app.prompt_history_window
        self._history: dict[str, Deque[str]] = {
            k: deque(maxlen=window) for k in self._pools
        }

    def generate(self, n: int = 3) -> List[str]:
        """Return n distinct prompts with varied style/composition/tone/concept."""
        selections: dict[str, List[str]] = {}
        for key, pool in self._pools.items():
            selections[key] = self._sample_avoiding_recent(pool, self._history[key], n)

        prompts = []
        for i in range(n):
            combo = {k: selections[k][i] for k in self._pools}
            prompt = PROMPT_TEMPLATE.format(**combo)
            prompts.append(prompt)
            log.info(
                "Prompt %d: style=%r composition=%r tone=%r concept=%r",
                i + 1, combo["style"], combo["composition"],
                combo["tone"], combo["concept"],
            )

        # Record this run's selections in history.
        for key in self._pools:
            for item in selections[key]:
                self._history[key].append(item)

        return prompts

    def _sample_avoiding_recent(
        self,
        pool: List[str],
        history: Deque[str],
        n: int,
    ) -> List[str]:
        """
        Sample n items from pool without replacement, preferring items not
        recently used. Falls back to the full pool if it's too small.
        """
        recent = set(history)
        preferred = [x for x in pool if x not in recent]
        fallback = [x for x in pool if x in recent]

        chosen: List[str] = []
        remaining_preferred = list(preferred)
        remaining_fallback = list(fallback)

        for _ in range(n):
            if remaining_preferred:
                pick = random.choice(remaining_preferred)
                remaining_preferred.remove(pick)
            elif remaining_fallback:
                pick = random.choice(remaining_fallback)
                remaining_fallback.remove(pick)
            else:
                # Pool exhausted; allow repeats.
                pick = random.choice(pool)
            chosen.append(pick)

        return chosen
