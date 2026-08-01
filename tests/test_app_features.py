from datetime import UTC, datetime, timedelta

from httpx import ASGITransport, AsyncClient

from mc3000_control import __release_notes__, __version__
from mc3000_control.app import create_app
from mc3000_control.battery_manager import BatteryValues

ADDRESS = "AA:BB:CC:DD:EE:FF"


async def test_health_and_interface_expose_version_fixes(tmp_path) -> None:
    app = create_app(data_dir=tmp_path, scan_timeout=0.01)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            health = await client.get("/api/health")
            interface = await client.get("/")
            login = await client.get("/login")
            script = await client.get("/static/app.js")
            removed_workshop = await client.get("/api/workshop")

    assert health.status_code == 200
    assert health.json()["version"] == __version__
    assert health.json()["fixes"] == list(__release_notes__)
    assert health.json()["archived_battery_retention_days"] == 30
    assert 'id="versionBadge"' in interface.text
    assert 'id="appFixes"' in interface.text
    assert 'id="settingsPhaseOpacity"' in interface.text
    assert 'id="settingsTheme"' in interface.text
    assert 'document.documentElement.dataset.theme' in interface.text
    assert 'document.documentElement.dataset.theme' in login.text
    assert "workshopView" not in interface.text
    assert "loadWorkshop" not in script.text
    assert removed_workshop.status_code == 404
    assert "runPhaseBands(data)" not in script.text
    assert "runPhaseAnnotations(data).phaseBands" in script.text
    assert "enableBackdropClose(dialog)" in script.text
    assert "[elements.curveDialog, elements.runChartDialog]" in script.text
    assert 'class="battery-list-result"' in script.text
    assert "<small>Kapazität ${measuredCapacity" in script.text
    assert "Soll/Ist ${formatNumber(capacityRatio, 1)} %" in script.text
    assert "Noch keine Messung" in script.text
    assert "assignedBatteryIdsExcept" in script.text
    assert "refreshDeviceConfigurationBatteryOptions" in script.text
    assert "unavailableBatteryIds.has" in script.text
    assert "Messwerte bleiben danach noch" in script.text
    assert "archivedBatteryRetentionDays" in script.text
    assert "historyPhaseAnnotations(points)" in script.text
    assert "drawSparklinePhaseBands" in script.text
    assert "chartPalette()" in script.text
    assert "applyTheme(settings.theme)" in script.text
    assert "Lüfterregelung ${fanModeLabel(device.basic.fan_mode)}" in script.text
    assert '0: "Automatik"' in script.text
    assert "Max. Slottemperatur" not in script.text


def slot(active: bool, capacity_mah: int, resistance_mohm: int) -> dict:
    return {
        "battery_type_code": 0,
        "mode_code": 3,
        "cycle_count": 0,
        "status_code": 1 if active else 0,
        "active": active,
        "time_s": 0 if active else 2,
        "voltage_v": 3.7,
        "current_a": 1.0 if active else 0.0,
        "capacity_mah": capacity_mah,
        "temperature_c": 28,
        "resistance_mohm": resistance_mohm,
    }


async def test_reports_pack_builder_qr_notifications_and_backup(tmp_path) -> None:
    app = create_app(data_dir=tmp_path, scan_timeout=0.01)
    async with app.router.lifespan_context(app):
        now = datetime.now(UTC)
        batteries = []
        for index, (capacity, resistance) in enumerate(
            ((1900, 31), (1890, 32)),
            start=1,
        ):
            battery = app.state.batteries.save(
                BatteryValues(
                    code=f"00{index}",
                    name="",
                    battery_type_code=0,
                    nominal_capacity_mah=2000,
                    notes="",
                )
            )
            run_ids = app.state.measurements.record_snapshot(
                ADDRESS,
                now.isoformat(),
                [slot(True, 100, resistance), None, None, None],
                [None, None, None, None],
                {},
                {1: battery.id},
            )
            app.state.measurements.record_snapshot(
                ADDRESS,
                (now + timedelta(seconds=2)).isoformat(),
                [slot(False, capacity, resistance), None, None, None],
                run_ids,
                {},
                {1: battery.id},
            )
            batteries.append(battery)

        run_id = app.state.measurements.list_runs(battery_id=batteries[0].id)[0]["id"]
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            report = await client.get(f"/api/recordings/runs/{run_id}/report")
            chart = await client.get(f"/api/recordings/runs/{run_id}/chart")
            pack = await client.post(
                "/api/batteries/pack-builder",
                json={
                    "battery_ids": [battery.id for battery in batteries],
                    "cells_per_group": 2,
                },
            )
            qr = await client.get(f"/api/batteries/{batteries[0].id}/qr.svg")
            sheet_pdf = await client.get(
                f"/api/batteries/{batteries[0].id}/sheet.pdf"
            )
            report_pdf = await client.get(
                f"/api/recordings/runs/{run_id}/report.pdf"
            )
            notifications = await client.get("/api/notifications")
            backup = await client.get("/api/admin/backup")
            deleted = await client.delete(f"/api/recordings/runs/{run_id}")
            missing = await client.get(f"/api/recordings/runs/{run_id}/report")

        assert report.status_code == 200
        assert report.json()["battery_code"] == "001"
        assert chart.status_code == 200
        assert chart.json()["minutes_before"] == 5
        assert chart.json()["minutes_after"] == 60
        assert chart.json()["total_points"] == 4
        assert chart.json()["capacity_target_mah"] == 2000
        assert chart.json()["capacity_actual_mah"] == 1900
        assert chart.json()["capacity_ratio_percent"] == 95.0
        assert pack.status_code == 200
        assert pack.json()["groups"][0]["within_limits"] is True
        assert qr.status_code == 200
        assert qr.headers["content-type"].startswith("image/svg+xml")
        assert b"<svg" in qr.content
        assert sheet_pdf.status_code == 200
        assert sheet_pdf.content.startswith(b"%PDF")
        assert report_pdf.status_code == 200
        assert report_pdf.content.startswith(b"%PDF")
        assert notifications.json()["unread_count"] == 2
        assert backup.status_code == 200
        assert backup.content.startswith(b"PK")
        assert deleted.status_code == 200
        assert deleted.json()["deleted"]["measurements"] == 2
        assert deleted.json()["deleted"]["notifications"] == 1
        assert missing.status_code == 404


async def test_numbered_battery_api_uses_next_numeric_code(tmp_path) -> None:
    app = create_app(data_dir=tmp_path, scan_timeout=0.01)
    async with app.router.lifespan_context(app):
        archived = app.state.batteries.save(
            BatteryValues(
                code="009",
                name="",
                battery_type_code=0,
                nominal_capacity_mah=2000,
                notes="",
            )
        )
        app.state.batteries.archive(archived.id)
        app.state.batteries.save(
            BatteryValues(
                code="WERKBANK",
                name="",
                battery_type_code=0,
                nominal_capacity_mah=2000,
                notes="",
            )
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            first = await client.post(
                "/api/batteries/numbered",
                json={
                    "battery_type_code": 0,
                    "nominal_capacity_mah": 2500,
                },
            )
            second = await client.post(
                "/api/batteries/numbered",
                json={
                    "battery_type_code": 1,
                    "nominal_capacity_mah": 1800,
                },
            )

        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        assert first.json()["battery"]["code"] == "010"
        assert first.json()["battery"]["nominal_capacity_mah"] == 2500
        assert first.json()["battery"]["standard_time_limit_min"] == 360
        assert second.json()["battery"]["code"] == "011"
        assert second.json()["battery"]["battery_type_code"] == 1


async def test_archived_battery_can_be_permanently_deleted_with_confirmation(
    tmp_path,
) -> None:
    app = create_app(data_dir=tmp_path, scan_timeout=0.01)
    async with app.router.lifespan_context(app):
        battery = app.state.batteries.save(
            BatteryValues(
                code="006",
                name="Fehlanlage",
                battery_type_code=0,
                nominal_capacity_mah=3000,
                notes="",
            )
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            active = await client.request(
                "DELETE",
                f"/api/batteries/{battery.id}/permanent",
                json={"confirmation": "006"},
            )
            archived = await client.delete(f"/api/batteries/{battery.id}")
            wrong = await client.request(
                "DELETE",
                f"/api/batteries/{battery.id}/permanent",
                json={"confirmation": "007"},
            )
            deleted = await client.request(
                "DELETE",
                f"/api/batteries/{battery.id}/permanent",
                json={"confirmation": "006"},
            )
            recreated = await client.post(
                "/api/batteries",
                json={
                    "code": "006",
                    "name": "Korrekte Anlage",
                    "battery_type_code": 0,
                    "nominal_capacity_mah": 3000,
                    "notes": "",
                },
            )

        assert active.status_code == 409
        assert archived.status_code == 200
        assert wrong.status_code == 400
        assert deleted.status_code == 200
        assert deleted.json()["battery_code"] == "006"
        assert recreated.status_code == 200, recreated.text
        assert recreated.json()["battery"]["code"] == "006"


async def test_device_removal_api_protects_active_program(tmp_path) -> None:
    app = create_app(data_dir=tmp_path, scan_timeout=0.01)
    async with app.router.lifespan_context(app):
        registration = app.state.manager.registry.save(ADDRESS, "Werkbank")
        session = app.state.manager._ensure_session(registration)
        session.slots[0] = {"active": True}

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            protected = await client.delete(f"/api/devices/{ADDRESS}")
            session.slots[0] = {"active": False}
            removed = await client.delete(f"/api/devices/{ADDRESS}")

        assert protected.status_code == 409
        assert "laufenden Programms" in protected.json()["detail"]
        assert removed.status_code == 200
        assert removed.json()["removed"] == {
            "address": ADDRESS,
            "alias": "Werkbank",
        }
        assert app.state.manager.registry.get(ADDRESS) is None
