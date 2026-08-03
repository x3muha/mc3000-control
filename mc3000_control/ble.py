from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from . import protocol
from .registry import DeviceRegistry, RegisteredDevice, normalize_address
from .storage import BatteryStore, MeasurementStore, ProfileStore

LOGGER = logging.getLogger(__name__)
ChangeCallback = Callable[[], Awaitable[None]]

# Removal is evaluated only for inactive slots. A zero reading is unambiguous;
# non-zero contact-loss readings must stay at or below one quarter of the last
# credible voltage for two complete polling cycles before an assignment is released.
BATTERY_REMOVAL_VOLTAGE_RATIO = 0.25
BATTERY_REMOVAL_CONFIRMATIONS = 2


@dataclass(slots=True)
class DiscoveredDevice:
    address: str
    name: str
    rssi: int | None
    last_seen: str
    registered: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DeviceSession:
    def __init__(
        self,
        registration: RegisteredDevice,
        on_change: ChangeCallback,
        profile_store: ProfileStore,
        battery_store: BatteryStore,
        measurement_store: MeasurementStore,
        *,
        poll_interval: float = 0.25,
        active_record_interval: float = 2,
        idle_record_interval: float = 30,
    ) -> None:
        self.registration = registration
        self.on_change = on_change
        self.profile_store = profile_store
        self.battery_store = battery_store
        self.measurement_store = measurement_store
        self.poll_interval = poll_interval
        self.active_record_interval = active_record_interval
        self.idle_record_interval = idle_record_interval
        self.ble_device: BLEDevice | None = None
        self.client: BleakClient | None = None
        self.characteristic: Any | None = None
        self.state = "released" if registration.released else "waiting"
        self.error: str | None = None
        self.last_update: str | None = None
        self.version: dict[str, Any] | None = None
        self.basic: dict[str, Any] | None = None
        self.slots: list[dict[str, Any] | None] = [None] * protocol.SLOT_COUNT
        self._notifications: asyncio.Queue[bytes] = asyncio.Queue()
        self._request_lock = asyncio.Lock()
        self._configuration_lock = asyncio.Lock()
        self._stop = asyncio.Event()
        self._wake = asyncio.Event()
        self._disconnected = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._consecutive_errors = 0
        self._last_recorded_at = 0.0
        self._run_ids: list[int | None] = [None] * protocol.SLOT_COUNT
        self._profile_ids = profile_store.assignments_for(registration.address)
        self._battery_ids = battery_store.assignments_for(registration.address)
        self._battery_reference_voltage_v: dict[int, float] = {}
        self._battery_removal_counts: dict[int, int] = {}
        self._programs = profile_store.programs_for(registration.address)
        for slot, profile_id in self._profile_ids.items():
            if slot in self._programs:
                continue
            stored = profile_store.get(profile_id)
            if stored is not None:
                self._programs[slot] = {
                    "source": "profile",
                    "label": stored.values.name,
                    "details": stored.to_dict(),
                    "battery_id": self._battery_ids.get(slot),
                    "profile_id": profile_id,
                    "selected_at": stored.updated_at,
                }
        for slot, battery_id in self._battery_ids.items():
            if slot in self._programs:
                continue
            battery = battery_store.get(battery_id)
            if battery is not None:
                standard = battery.values.to_dict()["standard_program"]
                self._programs[slot] = {
                    "source": "standard",
                    "label": f"{standard['mode']} · Standard",
                    "details": standard,
                    "battery_id": battery_id,
                    "profile_id": None,
                    "selected_at": battery.updated_at,
                }

    @property
    def address(self) -> str:
        return self.registration.address

    @property
    def connected(self) -> bool:
        return bool(
            self.client and self.client.is_connected and self.state == "connected"
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "alias": self.registration.alias,
            "enabled": self.registration.enabled,
            "released": self.registration.released,
            "serial_number": self.registration.serial_number,
            "state": self.state,
            "connected": self.connected,
            "error": self.error,
            "last_update": self.last_update,
            "version": self.version,
            "basic": self.basic,
            "slots": [_slot_snapshot(slot) for slot in self.slots],
            "profile_ids": self._profile_ids,
            "battery_ids": self._battery_ids,
            "programs": self._programs,
        }

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(
                self._run(),
                name=f"mc3000-{self.address}",
            )

    async def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        await self._disconnect()

    def update_device(self, device: BLEDevice) -> None:
        self.ble_device = device
        self._wake.set()

    def update_registration(self, registration: RegisteredDevice) -> None:
        was_released = self.registration.released
        self.registration = registration
        if registration.released:
            self.state = "released"
        elif was_released:
            self.state = "waiting"
        self._wake.set()

    async def start_slot(self, slot: int) -> dict[str, Any]:
        self._require_slot(slot)
        current = self.slots[slot - 1]
        if current is None or current["voltage_v"] <= 0:
            raise RuntimeError(f"Slot {slot} erkennt keine Batterie")
        if current["active"]:
            raise RuntimeError(f"Slot {slot} ist bereits aktiv")
        if current["status_code"] >= 128:
            raise RuntimeError(f"Slot {slot} meldet {current['status']}")
        if slot not in self._programs:
            raise RuntimeError(f"Für Slot {slot} ist kein Startprogramm ausgewählt")
        return await self._start_slots([slot])

    async def start_all(self) -> dict[str, Any]:
        slots = [
            index + 1
            for index, current in enumerate(self.slots)
            if current is not None
            and not current["active"]
            and current["voltage_v"] > 0
            and current["status_code"] < 128
        ]
        if not slots:
            raise RuntimeError("Kein startbereiter Slot mit Batterie gefunden")
        missing = [slot for slot in slots if slot not in self._programs]
        if missing:
            slot_list = ", ".join(str(slot) for slot in missing)
            raise RuntimeError(
                f"Für Slot {slot_list} ist kein Startprogramm ausgewählt"
            )
        return await self._start_slots(slots)

    async def _start_slots(self, slots: list[int]) -> dict[str, Any]:
        slot_mask = sum(1 << (slot - 1) for slot in slots)
        response = await self._request(
            protocol.command_start(slot_mask),
            protocol.Opcode.START,
        )
        for slot in slots:
            await self._poll_slot(slot - 1)
        return {
            "ok": True,
            "slots": slots,
            "response": response.hex().upper(),
        }

    async def stop_slot(self, slot: int) -> dict[str, Any]:
        self._require_slot(slot)
        response = await self._request(
            protocol.command_stop(1 << (slot - 1)),
            protocol.Opcode.STOP,
        )
        await self._poll_slot(slot - 1)
        return {"ok": True, "slot": slot, "response": response.hex().upper()}

    async def stop_all(self) -> dict[str, Any]:
        response = await self._request(
            protocol.command_stop(0x0F),
            protocol.Opcode.STOP,
        )
        for slot in range(protocol.SLOT_COUNT):
            await self._poll_slot(slot)
        return {"ok": True, "response": response.hex().upper()}

    async def read_curve(self, slot: int) -> dict[str, Any]:
        self._require_slot(slot)
        response = await self._request(
            protocol.command_curve(slot - 1),
            protocol.Opcode.VOLTAGE_CURVE,
            response_size=protocol.CURVE_SIZE,
            timeout=8,
        )
        return protocol.parse_curve(response)

    async def apply_profile(self, packet: bytes, slots: list[int]) -> dict[str, Any]:
        clean_slots = sorted(set(slots))
        if not clean_slots or any(
            slot not in range(1, protocol.SLOT_COUNT + 1) for slot in clean_slots
        ):
            raise ValueError("Slot muss zwischen 1 und 4 liegen")
        if len(packet) != protocol.PROFILE_SIZE:
            raise ValueError("MC3000-Profil muss genau 40 Byte lang sein")
        if packet[0] != 0x0F or packet[1] != protocol.Opcode.SET_PROFILE:
            raise ValueError("Ungültiges MC3000-Profilpaket")

        for slot in clean_slots:
            current = self.slots[slot - 1]
            if current and current["active"]:
                raise RuntimeError(
                    f"Slot {slot} ist aktiv und muss vor dem Profilwechsel beendet werden"
                )

        slot_mask = sum(1 << (slot - 1) for slot in clean_slots)
        if packet[2] != slot_mask:
            raise ValueError("Slot-Auswahl stimmt nicht mit dem Profilpaket überein")

        response = await self._write_profile(packet, slot_mask)
        for slot in clean_slots:
            await self._poll_slot(slot - 1)
        return {
            "ok": True,
            "slots": clean_slots,
            "response": response.hex().upper(),
            "started": False,
        }

    async def acquire_configuration(self) -> bool:
        """Acquire the device-wide configuration guard without queueing duplicates."""

        if self._configuration_lock.locked():
            return False
        await self._configuration_lock.acquire()
        return True

    def release_configuration(self) -> None:
        if self._configuration_lock.locked():
            self._configuration_lock.release()

    def mark_profile_applied(
        self,
        slots: list[int],
        profile_id: int,
        program: dict[str, Any],
    ) -> None:
        for slot in slots:
            self._profile_ids[slot] = profile_id
            self._programs[slot] = dict(program)

    def mark_slot_configuration(
        self,
        slot: int,
        battery_id: int | None,
        profile_id: int | None,
        program: dict[str, Any],
    ) -> None:
        if profile_id is None:
            self._profile_ids.pop(slot, None)
        else:
            self._profile_ids[slot] = profile_id
        if battery_id is None:
            self._battery_ids.pop(slot, None)
            self._reset_battery_presence_tracking(slot)
        else:
            self._battery_ids[slot] = battery_id
            self._reset_battery_presence_tracking(slot)
            current = self.slots[slot - 1]
            if current is not None and float(current.get("voltage_v", 0)) > 0:
                self._battery_reference_voltage_v[slot] = float(current["voltage_v"])
        self._programs[slot] = dict(program)

    def clear_battery_assignment(self, battery_id: int) -> None:
        cleared_slots = {
            slot
            for slot, assigned_id in self._battery_ids.items()
            if assigned_id == battery_id
        }
        self._battery_ids = {
            slot: assigned_id
            for slot, assigned_id in self._battery_ids.items()
            if assigned_id != battery_id
        }
        for slot in cleared_slots:
            self._reset_battery_presence_tracking(slot)
            self._profile_ids.pop(slot, None)
            self._programs.pop(slot, None)

    async def _run(self) -> None:
        while not self._stop.is_set():
            if not self.registration.enabled:
                self.state = "disabled"
                await self._notify_change()
                await self._wait_for_wake(30)
                continue

            if self.registration.released:
                self.state = "released"
                self.error = None
                await self._disconnect()
                await self._notify_change()
                await self._wait_for_wake(30)
                continue

            if self.ble_device is None:
                self.state = "waiting"
                await self._notify_change()
                await self._wait_for_wake(10)
                continue

            try:
                await self._connect_and_poll()
                self._consecutive_errors = 0
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - session boundary must reconnect
                self._consecutive_errors += 1
                self.state = "error"
                self.error = _clean_error(exc)
                LOGGER.warning("%s: BLE error: %s", self.address, self.error)
                await self._notify_change()
            finally:
                await self._disconnect()

            delay = min(2 ** min(self._consecutive_errors, 4), 20)
            await self._wait_for_wake(delay)

    async def _connect_and_poll(self) -> None:
        if self.ble_device is None:
            return

        self.state = "connecting"
        self.error = None
        self._disconnected.clear()
        await self._notify_change()

        def disconnected_callback(_client: BleakClient) -> None:
            self._disconnected.set()

        self.client = BleakClient(
            self.ble_device,
            disconnected_callback=disconnected_callback,
            services=[protocol.SERVICE_UUID],
            timeout=20,
        )
        await self.client.connect()
        self.characteristic = self.client.services.get_characteristic(
            protocol.CHARACTERISTIC_UUID
        )
        if self.characteristic is None:
            raise RuntimeError("MC3000-Charakteristik FFE1 wurde nicht gefunden")
        await self.client.start_notify(self.characteristic, self._on_notification)

        self.version = protocol.parse_version(
            await self._request(
                protocol.command_version(self.address),
                protocol.Opcode.VERSION,
            )
        ).to_dict()
        self.basic = protocol.parse_basic(
            await self._request(protocol.command_basic(), protocol.Opcode.GET_BASIC)
        ).to_dict()
        self.state = "connected"
        self.error = None
        self._consecutive_errors = 0
        await self._notify_change()

        basic_refresh_at = asyncio.get_running_loop().time() + 30
        while (
            not self._stop.is_set()
            and not self.registration.released
            and self.client.is_connected
            and not self._disconnected.is_set()
        ):
            for slot in range(protocol.SLOT_COUNT):
                await self._poll_slot(slot)
                await asyncio.sleep(self.poll_interval)

            now = asyncio.get_running_loop().time()
            if now >= basic_refresh_at:
                self.basic = protocol.parse_basic(
                    await self._request(
                        protocol.command_basic(),
                        protocol.Opcode.GET_BASIC,
                    )
                ).to_dict()
                basic_refresh_at = now + 30

            self.last_update = datetime.now(UTC).isoformat()
            await self._record_if_due()
            await self._reconcile_battery_presence()
            await self._notify_change()

    async def _poll_slot(self, slot: int) -> None:
        response = await self._request(
            protocol.command_status(slot),
            protocol.Opcode.STATUS,
        )
        self.slots[slot] = protocol.parse_slot(response).to_dict()

    async def _request(
        self,
        command: bytes,
        expected_opcode: int | protocol.Opcode,
        *,
        response_size: int = protocol.FRAME_SIZE,
        timeout: float = 4,
    ) -> bytes:
        if (
            self.client is None
            or not self.client.is_connected
            or self.characteristic is None
        ):
            raise RuntimeError("Ladegerät ist nicht verbunden")

        async with self._request_lock:
            while not self._notifications.empty():
                with contextlib.suppress(asyncio.QueueEmpty):
                    self._notifications.get_nowait()

            await self.client.write_gatt_char(
                self.characteristic,
                command,
                response=True,
            )

            collected = bytearray()
            async with asyncio.timeout(timeout):
                while len(collected) < response_size:
                    chunk = await self._notifications.get()
                    if not collected and (
                        len(chunk) < 2
                        or chunk[0] != 0x0F
                        or chunk[1] != int(expected_opcode)
                    ):
                        continue
                    collected.extend(chunk)

            return bytes(collected[:response_size])

    async def _write_profile(self, packet: bytes, slot_mask: int) -> bytes:
        if (
            self.client is None
            or not self.client.is_connected
            or self.characteristic is None
        ):
            raise RuntimeError("Ladegerät ist nicht verbunden")

        async with self._request_lock:
            while not self._notifications.empty():
                with contextlib.suppress(asyncio.QueueEmpty):
                    self._notifications.get_nowait()

            await self.client.write_gatt_char(
                self.characteristic,
                protocol.command_stop(slot_mask),
                response=False,
            )
            await asyncio.sleep(0.5)
            while not self._notifications.empty():
                with contextlib.suppress(asyncio.QueueEmpty):
                    self._notifications.get_nowait()

            await self.client.write_gatt_char(
                self.characteristic,
                packet[: protocol.FRAME_SIZE],
                response=False,
            )
            await asyncio.sleep(0.05)
            await self.client.write_gatt_char(
                self.characteristic,
                packet[protocol.FRAME_SIZE :],
                response=False,
            )

            async with asyncio.timeout(5):
                while True:
                    response = await self._notifications.get()
                    if (
                        len(response) >= protocol.FRAME_SIZE
                        and response[0] == 0x0F
                        and response[1] == protocol.Opcode.SET_PROFILE
                    ):
                        return response[: protocol.FRAME_SIZE]

    async def _record_if_due(self) -> None:
        if not all(self.slots):
            return
        now = asyncio.get_running_loop().time()
        active = any(slot and slot["active"] for slot in self.slots)
        ended = any(
            run_id is not None and self.slots[index] and not self.slots[index]["active"]
            for index, run_id in enumerate(self._run_ids)
        )
        ended_slots = [
            index + 1
            for index, run_id in enumerate(self._run_ids)
            if run_id is not None
            and self.slots[index]
            and not self.slots[index]["active"]
        ]
        interval = self.active_record_interval if active else self.idle_record_interval
        if not ended and now - self._last_recorded_at < interval:
            return
        recorded_at = self.last_update or datetime.now(UTC).isoformat()
        self._run_ids = await asyncio.to_thread(
            self.measurement_store.record_snapshot,
            self.address,
            recorded_at,
            list(self.slots),
            self._run_ids,
            dict(self._profile_ids),
            dict(self._battery_ids),
        )
        if ended_slots:
            untracked_slots = [
                slot for slot in ended_slots if slot not in self._battery_ids
            ]
            if untracked_slots:
                await asyncio.to_thread(
                    self.profile_store.clear_assignments,
                    self.address,
                    untracked_slots,
                )
                await asyncio.to_thread(
                    self.profile_store.clear_slot_programs,
                    self.address,
                    untracked_slots,
                )
            for slot in untracked_slots:
                self._profile_ids.pop(slot, None)
                self._programs.pop(slot, None)
        self._last_recorded_at = now

    async def _reconcile_battery_presence(self) -> None:
        removed_slots: list[int] = []
        assigned_slots = set(self._battery_ids)
        for slot in list(self._battery_reference_voltage_v):
            if slot not in assigned_slots:
                self._reset_battery_presence_tracking(slot)

        for slot in sorted(assigned_slots):
            current = self.slots[slot - 1]
            if current is None:
                continue
            voltage_v = float(current.get("voltage_v", 0))
            if current.get("active"):
                if voltage_v > 0:
                    self._battery_reference_voltage_v[slot] = voltage_v
                self._battery_removal_counts.pop(slot, None)
                continue
            if voltage_v <= 0:
                removed_slots.append(slot)
                continue

            reference_v = self._battery_reference_voltage_v.get(slot)
            if reference_v is None or reference_v <= 0:
                self._battery_reference_voltage_v[slot] = voltage_v
                self._battery_removal_counts.pop(slot, None)
                continue

            significant_drop = voltage_v <= reference_v * BATTERY_REMOVAL_VOLTAGE_RATIO
            if significant_drop:
                confirmations = self._battery_removal_counts.get(slot, 0) + 1
                self._battery_removal_counts[slot] = confirmations
                if confirmations >= BATTERY_REMOVAL_CONFIRMATIONS:
                    removed_slots.append(slot)
                continue

            self._battery_removal_counts.pop(slot, None)

        if not removed_slots:
            return

        async with self._configuration_lock:
            removed_slots = [
                slot
                for slot in removed_slots
                if slot in self._battery_ids
                and (
                    float((self.slots[slot - 1] or {}).get("voltage_v", 0)) <= 0
                    or self._battery_removal_counts.get(slot, 0)
                    >= BATTERY_REMOVAL_CONFIRMATIONS
                )
            ]
            if not removed_slots:
                return
            await asyncio.to_thread(
                self.battery_store.clear_assignments,
                self.address,
                removed_slots,
            )
            await asyncio.to_thread(
                self.profile_store.clear_assignments,
                self.address,
                removed_slots,
            )
            await asyncio.to_thread(
                self.profile_store.clear_slot_programs,
                self.address,
                removed_slots,
            )
            for slot in removed_slots:
                battery_id = self._battery_ids.pop(slot, None)
                self._profile_ids.pop(slot, None)
                self._programs.pop(slot, None)
                self._reset_battery_presence_tracking(slot)
                LOGGER.info(
                    "%s: Batteriezuordnung %s in Slot %s nach Entnahmeerkennung gelöst",
                    self.address,
                    battery_id,
                    slot,
                )

    def _reset_battery_presence_tracking(self, slot: int) -> None:
        self._battery_reference_voltage_v.pop(slot, None)
        self._battery_removal_counts.pop(slot, None)

    def _on_notification(self, _sender: Any, data: bytearray) -> None:
        self._notifications.put_nowait(bytes(data))

    async def _disconnect(self) -> None:
        client = self.client
        characteristic = self.characteristic
        self.client = None
        self.characteristic = None
        if client is None:
            return
        if client.is_connected and characteristic is not None:
            with contextlib.suppress(Exception):
                await client.stop_notify(characteristic)
        if client.is_connected:
            with contextlib.suppress(Exception):
                await client.disconnect()

    async def _wait_for_wake(self, timeout: float) -> None:
        self._wake.clear()
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(timeout):
                await self._wake.wait()

    async def _notify_change(self) -> None:
        await self.on_change()

    @staticmethod
    def _require_slot(slot: int) -> None:
        if slot not in range(1, protocol.SLOT_COUNT + 1):
            raise ValueError("Slot muss zwischen 1 und 4 liegen")


class DeviceManager:
    def __init__(
        self,
        registry: DeviceRegistry,
        profile_store: ProfileStore,
        battery_store: BatteryStore,
        measurement_store: MeasurementStore,
        *,
        scan_timeout: float = 8,
        active_record_interval: float = 2,
        idle_record_interval: float = 30,
    ) -> None:
        self.registry = registry
        self.profile_store = profile_store
        self.battery_store = battery_store
        self.measurement_store = measurement_store
        self.scan_timeout = scan_timeout
        self.active_record_interval = active_record_interval
        self.idle_record_interval = idle_record_interval
        self.sessions: dict[str, DeviceSession] = {}
        self.discovered: dict[str, DiscoveredDevice] = {}
        self._ble_devices: dict[str, BLEDevice] = {}
        self._subscribers: set[asyncio.Queue] = set()
        self._scan_lock = asyncio.Lock()
        self._stop = asyncio.Event()
        self._scan_wake = asyncio.Event()
        self._scan_task: asyncio.Task | None = None

    async def start(self) -> None:
        for registration in self.registry.list():
            self._ensure_session(registration)
        try:
            await self.scan()
        except Exception as exc:  # noqa: BLE001 - startup continues without an adapter
            LOGGER.warning("Initial BLE scan failed: %s", _clean_error(exc))
            await self.publish()
        self._scan_task = asyncio.create_task(
            self._scan_loop(),
            name="mc3000-scanner",
        )

    async def stop(self) -> None:
        self._stop.set()
        self._scan_wake.set()
        if self._scan_task is not None:
            self._scan_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._scan_task
        await asyncio.gather(
            *(session.stop() for session in self.sessions.values()),
            return_exceptions=True,
        )

    async def scan(self) -> list[dict[str, Any]]:
        async with self._scan_lock:
            found = await BleakScanner.discover(
                timeout=self.scan_timeout,
                return_adv=True,
            )
            seen_at = datetime.now(UTC).isoformat()
            registrations = {device.address: device for device in self.registry.list()}

            for device, advertisement in found.values():
                if not _is_mc3000(device, advertisement):
                    continue
                address = normalize_address(device.address)
                name = advertisement.local_name or device.name or "MC3000"
                self._ble_devices[address] = device
                self.discovered[address] = DiscoveredDevice(
                    address=address,
                    name=name,
                    rssi=advertisement.rssi,
                    last_seen=seen_at,
                    registered=address in registrations,
                )
                session = self.sessions.get(address)
                if session is not None:
                    session.update_device(device)

            await self.publish()
            return self.discovered_snapshots()

    async def enroll(self, address: str, alias: str) -> dict[str, Any]:
        normalized = normalize_address(address)
        if normalized not in self.discovered:
            await self.scan()
        if normalized not in self.discovered:
            raise KeyError("MC3000 wurde beim Scan nicht gefunden")

        registration = self.registry.save(
            normalized, alias, enabled=True, released=False
        )
        session = self._ensure_session(registration)
        session.update_device(self._ble_devices[normalized])
        self.discovered[normalized].registered = True
        await self.publish()
        return session.snapshot()

    async def rename(self, address: str, alias: str) -> dict[str, Any]:
        registration = self.registry.get(address)
        if registration is None:
            raise KeyError(address)
        updated = self.registry.save(
            registration.address,
            alias,
            enabled=registration.enabled,
            released=registration.released,
            serial_number=registration.serial_number,
        )
        session = self._ensure_session(updated)
        session.update_registration(updated)
        await self.publish()
        return session.snapshot()

    async def update_details(
        self,
        address: str,
        *,
        alias: str,
        serial_number: str,
    ) -> dict[str, Any]:
        registration = self.registry.get(address)
        if registration is None:
            raise KeyError(address)
        updated = self.registry.save(
            registration.address,
            alias,
            enabled=registration.enabled,
            released=registration.released,
            serial_number=serial_number,
        )
        session = self._ensure_session(updated)
        session.update_registration(updated)
        await self.publish()
        return session.snapshot()

    async def set_released(self, address: str, released: bool) -> dict[str, Any]:
        updated = self.registry.set_released(address, released)
        session = self._ensure_session(updated)
        session.update_registration(updated)
        if not released:
            device = self._ble_devices.get(updated.address)
            if device is not None:
                session.update_device(device)
            self._scan_wake.set()
        await self.publish()
        return session.snapshot()

    async def remove(self, address: str) -> dict[str, Any]:
        normalized = normalize_address(address)
        registration = self.registry.get(normalized)
        if registration is None:
            raise KeyError(address)

        session = self.sessions.get(normalized)
        if session is not None and any(
            slot and slot.get("active")
            for slot in session.slots
        ):
            raise RuntimeError(
                "Ladegerät kann während eines laufenden Programms "
                "nicht entfernt werden"
            )

        if session is not None:
            await session.stop()
            self.sessions.pop(normalized, None)
        self.registry.delete(normalized)
        discovered = self.discovered.get(normalized)
        if discovered is not None:
            discovered.registered = False
        await self.publish()
        return {
            "address": normalized,
            "alias": registration.alias,
        }

    def get_session(self, address: str) -> DeviceSession:
        normalized = normalize_address(address)
        session = self.sessions.get(normalized)
        if session is None:
            raise KeyError(address)
        return session

    def snapshots(self) -> list[dict[str, Any]]:
        return [session.snapshot() for session in self.sessions.values()]

    def discovered_snapshots(self) -> list[dict[str, Any]]:
        return [device.to_dict() for device in self.discovered.values()]

    def payload(self) -> dict[str, Any]:
        return {
            "devices": self.snapshots(),
            "discovered": self.discovered_snapshots(),
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=1)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    async def publish(self) -> None:
        payload = self.payload()
        for queue in tuple(self._subscribers):
            if queue.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(payload)

    def _ensure_session(self, registration: RegisteredDevice) -> DeviceSession:
        session = self.sessions.get(registration.address)
        if session is None:
            session = DeviceSession(
                registration,
                self.publish,
                self.profile_store,
                self.battery_store,
                self.measurement_store,
                active_record_interval=self.active_record_interval,
                idle_record_interval=self.idle_record_interval,
            )
            self.sessions[registration.address] = session
            device = self._ble_devices.get(registration.address)
            if device is not None:
                session.update_device(device)
            session.start()
        else:
            session.update_registration(registration)
        return session

    async def _scan_loop(self) -> None:
        while not self._stop.is_set():
            connected = [
                session.connected
                for session in self.sessions.values()
                if session.registration.enabled and not session.registration.released
            ]
            delay = 120 if connected and all(connected) else 15
            self._scan_wake.clear()
            with contextlib.suppress(TimeoutError):
                async with asyncio.timeout(delay):
                    await self._scan_wake.wait()
            if self._stop.is_set():
                return
            try:
                await self.scan()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - scanner retries after any backend error
                LOGGER.warning("BLE scan failed: %s", _clean_error(exc))


def _is_mc3000(device: BLEDevice, advertisement: AdvertisementData) -> bool:
    name = advertisement.local_name or device.name or ""
    services = {value.lower() for value in advertisement.service_uuids}
    return name in protocol.DEVICE_NAMES or protocol.SERVICE_UUID in services


def _clean_error(error: Exception) -> str:
    text = str(error).strip()
    return text or error.__class__.__name__


def _slot_snapshot(slot: dict[str, Any] | None) -> dict[str, Any] | None:
    if slot is None:
        return None
    snapshot = dict(slot)
    current = abs(float(snapshot.get("current_a") or 0))
    status_code = snapshot.get("status_code")
    if status_code in (0, 4):
        snapshot["current_a"] = 0.0
    else:
        snapshot["current_a"] = -current if status_code == 2 and current else current
    return snapshot
