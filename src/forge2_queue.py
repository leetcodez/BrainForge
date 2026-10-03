"""Advisory queue ordering with reserved exploration; NEVER drops a candidate."""
from __future__ import annotations
import math
import random


def prioritize(candidates, scorer, explore_fraction=.2, rng=None):
    candidates=list(candidates);rng=rng or random
    if not candidates:return []
    scores=[]
    for candidate in candidates:
        try:
            value=scorer(*candidate)
            value=float(value) if value is not None else None
            if value is not None and not math.isfinite(value):value=None
        except Exception:value=None
        scores.append(value)
    if all(s is None for s in scores):return candidates
    exploratory=rng.sample(range(len(candidates)),max(1,round(len(candidates)*explore_fraction)))
    ranked=sorted((i for i in range(len(candidates)) if i not in set(exploratory)),
                  key=lambda i:scores[i] if scores[i] is not None else -1,reverse=True)
    # Spread exploratory proposals through the queue, not in an ignored tail.
    order=[];stride=max(1,round(1/max(explore_fraction,1/len(candidates))))
    while ranked or exploratory:
        for _ in range(stride-1):
            if ranked:order.append(ranked.pop(0))
        if exploratory:order.append(exploratory.pop(0))
        elif ranked:order.append(ranked.pop(0))
    return [candidates[i] for i in order]
