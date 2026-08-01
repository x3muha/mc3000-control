from mc3000_control.registry import DeviceRegistry, normalize_address


def test_registry_round_trip(tmp_path) -> None:
    registry = DeviceRegistry(tmp_path / "registry.db")

    created = registry.save(
        "aa:bb:cc:dd:ee:ff",
        "Werkbank",
        serial_number="SN-1234",
    )
    loaded = registry.get("AA:BB:CC:DD:EE:FF")

    assert created.address == "AA:BB:CC:DD:EE:FF"
    assert created.serial_number == "SN-1234"
    assert loaded == created
    assert registry.list() == [created]


def test_registry_updates_release_state(tmp_path) -> None:
    registry = DeviceRegistry(tmp_path / "registry.db")
    registry.save("AA:BB:CC:DD:EE:FF", "Werkbank")

    released = registry.set_released("aa:bb:cc:dd:ee:ff", True)

    assert released.released is True
    assert registry.get(released.address).released is True


def test_registry_deletes_device(tmp_path) -> None:
    registry = DeviceRegistry(tmp_path / "registry.db")
    created = registry.save("AA:BB:CC:DD:EE:FF", "Werkbank")

    deleted = registry.delete(created.address)

    assert deleted == created
    assert registry.get(created.address) is None
    assert registry.list() == []


def test_address_validation() -> None:
    assert normalize_address("aa:bb:cc:dd:ee:ff") == "AA:BB:CC:DD:EE:FF"

    for value in ("", "AA:BB", "GG:BB:CC:DD:EE:FF", "A:BB:CC:DD:EE:FF"):
        try:
            normalize_address(value)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid address accepted: {value}")
