"""Crash-safe JSON state and single-writer campaign ownership (Linux/WSL)."""
from __future__ import annotations
import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterator


def atomic_json(path: str | Path, value: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            json.dump(value, fh, indent=1, allow_nan=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@contextlib.contextmanager
def campaign_lock(root: str | Path) -> Iterator[None]:
    """A second runner fails immediately rather than corrupting shared state."""
    import fcntl
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.forge2.lock').open('a') as fh:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('Another Forge2 runner owns this campaign root') from exc
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def as_tuples(value):
    """Recover stdlib Random state after a JSON roundtrip."""
    return tuple(as_tuples(v) for v in value) if isinstance(value,list) else value
