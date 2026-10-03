Part of **Forge v2 — Consultant Overhaul (Sept 2026)**. Thompson-sampling bandit over dataset arms: priors seeded from pyramid multiplier (optimism) and crowding (pessimism), updated after every burst by reading the engine's own SQLite database (no engine hooks needed), with a forgetting cap so arms stay adaptive and an exploration floor so fresh datasets keep entering the rotation. Drives which datasets enter each vocabulary rotation — sample efficiency is the scarcest resource at \~3 concurrent simulations.
```python
"""Forge2 Thompson-sampling bandit over dataset arms (finding #10).

The search space is ~10^8 (fields x axes) and the simulation budget is ~10^3
per burst, so WHERE the engine looks matters more than how fast it looks.
Each candidate dataset is an arm; the reward is "this burst produced a keeper
from that dataset". Thompson sampling naturally balances exploiting datasets
that produce keepers against exploring high-multiplier virgin datasets, whose
priors are seeded optimistically from the catalog itself.

Stdlib-only. State is a small JSON file per campaign; updates are derived by
reading the engine's own SQLite database after each burst (no engine hooks
needed, so the GA core stays untouched).
"""

import json
import math
import random
import sqlite3
from pathlib import Path

import forge2_config as F2


class DatasetBandit:
    def __init__(self, state_path):
        self.state_path = Path(state_path)
        self.arms = {}  # dataset -> {"a": float, "b": float, "prior_a": float, "prior_b": float}
        if self.state_path.exists():
            try:
                self.arms = json.loads(self.state_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self.arms = {}

    # --- priors ------------------------------------------------------------------
    def ensure_arm(self, dataset, avg_multiplier=1.0, avg_alpha_count=0.0):
        """Create the arm if missing, seeding an optimism prior from the catalog:
        high pyramid multiplier raises alpha0 (optimism), crowding raises beta0
        (pessimism). Existing arms are never re-seeded."""
        if dataset in self.arms:
            return
        prior_a = 1.0 + F2.BANDIT_PRIOR_MULT_WEIGHT * max(0.0, avg_multiplier - 1.0)
        prior_b = F2.BANDIT_PRIOR_BETA + F2.BANDIT_PRIOR_CROWD_WEIGHT * math.log10(
            1.0 + max(0.0, avg_alpha_count)
        )
        self.arms[dataset] = {
            "a": prior_a, "b": prior_b, "prior_a": prior_a, "prior_b": prior_b,
        }

    # --- selection -----------------------------------------------------------------
    def sample_arms(self, candidates, k):
        """Pick k datasets from `candidates` (list of dataset ids). Thompson draw
        per arm; a small uniform-random exploration floor guarantees fresh
        datasets keep entering the rotation."""
        candidates = [c for c in dict.fromkeys(candidates) if c]
        if not candidates:
            return []
        k = min(k, len(candidates))
        floor = min(F2.BANDIT_EXPLORE_FLOOR, k)
        explored = random.sample(candidates, floor)
        remaining = [c for c in candidates if c not in set(explored)]
        draws = []
        for ds in remaining:
            arm = self.arms.get(ds)
            if arm is None:
                draws.append((random.betavariate(1.0, F2.BANDIT_PRIOR_BETA), ds))
            else:
                draws.append((random.betavariate(max(arm["a"], 1e-3), max(arm["b"], 1e-3)), ds))
        draws.sort(key=lambda t: t[0], reverse=True)
        chosen = explored + [ds for _, ds in draws[: max(0, k - floor)]]
        return chosen[:k]

    # --- updates -------------------------------------------------------------------
    def update(self, dataset, success):
        arm = self.arms.get(dataset)
        if arm is None:
            self.ensure_arm(dataset)
            arm = self.arms[dataset]
        if success:
            arm["a"] += 1.0
        else:
            arm["b"] += 1.0
        # Forgetting cap: rescale so old evidence decays and arms stay adaptive.
        total = arm["a"] + arm["b"]
        if total > F2.BANDIT_COUNT_CAP:
            scale = F2.BANDIT_COUNT_CAP / total
            arm["a"] *= scale
            arm["b"] *= scale

    def update_from_db(self, db_path, field_to_dataset, since_rowid=0):
        """Fold the engine's own results back into the bandit. Reads rows with a
        real score from alpha_population (rowid > since_rowid), maps each row's
        expression to a dataset via `field_to_dataset` (longest-token match), and
        counts a success when the row clears the keeper bar. Returns the max
        rowid seen so the caller can checkpoint incremental updates."""
        db_path = Path(db_path)
        if not db_path.exists():
            return since_rowid
        try:
            conn = sqlite3.connect(str(db_path))
        except sqlite3.Error:
            return since_rowid
        max_rowid = since_rowid
        lo, hi = F2.BANDIT_TURNOVER_BAND
        try:
            cur = conn.execute(
                "SELECT id, expression, sharpe, turnover FROM alpha_population "
                "WHERE sharpe IS NOT NULL AND id > ? ORDER BY id ASC",
                (int(since_rowid),),
            )
            for rowid, expression, sharpe, turnover in cur.fetchall():
                max_rowid = max(max_rowid, int(rowid))
                ds = self.map_expression(expression, field_to_dataset)
                if ds is None:
                    continue
                ok_turnover = turnover is not None and lo <= float(turnover) <= hi
                success = (sharpe is not None
                           and float(sharpe) >= F2.BANDIT_SUCCESS_SHARPE
                           and ok_turnover)
                self.update(ds, success)
        except sqlite3.Error:
            pass
        finally:
            conn.close()
        return max_rowid

    @staticmethod
    def map_expression(expression, field_to_dataset):
        """Dominant dataset of an expression: the dataset of its most frequent
        known field token."""
        counts = {}
        for tok in _identifier_tokens(expression):
            ds = field_to_dataset.get(tok)
            if ds:
                counts[ds] = counts.get(ds, 0) + 1
        if not counts:
            return None
        return max(counts.items(), key=lambda kv: kv[1])[0]

    # --- persistence -----------------------------------------------------------------
    def save(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self.arms, indent=1), encoding="utf-8")

    def summary(self, top=12):
        rows = []
        for ds, arm in self.arms.items():
            mean = arm["a"] / max(arm["a"] + arm["b"], 1e-9)
            evidence = (arm["a"] - arm["prior_a"]) + (arm["b"] - arm["prior_b"])
            rows.append((mean, evidence, ds))
        rows.sort(reverse=True)
        return [
            {"dataset": ds, "posterior_mean": round(m, 4), "evidence": round(e, 1)}
            for m, e, ds in rows[:top]
        ]


def _identifier_tokens(expression):
    out, cur = [], []
    for ch in expression or "":
        if ch.isalnum() or ch == "_":
            cur.append(ch)
        elif cur:
            out.append("".join(cur))
            cur = []
    if cur:
        out.append("".join(cur))
    return out
```