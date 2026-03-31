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
The sticker must display the text "AI is not art" prominently.
The sticker must also include the subtext "AI generated image".
Transparent background — no background color, gradient, or fill outside the sticker.
Single unified sticker silhouette with one continuous outer border (white or clearly defined).
No detached floating elements, no internal islands that could become separate cut paths.
No shadows, glow, or gradients outside the sticker boundary.
Flat top-down printable composition, suitable for physical sticker printing and die-cutting.
All text and design elements contained within the main sticker shape.\
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
