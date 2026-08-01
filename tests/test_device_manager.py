import pytest

from mc3000_control.ble import DeviceManager, DeviceSession
from mc3000_control.registry import DeviceRegistry
from mc3000_control.storage import BatteryStore, MeasurementStore, ProfileStore

ADDRESS = "AA:BB:CC:DD:EE:FF"


def make_manager(tmp_path) -> DeviceManager:
    database = tmp_path / "mc3000.db"
    return DeviceManager(
        DeviceRegistry(database),
        ProfileStore(database),
        BatteryStore(database),
        MeasurementStore(database),
        scan_timeout=0.01,
    )


async def test_scan_does_not_disconnect_existing_session(
    tmp_path,
    monkeypatch,
) -> None:
    manager = make_manager(tmp_path)
    registration = manager.registry.save(ADDRESS, "Werkbank")
    session = DeviceSession(
        registration,
        manager.publish,
        manager.profile_store,
        manager.battery_store,
        manager.measurement_store,
    )

    class ConnectedClient:
        is_connected = True

    session.client = ConnectedClient()
    session.state = "connected"
    manager.sessions[ADDRESS] = session

    async def empty_scan(**_kwargs):
        return {}

    monkeypatch.setattr(
        "mc3000_control.ble.BleakScanner.discover",
        empty_scan,
    )

    await manager.scan()

    assert manager.sessions[ADDRESS] is session
    assert session.connected is True


def test_session_snapshot_normalizes_display_current(tmp_path) -> None:
    manager = make_manager(tmp_path)
    registration = manager.registry.save(ADDRESS, "Werkbank")
    session = DeviceSession(
        registration,
        manager.publish,
        manager.profile_store,
        manager.battery_store,
        manager.measurement_store,
    )
    session.slots = [
        {"status_code": 0, "status": "Bereit", "current_a": 0.009},
        {"status_code": 4, "status": "Fertig", "current_a": 0.010},
        {"status_code": 2, "status": "Entladen", "current_a": 1.005},
        {"status_code": 1, "status": "Laden", "current_a": 0.006},
    ]

    snapshot = session.snapshot()

    assert [slot["current_a"] for slot in snapshot["slots"]] == [
        0.0,
        0.0,
        -1.005,
        0.006,
    ]
    assert [slot["current_a"] for slot in session.slots] == [
        0.009,
        0.010,
        1.005,
        0.006,
    ]


async def test_remove_rejects_active_program_and_then_unregisters(
    tmp_path,
) -> None:
    manager = make_manager(tmp_path)
    registration = manager.registry.save(ADDRESS, "Werkbank")
    session = DeviceSession(
        registration,
        manager.publish,
        manager.profile_store,
        manager.battery_store,
        manager.measurement_store,
    )
    session.slots[0] = {"active": True}
    manager.sessions[ADDRESS] = session

    with pytest.raises(RuntimeError, match="laufenden Programms"):
        await manager.remove(ADDRESS)

    assert manager.registry.get(ADDRESS) == registration
    assert ADDRESS in manager.sessions

    session.slots[0] = {"active": False}
    removed = await manager.remove(ADDRESS)

    assert removed == {"address": ADDRESS, "alias": "Werkbank"}
    assert manager.registry.get(ADDRESS) is None
    assert ADDRESS not in manager.sessions
