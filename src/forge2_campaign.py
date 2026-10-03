"""Forge2 campaign runner: the end-to-end consultant-era search loop.

    plan -> build vocabulary -> burst -> learn -> rotate

Each BURST pins one (region, delay) campaign axis, builds a fresh two-tier
vocabulary (bandit-chosen active set), and runs the stock engine for a few
generations in an ISOLATED campaign directory (own SQLite DB, own checkpoint,
own vocabulary files) via subprocess -- a fresh interpreter per burst, so the
engine's import-time vocabulary loading always sees the latest active set.

After each burst the campaign reads the engine's own database to update the
dataset bandit (finding #10), prints the pyramid-weighted keeper report and the
Meucci Effective-Number-of-Bets of the elite PnL basket (finding #12), then
rotates to the next axis by largest weight deficit (findings #3, #4).

Usage (from the BrainForge repo directory, .env configured as usual):

    python forge2_campaign.py --plan                 # show schedule + stats
    python forge2_campaign.py --build-only USA 1     # emit vocab files only
    python forge2_campaign.py --bursts 6             # run six bursts

State layout (created on demand):
    campaigns/<REGION>_d<DELAY>/data_fields.json
    campaigns/<REGION>_d<DELAY>/seed_pool.json
    campaigns/<REGION>_d<DELAY>/forge2_field_meta.json
    campaigns/<REGION>_d<DELAY>/brain_memory.db      (engine-owned)
    campaigns/<REGION>_d<DELAY>/checkpoint.json      (engine-owned)
    campaigns/<REGION>_d<DELAY>/forge2_bandit_state.json
    campaigns/<REGION>_d<DELAY>/forge2_campaign_state.json
"""

import hashlib
import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import forge2_config as F2
from forge2_storage import atomic_json, campaign_lock
from forge2_bandit import DatasetBandit
from forge2_catalog import CatalogIndex
from forge2_vocabulary import VocabularyBuilder, load_live_operators


def campaign_dir(region, delay):
    d = Path(F2.CAMPAIGN_ROOT) / (str(region).upper() + "_d" + str(int(delay)))
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_state(cdir):
    p = cdir / "forge2_campaign_state.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError("Invalid campaign state: " + str(p)) from exc
    return {"bursts_done": 0, "since_rowid": 0}


def save_state(cdir, state):
    atomic_json(cdir / "forge2_campaign_state.json", state)


def pick_axis(states):
    """Largest weight-deficit scheduling: realized burst shares converge to the
    configured axis weights, which ENFORCES the delay-0 share (finding #4)."""
    total = sum(s["bursts_done"] for s in states.values()) or 0
    best_key, best_deficit = None, None
    for key, axis in AXES.items():
        done = states[key]["bursts_done"]
        share = done / total if total else 0.0
        deficit = axis["weight"] - share
        if best_deficit is None or deficit > best_deficit:
            best_key, best_deficit = key, deficit
    return best_key


AXES = {
    str(a["region"]).upper() + "_d" + str(int(a["delay"])): a
    for a in F2.CAMPAIGN_AXES
}


def build_vocabulary(catalog, live_ops, region, delay, cdir):
    manifest_path=cdir/"forge2_epoch_manifest.json"
    manifest=json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    committed_path=cdir/manifest.get("epoch_dir", ".")/F2.BANDIT_STATE_FILE
    learned=cdir/"forge2_learning_commit.json"
    if learned.exists():
        commit=json.loads(learned.read_text())
        if commit.get("epoch_id")==manifest.get("epoch_id"):
            atomic_json(cdir/F2.BANDIT_STATE_FILE,commit["bandit"])
            committed_path=cdir/F2.BANDIT_STATE_FILE
    bandit = DatasetBandit(committed_path)
    builder = VocabularyBuilder(catalog, region, int(delay), live_ops, bandit=bandit)
    built = builder.write(cdir)
    return built


def run_burst_subprocess(repo, region, delay, cdir, generations):
    manifest=json.loads((cdir/"forge2_epoch_manifest.json").read_text())
    epoch_dir=cdir/manifest.get("epoch_dir", ".")
    for name,digest in manifest["files"].items():
        if hashlib.sha256((epoch_dir/name).read_bytes()).hexdigest()!=digest:
            raise ValueError("Incomplete/corrupted vocabulary epoch: "+name)
    env = dict(os.environ)
    env.update(F2.OVERRIDE_ENV)
    env["WQ_OPERATORS_PATH"]=str(Path(F2.OPERATORS_PATH).resolve())
    env["FORGE2_EPOCH_ID"]=manifest.get("epoch_id", "")
    env["FORGE2_POLICY_PATH"]=str(cdir/"forge2_run_policy.json")
    env["FORGE2_TRIAL_LEDGER"] = str(Path(F2.CAMPAIGN_ROOT) / "forge2_trials.sqlite")
    env["WQ_FIELD_CATALOG"] = str(epoch_dir / "data_fields.json")
    env["WQ_SEED_POOL"] = str(epoch_dir / "seed_pool.json")
    env["BRAINFORGE_DB"] = str(cdir / "brain_memory.db")
    env["WQ_CHECKPOINT"] = str(cdir / "checkpoint.json")
    cmd = [
        sys.executable, str(Path(__file__).with_name("forge2_factory.py")),
        "--region", str(region), "--delay", str(int(delay)),
        "--generations", str(int(generations)),
        "--meta", str(epoch_dir / "forge2_field_meta.json"),
        "--repo", str(repo),
    ]
    print("[forge2] launching burst:", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(repo), env=env)
    return proc.returncode


def post_burst_learning(cdir):
    """Bandit update from the engine DB + keeper/pyramid/ENB report."""
    mp=cdir/"forge2_epoch_manifest.json"
    manifest=json.loads(mp.read_text()) if mp.exists() else {}
    edir=cdir/manifest.get("epoch_dir", ".")
    learned=cdir/"forge2_learning_commit.json"
    commit=json.loads(learned.read_text()) if learned.exists() else {}
    if manifest.get("epoch_id") and commit.get("epoch_id")!=manifest["epoch_id"] and (edir/F2.BANDIT_STATE_FILE).exists():
        atomic_json(cdir/F2.BANDIT_STATE_FILE,json.loads((edir/F2.BANDIT_STATE_FILE).read_text()))
    meta_path = edir / "forge2_field_meta.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        meta = {}
    field_to_dataset = meta.get("field_to_dataset") or {}
    state = load_state(cdir)
    bandit = DatasetBandit(cdir / F2.BANDIT_STATE_FILE)
    state["since_rowid"] = bandit.update_from_db(
        cdir / "brain_memory.db", field_to_dataset,
        since_rowid=state.get("since_rowid", 0))
    bandit.save()
    manifest_path=cdir/"forge2_epoch_manifest.json"
    manifest=json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    atomic_json(cdir/"forge2_learning_commit.json",{"epoch_id":manifest.get("epoch_id"),
                 "bandit":json.loads((cdir/F2.BANDIT_STATE_FILE).read_text())})
    save_state(cdir, state)
    print("[forge2] bandit top arms:")
    for row in bandit.summary(top=10):
        print("   ", row)
    report_keepers_and_enb(cdir, meta)
    return state


def report_keepers_and_enb(cdir, meta):
    db = cdir / "brain_memory.db"
    if not db.exists():
        return
    mult_of = {}
    for expr_id, m in (meta.get("fields") or {}).items():
        for tok in expr_id.replace("(", " ").replace(")", " ").replace(",", " ").split():
            mult_of.setdefault(tok, float(m.get("multiplier") or 1.0))
    try:
        conn = sqlite3.connect(str(db))
        rows = conn.execute(
            "SELECT expression, alpha_id, sharpe, turnover, fitness "
            "FROM alpha_population WHERE sharpe IS NOT NULL "
            "ORDER BY fitness DESC LIMIT ?", (F2.ENB_REPORT_TOP_N,)).fetchall()
        keepers = [r for r in rows if (r[2] or 0) >= F2.BANDIT_SUCCESS_SHARPE]
        print("[forge2] keepers (sharpe >= %.2f): %d of top %d"
              % (F2.BANDIT_SUCCESS_SHARPE, len(keepers), len(rows)))
        alpha_ids = [r[1] for r in rows if r[1] and r[1] != "MANUAL_SEED"]
        series = {}
        for aid in alpha_ids:
            pts = conn.execute(
                "SELECT date, pnl FROM alpha_pnl WHERE alpha_id = ? ORDER BY date",
                (aid,)).fetchall()
            if len(pts) >= 60:
                series[aid] = dict(pts)
        conn.close()
    except sqlite3.Error as e:
        print("[forge2] report skipped (db error):", e)
        return
    from forge2_statistics import diversification_diagnostics
    diagnostic = diversification_diagnostics(series)
    atomic_json(cdir / "forge2_diversification.json", diagnostic)
    enb = diagnostic["value"]
    if enb is not None:
        print("[forge2] elite basket spectral effective rank = %.2f over %d PnL series"
              % (enb, len(series)))


def effective_number_of_bets(series_by_id, min_overlap=60):
    """Compatibility alias; value is spectral effective rank, NOT Meucci ENB."""
    from forge2_statistics import diversification_diagnostics
    return diversification_diagnostics(series_by_id,min_overlap)["value"]


def main():
    ap = argparse.ArgumentParser(description="Forge2 campaign runner")
    ap.add_argument("--repo", default=".", help="path to the BrainForge repo")
    ap.add_argument("--catalog", default=F2.CATALOG_PATH)
    ap.add_argument("--operators", default=F2.OPERATORS_PATH)
    ap.add_argument("--plan", action="store_true", help="print schedule + stats")
    ap.add_argument("--build-only", nargs=2, metavar=("REGION", "DELAY"),
                    help="build vocabulary files for one axis and exit")
    ap.add_argument("--bursts", type=int, default=F2.MAX_BURSTS)
    ap.add_argument("--generations", type=int, default=F2.BURST_GENERATIONS)
    args = ap.parse_args()

    print("[forge2] loading catalog:", args.catalog)
    catalog = CatalogIndex(args.catalog)
    print("[forge2] catalog fields:", len(catalog.fields))
    F2.OPERATORS_PATH=str(Path(args.operators).resolve())
    live_ops = load_live_operators(args.operators)
    print("[forge2] live operators:", len(live_ops))

    if args.plan:
        for key, axis in AXES.items():
            stats = catalog.campaign_stats(axis["region"], int(axis["delay"]))
            print("[forge2] axis", key, "weight", axis["weight"], "->", stats)
        return

    if args.build_only:
        region, delay = args.build_only[0].upper(), int(args.build_only[1])
        cdir = campaign_dir(region, delay)
        built = build_vocabulary(catalog, live_ops, region, delay, cdir)
        print("[forge2] built vocabulary ->", cdir)
        print("[forge2] stats:", json.dumps(built["stats"], indent=1))
        return

    states = {key: load_state(campaign_dir(a["region"], a["delay"]))
              for key, a in AXES.items()}
    burst_no = 0
    while True:
        if args.bursts and burst_no >= args.bursts:
            print("[forge2] burst budget reached; stopping.")
            break
        pending_axes=[k for k,a in AXES.items() if (campaign_dir(a["region"],a["delay"])/"checkpoint.json").exists()
            and json.loads((campaign_dir(a["region"],a["delay"])/"checkpoint.json").read_text()).get("pending_offspring")]
        key = pending_axes[0] if pending_axes else pick_axis(states)
        axis = AXES[key]
        region, delay = axis["region"], int(axis["delay"])
        cdir = campaign_dir(region, delay)
        print("[forge2] ===== burst %d on %s =====" % (burst_no + 1, key))
        checkpoint=cdir/"checkpoint.json"
        pending=json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
        if pending.get("pending_offspring"):
            if not (cdir/"forge2_epoch_manifest.json").exists():raise ValueError("Pending generation has no committed epoch")
            manifest=json.loads((cdir/"forge2_epoch_manifest.json").read_text())
            if getattr(catalog,"catalog_hash",None) and manifest.get("catalog_hash")!=catalog.catalog_hash:
                raise ValueError("Pending epoch catalog changed; restore recorded catalog before replay")
            print("[forge2] reusing pinned epoch; exploration/RNG unchanged")
        else:
            built = build_vocabulary(catalog, live_ops, region, delay, cdir)
            print("[forge2] vocabulary:", json.dumps(built["stats"]))
        rc = run_burst_subprocess(args.repo, region, delay, cdir, args.generations)
        states[key] = post_burst_learning(cdir)
        if rc != 0:
            raise RuntimeError("Burst failed rc=%d; completed outcomes saved, schedule not advanced" % rc)
        states[key]["bursts_done"] = states[key].get("bursts_done", 0) + 1
        save_state(cdir, states[key])
        burst_no += 1


if __name__ == "__main__":
    with campaign_lock(F2.CAMPAIGN_ROOT):
        main()
