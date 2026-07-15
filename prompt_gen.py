from __future__ import annotations

"""
Prompt generation with strong diversity, anti-repeat logic, and controlled
creative instability.

For each button press we generate N prompts. Each prompt independently samples
from multiple orthogonal pools so the model has room to do something specific,
unexpected, and expressive instead of converging on the same safe sticker idea.

We still keep hard production constraints for die-cut stickers, but we add:
- multiple prompt scaffolds
- wildcard creative modifiers
- material / provenance fiction
- era / time-drift
- render / framing mode
- text treatment
- tension / contradiction
- anti-default instructions
- optional political framing
- concept families
- rarity-weighted chaos modifiers

A rolling history window prevents recently used items from recurring too often.
"""

import logging
import random
from collections import deque
from typing import Deque, Dict, List

from config import Config

log = logging.getLogger("aina.prompt")

PROMPT_TEMPLATES = [
    """\
Create a sticker illustration with the following creative direction:
- Style: {style}
- Composition: {composition}
- Tone: {tone}
- Concept family: {concept_family}
- Core concept: {concept}
- Sticker silhouette shape: {sticker_shape}
- Render/framing mode: {render_mode}
- Material/provenance feel: {materiality}
- Era/provenance: {era}
- Text treatment: {text_treatment}
- Tension to embrace: {tension}
- Political framing: {political_mode}
- Wildcard modifier: {wildcard}
- Rare modifier: {rare_modifier}
- Anti-default: {anti_default}
""",
    """\
Design a visually distinctive sticker.
Use a {style} approach, a {composition} layout, and a {tone} mood.
The image should belong to the {concept_family} family and center on {concept}.
The sticker's outer silhouette should be: {sticker_shape}.
Render it like {render_mode}. Make it feel like {materiality} and as if it came from {era}.
Treat the text like {text_treatment}. Mix in this contradiction: {tension}.
Apply this political framing: {political_mode}.
Inject this wildcard quality: {wildcard}.
Add this rare creative push: {rare_modifier}.
Avoid this default move: {anti_default}.
""",
    """\
Make a sticker that feels specific, surprising, and memorable rather than generic.
Start from {concept} in the {concept_family} family.
Express it through {style}, using a {composition} composition and a {tone} tone.
The sticker shape itself should be: {sticker_shape}.
Frame or render it as {render_mode}.
Make it feel physically like {materiality} and culturally or historically like {era}.
Let the typography feel like {text_treatment}.
Build in this productive contradiction: {tension}.
Political framing: {political_mode}.
Creative wildcard: {wildcard}.
Rare modifier: {rare_modifier}.
Negative steering: {anti_default}.
""",
]

PRODUCTION_REQUIREMENTS = """\
CORE MESSAGE REQUIREMENTS:
- The text "AI is not art" must appear prominently and be clearly legible.
- The subtext "AI generated image" must also appear and be readable.
- The overall subject matter may be literal, symbolic, scenic, abstract, political, mundane, photorealistic, painterly, or surreal, but the sticker must still clearly contain that text.

CREATIVE QUALITY REQUIREMENTS:
- Make the result visually distinctive, specific, and memorable.
- Avoid the most obvious or generic interpretation of the concept.
- Do not default to bland clipart unless the selected direction clearly calls for it.
- The sticker can be funny, serious, beautiful, eerie, political, documentary-like, commercial, scenic, or strange.
- Rich internal detail is encouraged: texture, depth, lighting, gradients, shading, reflections, and 3D rendering are allowed inside the sticker silhouette.
- The design should look compelling as a real physical sticker someone would want to keep.

CUTLINE REQUIREMENTS — critical for physical die-cutting:
- Transparent background. Absolutely no color, fill, shadow, glow, haze, or gradient outside the sticker boundary.
- The sticker silhouette does NOT need to be rectangular. It can follow the shape of the artwork, be circular, organic, irregular, or any custom form — as long as it is a single unified shape.
- Single unified silhouette with one continuous hard outer edge.
- The outer edge must be fully opaque — no feathering, anti-aliasing halos, or semi-transparent pixels at the boundary.
- No drop shadows, outer glow, smoke, particles, reflections, or effects that extend outside the sticker shape.
- No detached floating elements. No separate islands. Keep it as one solid cuttable sticker object.
- No internal transparent holes that would complicate cutting.
- All artwork, text, and decoration must remain entirely within the sticker silhouette.
- The final result must read as a top-down printable sticker image, even if the internal content is photorealistic or three-dimensional.
"""


class PromptGenerator:
    def __init__(self, cfg: Config):
        self._pools: Dict[str, List[str]] = {
            "style": list(cfg.prompts.styles),
            "composition": list(cfg.prompts.compositions),
            "tone": list(cfg.prompts.tones),
            "concept": list(cfg.prompts.concepts),
            "concept_family": list(getattr(cfg.prompts, "concept_families", [])),
            "sticker_shape": list(getattr(cfg.prompts, "sticker_shapes", [])),
            "wildcard": list(getattr(cfg.prompts, "wildcards", [])),
            "materiality": list(getattr(cfg.prompts, "materialities", [])),
            "era": list(getattr(cfg.prompts, "eras", [])),
            "render_mode": list(getattr(cfg.prompts, "render_modes", [])),
            "text_treatment": list(getattr(cfg.prompts, "text_treatments", [])),
            "tension": list(getattr(cfg.prompts, "tensions", [])),
            "anti_default": list(getattr(cfg.prompts, "anti_defaults", [])),
            "political_mode": list(getattr(cfg.prompts, "political_modes", [])),
            "rare_modifier": list(getattr(cfg.prompts, "rare_modifiers", [])),
        }
        window = cfg.app.prompt_history_window
        self._history: dict[str, Deque[str]] = {
            k: deque(maxlen=window) for k in self._pools if self._pools[k]
        }

    def generate(self, n: int = 3) -> List[str]:
        """Return n distinct prompts with strong diversity and anti-repeat logic."""
        if n <= 0:
            return []

        selections: dict[str, List[str]] = {}
        for key, pool in self._pools.items():
            if not pool:
                continue
            selections[key] = self._sample_avoiding_recent(pool, self._history[key], n)

        prompts: List[str] = []
        for i in range(n):
            combo = {k: selections[k][i] for k in selections}
            combo.setdefault("concept_family", self._infer_concept_family(combo.get("concept", "")))
            template = random.choice(PROMPT_TEMPLATES)
            prompt = f"{template.format(**combo).rstrip()}\n\n{PRODUCTION_REQUIREMENTS}"
            prompts.append(prompt)
            log.info(
                "Prompt %d: style=%r composition=%r tone=%r concept_family=%r concept=%r render_mode=%r materiality=%r era=%r text_treatment=%r tension=%r political_mode=%r wildcard=%r rare_modifier=%r anti_default=%r",
                i + 1,
                combo.get("style"),
                combo.get("composition"),
                combo.get("tone"),
                combo.get("concept_family"),
                combo.get("concept"),
                combo.get("render_mode"),
                combo.get("materiality"),
                combo.get("era"),
                combo.get("text_treatment"),
                combo.get("tension"),
                combo.get("political_mode"),
                combo.get("wildcard"),
                combo.get("rare_modifier"),
                combo.get("anti_default"),
            )

        for key, pool in selections.items():
            for item in pool:
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
                pick = random.choice(pool)
            chosen.append(pick)

        return chosen

    def _infer_concept_family(self, concept: str) -> str:
        """Best-effort fallback if concept families are not configured."""
        value = concept.lower()

        family_keywords = {
            "nature": [
                "flower", "tree", "forest", "jungle", "desert", "mountain",
                "canyon", "river", "waterfall", "ocean", "reef", "island",
                "sunrise", "sunset", "sky", "storm", "snow", "rain",
            ],
            "space": [
                "planet", "space", "astronaut", "spaceship", "satellite",
                "rocket", "galaxy", "orbit", "alien",
            ],
            "animals": [
                "cat", "dog", "bird", "fish", "horse", "cow", "sheep",
                "insect", "butterfly", "spider", "lizard", "frog", "owl", "eagle",
            ],
            "people": [
                "person", "people", "crowd", "portrait", "family", "child", "figure",
            ],
            "food": [
                "fruit", "vegetable", "meal", "dessert", "ice cream", "pizza",
                "burger", "coffee", "tea", "drink", "bottle", "glass",
            ],
            "places": [
                "house", "cabin", "city", "street", "parking", "station",
                "airport", "office", "library", "bookstore", "coffee shop", "kitchen",
            ],
            "technology": [
                "circuit", "keyboard", "computer", "monitor", "server", "cable",
                "electronics", "robot", "printer",
            ],
            "vehicles": [
                "vehicle", "car", "truck", "motorcycle", "bicycle", "airplane",
                "boat", "submarine", "train",
            ],
            "systems_and_politics": [
                "warning", "compliance", "certification", "policy", "boardroom",
                "surveillance", "governance", "risk", "privacy", "protest", "museum",
            ],
            "fantasy_and_sci_fi": [
                "dragon", "alien", "monster", "fantasy", "sci-fi", "creature",
            ],
            "abstract": [
                "abstract", "pattern", "shapes", "grid", "spiral", "noise", "glitch",
                "dot", "line", "nothingness", "empty",
            ],
        }

        for family, keywords in family_keywords.items():
            if any(keyword in value for keyword in keywords):
                return family

        return "general"
