import asyncio
import json
import logging
import random
import re

import google.generativeai as genai

import config
from syntax_validator import SyntaxValidator

logger = logging.getLogger(__name__)

# Typed placeholders -> the field group each one draws from. Keeping this map in
# sync with the prompt is what makes the categorized-placeholder system real
# (previously the LLM was only ever told about a single untyped {FIELD}, so the
# typing was dead code).
_PLACEHOLDER_GROUPS = {
    "{PRICE}": "price",
    "{VOLATILITY}": "volatility",
    "{FUNDAMENTAL}": "fundamental",
    "{SENTIMENT}": "sentiment",
    "{MACRO}": "macro",
    "{SIZE}": "size",
    "{MOMENTUM}": "momentum",
    "{RELATIONSHIP}": "relationship",
}

_PLACEHOLDER_TOKEN = re.compile(
    r"\{(PRICE|VOLATILITY|FUNDAMENTAL|SENTIMENT|MACRO|SIZE|MOMENTUM|RELATIONSHIP|FIELD|LOOKBACK_SHORT|LOOKBACK_LONG|NEUTRALIZATION)\}"
)


class LLMSeedGenerator:
    def __init__(self):
        self.enabled = bool(config.GEMINI_API_KEY)
        if self.enabled:
            genai.configure(api_key=config.GEMINI_API_KEY)
            self.model = genai.GenerativeModel(config.LLM_MODEL)
        else:
            self.model = None
            logger.warning("GEMINI_API_KEY not set; LLM seeding will fall back to built-in templates.")

    # --- placeholder filling -------------------------------------------------
    @staticmethod
    def _random_field(group: str) -> str:
        return random.choice(config.FIELD_GROUPS[group])

    @classmethod
    def fill_template(cls, template: str) -> str:
        """Substitute every typed placeholder with a concrete, type-correct value.
        Each occurrence is randomized independently."""
        def _sub(match: re.Match) -> str:
            token = match.group(0)
            kind = match.group(1)
            if token in _PLACEHOLDER_GROUPS:
                return cls._random_field(_PLACEHOLDER_GROUPS[token])
            if kind == "FIELD":
                return random.choice(config.DATA_DICTIONARY)
            if kind == "LOOKBACK_SHORT":
                return str(random.choice([5, 10, 15, 20, 22]))
            if kind == "LOOKBACK_LONG":
                return str(random.choice([60, 120, 180, 252]))
            if kind == "NEUTRALIZATION":
                return random.choice(config.NEUTRALIZATIONS)
            return token

        return _PLACEHOLDER_TOKEN.sub(_sub, template)

    def _materialize(self, templates, want: int):
        """Fill, validate and de-duplicate templates into canonical expressions."""
        seen = set()
        results = []
        # Several fill attempts per template since fields are randomized.
        attempts = max(1, (want // max(1, len(templates))) + 2)
        for template in templates:
            if not isinstance(template, str) or not template.strip():
                continue
            for _ in range(attempts):
                filled = self.fill_template(template)
                ok, canonical = SyntaxValidator.parse_and_validate(filled)
                if ok and canonical not in seen and not SyntaxValidator.is_tautology(canonical):
                    seen.add(canonical)
                    results.append(canonical)
                if len(results) >= want:
                    return results
        return results

    # --- prompt --------------------------------------------------------------
    def _build_prompt(self, count: int) -> str:
        operators = ", ".join(config.ALLOWED_OPERATORS)
        return (
            "You are a quantitative researcher writing alpha signals in WorldQuant "
            "FASTEXPR. Produce diverse, economically-motivated signal TEMPLATES.\n\n"
            "Rules:\n"
            f"1. Use ONLY these operators (exact names): {operators}.\n"
            "2. Do NOT write raw data field names. Use ONLY these TYPED placeholders, "
            "which will be substituted automatically with the correct field type:\n"
            "   {PRICE} {VOLATILITY} {FUNDAMENTAL} {SENTIMENT} {MACRO} {SIZE} "
            "{MOMENTUM} {RELATIONSHIP} {FIELD}\n"
            "3. For time windows use {LOOKBACK_SHORT} and {LOOKBACK_LONG} (never bare numbers for windows).\n"
            "4. Wrap the final signal in group_neutralize(<expr>, {NEUTRALIZATION}).\n"
            "5. Each template must be a single valid FASTEXPR expression on one line.\n\n"
            f"Return STRICT JSON: an array of exactly {count} strings, nothing else."
        )

    def _call_llm(self, count: int):
        if not self.enabled:
            return []
        try:
            response = self.model.generate_content(self._build_prompt(count))
            text = (response.text or "").strip()
            match = re.search(r"\[.*\]", text, re.DOTALL)
            if not match:
                logger.warning("LLM response contained no JSON array.")
                return []
            parsed = json.loads(match.group(0))
            if not isinstance(parsed, list):
                return []
            # Defensive: keep only non-empty strings.
            return [item for item in parsed if isinstance(item, str) and item.strip()]
        except Exception as e:
            logger.error(f"LLM seed generation failed: {e}")
            return []

    # --- public API ----------------------------------------------------------
    def generate_seeds_sync(self, count: int):
        templates = self._call_llm(count)
        results = self._materialize(templates, count) if templates else []
        if len(results) < count:
            # Top up from the curated built-in templates so we always return
            # something usable even if the LLM is unavailable or stingy.
            results += self._materialize(config.QUANT_TEMPLATES, count - len(results))
        return results[:count]

    async def generate_seeds(self, count: int):
        return await asyncio.to_thread(self.generate_seeds_sync, count)