from dataclasses import replace

import pytest
from httpx import ASGITransport, AsyncClient

from mc3000_control import protocol
from mc3000_control.app import _apply_profile_groups, create_app
from mc3000_control.battery_manager import BatteryValues
from mc3000_control.ble import DeviceSession
from mc3000_control.profiles import effective_time_limit_min
from mc3000_control.registry import RegisteredDevice

ADDRESS = "AA:BB:CC:DD:EE:FF"


class FakeClient:
    def __init__(self, session: DeviceSession) -> None:
        self.session = session
        self.is_connected = True
        self.writes: list[bytes] = []
        self.awaiting_profile_tail = False

    async def write_gatt_char(
        self,
        _characteristic,
        data: bytes,
        *,
        response: bool,
    ) -> None:
        self.writes.append(bytes(data))
        if data[1] == protocol.Opcode.STATUS:
            assert response is True
        else:
            assert response is False
        if self.awaiting_profile_tail:
            self.awaiting_profile_tail = False
            self.session._on_notification(
                None,
                bytearray(protocol.make_frame(protocol.Opcode.SET_PROFILE, b"\x03")),
            )
        elif data[1] == protocol.Opcode.SET_PROFILE:
            self.awaiting_profile_tail = True
        elif data[1] == protocol.Opcode.STATUS:
            slot = data[2]
            payload = bytes([slot, 0, 0, 0, 0]) + bytes(12)
            self.session._on_notification(
                None,
                bytearray(protocol.make_frame(protocol.Opcode.STATUS, payload)),
            )


async def test_shared_profile_configures_all_slots_without_start(tmp_path) -> None:
    app = create_app(data_dir=tmp_path, scan_timeout=0.01)
    async with app.router.lifespan_context(app):
        manager = app.state.manager
        session = DeviceSession(
            RegisteredDevice(ADDRESS, "Test", True, False),
            manager.publish,
            app.state.profiles,
            app.state.batteries,
            app.state.measurements,
        )
        fake = FakeClient(session)
        session.client = fake
        session.characteristic = object()
        session.state = "connected"
        session.slots = [
            {
                "active": False,
                "voltage_v": 3.8,
                "status_code": 0,
                "status": "Bereit",
            },
            {
                "active": False,
                "voltage_v": 3.7,
                "status_code": 0,
                "status": "Bereit",
            },
            None,
            None,
        ]
        manager.sessions[ADDRESS] = session
        first = app.state.batteries.save(
            BatteryValues(
                code="001",
                name="",
                battery_type_code=0,
                nominal_capacity_mah=2000,
                notes="",
            )
        )
        second = app.state.batteries.save(
            BatteryValues(
                code="002",
                name="",
                battery_type_code=0,
                nominal_capacity_mah=2000,
                notes="",
            )
        )
        profile = next(
            stored
            for stored in app.state.profiles.list()
            if stored.values.battery_type_code == 0
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.put(
                f"/api/devices/{ADDRESS}/configuration",
                json={
                    "slots": [
                        {
                            "slot": 1,
                            "battery_id": first.id,
                            "capacity_mah": 1500,
                        },
                        {
                            "slot": 2,
                            "battery_id": second.id,
                            "capacity_mah": 3000,
                        },
                    ],
                    "program_source": "profile",
                    "profile_id": profile.id,
                },
            )

        assert response.status_code == 200, response.text
        assert response.json()["started"] is False
        profile_packets = [
            write
            for write in fake.writes
            if len(write) == protocol.FRAME_SIZE
            and write[0] == 0x0F
            and write[1] == protocol.Opcode.SET_PROFILE
        ]
        assert [packet[2] for packet in profile_packets] == [0x01, 0x02]
        assert [
            int.from_bytes(packet[5:7], "big")
            for packet in profile_packets
        ] == [1500, 3000]
        assert not any(
            write[1] == protocol.Opcode.START
            for write in fake.writes
            if len(write) == protocol.FRAME_SIZE and write[0] == 0x0F
        )
        assert app.state.batteries.assignments_for(ADDRESS) == {
            1: first.id,
            2: second.id,
        }
        assert app.state.profiles.assignments_for(ADDRESS) == {
            1: profile.id,
            2: profile.id,
        }
        programs = app.state.profiles.programs_for(ADDRESS)
        assert programs[1]["details"]["capacity_mah"] == 1500
        assert programs[2]["details"]["capacity_mah"] == 3000
        assert programs[1]["label"].endswith("· 1500 mAh")
        assert programs[2]["label"].endswith("· 3000 mAh")
        assert app.state.profiles.get(profile.id).values.capacity_mah == (
            profile.values.capacity_mah
        )


async def test_identical_automatic_program_is_transferred_to_all_slots_once(
    tmp_path,
) -> None:
    app = create_app(data_dir=tmp_path, scan_timeout=0.01)
    async with app.router.lifespan_context(app):
        manager = app.state.manager
        session = DeviceSession(
            RegisteredDevice(ADDRESS, "Test", True, False),
            manager.publish,
            app.state.profiles,
            app.state.batteries,
            app.state.measurements,
        )
        fake = FakeClient(session)
        session.client = fake
        session.characteristic = object()
        session.state = "connected"
        session.slots = [
            {
                "active": False,
                "voltage_v": 3.8,
                "battery_type_code": 0,
                "status_code": 0,
                "status": "Bereit",
            }
            for _slot in range(4)
        ]
        manager.sessions[ADDRESS] = session
        batteries = [
            app.state.batteries.save(
                BatteryValues(
                    code=f"{index:03d}",
                    name="",
                    battery_type_code=0,
                    nominal_capacity_mah=2600,
                    notes="",
                )
            )
            for index in range(1, 5)
        ]

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.put(
                f"/api/devices/{ADDRESS}/configuration",
                json={
                    "slots": [
                        {
                            "slot": index,
                            "battery_id": battery.id,
                            "capacity_mah": 2600,
                        }
                        for index, battery in enumerate(batteries, start=1)
                    ],
                    "program_source": "automatic",
                    "automatic_program": "refresh",
                    "time_limit_mode": "off",
                },
            )

        assert response.status_code == 200, response.text
        profile_packets = [
            write
            for write in fake.writes
            if len(write) == protocol.FRAME_SIZE
            and write[0] == 0x0F
            and write[1] == protocol.Opcode.SET_PROFILE
        ]
        assert [packet[2] for packet in profile_packets] == [0x0F]
        assert response.json()["results"][0]["slots"] == [1, 2, 3, 4]
        assert not any(
            write[1] == protocol.Opcode.START
            for write in fake.writes
            if len(write) == protocol.FRAME_SIZE and write[0] == 0x0F
        )


async def test_group_profile_timeout_falls_back_to_individual_slots(tmp_path) -> None:
    app = create_app(data_dir=tmp_path, scan_timeout=0.01)
    async with app.router.lifespan_context(app):
        session = DeviceSession(
            RegisteredDevice(ADDRESS, "Test", True, False),
            app.state.manager.publish,
            app.state.profiles,
            app.state.batteries,
            app.state.measurements,
        )
        profile = app.state.profiles.list()[0].values
        calls: list[list[int]] = []

        async def apply_profile(_packet: bytes, slots: list[int]) -> dict:
            calls.append(list(slots))
            if len(slots) > 1:
                raise TimeoutError
            return {"ok": True, "slots": slots, "started": False}

        session.apply_profile = apply_profile  # type: ignore[method-assign]

        results = await _apply_profile_groups(
            session,
            [(1, profile), (2, profile)],
        )

        assert calls == [[1, 2], [1], [2]]
        assert [result["slots"] for result in results] == [[1], [2]]


async def test_single_profile_timeout_returns_explanatory_error(tmp_path) -> None:
    app = create_app(data_dir=tmp_path, scan_timeout=0.01)
    async with app.router.lifespan_context(app):
        session = DeviceSession(
            RegisteredDevice(ADDRESS, "Test", True, False),
            app.state.manager.publish,
            app.state.profiles,
            app.state.batteries,
            app.state.measurements,
        )
        profile = app.state.profiles.list()[0].values

        async def apply_profile(_packet: bytes, _slots: list[int]) -> dict:
            raise TimeoutError

        session.apply_profile = apply_profile  # type: ignore[method-assign]

        with pytest.raises(
            RuntimeError,
            match="Profilübertragung für Slot 1 nicht bestätigt",
        ):
            await _apply_profile_groups(session, [(1, profile)])


async def test_automatic_slot_program_is_clamped_and_persisted(tmp_path) -> None:
    app = create_app(data_dir=tmp_path, scan_timeout=0.01)
    async with app.router.lifespan_context(app):
        manager = app.state.manager
        session = DeviceSession(
            RegisteredDevice(ADDRESS, "Test", True, False),
            manager.publish,
            app.state.profiles,
            app.state.batteries,
            app.state.measurements,
        )
        session.client = FakeClient(session)
        session.characteristic = object()
        session.state = "connected"
        session.slots[0] = {
            "active": False,
            "voltage_v": 3.8,
            "status_code": 0,
            "status": "Bereit",
        }
        manager.sessions[ADDRESS] = session
        battery = app.state.batteries.save(
            BatteryValues(
                code="001",
                name="",
                battery_type_code=0,
                nominal_capacity_mah=2500,
                notes="",
            )
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.put(
                f"/api/devices/{ADDRESS}/slots/1/configuration",
                json={
                    "battery_id": battery.id,
                    "program_source": "automatic",
                    "automatic_program": "refresh",
                    "capacity_mah": 4000,
                },
            )

        assert response.status_code == 200
        assert response.json()["program"]["charge_current_ma"] == 2000
        assert response.json()["program"]["discharge_current_ma"] == 2000
        assert response.json()["program"]["time_limit_mode"] == "manual"
        assert response.json()["program"]["effective_time_limit_min"] == 360
        selected = session.snapshot()["programs"][1]
        assert selected["source"] == "automatic"
        assert selected["label"] == "Refresh · 4000 mAh"
        assert app.state.profiles.programs_for(ADDRESS)[1]["details"][
            "capacity_mah"
        ] == 4000


async def test_slot_profile_can_be_used_without_battery_record(tmp_path) -> None:
    app = create_app(data_dir=tmp_path, scan_timeout=0.01)
    async with app.router.lifespan_context(app):
        manager = app.state.manager
        session = DeviceSession(
            RegisteredDevice(ADDRESS, "Test", True, False),
            manager.publish,
            app.state.profiles,
            app.state.batteries,
            app.state.measurements,
        )
        fake = FakeClient(session)
        session.client = fake
        session.characteristic = object()
        session.state = "connected"
        session.slots[0] = {
            "active": False,
            "voltage_v": 3.8,
            "battery_type_code": 0,
            "status_code": 0,
            "status": "Bereit",
        }
        manager.sessions[ADDRESS] = session
        battery = app.state.batteries.save(
            BatteryValues(
                code="001",
                name="",
                battery_type_code=0,
                nominal_capacity_mah=2000,
                notes="",
            )
        )
        app.state.batteries.assign(ADDRESS, 1, battery.id)
        session._battery_ids[1] = battery.id
        profile = next(
            stored
            for stored in app.state.profiles.list()
            if stored.values.battery_type_code == 0
            and stored.values.mode_code == 0
        )
        profile = app.state.profiles.save(
            replace(profile.values, time_limit_mode="automatic"),
            profile_id=profile.id,
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.put(
                f"/api/devices/{ADDRESS}/slots/1/configuration",
                json={
                    "battery_id": None,
                    "program_source": "profile",
                    "profile_id": profile.id,
                    "capacity_mah": 3250,
                },
            )

        assert response.status_code == 200
        assert response.json()["battery"] is None
        assert response.json()["program"]["capacity_mah"] == 3250
        assert response.json()["program"]["effective_time_limit_min"] == (
            effective_time_limit_min(
                replace(profile.values, capacity_mah=3250)
            )
        )
        assert app.state.batteries.assignments_for(ADDRESS) == {}
        selected = session.snapshot()["programs"][1]
        assert selected["battery_id"] is None
        assert selected["details"]["capacity_mah"] == 3250
        assert selected["label"].endswith("· 3250 mAh")
        profile_packets = [
            write
            for write in fake.writes
            if len(write) == protocol.FRAME_SIZE
            and write[0] == 0x0F
            and write[1] == protocol.Opcode.SET_PROFILE
        ]
        assert int.from_bytes(profile_packets[0][5:7], "big") == 3250
        assert app.state.profiles.get(profile.id).values.capacity_mah != 3250
        assert session.snapshot()["battery_ids"] == {}
        assert not any(
            write[1] == protocol.Opcode.START
            for write in fake.writes
            if len(write) == protocol.FRAME_SIZE and write[0] == 0x0F
        )


async def test_anonymous_automatic_program_uses_detected_battery_type(tmp_path) -> None:
    app = create_app(data_dir=tmp_path, scan_timeout=0.01)
    async with app.router.lifespan_context(app):
        gentle = app.state.profiles.get_automatic("gentle_charge")
        assert gentle is not None
        app.state.profiles.save_automatic(
            replace(
                gentle.values,
                charge_c_rate=0.25,
                time_limit_mode="off",
            ),
            program_key=gentle.key,
        )
        manager = app.state.manager
        session = DeviceSession(
            RegisteredDevice(ADDRESS, "Test", True, False),
            manager.publish,
            app.state.profiles,
            app.state.batteries,
            app.state.measurements,
        )
        session.client = FakeClient(session)
        session.characteristic = object()
        session.state = "connected"
        session.slots[0] = {
            "active": False,
            "voltage_v": 3.3,
            "battery_type_code": 1,
            "status_code": 0,
            "status": "Bereit",
        }
        manager.sessions[ADDRESS] = session

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.put(
                f"/api/devices/{ADDRESS}/slots/1/configuration",
                json={
                    "battery_id": None,
                    "program_source": "automatic",
                    "automatic_program": "gentle_charge",
                    "capacity_mah": 2000,
                },
            )

        assert response.status_code == 200
        assert response.json()["battery"] is None
        assert response.json()["program"]["charge_current_ma"] == 500
        assert response.json()["program"]["charge_voltage_mv"] == 3600
        assert response.json()["program"]["effective_time_limit_min"] == 0
        assert app.state.batteries.assignments_for(ADDRESS) == {}
        assert session.snapshot()["programs"][1]["battery_id"] is None


async def test_slot_configuration_creates_numbered_battery_and_allows_live_edit(
    tmp_path,
) -> None:
    app = create_app(data_dir=tmp_path, scan_timeout=0.01)
    async with app.router.lifespan_context(app):
        manager = app.state.manager
        session = DeviceSession(
            RegisteredDevice(ADDRESS, "Test", True, False),
            manager.publish,
            app.state.profiles,
            app.state.batteries,
            app.state.measurements,
        )
        session.client = FakeClient(session)
        session.characteristic = object()
        session.state = "connected"
        session.slots[0] = {
            "active": False,
            "voltage_v": 3.8,
            "battery_type_code": 0,
            "status_code": 0,
            "status": "Bereit",
        }
        manager.sessions[ADDRESS] = session

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            configured = await client.put(
                f"/api/devices/{ADDRESS}/slots/1/configuration",
                json={
                    "battery_id": None,
                    "create_battery": True,
                    "program_source": "automatic",
                    "automatic_program": "refresh",
                    "capacity_mah": 2850,
                },
            )
            battery = configured.json()["battery"]
            session.slots[0]["active"] = True
            updated = await client.put(
                f"/api/batteries/{battery['id']}",
                json={
                    "code": battery["code"],
                    "name": "Werkstattzelle",
                    "battery_type_code": 0,
                    "nominal_capacity_mah": 2850,
                    "manufacturer": "Samsung",
                    "model": "INR18650-30Q",
                    "form_factor": "18650",
                    "origin": "Akkupack links",
                    "in_service_since": "2026-07-31",
                    "protected": True,
                    "notes": "Beim ersten Refresh angelegt",
                },
            )

        assert configured.status_code == 200, configured.text
        assert battery["code"] == "001"
        assert battery["battery_type_code"] == 0
        assert battery["nominal_capacity_mah"] == 2850
        assert app.state.batteries.assignments_for(ADDRESS) == {
            1: battery["id"],
        }
        assert session.snapshot()["battery_ids"][1] == battery["id"]
        assert updated.status_code == 200, updated.text
        assert updated.json()["battery"]["name"] == "Werkstattzelle"
        assert updated.json()["battery"]["manufacturer"] == "Samsung"
        assert updated.json()["battery"]["model"] == "INR18650-30Q"
        assert updated.json()["battery"]["form_factor"] == "18650"
        assert updated.json()["battery"]["origin"] == "Akkupack links"
        assert updated.json()["battery"]["in_service_since"] == "2026-07-31"
        assert updated.json()["battery"]["protected"] is True


async def test_bulk_configuration_creates_one_numbered_battery_per_slot(
    tmp_path,
) -> None:
    app = create_app(data_dir=tmp_path, scan_timeout=0.01)
    async with app.router.lifespan_context(app):
        manager = app.state.manager
        session = DeviceSession(
            RegisteredDevice(ADDRESS, "Test", True, False),
            manager.publish,
            app.state.profiles,
            app.state.batteries,
            app.state.measurements,
        )
        session.client = FakeClient(session)
        session.characteristic = object()
        session.state = "connected"
        session.slots = [
            {
                "active": False,
                "voltage_v": 3.8,
                "battery_type_code": 0,
                "status_code": 0,
                "status": "Bereit",
            },
            {
                "active": False,
                "voltage_v": 3.3,
                "battery_type_code": 1,
                "status_code": 0,
                "status": "Bereit",
            },
            None,
            None,
        ]
        manager.sessions[ADDRESS] = session

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.put(
                f"/api/devices/{ADDRESS}/configuration",
                json={
                    "slots": [
                        {
                            "slot": 1,
                            "create_battery": True,
                            "capacity_mah": 3000,
                        },
                        {
                            "slot": 2,
                            "create_battery": True,
                            "capacity_mah": 1800,
                        },
                    ],
                    "program_source": "automatic",
                    "automatic_program": "refresh",
                },
            )

        assert response.status_code == 200, response.text
        created = response.json()["created_batteries"]
        assert [battery["code"] for battery in created] == ["001", "002"]
        assert [battery["battery_type_code"] for battery in created] == [0, 1]
        assert [battery["nominal_capacity_mah"] for battery in created] == [
            3000,
            1800,
        ]
        assignments = app.state.batteries.assignments_for(ADDRESS)
        assert assignments == {
            1: created[0]["id"],
            2: created[1]["id"],
        }
        assert session.snapshot()["battery_ids"] == assignments


async def test_failed_bulk_configuration_does_not_create_batteries(
    tmp_path,
) -> None:
    app = create_app(data_dir=tmp_path, scan_timeout=0.01)
    async with app.router.lifespan_context(app):
        manager = app.state.manager
        session = DeviceSession(
            RegisteredDevice(ADDRESS, "Test", True, False),
            manager.publish,
            app.state.profiles,
            app.state.batteries,
            app.state.measurements,
        )
        session.client = FakeClient(session)
        session.characteristic = object()
        session.state = "connected"
        session.slots = [
            {
                "active": False,
                "voltage_v": 3.8,
                "battery_type_code": 0,
                "status_code": 0,
                "status": "Bereit",
            },
            {
                "active": False,
                "voltage_v": 3.7,
                "battery_type_code": 0,
                "status_code": 0,
                "status": "Bereit",
            },
            None,
            None,
        ]
        manager.sessions[ADDRESS] = session
        payload = {
            "slots": [
                {"slot": 1, "create_battery": True, "capacity_mah": 3000},
                {"slot": 2, "create_battery": True, "capacity_mah": 3000},
            ],
            "program_source": "automatic",
            "automatic_program": "refresh",
        }
        original_apply_profile = session.apply_profile

        async def fail_apply_profile(_packet: bytes, _slots: list[int]) -> dict:
            raise RuntimeError("simulierter Profilfehler")

        session.apply_profile = fail_apply_profile  # type: ignore[method-assign]
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            failed = await client.put(
                f"/api/devices/{ADDRESS}/configuration",
                json=payload,
            )
            session.apply_profile = original_apply_profile  # type: ignore[method-assign]
            retried = await client.put(
                f"/api/devices/{ADDRESS}/configuration",
                json=payload,
            )

        assert failed.status_code == 409
        assert retried.status_code == 200, retried.text
        assert [
            battery.values.code for battery in app.state.batteries.list()
        ] == ["001", "002"]


async def test_parallel_bulk_configuration_is_rejected_without_batteries(
    tmp_path,
) -> None:
    app = create_app(data_dir=tmp_path, scan_timeout=0.01)
    async with app.router.lifespan_context(app):
        manager = app.state.manager
        session = DeviceSession(
            RegisteredDevice(ADDRESS, "Test", True, False),
            manager.publish,
            app.state.profiles,
            app.state.batteries,
            app.state.measurements,
        )
        session.client = FakeClient(session)
        session.characteristic = object()
        session.state = "connected"
        session.slots[0] = {
            "active": False,
            "voltage_v": 3.8,
            "battery_type_code": 0,
            "status_code": 0,
            "status": "Bereit",
        }
        manager.sessions[ADDRESS] = session

        assert await session.acquire_configuration() is True
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                response = await client.put(
                    f"/api/devices/{ADDRESS}/configuration",
                    json={
                        "slots": [
                            {
                                "slot": 1,
                                "create_battery": True,
                                "capacity_mah": 3000,
                            }
                        ],
                        "program_source": "automatic",
                        "automatic_program": "refresh",
                    },
                )
        finally:
            session.release_configuration()

        assert response.status_code == 409
        assert response.json()["detail"] == (
            "Für dieses Ladegerät läuft bereits eine Konfiguration"
        )
        assert app.state.batteries.list() == []


async def test_bulk_profile_allows_multiple_anonymous_batteries(tmp_path) -> None:
    app = create_app(data_dir=tmp_path, scan_timeout=0.01)
    async with app.router.lifespan_context(app):
        manager = app.state.manager
        session = DeviceSession(
            RegisteredDevice(ADDRESS, "Test", True, False),
            manager.publish,
            app.state.profiles,
            app.state.batteries,
            app.state.measurements,
        )
        session.client = FakeClient(session)
        session.characteristic = object()
        session.state = "connected"
        session.slots = [
            {
                "active": False,
                "voltage_v": 3.8,
                "battery_type_code": 0,
                "status_code": 0,
                "status": "Bereit",
            },
            {
                "active": False,
                "voltage_v": 3.7,
                "battery_type_code": 0,
                "status_code": 0,
                "status": "Bereit",
            },
            None,
            None,
        ]
        manager.sessions[ADDRESS] = session
        profile = next(
            stored
            for stored in app.state.profiles.list()
            if stored.values.battery_type_code == 0
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.put(
                f"/api/devices/{ADDRESS}/configuration",
                json={
                    "slots": [
                        {"slot": 1, "battery_id": None},
                        {"slot": 2, "battery_id": None},
                    ],
                    "program_source": "profile",
                    "profile_id": profile.id,
                },
            )

        assert response.status_code == 200, response.text
        assert app.state.batteries.assignments_for(ADDRESS) == {}
        assert session.snapshot()["battery_ids"] == {}
        assert session.snapshot()["programs"][1]["battery_id"] is None
        assert session.snapshot()["programs"][2]["battery_id"] is None


async def test_standard_program_time_limit_mode_is_calculated_and_persisted(
    tmp_path,
) -> None:
    app = create_app(data_dir=tmp_path, scan_timeout=0.01)
    async with app.router.lifespan_context(app):
        battery = app.state.batteries.save(
            BatteryValues(
                code="001",
                name="",
                battery_type_code=0,
                nominal_capacity_mah=2000,
                notes="",
            )
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.put(
                f"/api/batteries/{battery.id}/standard-program",
                json={
                    "mode_code": 4,
                    "charge_c_rate": 1,
                    "discharge_c_rate": 1,
                    "cycle_count": 1,
                    "cycle_mode": 1,
                    "time_limit_mode": "automatic",
                    "time_limit_min": 360,
                },
            )

        assert response.status_code == 200, response.text
        assert response.json()["standard_program"]["time_limit_mode"] == "automatic"
        assert response.json()["standard_program"]["effective_time_limit_min"] == 280
        stored = app.state.batteries.get(battery.id)
        assert stored is not None
        assert stored.values.standard_time_limit_mode == "automatic"
        assert stored.values.standard_time_limit_min == 360


async def test_profile_api_persists_disabled_time_limit(tmp_path) -> None:
    app = create_app(data_dir=tmp_path, scan_timeout=0.01)
    async with app.router.lifespan_context(app):
        source = app.state.profiles.list()[0].to_dict()
        payload = {
            key: value
            for key, value in source.items()
            if key
            not in {
                "id",
                "battery_type",
                "mode",
                "effective_time_limit_min",
                "created_at",
                "updated_at",
            }
        }
        payload.update(
            name="Zeitlimit aus",
            time_limit_mode="off",
            time_limit_min=360,
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.post("/api/profiles", json=payload)

        assert response.status_code == 200, response.text
        assert response.json()["profile"]["time_limit_mode"] == "off"
        assert response.json()["profile"]["effective_time_limit_min"] == 0


async def test_automatic_profile_api_edits_and_duplicates_settings(tmp_path) -> None:
    app = create_app(data_dir=tmp_path, scan_timeout=0.01)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            options = await client.get("/api/batteries/options")
            gentle = next(
                profile
                for profile in options.json()["automatic_programs"]
                if profile["key"] == "gentle_charge"
            )
            payload = {
                key: gentle[key]
                for key in (
                    "label",
                    "description",
                    "mode_code",
                    "charge_c_rate",
                    "discharge_c_rate",
                    "cycle_count",
                    "cycle_mode",
                    "charge_rest_min",
                    "discharge_rest_min",
                    "temp_limit_c",
                    "time_limit_mode",
                    "time_limit_min",
                )
            }
            payload.update(
                label="Noch schonender laden",
                charge_c_rate=0.25,
                time_limit_mode="automatic",
            )
            updated = await client.put(
                "/api/automatic-profiles/gentle_charge",
                json=payload,
            )
            payload["label"] = "Noch schonender laden (Kopie)"
            duplicated = await client.post(
                "/api/automatic-profiles",
                json=payload,
            )
            refreshed = await client.get("/api/batteries/options")

        assert updated.status_code == 200, updated.text
        assert updated.json()["profile"]["charge_c_rate"] == 0.25
        assert updated.json()["profile"]["is_builtin"] is True
        assert duplicated.status_code == 200, duplicated.text
        assert duplicated.json()["profile"]["is_builtin"] is False
        assert duplicated.json()["profile"]["key"].startswith("own_")
        profiles = refreshed.json()["automatic_programs"]
        assert len(profiles) == 6
        assert next(
            profile
            for profile in profiles
            if profile["key"] == "gentle_charge"
        )["time_limit_mode"] == "automatic"


async def test_default_program_setting_is_empty_and_validated(tmp_path) -> None:
    app = create_app(data_dir=tmp_path, scan_timeout=0.01)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            initial = await client.get("/api/settings")
            saved = await client.put(
                "/api/settings",
                json={"default_program": "automatic:gentle_charge"},
            )
            invalid = await client.put(
                "/api/settings",
                json={"default_program": "profile:999"},
            )
            opacity = await client.put(
                "/api/settings",
                json={"default_program": "", "phase_opacity_percent": 22},
            )
            invalid_opacity = await client.put(
                "/api/settings",
                json={"default_program": "", "phase_opacity_percent": 14},
            )
            dark_theme = await client.put(
                "/api/settings",
                json={"default_program": "", "theme": "dark"},
            )
            invalid_theme = await client.put(
                "/api/settings",
                json={"default_program": "", "theme": "night"},
            )
            refreshed = await client.get("/api/settings")

        assert initial.json() == {
            "default_program": "",
            "phase_opacity_percent": 15,
            "theme": "system",
            "login_enabled": False,
            "login_username": "",
        }
        assert saved.status_code == 200
        assert saved.json()["default_program"] == "automatic:gentle_charge"
        assert invalid.status_code == 400
        assert opacity.status_code == 200
        assert opacity.json()["phase_opacity_percent"] == 22
        assert invalid_opacity.status_code == 422
        assert dark_theme.status_code == 200
        assert dark_theme.json()["theme"] == "dark"
        assert invalid_theme.status_code == 422
        assert refreshed.json()["phase_opacity_percent"] == 22
        assert refreshed.json()["theme"] == "dark"


async def test_optional_login_protects_api_and_hashes_password(tmp_path) -> None:
    app = create_app(data_dir=tmp_path, scan_timeout=0.01)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            enabled = await client.put(
                "/api/settings",
                json={
                    "default_program": "",
                    "login_enabled": True,
                    "login_username": "werkstatt",
                    "login_password": "sehr-sicher",
                },
            )
            blocked = await client.get("/api/settings")
            wrong = await client.post(
                "/api/auth/login",
                json={"username": "werkstatt", "password": "falsch"},
            )
            logged_in = await client.post(
                "/api/auth/login",
                json={"username": "werkstatt", "password": "sehr-sicher"},
            )
            accessible = await client.get("/api/settings")
            logged_out = await client.post("/api/auth/logout")
            blocked_again = await client.get("/api/settings")

        password_record = app.state.profiles.get_app_setting(
            "auth_password",
            "",
        )

    assert enabled.status_code == 200
    assert blocked.status_code == 401
    assert wrong.status_code == 401
    assert logged_in.status_code == 200
    assert logged_in.cookies.get("mc3000_session")
    assert accessible.status_code == 200
    assert logged_out.status_code == 200
    assert blocked_again.status_code == 401
    assert password_record.startswith("scrypt$")
    assert "sehr-sicher" not in password_record


async def test_profile_categories_are_persistent_and_defaults_are_protected(
    tmp_path,
) -> None:
    app = create_app(data_dir=tmp_path, scan_timeout=0.01)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            initial = await client.get("/api/profile-categories")
            created = await client.post(
                "/api/profile-categories",
                json={"name": "Werkstatt-Spezial"},
            )
            custom_key = created.json()["category"]["key"]
            protected = await client.delete("/api/profile-categories/lithium")
            deleted = await client.delete(
                f"/api/profile-categories/{custom_key}"
            )
            refreshed = await client.get("/api/profile-categories")

    assert initial.status_code == 200
    assert {item["key"] for item in initial.json()["categories"]} >= {
        "general",
        "automatic",
        "lithium",
        "nickel",
    }
    assert created.status_code == 200
    assert protected.status_code == 409
    assert deleted.status_code == 200
    assert custom_key not in {
        item["key"] for item in refreshed.json()["categories"]
    }
