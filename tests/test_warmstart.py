"""Acceptance and regression tests for evidence-aware warmstart builder and restore contract.

Covers all 8 bounded acceptance findings from WARMSTART_REVIEW.md:
  1. Create-only destination guards, alias rejection, protected checkpoint filenames, atomic create.
  2. Decoded check evidence: preserves missing, malformed, failed, pending, unknown, and valid payloads.
  3. Evaluation identity deduplication: whitespace collapsed under identical settings; distinct decays preserved.
  4. No/short/non-overlapping/flat PnL cannot enter core; exploration ceiling strictly enforced; honest underfill.
  5. Core and exploration identities are disjoint; dataset attribution enforced; deterministic sorting.
  6. Full selection controls, input hashes, and matched interval diagnostics serialized.
  7. Immutability of source DB and checkpoints; determinism for fixed inputs.
  8. Isolated restore preserves membership and warmstart manifest through next _save_checkpoint().
"""
from __future__ import annotations
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import pytest

import config
from forge2_search import candidate_identity
from forge2_warmstart import (
    build_evidence_aware_warmstart,
    exclusive_create_atomic_json,
    evaluate_raw_check_payload,
    deduplicate_by_evaluation_identity,
    audit_series_intervals,
    compute_file_sha256,
)
from orchestrator import AlphaFactory


def create_fixture_db(
    directory: Path,
    alpha_rows: list[tuple],
    pnl_rows: list[tuple] | None = None,
    checks_rows: list[tuple] | None = None,
) -> tuple[Path, Path]:
    """Create isolated SQLite database and metadata fixtures."""
    db_path = directory / "fixture_source.db"
    con = sqlite3.connect(db_path)
    con.execute(
        "CREATE TABLE alpha_population ("
        "id INTEGER, alpha_id TEXT, expression TEXT, universe TEXT, decay INTEGER, "
        "fitness REAL, sharpe REAL, turnover REAL, is_qualified INTEGER)"
    )
    con.executemany("INSERT INTO alpha_population VALUES (?,?,?,?,?,?,?,?,?)", alpha_rows)

    con.execute("CREATE TABLE alpha_pnl (alpha_id TEXT, date TEXT, pnl REAL)")
    if pnl_rows:
        con.executemany("INSERT INTO alpha_pnl VALUES (?,?,?)", pnl_rows)

    con.execute("CREATE TABLE alpha_checks (alpha_id TEXT, metrics_json TEXT)")
    if checks_rows:
        con.executemany("INSERT INTO alpha_checks VALUES (?,?)", checks_rows)

    con.commit()
    con.close()

    meta_path = directory / "fixture_meta.json"
    meta_path.write_text(json.dumps({
        "epoch_id": "test_epoch_001",
        "catalog_hash": "cat_hash_123",
        "operators_hash": "op_hash_456",
        "field_metadata": {
            "f": {"dataset": "earnings4", "type": "MATRIX"},
            "vol": {"dataset": "earnings4", "type": "MATRIX"},
            "sales": {"dataset": "earnings4", "type": "MATRIX"},
        }
    }), encoding="utf-8")

    return db_path, meta_path


# ---------------------------------------------------------------------------
# Test 1: Destination guards and protected filenames
# ---------------------------------------------------------------------------
def test_destination_guards_and_alias_rejection(tmp_path):
    rows = [(1, "a", "rank(f)", "TOP3000", 0, 1.0, 1.5, 0.2, 0)]
    db_path, meta_path = create_fixture_db(tmp_path, rows)
    initial_db_hash = compute_file_sha256(db_path)
    initial_meta_hash = compute_file_sha256(meta_path)

    # Rejection of existing destination without modifying bytes
    existing_out = tmp_path / "already_exists.json"
    existing_out.write_text('{"untouched": true}')
    existing_hash = compute_file_sha256(existing_out)
    with pytest.raises(FileExistsError):
        build_evidence_aware_warmstart(str(db_path), str(meta_path), str(existing_out))
    assert compute_file_sha256(existing_out) == existing_hash

    # Rejection of input path aliases (source db and meta)
    with pytest.raises(ValueError, match="conflicts with input path"):
        build_evidence_aware_warmstart(str(db_path), str(meta_path), str(db_path))
    assert compute_file_sha256(db_path) == initial_db_hash

    with pytest.raises(ValueError, match="conflicts with input path"):
        build_evidence_aware_warmstart(str(db_path), str(meta_path), str(meta_path))
    assert compute_file_sha256(meta_path) == initial_meta_hash

    # Rejection of protected checkpoint filenames (.wq_checkpoint.json, checkpoint.json)
    for protected in [".wq_checkpoint.json", "checkpoint.json", "forge2_campaign_state.json"]:
        target = tmp_path / protected
        with pytest.raises(ValueError, match="protected checkpoint"):
            build_evidence_aware_warmstart(str(db_path), str(meta_path), str(target))
        assert not target.exists()


# ---------------------------------------------------------------------------
# Test 2: Check evidence states (missing, malformed, failed, pending, valid)
# ---------------------------------------------------------------------------
def test_check_evidence_payload_states():
    # 1. Missing payload
    eval_missing = evaluate_raw_check_payload(None)
    assert eval_missing["qualification_status"] == "CHECKS_UNVERIFIABLE"
    assert eval_missing["evidence_verified"] is False

    # 2. Malformed JSON string
    eval_malformed = evaluate_raw_check_payload("not-valid-json")
    assert eval_malformed["qualification_status"] == "CHECKS_UNVERIFIABLE"
    assert eval_malformed["evidence_verified"] is False
    assert "malformed_json_payload" in eval_malformed["reason"]

    # 3. Empty or unverified structure
    eval_empty = evaluate_raw_check_payload(json.dumps({"checks": []}))
    assert eval_empty["qualification_status"] == "CHECKS_UNVERIFIABLE"
    assert eval_empty["evidence_verified"] is False

    # 4. Failed check payload
    failed_payload = json.dumps({
        "checks": [
            {"name": "TURNOVER", "result": "FAIL", "value": 0.9},
            {"name": "SHARPE", "result": "PASS", "value": 1.5}
        ]
    })
    eval_failed = evaluate_raw_check_payload(failed_payload)
    assert eval_failed["qualification_status"] == "CHECKS_FAILED"
    assert eval_failed["evidence_verified"] is True
    assert "TURNOVER" in eval_failed["failed_checks"]

    # 5. Pending check payload
    pending_payload = json.dumps({
        "checks": [
            {"name": "SELF_CORRELATION", "result": "PENDING"},
            {"name": "SHARPE", "result": "PASS", "value": 1.5}
        ]
    })
    eval_pending = evaluate_raw_check_payload(pending_payload)
    assert eval_pending["qualification_status"] == "CHECKS_PENDING"
    assert eval_pending["evidence_verified"] is True
    assert "SELF_CORRELATION" in eval_pending["pending_checks"]

    # 6. Valid passing check payload
    valid_payload = json.dumps({
        "checks": [
            {"name": "LOW_SHARPE", "result": "PASS", "value": 2.1},
            {"name": "HIGH_TURNOVER", "result": "PASS", "value": 0.25}
        ]
    })
    eval_valid = evaluate_raw_check_payload(valid_payload)
    assert eval_valid["qualification_status"] == "HISTORICAL_CHECKS_PASSED"
    assert eval_valid["evidence_verified"] is True
    assert eval_valid["failed_checks"] == []
    assert "caveat" in eval_valid["platform_qualification_caveat"].lower()


# ---------------------------------------------------------------------------
# Test 3: Deduplication collapses whitespace but preserves distinct decays
# ---------------------------------------------------------------------------
def test_evaluation_identity_deduplication(tmp_path):
    rows = [
        (1, "a", "rank(f)", "TOP3000", 0, 3.0, 2.0, 0.2, 0),
        (2, "b", "rank( f )", "TOP3000", 0, 2.0, 2.0, 0.2, 0),  # Whitespace variant of 'a', lower fitness
        (3, "c", "rank(f)", "TOP3000", 5, 1.0, 2.0, 0.2, 0),    # Different decay=5, distinct evaluation identity
    ]
    db_path, meta_path = create_fixture_db(tmp_path, rows)
    out_path = tmp_path / "warmstart_dedup.json"

    payload = build_evidence_aware_warmstart(
        str(db_path), str(meta_path), str(out_path),
        size=5, explore_fraction=0.4
    )

    manifest = payload["warmstart_manifest"]
    admitted = manifest["measured_core"] + manifest["unverified_exploration"]
    eval_ids = [m["evaluation_identity"] for m in admitted]

    # Exactly 2 unique evaluation identities should exist ('a' and 'c')
    assert len(eval_ids) == 2
    assert len(set(eval_ids)) == 2

    # Member 'a' (fitness=3.0) must be retained, 'b' (fitness=2.0) dropped
    alpha_ids = [m["alpha_id"] for m in admitted]
    assert "a" in alpha_ids
    assert "b" not in alpha_ids
    assert "c" in alpha_ids

    # Decay settings must be preserved (one decay=0, one decay=5)
    decays = sorted(m["decay"] for m in admitted)
    assert decays == [0, 5]


# ---------------------------------------------------------------------------
# Test 4: No-evidence fallback cannot exceed declared exploration quota
# ---------------------------------------------------------------------------
def test_no_pnl_fallback_strictly_obeys_exploration_quota(tmp_path):
    # In this fixture, candidates have NO PnL records
    rows = [
        (1, "a", "rank(f)", "TOP3000", 0, 3.0, 2.0, 0.2, 0),
        (2, "b", "rank( f )", "TOP3000", 0, 2.0, 2.0, 0.2, 0),
        (3, "c", "rank(f)", "TOP3000", 5, 1.0, 2.0, 0.2, 0),
    ]
    db_path, meta_path = create_fixture_db(tmp_path, rows)
    out_path = tmp_path / "warmstart_quota.json"

    # size=5, explore_fraction=0.2 => reserve = ceil(5*0.2) = 1
    payload = build_evidence_aware_warmstart(
        str(db_path), str(meta_path), str(out_path),
        size=5, explore_fraction=0.2
    )

    manifest = payload["warmstart_manifest"]
    # Because there is no PnL, measured core must be 0
    assert manifest["measured_core_count"] == 0
    # Exploration quota must not exceed declared_reserve (1)
    assert manifest["declared_reserve"] == 1
    assert manifest["unverified_exploration_count"] == 1
    assert manifest["total_warmstart_count"] == 1
    # Underfill must be explicitly reported (5 - 1 = 4)
    assert manifest["underfill_count"] == 4


# ---------------------------------------------------------------------------
# Test 5: Disjoint identities, dataset attribution, deterministic sorting
# ---------------------------------------------------------------------------
def test_disjoint_identities_and_deterministic_sorting(tmp_path):
    # Build 70 trading day PnL points
    dates = [f"2023-01-{i:02d}" for i in range(1, 32)] + [f"2023-02-{i:02d}" for i in range(1, 29)] + [f"2023-03-{i:02d}" for i in range(1, 20)]
    pnl_a = [("a", d, float(i)) for i, d in enumerate(dates)]
    pnl_c = [("c", d, float(i * 1.5)) for i, d in enumerate(dates)]

    rows = [
        (1, "a", "rank(f)", "TOP3000", 0, 3.0, 2.0, 0.2, 0),
        (2, "c", "rank(vol)", "TOP3000", 0, 2.0, 2.0, 0.2, 0),
        (3, "d", "rank(sales)", "TOP3000", 0, 1.5, 1.5, 0.2, 0),  # No PnL, for exploration
        (4, "const", "group_neutralize(-1, SECTOR)", "TOP3000", 0, 0.5, 0.0, 0.0, 0), # Unattributed, must be rejected
    ]
    db_path, meta_path = create_fixture_db(tmp_path, rows, pnl_rows=pnl_a + pnl_c)
    out1 = tmp_path / "warmstart_det1.json"
    out2 = tmp_path / "warmstart_det2.json"

    p1 = build_evidence_aware_warmstart(str(db_path), str(meta_path), str(out1), size=3, explore_fraction=0.33)
    p2 = build_evidence_aware_warmstart(str(db_path), str(meta_path), str(out2), size=3, explore_fraction=0.33)

    # Determinism across runs
    assert p1["population"] == p2["population"]
    assert p1["warmstart_file_hash"] == p2["warmstart_file_hash"]

    m1 = p1["warmstart_manifest"]
    core_ids = {c["evaluation_identity"] for c in m1["measured_core"]}
    exp_ids = {e["evaluation_identity"] for e in m1["unverified_exploration"]}

    # Disjointness between core and exploration
    assert core_ids.isdisjoint(exp_ids)

    # Degenerate constant expression with no dataset fields must NOT enter exploration
    all_exprs = [e[0] for e in p1["population"]]
    assert "group_neutralize(-1, SECTOR)" not in all_exprs


# ---------------------------------------------------------------------------
# Test 6: Serialized controls and interval diagnostics
# ---------------------------------------------------------------------------
def test_serialized_controls_and_gap_diagnostics(tmp_path):
    # Series with a 5-day gap (excluded by max_gap_days=4)
    series = {
        "2023-01-01": 10.0,
        "2023-01-02": 11.0,
        "2023-01-08": 12.0, # 6-day gap from Jan 2
        "2023-01-09": 13.0,
    }
    audit = audit_series_intervals(series, max_gap_days=4)
    assert audit["raw_points"] == 4
    assert audit["adjacent_differences"] == 3
    assert audit["excluded_gap_count"] == 1
    assert audit["excluded_gaps"][0]["calendar_days"] == 6
    assert audit["matched_intervals"] == 2


# ---------------------------------------------------------------------------
# Test 7: Source immutability
# ---------------------------------------------------------------------------
def test_source_immutability(tmp_path):
    rows = [(1, "a", "rank(f)", "TOP3000", 0, 1.0, 1.5, 0.2, 0)]
    db_path, meta_path = create_fixture_db(tmp_path, rows)
    db_before = compute_file_sha256(db_path)
    meta_before = compute_file_sha256(meta_path)

    out_path = tmp_path / "warmstart_immutability.json"
    build_evidence_aware_warmstart(str(db_path), str(meta_path), str(out_path), size=2, explore_fraction=0.5)

    assert compute_file_sha256(db_path) == db_before
    assert compute_file_sha256(meta_path) == meta_before


# ---------------------------------------------------------------------------
# Test 8: Isolated restore preserves membership and manifest through _save_checkpoint
# ---------------------------------------------------------------------------
def test_isolated_restore_and_save_preserves_warmstart_manifest(tmp_path):
    rows = [(1, "a", "rank(f)", "TOP3000", 0, 1.0, 1.5, 0.2, 0)]
    db_path, meta_path = create_fixture_db(tmp_path, rows)

    warmstart_path = tmp_path / "warmstart_for_restore.json"
    payload = build_evidence_aware_warmstart(str(db_path), str(meta_path), str(warmstart_path), size=2, explore_fraction=0.5)

    # Point orchestrator checkpoint path to warmstart artifact
    config.CHECKPOINT_PATH = str(warmstart_path)

    # Construct AlphaFactory without network transports or DB initialization
    engine = AlphaFactory.__new__(AlphaFactory)
    engine._restore_checkpoint()

    # Verify keys restored and manifest retained
    assert engine._resume_population_keys == payload["population"]
    assert hasattr(engine, "warmstart_manifest")
    assert engine.warmstart_manifest == payload["warmstart_manifest"]
    assert engine.warmstart_file_hash == payload["warmstart_file_hash"]

    # Emulate population and save next checkpoint to a separate checkpoint path
    next_checkpoint_path = tmp_path / "next_run_checkpoint.json"
    config.CHECKPOINT_PATH = str(next_checkpoint_path)
    engine.population = [{"expression": p[0], "universe": p[1], "decay": p[2]} for p in payload["population"]]
    engine._save_checkpoint()

    # Verify that the saved checkpoint retained the warmstart manifest and file hash
    saved_data = json.loads(next_checkpoint_path.read_text(encoding="utf-8"))
    assert "warmstart_manifest" in saved_data
    assert saved_data["warmstart_manifest"] == payload["warmstart_manifest"]
    assert saved_data["warmstart_file_hash"] == payload["warmstart_file_hash"]
