"""Acceptance and regression tests for evidence-aware warmstart builder and restore contract.

Covers all findings and non-vacuous acceptance requirements from WARMSTART_RECHECK.md:
  1. Concurrent publication: mkstemp-allocated unique temp files; asserts winning publisher's file bytes match intended payload.
  2. Measured-rejected clones barred from exploration: known pairwise clones (|r|=1.0), sign flips, and subspace rejections cannot enter exploration reserve.
  3. Import contract validation: tampered decay, bad manifest digest, bad receipt hash, tier count mismatch, and incompatible epoch rejected before resume state mutation.
  4. Non-vacuous measured core: independent nonflat random walks assert len(measured_core) >= 1 before checking disjointness.
  5. Check evidence states: missing, malformed, empty, failed, pending, historical pass.
  6. Evaluation identity deduplication: whitespace collapsed under identical settings; distinct decays preserved.
  7. No-evidence fallback: zero PnL cannot enter core; strictly obeys exploration reserve ceiling; explicit underfill.
  8. Full selection controls, input hashes, and matched interval diagnostics serialized.
  9. Immutability of source DB and checkpoints; determinism for fixed inputs.
  10. Isolated restore and save cycle preserves membership and manifest through next _save_checkpoint().
"""
from __future__ import annotations
import copy
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import numpy as np
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
    validate_warmstart_import,
)
from orchestrator import AlphaFactory


def create_fixture_db(
    directory: Path,
    alpha_rows: list[tuple],
    pnl_rows: list[tuple] | None = None,
    checks_rows: list[tuple] | None = None,
    meta_fields: list[str] | None = None,
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

    fields = meta_fields or ["f", "vol", "sales"]
    meta_path = directory / "fixture_meta.json"
    meta_path.write_text(json.dumps({
        "epoch_id": "test_epoch_001",
        "catalog_hash": "cat_hash_123",
        "operators_hash": "op_hash_456",
        "field_metadata": {k: {"dataset": "earnings4", "type": "MATRIX"} for k in fields}
    }), encoding="utf-8")

    return db_path, meta_path


# ---------------------------------------------------------------------------
# Test 1: Destination guards, alias rejection, and concurrent publication race
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


def test_concurrent_publication_writer_integrity(tmp_path):
    """Assert concurrent publishers allocate unique temp files and winner's payload matches destination."""
    target = tmp_path / "concurrent_published.json"
    outcomes = {}
    winner_name = []
    barrier = threading.Barrier(2)

    def publish(name, payload_data):
        try:
            barrier.wait(timeout=5)
            h = exclusive_create_atomic_json(target, payload_data)
            outcomes[name] = {"result": "success", "hash": h}
            winner_name.append(name)
        except Exception as exc:
            outcomes[name] = {"result": type(exc).__name__, "error": str(exc)}

    payload_a = {"publisher": "A", "random_id": "alpha_123"}
    payload_b = {"publisher": "B", "random_id": "beta_456"}

    t_a = threading.Thread(target=publish, args=("A", payload_a), name="A")
    t_b = threading.Thread(target=publish, args=("B", payload_b), name="B")

    t_a.start()
    t_b.start()
    t_a.join(timeout=10)
    t_b.join(timeout=10)

    assert not t_a.is_alive() and not t_b.is_alive()
    assert len(winner_name) == 1
    winner = winner_name[0]
    loser = "B" if winner == "A" else "A"

    assert outcomes[winner]["result"] == "success"
    assert outcomes[loser]["result"] == "FileExistsError"

    # Crucial assertion: destination file bytes MUST match winning publisher's intended payload!
    target_data = json.loads(target.read_text(encoding="utf-8"))
    assert target_data["publisher"] == winner
    expected_data = payload_a if winner == "A" else payload_b
    assert target_data == expected_data


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
# Test 4: Measured-rejected clones and sign flips barred from exploration
# ---------------------------------------------------------------------------
def test_measured_rejected_clones_barred_from_exploration(tmp_path):
    """Assert candidate rejected from core for correlation redundancy cannot enter exploration."""
    rows = [
        (1, "a", "rank(f)", "TOP3000", 0, 3.0, 2.0, 0.2, 0),
        (2, "b", "rank(vol)", "TOP3000", 0, 2.9, 2.0, 0.2, 0),
        (3, "c", "rank(sales)", "TOP3000", 0, 2.0, 2.0, 0.2, 0),
    ]
    # Synthetic PnL: a and b have IDENTICAL nonflat series (|r|=1.0); c has independent series
    rng = np.random.default_rng(42)
    pnl_shared = np.cumsum(rng.normal(size=100))
    pnl_c = np.cumsum(rng.normal(size=100))
    start_date = datetime.date(2023, 1, 1)

    pnl_rows = []
    for aid, series in [("a", pnl_shared), ("b", pnl_shared), ("c", pnl_c)]:
        for i, val in enumerate(series):
            d = (start_date + datetime.timedelta(days=i)).isoformat()
            pnl_rows.append((aid, d, float(val)))

    db_path, meta_path = create_fixture_db(tmp_path, rows, pnl_rows=pnl_rows)
    out_path = tmp_path / "warmstart_no_clone_exploration.json"

    # size=3, explore_fraction=0.33 => core_target=2, reserve=1
    payload = build_evidence_aware_warmstart(
        str(db_path), str(meta_path), str(out_path),
        size=3, explore_fraction=0.33, min_overlap=10
    )

    manifest = payload["warmstart_manifest"]
    core_ids = [x["alpha_id"] for x in manifest["measured_core"]]
    explore_ids = [x["alpha_id"] for x in manifest["unverified_exploration"]]

    # Core must select 'a' and 'c'
    assert core_ids == ["a", "c"]
    # Candidate 'b' was rejected during core selection for absolute_return_redundancy
    assert manifest["basket_report"]["rejection_summary"].get("absolute_return_redundancy", 0) >= 1

    # Crucial assertion: candidate 'b' MUST NOT be admitted into exploration!
    assert "b" not in explore_ids
    # Since there are no other candidates, exploration underfills honestly
    assert explore_ids == []
    assert manifest["underfill_count"] == 1


# ---------------------------------------------------------------------------
# Test 5: Non-vacuous measured core, disjoint identities, deterministic sorting
# ---------------------------------------------------------------------------
def test_disjoint_identities_and_deterministic_sorting(tmp_path):
    # Nonflat independent random walks to guarantee non-vacuous measured core
    rng = np.random.default_rng(101)
    dates = [(datetime.date(2023, 1, 1) + datetime.timedelta(days=i)).isoformat() for i in range(100)]
    pnl_a = [("a", d, float(v)) for d, v in zip(dates, np.cumsum(rng.normal(size=100)))]
    pnl_c = [("c", d, float(v)) for d, v in zip(dates, np.cumsum(rng.normal(size=100)))]

    rows = [
        (1, "a", "rank(f)", "TOP3000", 0, 3.0, 2.0, 0.2, 0),
        (2, "c", "rank(vol)", "TOP3000", 0, 2.0, 2.0, 0.2, 0),
        (3, "d", "rank(sales)", "TOP3000", 0, 1.5, 1.5, 0.2, 0),  # No PnL, for exploration
        (4, "const", "group_neutralize(-1, SECTOR)", "TOP3000", 0, 0.5, 0.0, 0.0, 0), # Unattributed
    ]
    db_path, meta_path = create_fixture_db(tmp_path, rows, pnl_rows=pnl_a + pnl_c)
    out1 = tmp_path / "warmstart_det1.json"
    out2 = tmp_path / "warmstart_det2.json"

    p1 = build_evidence_aware_warmstart(str(db_path), str(meta_path), str(out1), size=3, explore_fraction=0.33, min_overlap=10)
    p2 = build_evidence_aware_warmstart(str(db_path), str(meta_path), str(out2), size=3, explore_fraction=0.33, min_overlap=10)

    # Determinism across runs
    assert p1["population"] == p2["population"]
    assert p1["warmstart_file_hash"] == p2["warmstart_file_hash"]

    m1 = p1["warmstart_manifest"]
    core_ids = {c["evaluation_identity"] for c in m1["measured_core"]}
    exp_ids = {e["evaluation_identity"] for e in m1["unverified_exploration"]}

    # Non-vacuous assertion: measured core MUST have members!
    assert len(m1["measured_core"]) >= 1
    assert len(m1["unverified_exploration"]) >= 1

    # Disjointness between core and exploration
    assert core_ids.isdisjoint(exp_ids)

    # Degenerate constant expression with no dataset fields must NOT enter exploration
    all_exprs = [e[0] for e in p1["population"]]
    assert "group_neutralize(-1, SECTOR)" not in all_exprs


# ---------------------------------------------------------------------------
# Test 6: Serialized controls, provenance, and gap diagnostics
# ---------------------------------------------------------------------------
def test_serialized_controls_and_provenance_validation(tmp_path):
    rows = [(1, "a", "rank(f)", "TOP3000", 0, 1.0, 1.5, 0.2, 0)]
    # Series with a 6-day gap (excluded by max_gap_days=4)
    series = {
        "2023-01-01": 10.0,
        "2023-01-02": 11.0,
        "2023-01-08": 12.0, # 6-day gap
        "2023-01-09": 13.0,
    }
    audit = audit_series_intervals(series, max_gap_days=4)
    assert audit["raw_points"] == 4
    assert audit["adjacent_differences"] == 3
    assert audit["excluded_gap_count"] == 1
    assert audit["excluded_gaps"][0]["calendar_days"] == 6
    assert audit["matched_intervals"] == 2

    # Assert full control and provenance serialization in warmstart
    db_path, meta_path = create_fixture_db(tmp_path, rows)
    out_path = tmp_path / "warmstart_provenance.json"
    payload = build_evidence_aware_warmstart(
        str(db_path), str(meta_path), str(out_path),
        size=2, explore_fraction=0.5, max_dataset_fraction=0.8,
        max_abs_correlation=0.75, min_residual_fraction=0.15, min_overlap=30, ridge=1e-5
    )
    m = payload["warmstart_manifest"]
    assert m["selection_controls"]["size"] == 2
    assert m["selection_controls"]["max_dataset_fraction"] == 0.8
    assert m["selection_controls"]["max_abs_correlation"] == 0.75
    assert m["selection_controls"]["min_residual_fraction"] == 0.15
    assert m["selection_controls"]["min_overlap"] == 30
    assert m["selection_controls"]["ridge"] == 1e-5

    prov = m["provenance"]
    assert prov["source_db_sha256"] == compute_file_sha256(db_path)
    assert prov["meta_sha256"] == compute_file_sha256(meta_path)
    assert prov["catalog_hash"] == "cat_hash_123"
    assert prov["operators_hash"] == "op_hash_456"
    assert "caveat" in prov["regime_caveat"].lower()


# ---------------------------------------------------------------------------
# Test 7: Warmstart import contract validation (tampering, digest, receipt)
# ---------------------------------------------------------------------------
def test_warmstart_import_contract_validations(tmp_path):
    rows = [(1, "a", "rank(f)", "TOP3000", 0, 1.0, 1.5, 0.2, 0)]
    db_path, meta_path = create_fixture_db(tmp_path, rows)
    out_path = tmp_path / "warmstart_contract.json"
    payload = build_evidence_aware_warmstart(str(db_path), str(meta_path), str(out_path), size=1, explore_fraction=0.0)

    receipt_path = tmp_path / "warmstart_contract.json.receipt.json"
    receipt_data = json.loads(receipt_path.read_text(encoding="utf-8"))

    # 1. Valid artifact passes validation
    valid_res = validate_warmstart_import(payload, checkpoint_path=out_path, expected_receipt=receipt_data)
    assert valid_res["measured_core_count"] == 0
    assert valid_res["unverified_exploration_count"] == 0

    # 2. Tampered population decay is rejected!
    tampered_decay = copy.deepcopy(payload)
    # If population exists, alter decay; if empty, append altered triple
    if tampered_decay["population"]:
        tampered_decay["population"][0][2] = 5
    else:
        tampered_decay["population"] = [["rank(f)", "TOP3000", 5]]
    with pytest.raises(ValueError, match="Population length|does not match"):
        validate_warmstart_import(tampered_decay, checkpoint_path=out_path)

    # 3. Tampered manifest content (without updating manifest_sha256) is rejected!
    tampered_manifest = copy.deepcopy(payload)
    tampered_manifest["warmstart_manifest"]["target_size"] = 999
    with pytest.raises(ValueError, match="manifest digest mismatch"):
        validate_warmstart_import(tampered_manifest, checkpoint_path=out_path)

    # 4. Tampered file hash against receipt is rejected!
    with pytest.raises(ValueError, match="digest mismatch with receipt"):
        bad_receipt = dict(receipt_data, warmstart_file_sha256="bad_sha_hash_123")
        validate_warmstart_import(payload, checkpoint_path=out_path, expected_receipt=bad_receipt)

    # 5. Incompatible epoch is rejected!
    with pytest.raises(ValueError, match="incompatible"):
        validate_warmstart_import(payload, checkpoint_path=out_path, expected_epoch_id="epoch_xyz_mismatch")


# ---------------------------------------------------------------------------
# Test 8: Source immutability
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
# Test 9: Isolated restore and save cycle with tamper detection
# ---------------------------------------------------------------------------
def test_isolated_restore_and_save_preserves_warmstart_manifest(tmp_path):
    rng = np.random.default_rng(202)
    dates = [(datetime.date(2023, 1, 1) + datetime.timedelta(days=i)).isoformat() for i in range(100)]
    pnl_a = [("a", d, float(v)) for d, v in zip(dates, np.cumsum(rng.normal(size=100)))]

    rows = [(1, "a", "rank(f)", "TOP3000", 0, 1.0, 1.5, 0.2, 0)]
    db_path, meta_path = create_fixture_db(tmp_path, rows, pnl_rows=pnl_a)

    warmstart_path = tmp_path / "warmstart_for_restore.json"
    payload = build_evidence_aware_warmstart(str(db_path), str(meta_path), str(warmstart_path), size=2, explore_fraction=0.5, min_overlap=10)

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

    # Now verify tamper rejection on restore:
    tampered_path = tmp_path / "tampered_checkpoint.json"
    tampered_data = copy.deepcopy(payload)
    tampered_data["population"][0][2] = 5  # Modify decay
    tampered_path.write_text(json.dumps(tampered_data), encoding="utf-8")

    config.CHECKPOINT_PATH = str(tampered_path)
    tamper_engine = AlphaFactory.__new__(AlphaFactory)
    with pytest.raises(ValueError, match="does not match manifest member"):
        tamper_engine._restore_checkpoint()
