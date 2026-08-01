from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from .protocol import BATTERY_TYPES, PROFILE_SIZE, Opcode, ProtocolError

CHARGE_VOLTAGE_MIN_MV = (4000, 3400, 4100, 1470, 1470, 1850, 1470, 1400, 2600, 3200)
CHARGE_VOLTAGE_MAX_MV = (4250, 3650, 4400, 1800, 1800, 1950, 1800, 1700, 2900, 4150)
CHARGE_VOLTAGE_DEFAULT_MV = (
    4200,
    3600,
    4350,
    1650,
    1650,
    1900,
    1650,
    1650,
    2850,
    4000,
)
DISCHARGE_VOLTAGE_MIN_MV = (
    2500,
    2000,
    2650,
    500,
    500,
    1000,
    500,
    500,
    1500,
    1500,
)
DISCHARGE_VOLTAGE_MAX_MV = (
    3650,
    3150,
    3750,
    1100,
    1100,
    1300,
    1000,
    1300,
    2250,
    3500,
)
DISCHARGE_VOLTAGE_DEFAULT_MV = (
    3000,
    2900,
    3300,
    1000,
    1000,
    1200,
    900,
    900,
    1800,
    2000,
)
KEEP_VOLTAGE_MIN_MV = (3980, 3380, 4080, 1300, 1300, 1500, 1300, 1400, 2580, 3980)
KEEP_VOLTAGE_MAX_MV = (4180, 3580, 4330, 1450, 1450, 1880, 1450, 1500, 2830, 4180)
KEEP_VOLTAGE_DEFAULT_MV = (
    4150,
    3550,
    4250,
    1350,
    1350,
    1600,
    1350,
    1450,
    2700,
    4150,
)
STORAGE_VOLTAGE_RANGES_MV = {
    0: (3650, 4000, 3800),
    1: (3150, 3400, 3300),
    2: (3750, 4100, 3900),
    8: (2250, 2600, 2400),
}
CHARGE_CURRENT_MIN_MA = 50
CHARGE_CURRENT_MAX_MA = 3000
DISCHARGE_CURRENT_MIN_MA = 50
DISCHARGE_CURRENT_MAX_MA = 2000
CURRENT_STEP_MA = 10
TIME_LIMIT_MODES = frozenset({"automatic", "manual", "off"})
AUTOMATIC_TIME_LIMIT_FACTOR = 1.5
DEFAULT_MANUAL_TIME_LIMIT_MIN = 360

LITHIUM_TYPES = frozenset({0, 1, 2, 8, 9})
SHORT_MODE_TYPES = frozenset({5, 7})
NICKEL_TYPES = frozenset({3, 4, 6})

MODES_BY_TYPE = {
    "lithium": {0: "Laden", 1: "Refresh", 2: "Lagern", 3: "Entladen", 4: "Zyklus"},
    "short": {0: "Laden", 1: "Refresh", 2: "Entladen", 3: "Zyklus"},
    "nickel": {0: "Laden", 1: "Refresh", 2: "Break-in", 3: "Entladen", 4: "Zyklus"},
}


class ProfileError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ProfileValues:
    name: str
    description: str
    battery_type_code: int
    mode_code: int
    capacity_mah: int
    charge_current_ma: int
    discharge_current_ma: int
    charge_voltage_mv: int
    discharge_voltage_mv: int
    charge_end_current_ma: int
    discharge_end_current_ma: int
    charge_rest_min: int
    discharge_rest_min: int
    cycle_count: int
    cycle_mode: int
    delta_peak_mv: int
    trickle_current_ma: int
    keep_voltage_mv: int
    temp_limit_c: int
    time_limit_min: int
    time_limit_mode: str = "manual"

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> ProfileValues:
        return cls(**{field: values[field] for field in cls.__dataclass_fields__})

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["battery_type"] = BATTERY_TYPES[self.battery_type_code]
        result["mode"] = mode_name(self.battery_type_code, self.mode_code)
        result["effective_time_limit_min"] = effective_time_limit_min(self)
        return result


def mode_options(battery_type_code: int) -> dict[int, str]:
    if battery_type_code in LITHIUM_TYPES:
        return MODES_BY_TYPE["lithium"]
    if battery_type_code in SHORT_MODE_TYPES:
        return MODES_BY_TYPE["short"]
    return MODES_BY_TYPE["nickel"]


def mode_name(battery_type_code: int, mode_code: int) -> str:
    return mode_options(battery_type_code).get(mode_code, f"Unbekannt ({mode_code})")


def voltage_limits(battery_type_code: int, mode_code: int) -> dict[str, int]:
    _require_battery_type(battery_type_code)
    charge_min = CHARGE_VOLTAGE_MIN_MV[battery_type_code]
    charge_max = CHARGE_VOLTAGE_MAX_MV[battery_type_code]
    charge_default = CHARGE_VOLTAGE_DEFAULT_MV[battery_type_code]
    if mode_code == 2 and battery_type_code in STORAGE_VOLTAGE_RANGES_MV:
        charge_min, charge_max, charge_default = STORAGE_VOLTAGE_RANGES_MV[
            battery_type_code
        ]
    return {
        "charge_min_mv": charge_min,
        "charge_max_mv": charge_max,
        "charge_default_mv": charge_default,
        "discharge_min_mv": DISCHARGE_VOLTAGE_MIN_MV[battery_type_code],
        "discharge_max_mv": DISCHARGE_VOLTAGE_MAX_MV[battery_type_code],
        "discharge_default_mv": DISCHARGE_VOLTAGE_DEFAULT_MV[battery_type_code],
        "keep_min_mv": KEEP_VOLTAGE_MIN_MV[battery_type_code],
        "keep_max_mv": KEEP_VOLTAGE_MAX_MV[battery_type_code],
        "keep_default_mv": KEEP_VOLTAGE_DEFAULT_MV[battery_type_code],
    }


def validate_profile(profile: ProfileValues) -> None:
    name = profile.name.strip()
    if not name or len(name) > 80:
        raise ProfileError("Profilname muss zwischen 1 und 80 Zeichen lang sein")
    if len(profile.description) > 500:
        raise ProfileError("Beschreibung darf höchstens 500 Zeichen lang sein")

    _require_battery_type(profile.battery_type_code)
    if profile.mode_code not in mode_options(profile.battery_type_code):
        raise ProfileError("Programm passt nicht zum gewählten Akkutyp")

    _range("Kapazität", profile.capacity_mah, 0, 50000)
    if (
        profile.battery_type_code in NICKEL_TYPES
        and profile.mode_code == 2
        and profile.capacity_mah < 100
    ):
        raise ProfileError("Break-in benötigt mindestens 100 mAh Kapazität")

    _range(
        "Ladestrom",
        profile.charge_current_ma,
        CHARGE_CURRENT_MIN_MA,
        CHARGE_CURRENT_MAX_MA,
    )
    _range(
        "Entladestrom",
        profile.discharge_current_ma,
        DISCHARGE_CURRENT_MIN_MA,
        DISCHARGE_CURRENT_MAX_MA,
    )
    limits = voltage_limits(profile.battery_type_code, profile.mode_code)
    _range(
        "Lade-Endspannung",
        profile.charge_voltage_mv,
        limits["charge_min_mv"],
        limits["charge_max_mv"],
    )
    _range(
        "Entlade-Endspannung",
        profile.discharge_voltage_mv,
        limits["discharge_min_mv"],
        limits["discharge_max_mv"],
    )
    _range(
        "Lade-Abschaltstrom",
        profile.charge_end_current_ma,
        0,
        profile.charge_current_ma,
    )
    _range(
        "Entlade-Abschaltstrom",
        profile.discharge_end_current_ma,
        0,
        profile.discharge_current_ma,
    )
    if profile.battery_type_code == 9 and (
        profile.charge_end_current_ma == 0 or profile.discharge_end_current_ma == 0
    ):
        raise ProfileError("Na-Ion erlaubt keinen Abschaltstrom von 0 mA")

    _range("Ladepause", profile.charge_rest_min, 0, 240)
    _range("Entladepause", profile.discharge_rest_min, 0, 240)
    _range("Zykluszahl", profile.cycle_count, 1, 99)
    _range("Zyklusfolge", profile.cycle_mode, 0, 3)
    if (
        profile.battery_type_code in NICKEL_TYPES
        and profile.mode_code == 2
        and profile.cycle_mode not in (0, 1)
    ):
        raise ProfileError("Break-in erlaubt nur C>D>C oder D>C>D")

    _range("Delta-Peak", profile.delta_peak_mv, 0, 20)
    _range("Erhaltungsstrom", profile.trickle_current_ma, 0, 300)
    if profile.trickle_current_ma % 10:
        raise ProfileError("Erhaltungsstrom muss in 10-mA-Schritten angegeben werden")
    if profile.battery_type_code not in NICKEL_TYPES and (
        profile.delta_peak_mv or profile.trickle_current_ma
    ):
        raise ProfileError("Delta-Peak und Erhaltungsstrom sind nur für Nickel-Akkus")

    if profile.keep_voltage_mv:
        _range(
            "Erhaltungsspannung",
            profile.keep_voltage_mv,
            limits["keep_min_mv"],
            limits["keep_max_mv"],
        )
    if profile.temp_limit_c and not 20 <= profile.temp_limit_c <= 70:
        raise ProfileError("Temperaturlimit muss aus oder zwischen 20 und 70 Grad sein")
    if profile.time_limit_mode not in TIME_LIMIT_MODES:
        raise ProfileError("Zeitlimit-Modus muss automatisch, manuell oder aus sein")
    _range("Zeitlimit", profile.time_limit_min, 0, 1440)
    if profile.time_limit_mode == "manual" and profile.time_limit_min == 0:
        raise ProfileError("Manuelles Zeitlimit muss mindestens eine Minute betragen")
    if profile.time_limit_mode == "automatic" and profile.capacity_mah <= 0:
        raise ProfileError("Automatisches Zeitlimit benötigt eine Akkukapazität")


def effective_time_limit_min(profile: ProfileValues) -> int:
    if profile.time_limit_mode == "off":
        return 0
    if profile.time_limit_mode == "manual":
        return profile.time_limit_min

    charge_phases, discharge_phases, use_longest_phase = _time_limit_phases(profile)
    charge_minutes = (
        profile.capacity_mah / profile.charge_current_ma * 60
        if charge_phases
        else 0
    )
    discharge_minutes = (
        profile.capacity_mah / profile.discharge_current_ma * 60
        if discharge_phases
        else 0
    )
    if use_longest_phase:
        duration_min = max(charge_minutes, discharge_minutes)
    else:
        duration_min = (
            charge_phases * charge_minutes
            + discharge_phases * discharge_minutes
        )
    duration_min *= AUTOMATIC_TIME_LIMIT_FACTOR
    duration_min += _automatic_rest_time_min(
        profile,
        charge_phases,
        discharge_phases,
    )
    return max(1, min(1440, math.ceil(duration_min)))


def _time_limit_phases(profile: ProfileValues) -> tuple[int, int, bool]:
    mode = mode_name(profile.battery_type_code, profile.mode_code)
    if mode == "Laden":
        return 1, 0, False
    if mode == "Entladen":
        return 0, 1, False
    if mode == "Lagern":
        return 1, 1, True
    if mode == "Refresh":
        return 2, 1, False
    if mode in {"Zyklus", "Break-in"}:
        cycle_count = profile.cycle_count
        if profile.cycle_mode == 1:
            return cycle_count + 1, cycle_count, False
        if profile.cycle_mode == 3:
            return cycle_count, cycle_count + 1, False
        return cycle_count, cycle_count, False
    return 1, 0, False


def _automatic_rest_time_min(
    profile: ProfileValues,
    charge_phases: int,
    discharge_phases: int,
) -> int:
    phase_count = charge_phases + discharge_phases
    if phase_count <= 1:
        return 0
    return (phase_count - 1) * max(
        profile.charge_rest_min,
        profile.discharge_rest_min,
    )


def build_profile_packet(profile: ProfileValues, slot_mask: int) -> bytes:
    validate_profile(profile)
    if not 1 <= slot_mask <= 0x0F:
        raise ProtocolError("Slot-Maske muss zwischen 1 und 15 liegen")

    packet = bytearray(PROFILE_SIZE)
    packet[0] = 0x0F
    packet[1] = int(Opcode.SET_PROFILE)
    packet[2] = slot_mask
    packet[3] = profile.battery_type_code
    packet[4] = profile.mode_code
    _put_u16(packet, 5, profile.capacity_mah)
    _put_u16(packet, 7, profile.charge_current_ma)
    _put_u16(packet, 9, profile.discharge_current_ma)
    _put_u16(packet, 11, profile.charge_voltage_mv)
    _put_u16(packet, 13, profile.discharge_voltage_mv)

    charge_end = profile.charge_end_current_ma
    discharge_end = profile.discharge_end_current_ma
    if profile.mode_code in (1, 4):
        charge_end = charge_end or profile.charge_current_ma
        discharge_end = discharge_end or profile.discharge_current_ma
    _put_u16(packet, 15, charge_end)
    _put_u16(packet, 17, discharge_end)

    packet[19] = profile.charge_rest_min
    packet[20] = profile.cycle_count
    packet[21] = profile.cycle_mode
    if profile.battery_type_code in NICKEL_TYPES:
        packet[22] = profile.delta_peak_mv
        packet[23] = profile.trickle_current_ma // 10
    _put_u16(packet, 24, profile.keep_voltage_mv)
    packet[26] = profile.temp_limit_c
    _put_u16(
        packet,
        27,
        0
        if profile.mode_code == 2 and profile.battery_type_code in NICKEL_TYPES
        else effective_time_limit_min(profile),
    )
    packet[29] = profile.discharge_rest_min
    packet[39] = sum(packet[:39]) & 0xFF
    return bytes(packet)


def profile_options_payload() -> dict[str, Any]:
    batteries = []
    for code, name in BATTERY_TYPES.items():
        limits = voltage_limits(code, 0)
        batteries.append(
            {
                "code": code,
                "name": name,
                "modes": [
                    {"code": mode_code, "name": label}
                    for mode_code, label in mode_options(code).items()
                ],
                "defaults": limits,
                "nickel": code in NICKEL_TYPES,
            }
        )
    return {
        "battery_types": batteries,
        "time_limit_modes": [
            {"value": "automatic", "label": "Automatisch"},
            {"value": "manual", "label": "Manuell"},
            {"value": "off", "label": "Aus"},
        ],
        "automatic_time_limit_factor": AUTOMATIC_TIME_LIMIT_FACTOR,
        "default_manual_time_limit_min": DEFAULT_MANUAL_TIME_LIMIT_MIN,
    }


def _require_battery_type(value: int) -> None:
    if value not in BATTERY_TYPES:
        raise ProfileError("Unbekannter Akkutyp")


def _range(name: str, value: int, minimum: int, maximum: int) -> None:
    if not minimum <= value <= maximum:
        raise ProfileError(f"{name} muss zwischen {minimum} und {maximum} liegen")


def _put_u16(target: bytearray, index: int, value: int) -> None:
    if not 0 <= value <= 0xFFFF:
        raise ProtocolError("16-Bit-Wert liegt ausserhalb des gültigen Bereichs")
    target[index] = value >> 8
    target[index + 1] = value & 0xFF
