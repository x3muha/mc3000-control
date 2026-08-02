import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from mc3000_control.battery_manager import BatteryError, BatteryValues
from mc3000_control.storage import BatteryStore, MeasurementStore, ProfileStore

ADDRESS = "AA:BB:CC:DD:EE:FF"


def slot(
    *,
    active: bool = False,
    time_s: int = 0,
    mode_code: int = 0,
    capacity_mah: int = 123,
    resistance_mohm: int = 42,
    status_code: int | None = None,
) -> dict:
    effective_status = (
        status_code
        if status_code is not None
        else 2
        if active and mode_code == 3
        else 1
        if active
        else 0
    )
    return {
        "battery_type_code": 0,
        "mode_code": mode_code,
        "cycle_count": 0,
        "status_code": effective_status,
        "active": active,
        "time_s": time_s,
        "voltage_v": 4.123,
        "current_a": 1.0 if active else 0.0,
        "capacity_mah": capacity_mah,
        "temperature_c": 27,
        "resistance_mohm": resistance_mohm,
    }


def test_discharge_current_is_negative_in_history_and_csv(tmp_path) -> None:
    database = tmp_path / "mc3000.db"
    ProfileStore(database)
    store = MeasurementStore(database)
    recorded_at = datetime.now(UTC)
    discharge = {
        **slot(active=True, mode_code=3),
        "status_code": 2,
        "current_a": 1.25,
    }
    store.record_snapshot(
        ADDRESS,
        recorded_at.isoformat(),
        [discharge, None, None, None],
        [None, None, None, None],
        {},
        {},
    )

    history = store.history(
        ADDRESS,
        1,
        (recorded_at - timedelta(seconds=1)).isoformat(),
        (recorded_at + timedelta(seconds=1)).isoformat(),
    )
    csv_text = "".join(
        store.iter_csv(
            ADDRESS,
            1,
            (recorded_at - timedelta(seconds=1)).isoformat(),
            (recorded_at + timedelta(seconds=1)).isoformat(),
        )
    )

    assert history["points"][0]["current_a"] == -1.25
    assert ";-1.250;" in csv_text


def test_profile_store_seeds_and_updates_profiles(tmp_path) -> None:
    store = ProfileStore(tmp_path / "mc3000.db")
    profiles = store.list()

    assert len(profiles) == 7
    assert {profile.values.name for profile in profiles} >= {
        "Li-Ion 4,20 V / 1 A",
        "LiFePO4 Kapazitätstest / 1 A",
        "NiMH Refresh / 1 A",
    }
    assert {profile.values.time_limit_mode for profile in profiles} == {"manual"}
    assert {profile.values.time_limit_min for profile in profiles} == {360}
    assert all(profile.is_builtin for profile in profiles)
    updated_values = replace(profiles[0].values, name="Eigenes Profil")
    updated = store.save(updated_values, profile_id=profiles[0].id)
    created = store.save(replace(profiles[1].values, name="Meine Kopie"))

    assert updated.values.name == "Eigenes Profil"
    assert updated.is_builtin is True
    assert created.is_builtin is False


def test_existing_profiles_get_time_limit_mode_and_six_hour_defaults(tmp_path) -> None:
    path = tmp_path / "mc3000.db"
    ProfileStore(path)
    with sqlite3.connect(path) as connection:
        connection.execute("ALTER TABLE profiles DROP COLUMN time_limit_mode")
        connection.execute("ALTER TABLE profiles DROP COLUMN is_builtin")
        connection.execute(
            """
            UPDATE profiles
            SET time_limit_min = 240
            WHERE name = 'Li-Ion 4,20 V / 1 A'
            """
        )
        connection.execute(
            """
            UPDATE app_metadata
            SET value = '2'
            WHERE key = 'default_profiles_version'
            """
        )

    migrated = ProfileStore(path)
    profile = next(
        item
        for item in migrated.list()
        if item.values.name == "Li-Ion 4,20 V / 1 A"
    )

    assert profile.values.time_limit_mode == "manual"
    assert profile.values.time_limit_min == 360
    assert profile.is_builtin is True


def test_app_setting_defaults_empty_and_persists(tmp_path) -> None:
    path = tmp_path / "mc3000.db"
    store = ProfileStore(path)

    assert store.get_app_setting("default_program") == ""
    store.set_app_setting("default_program", "automatic:gentle_charge")

    assert ProfileStore(path).get_app_setting("default_program") == (
        "automatic:gentle_charge"
    )


def test_automatic_profiles_are_editable_and_duplicable(tmp_path) -> None:
    path = tmp_path / "mc3000.db"
    store = ProfileStore(path)
    automatic_profiles = store.list_automatic()

    assert len(automatic_profiles) == 5
    assert all(profile.is_builtin for profile in automatic_profiles)
    gentle = store.get_automatic("gentle_charge")
    assert gentle is not None

    updated = store.save_automatic(
        replace(
            gentle.values,
            label="Sehr schonend laden",
            charge_c_rate=0.25,
            time_limit_mode="automatic",
        ),
        program_key=gentle.key,
    )
    duplicated = store.save_automatic(
        replace(updated.values, label="Sehr schonend laden (Kopie)")
    )

    reopened = ProfileStore(path)
    persisted = reopened.get_automatic("gentle_charge")
    assert persisted is not None
    assert persisted.values.label == "Sehr schonend laden"
    assert persisted.values.charge_c_rate == 0.25
    assert persisted.values.time_limit_mode == "automatic"
    assert persisted.is_builtin is True
    assert duplicated.key.startswith("own_")
    assert duplicated.is_builtin is False


def test_measurements_create_and_close_an_automatic_run(tmp_path) -> None:
    path = tmp_path / "mc3000.db"
    profiles = ProfileStore(path)
    measurements = MeasurementStore(path)
    profile_id = profiles.list()[0].id
    profiles.assign(ADDRESS, [1], profile_id)
    now = datetime.now(UTC)

    run_ids = measurements.record_snapshot(
        ADDRESS,
        now.isoformat(),
        [slot(active=True), None, None, None],
        [None, None, None, None],
        {1: profile_id},
    )
    assert run_ids[0] is not None

    run_ids = measurements.record_snapshot(
        ADDRESS,
        (now + timedelta(seconds=2)).isoformat(),
        [slot(active=False, time_s=2), None, None, None],
        run_ids,
        {1: profile_id},
    )
    assert run_ids[0] is None

    runs = measurements.list_runs(address=ADDRESS, slot=1)
    assert len(runs) == 1
    assert runs[0]["ended_at"] is not None
    assert runs[0]["sample_count"] == 2


def test_history_and_csv_include_all_measurements(tmp_path) -> None:
    path = tmp_path / "mc3000.db"
    ProfileStore(path)
    measurements = MeasurementStore(path)
    now = datetime.now(UTC)
    run_ids = [None, None, None, None]
    for index in range(25):
        run_ids = measurements.record_snapshot(
            ADDRESS,
            (now + timedelta(seconds=index)).isoformat(),
            [slot(active=False, time_s=index), None, None, None],
            run_ids,
            {},
        )

    history = measurements.history(
        ADDRESS,
        1,
        (now - timedelta(seconds=1)).isoformat(),
        (now + timedelta(seconds=30)).isoformat(),
        limit=10,
    )
    exported = "".join(
        measurements.iter_csv(
            ADDRESS,
            1,
            (now - timedelta(seconds=1)).isoformat(),
            (now + timedelta(seconds=30)).isoformat(),
        )
    )

    assert history["total_points"] == 25
    assert history["returned_points"] <= 11
    assert history["points"][0]["resistance_mohm"] == 42
    assert exported.count("\n") == 26
    assert "Innenwiderstand_mOhm" in exported
    assert ";" in exported.splitlines()[0]


def test_battery_runs_calculate_soh_and_compare_curves(tmp_path) -> None:
    path = tmp_path / "mc3000.db"
    ProfileStore(path)
    batteries = BatteryStore(path)
    measurements = MeasurementStore(path)
    stored = batteries.save(
        BatteryValues(
            code="001",
            name="Testakku",
            battery_type_code=0,
            nominal_capacity_mah=2000,
            notes="",
        )
    )
    batteries.assign(ADDRESS, 1, stored.id)
    now = datetime.now(UTC)

    run_ids = measurements.record_snapshot(
        ADDRESS,
        now.isoformat(),
        [slot(active=True, mode_code=3, capacity_mah=100), None, None, None],
        [None, None, None, None],
        {},
        {1: stored.id},
    )
    run_ids = measurements.record_snapshot(
        ADDRESS,
        (now + timedelta(minutes=30)).isoformat(),
        [
            slot(
                active=True,
                time_s=1800,
                mode_code=3,
                capacity_mah=1800,
                resistance_mohm=55,
            ),
            None,
            None,
            None,
        ],
        run_ids,
        {},
        {1: stored.id},
    )
    measurements.record_snapshot(
        ADDRESS,
        (now + timedelta(minutes=31)).isoformat(),
        [
            slot(
                active=False,
                time_s=1860,
                mode_code=3,
                capacity_mah=1800,
                resistance_mohm=55,
            ),
            None,
            None,
            None,
        ],
        run_ids,
        {},
        {1: stored.id},
    )

    statistics = measurements.battery_statistics(stored.id)
    runs = measurements.list_runs(battery_id=stored.id)
    comparison = measurements.compare_runs(stored.id, [runs[0]["id"]])
    exported = "".join(measurements.iter_battery_csv(stored.id))

    assert statistics["soh_percent"] == 90.0
    assert statistics["latest_capacity_mah"] == 1800
    assert runs[0]["battery_code"] == "001"
    assert runs[0]["capacity_soh_percent"] == 90.0
    assert runs[0]["capacity_ratio_percent"] == 90.0
    assert runs[0]["capacity_actual_mah"] == 1800
    assert len(comparison["runs"][0]["points"]) == 3
    assert ";001;" in exported


def test_completed_run_creates_report_and_notification(tmp_path) -> None:
    path = tmp_path / "mc3000.db"
    ProfileStore(path)
    batteries = BatteryStore(path)
    measurements = MeasurementStore(path)
    stored = batteries.save(
        BatteryValues(
            code="REPORT-1",
            name="Bericht",
            battery_type_code=0,
            nominal_capacity_mah=2000,
            notes="",
        )
    )
    now = datetime.now(UTC)
    run_ids = measurements.record_snapshot(
        ADDRESS,
        now.isoformat(),
        [slot(active=True, mode_code=3, capacity_mah=100), None, None, None],
        [None, None, None, None],
        {},
        {1: stored.id},
    )
    measurements.record_snapshot(
        ADDRESS,
        (now + timedelta(seconds=2)).isoformat(),
        [
            slot(
                active=False,
                time_s=2,
                mode_code=3,
                capacity_mah=1700,
                resistance_mohm=51,
            ),
            None,
            None,
            None,
        ],
        run_ids,
        {},
        {1: stored.id},
    )

    run = measurements.list_runs(battery_id=stored.id)[0]
    report = measurements.run_report(run["id"])
    notifications = measurements.list_notifications(unread_only=True)

    assert report["soh_percent"] == 85.0
    assert report["capacity_ratio_percent"] == 85.0
    assert report["capacity_actual_mah"] == 1700
    assert report["duration_s"] == 2
    assert report["energy_wh"] > 0
    assert report["battery_code"] == "REPORT-1"
    assert notifications[0]["run_id"] == run["id"]
    assert notifications[0]["read"] is False
    assert measurements.mark_notifications_read([notifications[0]["id"]]) == 1
    assert measurements.list_notifications(unread_only=True) == []


def test_refresh_capacity_ratio_uses_discharge_phase_and_saved_target(
    tmp_path,
) -> None:
    path = tmp_path / "mc3000.db"
    ProfileStore(path)
    batteries = BatteryStore(path)
    measurements = MeasurementStore(path)
    stored = batteries.save(
        BatteryValues(
            code="RATIO-1",
            name="",
            battery_type_code=0,
            nominal_capacity_mah=2600,
            notes="",
        )
    )
    now = datetime.now(UTC)
    run_ids = measurements.record_snapshot(
        ADDRESS,
        now.isoformat(),
        [
            slot(
                active=True,
                mode_code=1,
                status_code=1,
                capacity_mah=100,
            ),
            None,
            None,
            None,
        ],
        [None, None, None, None],
        {},
        {1: stored.id},
    )
    run_ids = measurements.record_snapshot(
        ADDRESS,
        (now + timedelta(hours=2)).isoformat(),
        [
            slot(
                active=True,
                mode_code=1,
                status_code=2,
                capacity_mah=1600,
            ),
            None,
            None,
            None,
        ],
        run_ids,
        {},
        {1: stored.id},
    )
    measurements.record_snapshot(
        ADDRESS,
        (now + timedelta(hours=4)).isoformat(),
        [
            slot(
                active=False,
                mode_code=1,
                status_code=4,
                capacity_mah=1700,
            ),
            None,
            None,
            None,
        ],
        run_ids,
        {},
        {1: stored.id},
    )
    batteries.save(
        replace(stored.values, nominal_capacity_mah=3000),
        battery_id=stored.id,
    )

    run = measurements.list_runs(battery_id=stored.id)[0]
    report = measurements.run_report(run["id"])
    chart = measurements.run_chart(run["id"])
    statistics = measurements.battery_statistics(stored.id)

    assert run["nominal_capacity_mah"] == 2600
    assert run["max_capacity_mah"] == 1700
    assert run["capacity_actual_mah"] == 1600
    assert run["capacity_ratio_percent"] == 61.5
    assert run["capacity_soh_percent"] is None
    assert report["nominal_capacity_mah"] == 2600
    assert report["capacity_actual_mah"] == 1600
    assert report["capacity_ratio_percent"] == 61.5
    assert report["soh_percent"] is None
    assert chart["capacity_target_mah"] == 2600
    assert chart["capacity_actual_mah"] == 1600
    assert chart["capacity_ratio_percent"] == 61.5
    assert statistics["latest_capacity_result_mah"] == 1600
    assert statistics["latest_capacity_target_mah"] == 2600
    assert statistics["latest_capacity_ratio_percent"] == 61.5


def test_completed_run_chart_window_and_delete_remove_report_data(tmp_path) -> None:
    path = tmp_path / "mc3000.db"
    ProfileStore(path)
    measurements = MeasurementStore(path)
    ended_at = datetime(2026, 7, 30, 10, 0, tzinfo=UTC)
    started_at = ended_at - timedelta(hours=2)

    measurements.record_snapshot(
        ADDRESS,
        (started_at - timedelta(minutes=9)).isoformat(),
        [slot(active=False), None, None, None],
        [None, None, None, None],
        {},
    )
    run_ids = measurements.record_snapshot(
        ADDRESS,
        started_at.isoformat(),
        [slot(active=True), None, None, None],
        [None, None, None, None],
        {},
    )
    run_id = run_ids[0]
    measurements.record_snapshot(
        ADDRESS,
        ended_at.isoformat(),
        [slot(active=False), None, None, None],
        run_ids,
        {},
    )
    measurements.record_snapshot(
        ADDRESS,
        (ended_at + timedelta(minutes=30)).isoformat(),
        [slot(active=False), None, None, None],
        [None, None, None, None],
        {},
    )

    assert run_id is not None
    chart = measurements.run_chart(run_id)
    deleted = measurements.delete_run(run_id)
    remaining = measurements.history(
        ADDRESS,
        1,
        (ended_at - timedelta(minutes=10)).isoformat(),
        (ended_at + timedelta(hours=1)).isoformat(),
    )

    assert chart["since"] == (started_at - timedelta(minutes=5)).isoformat()
    assert chart["until"] == (ended_at + timedelta(hours=1)).isoformat()
    assert chart["total_points"] == 3
    assert deleted == {"measurements": 2, "notifications": 1}
    assert remaining["total_points"] == 1
    assert measurements.list_runs() == []
    assert measurements.list_notifications() == []
    with pytest.raises(KeyError):
        measurements.run_report(run_id)


def test_active_run_cannot_be_deleted_or_opened_as_completion_chart(tmp_path) -> None:
    path = tmp_path / "mc3000.db"
    ProfileStore(path)
    measurements = MeasurementStore(path)
    run_ids = measurements.record_snapshot(
        ADDRESS,
        datetime.now(UTC).isoformat(),
        [slot(active=True), None, None, None],
        [None, None, None, None],
        {},
    )
    run_id = run_ids[0]

    assert run_id is not None
    with pytest.raises(ValueError, match="laufender Programmlauf"):
        measurements.delete_run(run_id)
    with pytest.raises(ValueError, match="erst nach Abschluss"):
        measurements.run_chart(run_id)


def test_battery_store_persists_standard_program(tmp_path) -> None:
    store = BatteryStore(tmp_path / "mc3000.db")
    stored = store.save(
        BatteryValues(
            code="001",
            name="Testakku",
            battery_type_code=0,
            nominal_capacity_mah=2500,
            notes="",
            standard_mode_code=4,
            standard_charge_c_rate=0.8,
            standard_discharge_c_rate=0.4,
            standard_cycle_count=3,
            standard_cycle_mode=1,
            standard_time_limit_mode="off",
            standard_time_limit_min=360,
        )
    )

    loaded = store.get(stored.id)

    assert loaded is not None
    assert loaded.values.standard_mode_code == 4
    assert loaded.values.standard_charge_c_rate == 0.8
    assert loaded.values.standard_cycle_count == 3
    assert loaded.values.standard_time_limit_mode == "off"
    assert loaded.values.standard_time_limit_min == 360
    assert loaded.to_dict()["standard_program"]["mode"] == "Zyklus"


def test_battery_store_persists_catalog_metadata_and_technical_values(tmp_path) -> None:
    store = BatteryStore(tmp_path / "mc3000.db")
    stored = store.save(
        BatteryValues(
            code="CAT-1",
            name="Katalogzelle",
            battery_type_code=0,
            nominal_capacity_mah=3000,
            notes="",
            manufacturer="Samsung",
            model="INR18650-30Q",
            form_factor="18650",
            chemistry_detail="NMC",
            weight_g=48.1,
            nominal_voltage_v=3.6,
            min_voltage_v=2.5,
            max_voltage_v=4.2,
            max_charge_current_a=4,
            max_discharge_current_a=15,
            cycle_life=500,
            manufacture_year=2020,
            dimensions="Ø 18,3 × 65 mm",
            data_source_name="BetterBat",
            data_source_url="https://example.com/cell",
            data_source_retrieved_at="2026-08-02T10:00:00+00:00",
            technical_notes="Wert vor Verwendung prüfen.",
            technical_data={"Document ID": "TEST-30Q", "Rated Ah": "3"},
        )
    )

    loaded = store.get(stored.id)

    assert loaded is not None
    assert loaded.values.weight_g == 48.1
    assert loaded.values.nominal_voltage_v == 3.6
    assert loaded.values.max_discharge_current_a == 15
    assert loaded.values.data_source_url == "https://example.com/cell"
    assert loaded.values.technical_data == {
        "Document ID": "TEST-30Q",
        "Rated Ah": "3",
    }


def test_battery_cannot_be_assigned_to_two_slots(tmp_path) -> None:
    store = BatteryStore(tmp_path / "mc3000.db")
    stored = store.save(
        BatteryValues(
            code="001",
            name="",
            battery_type_code=0,
            nominal_capacity_mah=2000,
            notes="",
        )
    )
    store.assign(ADDRESS, 1, stored.id)

    with pytest.raises(BatteryError, match="bereits einem anderen Slot"):
        store.assign(ADDRESS, 2, stored.id)


def test_bulk_assignment_can_move_batteries_between_target_slots(tmp_path) -> None:
    store = BatteryStore(tmp_path / "mc3000.db")
    first = store.save(
        BatteryValues(
            code="001",
            name="",
            battery_type_code=0,
            nominal_capacity_mah=2000,
            notes="",
        )
    )
    second = store.save(
        BatteryValues(
            code="002",
            name="",
            battery_type_code=0,
            nominal_capacity_mah=2000,
            notes="",
        )
    )
    store.assign_many(ADDRESS, {1: first.id, 2: second.id})

    store.assign_many(ADDRESS, {1: second.id, 2: first.id})

    assert store.assignments_for(ADDRESS) == {1: second.id, 2: first.id}


def test_retention_keeps_active_and_recently_archived_battery_history(tmp_path) -> None:
    path = tmp_path / "mc3000.db"
    ProfileStore(path)
    batteries = BatteryStore(path)
    measurements = MeasurementStore(path)

    def create_battery_with_old_run(code: str):
        stored = batteries.save(
            BatteryValues(
                code=code,
                name="",
                battery_type_code=0,
                nominal_capacity_mah=2000,
                notes="",
            )
        )
        run_ids = measurements.record_snapshot(
            ADDRESS,
            old.isoformat(),
            [slot(active=True, mode_code=3), None, None, None],
            [None, None, None, None],
            {},
            {1: stored.id},
        )
        measurements.record_snapshot(
            ADDRESS,
            (old + timedelta(minutes=1)).isoformat(),
            [slot(active=False, mode_code=3), None, None, None],
            run_ids,
            {},
            {1: stored.id},
        )
        return stored

    old = datetime.now(UTC) - timedelta(days=100)
    active = create_battery_with_old_run("001")
    recently_archived = create_battery_with_old_run("002")
    expired_archive = create_battery_with_old_run("003")
    batteries.archive(recently_archived.id)
    batteries.archive(expired_archive.id)
    expired_archived_at = datetime.now(UTC) - timedelta(days=31)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE batteries SET archived_at = ? WHERE id = ?",
            (expired_archived_at.isoformat(), expired_archive.id),
        )
    measurements.record_snapshot(
        ADDRESS,
        old.isoformat(),
        [None, slot(active=False), None, None],
        [None, None, None, None],
        {},
        {},
    )

    deleted = measurements.purge_before(
        (datetime.now(UTC) - timedelta(days=90)).isoformat(),
        archived_battery_cutoff=(
            datetime.now(UTC) - timedelta(days=30)
        ).isoformat(),
    )
    generic_history = measurements.history(
        ADDRESS,
        2,
        (old - timedelta(minutes=1)).isoformat(),
        (old + timedelta(minutes=1)).isoformat(),
    )

    assert measurements.list_runs(battery_id=active.id)[0]["sample_count"] == 2
    assert measurements.list_runs(
        battery_id=recently_archived.id
    )[0]["sample_count"] == 2
    assert measurements.list_runs(battery_id=expired_archive.id) == []
    assert generic_history["total_points"] == 0
    assert deleted == 3
    assert batteries.get(expired_archive.id) is not None
    restored = batteries.save(
        replace(recently_archived.values, archived=False),
        battery_id=recently_archived.id,
    )
    assert restored.archived_at == ""


def test_permanent_battery_delete_removes_history_and_releases_code(tmp_path) -> None:
    path = tmp_path / "mc3000.db"
    ProfileStore(path)
    batteries = BatteryStore(path)
    measurements = MeasurementStore(path)
    battery = batteries.save(
        BatteryValues(
            code="006",
            name="Fehlanlage",
            battery_type_code=0,
            nominal_capacity_mah=3000,
            notes="",
        )
    )
    started_at = datetime.now(UTC) - timedelta(minutes=1)
    run_ids = measurements.record_snapshot(
        ADDRESS,
        started_at.isoformat(),
        [slot(active=True), None, None, None],
        [None, None, None, None],
        {},
        {1: battery.id},
    )
    measurements.record_snapshot(
        ADDRESS,
        (started_at + timedelta(seconds=30)).isoformat(),
        [slot(active=False), None, None, None],
        run_ids,
        {},
        {1: battery.id},
    )

    with pytest.raises(BatteryError, match="archiviert"):
        batteries.delete_permanently(battery.id)

    batteries.archive(battery.id)
    deleted = batteries.delete_permanently(battery.id)
    reused = batteries.save(
        BatteryValues(
            code="006",
            name="Korrekte Anlage",
            battery_type_code=0,
            nominal_capacity_mah=3000,
            notes="",
        )
    )

    assert deleted == {
        "measurements": 2,
        "runs": 1,
        "notifications": 1,
    }
    assert batteries.get(battery.id) is None
    assert reused.values.code == "006"
    with sqlite3.connect(path) as connection:
        for table in ("measurements", "recording_runs", "notifications"):
            assert connection.execute(
                f"SELECT COUNT(*) FROM {table} WHERE battery_id = ?",
                (battery.id,),
            ).fetchone()[0] == 0


def test_existing_measurement_database_is_migrated(tmp_path) -> None:
    path = tmp_path / "mc3000.db"
    ProfileStore(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE recording_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address TEXT NOT NULL,
                slot INTEGER NOT NULL,
                profile_id INTEGER,
                battery_type_code INTEGER NOT NULL,
                mode_code INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE measurements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recorded_at TEXT NOT NULL,
                address TEXT NOT NULL,
                slot INTEGER NOT NULL,
                run_id INTEGER,
                profile_id INTEGER,
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
                cycle_count INTEGER NOT NULL
            )
            """
        )

    MeasurementStore(path)

    with sqlite3.connect(path) as connection:
        run_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(recording_runs)")
        }
        measurement_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(measurements)")
        }
    assert "battery_id" in run_columns
    assert "nominal_capacity_mah" in run_columns
    assert "battery_id" in measurement_columns


def test_existing_battery_database_gets_standard_program_defaults(tmp_path) -> None:
    path = tmp_path / "mc3000.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE batteries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL COLLATE NOCASE UNIQUE,
                name TEXT NOT NULL DEFAULT '',
                battery_type_code INTEGER NOT NULL,
                nominal_capacity_mah INTEGER NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                archived INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO batteries(
                code, name, battery_type_code, nominal_capacity_mah,
                notes, archived, created_at, updated_at
            )
            VALUES (
                '001', '', 0, 2000, '', 1,
                '2025-01-01T00:00:00+00:00',
                '2025-02-01T00:00:00+00:00'
            )
            """
        )

    store = BatteryStore(path)
    stored = store.get_by_code("001")

    assert stored is not None
    assert stored.values.standard_mode_code == 0
    assert stored.values.standard_charge_c_rate == 0.5
    assert stored.values.standard_discharge_c_rate == 0.5
    assert stored.values.standard_cycle_count == 1
    assert stored.values.standard_time_limit_mode == "manual"
    assert stored.values.standard_time_limit_min == 360
    assert stored.values.manufacturer == ""
    assert stored.values.model == ""
    assert stored.values.form_factor == ""
    assert stored.values.origin == ""
    assert stored.values.in_service_since == ""
    assert stored.values.protected is False
    assert stored.values.archived is True
    assert stored.archived_at == "2025-02-01T00:00:00+00:00"
