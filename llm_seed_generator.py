import asyncio
import json
import logging
import random
import re
import urllib.request
from collections import Counter

import config
from syntax_validator import SyntaxValidator

logger = logging.getLogger(__name__)

# Typed placeholders -> the field group each one draws from. Keeping this map in
# sync with the prompt is what makes the categorized-placeholder system real.
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

# Reverse lookup: concrete field -> its group, so failure-feedback can
# down-weight exactly the fields that keep showing up in losers.
_FIELD_TO_GROUP = {}
for _group, _fields in config.FIELD_GROUPS.items():
    for _field in _fields:
        _FIELD_TO_GROUP[_field] = _group

# Operator applied DIRECTLY to the {FIELD} placeholder of a breadth-first simple
# template (rank in "rank({FIELD})"; ts_delta in "ts_decay_linear(ts_delta(
# {FIELD}, ...), ...)"). Paired with a field's affinity family this is what
# decides whether a template economically suits the field it is pinned to.
_TEMPLATE_FIELD_OPERATOR = re.compile(r"(\w+)\s*\(\s*\{FIELD\}")


class _EmptyFieldPool(Exception):
    """Raised by `_choose_field` when its candidate pool is empty -- e.g. a typed
    placeholder like {PRICE} appears in a template during a dataset-restricted
    run (WQ_DATASET_ID set) where that entire field GROUP is empty. Callers in
    the materialize passes catch this and DISCARD the offending template instead
    of (a) crashing with 'IndexError: Cannot choose from an empty sequence', or
    (b) substituting a fake field name -- which would slip past the syntax
    validator (it does NOT check field existence) and waste a live BRAIN
    simulation on a nonsense alpha."""


def _choose_field(pool, memory=None):
    """Pick a field from `pool`, biased by (Upgrade #2) per-group seeding weights
    that favour slow / alternative data (fundamental, sentiment, relationship,
    macro) and (experience memory) penalties for fields over-represented in
    recent failures. Falls back to a uniform choice if weights vanish.

    Raises _EmptyFieldPool when `pool` is empty so a restricted run discards the
    template rather than crashing or fabricating a field."""
    if not pool:
        raise _EmptyFieldPool()
    weights = []
    for f in pool:
        gw = config.SEED_FIELD_GROUP_WEIGHTS.get(_FIELD_TO_GROUP.get(f), 1.0)
        pen = memory.field_penalty.get(f, 1.0) if (memory and memory.field_penalty) else 1.0
        weights.append(max(0.0, gw * pen))
    if sum(weights) <= 0:
        return random.choice(pool)
    return random.choices(pool, weights=weights, k=1)[0]


class ExperienceMemory:
    """Failure-feedback store (the 'Critic's Memory').

    Turns a list of recently-failed alphas -- each a dict {expression, reason}
    -- into two steering signals:
      * per-field discouragement weights, so the deterministic grammar engine
        samples away from fields that dominate recent failures; and
      * a compact human-readable digest appended to the LLM prompt so a model,
        when enabled, avoids re-proposing known-bad structures.
    This is the 'frequent-subtree / failure avoidance' idea that keeps the
    population diverse and stops the factory wasting simulations on losers.
    """

    def __init__(self, records):
        self.records = list(records or [])
        self.field_penalty = self._compute_field_penalty()

    @staticmethod
    def _record_expr(rec):
        if isinstance(rec, dict):
            return rec.get("expression", "")
        return str(rec)

    def _compute_field_penalty(self):
        if not config.EXPERIENCE_MEMORY_ENABLED or not self.records:
            return {}
        counts = Counter()
        for rec in self.records:
            expr = self._record_expr(rec)
            for field in _FIELD_TO_GROUP:
                if re.search(rf"\b{re.escape(field)}\b", expr):
                    counts[field] += 1
        if not counts:
            return {}
        worst = [f for f, _ in counts.most_common(config.EXPERIENCE_MAX_BANNED_FIELDS)]
        return {f: config.EXPERIENCE_BANNED_FIELD_PENALTY for f in worst}

    def weighted_choice(self, pool):
        """random.choice, but biased away from fields over-represented in
        recent failures."""
        if not self.field_penalty:
            return random.choice(pool)
        weights = [self.field_penalty.get(f, 1.0) for f in pool]
        if sum(weights) <= 0:
            return random.choice(pool)
        return random.choices(pool, weights=weights, k=1)[0]

    def loser_set(self):
        return {self._record_expr(r) for r in self.records if self._record_expr(r)}

    def prompt_digest(self, limit=15):
        if not self.records:
            return ""
        lines = []
        for rec in self.records[-limit:]:
            expr = self._record_expr(rec)
            reason = rec.get("reason", "unspecified") if isinstance(rec, dict) else "unspecified"
            lines.append(f"- {expr}  -> FAILED: {reason}")
        return "\n".join(lines)


class LLMSeedGenerator:
    """Seed generator with a deterministic grammar/template backbone and an
    OPTIONAL, pluggable LLM idea-injector (off by default).

    Design rationale (backed by the alpha-mining literature, e.g. Alpha-GPT and
    AlphaAgent): an LLM is useful for *novel ideas* but unreliable as the sole
    source of *good* alphas, and a weak model must never bottleneck seeding. So
    the grammar engine always produces a valid, diverse, economically-motivated
    population; the LLM, when configured, only contributes a bounded fraction.
    Both consume the ExperienceMemory failure-feedback signal.
    """

    def __init__(self):
        self.provider = config.LLM_PROVIDER
        self.model_name = config.LLM_MODEL
        self.llm_enabled = bool(config.SEED_LLM_ENABLED) and self._provider_ready()
        if config.SEED_LLM_ENABLED and not self.llm_enabled:
            logger.warning(
                "SEED_LLM_ENABLED is set but provider %r is not configured; "
                "falling back to the deterministic grammar engine only.", self.provider)
        elif not config.SEED_LLM_ENABLED:
            logger.info("LLM seeding disabled (recommended default); using the grammar engine.")
        else:
            logger.info("LLM seeding enabled via provider %r (model %r).", self.provider, self.model_name)

    def _provider_ready(self):
        return {
            "gemini": bool(config.GEMINI_API_KEY),
            "openai": bool(config.OPENAI_API_KEY),
            "anthropic": bool(config.ANTHROPIC_API_KEY),
            "ollama": bool(config.OLLAMA_BASE_URL),
        }.get(self.provider, False)

    # --- placeholder filling -------------------------------------------------
    @classmethod
    def fill_template(cls, template, memory=None):
        """Substitute every typed placeholder with a concrete, type-correct
        value. Each occurrence is randomized independently; when a memory is
        supplied, field choices steer away from recent failures."""
        def _sub(match):
            token = match.group(0)
            kind = match.group(1)
            if token in _PLACEHOLDER_GROUPS:
                pool = config.FIELD_GROUPS[_PLACEHOLDER_GROUPS[token]]
                return _choose_field(pool, memory)
            if kind == "FIELD":
                return _choose_field(config.DATA_DICTIONARY, memory)
            if kind == "LOOKBACK_SHORT":
                return str(random.choice([5, 10, 15, 20, 22]))
            if kind == "LOOKBACK_LONG":
                return str(random.choice([60, 120, 180, 252]))
            if kind == "NEUTRALIZATION":
                # Bias toward coarse SECTOR/MARKET groups on sparse data to avoid
                # the "weight too concentrated / too few instruments" failure;
                # still explores SUBINDUSTRY/INDUSTRY. Uniform if unavailable.
                if hasattr(config, "choose_neutralization"):
                    return config.choose_neutralization()
                return random.choice(config.NEUTRALIZATIONS)
            return token

        return _PLACEHOLDER_TOKEN.sub(_sub, template)

    @classmethod
    def fill_template_for_field(cls, template, field, memory=None):
        """Like fill_template, but PINS the {FIELD} placeholder to one specific
        data field (the remaining lookback / neutralization placeholders still
        randomize). Used by the breadth-first pass to guarantee coverage of
        every field -- including niche ones -- instead of leaving field choice
        to weighted random sampling."""
        seeded = template.replace("{FIELD}", field)
        return cls.fill_template(seeded, memory)

    def _materialize(self, templates, want, memory=None, avoid_motifs=None):
        """Fill, validate and de-duplicate templates into canonical
        expressions, skipping tautologies and known losers. When `avoid_motifs`
        is supplied (Frequent Subtree Avoidance, Upgrade #3), candidates carrying
        an over-used winner motif are kept only with probability
        config.FSA_PENALTY so the population keeps exploring un-crowded shapes."""
        seen = set()
        results = []
        avoid = memory.loser_set() if memory else set()
        attempts = max(1, (want // max(1, len(templates))) + 2)
        for template in templates:
            if not isinstance(template, str) or not template.strip():
                continue
            for _ in range(attempts):
                try:
                    filled = self.fill_template(template, memory)
                except _EmptyFieldPool:
                    break  # template needs an empty field group; discard it
                ok, canonical = SyntaxValidator.parse_and_validate(filled)
                if (ok and canonical not in seen and canonical not in avoid
                        and not SyntaxValidator.is_tautology(canonical)):
                    if (avoid_motifs and config.FSA_ENABLED
                            and SyntaxValidator.structural_motifs(canonical) & avoid_motifs
                            and random.random() > config.FSA_PENALTY):
                        continue
                    seen.add(canonical)
                    results.append(canonical)
                if len(results) >= want:
                    return results
        return results

    @staticmethod
    def _template_field_operator(template):
        """Operator applied DIRECTLY to the {FIELD} placeholder of a simple
        template -- the transform that actually touches the data field (rank in
        "rank({FIELD})"; ts_delta in "ts_decay_linear(ts_delta({FIELD}, ...),
        ...)"). Returns "" when the template has no {FIELD} (affinity then stays
        neutral)."""
        m = _TEMPLATE_FIELD_OPERATOR.search(template or "")
        return m.group(1) if m else ""

    def _affinity_weighted_templates(self, templates, field, k=2):
        """Pick up to k DISTINCT templates for `field`, biased by the SOFT
        operator-field affinity prior (config.operator_affinity_weight): a
        template whose field-operator suits the field's family is up-weighted, a
        discouraged one down-weighted, everything else neutral (1.0). Falls back
        to a uniform shuffle when affinity is disabled, the family is unknown, or
        the weights vanish, so exploration is never lost and NOTHING is ever
        removed from the pool (WQ_AFFINITY_ENABLED=0 restores pure-random
        pairing)."""
        pool = list(templates)
        if not pool:
            return []
        family = config.field_family(field) if hasattr(config, "field_family") else None
        if not family or not getattr(config, "AFFINITY_ENABLED", False):
            random.shuffle(pool)
            return pool[:k]
        chosen = []
        remaining = pool[:]
        for _ in range(min(k, len(remaining))):
            weights = [max(0.0, config.operator_affinity_weight(
                self._template_field_operator(t), family)) for t in remaining]
            if sum(weights) <= 0:
                pick = random.choice(remaining)
            else:
                pick = random.choices(remaining, weights=weights, k=1)[0]
            chosen.append(pick)
            remaining.remove(pick)
        return chosen

    def _materialize_breadth_first(self, templates, want, memory=None, avoid_motifs=None):
        """Field-COVERAGE seeding: walk the ENTIRE data dictionary and build one
        simple alpha per field, so niche / under-used fields are exercised
        instead of being drowned out by the weighted random field sampling in
        fill_template. This is the 'wide and simple' discovery stage -- where
        uncrowded, submittable alphas are most likely to surface early.

        The per-field template choice is biased by the SOFT operator-field
        affinity prior so a field is paired with transforms that economically
        suit its family (an options/IV field favours rank/zscore/decay over a
        first-difference; an earnings step field favours ts_delta) instead of a
        coin-flip -- closing the last spot where the engine 'randomly fits
        operators to fields'. Nothing is forbidden: every template stays in the
        pool, so exploration is preserved and WQ_AFFINITY_ENABLED=0 restores the
        old uniform-random pairing."""
        templates = [t for t in (templates or []) if isinstance(t, str) and t.strip()]
        if not templates or want <= 0:
            return []
        avoid = memory.loser_set() if memory else set()
        fields = list(config.DATA_DICTIONARY)
        random.shuffle(fields)
        seen = set()
        results = []
        for field in fields:
            for template in self._affinity_weighted_templates(templates, field, k=2):
                try:
                    filled = self.fill_template_for_field(template, field, memory)
                except _EmptyFieldPool:
                    continue  # this template needs an empty group; try another
                ok, canonical = SyntaxValidator.parse_and_validate(filled)
                if (ok and canonical not in seen and canonical not in avoid
                        and not SyntaxValidator.is_tautology(canonical)):
                    if (avoid_motifs and config.FSA_ENABLED
                            and SyntaxValidator.structural_motifs(canonical) & avoid_motifs
                            and random.random() > config.FSA_PENALTY):
                        continue
                    seen.add(canonical)
                    results.append(canonical)
                    break
            if len(results) >= want:
                break
        return results

    def _load_seed_pool(self):
        """Load field_harvester.py's seed_pool.json: a ranked list of raw
        fields, each with ready-to-fill simple templates. Returns [] when the
        file is absent / malformed so seeding silently falls back to the static
        dictionary."""
        path = getattr(config, "SEED_POOL_PATH", "")
        if not path:
            return []
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return []
        return data if isinstance(data, list) else []

    def _materialize_from_seed_pool(self, want, memory=None, avoid_motifs=None):
        """Data-first seeding: walk seed_pool.json in priority order and build up
        to config.SEED_POOL_MAX_PER_FIELD validated alphas per field from its
        precomputed templates (filling {NEUTRALIZATION}/{LOOKBACK_*}). This is
        the 'wide and simple over BETTER data' stage -- field choice is delegated
        to the harvester's value / crowding / coverage ranking instead of the
        static dictionary. Allowing a few templates per field (instead of
        exactly one) lets each field's family + term-structure-spread templates
        actually participate at generation 0 rather than being decided by a
        single shuffle."""
        pool = self._load_seed_pool()
        if not pool or want <= 0:
            return []
        avoid = memory.loser_set() if memory else set()
        max_per_field = max(1, int(getattr(config, "SEED_POOL_MAX_PER_FIELD", 1)))
        seen = set()
        results = []
        for entry in pool:
            templates = entry.get("templates") if isinstance(entry, dict) else None
            if not templates:
                continue
            choices = list(templates)
            random.shuffle(choices)
            made = 0
            for template in choices:
                try:
                    filled = self.fill_template(template, memory)
                except _EmptyFieldPool:
                    continue  # template needs an empty field group; skip it
                ok, canonical = SyntaxValidator.parse_and_validate(filled)
                if (ok and canonical not in seen and canonical not in avoid
                        and not SyntaxValidator.is_tautology(canonical)):
                    if (avoid_motifs and config.FSA_ENABLED
                            and SyntaxValidator.structural_motifs(canonical) & avoid_motifs
                            and random.random() > config.FSA_PENALTY):
                        continue
                    seen.add(canonical)
                    results.append(canonical)
                    made += 1
                    if len(results) >= want or made >= max_per_field:
                        break  # cap templates per field to keep the pass breadth-first
            if len(results) >= want:
                break
        return results

    # --- prompt --------------------------------------------------------------
    def _build_prompt(self, count, memory):
        operators = ", ".join(config.ALLOWED_OPERATORS)
        dictionary = "\n".join(
            f"   {group}: {', '.join(fields)}" for group, fields in config.FIELD_GROUPS.items()
        )
        lines = [
            "You are a quantitative researcher inventing alpha signals for "
            "WorldQuant BRAIN (FASTEXPR). For EACH idea, reason about the economic "
            "mechanism first, then write the expression that captures it.",
            "",
            "Rules:",
            f"1. Use ONLY these operators (exact names): {operators}.",
            "2. Prefer the TYPED placeholders below; each is auto-substituted with a "
            "correct field of that type: {PRICE} {VOLATILITY} {FUNDAMENTAL} "
            "{SENTIMENT} {MACRO} {SIZE} {MOMENTUM} {RELATIONSHIP} {FIELD}. You MAY "
            "also use the EXACT real field names listed below when an idea needs two "
            "specific related fields (e.g. a call/put or term-structure spread). "
            "Never invent field names.",
            "3. For time windows use {LOOKBACK_SHORT} / {LOOKBACK_LONG} (never bare "
            "numbers for windows).",
            "4. DIVERSITY IS THE GOAL. Do NOT make every signal a plain "
            "group_neutralize(rank(<one field>)) -- that shape is already "
            "over-represented and will be discarded. Vary the OUTER structure across "
            "ideas: cross-sectional (rank, zscore, normalize), time-series (ts_delta, "
            "ts_mean, ts_zscore, ts_rank, ts_regression, ts_decay_linear), comparative "
            "spreads (subtract / divide of two related fields), non-linear (sign, abs, "
            "log, power) and conditional (trade_when, if_else) shapes. Neutralize "
            "where it helps using {NEUTRALIZATION} as the group, not identically every "
            "time.",
            "5. The most VALUABLE and least crowded ideas exploit related-field "
            "structure -- prioritize them:",
            "   - Term structure / curve: near-minus-far of one family, e.g. default "
            "curve steepness subtract(mdl53_jc5_5year, mdl53_jc5_1year), and its "
            "inversion; ride a flattening curve, fade a steepening one.",
            "   - Cross-instrument skew: option call vs put, e.g. group_neutralize("
            "ts_mean(subtract(implied_volatility_call_30, implied_volatility_put_30), "
            "3), bucket(rank(cap), range=\"0,1,0.1\")).",
            "   - Acceleration / inflection: a second derivative via ts_delta of a "
            "ts_delta, optionally gated by sign(), for credit-quality or earnings "
            "momentum the market underreacts to.",
            "6. Each expression must be a single valid FASTEXPR expression on one line.",
            "",
            "Real data fields by category (use these EXACT names only):",
            dictionary,
        ]
        digest = memory.prompt_digest() if memory else ""
        if digest:
            lines += [
                "",
                "These recent ideas FAILED on the live server. Do NOT repeat their "
                "structures or the field/operator combinations behind them -- propose "
                "structurally different mechanisms:",
                digest,
            ]
        lines += [
            "",
            "Return STRICT JSON only: an array of exactly " + str(count) + " objects, "
            "each with two string keys -- \"rationale\" (a one-sentence economic "
            "thesis) and \"expression\" (the FASTEXPR signal). No text outside the "
            "JSON array.",
        ]
        return "\n".join(lines)

    # --- provider dispatch ---------------------------------------------------
    def _call_llm(self, count, memory):
        if not self.llm_enabled:
            return []
        prompt = self._build_prompt(count, memory)
        try:
            if self.provider == "gemini":
                text = self._call_gemini(prompt)
            elif self.provider == "openai":
                text = self._call_openai(prompt)
            elif self.provider == "anthropic":
                text = self._call_anthropic(prompt)
            elif self.provider == "ollama":
                text = self._call_ollama(prompt)
            else:
                return []
        except Exception as e:
            logger.error(f"LLM seed generation failed ({self.provider}): {e}")
            return []
        items = self._parse_llm_items(text)
        for expr, rationale in items[:5]:
            if rationale:
                logger.info("LLM alpha idea: %s  <=  %s", expr, rationale)
        if items:
            logger.info("LLM proposed %d candidate expression(s).", len(items))
        return [expr for expr, _ in items]

    def _call_gemini(self, prompt):
        import google.generativeai as genai
        genai.configure(api_key=config.GEMINI_API_KEY)
        model = genai.GenerativeModel(self.model_name)
        return model.generate_content(prompt).text or ""

    def _call_openai(self, prompt):
        from openai import OpenAI
        client = OpenAI(api_key=config.OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.9,
        )
        return resp.choices[0].message.content or ""

    def _call_anthropic(self, prompt):
        import anthropic
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=self.model_name,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")

    def _call_ollama(self, prompt):
        payload = json.dumps(
            {"model": self.model_name, "prompt": prompt, "stream": False}
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{config.OLLAMA_BASE_URL.rstrip('/')}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as fh:
            return json.loads(fh.read().decode("utf-8")).get("response", "")

    @staticmethod
    def _extract_json_array(text):
        text = (text or "").strip()
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if not match:
            logger.warning("LLM response contained no JSON array.")
            return None
        try:
            parsed = json.loads(match.group(0))
        except Exception:
            return None
        return parsed if isinstance(parsed, list) else None

    @classmethod
    def _parse_llm_items(cls, text):
        """Parse the LLM response into [(expression, rationale)] tuples. Accepts
        the rich object form with "expression"/"rationale" keys AND a bare array
        of expression strings (back-compat). Items lacking a usable expression
        are dropped."""
        parsed = cls._extract_json_array(text)
        if parsed is None:
            return []
        items = []
        for item in parsed:
            if isinstance(item, str):
                expr, rationale = item.strip(), ""
            elif isinstance(item, dict):
                expr = (item.get("expression") or item.get("expr")
                        or item.get("alpha") or "").strip()
                rationale = str(item.get("rationale") or item.get("reason") or "").strip()
            else:
                continue
            if expr:
                items.append((expr, rationale))
        return items

    @classmethod
    def _parse_json_array(cls, text):
        """Back-compat shim: expression strings only."""
        return [expr for expr, _ in cls._parse_llm_items(text)]

    # --- public API ----------------------------------------------------------
    def generate_seeds_sync(self, count, experience=None, avoid_motifs=None):
        if count <= 0:
            return []
        memory = ExperienceMemory(experience)
        avoid_motifs = set(avoid_motifs or ())
        results = []
        # Optional LLM idea-injection (off by default). Bounded fraction; the
        # grammar engine always supplies the remainder so a weak/missing model
        # can never starve or bottleneck the population.
        if self.llm_enabled:
            quota = max(1, int(count * config.LLM_SEED_FRACTION))
            templates = self._call_llm(quota, memory)
            if templates:
                results += self._materialize(templates, quota, memory, avoid_motifs)
        # Deterministic grammar backbone fills whatever the LLM did not. Lead
        # with the breadth-first "wide and simple" pass -- one simple alpha per
        # data field -- so niche / under-used fields are actually exercised (the
        # highest-ROI place to find uncrowded, submittable alphas) before falling
        # back to the richer, more complex QUANT_TEMPLATES library.
        # Data-first pass: lead with the harvested seed pool (raw, uncrowded,
        # high-value fields ranked from the LIVE catalog) when available, so
        # seeding tracks the real data landscape rather than the static dict.
        # Reserve a structural-diversity quota for the rich QUANT_TEMPLATES.
        # With a large harvested catalog the data-first seed pool has more fields
        # than POPULATION_SIZE, so without this reservation the single-field
        # seed-pool / breadth-first passes would consume the entire population and
        # starve every multi-field / turnover-gated / term-structure-spread shape
        # out of generation 0. Cap the data-first passes at (count - quant_quota),
        # then ALWAYS let QUANT_TEMPLATES fill the reserved slots (and backfill
        # anything the data-first passes left short).
        quant_quota = int(count * getattr(config, "SEED_QUANT_FRACTION", 0.0))
        data_target = max(len(results), count - quant_quota)
        # Coverage-first (gen-0 field breadth): guarantee one simple alpha for
        # EVERY field via the breadth-first pass over the entire dictionary
        # BEFORE the priority-ranked seed pool spends the remaining budget on
        # extra variants of the top fields. Without this, when there are more
        # fields than the seed budget the priority-ordered seed pool exhausts the
        # budget on the top handful of fields and the long tail is never seeded
        # -- the generation-0 field-crowding failure (e.g. 73 / 371 fields).
        coverage_first = getattr(config, "SEED_COVERAGE_FIRST", True)
        if (coverage_first and len(results) < data_target
                and getattr(config, "BREADTH_FIRST_SEEDING", True)):
            results += self._materialize_breadth_first(
                config.SIMPLE_TEMPLATES, data_target - len(results), memory, avoid_motifs)
        if len(results) < data_target and getattr(config, "SEED_POOL_FIRST", True):
            results += self._materialize_from_seed_pool(
                data_target - len(results), memory, avoid_motifs)
        if (not coverage_first and len(results) < data_target
                and getattr(config, "BREADTH_FIRST_SEEDING", True)):
            results += self._materialize_breadth_first(
                config.SIMPLE_TEMPLATES, data_target - len(results), memory, avoid_motifs)
        if len(results) < count:
            results += self._materialize(config.QUANT_TEMPLATES, count - len(results), memory, avoid_motifs)
        # Order-preserving de-dup, then cap.
        return list(dict.fromkeys(results))[:count]

    async def generate_seeds(self, count, experience=None, avoid_motifs=None):
        return await asyncio.to_thread(self.generate_seeds_sync, count, experience, avoid_motifs)