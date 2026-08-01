from __future__ import annotations

import io
from datetime import UTC, datetime
from typing import Any

import segno
from reportlab.graphics.shapes import Drawing, Line, PolyLine, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def battery_sheet_pdf(
    battery: dict[str, Any],
    *,
    qr_target: str,
) -> bytes:
    story = _battery_header(battery, qr_target=qr_target)
    story.extend(
        [
            Spacer(1, 5 * mm),
            Paragraph("Batterie-Steckblatt", _styles()["Heading1"]),
            _battery_details_table(battery),
            Spacer(1, 5 * mm),
            Paragraph("Auswertung", _styles()["Heading2"]),
            _statistics_table(battery.get("statistics") or {}),
            Spacer(1, 5 * mm),
            Paragraph("Notizen", _styles()["Heading2"]),
            Paragraph(
                _safe_text(battery.get("notes")) or "Keine Notizen hinterlegt.",
                _styles()["BodyText"],
            ),
        ]
    )
    return _build_pdf(story, title=f"Batterie {battery.get('code', '')}")


def run_report_pdf(
    report: dict[str, Any],
    chart: dict[str, Any],
    battery: dict[str, Any] | None,
    *,
    qr_target: str | None,
    phase_opacity_percent: int = 15,
) -> bytes:
    story: list[Any] = []
    if battery and qr_target:
        story.extend(_battery_header(battery, qr_target=qr_target))
        story.append(Spacer(1, 4 * mm))
    story.extend(
        [
            Paragraph("Prüfbericht", _styles()["Heading1"]),
            Paragraph(
                f"{_safe_text(report.get('mode'))} · Slot {report.get('slot')} · "
                f"Lauf {report.get('id')}",
                _styles()["Subheading"],
            ),
            Spacer(1, 3 * mm),
            _report_table(report),
            Spacer(1, 4 * mm),
            Paragraph("Bewertung", _styles()["Heading2"]),
            _warning_block(report),
            PageBreak(),
            Paragraph("Messdiagramme", _styles()["Heading1"]),
            Paragraph(
                "Der Bericht zeigt den vollständigen aufgezeichneten Programmlauf. "
                "Entladestrom wird negativ dargestellt.",
                _styles()["BodyText"],
            ),
            Spacer(1, 3 * mm),
            _chart(
                "Spannung / Strom",
                chart.get("points") or [],
                (("voltage_v", "Spannung V", colors.HexColor("#16825d")),
                 ("current_a", "Strom A", colors.HexColor("#b52b34"))),
                run_id=report.get("id"),
                phase_opacity_percent=phase_opacity_percent,
            ),
            Spacer(1, 3 * mm),
            _chart(
                "Temperatur / Innenwiderstand",
                chart.get("points") or [],
                (("temperature_c", "Temperatur °C", colors.HexColor("#f59e0b")),
                 ("resistance_mohm", "Widerstand mΩ", colors.HexColor("#7c3aed"))),
                run_id=report.get("id"),
                phase_opacity_percent=phase_opacity_percent,
            ),
            Spacer(1, 3 * mm),
            _chart(
                "Kapazität",
                chart.get("points") or [],
                (("capacity_mah", "Ist mAh", colors.HexColor("#059669")),),
                target=report.get("nominal_capacity_mah"),
                run_id=report.get("id"),
                phase_opacity_percent=phase_opacity_percent,
            ),
        ]
    )
    return _build_pdf(story, title=f"Prüfbericht Lauf {report.get('id')}")


def _build_pdf(story: list[Any], *, title: str) -> bytes:
    output = io.BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=15 * mm,
        title=title,
        author="MC3000 Control",
    )
    document.build(story, onFirstPage=_page_footer, onLaterPages=_page_footer)
    return output.getvalue()


def _page_footer(canvas: Any, document: Any) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#64748b"))
    canvas.drawString(16 * mm, 8 * mm, "MC3000 Control")
    canvas.drawRightString(
        A4[0] - 16 * mm,
        8 * mm,
        f"Seite {document.page}",
    )
    canvas.restoreState()


def _battery_header(
    battery: dict[str, Any],
    *,
    qr_target: str,
) -> list[Any]:
    qr = io.BytesIO()
    segno.make(qr_target, error="m").save(
        qr,
        kind="png",
        scale=5,
        border=2,
    )
    qr.seek(0)
    title = Paragraph(
        f"<b>Batterie { _safe_text(battery.get('code')) }</b><br/>"
        f"{_safe_text(battery.get('name')) or _safe_text(battery.get('battery_type'))}",
        _styles()["BatteryTitle"],
    )
    table = Table(
        [[title, Image(qr, width=28 * mm, height=28 * mm)]],
        colWidths=[145 * mm, 28 * mm],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eff6ff")),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#93c5fd")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (0, 0), 6 * mm),
                ("RIGHTPADDING", (-1, 0), (-1, 0), 2 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 2 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
            ]
        )
    )
    return [table]


def _battery_details_table(battery: dict[str, Any]) -> Table:
    rows = [
        ("Batterienummer", battery.get("code") or "–", "Chemie", battery.get("battery_type") or "–"),
        ("Name", battery.get("name") or "–", "Nennkapazität", _unit(battery.get("nominal_capacity_mah"), "mAh")),
        ("Hersteller", battery.get("manufacturer") or "–", "Typ / Modell", battery.get("model") or "–"),
        ("Bauform", battery.get("form_factor") or "–", "Protection", "Ja" if battery.get("protected") else "Nein"),
        ("Herkunft", battery.get("origin") or "–", "In Betrieb seit", _date(battery.get("in_service_since"))),
        ("Angelegt", _date_time(battery.get("created_at")), "Aktualisiert", _date_time(battery.get("updated_at"))),
    ]
    return _key_value_table(rows)


def _statistics_table(statistics: dict[str, Any]) -> Table:
    rows = [
        ("Kapazitäts-SOH", _percent(statistics.get("soh_percent")), "Programmläufe", statistics.get("run_count") or 0),
        ("Letztes Soll / Ist", _percent(statistics.get("latest_capacity_ratio_percent")), "Kapazitätstests", statistics.get("capacity_test_count") or 0),
        ("Letzte Kapazität", _unit(statistics.get("latest_capacity_result_mah"), "mAh"), "Innenwiderstand", _unit(statistics.get("latest_resistance_mohm"), "mΩ")),
    ]
    return _key_value_table(rows)


def _report_table(report: dict[str, Any]) -> Table:
    rows = [
        ("Batterie", report.get("battery_code") or "ohne Akte", "Programm", report.get("mode") or "–"),
        ("Beginn", _date_time(report.get("started_at")), "Ende", _date_time(report.get("ended_at"))),
        ("Kapazität Soll", _unit(report.get("nominal_capacity_mah"), "mAh"), "Kapazität Ist", _unit(report.get("capacity_actual_mah"), "mAh")),
        ("Soll / Ist", _percent(report.get("capacity_ratio_percent")), "Energie", _unit(report.get("energy_wh"), "Wh", decimals=3)),
        ("Spannung Start / Ende", f"{_number(report.get('start_voltage_v'), 3)} / {_number(report.get('end_voltage_v'), 3)} V", "Max. Temperatur", _unit(report.get("maximum_temperature_c"), "°C")),
        ("Innenwiderstand Start / Ende", f"{_number(report.get('start_resistance_mohm'), 0)} / {_number(report.get('end_resistance_mohm'), 0)} mΩ", "Messpunkte", report.get("sample_count") or 0),
    ]
    return _key_value_table(rows)


def _key_value_table(rows: list[tuple[Any, ...]]) -> Table:
    data = []
    for row in rows:
        data.append(
            [
                Paragraph(f"<b>{_safe_text(row[0])}</b>", _styles()["Small"]),
                Paragraph(_safe_text(row[1]), _styles()["Small"]),
                Paragraph(f"<b>{_safe_text(row[2])}</b>", _styles()["Small"]),
                Paragraph(_safe_text(row[3]), _styles()["Small"]),
            ]
        )
    table = Table(data, colWidths=[34 * mm, 53 * mm, 34 * mm, 52 * mm])
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f8fafc")),
                ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f8fafc")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 2.2 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2 * mm),
            ]
        )
    )
    return table


def _warning_block(report: dict[str, Any]) -> Table:
    warnings = report.get("warnings") or []
    if not warnings:
        warnings = [{"level": "ok", "text": "Keine Auffälligkeiten erkannt."}]
    palette = {
        "danger": colors.HexColor("#fee2e2"),
        "warning": colors.HexColor("#fef3c7"),
        "info": colors.HexColor("#dbeafe"),
        "ok": colors.HexColor("#dcfce7"),
    }
    data = [[Paragraph(_safe_text(item.get("text")), _styles()["BodyText"])] for item in warnings]
    table = Table(data, colWidths=[173 * mm])
    commands: list[tuple[Any, ...]] = [
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5 * mm),
    ]
    for index, item in enumerate(warnings):
        commands.append(
            ("BACKGROUND", (0, index), (0, index), palette.get(item.get("level"), palette["info"]))
        )
    table.setStyle(TableStyle(commands))
    return table


def _chart(
    title: str,
    points: list[dict[str, Any]],
    series: tuple[tuple[str, str, colors.Color], ...],
    *,
    target: float | None = None,
    run_id: int | None = None,
    phase_opacity_percent: int = 15,
) -> Drawing:
    width, height = 173 * mm, 52 * mm
    drawing = Drawing(width, height)
    left, right, bottom, top = 11 * mm, 5 * mm, 9 * mm, 8 * mm
    plot_width = width - left - right
    plot_height = height - bottom - top
    drawing.add(String(0, height - 4 * mm, title, fontName="Helvetica-Bold", fontSize=10))
    drawing.add(Rect(left, bottom, plot_width, plot_height, fillColor=colors.white, strokeColor=colors.HexColor("#cbd5e1")))
    if not points:
        drawing.add(String(left + plot_width / 2, bottom + plot_height / 2, "Keine Messpunkte", textAnchor="middle", fillColor=colors.grey))
        return drawing
    x_values = [
        datetime.fromisoformat(str(point["recorded_at"])).timestamp()
        for point in points
    ]
    x_min, x_max = min(x_values), max(x_values)
    if x_max == x_min:
        x_max += 1
    opacity = max(15, min(25, int(phase_opacity_percent))) / 100
    for phase_start, phase_end, label, colour in _phase_bands(points, run_id):
        if phase_end < x_min or phase_start > x_max:
            continue
        clipped_start = max(x_min, phase_start)
        clipped_end = min(x_max, phase_end)
        x = left + (clipped_start - x_min) / (x_max - x_min) * plot_width
        phase_width = max(
            0.8,
            (clipped_end - clipped_start) / (x_max - x_min) * plot_width,
        )
        drawing.add(
            Rect(
                x,
                bottom,
                phase_width,
                plot_height,
                fillColor=colour,
                strokeColor=None,
                fillOpacity=opacity,
            )
        )
        if phase_width >= 18 * mm:
            drawing.add(
                String(
                    x + phase_width / 2,
                    bottom + plot_height - 3 * mm,
                    label,
                    fontName="Helvetica-Bold",
                    fontSize=6,
                    fillColor=colour,
                    textAnchor="middle",
                )
            )
    for index, (key, label, colour) in enumerate(series):
        values = [
            float(point[key])
            for point in points
            if point.get(key) is not None
        ]
        if not values:
            continue
        y_min, y_max = min(values), max(values)
        if key == "capacity_mah":
            y_min = 0
            if target is not None:
                y_max = max(y_max, float(target))
        if y_max == y_min:
            y_max += 1
        coordinates: list[float] = []
        for x_value, point in zip(x_values, points, strict=False):
            raw = point.get(key)
            if raw is None:
                continue
            x = left + (x_value - x_min) / (x_max - x_min) * plot_width
            y = bottom + (float(raw) - y_min) / (y_max - y_min) * plot_height
            coordinates.extend((x, y))
        if len(coordinates) >= 4:
            drawing.add(PolyLine(coordinates, strokeColor=colour, strokeWidth=1.2))
        legend_x = left + index * 65 * mm
        drawing.add(Line(legend_x, 3 * mm, legend_x + 6 * mm, 3 * mm, strokeColor=colour, strokeWidth=2))
        drawing.add(String(legend_x + 8 * mm, 1.5 * mm, f"{label}: {_number(y_min, 2)}–{_number(y_max, 2)}", fontSize=7))
        if target is not None and key == "capacity_mah" and y_min <= float(target) <= y_max:
            target_y = bottom + (float(target) - y_min) / (y_max - y_min) * plot_height
            drawing.add(Line(left, target_y, left + plot_width, target_y, strokeColor=colors.HexColor("#64748b"), strokeDashArray=[3, 3]))
    start_label = datetime.fromtimestamp(x_min, UTC).astimezone().strftime("%H:%M")
    end_label = datetime.fromtimestamp(x_max, UTC).astimezone().strftime("%H:%M")
    drawing.add(String(left, bottom - 4 * mm, start_label, fontSize=7))
    drawing.add(String(left + plot_width, bottom - 4 * mm, end_label, fontSize=7, textAnchor="end"))
    return drawing


def _phase_bands(
    points: list[dict[str, Any]],
    run_id: int | None,
) -> list[tuple[float, float, str, colors.Color]]:
    states: list[dict[str, Any]] = []
    for point in points:
        if run_id is not None and point.get("run_id") != run_id:
            continue
        status = int(point.get("status_code") or 0)
        if status not in {1, 2, 3, 4}:
            continue
        stamp = datetime.fromisoformat(str(point["recorded_at"])).timestamp()
        if not states or states[-1]["status"] != status:
            states.append({"status": status, "start": stamp, "end": stamp})
        else:
            states[-1]["end"] = stamp
    green = colors.HexColor("#16825d")
    red = colors.HexColor("#b52b34")
    orange = colors.HexColor("#c47a00")
    totals = {
        status: sum(1 for state in states if state["status"] == status)
        for status in (1, 2)
    }
    seen = {1: 0, 2: 0}
    bands: list[tuple[float, float, str, colors.Color]] = []
    for index, state in enumerate(states):
        status = state["status"]
        if status not in {1, 2, 3}:
            continue
        next_state = states[index + 1] if index + 1 < len(states) else None
        phase_end = next_state["start"] if next_state else state["end"]
        if status == 3:
            label, colour = "Pause", orange
        else:
            seen[status] += 1
            label = "Laden" if status == 1 else "Entladen"
            if totals[status] > 1:
                label = f"{label} {seen[status]}"
            colour = green if status == 1 else red
        bands.append((state["start"], phase_end, label, colour))
    return bands


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "Heading1": ParagraphStyle("Heading1De", parent=base["Heading1"], fontName="Helvetica-Bold", fontSize=17, leading=20, textColor=colors.HexColor("#0f172a"), spaceAfter=6),
        "Heading2": ParagraphStyle("Heading2De", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=colors.HexColor("#1e3a8a"), spaceAfter=4),
        "Subheading": ParagraphStyle("SubheadingDe", parent=base["Normal"], fontName="Helvetica", fontSize=9, textColor=colors.HexColor("#475569")),
        "BatteryTitle": ParagraphStyle("BatteryTitle", parent=base["Normal"], fontName="Helvetica", fontSize=15, leading=20, textColor=colors.HexColor("#1e3a8a")),
        "BodyText": ParagraphStyle("BodyDe", parent=base["BodyText"], fontName="Helvetica", fontSize=9, leading=12),
        "Small": ParagraphStyle("SmallDe", parent=base["BodyText"], fontName="Helvetica", fontSize=8, leading=10),
    }


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _date(value: Any) -> str:
    if not value:
        return "–"
    try:
        return datetime.fromisoformat(str(value)).strftime("%d.%m.%Y")
    except ValueError:
        return str(value)


def _date_time(value: Any) -> str:
    if not value:
        return "–"
    try:
        return datetime.fromisoformat(str(value)).strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return str(value)


def _number(value: Any, decimals: int = 1) -> str:
    if value is None:
        return "–"
    return f"{float(value):.{decimals}f}".replace(".", ",")


def _unit(value: Any, unit: str, *, decimals: int = 0) -> str:
    return "–" if value is None else f"{_number(value, decimals)} {unit}"


def _percent(value: Any) -> str:
    return "–" if value is None else f"{_number(value, 1)} %"
