"""Append-only JSONL audit sink for runtime decisions.

Phase 4 will grow this into the full hook bus. Until then, SideEffectCeiling
and PermissionsHook write permission / side-effect events here when a sink
path is configured (project ``team_sink`` or an explicit path).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def resolve_audit_sink(explicit: Path | str | None = None) -> Path | None:
    """Prefer an explicit path, then ``BBSCTL_AUDIT_SINK``, else None."""
    if explicit is not None:
        return Path(explicit)
    env = os.environ.get("BBSCTL_AUDIT_SINK", "").strip()
    if env:
        return Path(env)
    return None


def append_audit_event(
    sink: Path | str | None,
    event_type: str,
    *,
    payload: dict[str, Any] | None = None,
) -> bool:
    """Append one JSON object to ``sink``. Returns True when a line was written."""
    path = resolve_audit_sink(sink)
    if path is None:
        return False
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event_type,
        **(payload or {}),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return True


__all__ = ["append_audit_event", "resolve_audit_sink"]
