from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import IntEnum
from typing import Any

SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
CHARACTERISTIC_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"
DEVICE_NAMES = frozenset({"Charger", "SimpleBLEPeripheral", "HitecCharger"})

FRAME_SIZE = 20
PROFILE_SIZE = 40
CURVE_SIZE = 245
SLOT_COUNT = 4


class Opcode(IntEnum):
    START = 0x05
    SET_PROFILE = 0x11
    STATUS = 0x55
    VOLTAGE_CURVE = 0x56
    VERSION = 0x57
    GET_BASIC = 0x61
    SET_BASIC = 0x63
    STOP = 0xFE


BATTERY_TYPES = {
    0: "Li-Ion",
    1: "LiFePO4",
    2: "Li-Ion 4,35 V",
    3: "NiMH",
    4: "NiCd",
    5: "NiZn",
    6: "Eneloop",
    7: "RAM",
    8: "LTO",
    9: "Na-Ion",
}

STATUS_NAMES = {
    0: "Bereit",
    1: "Laden",
    2: "Entladen",
    3: "Pause",
    4: "Fertig",
    128: "Eingangsspannung zu niedrig",
    129: "Eingangsspannung zu hoch",
    130: "MCP3424-1 Fehler",
    131: "MCP3424-2 Fehler",
    132: "Kontakt unterbrochen",
    133: "Spannung prüfen",
    134: "Kapazitätslimit",
    135: "Zeitlimit",
    136: "Gerätetemperatur zu hoch",
    137: "Akkutemperatur zu hoch",
    138: "Kurzschluss",
    139: "Verpolung",
}

ACTIVE_STATUS_CODES = frozenset({1, 2, 3})
LITHIUM_TYPE_CODES = frozenset({0, 1, 2, 8, 9})


class ProtocolError(ValueError):
    pass


@dataclass(slots=True)
class VersionInfo:
    firmware: str
    hardware: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BasicData:
    temperature_unit: str
    system_beep: bool
    display_mode: int
    screensaver: bool
    fan_mode: int
    input_voltage_v: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SlotStatus:
    slot: int
    battery_type_code: int
    battery_type: str
    mode_code: int
    mode: str
    cycle_count: int
    status_code: int
    status: str
    active: bool
    time_s: int
    voltage_v: float
    current_a: float
    capacity_mah: int
    temperature_c: int
    resistance_mohm: int
    led_mask: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def checksum(data: bytes | bytearray) -> int:
    return sum(data) & 0xFF


def make_frame(opcode: int | Opcode, payload: bytes = b"") -> bytes:
    if len(payload) > FRAME_SIZE - 3:
        raise ProtocolError("Nutzdaten sind für ein MC3000-Paket zu lang")

    frame = bytearray(FRAME_SIZE)
    frame[0] = 0x0F
    frame[1] = int(opcode) & 0xFF
    frame[2 : 2 + len(payload)] = payload
    frame[-1] = checksum(frame[:-1])
    return bytes(frame)


def command_status(slot: int) -> bytes:
    _validate_slot(slot)
    return make_frame(Opcode.STATUS, bytes([slot]))


def command_version(mac_address: str | None = None) -> bytes:
    frame = bytearray(make_frame(Opcode.VERSION))
    if mac_address:
        parts = mac_address.split(":")
        if len(parts) != 6:
            raise ProtocolError("Ungültige Bluetooth-Adresse")
        frame[3:9] = bytes(int(part, 16) for part in reversed(parts))
        frame[-1] = checksum(frame[:-1])
    return bytes(frame)


def command_basic() -> bytes:
    return make_frame(Opcode.GET_BASIC)


def command_curve(slot: int) -> bytes:
    _validate_slot(slot)
    return make_frame(Opcode.VOLTAGE_CURVE, bytes([slot]))


def command_start(slot_mask: int) -> bytes:
    _validate_slot_mask(slot_mask)
    return make_frame(Opcode.START, bytes([slot_mask]))


def command_stop(slot_mask: int) -> bytes:
    _validate_slot_mask(slot_mask)
    return make_frame(Opcode.STOP, bytes([slot_mask]))


def parse_version(frame: bytes) -> VersionInfo:
    _require_frame(frame, Opcode.VERSION, verify_checksum=False)
    return VersionInfo(
        firmware=f"{frame[14]}.{frame[15]:02d}",
        hardware=f"{frame[16] // 10}.{frame[16] % 10}",
    )


def parse_basic(frame: bytes) -> BasicData:
    _require_frame(frame, Opcode.GET_BASIC)
    return BasicData(
        temperature_unit="C" if frame[2] == 0 else "F",
        system_beep=bool(frame[3]),
        display_mode=frame[4],
        screensaver=bool(frame[5]),
        fan_mode=frame[6],
        input_voltage_v=round(_u16(frame, 7) / 1000, 3),
    )


def parse_slot(frame: bytes) -> SlotStatus:
    _require_frame(frame, Opcode.STATUS)
    slot = frame[2]
    _validate_slot(slot)
    battery_type_code = frame[3]
    mode_code = frame[4]
    status_code = frame[6]
    return SlotStatus(
        slot=slot + 1,
        battery_type_code=battery_type_code,
        battery_type=BATTERY_TYPES.get(
            battery_type_code, f"Unbekannt ({battery_type_code})"
        ),
        mode_code=mode_code,
        mode=mode_name(mode_code, battery_type_code),
        cycle_count=frame[5],
        status_code=status_code,
        status=STATUS_NAMES.get(status_code, f"Fehler {status_code}"),
        active=status_code in ACTIVE_STATUS_CODES,
        time_s=_u16(frame, 7),
        voltage_v=round(_u16(frame, 9) / 1000, 3),
        current_a=round(_u16(frame, 11) / 1000, 3),
        capacity_mah=_u16(frame, 13),
        temperature_c=frame[15],
        resistance_mohm=_u16(frame, 16),
        led_mask=frame[18],
    )


def parse_curve(data: bytes) -> dict[str, Any]:
    if len(data) < CURVE_SIZE:
        raise ProtocolError(
            f"Spannungskurve ist unvollständig: {len(data)} von {CURVE_SIZE} Byte"
        )
    if data[0] != 0x0F or data[1] != Opcode.VOLTAGE_CURVE:
        raise ProtocolError("Unerwartete Antwort auf Spannungskurven-Abfrage")

    slot = data[2]
    _validate_slot(slot)
    interval_s = _u16(data, 3)
    points_mv = [_u16(data, index - 1) for index in range(6, CURVE_SIZE, 2)]
    points = [
        {
            "index": index,
            "time_s": index * interval_s,
            "voltage_v": round(value / 1000, 3),
        }
        for index, value in enumerate(points_mv)
        if value > 0
    ]
    return {
        "slot": slot + 1,
        "interval_s": interval_s,
        "points": points,
    }


def mode_name(mode_code: int, battery_type_code: int) -> str:
    if mode_code == 0:
        return "Laden"
    if mode_code == 1:
        return "Refresh"
    if mode_code == 2:
        if battery_type_code in {5, 7}:
            return "Entladen"
        return "Lagern" if battery_type_code in LITHIUM_TYPE_CODES else "Break-in"
    if mode_code == 3:
        if battery_type_code in {5, 7}:
            return "Zyklus"
        return "Entladen"
    if mode_code == 4:
        return "Zyklus"
    return f"Unbekannt ({mode_code})"


def _require_frame(
    frame: bytes,
    opcode: int | Opcode,
    *,
    verify_checksum: bool = True,
) -> None:
    if len(frame) < FRAME_SIZE:
        raise ProtocolError(f"Antwort ist zu kurz: {len(frame)} Byte")
    if frame[0] != 0x0F:
        raise ProtocolError("Ungültiger Paketanfang")
    if frame[1] != int(opcode):
        raise ProtocolError(
            f"Unerwarteter Befehl 0x{frame[1]:02X}, erwartet 0x{int(opcode):02X}"
        )
    if verify_checksum and frame[-1] != checksum(frame[:-1]):
        raise ProtocolError("Ungültige Prüfsumme")


def _validate_slot(slot: int) -> None:
    if slot not in range(SLOT_COUNT):
        raise ProtocolError("Slot muss zwischen 0 und 3 liegen")


def _validate_slot_mask(slot_mask: int) -> None:
    if not 1 <= slot_mask <= 0x0F:
        raise ProtocolError("Slot-Maske muss zwischen 1 und 15 liegen")


def _u16(data: bytes | bytearray, index: int) -> int:
    return ((data[index] & 0xFF) << 8) | (data[index + 1] & 0xFF)
