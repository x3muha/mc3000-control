from __future__ import annotations

import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(slots=True)
class RegisteredDevice:
    address: str
    alias: str
    enabled: bool
    released: bool
    serial_number: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class DeviceRegistry:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS devices (
                    address TEXT PRIMARY KEY,
                    alias TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    released INTEGER NOT NULL DEFAULT 0,
                    serial_number TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(devices)").fetchall()
            }
            if "serial_number" not in columns:
                connection.execute(
                    "ALTER TABLE devices ADD COLUMN serial_number TEXT NOT NULL DEFAULT ''"
                )

    def list(self) -> list[RegisteredDevice]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT address, alias, enabled, released, serial_number FROM devices ORDER BY created_at"
            ).fetchall()
        return [
            RegisteredDevice(
                address=row["address"],
                alias=row["alias"],
                enabled=bool(row["enabled"]),
                released=bool(row["released"]),
                serial_number=str(row["serial_number"]),
            )
            for row in rows
        ]

    def get(self, address: str) -> RegisteredDevice | None:
        normalized = normalize_address(address)
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT address, alias, enabled, released, serial_number FROM devices WHERE address = ?",
                (normalized,),
            ).fetchone()
        if row is None:
            return None
        return RegisteredDevice(
            address=row["address"],
            alias=row["alias"],
            enabled=bool(row["enabled"]),
            released=bool(row["released"]),
            serial_number=str(row["serial_number"]),
        )

    def save(
        self,
        address: str,
        alias: str,
        *,
        enabled: bool = True,
        released: bool = False,
        serial_number: str = "",
    ) -> RegisteredDevice:
        normalized = normalize_address(address)
        clean_alias = alias.strip()
        if not clean_alias:
            raise ValueError("Gerätename darf nicht leer sein")
        clean_serial_number = serial_number.strip()
        if len(clean_serial_number) > 80:
            raise ValueError("Seriennummer darf höchstens 80 Zeichen lang sein")
        now = datetime.now(UTC).isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO devices(address, alias, enabled, released, serial_number, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(address) DO UPDATE SET
                    alias = excluded.alias,
                    enabled = excluded.enabled,
                    released = excluded.released,
                    serial_number = excluded.serial_number,
                    updated_at = excluded.updated_at
                """,
                (
                    normalized,
                    clean_alias,
                    int(enabled),
                    int(released),
                    clean_serial_number,
                    now,
                    now,
                ),
            )
        return RegisteredDevice(
            normalized, clean_alias, enabled, released, clean_serial_number
        )

    def set_released(self, address: str, released: bool) -> RegisteredDevice:
        device = self.get(address)
        if device is None:
            raise KeyError(address)
        return self.save(
            device.address,
            device.alias,
            enabled=device.enabled,
            released=released,
            serial_number=device.serial_number,
        )

    def delete(self, address: str) -> RegisteredDevice:
        device = self.get(address)
        if device is None:
            raise KeyError(address)
        with self._lock, self._connect() as connection:
            connection.execute(
                "DELETE FROM devices WHERE address = ?",
                (device.address,),
            )
        return device


def normalize_address(address: str) -> str:
    value = address.strip().upper()
    parts = value.split(":")
    if len(parts) != 6 or any(
        len(part) != 2 or any(char not in "0123456789ABCDEF" for char in part)
        for part in parts
    ):
        raise ValueError("Ungültige Bluetooth-Adresse")
    return value
