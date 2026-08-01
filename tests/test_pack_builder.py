import pytest

from mc3000_control.pack_builder import PackBuilderError, build_cell_groups


def cell(
    battery_id: int,
    code: str,
    capacity_mah: int,
    resistance_mohm: int,
    *,
    battery_type_code: int = 0,
) -> dict:
    return {
        "id": battery_id,
        "code": code,
        "battery_type_code": battery_type_code,
        "statistics": {
            "latest_capacity_mah": capacity_mah,
            "latest_resistance_mohm": resistance_mohm,
            "soh_percent": round(capacity_mah / 30, 1),
        },
    }


def test_pack_builder_groups_closest_cells() -> None:
    result = build_cell_groups(
        [
            cell(1, "001", 3000, 31),
            cell(2, "002", 2990, 30),
            cell(3, "003", 2985, 32),
            cell(4, "004", 3010, 31),
            cell(5, "005", 2500, 70),
        ],
        cells_per_group=4,
    )

    assert [item["code"] for item in result["groups"][0]["cells"]] == [
        "001",
        "002",
        "003",
        "004",
    ]
    assert result["groups"][0]["within_limits"] is True
    assert result["unused_cells"][0]["code"] == "005"


def test_pack_builder_rejects_mixed_chemistry() -> None:
    with pytest.raises(PackBuilderError, match="gleicher Chemie"):
        build_cell_groups(
            [
                cell(1, "001", 3000, 30, battery_type_code=0),
                cell(2, "002", 3000, 30, battery_type_code=5),
            ],
            cells_per_group=2,
        )
