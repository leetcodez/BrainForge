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
from forge2_storage import atomic_json, as_tuples
from forge2_expression import field_tokens


class DatasetBandit:
    def __init__(self, state_path, rng=None):
        self.state_path = Path(state_path)
        self.rng = rng or random.Random(F2.RANDOM_SEED)
        self.arms = {}
        self.observations = {}
        self.manual = {}
        if self.state_path.exists():
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            if data.get("version") == 2:
                self.arms = data["arms"]
                self.observations = data.get("observations", {})
                self.manual = data.get("manual", {})
                if rng is None and data.get("rng_state"):
                    self.rng.setstate(as_tuples(data["rng_state"]))
            else:
                # Legacy posterior cannot establish exactly-once provenance.
                # Reset to its saved priors, then replay scored DB outcomes.
                self.arms = data
                for arm in self.arms.values():
                    arm["a"], arm["b"] = arm["prior_a"], arm["prior_b"]
        self.last_learning = {"scored": 0, "changed": 0, "unknown": 0}

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
        explored = self.rng.sample(candidates, floor)
        remaining = [c for c in candidates if c not in set(explored)]
        draws = []
        for ds in remaining:
            arm = self.arms.get(ds)
            if arm is None:
                draws.append((self.rng.betavariate(1.0, F2.BANDIT_PRIOR_BETA), ds))
            else:
                draws.append((self.rng.betavariate(max(arm["a"], 1e-3), max(arm["b"], 1e-3)), ds))
        draws.sort(key=lambda t: t[0], reverse=True)
        chosen = explored + [ds for _, ds in draws[: max(0, k - floor)]]
        return chosen[:k]

    # --- updates -------------------------------------------------------------------
    def _recompute(self):
        counts = {}
        for obs in self.observations.values():
            c = counts.setdefault(obs["dataset"], [0.0, 0.0])
            c[0 if obs["success"] else 1] += 1.0
        for ds, values in self.manual.items():
            c = counts.setdefault(ds, [0.0, 0.0])
            c[0] += values[0]; c[1] += values[1]
        for ds, arm in self.arms.items():
            good, bad = counts.get(ds, (0.0, 0.0))
            # Cap EVIDENCE, preserving the prior and deterministic replay.
            evidence = good + bad
            scale = min(1.0, F2.BANDIT_COUNT_CAP / evidence) if evidence else 1.0
            arm["a"] = arm["prior_a"] + good * scale
            arm["b"] = arm["prior_b"] + bad * scale

    def update(self, dataset, success):
        self.ensure_arm(dataset)
        counts = self.manual.setdefault(dataset, [0.0, 0.0])
        counts[0 if success else 1] += 1.0
        self._recompute()

    def update_from_db(self, db_path, field_to_dataset, since_rowid=0):
        """Reconcile completed outcomes, including rows enriched IN PLACE.

        The legacy row cursor is returned for compatibility, but is never used
        to exclude older rows. The v2 observation ledger makes replay and reward
        revisions idempotent. A complete scored-row snapshot also withdraws
        observations that became unscored, unverifiable, or were deleted.
        Missing files/schema/read errors are not authoritative empty snapshots.
        Campaign ownership is held by campaign_lock.
        """
        db_path = Path(db_path).resolve()
        if not db_path.exists():
            return since_rowid
        conn = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)
        try:
            columns = {r[1] for r in conn.execute("PRAGMA table_info(alpha_population)")}
            needed = {"id","expression","sharpe","turnover","is_qualified","failed_checks","fitness"}
            if not needed <= columns:
                raise ValueError("Bandit requires qualification-aware schema; missing "
                                 + ", ".join(sorted(needed-columns)))
            rows = conn.execute("SELECT id,expression,sharpe,turnover,is_qualified,failed_checks "
                                "FROM alpha_population WHERE sharpe IS NOT NULL AND fitness IS NOT NULL "
                                "ORDER BY id").fetchall()
        finally:
            conn.close()
        stats = {"scored": len(rows), "changed": 0, "unknown": 0}
        max_id = int(since_rowid)
        current = {}
        for rowid, expr, sharpe, turnover, qualified, failures in rows:
            max_id = max(max_id, int(rowid))
            key = str(db_path) + "#" + str(rowid)
            old = self.observations.get(key)
            # Attribution of historical rows survives active-vocabulary rotation.
            ds = old["dataset"] if old else self.map_expression(expr,field_to_dataset)
            if not ds or failures is None or "CHECKS_UNVERIFIABLE" in failures:
                stats["unknown"] += 1
                continue
            self.ensure_arm(ds)
            lo,hi = F2.BANDIT_TURNOVER_BAND
            success = bool(qualified and not failures and sharpe >= F2.BANDIT_SUCCESS_SHARPE
                           and turnover is not None and lo <= turnover <= hi)
            obs = {"dataset":ds,"success":success}
            current[key] = obs
            if obs != old:
                stats["changed"] += 1
        # Reconcile only this source. rpartition tolerates '#' inside DB paths;
        # a prefix match could accidentally censor another database's evidence.
        retired = [key for key in self.observations
                   if key.rpartition("#")[0] == str(db_path) and key not in current]
        for key in retired:
            del self.observations[key]
        stats["changed"] += len(retired)
        self.observations.update(current)
        self._recompute()
        self.last_learning = stats
        return max_id

    @staticmethod
    def map_expression(expression, field_to_dataset):
        """Dominant dataset of an expression: the dataset of its most frequent
        known field token."""
        counts = {}
        for tok in set(field_tokens(expression)):
            ds = field_to_dataset.get(tok)
            if ds:
                counts[ds] = counts.get(ds, 0) + 1
        if not counts:
            return None
        return max(counts.items(), key=lambda kv: kv[1])[0]

    # --- persistence -----------------------------------------------------------------
    def save(self):
        atomic_json(self.state_path, {"version":2, "arms":self.arms,
                                      "observations":self.observations,
                                      "manual":self.manual, "rng_state":self.rng.getstate()})

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
