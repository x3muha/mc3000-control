from mc3000_control.battery_manager import (
    AutomaticProgramValues,
    BatteryValues,
    build_automatic_profile,
    build_standard_profile,
    normalize_battery_code,
)


def battery(**overrides) -> BatteryValues:
    values = {
        "code": "001",
        "name": "Taschenlampe",
        "battery_type_code": 0,
        "nominal_capacity_mah": 2000,
        "notes": "",
        "archived": False,
    }
    values.update(overrides)
    return BatteryValues(**values)


def test_battery_number_keeps_leading_zeroes() -> None:
    assert normalize_battery_code(" 001 ") == "001"


def test_standard_program_calculates_currents_from_c_rate() -> None:
    profile, summary = build_standard_profile(
        battery(nominal_capacity_mah=1500),
        mode_code=4,
        charge_c_rate=1.5,
        discharge_c_rate=1,
        cycle_count=3,
        cycle_mode=1,
    )

    assert profile.charge_current_ma == 2250
    assert profile.discharge_current_ma == 1500
    assert profile.cycle_count == 3
    assert profile.charge_voltage_mv == 4200
    assert summary["charge_c_rate"] == 1.5
    assert summary["time_limit_mode"] == "manual"
    assert summary["effective_time_limit_min"] == 360


def test_lifepo4_standard_program_uses_its_voltage_limits() -> None:
    profile, _summary = build_standard_profile(
        battery(battery_type_code=1),
        mode_code=0,
        charge_c_rate=0.5,
        discharge_c_rate=0.5,
        cycle_count=1,
        cycle_mode=0,
    )

    assert profile.charge_voltage_mv == 3600
    assert profile.discharge_voltage_mv == 2900


def test_standard_program_clamps_currents_to_charger_limits() -> None:
    profile, summary = build_standard_profile(
        battery(nominal_capacity_mah=2000),
        mode_code=4,
        charge_c_rate=2,
        discharge_c_rate=2,
        cycle_count=1,
        cycle_mode=0,
    )

    assert profile.charge_current_ma == 3000
    assert profile.discharge_current_ma == 2000
    assert summary["charge_current_ma"] == 3000
    assert summary["discharge_current_ma"] == 2000


def test_standard_program_uses_device_minimum_and_current_steps() -> None:
    minimum_profile, _summary = build_standard_profile(
        battery(nominal_capacity_mah=100),
        mode_code=4,
        charge_c_rate=0.05,
        discharge_c_rate=0.05,
        cycle_count=1,
        cycle_mode=0,
    )
    rounded_profile, _summary = build_standard_profile(
        battery(nominal_capacity_mah=250),
        mode_code=0,
        charge_c_rate=0.5,
        discharge_c_rate=0.5,
        cycle_count=1,
        cycle_mode=0,
    )

    assert minimum_profile.charge_current_ma == 50
    assert minimum_profile.discharge_current_ma == 50
    assert rounded_profile.charge_current_ma == 130


def test_charge_program_ignores_unused_discharge_rate_limit() -> None:
    profile, _summary = build_standard_profile(
        battery(nominal_capacity_mah=5000),
        mode_code=0,
        charge_c_rate=0.5,
        discharge_c_rate=0.5,
        cycle_count=1,
        cycle_mode=0,
    )

    assert profile.charge_current_ma == 2500
    assert profile.discharge_current_ma == 2000


def test_automatic_refresh_uses_entered_capacity_and_fixed_c_rates() -> None:
    profile, summary = build_automatic_profile(
        battery(nominal_capacity_mah=3000),
        "refresh",
        1800,
    )

    assert profile.capacity_mah == 1800
    assert profile.charge_current_ma == 900
    assert profile.discharge_current_ma == 1800
    assert profile.mode_code == 1
    assert summary["capacity_mah"] == 1800
    assert summary["charge_c_rate"] == 0.5
    assert summary["discharge_c_rate"] == 1.0


def test_automatic_refresh_can_calculate_time_limit_from_all_phases() -> None:
    profile, summary = build_automatic_profile(
        battery(),
        "refresh",
        1800,
        time_limit_mode="automatic",
    )

    assert profile.time_limit_mode == "automatic"
    assert summary["effective_time_limit_min"] == 460


def test_automatic_discharge_respects_mc3000_current_limit() -> None:
    profile, summary = build_automatic_profile(battery(), "capacity_test", 2500)

    assert profile.discharge_current_ma == 2000
    assert summary["discharge_current_ma"] == 2000


def test_automatic_profile_uses_edited_automation_settings() -> None:
    template = AutomaticProgramValues(
        label="Eigener Refresh",
        description="Angepasste Automatik.",
        mode_code=1,
        charge_c_rate=0.75,
        discharge_c_rate=1.25,
        cycle_count=1,
        cycle_mode=0,
        charge_rest_min=12,
        discharge_rest_min=8,
        temp_limit_c=42,
        time_limit_mode="off",
        time_limit_min=360,
    )

    profile, summary = build_automatic_profile(
        battery(),
        "edited",
        2000,
        template=template,
    )

    assert profile.name == "Eigener Refresh · 2000 mAh"
    assert profile.charge_current_ma == 1500
    assert profile.discharge_current_ma == 2000
    assert profile.charge_rest_min == 12
    assert profile.discharge_rest_min == 8
    assert profile.temp_limit_c == 42
    assert profile.time_limit_mode == "off"
    assert summary["effective_time_limit_min"] == 0
