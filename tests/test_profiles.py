import pytest

from mc3000_control.profiles import (
    ProfileError,
    ProfileValues,
    build_profile_packet,
    effective_time_limit_min,
    mode_name,
    validate_profile,
)
from mc3000_control.protocol import Opcode, checksum


def profile(**overrides) -> ProfileValues:
    values = {
        "name": "Werkstatt Li-Ion",
        "description": "",
        "battery_type_code": 0,
        "mode_code": 0,
        "capacity_mah": 3000,
        "charge_current_ma": 1000,
        "discharge_current_ma": 500,
        "charge_voltage_mv": 4200,
        "discharge_voltage_mv": 3000,
        "charge_end_current_ma": 100,
        "discharge_end_current_ma": 500,
        "charge_rest_min": 0,
        "discharge_rest_min": 0,
        "cycle_count": 1,
        "cycle_mode": 0,
        "delta_peak_mv": 0,
        "trickle_current_ma": 0,
        "keep_voltage_mv": 4150,
        "temp_limit_c": 45,
        "time_limit_min": 240,
    }
    values.update(overrides)
    return ProfileValues(**values)


def test_profile_packet_matches_manufacturer_layout() -> None:
    packet = build_profile_packet(profile(), 0x05)

    assert len(packet) == 40
    assert packet[:5] == bytes([0x0F, Opcode.SET_PROFILE, 0x05, 0x00, 0x00])
    assert packet[5:19].hex() == "0bb803e801f410680bb8006401f4"
    assert packet[24:30].hex() == "10362d00f000"
    assert packet[39] == checksum(packet[:39])


def test_time_limit_modes_resolve_to_manual_automatic_or_off() -> None:
    manual = profile(time_limit_mode="manual", time_limit_min=360)
    automatic = profile(
        capacity_mah=2000,
        charge_current_ma=1000,
        time_limit_mode="automatic",
    )
    disabled = profile(time_limit_mode="off", time_limit_min=360)

    assert effective_time_limit_min(manual) == 360
    assert effective_time_limit_min(automatic) == 180
    assert effective_time_limit_min(disabled) == 0
    assert build_profile_packet(manual, 1)[27:29] == bytes([0x01, 0x68])
    assert build_profile_packet(automatic, 1)[27:29] == bytes([0x00, 0xB4])
    assert build_profile_packet(disabled, 1)[27:29] == bytes([0x00, 0x00])


def test_automatic_cycle_limit_includes_all_phases_and_rest_periods() -> None:
    cycle = profile(
        mode_code=4,
        capacity_mah=2000,
        charge_current_ma=1000,
        discharge_current_ma=1000,
        cycle_mode=1,
        charge_rest_min=5,
        discharge_rest_min=5,
        time_limit_mode="automatic",
    )

    assert effective_time_limit_min(cycle) == 550


def test_automatic_multi_cycle_limit_uses_continuous_cycle_sequence() -> None:
    cycle = profile(
        mode_code=4,
        capacity_mah=2000,
        charge_current_ma=1000,
        discharge_current_ma=1000,
        cycle_count=2,
        cycle_mode=1,
        charge_rest_min=5,
        discharge_rest_min=5,
        time_limit_mode="automatic",
    )

    # C-D-C with N=2 is C-D-C-D-C: three charges and two discharges.
    assert effective_time_limit_min(cycle) == 920


def test_automatic_refresh_limit_includes_final_recharge() -> None:
    refresh = profile(
        mode_code=1,
        capacity_mah=2000,
        charge_current_ma=1000,
        discharge_current_ma=1000,
        charge_rest_min=5,
        discharge_rest_min=5,
        time_limit_mode="automatic",
    )

    assert effective_time_limit_min(refresh) == 550


def test_refresh_replaces_disabled_end_currents() -> None:
    packet = build_profile_packet(
        profile(
            mode_code=1,
            charge_end_current_ma=0,
            discharge_end_current_ma=0,
        ),
        1,
    )

    assert packet[15:17] == bytes([0x03, 0xE8])
    assert packet[17:19] == bytes([0x01, 0xF4])


def test_nickel_only_fields_are_encoded() -> None:
    packet = build_profile_packet(
        profile(
            battery_type_code=3,
            charge_voltage_mv=1650,
            discharge_voltage_mv=1000,
            keep_voltage_mv=1350,
            delta_peak_mv=5,
            trickle_current_ma=120,
        ),
        1,
    )

    assert packet[22] == 5
    assert packet[23] == 12


def test_invalid_chemistry_values_are_rejected() -> None:
    with pytest.raises(ProfileError, match="Lade-Endspannung"):
        validate_profile(profile(charge_voltage_mv=4350))

    with pytest.raises(ProfileError, match="Nickel"):
        validate_profile(profile(delta_peak_mv=3))

    with pytest.raises(ProfileError, match="mindestens eine Minute"):
        validate_profile(profile(time_limit_mode="manual", time_limit_min=0))


def test_short_mode_chemistries_use_their_own_mode_numbers() -> None:
    assert mode_name(5, 2) == "Entladen"
    assert mode_name(5, 3) == "Zyklus"
