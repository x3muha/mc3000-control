import io
import json
import zipfile

from httpx import ASGITransport, AsyncClient

from mc3000_control import __version__
from mc3000_control.app import create_app
from mc3000_control.diagnostics import create_diagnostics


async def test_profile_exchange_round_trip_and_limits(tmp_path) -> None:
    app = create_app(data_dir=tmp_path, scan_timeout=0.01)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            exported = await client.get("/api/profiles/export")
            imported = await client.post(
                "/api/profiles/import",
                content=exported.content,
                headers={"Content-Type": "application/json"},
            )
            oversized = await client.post(
                "/api/profiles/import",
                content=b"x" * 1_000_001,
                headers={"Content-Type": "application/json"},
            )

    payload = exported.json()
    assert exported.status_code == 200
    assert payload["format"] == "mc3000-control-profiles"
    assert payload["format_version"] == 1
    assert payload["application_version"] == __version__
    assert imported.status_code == 200
    assert imported.json()["imported"]["profiles"] == len(payload["profiles"])
    assert oversized.status_code == 413


def test_diagnostics_redacts_private_identifiers() -> None:
    address = "AA:BB:CC:DD:EE:FF"
    content = create_diagnostics(
        version="1.0.0",
        manager_payload={
            "devices": [
                {
                    "address": address,
                    "alias": "Private workbench",
                    "serial_number": "SECRET-SERIAL",
                    "state": "connected",
                    "connected": True,
                    "enabled": True,
                    "released": False,
                    "error": f"failed at {address} from 192.168.1.23",
                    "version": {"firmware": "1.25", "hardware": "2.2"},
                    "basic": {"input_voltage_v": 12.1, "fan_mode": 0},
                    "slots": [{"slot": 1, "status_code": 0, "active": False}],
                }
            ]
        },
        profile_count=3,
        battery_count=4,
        run_count=5,
    )
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = set(archive.namelist())
        combined = "\n".join(
            archive.read(name).decode("utf-8") for name in names
        )
        data = json.loads(archive.read("diagnostics.json"))

    assert names == {"diagnostics.json", "recent.log", "README.txt"}
    assert address not in combined
    assert "192.168.1.23" not in combined
    assert "Private workbench" not in combined
    assert "SECRET-SERIAL" not in combined
    assert data["devices"][0]["id"] == "device-1"
    assert data["privacy"]["database"] == "not_included"


async def test_security_headers_login_rate_limit_and_pwa(tmp_path) -> None:
    app = create_app(data_dir=tmp_path, scan_timeout=0.01)
    async with app.router.lifespan_context(app):
        app.state.profiles.set_app_setting("auth_enabled", "1")
        app.state.profiles.set_app_setting("auth_username", "admin")
        app.state.profiles.set_app_setting("auth_password", "invalid-record")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            cross_origin = await client.post(
                "/api/auth/login",
                json={"username": "admin", "password": "wrong-password"},
                headers={"Origin": "https://attacker.invalid"},
            )
            auth_status = await client.get("/api/auth/status")
            responses = [
                await client.post(
                    "/api/auth/login",
                    json={"username": "admin", "password": "wrong-password"},
                )
                for _ in range(6)
            ]
            manifest = await client.get("/manifest.webmanifest")
            worker = await client.get("/sw.js")
            demo = await client.get("/static/demo.js")
            interface = await client.get("/")

    assert cross_origin.status_code == 403
    assert auth_status.json() == {"enabled": True}
    assert [response.status_code for response in responses[:5]] == [401] * 5
    assert responses[5].status_code == 429
    assert responses[5].headers["retry-after"] == "300"
    assert manifest.status_code == 200
    assert manifest.json()["display"] == "standalone"
    assert worker.status_code == 200
    assert "url.pathname.startsWith(\"/api/\")" in worker.text
    assert "Demo mode is read-only" in demo.text
    assert interface.headers["x-frame-options"] == "DENY"
    assert interface.headers["x-content-type-options"] == "nosniff"
    assert "object-src 'none'" in interface.headers["content-security-policy"]
