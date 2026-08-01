import sqlite3

import pytest

from mc3000_control.backup import BackupError, create_backup, inspect_backup, restore_backup
from mc3000_control.registry import DeviceRegistry
from mc3000_control.storage import BatteryStore, MeasurementStore, ProfileStore


def initialized_database(path):
    DeviceRegistry(path)
    ProfileStore(path)
    BatteryStore(path)
    MeasurementStore(path)


def test_backup_round_trip_restores_database(tmp_path) -> None:
    database = tmp_path / "mc3000-control.db"
    initialized_database(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO app_metadata(key, value) VALUES ('test', 'vorher')"
        )

    content = create_backup(database, version="test")
    inspection = inspect_backup(content)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE app_metadata SET value = 'nachher' WHERE key = 'test'"
        )

    result = restore_backup(database, content, current_version="test")

    assert inspection["manifest"]["format"] == "mc3000-control-backup"
    assert result["restart_required"] is True
    assert result["rollback_backup"]
    with sqlite3.connect(database) as connection:
        value = connection.execute(
            "SELECT value FROM app_metadata WHERE key = 'test'"
        ).fetchone()[0]
    assert value == "vorher"


def test_invalid_backup_is_rejected(tmp_path) -> None:
    with pytest.raises(BackupError, match="beschädigt"):
        inspect_backup(b"kein zip")
