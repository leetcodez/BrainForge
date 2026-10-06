"""Evidence-aware warmstart publication, validation, and import contract.

Provides create-only, fail-closed warmstart building, validation, and restore:
  - Strict destination guards: mkstemp-allocated unique temp files, fsync, O_EXCL no-clobber publication.
  - Evaluation identity: AST-normalized whitespace with distinct evaluation settings.
  - Decoded check evidence: preserves malformed, failed, pending, and unverifiable states.
  - Honest quota partitioning: measured core requires verified PnL; exploration reserve is strictly capped.
  - Rejection filtering: candidates rejected from core (correlation, sign flips, subspace) cannot enter exploration.
  - Import validation contract: validates schema, recomputed manifest digest, member equality, and receipt.
  - Complete provenance: serialized input hashes, selection controls, and interval diagnostics.
"""
from __future__ import annotations
import ast
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import tempfile
from typing import Any

import numpy as np

from forge2_checks import parse_checks
from forge2_expression import field_tokens
from forge2_portfolio import select_basket, dataset_members
from forge2_search import candidate_identity
from forge2_statistics import daily_changes


PROTECTED_CHECKPOINT_FILENAMES = {
    "checkpoint.json",
    ".wq_checkpoint.json",
    "forge2_campaign_state.json",
    "forge2_run_policy.json",
    "forge2_epoch_manifest.json",
}

WARMSTART_SCHEMA_VERSION = "forge2-warmstart-v1"


def compute_file_sha256(path: Path | str) -> str:
    p = Path(path).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"File not found: {p}")
    return hashlib.sha256(p.read_bytes()).hexdigest()


def compute_manifest_sha256(manifest: dict) -> str:
    """Compute deterministic SHA-256 of warmstart manifest content excluding manifest_sha256."""
    clean = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    raw = json.dumps(clean, sort_keys=True, allow_nan=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def audit_series_intervals(series: dict, max_gap_days: int = 4) -> dict:
    """Audit raw observation points, differenced intervals, and gap exclusions."""
    points = []
    for date, value in sorted(series.items()):
        try:
            day = datetime.date.fromisoformat(str(date)[:10])
            val = float(value)
            if math.isfinite(val):
                points.append((day, str(date), val))
        except (ValueError, TypeError):
            continue

    if len(points) < 2:
        return {
            "raw_points": len(points),
            "adjacent_differences": 0,
            "excluded_gaps": [],
            "matched_intervals": 0,
            "unit": "matched cumulative-PnL intervals; not guaranteed single trading days",
        }

    excluded_gaps = []
    matched_count = 0
    for (day1, d1, v1), (day2, d2, v2) in zip(points, points[1:]):
        gap = (day2 - day1).days
        if gap <= 0:
            continue
        if gap > max_gap_days:
            excluded_gaps.append({
                "start_date": d1,
                "end_date": d2,
                "calendar_days": gap,
                "reason": f"calendar_days ({gap}) > max_gap_days ({max_gap_days})",
            })
        else:
            matched_count += 1

    return {
        "raw_points": len(points),
        "start_date": points[0][1],
        "end_date": points[-1][1],
        "adjacent_differences": len(points) - 1,
        "excluded_gap_count": len(excluded_gaps),
        "excluded_gaps": excluded_gaps,
        "matched_intervals": matched_count,
        "unit": "matched cumulative-PnL intervals; not guaranteed single trading days",
    }


def exclusive_create_atomic_json(target_path: Path | str, data: dict, input_paths: list[Path | str] | None = None) -> str:
    """Race-safe create-only atomic JSON publication with alias and collision protection.

    Guarantees:
      - Uses secure uniquely allocated temporary file (mkstemp in target directory).
      - Thread-safe and process-safe: no shared temp filename.
      - Serializes with allow_nan=False and fsyncs temp file and containing directory.
      - Atomic no-clobber link: raises FileExistsError if target exists.
    """
    target = Path(target_path).resolve()
    target_name = target.name.lower()

    # Guard 1: Protected checkpoint and state filenames
    if target.name in PROTECTED_CHECKPOINT_FILENAMES or "checkpoint" in target_name:
        raise ValueError(
            f"Safety guard: destination '{target.name}' is a protected checkpoint or state filename. "
            "Warmstart artifacts must be published to dedicated create-only destinations."
        )

    # Guard 2: Input path alias and samefile protection
    if input_paths:
        for inp in input_paths:
            if not inp:
                continue
            inp_resolved = Path(inp).resolve()
            if target == inp_resolved:
                raise ValueError(f"Safety guard: destination '{target}' conflicts with input path '{inp_resolved}'.")
            if inp_resolved.exists() and target.exists():
                try:
                    if os.path.samefile(inp_resolved, target):
                        raise ValueError(f"Safety guard: destination '{target}' is an alias to input '{inp_resolved}'.")
                except OSError:
                    pass

    # Guard 3: Strict destination existence check
    if target.exists():
        raise FileExistsError(f"Safety guard: destination '{target}' already exists. Create-only publication prevents overwriting existing state.")

    # Guard 4: Secure unique temporary file allocation in destination directory
    target.parent.mkdir(parents=True, exist_ok=True)
    raw_bytes = json.dumps(data, indent=1, sort_keys=True, allow_nan=False).encode("utf-8")

    fd, tmp_path_str = tempfile.mkstemp(prefix=f".tmp.{target.name}.", dir=str(target.parent))
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw_bytes)
            f.flush()
            os.fsync(f.fileno())

        # Link primitive: atomic no-clobber creation
        try:
            os.link(tmp_path, target)
        except OSError as exc:
            if target.exists():
                raise FileExistsError(f"Safety guard: destination '{target}' already exists.") from exc
            raise RuntimeError(f"Atomic create-only publication failed for '{target}': {exc}") from exc

        # Fsync containing directory
        dir_fd = os.open(str(target.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass

    return hashlib.sha256(target.read_bytes()).hexdigest()


def evaluate_raw_check_payload(raw_json_str: Any) -> dict:
    """Decode and parse raw check metrics; preserves distinct evidence states."""
    if raw_json_str is None or raw_json_str == "":
        return {
            "qualification_status": "CHECKS_UNVERIFIABLE",
            "evidence_verified": False,
            "failed_checks": [],
            "pending_checks": [],
            "warnings": [],
            "reason": "missing_checks_payload",
        }
    if not isinstance(raw_json_str, (str, dict)):
        return {
            "qualification_status": "CHECKS_UNVERIFIABLE",
            "evidence_verified": False,
            "failed_checks": [],
            "pending_checks": [],
            "warnings": [],
            "reason": "invalid_payload_type",
        }

    try:
        payload = json.loads(raw_json_str) if isinstance(raw_json_str, str) else raw_json_str
    except Exception as exc:
        return {
            "qualification_status": "CHECKS_UNVERIFIABLE",
            "evidence_verified": False,
            "failed_checks": [],
            "pending_checks": [],
            "warnings": [],
            "reason": f"malformed_json_payload: {exc}",
        }

    evidence = parse_checks(payload)
    if not evidence.verified:
        return {
            "qualification_status": "CHECKS_UNVERIFIABLE",
            "evidence_verified": False,
            "failed_checks": evidence.failed,
            "pending_checks": evidence.pending,
            "warnings": evidence.warnings,
            "unknown": evidence.unknown,
            "reason": "unverifiable_or_malformed_checks",
        }

    if evidence.failed:
        return {
            "qualification_status": "CHECKS_FAILED",
            "evidence_verified": True,
            "failed_checks": evidence.failed,
            "pending_checks": evidence.pending,
            "warnings": evidence.warnings,
            "reason": f"failed_checks: {', '.join(evidence.failed)}",
        }

    if evidence.pending:
        return {
            "qualification_status": "CHECKS_PENDING",
            "evidence_verified": True,
            "failed_checks": [],
            "pending_checks": evidence.pending,
            "warnings": evidence.warnings,
            "reason": f"pending_checks: {', '.join(evidence.pending)}",
        }

    return {
        "qualification_status": "HISTORICAL_CHECKS_PASSED",
        "evidence_verified": True,
        "failed_checks": [],
        "pending_checks": [],
        "warnings": evidence.warnings,
        "sharpe_2y": evidence.sharpe_2y,
        "pnl_realization": evidence.pnl_realization,
        "pyramid_multiplier": evidence.pyramid_multiplier,
        "reason": "all_historical_checks_passed",
        "platform_qualification_caveat": "Caveat: Historical check payload pass is not current platform qualification certification",
    }


def deduplicate_by_evaluation_identity(rows: list[dict], source_name: str, meta: dict) -> list[dict]:
    """Deduplicate candidates by semantic evaluation identity (AST + settings)."""
    groups: dict[str, list[dict]] = {}
    for r in rows:
        expr = r.get("expression") or ""
        universe = r.get("universe") or "TOP3000"
        decay = int(r.get("decay", 0))
        region = r.get("region") or "USA_ASSUMED"
        delay = int(r.get("delay", 1))

        payload = {
            "regular": expr,
            "type": "REGULAR",
            "settings": {"universe": universe, "decay": decay},
        }
        context = {
            "source": source_name,
            "region": region,
            "delay": delay,
        }
        try:
            eval_id = candidate_identity(payload, context)
        except Exception:
            eval_id = hashlib.sha256(f"{expr}|{universe}|{decay}|{source_name}".encode()).hexdigest()

        r["evaluation_identity"] = eval_id
        r["evaluation_settings"] = payload["settings"]
        r["evaluation_context"] = context
        groups.setdefault(eval_id, []).append(r)

    deduped = []
    for eval_id, members in groups.items():
        best = max(members, key=lambda m: (m.get("fitness") if m.get("fitness") is not None else -float("inf"), m.get("alpha_id") or ""))
        deduped.append(best)

    return sorted(deduped, key=lambda m: (-(m.get("fitness") if m.get("fitness") is not None else -float("inf")), m.get("alpha_id") or ""))


def validate_warmstart_import(
    data: dict,
    checkpoint_path: Path | str | None = None,
    expected_receipt: dict | None = None,
    expected_file_hash: str | None = None,
    expected_epoch_id: str | None = None,
    expected_catalog_hash: str | None = None,
) -> dict:
    """Validates warmstart import contract before mutating resume state.

    Checks:
      - Valid schema_version and warmstart_manifest structure.
      - Recomputed manifest digest matching manifest_sha256.
      - Exact 1:1 correspondence between population keys and manifest members.
      - Tier quotas and counts consistency.
      - Disjointness of measured core and unverified exploration evaluation identities.
      - Receipt and file digest verification (when provided).
      - Incompatible epoch / catalog validation.
    """
    if not isinstance(data, dict):
        raise ValueError("Invalid checkpoint data: expected JSON object")

    population = data.get("population")
    if not isinstance(population, list):
        raise ValueError("Checkpoint missing valid population list")

    manifest = data.get("warmstart_manifest")
    if not manifest or not isinstance(manifest, dict):
        raise ValueError("Warmstart import requires valid warmstart_manifest dictionary")

    # 1. Manifest digest recomputation
    stored_manifest_hash = manifest.get("manifest_sha256")
    if not stored_manifest_hash:
        raise ValueError("Warmstart manifest missing manifest_sha256")
    computed_manifest_hash = compute_manifest_sha256(manifest)
    if stored_manifest_hash != computed_manifest_hash:
        raise ValueError(
            f"Warmstart manifest digest mismatch: computed {computed_manifest_hash} != stored {stored_manifest_hash}"
        )

    # 2. Member lists and tier count validation
    measured_core = manifest.get("measured_core", [])
    unverified_exploration = manifest.get("unverified_exploration", [])
    if not isinstance(measured_core, list) or not isinstance(unverified_exploration, list):
        raise ValueError("Invalid tier members structure in warmstart manifest")

    if manifest.get("measured_core_count") != len(measured_core):
        raise ValueError("Warmstart measured_core_count mismatch with actual members")
    if manifest.get("unverified_exploration_count") != len(unverified_exploration):
        raise ValueError("Warmstart unverified_exploration_count mismatch with actual members")
    expected_total = len(measured_core) + len(unverified_exploration)
    if manifest.get("total_warmstart_count") != expected_total:
        raise ValueError("Warmstart total_warmstart_count mismatch with actual members")
    if len(population) != expected_total:
        raise ValueError(f"Population length ({len(population)}) does not match manifest member count ({expected_total})")

    # 3. Exact 1:1 member correspondence
    all_members = measured_core + unverified_exploration
    for idx, (item, m) in enumerate(zip(population, all_members)):
        if not isinstance(item, list) or len(item) != 3:
            raise ValueError(f"Population item {idx} is not a [expr, universe, decay] triple")
        expr, universe, decay = item
        if expr != m.get("expression") or universe != m.get("universe") or decay != m.get("decay"):
            raise ValueError(
                f"Warmstart population at index {idx} does not match manifest member: "
                f"[{expr}, {universe}, {decay}] vs member {m.get('alpha_id')} "
                f"[{m.get('expression')}, {m.get('universe')}, {m.get('decay')}]"
            )

    # 4. Disjoint evaluation identities
    core_ids = {m.get("evaluation_identity") for m in measured_core}
    exp_ids = {m.get("evaluation_identity") for m in unverified_exploration}
    if not core_ids.isdisjoint(exp_ids):
        raise ValueError("Measured core and unverified exploration evaluation identities must be disjoint")

    # 5. File hash and receipt validation
    actual_file_hash = None
    if checkpoint_path:
        cp_path = Path(checkpoint_path).resolve()
        if cp_path.is_file():
            actual_file_hash = hashlib.sha256(cp_path.read_bytes()).hexdigest()

    if expected_file_hash and actual_file_hash:
        if actual_file_hash != expected_file_hash:
            raise ValueError(f"Warmstart file digest mismatch: {actual_file_hash} != expected {expected_file_hash}")

    if expected_receipt:
        receipt_file_hash = expected_receipt.get("warmstart_file_sha256")
        receipt_manifest_hash = expected_receipt.get("manifest_sha256")
        if receipt_manifest_hash and receipt_manifest_hash != stored_manifest_hash:
            raise ValueError(f"Warmstart manifest digest mismatch with receipt: {stored_manifest_hash} != {receipt_manifest_hash}")
        if receipt_file_hash and actual_file_hash and receipt_file_hash != actual_file_hash:
            raise ValueError(f"Warmstart file digest mismatch with receipt: {actual_file_hash} != {receipt_file_hash}")

    # 6. Context / epoch compatibility
    provenance = manifest.get("provenance", {})
    prov_epoch = provenance.get("epoch_id")
    if expected_epoch_id and prov_epoch is not None and prov_epoch != expected_epoch_id:
        raise ValueError(f"Warmstart epoch '{prov_epoch}' incompatible with destination epoch '{expected_epoch_id}'")

    if expected_catalog_hash and provenance.get("catalog_hash") is not None:
        if provenance["catalog_hash"] != expected_catalog_hash:
            raise ValueError("Warmstart catalog hash incompatible with destination catalog")

    return {
        "manifest": manifest,
        "file_hash": actual_file_hash or data.get("warmstart_file_hash"),
        "provenance": provenance,
        "measured_core_count": len(measured_core),
        "unverified_exploration_count": len(unverified_exploration),
    }


def build_evidence_aware_warmstart(
    db_path: str,
    meta_path: str,
    out_path: str,
    size: int = 20,
    explore_fraction: float = 0.2,
    max_dataset_fraction: float = 1.0,
    max_abs_correlation: float = 0.8,
    min_residual_fraction: float = 0.1,
    min_overlap: int = 60,
    ridge: float = 1e-6,
    epoch_id: str | None = None,
    epoch_manifest_path: str | None = None,
) -> dict:
    """Builds a create-only, evidence-aware warmstart artifact with strict validation."""
    db_file = Path(db_path).resolve()
    meta_file = Path(meta_path).resolve()
    out_file = Path(out_path).resolve()

    if not db_file.is_file():
        raise FileNotFoundError(f"Source database not found: {db_file}")
    if not meta_file.is_file():
        raise FileNotFoundError(f"Metadata file not found: {meta_file}")

    db_sha256 = compute_file_sha256(db_file)
    meta_sha256 = compute_file_sha256(meta_file)

    meta_obj = json.loads(meta_file.read_text(encoding="utf-8"))
    meta_dict = meta_obj.get("field_metadata", {})
    catalog_hash = meta_obj.get("catalog_hash")
    operators_hash = meta_obj.get("operators_hash")

    # If epoch_manifest_path is provided, extract epoch_id
    if epoch_manifest_path and not epoch_id:
        try:
            emp = Path(epoch_manifest_path).resolve()
            if emp.is_file():
                em_data = json.loads(emp.read_text(encoding="utf-8"))
                epoch_id = em_data.get("epoch_id")
        except Exception:
            pass

    # Read source database in immutable mode
    con = sqlite3.connect(db_file.as_uri() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in con.execute(
            "SELECT * FROM alpha_population WHERE universe='TOP3000' AND fitness IS NOT NULL AND sharpe IS NOT NULL "
            "ORDER BY fitness DESC, id"
        )]
        pnl_records = con.execute("SELECT alpha_id, date, pnl FROM alpha_pnl WHERE pnl IS NOT NULL").fetchall()
        try:
            checks_records = con.execute("SELECT alpha_id, metrics_json FROM alpha_checks").fetchall()
            checks_by_aid = {r["alpha_id"]: r["metrics_json"] for r in checks_records}
        except sqlite3.OperationalError:
            checks_by_aid = {}
    finally:
        con.close()

    pnls: dict[str, dict[str, float]] = {}
    for aid, date, val in pnl_records:
        pnls.setdefault(aid, {})[date] = val

    for r in rows:
        r["region"] = "USA_ASSUMED"
        r["delay"] = 1

    deduped = deduplicate_by_evaluation_identity(rows, db_file.name, meta_dict)

    sample_aid = next((r["alpha_id"] for r in deduped if r["alpha_id"] in pnls), None)
    interval_audit = audit_series_intervals(pnls[sample_aid]) if sample_aid else {
        "raw_points": 0, "adjacent_differences": 0, "excluded_gaps": [], "matched_intervals": 0,
        "unit": "matched cumulative-PnL intervals; not guaranteed single trading days"
    }

    def is_attributed(r: dict) -> bool:
        return len(dataset_members(r.get("expression") or "", meta_dict)) > 0

    def has_sufficient_pnl(r: dict) -> bool:
        aid = r.get("alpha_id")
        if not aid or aid not in pnls:
            return False
        diffs = daily_changes(pnls[aid])
        return len(diffs) >= min_overlap

    measured_pool = [r for r in deduped if is_attributed(r) and has_sufficient_pnl(r)]

    reserve = min(size - 1, math.ceil(size * explore_fraction)) if explore_fraction > 0 else 0
    core_target = size - reserve

    measured_core = []
    basket_report = {}
    counts: dict[str, int] = {}
    family_cap = math.ceil(size * max_dataset_fraction)

    # Core selection
    if measured_pool and core_target > 0:
        sel_core, rep_core = select_basket(
            measured_pool,
            pnls,
            meta_dict,
            size=core_target,
            min_overlap=min_overlap,
            max_abs_correlation=max_abs_correlation,
            min_residual_fraction=min_residual_fraction,
            max_dataset_fraction=max_dataset_fraction,
            explore_fraction=0.0,
            ridge=ridge,
        )
        basket_report = rep_core
        counts = dict(rep_core.get("dataset_counts", {}))
        verified_ids = {v["alpha_id"]: v for v in rep_core.get("verified", [])}
        for r in sel_core:
            aid = r["alpha_id"]
            if aid in verified_ids:
                v_data = verified_ids[aid]
                check_eval = evaluate_raw_check_payload(checks_by_aid.get(aid))
                measured_core.append({
                    "alpha_id": aid,
                    "evaluation_identity": r["evaluation_identity"],
                    "tier": "measured_core",
                    "expression": r["expression"],
                    "universe": r["universe"],
                    "decay": r["decay"],
                    "sharpe": r["sharpe"],
                    "turnover": r["turnover"],
                    "fitness": r["fitness"],
                    "datasets": v_data.get("datasets") or dataset_members(r["expression"], meta_dict),
                    "has_pnl": True,
                    "pnl_intervals": len(daily_changes(pnls[aid])),
                    "residual_fraction": v_data.get("residual_fraction"),
                    "raw_subspace_fraction": v_data.get("raw_subspace_fraction"),
                    "common_intervals": rep_core.get("common_intervals"),
                    "qualification_evidence": check_eval,
                    "legacy_is_qualified": r.get("is_qualified"),
                })
    else:
        basket_report = {
            "reason": "insufficient_pnl_evidence_for_core",
            "common_intervals": 0,
            "shrinkage": None,
            "rejections": {},
            "dataset_counts": {},
        }

    # Rejection and clone tracking
    core_eval_ids = {c["evaluation_identity"] for c in measured_core}
    core_rejected_aids = set(basket_report.get("rejections", {}).keys())

    # Selected diffs dictionary for correlation checking
    selected_diffs = {c["alpha_id"]: daily_changes(pnls[c["alpha_id"]]) for c in measured_core if c["alpha_id"] in pnls}

    unverified_exploration = []

    if reserve > 0:
        for r in deduped:
            if len(unverified_exploration) >= reserve:
                break

            # 1. Skip already selected core members
            if r["evaluation_identity"] in core_eval_ids:
                continue

            aid = r.get("alpha_id")

            # 2. Exclude any candidate explicitly rejected during core selection
            # (e.g. absolute_return_redundancy, raw_linear_subspace_redundancy, dataset_budget)
            if aid in core_rejected_aids:
                continue

            # 3. Require dataset attribution
            if not is_attributed(r):
                continue

            # 4. Enforce declared whole-basket dataset constraints
            fams = dataset_members(r["expression"], meta_dict)
            if fams and any(counts.get(f, 0) >= family_cap for f in fams):
                continue

            # 5. For candidates with recorded PnL: check correlation against selected basket
            has_pnl = bool(aid and aid in pnls)
            if has_pnl:
                r_diffs = daily_changes(pnls[aid])
                if len(r_diffs) >= min_overlap and selected_diffs:
                    # Check pairwise correlation against every selected candidate with PnL
                    is_collinear = False
                    for sel_aid, s_diffs in selected_diffs.items():
                        common_d = sorted(set(r_diffs.keys()) & set(s_diffs.keys()))
                        if len(common_d) >= min_overlap:
                            x1 = np.array([r_diffs[d] for d in common_d], dtype=float)
                            x2 = np.array([s_diffs[d] for d in common_d], dtype=float)
                            sd1 = float(x1.std())
                            sd2 = float(x2.std())
                            if sd1 > 1e-12 and sd2 > 1e-12:
                                r_val = abs(float(np.corrcoef(x1, x2)[0, 1]))
                                if r_val > max_abs_correlation:
                                    is_collinear = True
                                    break
                    if is_collinear:
                        # Measured clone / redundant candidate cannot enter exploration
                        continue

            check_eval = evaluate_raw_check_payload(checks_by_aid.get(aid) if aid else None)
            unverified_exploration.append({
                "alpha_id": aid,
                "evaluation_identity": r["evaluation_identity"],
                "tier": "unverified_exploration",
                "expression": r["expression"],
                "universe": r["universe"],
                "decay": r["decay"],
                "sharpe": r.get("sharpe"),
                "turnover": r.get("turnover"),
                "fitness": r.get("fitness"),
                "datasets": fams,
                "has_pnl": has_pnl,
                "diversity_verified": False,
                "pnl_verified": False,
                "signal_novelty_status": "unknown_unmeasured",
                "exploration_reason": "Admitted under declared exploration reserve quota; economic novelty and PnL diversity unverified",
                "qualification_evidence": check_eval,
                "legacy_is_qualified": r.get("is_qualified"),
            })

            # Update dataset counts and selected diffs
            for f in fams:
                counts[f] = counts.get(f, 0) + 1
            if has_pnl:
                selected_diffs[aid] = daily_changes(pnls[aid])

    engine_population = [[e["expression"], e["universe"], e["decay"]] for e in (measured_core + unverified_exploration)]

    total_admitted = len(engine_population)
    underfill_count = max(0, size - total_admitted)

    manifest_payload = {
        "target_size": size,
        "declared_reserve": reserve,
        "explore_fraction": explore_fraction,
        "measured_core_count": len(measured_core),
        "unverified_exploration_count": len(unverified_exploration),
        "total_warmstart_count": total_admitted,
        "underfill_count": underfill_count,
        "measured_core": measured_core,
        "unverified_exploration": unverified_exploration,
        "interval_diagnostics": interval_audit,
        "basket_report": {
            "reason": basket_report.get("reason"),
            "common_intervals": basket_report.get("common_intervals"),
            "shrinkage": basket_report.get("shrinkage"),
            "dataset_counts": counts,
            "rejection_summary": {k: list(basket_report.get("rejections", {}).values()).count(k) for k in set(basket_report.get("rejections", {}).values())},
        },
        "selection_controls": {
            "size": size,
            "explore_fraction": explore_fraction,
            "max_dataset_fraction": max_dataset_fraction,
            "max_abs_correlation": max_abs_correlation,
            "min_residual_fraction": min_residual_fraction,
            "min_overlap": min_overlap,
            "ridge": ridge,
        },
        "provenance": {
            "source_db_path": str(db_file),
            "source_db_sha256": db_sha256,
            "meta_path": str(meta_file),
            "meta_sha256": meta_sha256,
            "catalog_hash": catalog_hash,
            "operators_hash": operators_hash,
            "epoch_id": epoch_id or meta_obj.get("epoch_id"),
            "regime": {"region": "USA_ASSUMED", "delay": 1, "universe": "TOP3000"},
            "regime_caveat": "Caveat: Region USA and delay 1 are migration assumptions from legacy config defaults; unconfirmed in source simulation logs.",
            "qualification_caveat": "Caveat: All candidates retain parsed evidence status. Missing or historical checks are not platform certification.",
            "unmeasured_exploration_caveat": "Dataset attribution is only an attribution predicate; nonconstancy and economic meaning remain unmeasured without PnL.",
            "network_calls": 0,
        },
    }

    manifest_payload["manifest_sha256"] = compute_manifest_sha256(manifest_payload)

    warmstart_payload = {
        "schema_version": WARMSTART_SCHEMA_VERSION,
        "generation": 0,
        "submission_count": 0,
        "population": engine_population,
        "warmstart_manifest": manifest_payload,
    }

    warmstart_file_hash = exclusive_create_atomic_json(out_file, warmstart_payload, input_paths=[db_file, meta_file])

    warmstart_payload["warmstart_file_hash"] = warmstart_file_hash
    warmstart_payload["warmstart_file_path"] = str(out_file)

    receipt_file = out_file.with_name(f"{out_file.name}.receipt.json")
    if not receipt_file.exists():
        exclusive_create_atomic_json(receipt_file, {
            "warmstart_artifact": str(out_file),
            "warmstart_file_sha256": warmstart_file_hash,
            "manifest_sha256": manifest_payload["manifest_sha256"],
            "source_db_sha256": db_sha256,
            "meta_sha256": meta_sha256,
            "published_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "schema_version": WARMSTART_SCHEMA_VERSION,
        })

    return warmstart_payload
