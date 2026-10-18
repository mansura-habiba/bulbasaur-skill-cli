"""Durable / idempotent filesystem helpers.

Operations that mutate on-disk state should:
  1. Derive the desired end state from current inputs (reconcile).
  2. Write via a temp path + ``os.replace`` so a crash never leaves a
     half-written JSON/YAML as the live file.
  3. Skip the write when the bytes already match (double-run is a no-op).

See principle: make-operations-idempotent.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> bool:
    """Write ``text`` to ``path`` atomically. Returns True if bytes changed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode(encoding)
    if path.is_file():
        try:
            if path.read_bytes() == data:
                return False
        except OSError:
            pass

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return True


def atomic_write_json(path: Path, obj: Any, *, indent: int = 2) -> bool:
    """Serialize ``obj`` as JSON and write atomically. Returns True if changed."""
    text = json.dumps(obj, indent=indent) + "\n"
    return atomic_write_text(path, text)


def replace_directory(staging: Path, destination: Path) -> None:
    """Atomically replace ``destination`` with the contents of ``staging``.

    Crash mid-flight leaves either the old destination intact or a
    recognizable ``*.replacing`` sibling — never a half-copied tree as the
    live plugin/evidence path.
    """
    staging = Path(staging)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    backup: Path | None = None
    if destination.exists():
        backup = destination.with_name(destination.name + ".replacing")
        if backup.exists():
            shutil.rmtree(backup)
        os.replace(destination, backup)

    try:
        os.replace(staging, destination)
    except Exception:
        if backup is not None and backup.exists() and not destination.exists():
            os.replace(backup, destination)
        raise

    if backup is not None and backup.exists():
        shutil.rmtree(backup, ignore_errors=True)


def purge_stale_markers(parent: Path, *, suffix: str = ".replacing") -> None:
    """Remove leftover ``*.replacing`` dirs from a prior crashed replace."""
    parent = Path(parent)
    if not parent.is_dir():
        return
    for child in parent.iterdir():
        if child.is_dir() and child.name.endswith(suffix):
            shutil.rmtree(child, ignore_errors=True)


@contextmanager
def file_lock(path: Path, *, timeout: float = 30.0) -> Iterator[None]:
    """Exclusive advisory lock for read-modify-write of ``path``.

    Locks ``{path}.lock`` (sibling file). Intended for same-host / local FS.
    Prefer ``fcntl.flock`` on POSIX; fall back to exclusive create with retry.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")

    try:
        import fcntl  # type: ignore[attr-defined]
    except ImportError:
        fcntl = None  # type: ignore[assignment]

    if fcntl is not None:
        handle = open(lock_path, "a+", encoding="utf-8")
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    handle.close()
                    raise TimeoutError(f"timed out waiting for lock: {lock_path}") from None
                time.sleep(0.05)
        try:
            yield
        finally:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()
        return

    # Windows / no-fcntl: exclusive create of the lock file.
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"timed out waiting for lock: {lock_path}") from None
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            os.close(fd)
        finally:
            try:
                lock_path.unlink(missing_ok=True)
            except OSError:
                pass


__all__ = [
    "atomic_write_json",
    "atomic_write_text",
    "file_lock",
    "purge_stale_markers",
    "replace_directory",
]
