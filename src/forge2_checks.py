"""Lossless platform-check evidence; unknown/missing is not a passing gate."""
from __future__ import annotations
import math
import re
from dataclasses import dataclass, field


def finite(value):
    if isinstance(value,bool):return None
    try:
        v=float(value)
        return v if math.isfinite(v) else None
    except (TypeError,ValueError):
        return None


@dataclass
class CheckEvidence:
    verified: bool = False
    failed: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unknown: list[dict] = field(default_factory=list)
    raw: list[dict] = field(default_factory=list)
    sharpe_2y: float | None = None
    pnl_realization: float | None = None
    pyramid_multiplier: float | None = None


def parse_checks(metrics) -> CheckEvidence:
    out=CheckEvidence()
    if not isinstance(metrics,dict) or not isinstance(metrics.get('checks'),list) or not metrics['checks']:
        return out
    out.raw=metrics['checks']
    out.verified=True
    for c in out.raw:
        if not isinstance(c,dict):
            out.verified=False;out.unknown.append({'raw':c});continue
        name=str(c.get('name') or c.get('type') or '').strip().upper()
        result=str(c.get('result') or '').strip().upper()
        if not name or result not in {'PASS','FAIL','ERROR','PENDING','WARNING'}:
            out.verified=False;out.unknown.append(dict(c))
        elif result in {'FAIL','ERROR'}:out.failed.append(name)
        elif result=='PENDING':out.pending.append(name)
        elif result=='WARNING':out.warnings.append(name)
        normalized=re.sub('[^A-Z0-9]','',name)
        value=finite(c.get('value'))
        if value is not None:
            if ('2YEAR' in normalized or '2Y' in normalized or 'TWOYEAR' in normalized) and 'SHARPE' in normalized:
                out.sharpe_2y=value
            elif 'PNLREALIZATION' in normalized:out.pnl_realization=value
            elif 'PYRAMID' in normalized and 'MULTIPLIER' in normalized:out.pyramid_multiplier=value
    # Accept explicit metrics, never infer a metric from a limit or PASS label.
    for attr,keys in [('sharpe_2y',('sharpe2Y','sharpe2y','twoYearSharpe')),
                      ('pnl_realization',('pnlRealization',)),('pyramid_multiplier',('pyramidMultiplier',))]:
        for key in keys:
            value=finite(metrics.get(key))
            if value is not None:setattr(out,attr,value);break
    out.failed=list(dict.fromkeys(out.failed));out.pending=list(dict.fromkeys(out.pending))
    return out
