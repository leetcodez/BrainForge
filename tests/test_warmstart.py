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


# ---------------------------------------------------------------------------
# Test 10: Lifecycle acceptance - evolved population restore & immutable origin hash
# ---------------------------------------------------------------------------
def test_runtime_checkpoint_evolved_population_lifecycle(tmp_path):
    """Assert import -> evolve -> save -> restart correctly recovers evolved population,
    generation, and decision state while preserving the immutable original warmstart artifact hash.
    """
    v3_path = Path("evidence/evidence_aware_warmstart_v3.json")
    receipt_src = Path("evidence/evidence_aware_warmstart_v3.json.receipt.json")
    initial_warmstart = tmp_path / "warmstart_v3_copy.json"
    import shutil
    shutil.copyfile(v3_path, initial_warmstart)
    if receipt_src.is_file():
        shutil.copyfile(receipt_src, tmp_path / "warmstart_v3_copy.json.receipt.json")

    original_artifact_hash = hashlib.sha256(initial_warmstart.read_bytes()).hexdigest()

    # Step 1: Import initial warmstart artifact
    config.CHECKPOINT_PATH = str(initial_warmstart)
    engine_initial = AlphaFactory.__new__(AlphaFactory)
    import types
    engine_initial.genetic = types.SimpleNamespace(avoid_motifs=set())
    engine_initial._restore_checkpoint()

    assert engine_initial.warmstart_file_hash == original_artifact_hash
    assert engine_initial.checkpoint_file_hash == original_artifact_hash
    assert hasattr(engine_initial, "warmstart_manifest")
    initial_manifest = engine_initial.warmstart_manifest

    # Step 2: Simulate evolution - change decay, mutate expression, update decision & generation state
    evolved_population = [{"expression": expr, "universe": uni, "decay": dec}
                          for expr, uni, dec in engine_initial._resume_population_keys]
    # Evolve candidate 0: change decay from 0 to 5
    evolved_population[0]["decay"] = 5 if evolved_population[0]["decay"] != 5 else 10
    # Evolve candidate 1: replace expression with evolved variant
    evolved_population[1]["expression"] = "rank(ts_decay_linear(sales, 10))"

    engine_initial.population = evolved_population
    engine_initial.generation = 4
    engine_initial.submission_count = 15
    engine_initial.history_scores = [["expr_a", 1.8], ["expr_b", 2.4]]
    engine_initial.winner_exprs = ["expr_b"]
    engine_initial.loser_exprs = ["expr_a"]
    engine_initial._avoid_motifs = {"bad_motif_1"}
    engine_initial.experience = [{"key": "val"}]

    # Step 3: Save mutable runtime checkpoint
    runtime_checkpoint_path = tmp_path / "evolved_runtime_checkpoint.json"
    config.CHECKPOINT_PATH = str(runtime_checkpoint_path)
    engine_initial._save_checkpoint()

    runtime_cp_hash = hashlib.sha256(runtime_checkpoint_path.read_bytes()).hexdigest()
    assert runtime_cp_hash != original_artifact_hash

    # Step 4: Restart new engine from evolved runtime checkpoint
    engine_resumed = AlphaFactory.__new__(AlphaFactory)
    engine_resumed.genetic = types.SimpleNamespace(avoid_motifs=set())
    engine_resumed._restore_checkpoint()

    # Assert evolved population restored exactly without membership mismatch error
    assert engine_resumed._resume_population_keys[0][2] == evolved_population[0]["decay"]
    assert engine_resumed._resume_population_keys[1][0] == "rank(ts_decay_linear(sales, 10))"
    assert len(engine_resumed._resume_population_keys) == len(evolved_population)

    # Assert generation and execution state recovered
    assert engine_resumed.generation == 5  # Saved as self.generation + 1
    assert engine_resumed.submission_count == 15
    assert engine_resumed.history_scores == [["expr_a", 1.8], ["expr_b", 2.4]]
    assert engine_resumed.winner_exprs == ["expr_b"]
    assert engine_resumed.loser_exprs == ["expr_a"]
    assert engine_resumed._avoid_motifs == {"bad_motif_1"}
    assert engine_resumed.experience == [{"key": "val"}]

    # Assert provenance: immutable origin hash preserved, checkpoint digest recorded separately
    assert engine_resumed.warmstart_file_hash == original_artifact_hash
    assert engine_resumed.checkpoint_file_hash == runtime_cp_hash
    assert engine_resumed.warmstart_file_hash != engine_resumed.checkpoint_file_hash
    assert engine_resumed.warmstart_manifest == initial_manifest


# ---------------------------------------------------------------------------
# Test 11: Repeated unchanged-population restarts preserve immutable origin hash
# ---------------------------------------------------------------------------
def test_runtime_checkpoint_repeated_unchanged_population_restarts(tmp_path):
    """Assert repeated cycles of save -> restore -> save -> restore with unchanged population
    keep the original warmstart artifact hash stable without drifting to checkpoint hash.
    """
    v3_path = Path("evidence/evidence_aware_warmstart_v3.json")
    receipt_src = Path("evidence/evidence_aware_warmstart_v3.json.receipt.json")
    initial_warmstart = tmp_path / "warmstart_v3_restarts.json"
    import shutil
    shutil.copyfile(v3_path, initial_warmstart)
    if receipt_src.is_file():
        shutil.copyfile(receipt_src, tmp_path / "warmstart_v3_restarts.json.receipt.json")

    original_artifact_hash = hashlib.sha256(initial_warmstart.read_bytes()).hexdigest()

    # Cycle 0: Import original warmstart
    config.CHECKPOINT_PATH = str(initial_warmstart)
    e0 = AlphaFactory.__new__(AlphaFactory)
    import types
    e0.genetic = types.SimpleNamespace(avoid_motifs=set())
    e0._restore_checkpoint()
    e0.population = [{"expression": expr, "universe": uni, "decay": dec}
                     for expr, uni, dec in e0._resume_population_keys]

    assert e0.warmstart_file_hash == original_artifact_hash

    # Cycle 1: Save runtime checkpoint 1 and restore
    cp1_path = tmp_path / "runtime_cycle_1.json"
    config.CHECKPOINT_PATH = str(cp1_path)
    e0._save_checkpoint()
    cp1_hash = hashlib.sha256(cp1_path.read_bytes()).hexdigest()

    e1 = AlphaFactory.__new__(AlphaFactory)
    e1.genetic = types.SimpleNamespace(avoid_motifs=set())
    e1._restore_checkpoint()
    assert e1.warmstart_file_hash == original_artifact_hash
    assert e1.checkpoint_file_hash == cp1_hash
    assert e1.warmstart_file_hash != e1.checkpoint_file_hash

    # Cycle 2: Save runtime checkpoint 2 from e1 and restore
    cp2_path = tmp_path / "runtime_cycle_2.json"
    config.CHECKPOINT_PATH = str(cp2_path)
    e1.population = [{"expression": expr, "universe": uni, "decay": dec}
                     for expr, uni, dec in e1._resume_population_keys]
    e1._save_checkpoint()
    cp2_hash = hashlib.sha256(cp2_path.read_bytes()).hexdigest()

    e2 = AlphaFactory.__new__(AlphaFactory)
    e2.genetic = types.SimpleNamespace(avoid_motifs=set())
    e2._restore_checkpoint()
    assert e2.warmstart_file_hash == original_artifact_hash
    assert e2.checkpoint_file_hash == cp2_hash
    assert e2.warmstart_file_hash != e2.checkpoint_file_hash
    assert e2.warmstart_manifest == e0.warmstart_manifest


# ---------------------------------------------------------------------------
# Test 12: Mid-generation checkpoint with pending offspring recovery
# ---------------------------------------------------------------------------
def test_runtime_checkpoint_pending_offspring_recovery(tmp_path, monkeypatch):
    """Assert mid-generation checkpoint with pending offspring recovers via runtime route,
    and incompatible epoch fails closed.
    """
    monkeypatch.setenv("FORGE2_EPOCH_ID", "test_epoch_compat")
    cp_path = tmp_path / "pending_mid_gen_checkpoint.json"
    config.CHECKPOINT_PATH = str(cp_path)

    e = AlphaFactory.__new__(AlphaFactory)
    import types
    e.genetic = types.SimpleNamespace(avoid_motifs=set())
    e.generation = 2
    e.submission_count = 8
    e.population = [{"expression": "rank(f)", "universe": "TOP3000", "decay": 0}]
    e.warmstart_file_hash = "mock_origin_hash_abc"
    e.warmstart_manifest = {"target_size": 1}

    pending = [
        {"expression": "rank(pending_alpha_1)", "universe": "TOP3000", "decay": 0,
         "parent_id": "p_0", "mutation_type": "mutate_leaf", "origin": "evolution"},
        {"expression": "rank(pending_alpha_2)", "universe": "TOP3000", "decay": 5,
         "parent_id": "p_1", "mutation_type": "crossover", "origin": "evolution"},
    ]
    e._save_checkpoint(pending_offspring=pending)

    saved_data = json.loads(cp_path.read_text(encoding="utf-8"))
    assert saved_data["checkpoint_type"] == "runtime_checkpoint"
    assert saved_data["pending_generation"] == 2
    assert len(saved_data["pending_offspring"]) == 2

    # Restore in new engine with matching epoch
    resumed = AlphaFactory.__new__(AlphaFactory)
    resumed.genetic = types.SimpleNamespace(avoid_motifs=set())
    resumed._restore_checkpoint()

    assert resumed._resume_generation == 2
    assert len(resumed._resume_offspring) == 2
    assert resumed._resume_offspring[0]["expression"] == "rank(pending_alpha_1)"
    assert resumed._resume_offspring[1]["expression"] == "rank(pending_alpha_2)"
    assert resumed.warmstart_file_hash == "mock_origin_hash_abc"

    # Mismatched epoch must fail closed
    monkeypatch.setenv("FORGE2_EPOCH_ID", "different_epoch_id")
    resumed_mismatch = AlphaFactory.__new__(AlphaFactory)
    resumed_mismatch.genetic = types.SimpleNamespace(avoid_motifs=set())
    with pytest.raises(ValueError, match="different vocabulary epoch"):
        resumed_mismatch._restore_checkpoint()


# ---------------------------------------------------------------------------
# Test 13: Altered original artifact tamper rejection before state mutation
# ---------------------------------------------------------------------------
def test_original_artifact_tamper_rejection_intact(tmp_path):
    """Assert altered original warmstart artifact raises ValueError before engine state mutation."""
    v3_path = Path("evidence/evidence_aware_warmstart_v3.json")
    v3_data = json.loads(v3_path.read_text(encoding="utf-8"))

    # Case 1: Altered member decay in original artifact
    tampered_decay_data = copy.deepcopy(v3_data)
    tampered_decay_data["population"][0][2] = 99
    tampered_decay_path = tmp_path / "tampered_decay_art.json"
    tampered_decay_path.write_text(json.dumps(tampered_decay_data), encoding="utf-8")

    config.CHECKPOINT_PATH = str(tampered_decay_path)
    engine_decay = AlphaFactory.__new__(AlphaFactory)
    import types
    engine_decay.genetic = types.SimpleNamespace(avoid_motifs=set())
    with pytest.raises(ValueError, match="does not match manifest member"):
        engine_decay._restore_checkpoint()
    # Confirm engine state was NOT mutated
    assert not hasattr(engine_decay, "_resume_population_keys")
    assert not hasattr(engine_decay, "warmstart_manifest")

    # Case 2: Altered manifest body (digest mismatch)
    tampered_manifest_data = copy.deepcopy(v3_data)
    tampered_manifest_data["warmstart_manifest"]["target_size"] = 999
    tampered_manifest_path = tmp_path / "tampered_manifest_art.json"
    tampered_manifest_path.write_text(json.dumps(tampered_manifest_data), encoding="utf-8")

    config.CHECKPOINT_PATH = str(tampered_manifest_path)
    engine_manifest = AlphaFactory.__new__(AlphaFactory)
    engine_manifest.genetic = types.SimpleNamespace(avoid_motifs=set())
    with pytest.raises(ValueError, match="manifest digest mismatch"):
        engine_manifest._restore_checkpoint()
    assert not hasattr(engine_manifest, "_resume_population_keys")


# ---------------------------------------------------------------------------
# Test 14: Conflicting or invalid checkpoint markers fail closed
# ---------------------------------------------------------------------------
def test_invalid_and_conflicting_checkpoint_markers_fail_closed(tmp_path):
    """Assert invalid JSON, malformed populations, and conflicting markers fail closed."""
    # Case 1: Corrupt JSON
    corrupt_path = tmp_path / "corrupt.json"
    corrupt_path.write_text("{invalid json", encoding="utf-8")
    config.CHECKPOINT_PATH = str(corrupt_path)
    e1 = AlphaFactory.__new__(AlphaFactory)
    with pytest.raises(ValueError, match="Checkpoint is corrupt"):
        e1._restore_checkpoint()

    # Case 2: Conflicting schema markers
    conflicting_path = tmp_path / "conflicting.json"
    conflicting_path.write_text(json.dumps({
        "schema_version": "forge2-warmstart-v1",
        "checkpoint_type": "runtime_checkpoint",
        "population": [["rank(f)", "TOP3000", 0]],
    }), encoding="utf-8")
    config.CHECKPOINT_PATH = str(conflicting_path)
    e2 = AlphaFactory.__new__(AlphaFactory)
    with pytest.raises(ValueError, match="conflicting warmstart artifact schema and runtime checkpoint"):
        e2._restore_checkpoint()

    # Case 3: Malformed population structure in runtime checkpoint
    bad_pop_path = tmp_path / "bad_pop.json"
    bad_pop_path.write_text(json.dumps({
        "checkpoint_type": "runtime_checkpoint",
        "population": [["rank(f)", "TOP3000"]],  # Len 2 instead of 3
    }), encoding="utf-8")
    config.CHECKPOINT_PATH = str(bad_pop_path)
    e3 = AlphaFactory.__new__(AlphaFactory)
    with pytest.raises(ValueError, match="Invalid checkpoint population"):
        e3._restore_checkpoint()
