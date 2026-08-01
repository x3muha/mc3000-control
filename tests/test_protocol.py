from mc3000_control import protocol


def response(opcode: int, payload: bytes) -> bytes:
    frame = bytearray(20)
    frame[0] = 0x0F
    frame[1] = opcode
    frame[2 : 2 + len(payload)] = payload
    frame[-1] = protocol.checksum(frame[:-1])
    return bytes(frame)


def test_status_commands_use_zero_based_slots() -> None:
    assert protocol.command_status(0).hex() == "0f55000000000000000000000000000000000064"
    assert protocol.command_status(3).hex() == "0f55030000000000000000000000000000000067"


def test_start_and_stop_use_slot_bitmasks() -> None:
    assert protocol.command_start(0x04)[2] == 0x04
    assert protocol.command_stop(0x08)[2] == 0x08
    assert protocol.command_start(0x0F)[-1] == protocol.checksum(
        protocol.command_start(0x0F)[:-1]
    )


def test_parse_slot_status() -> None:
    frame = response(
        protocol.Opcode.STATUS,
        bytes(
            [
                1,
                0,
                0,
                0,
                1,
                0x00,
                0x7B,
                0x0F,
                0xA0,
                0x03,
                0xE8,
                0x04,
                0xD2,
                25,
                0x00,
                0x23,
                0x22,
            ]
        ),
    )

    slot = protocol.parse_slot(frame)

    assert slot.slot == 2
    assert slot.battery_type == "Li-Ion"
    assert slot.mode == "Laden"
    assert slot.status == "Laden"
    assert slot.active is True
    assert slot.time_s == 123
    assert slot.voltage_v == 4.0
    assert slot.current_a == 1.0
    assert slot.capacity_mah == 1234
    assert slot.temperature_c == 25
    assert slot.resistance_mohm == 35


def test_mode_two_depends_on_chemistry() -> None:
    assert protocol.mode_name(2, 0) == "Lagern"
    assert protocol.mode_name(2, 3) == "Break-in"


def test_parse_basic_data() -> None:
    frame = response(
        protocol.Opcode.GET_BASIC,
        bytes([0, 1, 1, 1, 0, 0x2A, 0xF8]),
    )

    basic = protocol.parse_basic(frame)

    assert basic.temperature_unit == "C"
    assert basic.system_beep is True
    assert basic.fan_mode == 0
    assert basic.input_voltage_v == 11.0


def test_parse_voltage_curve() -> None:
    curve = bytearray(protocol.CURVE_SIZE)
    curve[0] = 0x0F
    curve[1] = protocol.Opcode.VOLTAGE_CURVE
    curve[2] = 2
    curve[3] = 0
    curve[4] = 10
    curve[5:11] = bytes([0x0E, 0x74, 0x0E, 0x7E, 0x0E, 0x88])

    parsed = protocol.parse_curve(bytes(curve))

    assert parsed["slot"] == 3
    assert parsed["interval_s"] == 10
    assert parsed["points"] == [
        {"index": 0, "time_s": 0, "voltage_v": 3.7},
        {"index": 1, "time_s": 10, "voltage_v": 3.71},
        {"index": 2, "time_s": 20, "voltage_v": 3.72},
    ]


def test_invalid_checksum_is_rejected() -> None:
    frame = bytearray(response(protocol.Opcode.GET_BASIC, bytes(7)))
    frame[-1] ^= 0xFF

    try:
        protocol.parse_basic(bytes(frame))
    except protocol.ProtocolError as exc:
        assert "Prüfsumme" in str(exc)
    else:
        raise AssertionError("invalid checksum was accepted")
