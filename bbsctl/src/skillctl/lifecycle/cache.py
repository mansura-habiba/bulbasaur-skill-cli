"""Stage cache under ~/.cache/bbsctl/lifecycle/<stage>/<key>.json."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

from skillctl.eval.reproducibility import compute_corpus_hash, compute_skill_hash
from skillctl.lifecycle.result import Finding, EngineInfo, StageResult, StageStatus

if TYPE_CHECKING:
    from skillctl.lifecycle.engines.base import Engine, StageContext


def cache_root() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return Path(base) / "bbsctl" / "lifecycle"


def compute_stage_cache_key(
    *,
    stage: str,
    skill_hash: str,
    corpus_hash: str,
    engine_name: str,
    engine_rev: str,
    resolved_model_ids: dict[str, str] | None = None,
    stage_config: dict | None = None,
) -> str:
    payload = {
        "stage": stage,
        "skill_hash": skill_hash,
        "corpus_hash": corpus_hash,
        "engine_name": engine_name,
        "engine_rev": engine_rev,
        "resolved_model_ids": resolved_model_ids or {},
        "stage_config": stage_config or {},
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class StageCache:
    """Read/write StageResult JSON keyed by stage cache key."""

    def get(self, ctx: StageContext, engine: Engine) -> StageResult | None:
        key = self._key(ctx, engine)
        path = cache_root() / ctx.stage.value / f"{key}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return _result_from_dict(data)

    def put(self, ctx: StageContext, engine: Engine, result: StageResult) -> Path:
        key = self._key(ctx, engine)
        d = cache_root() / ctx.stage.value
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{key}.json"
        path.write_text(
            json.dumps(result.to_dict(), indent=2, default=str), encoding="utf-8"
        )
        return path

    def _key(self, ctx: StageContext, engine: Engine) -> str:
        skill_hash = compute_skill_hash(ctx.skill_dir)
        corpus_hash = compute_corpus_hash(ctx.skill_dir)
        rev = engine.version() or ""
        models = engine.resolved_model_ids(ctx) if hasattr(engine, "resolved_model_ids") else {}
        stage_cfg = {
            "strictness": ctx.strictness.value,
            "scan_engine": ctx.config.scan_engine,
            "certify_engine": ctx.config.certify_engine,
        }
        return compute_stage_cache_key(
            stage=ctx.stage.value,
            skill_hash=skill_hash,
            corpus_hash=corpus_hash,
            engine_name=engine.name,
            engine_rev=rev,
            resolved_model_ids=models,
            stage_config=stage_cfg,
        )


def _result_from_dict(data: dict) -> StageResult:
    findings = [
        Finding(
            severity=str(f.get("severity", "")),
            message=str(f.get("message", "")),
            rule_id=str(f.get("rule_id", "")),
            location=str(f.get("location", "")),
        )
        for f in (data.get("findings") or [])
    ]
    eng = data.get("engine") or {}
    return StageResult(
        stage=str(data.get("stage", "")),
        status=StageStatus(str(data.get("status", "failed"))),
        findings=findings,
        artifacts=dict(data.get("artifacts") or {}),
        engine=EngineInfo(
            name=str(eng.get("name", "")),
            version=str(eng.get("version", "")),
            revision=str(eng.get("revision", "")),
        ),
        duration_ms=int(data.get("duration_ms") or 0),
        cached=True,
        detail=str(data.get("detail") or ""),
    )


__all__ = [
    "StageCache",
    "cache_root",
    "compute_stage_cache_key",
]
