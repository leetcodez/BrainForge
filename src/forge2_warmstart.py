"""Evidence-aware warmstart publication and import contract.

Provides create-only, fail-closed warmstart building, validation, and restore:
  - Strict destination guards: create-only, protects checkpoints and input paths.
  - Evaluation identity: AST-normalized whitespace with distinct evaluation settings.
  - Decoded check evidence: preserves malformed, failed, pending, and unverifiable states.
  - Honest quota partitioning: measured core requires verified PnL; exploration reserve is strictly capped.
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
from typing import Any

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
    """Race-safe create-only atomic JSON publication with alias and collision protection."""
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

    # Guard 4: Atomic create-only write
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".tmp.{target.name}.{os.getpid()}")
    raw = json.dumps(data, indent=1, sort_keys=True)
    try:
        tmp.write_text(raw, encoding="utf-8")
        try:
            os.link(tmp, target)
            os.unlink(tmp)
        except OSError:
            # Fallback for filesystems where os.link fails: open with 'x' (O_CREAT | O_EXCL)
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
            with open(target, "x", encoding="utf-8") as f:
                f.write(raw)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
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
            # Fallback for unparseable ASTs
            eval_id = hashlib.sha256(f"{expr}|{universe}|{decay}|{source_name}".encode()).hexdigest()

        r["evaluation_identity"] = eval_id
        r["evaluation_settings"] = payload["settings"]
        r["evaluation_context"] = context
        groups.setdefault(eval_id, []).append(r)

    # Sort each group by fitness descending and pick the highest fitness representative
    deduped = []
    for eval_id, members in groups.items():
        best = max(members, key=lambda m: (m.get("fitness") if m.get("fitness") is not None else -float("inf"), m.get("alpha_id") or ""))
        deduped.append(best)

    # Sort final deduped population by fitness descending
    return sorted(deduped, key=lambda m: (-(m.get("fitness") if m.get("fitness") is not None else -float("inf")), m.get("alpha_id") or ""))


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

    # Compute input hashes before any operation
    db_sha256 = compute_file_sha256(db_file)
    meta_sha256 = compute_file_sha256(meta_file)

    meta_obj = json.loads(meta_file.read_text(encoding="utf-8"))
    meta_dict = meta_obj.get("field_metadata", {})
    catalog_hash = meta_obj.get("catalog_hash")
    operators_hash = meta_obj.get("operators_hash")

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

    # Organize PnLs by alpha_id
    pnls: dict[str, dict[str, float]] = {}
    for aid, date, val in pnl_records:
        pnls.setdefault(aid, {})[date] = val

    # Assign regime assumptions
    for r in rows:
        r["region"] = "USA_ASSUMED"
        r["delay"] = 1

    # Deduplicate population by semantic evaluation identity
    deduped = deduplicate_by_evaluation_identity(rows, db_file.name, meta_dict)

    # Establish intervals audit on the representative candidate
    sample_aid = next((r["alpha_id"] for r in deduped if r["alpha_id"] in pnls), None)
    interval_audit = audit_series_intervals(pnls[sample_aid]) if sample_aid else {
        "raw_points": 0, "adjacent_differences": 0, "excluded_gaps": [], "matched_intervals": 0,
        "unit": "matched cumulative-PnL intervals; not guaranteed single trading days"
    }

    # Partition into measured-core pool vs exploration pool
    # Core requires: attributed dataset fields, valid PnL with >= min_overlap
    def is_attributed(r: dict) -> bool:
        return len(dataset_members(r.get("expression") or "", meta_dict)) > 0

    def has_sufficient_pnl(r: dict) -> bool:
        aid = r.get("alpha_id")
        if not aid or aid not in pnls:
            return False
        diffs = daily_changes(pnls[aid])
        return len(diffs) >= min_overlap

    measured_pool = [r for r in deduped if is_attributed(r) and has_sufficient_pnl(r)]

    # Compute quotas
    reserve = min(size - 1, math.ceil(size * explore_fraction)) if explore_fraction > 0 else 0
    core_target = size - reserve

    measured_core = []
    basket_report = {}

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
        }

    # Exploration Reserve: strictly capped at reserve
    core_eval_ids = {c["evaluation_identity"] for c in measured_core}
    unverified_exploration = []

    if reserve > 0:
        for r in deduped:
            if r["evaluation_identity"] in core_eval_ids:
                continue
            if not is_attributed(r):
                continue
            aid = r.get("alpha_id")
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
                "datasets": dataset_members(r["expression"], meta_dict),
                "has_pnl": bool(aid and aid in pnls),
                "diversity_verified": False,
                "pnl_verified": False,
                "signal_novelty_status": "unknown_unmeasured",
                "exploration_reason": "Admitted under declared exploration reserve quota; economic novelty and PnL diversity unverified",
                "qualification_evidence": check_eval,
                "legacy_is_qualified": r.get("is_qualified"),
            })
            if len(unverified_exploration) >= reserve:
                break

    # Build engine-compatible population list: triples [expression, universe, decay]
    engine_population = [[e["expression"], e["universe"], e["decay"]] for e in (measured_core + unverified_exploration)]

    # Honest underfill accounting
    total_admitted = len(engine_population)
    underfill_count = max(0, size - total_admitted)

    # Compile the full versioned warmstart payload
    warmstart_payload = {
        "schema_version": WARMSTART_SCHEMA_VERSION,
        "generation": 0,
        "submission_count": 0,
        "population": engine_population,
        "warmstart_manifest": {
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
                "dataset_counts": basket_report.get("dataset_counts"),
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
                "regime_caveat": "Region USA and delay 1 are migration assumptions from legacy config defaults; unconfirmed in source simulation logs.",
                "qualification_caveat": "All candidates retain parsed evidence status. Missing or historical checks are not platform certification.",
                "network_calls": 0,
            },
        },
    }

    # Record deterministic manifest hash
    manifest_bytes = json.dumps(warmstart_payload["warmstart_manifest"], sort_keys=True).encode()
    warmstart_payload["warmstart_manifest"]["manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()

    # Publish via create-only atomic primitive
    warmstart_file_hash = exclusive_create_atomic_json(out_file, warmstart_payload, input_paths=[db_file, meta_file])

    # Record warmstart_file_hash in returned dictionary
    warmstart_payload["warmstart_file_hash"] = warmstart_file_hash
    warmstart_payload["warmstart_file_path"] = str(out_file)

    # Write companion receipt
    receipt_file = out_file.with_name(f"{out_file.name}.receipt.json")
    if not receipt_file.exists():
        exclusive_create_atomic_json(receipt_file, {
            "warmstart_artifact": str(out_file),
            "warmstart_file_sha256": warmstart_file_hash,
            "manifest_sha256": warmstart_payload["warmstart_manifest"]["manifest_sha256"],
            "source_db_sha256": db_sha256,
            "meta_sha256": meta_sha256,
            "published_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "schema_version": WARMSTART_SCHEMA_VERSION,
        })

    return warmstart_payload
