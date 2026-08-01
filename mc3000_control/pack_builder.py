from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Any


class PackBuilderError(ValueError):
    """Raised when a pack cannot be assembled from the selected cells."""


@dataclass(frozen=True, slots=True)
class CellCandidate:
    battery_id: int
    code: str
    battery_type_code: int
    capacity_mah: int
    resistance_mohm: int | None
    soh_percent: float | None

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> CellCandidate | None:
        statistics = value.get("statistics") or {}
        capacity = statistics.get("latest_capacity_mah")
        if not isinstance(capacity, int) or capacity <= 0:
            return None
        resistance = statistics.get("latest_resistance_mohm")
        return cls(
            battery_id=int(value["id"]),
            code=str(value["code"]),
            battery_type_code=int(value["battery_type_code"]),
            capacity_mah=capacity,
            resistance_mohm=(
                int(resistance)
                if isinstance(resistance, (int, float)) and resistance > 0
                else None
            ),
            soh_percent=(
                float(statistics["soh_percent"])
                if isinstance(statistics.get("soh_percent"), (int, float))
                else None
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "battery_id": self.battery_id,
            "code": self.code,
            "battery_type_code": self.battery_type_code,
            "capacity_mah": self.capacity_mah,
            "resistance_mohm": self.resistance_mohm,
            "soh_percent": self.soh_percent,
        }


def build_cell_groups(
    batteries: list[dict[str, Any]],
    *,
    cells_per_group: int,
    group_count: int = 1,
    max_capacity_spread_percent: float = 5,
    max_resistance_spread_percent: float = 20,
) -> dict[str, Any]:
    if cells_per_group not in range(2, 17):
        raise PackBuilderError("Eine Gruppe muss aus 2 bis 16 Zellen bestehen")
    if group_count not in range(1, 17):
        raise PackBuilderError("Es sind 1 bis 16 Gruppen möglich")
    if not 0 < max_capacity_spread_percent <= 50:
        raise PackBuilderError("Kapazitätsabweichung muss zwischen 0 und 50 % liegen")
    if not 0 < max_resistance_spread_percent <= 100:
        raise PackBuilderError(
            "Innenwiderstandsabweichung muss zwischen 0 und 100 % liegen"
        )

    candidates = [
        candidate
        for value in batteries
        if (candidate := CellCandidate.from_mapping(value)) is not None
    ]
    if not candidates:
        raise PackBuilderError(
            "Keine Batterie mit abgeschlossenem Kapazitätstest vorhanden"
        )
    chemistries = {candidate.battery_type_code for candidate in candidates}
    if len(chemistries) != 1:
        raise PackBuilderError("Für einen Pack nur Zellen gleicher Chemie auswählen")
    needed = cells_per_group * group_count
    if len(candidates) < needed:
        raise PackBuilderError(
            f"Mindestens {needed} getestete Zellen werden benötigt"
        )

    remaining = list(candidates)
    groups: list[dict[str, Any]] = []
    for group_index in range(group_count):
        group = min(
            combinations(remaining, cells_per_group),
            key=_group_score,
        )
        report = _group_report(
            group,
            group_index + 1,
            max_capacity_spread_percent=max_capacity_spread_percent,
            max_resistance_spread_percent=max_resistance_spread_percent,
        )
        groups.append(report)
        selected_ids = {cell.battery_id for cell in group}
        remaining = [
            cell for cell in remaining if cell.battery_id not in selected_ids
        ]

    return {
        "battery_type_code": candidates[0].battery_type_code,
        "cells_per_group": cells_per_group,
        "group_count": group_count,
        "eligible_cell_count": len(candidates),
        "unused_cells": [cell.to_dict() for cell in remaining],
        "groups": groups,
        "all_groups_within_limits": all(group["within_limits"] for group in groups),
    }


def _group_score(group: tuple[CellCandidate, ...]) -> tuple[float, float, float]:
    capacities = [cell.capacity_mah for cell in group]
    capacity_spread = _relative_spread(capacities)
    resistances = [
        cell.resistance_mohm for cell in group if cell.resistance_mohm is not None
    ]
    resistance_spread = (
        _relative_spread(resistances)
        if len(resistances) == len(group)
        else 1000
    )
    average_capacity = sum(capacities) / len(capacities)
    return capacity_spread, resistance_spread, -average_capacity


def _group_report(
    group: tuple[CellCandidate, ...],
    number: int,
    *,
    max_capacity_spread_percent: float,
    max_resistance_spread_percent: float,
) -> dict[str, Any]:
    capacities = [cell.capacity_mah for cell in group]
    resistances = [
        cell.resistance_mohm for cell in group if cell.resistance_mohm is not None
    ]
    capacity_spread = round(_relative_spread(capacities), 2)
    resistance_spread = (
        round(_relative_spread(resistances), 2)
        if len(resistances) == len(group)
        else None
    )
    warnings: list[str] = []
    if capacity_spread > max_capacity_spread_percent:
        warnings.append(
            f"Kapazitätsabweichung {capacity_spread:.1f} % liegt über dem Grenzwert"
        )
    if resistance_spread is None:
        warnings.append("Mindestens einer Zelle fehlt ein Innenwiderstandswert")
    elif resistance_spread > max_resistance_spread_percent:
        warnings.append(
            f"Innenwiderstandsabweichung {resistance_spread:.1f} % liegt über dem Grenzwert"
        )
    return {
        "number": number,
        "cells": [cell.to_dict() for cell in sorted(group, key=lambda cell: cell.code)],
        "average_capacity_mah": round(sum(capacities) / len(capacities)),
        "capacity_spread_percent": capacity_spread,
        "average_resistance_mohm": (
            round(sum(resistances) / len(resistances), 1)
            if len(resistances) == len(group)
            else None
        ),
        "resistance_spread_percent": resistance_spread,
        "within_limits": not warnings,
        "warnings": warnings,
    }


def _relative_spread(values: list[int]) -> float:
    average = sum(values) / len(values)
    if average <= 0:
        return 0
    return (max(values) - min(values)) / average * 100
