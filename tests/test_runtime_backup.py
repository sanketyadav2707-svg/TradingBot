from datetime import datetime, timezone
import json
import sqlite3

import pytest

from tradingbot.runtime.backup import (
    BackupVerificationError,
    create_sqlite_backup,
    restore_sqlite_backup,
    verify_backup,
)

NOW = datetime(2026, 11, 19, 15, 0, tzinfo=timezone.utc)


def make_db(path):
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE fills (id INTEGER PRIMARY KEY, amount TEXT NOT NULL)")
        db.execute("INSERT INTO fills VALUES (1, '125.75')")
    return path


def test_verified_backup_and_restore_round_trip(tmp_path):
    source = make_db(tmp_path / "paper.sqlite3")
    backup = tmp_path / "backup.sqlite3"
    manifest = create_sqlite_backup(source, backup, created_at=NOW)
    manifest_path = tmp_path / "backup.sqlite3.manifest.json"
    assert manifest.sha256 == verify_backup(backup, manifest_path).sha256
    restored = tmp_path / "restored.sqlite3"
    restore_sqlite_backup(
        backup, manifest_path, restored,
        operator_approved=True, trading_stopped=True,
    )
    with sqlite3.connect(restored) as db:
        assert db.execute("SELECT amount FROM fills").fetchone()[0] == "125.75"


def test_backup_refuses_overwrite_and_missing_source(tmp_path):
    source = make_db(tmp_path / "paper.sqlite3")
    backup = tmp_path / "backup.sqlite3"
    with pytest.raises(ValueError, match="overwrite_source"):
        create_sqlite_backup(source, source, created_at=NOW)
    create_sqlite_backup(source, backup, created_at=NOW)
    with pytest.raises(FileExistsError, match="destination"):
        create_sqlite_backup(source, backup, created_at=NOW)
    with pytest.raises(FileNotFoundError):
        create_sqlite_backup(tmp_path / "missing.sqlite3", tmp_path / "other.sqlite3", created_at=NOW)


def test_restore_requires_stopped_engine_and_operator_approval(tmp_path):
    source = make_db(tmp_path / "paper.sqlite3")
    backup = tmp_path / "backup.sqlite3"
    create_sqlite_backup(source, backup, created_at=NOW)
    manifest = tmp_path / "backup.sqlite3.manifest.json"
    with pytest.raises(RuntimeError, match="operator_approval"):
        restore_sqlite_backup(backup, manifest, tmp_path / "restore.sqlite3",
                              operator_approved=False, trading_stopped=True)
    with pytest.raises(RuntimeError, match="stopped_engine"):
        restore_sqlite_backup(backup, manifest, tmp_path / "restore.sqlite3",
                              operator_approved=True, trading_stopped=False)


def test_modified_backup_is_rejected(tmp_path):
    source = make_db(tmp_path / "paper.sqlite3")
    backup = tmp_path / "backup.sqlite3"
    create_sqlite_backup(source, backup, created_at=NOW)
    manifest = tmp_path / "backup.sqlite3.manifest.json"
    with backup.open("ab") as out:
        out.write(b"tamper")
    with pytest.raises(BackupVerificationError, match="checksum"):
        verify_backup(backup, manifest)


def test_modified_manifest_is_rejected(tmp_path):
    source = make_db(tmp_path / "paper.sqlite3")
    backup = tmp_path / "backup.sqlite3"
    create_sqlite_backup(source, backup, created_at=NOW)
    manifest = tmp_path / "backup.sqlite3.manifest.json"
    data = json.loads(manifest.read_text())
    data["sha256"] = "0" * 64
    manifest.write_text(json.dumps(data))
    with pytest.raises(BackupVerificationError, match="checksum"):
        verify_backup(backup, manifest)


def test_restore_never_overwrites_existing_destination(tmp_path):
    source = make_db(tmp_path / "paper.sqlite3")
    backup = tmp_path / "backup.sqlite3"
    create_sqlite_backup(source, backup, created_at=NOW)
    destination = tmp_path / "existing.sqlite3"
    destination.write_text("must survive")
    with pytest.raises(FileExistsError):
        restore_sqlite_backup(
            backup, tmp_path / "backup.sqlite3.manifest.json", destination,
            operator_approved=True, trading_stopped=True,
        )
    assert destination.read_text() == "must survive"
