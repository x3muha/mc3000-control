from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, replace
from datetime import date
from typing import Any
from urllib.parse import urlsplit

from .profiles import (
    CHARGE_CURRENT_MAX_MA,
    CHARGE_CURRENT_MIN_MA,
    CURRENT_STEP_MA,
    DEFAULT_MANUAL_TIME_LIMIT_MIN,
    DISCHARGE_CURRENT_MAX_MA,
    DISCHARGE_CURRENT_MIN_MA,
    TIME_LIMIT_MODES,
    ProfileValues,
    effective_time_limit_min,
)
from .protocol import BATTERY_TYPES

MANAGED_BATTERY_TYPES = {
    0: "Li-Ion",
    1: "LiFePO4",
}
STANDARD_MODES = {
    0: "Laden",
    1: "Refresh",
    3: "Kapazitätstest (Entladen)",
    4: "Zyklus",
}
AUTOMATIC_PROGRAMS = {
    "gentle_charge": {
        "label": "Schonend laden",
        "description": "Lädt mit 0,5 C.",
        "mode_code": 0,
        "charge_c_rate": 0.5,
        "discharge_c_rate": 1.0,
        "cycle_count": 1,
        "cycle_mode": 0,
        "charge_rest_min": 0,
        "discharge_rest_min": 0,
        "temp_limit_c": 45,
        "time_limit_mode": "manual",
        "time_limit_min": DEFAULT_MANUAL_TIME_LIMIT_MIN,
    },
    "standard_charge": {
        "label": "Standard laden",
        "description": "Lädt mit 1 C.",
        "mode_code": 0,
        "charge_c_rate": 1.0,
        "discharge_c_rate": 1.0,
        "cycle_count": 1,
        "cycle_mode": 0,
        "charge_rest_min": 0,
        "discharge_rest_min": 0,
        "temp_limit_c": 45,
        "time_limit_mode": "manual",
        "time_limit_min": DEFAULT_MANUAL_TIME_LIMIT_MIN,
    },
    "capacity_test": {
        "label": "Kapazitätstest",
        "description": "Entlädt mit 1 C und zeichnet die entnommene Kapazität auf.",
        "mode_code": 3,
        "charge_c_rate": 0.5,
        "discharge_c_rate": 1.0,
        "cycle_count": 1,
        "cycle_mode": 0,
        "charge_rest_min": 0,
        "discharge_rest_min": 0,
        "temp_limit_c": 45,
        "time_limit_mode": "manual",
        "time_limit_min": DEFAULT_MANUAL_TIME_LIMIT_MIN,
    },
    "refresh": {
        "label": "Refresh",
        "description": (
            "Lädt mit 0,5 C, entlädt mit 1 C und lädt danach erneut."
        ),
        "mode_code": 1,
        "charge_c_rate": 0.5,
        "discharge_c_rate": 1.0,
        "cycle_count": 1,
        "cycle_mode": 0,
        "charge_rest_min": 5,
        "discharge_rest_min": 5,
        "temp_limit_c": 45,
        "time_limit_mode": "manual",
        "time_limit_min": DEFAULT_MANUAL_TIME_LIMIT_MIN,
    },
    "cycle": {
        "label": "Zyklus C-D-C",
        "description": "Lädt mit 0,5 C, entlädt mit 1 C und lädt erneut.",
        "mode_code": 4,
        "charge_c_rate": 0.5,
        "discharge_c_rate": 1.0,
        "cycle_count": 1,
        "cycle_mode": 1,
        "charge_rest_min": 5,
        "discharge_rest_min": 5,
        "temp_limit_c": 45,
        "time_limit_mode": "manual",
        "time_limit_min": DEFAULT_MANUAL_TIME_LIMIT_MIN,
    },
}
BATTERY_CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
AUTOMATIC_PROGRAM_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")


class BatteryError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AutomaticProgramValues:
    label: str
    description: str
    mode_code: int
    charge_c_rate: float
    discharge_c_rate: float
    cycle_count: int
    cycle_mode: int
    charge_rest_min: int = 0
    discharge_rest_min: int = 0
    temp_limit_c: int = 45
    time_limit_mode: str = "manual"
    time_limit_min: int = DEFAULT_MANUAL_TIME_LIMIT_MIN

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> AutomaticProgramValues:
        return cls(
            **{
                field: values[field]
                for field in cls.__dataclass_fields__
                if field in values
            }
        )

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["mode"] = STANDARD_MODES.get(
            self.mode_code,
            f"Unbekannt ({self.mode_code})",
        )
        return result


@dataclass(frozen=True, slots=True)
class BatteryValues:
    code: str
    name: str
    battery_type_code: int
    nominal_capacity_mah: int
    notes: str
    manufacturer: str = ""
    model: str = ""
    form_factor: str = ""
    origin: str = ""
    in_service_since: str = ""
    protected: bool = False
    chemistry_detail: str = ""
    weight_g: float | None = None
    nominal_voltage_v: float | None = None
    min_voltage_v: float | None = None
    max_voltage_v: float | None = None
    max_charge_current_a: float | None = None
    max_discharge_current_a: float | None = None
    cycle_life: int | None = None
    manufacture_year: int | None = None
    dimensions: str = ""
    data_source_name: str = ""
    data_source_url: str = ""
    data_source_retrieved_at: str = ""
    technical_notes: str = ""
    technical_data: dict[str, str] = field(default_factory=dict)
    standard_mode_code: int = 0
    standard_charge_c_rate: float = 0.5
    standard_discharge_c_rate: float = 0.5
    standard_cycle_count: int = 1
    standard_cycle_mode: int = 0
    standard_time_limit_mode: str = "manual"
    standard_time_limit_min: int = DEFAULT_MANUAL_TIME_LIMIT_MIN
    archived: bool = False

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["battery_type"] = BATTERY_TYPES[self.battery_type_code]
        result["standard_program"] = {
            "mode_code": self.standard_mode_code,
            "mode": STANDARD_MODES[self.standard_mode_code],
            "charge_c_rate": self.standard_charge_c_rate,
            "discharge_c_rate": self.standard_discharge_c_rate,
            "cycle_count": self.standard_cycle_count,
            "cycle_mode": self.standard_cycle_mode,
            "time_limit_mode": self.standard_time_limit_mode,
            "time_limit_min": self.standard_time_limit_min,
        }
        return result


def normalize_battery_code(value: str) -> str:
    code = value.strip().upper()
    if not BATTERY_CODE_PATTERN.fullmatch(code):
        raise BatteryError(
            "Batterienummer darf nur Buchstaben, Zahlen, Punkt, Minus und "
            "Unterstrich enthalten"
        )
    return code


def validate_battery(values: BatteryValues) -> BatteryValues:
    code = normalize_battery_code(values.code)
    name = values.name.strip()
    notes = values.notes.strip()
    manufacturer = values.manufacturer.strip()
    model = values.model.strip()
    form_factor = values.form_factor.strip()
    origin = values.origin.strip()
    in_service_since = values.in_service_since.strip()
    chemistry_detail = values.chemistry_detail.strip()
    dimensions = values.dimensions.strip()
    data_source_name = values.data_source_name.strip()
    data_source_url = values.data_source_url.strip()
    data_source_retrieved_at = values.data_source_retrieved_at.strip()
    technical_notes = values.technical_notes.strip()
    if len(name) > 80:
        raise BatteryError("Batteriename darf höchstens 80 Zeichen lang sein")
    if len(manufacturer) > 80:
        raise BatteryError("Hersteller darf höchstens 80 Zeichen lang sein")
    if len(model) > 80:
        raise BatteryError("Typ oder Modell darf höchstens 80 Zeichen lang sein")
    if len(form_factor) > 40:
        raise BatteryError("Bauform darf höchstens 40 Zeichen lang sein")
    if len(origin) > 120:
        raise BatteryError("Herkunft darf höchstens 120 Zeichen lang sein")
    if len(chemistry_detail) > 80:
        raise BatteryError("Chemiedetail darf höchstens 80 Zeichen lang sein")
    if len(dimensions) > 120:
        raise BatteryError("Abmessungen dürfen höchstens 120 Zeichen lang sein")
    if len(data_source_name) > 120:
        raise BatteryError("Datenquelle darf höchstens 120 Zeichen lang sein")
    if len(data_source_url) > 1000:
        raise BatteryError("Quellenlink darf höchstens 1000 Zeichen lang sein")
    if data_source_url and urlsplit(data_source_url).scheme not in {"http", "https"}:
        raise BatteryError("Quellenlink muss mit http:// oder https:// beginnen")
    if len(data_source_retrieved_at) > 40:
        raise BatteryError("Abrufzeit der Datenquelle ist ungültig")
    if len(technical_notes) > 4000:
        raise BatteryError(
            "Technische Zusatzangaben dürfen höchstens 4000 Zeichen lang sein"
        )
    if in_service_since:
        try:
            date.fromisoformat(in_service_since)
        except ValueError as exc:
            raise BatteryError(
                "Datum muss ein gültiges Datum im Format JJJJ-MM-TT sein"
            ) from exc
    if values.battery_type_code not in MANAGED_BATTERY_TYPES:
        raise BatteryError("Standardprogramme unterstützen Li-Ion und LiFePO4")
    if not 100 <= values.nominal_capacity_mah <= 50000:
        raise BatteryError("Nennkapazität muss zwischen 100 und 50000 mAh liegen")
    if len(notes) > 1000:
        raise BatteryError("Notizen dürfen höchstens 1000 Zeichen lang sein")
    weight_g = _optional_number(
        values.weight_g,
        "Gewicht",
        minimum=0.01,
        maximum=100000,
    )
    nominal_voltage_v = _optional_number(
        values.nominal_voltage_v,
        "Nennspannung",
        minimum=0.01,
        maximum=20,
    )
    min_voltage_v = _optional_number(
        values.min_voltage_v,
        "Minimale Spannung",
        minimum=0,
        maximum=20,
    )
    max_voltage_v = _optional_number(
        values.max_voltage_v,
        "Maximale Spannung",
        minimum=0.01,
        maximum=20,
    )
    max_charge_current_a = _optional_number(
        values.max_charge_current_a,
        "Maximaler Ladestrom",
        minimum=0,
        maximum=1000,
    )
    max_discharge_current_a = _optional_number(
        values.max_discharge_current_a,
        "Maximaler Entladestrom",
        minimum=0,
        maximum=1000,
    )
    cycle_life = _optional_integer(
        values.cycle_life,
        "Zyklenlebensdauer",
        minimum=1,
        maximum=1_000_000,
    )
    manufacture_year = _optional_integer(
        values.manufacture_year,
        "Herstellungsjahr",
        minimum=1900,
        maximum=2100,
    )
    if len(values.technical_data) > 100:
        raise BatteryError("Es sind höchstens 100 technische Datenfelder erlaubt")
    technical_data: dict[str, str] = {}
    for raw_key, raw_value in values.technical_data.items():
        key = str(raw_key).strip()
        value = str(raw_value).strip()
        if not key or not value:
            continue
        if len(key) > 120:
            raise BatteryError(
                "Bezeichnung eines technischen Datenfelds ist zu lang"
            )
        if len(value) > 2000:
            raise BatteryError("Wert eines technischen Datenfelds ist zu lang")
        technical_data[key] = value
    _validate_standard_settings(
        mode_code=values.standard_mode_code,
        charge_c_rate=values.standard_charge_c_rate,
        discharge_c_rate=values.standard_discharge_c_rate,
        cycle_count=values.standard_cycle_count,
        cycle_mode=values.standard_cycle_mode,
    )
    _validate_time_limit_settings(
        values.standard_time_limit_mode,
        values.standard_time_limit_min,
    )
    return BatteryValues(
        code=code,
        name=name,
        battery_type_code=values.battery_type_code,
        nominal_capacity_mah=values.nominal_capacity_mah,
        notes=notes,
        manufacturer=manufacturer,
        model=model,
        form_factor=form_factor,
        origin=origin,
        in_service_since=in_service_since,
        protected=bool(values.protected),
        chemistry_detail=chemistry_detail,
        weight_g=weight_g,
        nominal_voltage_v=nominal_voltage_v,
        min_voltage_v=min_voltage_v,
        max_voltage_v=max_voltage_v,
        max_charge_current_a=max_charge_current_a,
        max_discharge_current_a=max_discharge_current_a,
        cycle_life=cycle_life,
        manufacture_year=manufacture_year,
        dimensions=dimensions,
        data_source_name=data_source_name,
        data_source_url=data_source_url,
        data_source_retrieved_at=data_source_retrieved_at,
        technical_notes=technical_notes,
        technical_data=technical_data,
        standard_mode_code=values.standard_mode_code,
        standard_charge_c_rate=values.standard_charge_c_rate,
        standard_discharge_c_rate=values.standard_discharge_c_rate,
        standard_cycle_count=values.standard_cycle_count,
        standard_cycle_mode=values.standard_cycle_mode,
        standard_time_limit_mode=values.standard_time_limit_mode,
        standard_time_limit_min=values.standard_time_limit_min,
        archived=bool(values.archived),
    )


def _optional_number(
    value: float | None,
    label: str,
    *,
    minimum: float,
    maximum: float,
) -> float | None:
    if value is None:
        return None
    number = float(value)
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise BatteryError(
            f"{label} muss zwischen {minimum:g} und {maximum:g} liegen"
        )
    return number


def _optional_integer(
    value: int | None,
    label: str,
    *,
    minimum: int,
    maximum: int,
) -> int | None:
    if value is None:
        return None
    number = int(value)
    if not minimum <= number <= maximum:
        raise BatteryError(
            f"{label} muss zwischen {minimum} und {maximum} liegen"
        )
    return number


def build_standard_profile(
    battery: BatteryValues,
    *,
    mode_code: int,
    charge_c_rate: float,
    discharge_c_rate: float,
    cycle_count: int,
    cycle_mode: int,
    time_limit_mode: str = "manual",
    time_limit_min: int = DEFAULT_MANUAL_TIME_LIMIT_MIN,
    charge_rest_min: int | None = None,
    discharge_rest_min: int | None = None,
    temp_limit_c: int = 45,
) -> tuple[ProfileValues, dict[str, Any]]:
    battery = validate_battery(battery)
    _validate_standard_settings(
        mode_code=mode_code,
        charge_c_rate=charge_c_rate,
        discharge_c_rate=discharge_c_rate,
        cycle_count=cycle_count,
        cycle_mode=cycle_mode,
    )
    _validate_time_limit_settings(time_limit_mode, time_limit_min)
    if charge_rest_min is None:
        charge_rest_min = 5 if mode_code in (1, 4) else 0
    if discharge_rest_min is None:
        discharge_rest_min = 5 if mode_code in (1, 4) else 0
    if not 0 <= charge_rest_min <= 240:
        raise BatteryError("Ladepause muss zwischen 0 und 240 Minuten liegen")
    if not 0 <= discharge_rest_min <= 240:
        raise BatteryError("Entladepause muss zwischen 0 und 240 Minuten liegen")
    if temp_limit_c and not 20 <= temp_limit_c <= 70:
        raise BatteryError(
            "Temperaturlimit muss aus oder zwischen 20 und 70 Grad sein"
        )

    charge_current_ma = _current_for_rate(
        battery.nominal_capacity_mah,
        charge_c_rate,
        minimum_ma=CHARGE_CURRENT_MIN_MA,
        maximum_ma=CHARGE_CURRENT_MAX_MA,
    )
    discharge_current_ma = _current_for_rate(
        battery.nominal_capacity_mah,
        discharge_c_rate,
        minimum_ma=DISCHARGE_CURRENT_MIN_MA,
        maximum_ma=DISCHARGE_CURRENT_MAX_MA,
    )
    settings = {
        0: (4200, 3000, 4150),
        1: (3600, 2900, 3550),
    }
    charge_voltage_mv, discharge_voltage_mv, keep_voltage_mv = settings[
        battery.battery_type_code
    ]
    charge_end_current_ma = max(
        50,
        min(charge_current_ma, round(charge_current_ma * 0.1 / 10) * 10),
    )

    profile = ProfileValues(
        name=f"Batterie {battery.code} Standard",
        description="Automatisch vom Batteriemanager erzeugt.",
        battery_type_code=battery.battery_type_code,
        mode_code=mode_code,
        capacity_mah=battery.nominal_capacity_mah,
        charge_current_ma=charge_current_ma,
        discharge_current_ma=discharge_current_ma,
        charge_voltage_mv=charge_voltage_mv,
        discharge_voltage_mv=discharge_voltage_mv,
        charge_end_current_ma=charge_end_current_ma,
        discharge_end_current_ma=discharge_current_ma,
        charge_rest_min=charge_rest_min,
        discharge_rest_min=discharge_rest_min,
        cycle_count=cycle_count if mode_code == 4 else 1,
        cycle_mode=cycle_mode if mode_code == 4 else 0,
        delta_peak_mv=0,
        trickle_current_ma=0,
        keep_voltage_mv=keep_voltage_mv,
        temp_limit_c=temp_limit_c,
        time_limit_min=time_limit_min,
        time_limit_mode=time_limit_mode,
    )
    effective_limit_min = effective_time_limit_min(profile)
    return profile, {
        "mode_code": mode_code,
        "mode": STANDARD_MODES[mode_code],
        "charge_c_rate": charge_c_rate,
        "discharge_c_rate": discharge_c_rate,
        "charge_current_ma": charge_current_ma,
        "discharge_current_ma": discharge_current_ma,
        "cycle_count": profile.cycle_count,
        "cycle_mode": profile.cycle_mode,
        "charge_rest_min": profile.charge_rest_min,
        "discharge_rest_min": profile.discharge_rest_min,
        "charge_voltage_mv": charge_voltage_mv,
        "discharge_voltage_mv": discharge_voltage_mv,
        "temp_limit_c": profile.temp_limit_c,
        "time_limit_mode": time_limit_mode,
        "time_limit_min": time_limit_min,
        "effective_time_limit_min": effective_limit_min,
    }


def build_automatic_profile(
    battery: BatteryValues,
    program_key: str,
    capacity_mah: int,
    *,
    template: AutomaticProgramValues | Mapping[str, Any] | None = None,
    time_limit_mode: str | None = None,
    time_limit_min: int | None = None,
) -> tuple[ProfileValues, dict[str, Any]]:
    raw_template = template or AUTOMATIC_PROGRAMS.get(program_key)
    if raw_template is None:
        raise BatteryError("Unbekanntes Automatikprogramm")
    if not 100 <= capacity_mah <= 50000:
        raise BatteryError("Kapazität muss zwischen 100 und 50000 mAh liegen")
    program = validate_automatic_program(
        raw_template
        if isinstance(raw_template, AutomaticProgramValues)
        else AutomaticProgramValues.from_mapping(raw_template)
    )
    selected_time_limit_mode = time_limit_mode or program.time_limit_mode
    selected_time_limit_min = (
        program.time_limit_min if time_limit_min is None else time_limit_min
    )

    calculated_battery = replace(
        battery,
        nominal_capacity_mah=capacity_mah,
    )
    profile, details = build_standard_profile(
        calculated_battery,
        mode_code=program.mode_code,
        charge_c_rate=program.charge_c_rate,
        discharge_c_rate=program.discharge_c_rate,
        cycle_count=program.cycle_count,
        cycle_mode=program.cycle_mode,
        time_limit_mode=selected_time_limit_mode,
        time_limit_min=selected_time_limit_min,
        charge_rest_min=program.charge_rest_min,
        discharge_rest_min=program.discharge_rest_min,
        temp_limit_c=program.temp_limit_c,
    )
    profile = replace(
        profile,
        name=f"{program.label} · {capacity_mah} mAh",
        description=program.description,
    )
    return profile, {
        "key": program_key,
        **program.to_dict(),
        **details,
        "capacity_mah": capacity_mah,
    }


def battery_options_payload(
    automatic_programs: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    automatic_programs = automatic_programs or [
        {
            "key": key,
            **AutomaticProgramValues.from_mapping(values).to_dict(),
            "is_builtin": True,
        }
        for key, values in AUTOMATIC_PROGRAMS.items()
    ]
    return {
        "battery_types": [
            {"code": code, "name": name}
            for code, name in MANAGED_BATTERY_TYPES.items()
        ],
        "modes": [
            {"code": code, "name": name}
            for code, name in STANDARD_MODES.items()
        ],
        "c_rates": [0.25, 0.5, 1, 1.5, 2],
        "current_limits_ma": {
            "charge_min": CHARGE_CURRENT_MIN_MA,
            "charge_max": CHARGE_CURRENT_MAX_MA,
            "discharge_min": DISCHARGE_CURRENT_MIN_MA,
            "discharge_max": DISCHARGE_CURRENT_MAX_MA,
            "step": CURRENT_STEP_MA,
        },
        "time_limit_modes": [
            {"value": "automatic", "label": "Automatisch"},
            {"value": "manual", "label": "Manuell"},
            {"value": "off", "label": "Aus"},
        ],
        "default_manual_time_limit_min": DEFAULT_MANUAL_TIME_LIMIT_MIN,
        "cycle_modes": [
            {"code": 0, "name": "Laden > Entladen"},
            {"code": 1, "name": "Laden > Entladen > Laden"},
            {"code": 2, "name": "Entladen > Laden"},
            {"code": 3, "name": "Entladen > Laden > Entladen"},
        ],
        "automatic_programs": automatic_programs,
    }


def validate_automatic_program(
    values: AutomaticProgramValues,
) -> AutomaticProgramValues:
    label = values.label.strip()
    description = values.description.strip()
    if not label or len(label) > 80:
        raise BatteryError("Profilname muss zwischen 1 und 80 Zeichen lang sein")
    if len(description) > 500:
        raise BatteryError("Beschreibung darf höchstens 500 Zeichen lang sein")
    _validate_standard_settings(
        mode_code=values.mode_code,
        charge_c_rate=values.charge_c_rate,
        discharge_c_rate=values.discharge_c_rate,
        cycle_count=values.cycle_count,
        cycle_mode=values.cycle_mode,
    )
    if not 0 <= values.charge_rest_min <= 240:
        raise BatteryError("Ladepause muss zwischen 0 und 240 Minuten liegen")
    if not 0 <= values.discharge_rest_min <= 240:
        raise BatteryError("Entladepause muss zwischen 0 und 240 Minuten liegen")
    if values.temp_limit_c and not 20 <= values.temp_limit_c <= 70:
        raise BatteryError(
            "Temperaturlimit muss aus oder zwischen 20 und 70 Grad sein"
        )
    _validate_time_limit_settings(values.time_limit_mode, values.time_limit_min)
    return replace(values, label=label, description=description)


def _validate_c_rate(name: str, value: float) -> None:
    if not math.isfinite(value) or not 0.05 <= value <= 2:
        raise BatteryError(f"{name} muss zwischen 0,05 C und 2 C liegen")


def _validate_standard_settings(
    *,
    mode_code: int,
    charge_c_rate: float,
    discharge_c_rate: float,
    cycle_count: int,
    cycle_mode: int,
) -> None:
    if mode_code not in STANDARD_MODES:
        raise BatteryError("Unbekanntes Standardprogramm")
    _validate_c_rate("Lade-C-Rate", charge_c_rate)
    _validate_c_rate("Entlade-C-Rate", discharge_c_rate)
    if not 1 <= cycle_count <= 99:
        raise BatteryError("Zykluszahl muss zwischen 1 und 99 liegen")
    if cycle_mode not in range(4):
        raise BatteryError("Unbekannte Zyklusfolge")


def _validate_time_limit_settings(mode: str, minutes: int) -> None:
    if mode not in TIME_LIMIT_MODES:
        raise BatteryError("Zeitlimit-Modus muss automatisch, manuell oder aus sein")
    if not 0 <= minutes <= 1440:
        raise BatteryError("Zeitlimit muss zwischen 0 und 1440 Minuten liegen")
    if mode == "manual" and minutes == 0:
        raise BatteryError("Manuelles Zeitlimit muss mindestens eine Minute betragen")


def _current_for_rate(
    capacity_mah: int,
    c_rate: float,
    minimum_ma: int,
    maximum_ma: int,
) -> int:
    current_ma = (
        math.floor(capacity_mah * c_rate / CURRENT_STEP_MA + 0.5)
        * CURRENT_STEP_MA
    )
    return min(maximum_ma, max(minimum_ma, current_ma))
