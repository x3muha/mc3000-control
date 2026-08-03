from datetime import UTC, datetime

import pytest

from mc3000_control import protocol
from mc3000_control.battery_manager import BatteryValues
from mc3000_control.ble import DeviceSession
from mc3000_control.profiles import build_profile_packet
from mc3000_control.registry import RegisteredDevice
from mc3000_control.storage import BatteryStore, MeasurementStore, ProfileStore


class FakeClient:
    def __init__(self, session: DeviceSession) -> None:
        self.session = session
        self.is_connected = True
        self.writes: list[bytes] = []
        self.responses: list[bool] = []

    async def write_gatt_char(
        self,
        _characteristic,
        data: bytes,
        *,
        response: bool,
    ) -> None:
        self.writes.append(bytes(data))
        self.responses.append(response)
        if (
            len(self.writes) == 3
            and self.writes[1][1] == protocol.Opcode.SET_PROFILE
        ):
            self.session._on_notification(
                None,
                bytearray(protocol.make_frame(protocol.Opcode.SET_PROFILE, b"\x02")),
            )
        elif data[1] == protocol.Opcode.START:
            self.session._on_notification(
                None,
                bytearray(
                    protocol.make_frame(protocol.Opcode.START, bytes([data[2]]))
                ),
            )
        elif data[1] == protocol.Opcode.STATUS:
            slot = data[2]
            payload = bytes([slot, 0, 0, 0, 0]) + bytes(12)
            self.session._on_notification(
                None,
                bytearray(protocol.make_frame(protocol.Opcode.STATUS, payload)),
            )


async def test_profile_write_matches_phone_sequence_without_start(tmp_path) -> None:
    path = tmp_path / "mc3000.db"
    profiles = ProfileStore(path)
    batteries = BatteryStore(path)
    measurements = MeasurementStore(path)

    async def changed() -> None:
        pass

    session = DeviceSession(
        RegisteredDevice("AA:BB:CC:DD:EE:FF", "Test", True, False),
        changed,
        profiles,
        batteries,
        measurements,
    )
    fake = FakeClient(session)
    session.client = fake
    session.characteristic = object()
    session.slots[1] = {"active": False}
    packet = build_profile_packet(profiles.list()[0].values, 0x02)

    result = await session.apply_profile(packet, [2])

    assert result["started"] is False
    assert fake.responses[:3] == [False, False, False]
    assert fake.writes[0] == protocol.command_stop(0x02)
    assert fake.writes[1] == packet[:20]
    assert fake.writes[2] == packet[20:]
    assert all(
        write[1] != protocol.Opcode.START for write in fake.writes if write[0] == 0x0F
    )


async def test_shared_profile_is_written_to_multiple_slots_at_once(tmp_path) -> None:
    path = tmp_path / "mc3000.db"
    profiles = ProfileStore(path)
    batteries = BatteryStore(path)
    measurements = MeasurementStore(path)

    async def changed() -> None:
        pass

    session = DeviceSession(
        RegisteredDevice("AA:BB:CC:DD:EE:FF", "Test", True, False),
        changed,
        profiles,
        batteries,
        measurements,
    )
    fake = FakeClient(session)
    session.client = fake
    session.characteristic = object()
    session.slots[0] = {"active": False}
    session.slots[2] = {"active": False}
    packet = build_profile_packet(profiles.list()[0].values, 0x05)

    result = await session.apply_profile(packet, [1, 3])

    assert result["slots"] == [1, 3]
    assert fake.writes[0] == protocol.command_stop(0x05)
    assert fake.writes[1][2] == 0x05


async def test_start_all_uses_only_inserted_inactive_slots(tmp_path) -> None:
    path = tmp_path / "mc3000.db"
    profiles = ProfileStore(path)
    batteries = BatteryStore(path)
    measurements = MeasurementStore(path)

    async def changed() -> None:
        pass

    session = DeviceSession(
        RegisteredDevice("AA:BB:CC:DD:EE:FF", "Test", True, False),
        changed,
        profiles,
        batteries,
        measurements,
    )
    fake = FakeClient(session)
    session.client = fake
    session.characteristic = object()
    session.slots = [
        {"active": False, "voltage_v": 3.8, "status_code": 0},
        {"active": True, "voltage_v": 3.7, "status_code": 1},
        {"active": False, "voltage_v": 0.0, "status_code": 0},
        {"active": False, "voltage_v": 1.3, "status_code": 0},
    ]
    profile = profiles.list()[0]
    session.mark_profile_applied(
        [1, 4],
        profile.id,
        {
            "source": "profile",
            "label": profile.values.name,
            "details": profile.to_dict(),
            "battery_id": None,
            "profile_id": profile.id,
            "selected_at": datetime.now(UTC).isoformat(),
        },
    )

    result = await session.start_all()

    assert result["slots"] == [1, 4]
    assert fake.writes[0] == protocol.command_start(0x09)


async def test_start_is_rejected_without_selected_program(tmp_path) -> None:
    path = tmp_path / "mc3000.db"
    session = DeviceSession(
        RegisteredDevice("AA:BB:CC:DD:EE:FF", "Test", True, False),
        lambda: None,
        ProfileStore(path),
        BatteryStore(path),
        MeasurementStore(path),
    )
    session.slots[0] = {
        "active": False,
        "voltage_v": 3.8,
        "status_code": 0,
        "status": "Bereit",
    }

    with pytest.raises(RuntimeError, match="kein Startprogramm"):
        await session.start_slot(1)


async def test_battery_assignment_is_retained_until_voltage_collapse(tmp_path) -> None:
    path = tmp_path / "mc3000.db"
    profiles = ProfileStore(path)
    batteries = BatteryStore(path)
    measurements = MeasurementStore(path)
    battery = batteries.save(
        BatteryValues(
            code="001",
            name="",
            battery_type_code=0,
            nominal_capacity_mah=2000,
            notes="",
        )
    )
    batteries.assign("AA:BB:CC:DD:EE:FF", 1, battery.id)
    profile = profiles.list()[0]
    profiles.assign("AA:BB:CC:DD:EE:FF", [1], profile.id)
    profiles.set_slot_program(
        "AA:BB:CC:DD:EE:FF",
        1,
        source="profile",
        label=profile.values.name,
        details=profile.to_dict(),
        battery_id=battery.id,
        profile_id=profile.id,
    )
    active_slot = {
        "battery_type_code": 0,
        "mode_code": 3,
        "cycle_count": 0,
        "status_code": 2,
        "active": True,
        "time_s": 10,
        "voltage_v": 3.9,
        "current_a": 1.0,
        "capacity_mah": 100,
        "temperature_c": 27,
        "resistance_mohm": 40,
    }
    run_ids = measurements.record_snapshot(
        "AA:BB:CC:DD:EE:FF",
        datetime.now(UTC).isoformat(),
        [active_slot, None, None, None],
        [None, None, None, None],
        {1: profile.id},
        {1: battery.id},
    )

    async def changed() -> None:
        pass

    session = DeviceSession(
        RegisteredDevice("AA:BB:CC:DD:EE:FF", "Test", True, False),
        changed,
        profiles,
        batteries,
        measurements,
    )
    session.slots = [{**active_slot, "active": False, "status_code": 4}] * 4
    session._run_ids = run_ids
    session.last_update = datetime.now(UTC).isoformat()

    await session._record_if_due()

    assert session.snapshot()["battery_ids"] == {1: battery.id}
    assert session.snapshot()["profile_ids"] == {1: profile.id}
    assert session.snapshot()["programs"][1]["battery_id"] == battery.id
    assert batteries.assignments_for(session.address) == {1: battery.id}
    assert profiles.assignments_for(session.address) == {1: profile.id}
    assert profiles.programs_for(session.address)[1]["battery_id"] == battery.id

    await session._reconcile_battery_presence()
    session.slots[0]["voltage_v"] = 2.8
    await session._reconcile_battery_presence()

    assert session.snapshot()["battery_ids"] == {1: battery.id}

    session.slots[0]["voltage_v"] = 0.6
    await session._reconcile_battery_presence()

    assert session.snapshot()["battery_ids"] == {1: battery.id}

    await session._reconcile_battery_presence()

    assert session.snapshot()["battery_ids"] == {}
    assert session.snapshot()["profile_ids"] == {}
    assert session.snapshot()["programs"] == {}
    assert batteries.assignments_for(session.address) == {}
    assert profiles.assignments_for(session.address) == {}
    assert profiles.programs_for(session.address) == {}


async def test_zero_voltage_clears_persisted_battery_assignment_immediately(
    tmp_path,
) -> None:
    path = tmp_path / "mc3000.db"
    profiles = ProfileStore(path)
    batteries = BatteryStore(path)
    measurements = MeasurementStore(path)
    battery = batteries.save(
        BatteryValues(
            code="001",
            name="",
            battery_type_code=0,
            nominal_capacity_mah=2000,
            notes="",
        )
    )
    batteries.assign("AA:BB:CC:DD:EE:FF", 1, battery.id)

    async def changed() -> None:
        pass

    session = DeviceSession(
        RegisteredDevice("AA:BB:CC:DD:EE:FF", "Test", True, False),
        changed,
        profiles,
        batteries,
        measurements,
    )
    session.slots[0] = {"active": False, "voltage_v": 0.0}

    await session._reconcile_battery_presence()

    assert session.snapshot()["battery_ids"] == {}
    assert batteries.assignments_for(session.address) == {}


async def test_program_without_battery_record_is_cleared_after_run(tmp_path) -> None:
    path = tmp_path / "mc3000.db"
    profiles = ProfileStore(path)
    batteries = BatteryStore(path)
    measurements = MeasurementStore(path)
    profile = profiles.list()[0]
    profiles.assign("AA:BB:CC:DD:EE:FF", [1], profile.id)
    profiles.set_slot_program(
        "AA:BB:CC:DD:EE:FF",
        1,
        source="profile",
        label=profile.values.name,
        details=profile.to_dict(),
        battery_id=None,
        profile_id=profile.id,
    )
    active_slot = {
        "battery_type_code": 0,
        "mode_code": 0,
        "cycle_count": 0,
        "status_code": 1,
        "active": True,
        "time_s": 10,
        "voltage_v": 4.1,
        "current_a": 1.0,
        "capacity_mah": 100,
        "temperature_c": 27,
        "resistance_mohm": 40,
    }
    run_ids = measurements.record_snapshot(
        "AA:BB:CC:DD:EE:FF",
        datetime.now(UTC).isoformat(),
        [active_slot, None, None, None],
        [None, None, None, None],
        {1: profile.id},
        {},
    )

    async def changed() -> None:
        pass

    session = DeviceSession(
        RegisteredDevice("AA:BB:CC:DD:EE:FF", "Test", True, False),
        changed,
        profiles,
        batteries,
        measurements,
    )
    session.slots = [{**active_slot, "active": False, "status_code": 4}] * 4
    session._run_ids = run_ids

    await session._record_if_due()

    assert session.snapshot()["battery_ids"] == {}
    assert session.snapshot()["profile_ids"] == {}
    assert session.snapshot()["programs"] == {}
    assert profiles.assignments_for(session.address) == {}
    assert profiles.programs_for(session.address) == {}
