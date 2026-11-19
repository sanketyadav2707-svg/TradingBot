"""Offline SQLite backup and verified restore for paper trading state.

No background scheduler, cloud storage, broker calls or paid services.
Restore is deliberately a separate operator-only operation; it never
overwrites a running database or starts the trading engine.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


class BackupVerificationError(RuntimeError):
    """A backup is missing, altered, incomplete, or invalid."""


@dataclass(frozen=True)
class BackupManifest:
    format_version: int
    created_at: str
    sha256: str
    size_bytes: int
    sqlite_integrity: str


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _integrity(path: Path) -> str:
    uri = path.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=10) as db:
        rows = db.execute("PRAGMA integrity_check").fetchall()
    if rows != [("ok",)]:
        raise BackupVerificationError("sqlite_integrity_check_failed")
    return "ok"


def verify_backup(backup_path: str | Path, manifest_path: str | Path) -> BackupManifest:
    backup = Path(backup_path)
    manifest_file = Path(manifest_path)
    if not backup.is_file() or not manifest_file.is_file():
        raise BackupVerificationError("backup_or_manifest_missing")
    try:
        data = json.loads(manifest_file.read_text(encoding="utf-8"))
        if set(data) != {"format_version", "created_at", "sha256", "size_bytes", "sqlite_integrity"}:
            raise ValueError("invalid_manifest_fields")
        manifest = BackupManifest(**data)
    except (ValueError, TypeError, OSError) as exc:
        raise BackupVerificationError("invalid_backup_manifest") from exc
    if manifest.format_version != 1 or manifest.sqlite_integrity != "ok":
        raise BackupVerificationError("unsupported_or_invalid_backup_manifest")
    if backup.stat().st_size != manifest.size_bytes or _hash(backup) != manifest.sha256:
        raise BackupVerificationError("backup_checksum_mismatch")
    try:
        _integrity(backup)
    except (sqlite3.Error, OSError) as exc:
        raise BackupVerificationError("sqlite_backup_unreadable") from exc
    return manifest


def create_sqlite_backup(
    source_path: str | Path,
    backup_path: str | Path,
    *,
    created_at: datetime,
) -> BackupManifest:
    if not isinstance(created_at, datetime) or created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ValueError("created_at_must_be_timezone_aware")
    source = Path(source_path)
    target = Path(backup_path)
    manifest_path = target.with_name(target.name + ".manifest.json")
    if not source.is_file():
        raise FileNotFoundError("source_database_missing")
    if source.resolve() == target.resolve():
        raise ValueError("backup_must_not_overwrite_source")
    if target.exists() or manifest_path.exists():
        raise FileExistsError("backup_destination_must_not_exist")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".paper-backup-", suffix=".sqlite3", dir=target.parent)
    os.close(fd)
    temp = Path(temporary)
    try:
        source_uri = source.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(source_uri, uri=True, timeout=10) as original:
            with sqlite3.connect(temp, timeout=10) as snapshot:
                original.backup(snapshot)
        _integrity(temp)
        manifest = BackupManifest(
            format_version=1,
            created_at=created_at.astimezone(timezone.utc).isoformat(),
            sha256=_hash(temp),
            size_bytes=temp.stat().st_size,
            sqlite_integrity="ok",
        )
        # Write the manifest before publishing the backup. If the process
        # crashes here, verification fails closed rather than trusting it.
        with manifest_path.open("x", encoding="utf-8") as out:
            json.dump(asdict(manifest), out, sort_keys=True, indent=2)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, target)
        verify_backup(target, manifest_path)
        return manifest
    finally:
        temp.unlink(missing_ok=True)


def restore_sqlite_backup(
    backup_path: str | Path,
    manifest_path: str | Path,
    destination_path: str | Path,
    *,
    operator_approved: bool,
    trading_stopped: bool,
) -> BackupManifest:
    """Restore only into a new, absent destination; never overwrite state."""
    if operator_approved is not True or trading_stopped is not True:
        raise RuntimeError("restore_requires_operator_approval_and_stopped_engine")
    destination = Path(destination_path)
    if destination.exists():
        raise FileExistsError("restore_destination_must_not_exist")
    manifest = verify_backup(backup_path, manifest_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".paper-restore-", suffix=".sqlite3", dir=destination.parent)
    os.close(fd)
    temp = Path(temporary)
    try:
        with sqlite3.connect(Path(backup_path).resolve().as_uri() + "?mode=ro", uri=True) as original:
            with sqlite3.connect(temp) as restored:
                original.backup(restored)
        if _hash(temp) != manifest.sha256:
            raise BackupVerificationError("restored_database_checksum_mismatch")
        _integrity(temp)
        # No replacement: a concurrent process creating the destination
        # must cause an error, not silent state loss.
        os.link(temp, destination)
        return manifest
    finally:
        temp.unlink(missing_ok=True)
