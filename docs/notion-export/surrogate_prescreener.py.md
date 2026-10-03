```python
"""Cheap surrogate model that predicts whether a candidate alpha is worth a real
simulation. SHADOW-SAFE: this module only TRAINS and SCORES. Nothing here gates
the orchestrator. Featurization is pure-stdlib AST + config.field_family, so it
adds no runtime cost beyond a dict lookup.

    python surrogate_prescreener.py        # train on alpha_population, save model
"""
import ast
import pickle

import config
from db_manager import DatabaseManager

_FAMILIES = ["options_vol", "earnings_event", "analyst", "fundamental",
             "sentiment", "macro", "relationship", "price_volume"]
_GATE_OPS = ("trade_when", "keep")


def _ast_depth(tree):
    if tree is None:
        return 1
    def d(n):
        ch = list(ast.iter_child_nodes(n))
        return 1 + max((d(c) for c in ch), default=0)
    return d(tree)


def feature_names():
    base = ["expr_len", "ast_depth", "n_calls", "n_unique_ops", "n_gate_ops",
            "has_group_neutralize", "decay"]
    return base + [f"fam_{f}" for f in _FAMILIES] + [f"univ_{u}" for u in config.UNIVERSES]


def featurize(expression, universe="TOP3000", decay=0):
    try:
        tree = ast.parse(expression, mode="eval")
    except Exception:
        tree = None
    nodes = list(ast.walk(tree)) if tree else []
    call_nodes = [n for n in nodes if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    op_names = [n.func.id.lower() for n in call_nodes]
    names = [n.id for n in nodes if isinstance(n, ast.Name)]
    feats = [
        float(len(expression or "")),
        float(_ast_depth(tree)),
        float(len(call_nodes)),
        float(len(set(op_names))),
        float(sum(1 for o in op_names if o in _GATE_OPS)),
        1.0 if "group_neutralize" in op_names else 0.0,
        float(decay or 0),
    ]
    fam_counts = {f: 0 for f in _FAMILIES}
    for nm in names:
        fam = config.field_family(nm)
        if fam in fam_counts:
            fam_counts[fam] += 1
    feats += [float(fam_counts[f]) for f in _FAMILIES]
    feats += [1.0 if universe == u else 0.0 for u in config.UNIVERSES]
    return feats


def _is_winner(sharpe, turnover):
    if sharpe is None:
        return 0
    if sharpe < config.SURROGATE_WINNER_SHARPE:
        return 0
    t = turnover if turnover is not None else 0.0
    if t < getattr(config, "MIN_TURNOVER", 0.0) or t > config.MAX_TURNOVER:
        return 0
    return 1


def load_dataset(db=None):
    own = db is None
    if own:
        db = DatabaseManager(); db.init_db_sync()
    # Time-ordered (by insertion id) so evaluate_prescreener's 70/30 split is an
    # honest FORWARD split, not arbitrary engine order. Falls back to the
    # unordered loader on an older db_manager.
    loader = getattr(db, "load_history_chrono_sync", db.load_history_sync)
    rows = loader()  # (expr, universe, decay, sharpe, turnover, ...)
    X, y = [], []
    for expr, universe, decay, sharpe, turnover, *_ in rows:
        if sharpe is None:
            continue
        X.append(featurize(expr, universe, decay))
        y.append(_is_winner(sharpe, turnover))
    if own:
        db.close_sync()
    return X, y


def _new_classifier():
    try:
        from lightgbm import LGBMClassifier
        return LGBMClassifier(n_estimators=200, max_depth=-1, learning_rate=0.05,
                              subsample=0.8, class_weight="balanced")
    except Exception:
        from sklearn.ensemble import GradientBoostingClassifier
        return GradientBoostingClassifier(n_estimators=200, max_depth=3,
                                          learning_rate=0.05)


def train(model_path=None):
    X, y = load_dataset()
    pos = sum(y)
    print(f"Training rows: {len(y)} | winners: {pos} | losers: {len(y) - pos}")
    if len(y) < 50 or pos < 10 or pos == len(y):
        print("Not enough class balance to train a trustworthy model. Aborting.")
        return None
    clf = _new_classifier()
    clf.fit(X, y)
    path = model_path or config.SURROGATE_MODEL_PATH
    with open(path, "wb") as fh:
        pickle.dump({"model": clf, "features": feature_names()}, fh)
    print(f"Saved surrogate model -> {path}")
    return clf


_CACHE = {}


def _load_model():
    if "model" not in _CACHE:
        try:
            with open(config.SURROGATE_MODEL_PATH, "rb") as fh:
                _CACHE["model"] = pickle.load(fh)["model"]
        except Exception:
            _CACHE["model"] = None
    return _CACHE["model"]


def score(expression, universe="TOP3000", decay=0):
    """Predicted P(winner) in [0, 1], or None when no model is available.
    SHADOW callers must treat None / low scores as advisory only."""
    model = _load_model()
    if model is None:
        return None
    try:
        return float(model.predict_proba([featurize(expression, universe, decay)])[0][1])
    except Exception:
        return None


if __name__ == "__main__":
    train()
```