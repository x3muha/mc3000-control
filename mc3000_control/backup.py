from __future__ import annotations

import io
import json
import os
import sqlite3
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REQUIRED_TABLES = {
    "devices",
    "profiles",
    "batteries",
    "recording_runs",
    "measurements",
}
MAX_BACKUP_BYTES = 250 * 1024 * 1024


class BackupError(ValueError):
    """Raised when a backup cannot be created or restored safely."""


def create_backup(database_path: str | Path, *, version: str) -> bytes:
    source_path = Path(database_path)
    if not source_path.exists():
        raise BackupError("Datenbank wurde nicht gefunden")
    created_at = datetime.now(UTC).isoformat()
    with tempfile.TemporaryDirectory(prefix="mc3000-backup-") as temporary:
        snapshot_path = Path(temporary) / "mc3000-control.db"
        source = sqlite3.connect(source_path, timeout=30)
        target = sqlite3.connect(snapshot_path)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        manifest = {
            "format": "mc3000-control-backup",
            "format_version": 1,
            "application_version": version,
            "created_at": created_at,
            "database_file": "mc3000-control.db",
        }
        output = io.BytesIO()
        with zipfile.ZipFile(
            output,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        ) as archive:
            archive.writestr(
                "manifest.json",
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            )
            archive.write(snapshot_path, "mc3000-control.db")
        return output.getvalue()


def inspect_backup(content: bytes) -> dict[str, Any]:
    if not content:
        raise BackupError("Backup-Datei ist leer")
    if len(content) > MAX_BACKUP_BYTES:
        raise BackupError("Backup-Datei ist größer als 250 MB")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = set(archive.namelist())
            if "manifest.json" not in names or "mc3000-control.db" not in names:
                raise BackupError("Backup enthält nicht die erwarteten Dateien")
            if archive.getinfo("mc3000-control.db").file_size > MAX_BACKUP_BYTES:
                raise BackupError("Datenbank im Backup ist größer als 250 MB")
            manifest = json.loads(archive.read("manifest.json"))
            if manifest.get("format") != "mc3000-control-backup":
                raise BackupError("Datei ist kein Open-MC3000-Control-Backup")
            database = archive.read("mc3000-control.db")
    except (json.JSONDecodeError, zipfile.BadZipFile) as exc:
        raise BackupError("Backup-Datei ist beschädigt") from exc

    with tempfile.TemporaryDirectory(prefix="mc3000-validate-") as temporary:
        database_path = Path(temporary) / "mc3000-control.db"
        database_path.write_bytes(database)
        try:
            connection = sqlite3.connect(database_path)
            integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        except sqlite3.DatabaseError as exc:
            raise BackupError("Datenbank im Backup ist beschädigt") from exc
        finally:
            if "connection" in locals():
                connection.close()
    missing = sorted(REQUIRED_TABLES - tables)
    if integrity.lower() != "ok":
        raise BackupError(f"Datenbankprüfung fehlgeschlagen: {integrity}")
    if missing:
        raise BackupError(
            "Backup ist unvollständig; fehlende Tabellen: " + ", ".join(missing)
        )
    return {
        "manifest": manifest,
        "database_bytes": len(database),
        "tables": sorted(tables),
    }


def restore_backup(
    database_path: str | Path,
    content: bytes,
    *,
    current_version: str,
) -> dict[str, Any]:
    inspection = inspect_backup(content)
    target = Path(database_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    backup_dir = target.parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    rollback_path = backup_dir / f"vor-wiederherstellung-{timestamp}.zip"
    if target.exists():
        rollback_path.write_bytes(create_backup(target, version=current_version))

    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        database = archive.read("mc3000-control.db")
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=".mc3000-restore-",
        suffix=".db",
        dir=target.parent,
    )
    try:
        with os.fdopen(file_descriptor, "wb") as handle:
            handle.write(database)
            handle.flush()
            os.fsync(handle.fileno())
        Path(f"{target}-wal").unlink(missing_ok=True)
        Path(f"{target}-shm").unlink(missing_ok=True)
        os.replace(temporary_name, target)
    finally:
        Path(temporary_name).unlink(missing_ok=True)
    return {
        "ok": True,
        "manifest": inspection["manifest"],
        "rollback_backup": rollback_path.name if rollback_path.exists() else None,
        "restart_required": True,
    }
