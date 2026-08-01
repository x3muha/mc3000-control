from __future__ import annotations

import csv
import io
import json
import math
import sqlite3
import threading
from uuid import uuid4
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .battery_manager import (
    AUTOMATIC_PROGRAMS,
    AutomaticProgramValues,
    BatteryError,
    BatteryValues,
    validate_automatic_program,
    validate_battery,
)
from .profiles import (
    DEFAULT_MANUAL_TIME_LIMIT_MIN,
    ProfileValues,
    validate_profile,
)
from .protocol import BATTERY_TYPES, STATUS_NAMES, mode_name
from .registry import normalize_address

PROFILE_FIELDS = tuple(ProfileValues.__dataclass_fields__)
MEASUREMENT_COLUMNS = (
    "recorded_at",
    "address",
    "slot",
    "run_id",
    "profile_id",
    "battery_id",
    "battery_type_code",
    "mode_code",
    "status_code",
    "active",
    "time_s",
    "voltage_mv",
    "current_ma",
    "capacity_mah",
    "temperature_c",
    "resistance_mohm",
    "cycle_count",
)


@dataclass(frozen=True, slots=True)
class StoredProfile:
    id: int
    values: ProfileValues
    is_builtin: bool
    created_at: str
    updated_at: str
    category_key: str = "general"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            **self.values.to_dict(),
            "is_builtin": self.is_builtin,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "category_key": self.category_key,
        }


@dataclass(frozen=True, slots=True)
class StoredAutomaticProfile:
    key: str
    values: AutomaticProgramValues
    is_builtin: bool
    created_at: str
    updated_at: str
    category_key: str = "automatic"

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            **self.values.to_dict(),
            "is_builtin": self.is_builtin,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "category_key": self.category_key,
        }


@dataclass(frozen=True, slots=True)
class StoredBattery:
    id: int
    values: BatteryValues
    created_at: str
    updated_at: str
    archived_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            **self.values.to_dict(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "archived_at": self.archived_at,
        }


class SQLiteStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=10000")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection


class ProfileStore(SQLiteStore):
    def __init__(self, path: str | Path) -> None:
        super().__init__(path)
        self._initialize()
        self._seed_categories()
        self._seed_defaults()
        self._seed_automatic_profiles()
        self._assign_default_categories()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    battery_type_code INTEGER NOT NULL,
                    mode_code INTEGER NOT NULL,
                    capacity_mah INTEGER NOT NULL,
                    charge_current_ma INTEGER NOT NULL,
                    discharge_current_ma INTEGER NOT NULL,
                    charge_voltage_mv INTEGER NOT NULL,
                    discharge_voltage_mv INTEGER NOT NULL,
                    charge_end_current_ma INTEGER NOT NULL,
                    discharge_end_current_ma INTEGER NOT NULL,
                    charge_rest_min INTEGER NOT NULL,
                    discharge_rest_min INTEGER NOT NULL,
                    cycle_count INTEGER NOT NULL,
                    cycle_mode INTEGER NOT NULL,
                    delta_peak_mv INTEGER NOT NULL,
                    trickle_current_ma INTEGER NOT NULL,
                    keep_voltage_mv INTEGER NOT NULL,
                    temp_limit_c INTEGER NOT NULL,
                    time_limit_min INTEGER NOT NULL,
                    time_limit_mode TEXT NOT NULL DEFAULT 'manual',
                    is_builtin INTEGER NOT NULL DEFAULT 0,
                    category_key TEXT NOT NULL DEFAULT 'general',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            _add_column_if_missing(
                connection,
                "profiles",
                "time_limit_mode TEXT NOT NULL DEFAULT 'manual'",
            )
            _add_column_if_missing(
                connection,
                "profiles",
                "is_builtin INTEGER NOT NULL DEFAULT 0",
            )
            _add_column_if_missing(
                connection,
                "profiles",
                "category_key TEXT NOT NULL DEFAULT 'general'",
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS profile_assignments (
                    address TEXT NOT NULL,
                    slot INTEGER NOT NULL,
                    profile_id INTEGER,
                    applied_at TEXT NOT NULL,
                    PRIMARY KEY(address, slot),
                    FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE SET NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS slot_program_assignments (
                    address TEXT NOT NULL,
                    slot INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    label TEXT NOT NULL,
                    details_json TEXT NOT NULL DEFAULT '{}',
                    battery_id INTEGER,
                    profile_id INTEGER,
                    selected_at TEXT NOT NULL,
                    PRIMARY KEY(address, slot)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS app_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS automatic_profiles (
                    key TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    mode_code INTEGER NOT NULL,
                    charge_c_rate REAL NOT NULL,
                    discharge_c_rate REAL NOT NULL,
                    cycle_count INTEGER NOT NULL,
                    cycle_mode INTEGER NOT NULL,
                    charge_rest_min INTEGER NOT NULL DEFAULT 0,
                    discharge_rest_min INTEGER NOT NULL DEFAULT 0,
                    temp_limit_c INTEGER NOT NULL DEFAULT 45,
                    time_limit_mode TEXT NOT NULL DEFAULT 'manual',
                    time_limit_min INTEGER NOT NULL DEFAULT 360,
                    is_builtin INTEGER NOT NULL DEFAULT 0,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    category_key TEXT NOT NULL DEFAULT 'automatic',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            _add_column_if_missing(
                connection,
                "automatic_profiles",
                "category_key TEXT NOT NULL DEFAULT 'automatic'",
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS profile_categories (
                    key TEXT PRIMARY KEY,
                    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    description TEXT NOT NULL DEFAULT '',
                    is_builtin INTEGER NOT NULL DEFAULT 0,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def list(self) -> list[StoredProfile]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM profiles ORDER BY name, id"
            ).fetchall()
        return [_profile_from_row(row) for row in rows]

    def get(self, profile_id: int) -> StoredProfile | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM profiles WHERE id = ?",
                (profile_id,),
            ).fetchone()
        return _profile_from_row(row) if row is not None else None

    def save(
        self,
        values: ProfileValues,
        *,
        profile_id: int | None = None,
        category_key: str = "general",
    ) -> StoredProfile:
        validate_profile(values)
        clean_values = ProfileValues(
            **{
                **{field: getattr(values, field) for field in PROFILE_FIELDS},
                "name": values.name.strip(),
                "description": values.description.strip(),
            }
        )
        now = datetime.now(UTC).isoformat()
        data = [getattr(clean_values, field) for field in PROFILE_FIELDS]
        category_key = self._require_category(category_key)

        with self._lock, self._connect() as connection:
            if profile_id is None:
                placeholders = ", ".join("?" for _ in PROFILE_FIELDS)
                cursor = connection.execute(
                    f"""
                    INSERT INTO profiles ({", ".join(PROFILE_FIELDS)}, category_key, created_at, updated_at)
                    VALUES ({placeholders}, ?, ?, ?)
                    """,
                    (*data, category_key, now, now),
                )
                profile_id = int(cursor.lastrowid)
            else:
                if (
                    connection.execute(
                        "SELECT 1 FROM profiles WHERE id = ?",
                        (profile_id,),
                    ).fetchone()
                    is None
                ):
                    raise KeyError(profile_id)
                assignments = ", ".join(f"{field} = ?" for field in PROFILE_FIELDS)
                connection.execute(
                    f"UPDATE profiles SET {assignments}, category_key = ?, updated_at = ? WHERE id = ?",
                    (*data, category_key, now, profile_id),
                )

        stored = self.get(profile_id)
        if stored is None:
            raise RuntimeError("Profil konnte nicht gespeichert werden")
        return stored

    def delete(self, profile_id: int) -> None:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM profiles WHERE id = ?", (profile_id,)
            )
            if cursor.rowcount == 0:
                raise KeyError(profile_id)

    def list_automatic(self) -> list[StoredAutomaticProfile]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM automatic_profiles
                ORDER BY sort_order, label COLLATE NOCASE, key
                """
            ).fetchall()
        return [_automatic_profile_from_row(row) for row in rows]

    def get_automatic(self, program_key: str) -> StoredAutomaticProfile | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM automatic_profiles WHERE key = ?",
                (program_key,),
            ).fetchone()
        return _automatic_profile_from_row(row) if row is not None else None

    def save_automatic(
        self,
        values: AutomaticProgramValues,
        *,
        program_key: str | None = None,
        category_key: str = "automatic",
    ) -> StoredAutomaticProfile:
        clean = validate_automatic_program(values)
        category_key = self._require_category(category_key)
        now = datetime.now(UTC).isoformat()
        data = (
            clean.label,
            clean.description,
            clean.mode_code,
            clean.charge_c_rate,
            clean.discharge_c_rate,
            clean.cycle_count,
            clean.cycle_mode,
            clean.charge_rest_min,
            clean.discharge_rest_min,
            clean.temp_limit_c,
            clean.time_limit_mode,
            clean.time_limit_min,
        )
        with self._lock, self._connect() as connection:
            if program_key is None:
                program_key = f"own_{uuid4().hex}"
                next_order = int(
                    connection.execute(
                        "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM automatic_profiles"
                    ).fetchone()[0]
                )
                connection.execute(
                    """
                    INSERT INTO automatic_profiles(
                        key, label, description, mode_code, charge_c_rate,
                        discharge_c_rate, cycle_count, cycle_mode,
                        charge_rest_min, discharge_rest_min, temp_limit_c,
                        time_limit_mode, time_limit_min, is_builtin, sort_order,
                        category_key,
                        created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
                    """,
                    (program_key, *data, next_order, category_key, now, now),
                )
            else:
                cursor = connection.execute(
                    """
                    UPDATE automatic_profiles
                    SET label = ?, description = ?, mode_code = ?,
                        charge_c_rate = ?, discharge_c_rate = ?,
                        cycle_count = ?, cycle_mode = ?, charge_rest_min = ?,
                        discharge_rest_min = ?, temp_limit_c = ?,
                        time_limit_mode = ?, time_limit_min = ?, updated_at = ?
                        , category_key = ?
                    WHERE key = ?
                    """,
                    (*data, now, category_key, program_key),
                )
                if cursor.rowcount == 0:
                    raise KeyError(program_key)

        stored = self.get_automatic(program_key)
        if stored is None:
            raise RuntimeError("Automatikprofil konnte nicht gespeichert werden")
        return stored

    def assign(self, address: str, slots: Iterable[int], profile_id: int) -> None:
        normalized = normalize_address(address)
        now = datetime.now(UTC).isoformat()
        clean_slots = sorted(set(slots))
        if not clean_slots or any(slot not in range(1, 5) for slot in clean_slots):
            raise ValueError("Slot muss zwischen 1 und 4 liegen")
        if self.get(profile_id) is None:
            raise KeyError(profile_id)
        with self._lock, self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO profile_assignments(address, slot, profile_id, applied_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(address, slot) DO UPDATE SET
                    profile_id = excluded.profile_id,
                    applied_at = excluded.applied_at
                """,
                [(normalized, slot, profile_id, now) for slot in clean_slots],
            )

    def assignments_for(self, address: str) -> dict[int, int]:
        normalized = normalize_address(address)
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT slot, profile_id
                FROM profile_assignments
                WHERE address = ? AND profile_id IS NOT NULL
                """,
                (normalized,),
            ).fetchall()
        return {int(row["slot"]): int(row["profile_id"]) for row in rows}

    def clear_assignments(self, address: str, slots: Iterable[int]) -> None:
        normalized = normalize_address(address)
        clean_slots = sorted(set(slots))
        if not clean_slots or any(slot not in range(1, 5) for slot in clean_slots):
            raise ValueError("Slot muss zwischen 1 und 4 liegen")
        with self._lock, self._connect() as connection:
            connection.executemany(
                "DELETE FROM profile_assignments WHERE address = ? AND slot = ?",
                [(normalized, slot) for slot in clean_slots],
            )

    def set_slot_program(
        self,
        address: str,
        slot: int,
        *,
        source: str,
        label: str,
        details: dict[str, Any],
        battery_id: int | None,
        profile_id: int | None,
    ) -> None:
        normalized = normalize_address(address)
        if slot not in range(1, 5):
            raise ValueError("Slot muss zwischen 1 und 4 liegen")
        if source not in {"profile", "standard", "automatic"}:
            raise ValueError("Unbekannte Programmquelle")
        clean_label = label.strip()
        if not clean_label:
            raise ValueError("Programmname darf nicht leer sein")
        now = datetime.now(UTC).isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO slot_program_assignments(
                    address, slot, source, label, details_json,
                    battery_id, profile_id, selected_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(address, slot) DO UPDATE SET
                    source = excluded.source,
                    label = excluded.label,
                    details_json = excluded.details_json,
                    battery_id = excluded.battery_id,
                    profile_id = excluded.profile_id,
                    selected_at = excluded.selected_at
                """,
                (
                    normalized,
                    slot,
                    source,
                    clean_label,
                    json.dumps(details, ensure_ascii=True, separators=(",", ":")),
                    battery_id,
                    profile_id,
                    now,
                ),
            )

    def programs_for(self, address: str) -> dict[int, dict[str, Any]]:
        normalized = normalize_address(address)
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT slot, source, label, details_json,
                       battery_id, profile_id, selected_at
                FROM slot_program_assignments
                WHERE address = ?
                """,
                (normalized,),
            ).fetchall()
        programs: dict[int, dict[str, Any]] = {}
        for row in rows:
            try:
                details = json.loads(str(row["details_json"]))
            except (TypeError, ValueError):
                details = {}
            programs[int(row["slot"])] = {
                "source": str(row["source"]),
                "label": str(row["label"]),
                "details": details if isinstance(details, dict) else {},
                "battery_id": row["battery_id"],
                "profile_id": row["profile_id"],
                "selected_at": str(row["selected_at"]),
            }
        return programs

    def clear_slot_programs(self, address: str, slots: Iterable[int]) -> None:
        normalized = normalize_address(address)
        clean_slots = sorted(set(slots))
        if any(slot not in range(1, 5) for slot in clean_slots):
            raise ValueError("Slot muss zwischen 1 und 4 liegen")
        if not clean_slots:
            return
        with self._lock, self._connect() as connection:
            connection.executemany(
                "DELETE FROM slot_program_assignments WHERE address = ? AND slot = ?",
                [(normalized, slot) for slot in clean_slots],
            )

    def clear_programs_for_battery(self, battery_id: int) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "DELETE FROM slot_program_assignments WHERE battery_id = ?",
                (battery_id,),
            )

    def get_app_setting(self, key: str, default: str = "") -> str:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT value FROM app_metadata WHERE key = ?",
                (key,),
            ).fetchone()
        return str(row["value"]) if row is not None else default

    def set_app_setting(self, key: str, value: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO app_metadata(key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )

    def list_categories(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT key, name, description, is_builtin, sort_order
                FROM profile_categories
                ORDER BY sort_order, name COLLATE NOCASE
                """
            ).fetchall()
        return [
            {
                "key": str(row["key"]),
                "name": str(row["name"]),
                "description": str(row["description"]),
                "is_builtin": bool(row["is_builtin"]),
                "sort_order": int(row["sort_order"]),
            }
            for row in rows
        ]

    def create_category(self, name: str) -> dict[str, Any]:
        clean_name = name.strip()
        if not clean_name or len(clean_name) > 60:
            raise ValueError("Kategoriename muss zwischen 1 und 60 Zeichen lang sein")
        now = datetime.now(UTC).isoformat()
        key = f"custom_{uuid4().hex}"
        try:
            with self._lock, self._connect() as connection:
                sort_order = int(
                    connection.execute(
                        "SELECT COALESCE(MAX(sort_order), 99) + 1 FROM profile_categories"
                    ).fetchone()[0]
                )
                connection.execute(
                    """
                    INSERT INTO profile_categories(
                        key, name, description, is_builtin, sort_order,
                        created_at, updated_at
                    )
                    VALUES (?, ?, '', 0, ?, ?, ?)
                    """,
                    (key, clean_name, sort_order, now, now),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Diese Profilkategorie gibt es bereits") from exc
        return next(
            category
            for category in self.list_categories()
            if category["key"] == key
        )

    def delete_category(self, key: str) -> None:
        clean_key = self._require_category(key)
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT is_builtin FROM profile_categories WHERE key = ?",
                (clean_key,),
            ).fetchone()
            if row is None:
                raise KeyError(key)
            if bool(row["is_builtin"]):
                raise ValueError("Standardkategorien können nicht gelöscht werden")
            connection.execute(
                "UPDATE profiles SET category_key = 'general' WHERE category_key = ?",
                (clean_key,),
            )
            connection.execute(
                "UPDATE automatic_profiles SET category_key = 'automatic' WHERE category_key = ?",
                (clean_key,),
            )
            connection.execute(
                "DELETE FROM profile_categories WHERE key = ?",
                (clean_key,),
            )

    def _require_category(self, key: str) -> str:
        clean_key = key.strip() or "general"
        with self._lock, self._connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM profile_categories WHERE key = ?",
                (clean_key,),
            ).fetchone()
        if exists is None:
            raise ValueError("Profilkategorie wurde nicht gefunden")
        return clean_key

    def _seed_categories(self) -> None:
        now = datetime.now(UTC).isoformat()
        defaults = (
            ("general", "Allgemein", "Allgemeine und nicht zugeordnete Profile.", 10),
            ("automatic", "Automatik", "Kapazitätsbasierte Automatikprogramme.", 20),
            ("lithium", "Lithium", "Profile für Lithium-Akkus.", 30),
            ("nickel", "Nickel", "Profile für Nickel-Akkus.", 40),
        )
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO profile_categories(
                    key, name, description, is_builtin, sort_order,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, 1, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    is_builtin = 1,
                    sort_order = excluded.sort_order
                """,
                [(*item, now, now) for item in defaults],
            )

    def _assign_default_categories(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE profiles
                SET category_key = CASE
                    WHEN battery_type_code IN (0, 1, 2, 8, 9) THEN 'lithium'
                    WHEN battery_type_code IN (3, 4, 6) THEN 'nickel'
                    ELSE 'general'
                END
                WHERE is_builtin = 1
                """
            )
            connection.execute(
                """
                UPDATE automatic_profiles
                SET category_key = 'automatic'
                WHERE is_builtin = 1
                """
            )

    def _seed_defaults(self) -> None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value FROM app_metadata WHERE key = 'default_profiles_version'"
            ).fetchone()
            version = int(row["value"]) if row is not None else 0
            existing_names = {
                str(item["name"])
                for item in connection.execute("SELECT name FROM profiles").fetchall()
            }
        if version >= 4:
            return
        defaults = _default_profiles()
        if version < 2:
            for profile in defaults:
                if profile.name not in existing_names:
                    self.save(profile)
        with self._connect() as connection:
            if version < 3:
                names = [profile.name for profile in defaults]
                placeholders = ", ".join("?" for _ in names)
                connection.execute(
                    f"""
                    UPDATE profiles
                    SET time_limit_mode = 'manual',
                        time_limit_min = ?,
                        updated_at = ?
                    WHERE name IN ({placeholders})
                      AND description = ?
                      AND time_limit_min IN (240, 360)
                    """,
                    (
                        DEFAULT_MANUAL_TIME_LIMIT_MIN,
                        datetime.now(UTC).isoformat(),
                        *names,
                        "Beispielprofil. Werte vor dem Anwenden an den Akku anpassen.",
                    ),
                )
            if version < 4:
                names = [profile.name for profile in defaults]
                placeholders = ", ".join("?" for _ in names)
                connection.execute(
                    f"""
                    UPDATE profiles
                    SET is_builtin = 1
                    WHERE name IN ({placeholders})
                      AND description = ?
                    """,
                    (
                        *names,
                        "Beispielprofil. Werte vor dem Anwenden an den Akku anpassen.",
                    ),
                )
            connection.execute(
                """
                INSERT INTO app_metadata(key, value)
                VALUES ('default_profiles_version', '4')
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """
            )

    def _seed_automatic_profiles(self) -> None:
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            for sort_order, (program_key, raw_values) in enumerate(
                AUTOMATIC_PROGRAMS.items()
            ):
                values = validate_automatic_program(
                    AutomaticProgramValues.from_mapping(raw_values)
                )
                connection.execute(
                    """
                    INSERT INTO automatic_profiles(
                        key, label, description, mode_code, charge_c_rate,
                        discharge_c_rate, cycle_count, cycle_mode,
                        charge_rest_min, discharge_rest_min, temp_limit_c,
                        time_limit_mode, time_limit_min, is_builtin, sort_order,
                        created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
                    ON CONFLICT(key) DO NOTHING
                    """,
                    (
                        program_key,
                        values.label,
                        values.description,
                        values.mode_code,
                        values.charge_c_rate,
                        values.discharge_c_rate,
                        values.cycle_count,
                        values.cycle_mode,
                        values.charge_rest_min,
                        values.discharge_rest_min,
                        values.temp_limit_c,
                        values.time_limit_mode,
                        values.time_limit_min,
                        sort_order,
                        now,
                        now,
                    ),
                )


class BatteryStore(SQLiteStore):
    def __init__(self, path: str | Path) -> None:
        super().__init__(path)
        self._initialize()

    def _initialize(self) -> None:
        with self._connect() as connection:
            _ensure_battery_tables(connection)

    def list(self, *, include_archived: bool = False) -> list[StoredBattery]:
        where = "" if include_archived else "WHERE archived = 0"
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM batteries {where} ORDER BY code COLLATE NOCASE, id"
            ).fetchall()
        return [_battery_from_row(row) for row in rows]

    def get(self, battery_id: int) -> StoredBattery | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM batteries WHERE id = ?",
                (battery_id,),
            ).fetchone()
        return _battery_from_row(row) if row is not None else None

    def get_by_code(self, code: str) -> StoredBattery | None:
        clean = code.strip().upper()
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM batteries WHERE code = ? COLLATE NOCASE",
                (clean,),
            ).fetchone()
        return _battery_from_row(row) if row is not None else None

    def create_numbered(
        self,
        *,
        battery_type_code: int,
        nominal_capacity_mah: int,
    ) -> StoredBattery:
        return self.create_numbered_many(
            [(battery_type_code, nominal_capacity_mah)]
        )[0]

    def create_numbered_many(
        self,
        batteries: Iterable[tuple[int, int]],
    ) -> list[StoredBattery]:
        requested = list(batteries)
        if not requested:
            return []
        now = datetime.now(UTC).isoformat()
        battery_ids = []
        with self._lock, self._connect() as connection:
            numeric_codes = [
                int(row["code"])
                for row in connection.execute(
                    "SELECT code FROM batteries"
                ).fetchall()
                if str(row["code"]).isdigit()
            ]
            next_number = max(numeric_codes, default=0) + 1
            for offset, (battery_type_code, nominal_capacity_mah) in enumerate(
                requested
            ):
                values = validate_battery(
                    BatteryValues(
                        code=str(next_number + offset).zfill(3),
                        name="",
                        battery_type_code=battery_type_code,
                        nominal_capacity_mah=nominal_capacity_mah,
                        notes="",
                    )
                )
                cursor = connection.execute(
                    """
                    INSERT INTO batteries(
                        code, name, battery_type_code, nominal_capacity_mah,
                        notes, manufacturer, model, form_factor, origin,
                        in_service_since, protected,
                        standard_mode_code, standard_charge_c_rate,
                        standard_discharge_c_rate, standard_cycle_count,
                        standard_cycle_mode, standard_time_limit_mode,
                        standard_time_limit_min, archived, archived_at,
                        created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        values.code,
                        values.name,
                        values.battery_type_code,
                        values.nominal_capacity_mah,
                        values.notes,
                        values.manufacturer,
                        values.model,
                        values.form_factor,
                        values.origin,
                        values.in_service_since,
                        int(values.protected),
                        values.standard_mode_code,
                        values.standard_charge_c_rate,
                        values.standard_discharge_c_rate,
                        values.standard_cycle_count,
                        values.standard_cycle_mode,
                        values.standard_time_limit_mode,
                        values.standard_time_limit_min,
                        int(values.archived),
                        now if values.archived else "",
                        now,
                        now,
                    ),
                )
                battery_ids.append(int(cursor.lastrowid))

        stored = [self.get(battery_id) for battery_id in battery_ids]
        if any(battery is None for battery in stored):
            raise RuntimeError("Batterie konnte nicht gespeichert werden")
        return [battery for battery in stored if battery is not None]

    def save(
        self,
        values: BatteryValues,
        *,
        battery_id: int | None = None,
    ) -> StoredBattery:
        clean = validate_battery(values)
        now = datetime.now(UTC).isoformat()
        data = (
            clean.code,
            clean.name,
            clean.battery_type_code,
            clean.nominal_capacity_mah,
            clean.notes,
            clean.manufacturer,
            clean.model,
            clean.form_factor,
            clean.origin,
            clean.in_service_since,
            int(clean.protected),
            clean.standard_mode_code,
            clean.standard_charge_c_rate,
            clean.standard_discharge_c_rate,
            clean.standard_cycle_count,
            clean.standard_cycle_mode,
            clean.standard_time_limit_mode,
            clean.standard_time_limit_min,
            int(clean.archived),
        )
        try:
            with self._lock, self._connect() as connection:
                if battery_id is None:
                    cursor = connection.execute(
                        """
                        INSERT INTO batteries(
                            code, name, battery_type_code, nominal_capacity_mah,
                            notes, manufacturer, model, form_factor, origin,
                            in_service_since, protected,
                            standard_mode_code, standard_charge_c_rate,
                            standard_discharge_c_rate, standard_cycle_count,
                            standard_cycle_mode, standard_time_limit_mode,
                            standard_time_limit_min, archived, archived_at,
                            created_at, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (*data, now if clean.archived else "", now, now),
                    )
                    battery_id = int(cursor.lastrowid)
                else:
                    cursor = connection.execute(
                        """
                        UPDATE batteries
                        SET code = ?, name = ?, battery_type_code = ?,
                            nominal_capacity_mah = ?, notes = ?,
                            manufacturer = ?, model = ?, form_factor = ?,
                            origin = ?, in_service_since = ?, protected = ?,
                            standard_mode_code = ?, standard_charge_c_rate = ?,
                            standard_discharge_c_rate = ?,
                            standard_cycle_count = ?, standard_cycle_mode = ?,
                            standard_time_limit_mode = ?,
                            standard_time_limit_min = ?,
                            archived = ?,
                            archived_at = CASE
                                WHEN ? = 0 THEN ''
                                WHEN archived = 0 OR archived_at = '' THEN ?
                                ELSE archived_at
                            END,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (*data, int(clean.archived), now, now, battery_id),
                    )
                    if cursor.rowcount == 0:
                        raise KeyError(battery_id)
        except sqlite3.IntegrityError as exc:
            raise BatteryError(
                f"Batterienummer {clean.code} ist bereits vorhanden"
            ) from exc

        stored = self.get(battery_id)
        if stored is None:
            raise RuntimeError("Batterie konnte nicht gespeichert werden")
        return stored

    def archive(self, battery_id: int) -> None:
        now = datetime.now(UTC).isoformat()
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE batteries
                SET archived = 1, archived_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, now, battery_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(battery_id)
            connection.execute(
                "DELETE FROM battery_assignments WHERE battery_id = ?",
                (battery_id,),
            )

    def delete_permanently(self, battery_id: int) -> dict[str, int]:
        """Delete an archived battery and all history tied to its record."""

        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT archived FROM batteries WHERE id = ?",
                (battery_id,),
            ).fetchone()
            if row is None:
                raise KeyError(battery_id)
            if not bool(row["archived"]):
                raise BatteryError(
                    "Batterie muss vor dem endgültigen Löschen archiviert werden"
                )

            tables = {
                str(table["name"])
                for table in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            deleted = {
                "measurements": 0,
                "runs": 0,
                "notifications": 0,
            }
            has_runs = "recording_runs" in tables
            if "notifications" in tables:
                if has_runs:
                    cursor = connection.execute(
                        """
                        DELETE FROM notifications
                        WHERE battery_id = ?
                           OR run_id IN (
                               SELECT id FROM recording_runs WHERE battery_id = ?
                           )
                        """,
                        (battery_id, battery_id),
                    )
                else:
                    cursor = connection.execute(
                        "DELETE FROM notifications WHERE battery_id = ?",
                        (battery_id,),
                    )
                deleted["notifications"] = cursor.rowcount
            if "measurements" in tables:
                if has_runs:
                    cursor = connection.execute(
                        """
                        DELETE FROM measurements
                        WHERE battery_id = ?
                           OR run_id IN (
                               SELECT id FROM recording_runs WHERE battery_id = ?
                           )
                        """,
                        (battery_id, battery_id),
                    )
                else:
                    cursor = connection.execute(
                        "DELETE FROM measurements WHERE battery_id = ?",
                        (battery_id,),
                    )
                deleted["measurements"] = cursor.rowcount
            if has_runs:
                cursor = connection.execute(
                    "DELETE FROM recording_runs WHERE battery_id = ?",
                    (battery_id,),
                )
                deleted["runs"] = cursor.rowcount
            if "slot_program_assignments" in tables:
                connection.execute(
                    "DELETE FROM slot_program_assignments WHERE battery_id = ?",
                    (battery_id,),
                )
            connection.execute(
                "DELETE FROM battery_assignments WHERE battery_id = ?",
                (battery_id,),
            )
            connection.execute(
                "DELETE FROM batteries WHERE id = ?",
                (battery_id,),
            )
            return deleted

    def assign(self, address: str, slot: int, battery_id: int) -> None:
        self.assign_many(address, {slot: battery_id})

    def validate_assignments(
        self,
        address: str,
        assignments: dict[int, int],
    ) -> None:
        normalized = normalize_address(address)
        clean = dict(assignments)
        if not clean or any(slot not in range(1, 5) for slot in clean):
            raise ValueError("Slot muss zwischen 1 und 4 liegen")
        if len(set(clean.values())) != len(clean):
            raise BatteryError(
                "Eine Batterienummer kann nicht mehreren Slots zugeordnet werden"
            )
        for battery_id in clean.values():
            battery = self.get(battery_id)
            if battery is None or battery.values.archived:
                raise KeyError(battery_id)

        placeholders = ", ".join("?" for _ in clean)
        target_slots = set(clean)
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT a.address, a.slot, a.battery_id, b.code
                FROM battery_assignments a
                JOIN batteries b ON b.id = a.battery_id
                WHERE a.battery_id IN ({placeholders})
                """,
                tuple(clean.values()),
            ).fetchall()
        for row in rows:
            existing = (
                normalize_address(str(row["address"])),
                int(row["slot"]),
                int(row["battery_id"]),
            )
            if (
                existing[0] == normalized
                and existing[1] in target_slots
            ):
                continue
            raise BatteryError(
                f"Batterie {row['code']} ist bereits einem anderen Slot zugeordnet"
            )

    def assign_many(self, address: str, assignments: dict[int, int]) -> None:
        normalized = normalize_address(address)
        clean = dict(assignments)
        self.validate_assignments(normalized, clean)
        now = datetime.now(UTC).isoformat()
        with self._lock, self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO battery_assignments(address, slot, battery_id, assigned_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(address, slot) DO UPDATE SET
                    battery_id = excluded.battery_id,
                    assigned_at = excluded.assigned_at
                """,
                [
                    (normalized, slot, battery_id, now)
                    for slot, battery_id in clean.items()
                ],
            )

    def assignments_for(self, address: str) -> dict[int, int]:
        normalized = normalize_address(address)
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT slot, battery_id
                FROM battery_assignments
                WHERE address = ?
                """,
                (normalized,),
            ).fetchall()
        return {int(row["slot"]): int(row["battery_id"]) for row in rows}

    def clear_assignments(self, address: str, slots: Iterable[int]) -> None:
        normalized = normalize_address(address)
        clean_slots = sorted(set(slots))
        if any(slot not in range(1, 5) for slot in clean_slots):
            raise ValueError("Slot muss zwischen 1 und 4 liegen")
        if not clean_slots:
            return
        with self._lock, self._connect() as connection:
            connection.executemany(
                "DELETE FROM battery_assignments WHERE address = ? AND slot = ?",
                [(normalized, slot) for slot in clean_slots],
            )


class MeasurementStore(SQLiteStore):
    def __init__(self, path: str | Path) -> None:
        super().__init__(path)
        self._initialize()
        self._close_stale_runs()

    def _initialize(self) -> None:
        with self._connect() as connection:
            _ensure_battery_tables(connection)
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS recording_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    address TEXT NOT NULL,
                    slot INTEGER NOT NULL,
                    profile_id INTEGER,
                    battery_id INTEGER,
                    nominal_capacity_mah INTEGER,
                    battery_type_code INTEGER NOT NULL,
                    mode_code INTEGER NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE SET NULL,
                    FOREIGN KEY(battery_id) REFERENCES batteries(id) ON DELETE SET NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS measurements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recorded_at TEXT NOT NULL,
                    address TEXT NOT NULL,
                    slot INTEGER NOT NULL,
                    run_id INTEGER,
                    profile_id INTEGER,
                    battery_id INTEGER,
                    battery_type_code INTEGER NOT NULL,
                    mode_code INTEGER NOT NULL,
                    status_code INTEGER NOT NULL,
                    active INTEGER NOT NULL,
                    time_s INTEGER NOT NULL,
                    voltage_mv INTEGER NOT NULL,
                    current_ma INTEGER NOT NULL,
                    capacity_mah INTEGER NOT NULL,
                    temperature_c INTEGER NOT NULL,
                    resistance_mohm INTEGER NOT NULL,
                    cycle_count INTEGER NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES recording_runs(id) ON DELETE SET NULL,
                    FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE SET NULL,
                    FOREIGN KEY(battery_id) REFERENCES batteries(id) ON DELETE SET NULL
                )
                """
            )
            _add_column_if_missing(
                connection,
                "recording_runs",
                "battery_id INTEGER REFERENCES batteries(id) ON DELETE SET NULL",
            )
            _add_column_if_missing(
                connection,
                "recording_runs",
                "nominal_capacity_mah INTEGER",
            )
            _add_column_if_missing(
                connection,
                "measurements",
                "battery_id INTEGER REFERENCES batteries(id) ON DELETE SET NULL",
            )
            connection.execute(
                """
                UPDATE recording_runs
                SET nominal_capacity_mah = (
                    SELECT b.nominal_capacity_mah
                    FROM batteries b
                    WHERE b.id = recording_runs.battery_id
                )
                WHERE nominal_capacity_mah IS NULL
                  AND battery_id IS NOT NULL
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS measurements_slot_time
                ON measurements(address, slot, recorded_at)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS measurements_run
                ON measurements(run_id, recorded_at)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS recording_runs_started
                ON recording_runs(started_at DESC)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS measurements_battery_run
                ON measurements(battery_id, run_id, recorded_at)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS recording_runs_battery_started
                ON recording_runs(battery_id, started_at DESC)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    run_id INTEGER,
                    battery_id INTEGER,
                    read_at TEXT,
                    UNIQUE(kind, run_id),
                    FOREIGN KEY(run_id) REFERENCES recording_runs(id) ON DELETE CASCADE,
                    FOREIGN KEY(battery_id) REFERENCES batteries(id) ON DELETE SET NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS notifications_created
                ON notifications(created_at DESC)
                """
            )

    def record_snapshot(
        self,
        address: str,
        recorded_at: str,
        slots: list[dict[str, Any] | None],
        run_ids: list[int | None],
        profile_ids: dict[int, int],
        battery_ids: dict[int, int] | None = None,
    ) -> list[int | None]:
        normalized = normalize_address(address)
        next_run_ids = list(run_ids)
        battery_ids = battery_ids or {}
        with self._lock, self._connect() as connection:
            for index, slot in enumerate(slots):
                if slot is None:
                    continue
                slot_number = index + 1
                run_id = next_run_ids[index]
                profile_id = profile_ids.get(slot_number)
                battery_id = battery_ids.get(slot_number)
                active = bool(slot["active"])
                if active and run_id is None:
                    battery_capacity = None
                    if battery_id is not None:
                        battery_row = connection.execute(
                            "SELECT nominal_capacity_mah FROM batteries WHERE id = ?",
                            (battery_id,),
                        ).fetchone()
                        if battery_row is not None:
                            battery_capacity = battery_row["nominal_capacity_mah"]
                    cursor = connection.execute(
                        """
                        INSERT INTO recording_runs(
                            address, slot, profile_id, battery_id,
                            nominal_capacity_mah,
                            battery_type_code, mode_code, started_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            normalized,
                            slot_number,
                            profile_id,
                            battery_id,
                            battery_capacity,
                            slot["battery_type_code"],
                            slot["mode_code"],
                            recorded_at,
                        ),
                    )
                    run_id = int(cursor.lastrowid)
                    next_run_ids[index] = run_id

                if run_id is not None and battery_id is None:
                    run = connection.execute(
                        "SELECT battery_id FROM recording_runs WHERE id = ?",
                        (run_id,),
                    ).fetchone()
                    if run is not None:
                        battery_id = run["battery_id"]
                measurement_battery_id = (
                    battery_id if active or run_id is not None else None
                )
                values = (
                    recorded_at,
                    normalized,
                    slot_number,
                    run_id,
                    profile_id,
                    measurement_battery_id,
                    slot["battery_type_code"],
                    slot["mode_code"],
                    slot["status_code"],
                    int(active),
                    slot["time_s"],
                    round(float(slot["voltage_v"]) * 1000),
                    round(float(slot["current_a"]) * 1000),
                    slot["capacity_mah"],
                    slot["temperature_c"],
                    slot["resistance_mohm"],
                    slot["cycle_count"],
                )
                connection.execute(
                    f"""
                    INSERT INTO measurements ({", ".join(MEASUREMENT_COLUMNS)})
                    VALUES ({", ".join("?" for _ in MEASUREMENT_COLUMNS)})
                    """,
                    values,
                )

                if not active and run_id is not None:
                    connection.execute(
                        "UPDATE recording_runs SET ended_at = ? WHERE id = ?",
                        (recorded_at, run_id),
                    )
                    run = connection.execute(
                        """
                        SELECT r.battery_id, b.code
                        FROM recording_runs r
                        LEFT JOIN batteries b ON b.id = r.battery_id
                        WHERE r.id = ?
                        """,
                        (run_id,),
                    ).fetchone()
                    battery_label = (
                        f"Batterie {run['code']}"
                        if run is not None and run["code"]
                        else "Batterie ohne Akte"
                    )
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO notifications(
                            created_at, kind, title, message, run_id, battery_id
                        )
                        VALUES (?, 'run_completed', ?, ?, ?, ?)
                        """,
                        (
                            recorded_at,
                            f"Slot {slot_number} ist fertig",
                            f"{battery_label} auf {normalized}, Slot {slot_number}",
                            run_id,
                            run["battery_id"] if run is not None else None,
                        ),
                    )
                    next_run_ids[index] = None
        return next_run_ids

    def history(
        self,
        address: str,
        slot: int,
        since: str,
        until: str,
        *,
        limit: int = 2000,
    ) -> dict[str, Any]:
        normalized = normalize_address(address)
        if slot not in range(1, 5):
            raise ValueError("Slot muss zwischen 1 und 4 liegen")
        limit = max(10, min(limit, 5000))
        where = "address = ? AND slot = ? AND recorded_at BETWEEN ? AND ?"
        parameters = (normalized, slot, since, until)
        with self._lock, self._connect() as connection:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM measurements WHERE {where}",
                    parameters,
                ).fetchone()[0]
            )
            step = max(1, math.ceil(total / limit))
            if step == 1:
                rows = connection.execute(
                    f"""
                    SELECT * FROM measurements
                    WHERE {where}
                    ORDER BY recorded_at, id
                    """,
                    parameters,
                ).fetchall()
            else:
                rows = connection.execute(
                    f"""
                    WITH ranked AS (
                        SELECT *,
                               ROW_NUMBER() OVER (ORDER BY recorded_at, id) AS row_num,
                               COUNT(*) OVER () AS row_count
                        FROM measurements
                        WHERE {where}
                    )
                    SELECT * FROM ranked
                    WHERE row_num = 1
                       OR row_num = row_count
                       OR ((row_num - 1) % ?) = 0
                    ORDER BY recorded_at, id
                    """,
                    (*parameters, step),
                ).fetchall()
        return {
            "address": normalized,
            "slot": slot,
            "since": since,
            "until": until,
            "total_points": total,
            "returned_points": len(rows),
            "sample_step": step,
            "points": [_measurement_to_dict(row) for row in rows],
        }

    def list_runs(
        self,
        *,
        address: str | None = None,
        slot: int | None = None,
        battery_id: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        parameters: list[Any] = []
        if address is not None:
            clauses.append("r.address = ?")
            parameters.append(normalize_address(address))
        if slot is not None:
            if slot not in range(1, 5):
                raise ValueError("Slot muss zwischen 1 und 4 liegen")
            clauses.append("r.slot = ?")
            parameters.append(slot)
        if battery_id is not None:
            clauses.append("r.battery_id = ?")
            parameters.append(battery_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(max(1, min(limit, 500)))
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT r.*,
                       b.code AS battery_code,
                       COALESCE(
                           r.nominal_capacity_mah,
                           b.nominal_capacity_mah
                       ) AS capacity_target_mah,
                       COUNT(m.id) AS sample_count,
                       MAX(m.voltage_mv) AS max_voltage_mv,
                       MAX(m.current_ma) AS max_current_ma,
                       MAX(m.capacity_mah) AS max_capacity_mah,
                       MAX(
                           CASE WHEN m.status_code = 2
                           THEN m.capacity_mah END
                       ) AS discharge_capacity_mah,
                       MAX(m.temperature_c) AS max_temperature_c,
                       MIN(NULLIF(m.resistance_mohm, 0)) AS measured_resistance_mohm
                FROM recording_runs r
                LEFT JOIN measurements m ON m.run_id = r.id
                LEFT JOIN batteries b ON b.id = r.battery_id
                {where}
                GROUP BY r.id
                ORDER BY r.started_at DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return [_run_to_dict(row) for row in rows]

    def run_report(self, run_id: int) -> dict[str, Any]:
        with self._lock, self._connect() as connection:
            run = connection.execute(
                """
                SELECT r.*, b.code AS battery_code, b.name AS battery_name,
                       COALESCE(
                           r.nominal_capacity_mah,
                           b.nominal_capacity_mah
                       ) AS capacity_target_mah,
                       p.name AS profile_name, p.temp_limit_c AS profile_temp_limit_c
                FROM recording_runs r
                LEFT JOIN batteries b ON b.id = r.battery_id
                LEFT JOIN profiles p ON p.id = r.profile_id
                WHERE r.id = ?
                """,
                (run_id,),
            ).fetchone()
            if run is None:
                raise KeyError(run_id)
            rows = connection.execute(
                """
                SELECT *
                FROM measurements
                WHERE run_id = ?
                ORDER BY recorded_at, id
                """,
                (run_id,),
            ).fetchall()
        return _build_run_report(run, rows)

    def run_chart(
        self,
        run_id: int,
        *,
        minutes_before: int = 5,
        minutes_after: int = 60,
        limit: int = 2000,
    ) -> dict[str, Any]:
        if not 0 <= minutes_before <= 24 * 60:
            raise ValueError("Der Vorlauf muss zwischen 0 und 1440 Minuten liegen")
        if not 0 <= minutes_after <= 24 * 60:
            raise ValueError("Der Nachlauf muss zwischen 0 und 1440 Minuten liegen")
        report = self.run_report(run_id)
        if report["ended_at"] is None:
            raise ValueError(
                "Das Diagramm ist erst nach Abschluss des Programmlaufs verfügbar"
            )

        started_at = datetime.fromisoformat(str(report["started_at"]))
        ended_at = datetime.fromisoformat(str(report["ended_at"]))
        since = started_at - timedelta(minutes=minutes_before)
        until = ended_at + timedelta(minutes=minutes_after)
        history = self.history(
            str(report["address"]),
            int(report["slot"]),
            since.isoformat(),
            until.isoformat(),
            limit=limit,
        )
        return {
            "run_id": int(report["id"]),
            "started_at": str(report["started_at"]),
            "ended_at": str(report["ended_at"]),
            "battery_code": report["battery_code"],
            "mode": report["mode"],
            "capacity_target_mah": report["nominal_capacity_mah"],
            "capacity_actual_mah": report["capacity_actual_mah"],
            "capacity_ratio_percent": report["capacity_ratio_percent"],
            "minutes_before": minutes_before,
            "minutes_after": minutes_after,
            **history,
        }

    def delete_run(self, run_id: int) -> dict[str, int]:
        with self._lock, self._connect() as connection:
            run = connection.execute(
                "SELECT ended_at FROM recording_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if run is None:
                raise KeyError(run_id)
            if run["ended_at"] is None:
                raise ValueError("Ein laufender Programmlauf kann nicht gelöscht werden")
            measurement_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM measurements WHERE run_id = ?",
                    (run_id,),
                ).fetchone()[0]
            )
            notification_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM notifications WHERE run_id = ?",
                    (run_id,),
                ).fetchone()[0]
            )
            connection.execute(
                "DELETE FROM measurements WHERE run_id = ?",
                (run_id,),
            )
            connection.execute(
                "DELETE FROM recording_runs WHERE id = ?",
                (run_id,),
            )
        return {
            "measurements": measurement_count,
            "notifications": notification_count,
        }

    def list_notifications(
        self,
        *,
        unread_only: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        where = "WHERE read_at IS NULL" if unread_only else ""
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM notifications
                {where}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (max(1, min(limit, 200)),),
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "created_at": str(row["created_at"]),
                "kind": str(row["kind"]),
                "title": str(row["title"]),
                "message": str(row["message"]),
                "run_id": row["run_id"],
                "battery_id": row["battery_id"],
                "read": row["read_at"] is not None,
                "read_at": row["read_at"],
            }
            for row in rows
        ]

    def mark_notifications_read(self, notification_ids: Iterable[int]) -> int:
        clean_ids = sorted({int(value) for value in notification_ids})
        if not clean_ids:
            return 0
        now = datetime.now(UTC).isoformat()
        placeholders = ", ".join("?" for _ in clean_ids)
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                f"""
                UPDATE notifications
                SET read_at = COALESCE(read_at, ?)
                WHERE id IN ({placeholders})
                """,
                (now, *clean_ids),
            )
            return cursor.rowcount

    def battery_statistics(self, battery_id: int) -> dict[str, Any]:
        runs = self.list_runs(battery_id=battery_id, limit=500)
        completed = [run for run in runs if run["ended_at"] is not None]
        capacity_tests = [
            run
            for run in completed
            if run["mode_code"] == 3
            and run["capacity_actual_mah"] is not None
            and run["capacity_actual_mah"] > 0
        ]
        latest_test = capacity_tests[0] if capacity_tests else None
        soh_percent = latest_test["capacity_soh_percent"] if latest_test else None
        capacity_results = [
            run
            for run in completed
            if run["capacity_ratio_percent"] is not None
        ]
        latest_result = capacity_results[0] if capacity_results else None
        resistance_runs = [
            run for run in reversed(completed) if run["measured_resistance_mohm"]
        ]
        baseline_resistance = (
            resistance_runs[0]["measured_resistance_mohm"]
            if resistance_runs
            else None
        )
        latest_resistance = (
            resistance_runs[-1]["measured_resistance_mohm"]
            if resistance_runs
            else None
        )
        resistance_change = (
            round(
                (latest_resistance - baseline_resistance)
                / baseline_resistance
                * 100,
                1,
            )
            if baseline_resistance and latest_resistance
            else None
        )
        return {
            "run_count": len(runs),
            "completed_run_count": len(completed),
            "capacity_test_count": len(capacity_tests),
            "latest_run_at": runs[0]["started_at"] if runs else None,
            "latest_capacity_mah": (
                latest_test["capacity_actual_mah"] if latest_test else None
            ),
            "best_capacity_mah": (
                max(run["capacity_actual_mah"] for run in capacity_tests)
                if capacity_tests
                else None
            ),
            "soh_percent": soh_percent,
            "soh_basis_run_id": latest_test["id"] if latest_test else None,
            "soh_plausible": soh_percent is None or 0 <= soh_percent <= 130,
            "latest_capacity_result_mah": (
                latest_result["capacity_actual_mah"] if latest_result else None
            ),
            "latest_capacity_target_mah": (
                latest_result["nominal_capacity_mah"] if latest_result else None
            ),
            "latest_capacity_ratio_percent": (
                latest_result["capacity_ratio_percent"] if latest_result else None
            ),
            "latest_capacity_result_run_id": (
                latest_result["id"] if latest_result else None
            ),
            "baseline_resistance_mohm": baseline_resistance,
            "latest_resistance_mohm": latest_resistance,
            "resistance_change_percent": resistance_change,
        }

    def compare_runs(
        self,
        battery_id: int,
        run_ids: Iterable[int],
        *,
        limit: int = 1200,
    ) -> dict[str, Any]:
        clean_ids = list(dict.fromkeys(int(run_id) for run_id in run_ids))
        if not clean_ids or len(clean_ids) > 5:
            raise ValueError("Zwischen einem und fünf Läufen auswählen")
        available = {
            run["id"]: run
            for run in self.list_runs(battery_id=battery_id, limit=500)
        }
        if any(run_id not in available for run_id in clean_ids):
            raise ValueError("Mindestens ein Lauf gehört nicht zu dieser Batterie")
        return {
            "battery_id": battery_id,
            "runs": [
                {
                    **available[run_id],
                    "points": self._run_points(run_id, limit=limit),
                }
                for run_id in clean_ids
            ],
        }

    def _run_points(self, run_id: int, *, limit: int) -> list[dict[str, Any]]:
        limit = max(50, min(limit, 3000))
        with self._lock, self._connect() as connection:
            total = int(
                connection.execute(
                    "SELECT COUNT(*) FROM measurements WHERE run_id = ?",
                    (run_id,),
                ).fetchone()[0]
            )
            step = max(1, math.ceil(total / limit))
            rows = connection.execute(
                """
                WITH ranked AS (
                    SELECT *,
                           ROW_NUMBER() OVER (ORDER BY recorded_at, id) AS row_num,
                           COUNT(*) OVER () AS row_count
                    FROM measurements
                    WHERE run_id = ?
                )
                SELECT * FROM ranked
                WHERE row_num = 1
                   OR row_num = row_count
                   OR ((row_num - 1) % ?) = 0
                ORDER BY recorded_at, id
                """,
                (run_id, step),
            ).fetchall()
        return [_measurement_to_dict(row) for row in rows]

    def iter_csv(
        self,
        address: str,
        slot: int,
        since: str,
        until: str,
    ) -> Iterator[str]:
        normalized = normalize_address(address)
        if slot not in range(1, 5):
            raise ValueError("Slot muss zwischen 1 und 4 liegen")
        connection = self._connect()
        cursor = connection.execute(
            """
            SELECT m.*, b.code AS battery_code
            FROM measurements m
            LEFT JOIN batteries b ON b.id = m.battery_id
            WHERE m.address = ? AND m.slot = ?
              AND m.recorded_at BETWEEN ? AND ?
            ORDER BY m.recorded_at, m.id
            """,
            (normalized, slot, since, until),
        )
        output = io.StringIO()
        writer = csv.writer(output, delimiter=";")
        writer.writerow(
            (
                "Zeitpunkt",
                "Adresse",
                "Slot",
                "Akkutyp",
                "Programm",
                "Status",
                "Aktiv",
                "Laufzeit_s",
                "Spannung_V",
                "Strom_A",
                "Kapazität_mAh",
                "Temperatur_C",
                "Innenwiderstand_mOhm",
                "Zyklus",
                "Batterie",
                "Profil_ID",
                "Aufzeichnung_ID",
            )
        )
        yield "\ufeff" + output.getvalue()
        output.seek(0)
        output.truncate(0)
        try:
            while rows := cursor.fetchmany(1000):
                for row in rows:
                    writer.writerow(_measurement_csv_row(row))
                yield output.getvalue()
                output.seek(0)
                output.truncate(0)
        finally:
            connection.close()

    def iter_battery_csv(self, battery_id: int) -> Iterator[str]:
        connection = self._connect()
        cursor = connection.execute(
            """
            SELECT m.*, b.code AS battery_code
            FROM measurements m
            JOIN batteries b ON b.id = m.battery_id
            WHERE m.battery_id = ?
            ORDER BY m.recorded_at, m.id
            """,
            (battery_id,),
        )
        output = io.StringIO()
        writer = csv.writer(output, delimiter=";")
        writer.writerow(
            (
                "Zeitpunkt",
                "Adresse",
                "Slot",
                "Akkutyp",
                "Programm",
                "Status",
                "Aktiv",
                "Laufzeit_s",
                "Spannung_V",
                "Strom_A",
                "Kapazität_mAh",
                "Temperatur_C",
                "Innenwiderstand_mOhm",
                "Zyklus",
                "Batterie",
                "Profil_ID",
                "Aufzeichnung_ID",
            )
        )
        yield "\ufeff" + output.getvalue()
        output.seek(0)
        output.truncate(0)
        try:
            while rows := cursor.fetchmany(1000):
                for row in rows:
                    writer.writerow(_measurement_csv_row(row))
                yield output.getvalue()
                output.seek(0)
                output.truncate(0)
        finally:
            connection.close()

    def purge_before(
        self,
        cutoff: str,
        *,
        archived_battery_cutoff: str | None = None,
    ) -> int:
        with self._lock, self._connect() as connection:
            generic_cursor = connection.execute(
                """
                DELETE FROM measurements
                WHERE recorded_at < ? AND battery_id IS NULL
                """,
                (cutoff,),
            )
            archived_count = 0
            if archived_battery_cutoff is not None:
                archived_cursor = connection.execute(
                    """
                    DELETE FROM measurements
                    WHERE battery_id IN (
                        SELECT id
                        FROM batteries
                        WHERE archived = 1
                          AND archived_at != ''
                          AND archived_at < ?
                    )
                    """,
                    (archived_battery_cutoff,),
                )
                archived_count = archived_cursor.rowcount
            connection.execute(
                """
                DELETE FROM recording_runs
                WHERE ended_at IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM measurements WHERE run_id = recording_runs.id
                  )
                  AND (
                      (battery_id IS NULL AND ended_at < ?)
                      OR (
                          ? IS NOT NULL
                          AND battery_id IN (
                              SELECT id
                              FROM batteries
                              WHERE archived = 1
                                AND archived_at != ''
                                AND archived_at < ?
                          )
                      )
                  )
                """,
                (
                    cutoff,
                    archived_battery_cutoff,
                    archived_battery_cutoff,
                ),
            )
            return generic_cursor.rowcount + archived_count

    def _close_stale_runs(self) -> None:
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute(
                "UPDATE recording_runs SET ended_at = ? WHERE ended_at IS NULL",
                (now,),
            )


def _profile_from_row(row: sqlite3.Row) -> StoredProfile:
    values = ProfileValues.from_mapping(row)
    return StoredProfile(
        id=int(row["id"]),
        values=values,
        is_builtin=bool(row["is_builtin"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        category_key=str(row["category_key"]),
    )


def _automatic_profile_from_row(row: sqlite3.Row) -> StoredAutomaticProfile:
    return StoredAutomaticProfile(
        key=str(row["key"]),
        values=AutomaticProgramValues(
            label=str(row["label"]),
            description=str(row["description"]),
            mode_code=int(row["mode_code"]),
            charge_c_rate=float(row["charge_c_rate"]),
            discharge_c_rate=float(row["discharge_c_rate"]),
            cycle_count=int(row["cycle_count"]),
            cycle_mode=int(row["cycle_mode"]),
            charge_rest_min=int(row["charge_rest_min"]),
            discharge_rest_min=int(row["discharge_rest_min"]),
            temp_limit_c=int(row["temp_limit_c"]),
            time_limit_mode=str(row["time_limit_mode"]),
            time_limit_min=int(row["time_limit_min"]),
        ),
        is_builtin=bool(row["is_builtin"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        category_key=str(row["category_key"]),
    )


def _battery_from_row(row: sqlite3.Row) -> StoredBattery:
    return StoredBattery(
        id=int(row["id"]),
        values=BatteryValues(
            code=str(row["code"]),
            name=str(row["name"]),
            battery_type_code=int(row["battery_type_code"]),
            nominal_capacity_mah=int(row["nominal_capacity_mah"]),
            notes=str(row["notes"]),
            manufacturer=str(row["manufacturer"]),
            model=str(row["model"]),
            form_factor=str(row["form_factor"]),
            origin=str(row["origin"]),
            in_service_since=str(row["in_service_since"]),
            protected=bool(row["protected"]),
            standard_mode_code=int(row["standard_mode_code"]),
            standard_charge_c_rate=float(row["standard_charge_c_rate"]),
            standard_discharge_c_rate=float(row["standard_discharge_c_rate"]),
            standard_cycle_count=int(row["standard_cycle_count"]),
            standard_cycle_mode=int(row["standard_cycle_mode"]),
            standard_time_limit_mode=str(row["standard_time_limit_mode"]),
            standard_time_limit_min=int(row["standard_time_limit_min"]),
            archived=bool(row["archived"]),
        ),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        archived_at=str(row["archived_at"]),
    )


def _measurement_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "recorded_at": row["recorded_at"],
        "run_id": row["run_id"],
        "profile_id": row["profile_id"],
        "battery_id": row["battery_id"],
        "battery_type_code": row["battery_type_code"],
        "mode_code": row["mode_code"],
        "status_code": row["status_code"],
        "active": bool(row["active"]),
        "time_s": row["time_s"],
        "voltage_v": round(row["voltage_mv"] / 1000, 3),
        "current_a": _display_current_a(
            row["current_ma"],
            row["status_code"],
        ),
        "capacity_mah": row["capacity_mah"],
        "temperature_c": row["temperature_c"],
        "resistance_mohm": row["resistance_mohm"],
        "cycle_count": row["cycle_count"],
    }


def _measurement_csv_row(row: sqlite3.Row) -> tuple[Any, ...]:
    battery_type_code = int(row["battery_type_code"])
    mode_code = int(row["mode_code"])
    status_code = int(row["status_code"])
    return (
        row["recorded_at"],
        row["address"],
        row["slot"],
        BATTERY_TYPES.get(battery_type_code, battery_type_code),
        mode_name(mode_code, battery_type_code),
        STATUS_NAMES.get(status_code, status_code),
        "ja" if row["active"] else "nein",
        row["time_s"],
        f"{row['voltage_mv'] / 1000:.3f}",
        f"{_display_current_a(row['current_ma'], status_code):.3f}",
        row["capacity_mah"],
        row["temperature_c"],
        row["resistance_mohm"],
        row["cycle_count"],
        row["battery_code"] or "",
        row["profile_id"] or "",
        row["run_id"] or "",
    )


def _display_current_a(current_ma: int, status_code: int) -> float:
    current_a = round(abs(int(current_ma)) / 1000, 3)
    return -current_a if int(status_code) == 2 and current_a else current_a


def _run_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    battery_type_code = int(row["battery_type_code"])
    mode_code = int(row["mode_code"])
    nominal_capacity = row["capacity_target_mah"]
    max_capacity = row["max_capacity_mah"]
    discharge_capacity = row["discharge_capacity_mah"]
    capacity_actual = (
        max_capacity
        if row["ended_at"] is not None and mode_code == 3 and max_capacity
        else discharge_capacity
        if row["ended_at"] is not None and discharge_capacity
        else None
    )
    capacity_ratio = (
        round(capacity_actual / nominal_capacity * 100, 1)
        if nominal_capacity and capacity_actual
        else None
    )
    capacity_soh = capacity_ratio if mode_code == 3 else None
    return {
        "id": row["id"],
        "address": row["address"],
        "slot": row["slot"],
        "profile_id": row["profile_id"],
        "battery_id": row["battery_id"],
        "battery_code": row["battery_code"],
        "nominal_capacity_mah": nominal_capacity,
        "battery_type_code": battery_type_code,
        "battery_type": BATTERY_TYPES.get(battery_type_code, str(battery_type_code)),
        "mode_code": mode_code,
        "mode": mode_name(mode_code, battery_type_code),
        "started_at": row["started_at"],
        "ended_at": row["ended_at"],
        "sample_count": row["sample_count"],
        "max_voltage_v": (
            round(row["max_voltage_mv"] / 1000, 3)
            if row["max_voltage_mv"] is not None
            else None
        ),
        "max_current_a": (
            round(row["max_current_ma"] / 1000, 3)
            if row["max_current_ma"] is not None
            else None
        ),
        "max_capacity_mah": max_capacity,
        "capacity_actual_mah": capacity_actual,
        "capacity_ratio_percent": capacity_ratio,
        "max_temperature_c": row["max_temperature_c"],
        "measured_resistance_mohm": row["measured_resistance_mohm"],
        "capacity_soh_percent": capacity_soh,
    }


def _build_run_report(
    run: sqlite3.Row,
    measurements: list[sqlite3.Row],
) -> dict[str, Any]:
    battery_type_code = int(run["battery_type_code"])
    mode_code = int(run["mode_code"])
    started_at = str(run["started_at"])
    ended_at = str(run["ended_at"]) if run["ended_at"] else None
    first = measurements[0] if measurements else None
    last = measurements[-1] if measurements else None
    effective_end = ended_at or (str(last["recorded_at"]) if last else started_at)
    duration_s = max(
        0,
        round(
            (
                datetime.fromisoformat(effective_end)
                - datetime.fromisoformat(started_at)
            ).total_seconds()
        ),
    )

    capacities = [int(row["capacity_mah"]) for row in measurements]
    discharge_capacities = [
        int(row["capacity_mah"])
        for row in measurements
        if int(row["status_code"]) == 2
    ]
    temperatures = [int(row["temperature_c"]) for row in measurements]
    voltages = [int(row["voltage_mv"]) for row in measurements]
    currents = [int(row["current_ma"]) for row in measurements]
    resistances = [
        int(row["resistance_mohm"])
        for row in measurements
        if int(row["resistance_mohm"]) > 0
    ]
    energy_wh = 0.0
    for previous, current in zip(measurements, measurements[1:], strict=False):
        time_delta = (
            datetime.fromisoformat(str(current["recorded_at"]))
            - datetime.fromisoformat(str(previous["recorded_at"]))
        ).total_seconds()
        if not 0 < time_delta <= 300:
            continue
        previous_power = (
            abs(int(previous["voltage_mv"]) * int(previous["current_ma"])) / 1_000_000
        )
        current_power = (
            abs(int(current["voltage_mv"]) * int(current["current_ma"])) / 1_000_000
        )
        energy_wh += ((previous_power + current_power) / 2) * time_delta / 3600

    capacity_mah = max(capacities, default=0)
    nominal_capacity = run["capacity_target_mah"]
    capacity_actual = (
        capacity_mah
        if ended_at and mode_code == 3 and capacity_mah > 0
        else max(discharge_capacities)
        if ended_at and discharge_capacities
        else None
    )
    capacity_ratio = (
        round(capacity_actual / int(nominal_capacity) * 100, 1)
        if ended_at
        and nominal_capacity
        and capacity_actual
        else None
    )
    soh_percent = capacity_ratio if mode_code == 3 else None
    temperature_limit = int(run["profile_temp_limit_c"] or 45)
    max_temperature = max(temperatures, default=None)
    warnings: list[dict[str, str]] = []
    if not ended_at:
        warnings.append(
            {"level": "info", "text": "Programm ist noch nicht abgeschlossen"}
        )
    if len(measurements) < 2:
        warnings.append(
            {"level": "warning", "text": "Zu wenige Messpunkte für eine Auswertung"}
        )
    if max_temperature is not None and max_temperature >= temperature_limit:
        warnings.append(
            {
                "level": "danger",
                "text": (
                    f"Temperaturgrenze erreicht: {max_temperature} °C "
                    f"bei Grenzwert {temperature_limit} °C"
                ),
            }
        )
    if soh_percent is not None and soh_percent < 70:
        warnings.append(
            {
                "level": "danger",
                "text": f"Kapazität liegt nur noch bei {soh_percent:.1f} % SOH",
            }
        )
    elif soh_percent is not None and soh_percent < 80:
        warnings.append(
            {
                "level": "warning",
                "text": f"Kapazität liegt bei {soh_percent:.1f} % SOH",
            }
        )
    last_status_code = int(last["status_code"]) if last else None
    if last_status_code is not None and last_status_code >= 128:
        warnings.append(
            {
                "level": "danger",
                "text": (
                    "Ladegerät meldete "
                    f"{STATUS_NAMES.get(last_status_code, last_status_code)}"
                ),
            }
        )

    rating = "ok"
    if any(item["level"] == "danger" for item in warnings):
        rating = "danger"
    elif any(item["level"] == "warning" for item in warnings):
        rating = "warning"
    elif not ended_at:
        rating = "active"
    return {
        "id": int(run["id"]),
        "address": str(run["address"]),
        "slot": int(run["slot"]),
        "profile_id": run["profile_id"],
        "profile_name": run["profile_name"],
        "battery_id": run["battery_id"],
        "battery_code": run["battery_code"],
        "battery_name": run["battery_name"],
        "battery_type_code": battery_type_code,
        "battery_type": BATTERY_TYPES.get(battery_type_code, str(battery_type_code)),
        "mode_code": mode_code,
        "mode": mode_name(mode_code, battery_type_code),
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_s": duration_s,
        "sample_count": len(measurements),
        "capacity_mah": capacity_mah,
        "capacity_actual_mah": capacity_actual,
        "capacity_ratio_percent": capacity_ratio,
        "nominal_capacity_mah": nominal_capacity,
        "soh_percent": soh_percent,
        "energy_wh": round(energy_wh, 3),
        "start_voltage_v": (
            round(int(first["voltage_mv"]) / 1000, 3) if first else None
        ),
        "end_voltage_v": (
            round(int(last["voltage_mv"]) / 1000, 3) if last else None
        ),
        "minimum_voltage_v": (
            round(min(voltages) / 1000, 3) if voltages else None
        ),
        "maximum_voltage_v": (
            round(max(voltages) / 1000, 3) if voltages else None
        ),
        "maximum_current_a": (
            round(max(map(abs, currents)) / 1000, 3) if currents else None
        ),
        "maximum_temperature_c": max_temperature,
        "temperature_limit_c": temperature_limit,
        "start_resistance_mohm": resistances[0] if resistances else None,
        "end_resistance_mohm": resistances[-1] if resistances else None,
        "minimum_resistance_mohm": min(resistances) if resistances else None,
        "last_status": (
            STATUS_NAMES.get(last_status_code, str(last_status_code))
            if last_status_code is not None
            else None
        ),
        "rating": rating,
        "warnings": warnings,
    }


def _ensure_battery_tables(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS batteries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL COLLATE NOCASE UNIQUE,
            name TEXT NOT NULL DEFAULT '',
            battery_type_code INTEGER NOT NULL,
            nominal_capacity_mah INTEGER NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            manufacturer TEXT NOT NULL DEFAULT '',
            model TEXT NOT NULL DEFAULT '',
            form_factor TEXT NOT NULL DEFAULT '',
            origin TEXT NOT NULL DEFAULT '',
            in_service_since TEXT NOT NULL DEFAULT '',
            protected INTEGER NOT NULL DEFAULT 0,
            standard_mode_code INTEGER NOT NULL DEFAULT 0,
            standard_charge_c_rate REAL NOT NULL DEFAULT 0.5,
            standard_discharge_c_rate REAL NOT NULL DEFAULT 0.5,
            standard_cycle_count INTEGER NOT NULL DEFAULT 1,
            standard_cycle_mode INTEGER NOT NULL DEFAULT 0,
            standard_time_limit_mode TEXT NOT NULL DEFAULT 'manual',
            standard_time_limit_min INTEGER NOT NULL DEFAULT 360,
            archived INTEGER NOT NULL DEFAULT 0,
            archived_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    _add_column_if_missing(
        connection,
        "batteries",
        "manufacturer TEXT NOT NULL DEFAULT ''",
    )
    _add_column_if_missing(
        connection,
        "batteries",
        "model TEXT NOT NULL DEFAULT ''",
    )
    _add_column_if_missing(
        connection,
        "batteries",
        "form_factor TEXT NOT NULL DEFAULT ''",
    )
    _add_column_if_missing(
        connection,
        "batteries",
        "origin TEXT NOT NULL DEFAULT ''",
    )
    _add_column_if_missing(
        connection,
        "batteries",
        "in_service_since TEXT NOT NULL DEFAULT ''",
    )
    _add_column_if_missing(
        connection,
        "batteries",
        "protected INTEGER NOT NULL DEFAULT 0",
    )
    _add_column_if_missing(
        connection,
        "batteries",
        "standard_mode_code INTEGER NOT NULL DEFAULT 0",
    )
    _add_column_if_missing(
        connection,
        "batteries",
        "standard_charge_c_rate REAL NOT NULL DEFAULT 0.5",
    )
    _add_column_if_missing(
        connection,
        "batteries",
        "standard_discharge_c_rate REAL NOT NULL DEFAULT 0.5",
    )
    _add_column_if_missing(
        connection,
        "batteries",
        "standard_cycle_count INTEGER NOT NULL DEFAULT 1",
    )
    _add_column_if_missing(
        connection,
        "batteries",
        "standard_cycle_mode INTEGER NOT NULL DEFAULT 0",
    )
    _add_column_if_missing(
        connection,
        "batteries",
        "standard_time_limit_mode TEXT NOT NULL DEFAULT 'manual'",
    )
    _add_column_if_missing(
        connection,
        "batteries",
        "standard_time_limit_min INTEGER NOT NULL DEFAULT 360",
    )
    _add_column_if_missing(
        connection,
        "batteries",
        "archived_at TEXT NOT NULL DEFAULT ''",
    )
    connection.execute(
        """
        UPDATE batteries
        SET archived_at = updated_at
        WHERE archived = 1 AND archived_at = ''
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS battery_assignments (
            address TEXT NOT NULL,
            slot INTEGER NOT NULL,
            battery_id INTEGER NOT NULL,
            assigned_at TEXT NOT NULL,
            PRIMARY KEY(address, slot),
            FOREIGN KEY(battery_id) REFERENCES batteries(id) ON DELETE CASCADE
        )
        """
    )


def _add_column_if_missing(
    connection: sqlite3.Connection,
    table: str,
    definition: str,
) -> None:
    name = definition.split(maxsplit=1)[0]
    columns = {
        str(row["name"])
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if name not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def _default_profiles() -> tuple[ProfileValues, ...]:
    common = {
        "description": "Beispielprofil. Werte vor dem Anwenden an den Akku anpassen.",
        "mode_code": 0,
        "capacity_mah": 2000,
        "charge_current_ma": 1000,
        "discharge_current_ma": 500,
        "charge_end_current_ma": 100,
        "discharge_end_current_ma": 500,
        "charge_rest_min": 0,
        "discharge_rest_min": 0,
        "cycle_count": 1,
        "cycle_mode": 0,
        "delta_peak_mv": 0,
        "trickle_current_ma": 0,
        "temp_limit_c": 45,
        "time_limit_min": DEFAULT_MANUAL_TIME_LIMIT_MIN,
        "time_limit_mode": "manual",
    }
    return (
        ProfileValues(
            **common,
            name="Li-Ion 4,20 V / 1 A",
            battery_type_code=0,
            charge_voltage_mv=4200,
            discharge_voltage_mv=3000,
            keep_voltage_mv=4150,
        ),
        ProfileValues(
            **common,
            name="LiFePO4 3,60 V / 1 A",
            battery_type_code=1,
            charge_voltage_mv=3600,
            discharge_voltage_mv=2900,
            keep_voltage_mv=3550,
        ),
        ProfileValues(
            **{
                **common,
                "delta_peak_mv": 3,
                "trickle_current_ma": 100,
                "charge_end_current_ma": 1000,
            },
            name="NiMH Delta-Peak / 1 A",
            battery_type_code=3,
            charge_voltage_mv=1650,
            discharge_voltage_mv=1000,
            keep_voltage_mv=1350,
        ),
        ProfileValues(
            **{
                **common,
                "mode_code": 3,
                "discharge_current_ma": 1000,
                "discharge_end_current_ma": 1000,
            },
            name="Li-Ion Kapazitätstest / 1 A",
            battery_type_code=0,
            charge_voltage_mv=4200,
            discharge_voltage_mv=3000,
            keep_voltage_mv=4150,
        ),
        ProfileValues(
            **{
                **common,
                "mode_code": 3,
                "discharge_current_ma": 1000,
                "discharge_end_current_ma": 1000,
            },
            name="LiFePO4 Kapazitätstest / 1 A",
            battery_type_code=1,
            charge_voltage_mv=3600,
            discharge_voltage_mv=2900,
            keep_voltage_mv=3550,
        ),
        ProfileValues(
            **{
                **common,
                "mode_code": 1,
                "charge_current_ma": 500,
                "discharge_current_ma": 1000,
                "charge_end_current_ma": 50,
                "discharge_end_current_ma": 1000,
                "charge_rest_min": 5,
                "discharge_rest_min": 5,
                "time_limit_min": DEFAULT_MANUAL_TIME_LIMIT_MIN,
            },
            name="Li-Ion Refresh / 0,5 A / 1 A",
            battery_type_code=0,
            charge_voltage_mv=4200,
            discharge_voltage_mv=3000,
            keep_voltage_mv=4150,
        ),
        ProfileValues(
            **{
                **common,
                "mode_code": 1,
                "discharge_current_ma": 1000,
                "charge_end_current_ma": 1000,
                "discharge_end_current_ma": 1000,
                "charge_rest_min": 5,
                "discharge_rest_min": 5,
                "delta_peak_mv": 3,
                "trickle_current_ma": 100,
                "time_limit_min": DEFAULT_MANUAL_TIME_LIMIT_MIN,
            },
            name="NiMH Refresh / 1 A",
            battery_type_code=3,
            charge_voltage_mv=1650,
            discharge_voltage_mv=1000,
            keep_voltage_mv=1350,
        ),
    )
