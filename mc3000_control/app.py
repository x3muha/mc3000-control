from __future__ import annotations

import asyncio
import hashlib
import hmac
import io
import json
import logging
import os
import secrets
import signal
import time
from contextlib import asynccontextmanager, suppress
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import segno
import uvicorn
from fastapi import (
    FastAPI,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __release_notes__, __version__
from .backup import BackupError, create_backup, restore_backup
from .battery_manager import (
    AutomaticProgramValues,
    BatteryError,
    BatteryValues,
    battery_options_payload,
    build_automatic_profile,
    build_standard_profile,
)
from .ble import DeviceManager, DeviceSession
from .cell_catalog import (
    CATALOG_SOURCES,
    CellCatalogStore,
    import_catalog_sources,
)
from .diagnostics import create_diagnostics, install_log_collector
from .pack_builder import PackBuilderError, build_cell_groups
from .profile_exchange import (
    MAX_IMPORT_BYTES,
    ProfileExchangeError,
    export_profiles,
    import_profiles,
)
from .profiles import (
    DEFAULT_MANUAL_TIME_LIMIT_MIN,
    ProfileError,
    ProfileValues,
    build_profile_packet,
    profile_options_payload,
)
from .registry import DeviceRegistry
from .reports import battery_sheet_pdf, run_report_pdf
from .storage import BatteryStore, MeasurementStore, ProfileStore

LOGGER = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).with_name("static")
install_log_collector()


class EnrollRequest(BaseModel):
    address: str
    alias: str = Field(min_length=1, max_length=60)


class RenameRequest(BaseModel):
    alias: str = Field(min_length=1, max_length=60)


class DeviceDetailsRequest(BaseModel):
    alias: str = Field(min_length=1, max_length=60)
    serial_number: str = Field(default="", max_length=80)


class ProfileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)
    battery_type_code: int
    mode_code: int
    capacity_mah: int
    charge_current_ma: int
    discharge_current_ma: int
    charge_voltage_mv: int
    discharge_voltage_mv: int
    charge_end_current_ma: int
    discharge_end_current_ma: int
    charge_rest_min: int
    discharge_rest_min: int
    cycle_count: int
    cycle_mode: int
    delta_peak_mv: int
    trickle_current_ma: int
    keep_voltage_mv: int
    temp_limit_c: int
    time_limit_min: int = DEFAULT_MANUAL_TIME_LIMIT_MIN
    time_limit_mode: str = Field(
        default="manual",
        pattern="^(automatic|manual|off)$",
    )
    category_key: str = Field(default="general", max_length=80)

    def to_values(self) -> ProfileValues:
        return ProfileValues(**self.model_dump(exclude={"category_key"}))


class AutomaticProfileRequest(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)
    mode_code: int
    charge_c_rate: float
    discharge_c_rate: float
    cycle_count: int = Field(default=1, ge=1, le=99)
    cycle_mode: int = Field(default=0, ge=0, le=3)
    charge_rest_min: int = Field(default=0, ge=0, le=240)
    discharge_rest_min: int = Field(default=0, ge=0, le=240)
    temp_limit_c: int = Field(default=45, ge=0, le=70)
    time_limit_mode: str = Field(
        default="manual",
        pattern="^(automatic|manual|off)$",
    )
    time_limit_min: int = Field(
        default=DEFAULT_MANUAL_TIME_LIMIT_MIN,
        ge=0,
        le=1440,
    )
    category_key: str = Field(default="automatic", max_length=80)

    def to_values(self) -> AutomaticProgramValues:
        return AutomaticProgramValues(
            **self.model_dump(exclude={"category_key"})
        )


class ApplyProfileRequest(BaseModel):
    address: str
    slots: list[int] = Field(min_length=1, max_length=4)
    confirmation: str


class BatteryRequest(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(default="", max_length=80)
    battery_type_code: int
    nominal_capacity_mah: int
    notes: str = Field(default="", max_length=1000)
    manufacturer: str = Field(default="", max_length=80)
    model: str = Field(default="", max_length=80)
    form_factor: str = Field(default="", max_length=40)
    origin: str = Field(default="", max_length=120)
    in_service_since: str = Field(default="", max_length=10)
    protected: bool = False
    chemistry_detail: str = Field(default="", max_length=80)
    weight_g: float | None = None
    nominal_voltage_v: float | None = None
    min_voltage_v: float | None = None
    max_voltage_v: float | None = None
    max_charge_current_a: float | None = None
    max_discharge_current_a: float | None = None
    cycle_life: int | None = None
    manufacture_year: int | None = None
    dimensions: str = Field(default="", max_length=120)
    data_source_name: str = Field(default="", max_length=120)
    data_source_url: str = Field(default="", max_length=1000)
    data_source_retrieved_at: str = Field(default="", max_length=40)
    technical_notes: str = Field(default="", max_length=4000)
    technical_data: dict[str, str] = Field(default_factory=dict)
    archived: bool = False

    def to_values(self, standard: BatteryValues | None = None) -> BatteryValues:
        values = BatteryValues(**self.model_dump())
        if standard is None:
            return values
        return replace(
            values,
            standard_mode_code=standard.standard_mode_code,
            standard_charge_c_rate=standard.standard_charge_c_rate,
            standard_discharge_c_rate=standard.standard_discharge_c_rate,
            standard_cycle_count=standard.standard_cycle_count,
            standard_cycle_mode=standard.standard_cycle_mode,
            standard_time_limit_mode=standard.standard_time_limit_mode,
            standard_time_limit_min=standard.standard_time_limit_min,
        )


class NumberedBatteryRequest(BaseModel):
    battery_type_code: int
    nominal_capacity_mah: int = Field(ge=100, le=50000)


class CellCatalogImportRequest(BaseModel):
    sources: list[str] = Field(min_length=1, max_length=len(CATALOG_SOURCES))


class PermanentBatteryDeleteRequest(BaseModel):
    confirmation: str = Field(min_length=1, max_length=32)


class StandardProgramRequest(BaseModel):
    mode_code: int
    charge_c_rate: float
    discharge_c_rate: float
    cycle_count: int = Field(default=1, ge=1, le=99)
    cycle_mode: int = Field(default=0, ge=0, le=3)
    time_limit_mode: str = Field(
        default="manual",
        pattern="^(automatic|manual|off)$",
    )
    time_limit_min: int = Field(
        default=DEFAULT_MANUAL_TIME_LIMIT_MIN,
        ge=0,
        le=1440,
    )


class SlotConfigurationRequest(BaseModel):
    battery_id: int | None = None
    create_battery: bool = False
    program_source: str = Field(pattern="^(standard|profile|automatic)$")
    profile_id: int | None = None
    automatic_program: str | None = None
    capacity_mah: int | None = Field(default=None, ge=0, le=50000)
    time_limit_mode: str | None = Field(
        default=None,
        pattern="^(automatic|manual|off)$",
    )
    time_limit_min: int | None = Field(
        default=None,
        ge=0,
        le=1440,
    )


class BulkSlotAssignment(BaseModel):
    slot: int = Field(ge=1, le=4)
    battery_id: int | None = None
    create_battery: bool = False
    capacity_mah: int | None = Field(default=None, ge=0, le=50000)


class BulkConfigurationRequest(BaseModel):
    slots: list[BulkSlotAssignment] = Field(min_length=1, max_length=4)
    program_source: str = Field(pattern="^(standard|profile|automatic)$")
    profile_id: int | None = None
    automatic_program: str | None = None
    time_limit_mode: str | None = Field(
        default=None,
        pattern="^(automatic|manual|off)$",
    )
    time_limit_min: int | None = Field(
        default=None,
        ge=0,
        le=1440,
    )


class SettingsRequest(BaseModel):
    default_program: str = Field(default="", max_length=80)
    phase_opacity_percent: int | None = Field(default=None, ge=15, le=25)
    theme: str | None = Field(default=None, pattern="^(system|light|dark)$")
    login_enabled: bool | None = None
    login_username: str = Field(default="", max_length=80)
    login_password: str = Field(default="", max_length=200)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class ProfileCategoryRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class PackBuilderRequest(BaseModel):
    battery_ids: list[int] = Field(min_length=2, max_length=64)
    cells_per_group: int = Field(ge=2, le=16)
    group_count: int = Field(default=1, ge=1, le=16)
    max_capacity_spread_percent: float = Field(default=5, gt=0, le=50)
    max_resistance_spread_percent: float = Field(default=20, gt=0, le=100)


class NotificationReadRequest(BaseModel):
    notification_ids: list[int] = Field(min_length=1, max_length=200)


def create_app(
    *,
    data_dir: str | Path | None = None,
    scan_timeout: float | None = None,
) -> FastAPI:
    resolved_data_dir = Path(
        data_dir or os.environ.get("MC3000_DATA_DIR", "./data")
    ).resolve()
    resolved_scan_timeout = (
        scan_timeout
        if scan_timeout is not None
        else float(os.environ.get("MC3000_SCAN_TIMEOUT", "8"))
    )
    retention_days = max(1, int(os.environ.get("MC3000_RETENTION_DAYS", "90")))
    archived_battery_retention_days = max(
        1,
        int(os.environ.get("MC3000_ARCHIVED_BATTERY_RETENTION_DAYS", "30")),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database_path = resolved_data_dir / "mc3000-control.db"
        registry = DeviceRegistry(database_path)
        profile_store = ProfileStore(database_path)
        battery_store = BatteryStore(database_path)
        cell_catalog_store = CellCatalogStore(database_path)
        measurement_store = MeasurementStore(database_path)

        async def purge_expired_measurements() -> None:
            now = datetime.now(UTC)
            deleted = await asyncio.to_thread(
                measurement_store.purge_before,
                (now - timedelta(days=retention_days)).isoformat(),
                archived_battery_cutoff=(
                    now - timedelta(days=archived_battery_retention_days)
                ).isoformat(),
            )
            if deleted:
                LOGGER.info("Expired %s measurement records", deleted)

        async def retention_loop() -> None:
            while True:
                await asyncio.sleep(6 * 60 * 60)
                await purge_expired_measurements()

        await purge_expired_measurements()
        manager = DeviceManager(
            registry,
            profile_store,
            battery_store,
            measurement_store,
            scan_timeout=resolved_scan_timeout,
            active_record_interval=float(
                os.environ.get("MC3000_RECORD_ACTIVE_INTERVAL", "2")
            ),
            idle_record_interval=float(
                os.environ.get("MC3000_RECORD_IDLE_INTERVAL", "30")
            ),
        )
        app.state.manager = manager
        app.state.profiles = profile_store
        app.state.batteries = battery_store
        app.state.cell_catalog = cell_catalog_store
        app.state.measurements = measurement_store
        app.state.database_path = database_path
        app.state.data_dir = resolved_data_dir
        retention_task: asyncio.Task | None = None
        try:
            await manager.start()
            retention_task = asyncio.create_task(
                retention_loop(),
                name="mc3000-retention",
            )
            yield
        finally:
            if retention_task is not None:
                retention_task.cancel()
                with suppress(asyncio.CancelledError):
                    await retention_task
            await manager.stop()

    app = FastAPI(
        title="Open MC3000 Control",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )
    failed_logins: dict[str, list[float]] = {}

    async def security_headers(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin and not _origin_matches_host(origin, request.headers.get("host", "")):
                return JSONResponse(
                    {"detail": "Anfrage von einer fremden Herkunft wurde abgelehnt"},
                    status_code=403,
                )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; connect-src 'self' ws: wss:; "
            "img-src 'self' data:; script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        )
        return response

    @app.middleware("http")
    async def login_guard(request: Request, call_next):
        public_paths = {
            "/login",
            "/api/auth/status",
            "/api/auth/login",
            "/api/health",
            "/manifest.webmanifest",
            "/sw.js",
        }
        if request.url.path in public_paths or request.url.path.startswith("/static/"):
            return await call_next(request)
        enabled = await asyncio.to_thread(
            app.state.profiles.get_app_setting,
            "auth_enabled",
            "0",
        )
        if enabled != "1":
            return await call_next(request)
        secret = await asyncio.to_thread(
            app.state.profiles.get_app_setting,
            "auth_session_secret",
            "",
        )
        if _valid_session_cookie(
            request.cookies.get("mc3000_session", ""),
            secret,
        ):
            return await call_next(request)
        if request.url.path.startswith("/api/"):
            return JSONResponse(
                {"detail": "Anmeldung erforderlich"},
                status_code=401,
            )
        return RedirectResponse("/login", status_code=303)

    app.middleware("http")(security_headers)

    @app.get("/login", response_class=HTMLResponse)
    async def login_page() -> str:
        return _login_page()

    @app.get("/api/auth/status")
    async def auth_status() -> dict:
        enabled = await asyncio.to_thread(
            app.state.profiles.get_app_setting,
            "auth_enabled",
            "0",
        )
        return {"enabled": enabled == "1"}

    @app.post("/api/auth/login")
    async def login(request: Request, credentials: LoginRequest) -> Response:
        client_key = request.client.host if request.client else "unknown"
        now = time.monotonic()
        recent_failures = [
            value for value in failed_logins.get(client_key, []) if now - value < 300
        ]
        failed_logins[client_key] = recent_failures
        enabled, username, password_record, secret = await asyncio.gather(
            asyncio.to_thread(
                app.state.profiles.get_app_setting,
                "auth_enabled",
                "0",
            ),
            asyncio.to_thread(
                app.state.profiles.get_app_setting,
                "auth_username",
                "",
            ),
            asyncio.to_thread(
                app.state.profiles.get_app_setting,
                "auth_password",
                "",
            ),
            asyncio.to_thread(
                app.state.profiles.get_app_setting,
                "auth_session_secret",
                "",
            ),
        )
        if enabled != "1":
            failed_logins.pop(client_key, None)
            return JSONResponse({"ok": True, "enabled": False})
        if len(recent_failures) >= 5:
            return JSONResponse(
                {"detail": "Zu viele Anmeldeversuche. Bitte später erneut versuchen."},
                status_code=429,
                headers={"Retry-After": "300"},
            )
        username_valid = hmac.compare_digest(credentials.username, username)
        password_valid = _verify_password(credentials.password, password_record)
        if not (username_valid and password_valid):
            recent_failures.append(now)
            raise HTTPException(
                status_code=401,
                detail="Benutzername oder Passwort ist falsch",
            )
        failed_logins.pop(client_key, None)
        if not secret:
            secret = secrets.token_hex(32)
            await asyncio.to_thread(
                app.state.profiles.set_app_setting,
                "auth_session_secret",
                secret,
            )
        response = JSONResponse({"ok": True, "enabled": True})
        response.set_cookie(
            "mc3000_session",
            _session_cookie(secret),
            max_age=30 * 24 * 60 * 60,
            httponly=True,
            samesite="strict",
            secure=request.url.scheme == "https",
        )
        return response

    @app.post("/api/auth/logout")
    async def logout() -> Response:
        response = JSONResponse({"ok": True})
        response.delete_cookie("mc3000_session")
        return response

    @app.get("/api/health")
    async def health() -> dict:
        return {
            "ok": True,
            "version": __version__,
            "fixes": list(__release_notes__),
            "archived_battery_retention_days": archived_battery_retention_days,
        }

    @app.get("/api/state")
    async def state() -> dict:
        return app.state.manager.payload()

    @app.get("/api/settings")
    async def settings() -> dict:
        (
            default_program,
            phase_opacity,
            theme,
            login_enabled,
            login_username,
        ) = await asyncio.gather(
            asyncio.to_thread(
                app.state.profiles.get_app_setting,
                "default_program",
                "",
            ),
            asyncio.to_thread(
                app.state.profiles.get_app_setting,
                "phase_opacity_percent",
                "15",
            ),
            asyncio.to_thread(
                app.state.profiles.get_app_setting,
                "theme",
                "system",
            ),
            asyncio.to_thread(
                app.state.profiles.get_app_setting,
                "auth_enabled",
                "0",
            ),
            asyncio.to_thread(
                app.state.profiles.get_app_setting,
                "auth_username",
                "",
            ),
        )
        return {
            "default_program": default_program,
            "phase_opacity_percent": _phase_opacity_percent(phase_opacity),
            "theme": _theme_preference(theme),
            "login_enabled": login_enabled == "1",
            "login_username": login_username,
        }

    @app.put("/api/settings")
    async def update_settings(request: SettingsRequest) -> dict:
        automatic_profiles = await asyncio.to_thread(
            app.state.profiles.list_automatic
        )
        allowed = {
            "",
            "standard",
            *(f"automatic:{program.key}" for program in automatic_profiles),
        }
        if request.default_program not in allowed:
            raise HTTPException(
                status_code=400,
                detail="Unbekanntes Standardprogramm für neue Slots",
            )
        await asyncio.to_thread(
            app.state.profiles.set_app_setting,
            "default_program",
            request.default_program,
        )
        (
            current_phase_opacity,
            current_theme,
            current_enabled,
            current_username,
        ) = await asyncio.gather(
            asyncio.to_thread(
                app.state.profiles.get_app_setting,
                "phase_opacity_percent",
                "15",
            ),
            asyncio.to_thread(
                app.state.profiles.get_app_setting,
                "theme",
                "system",
            ),
            asyncio.to_thread(
                app.state.profiles.get_app_setting,
                "auth_enabled",
                "0",
            ),
            asyncio.to_thread(
                app.state.profiles.get_app_setting,
                "auth_username",
                "",
            ),
        )
        phase_opacity_percent = (
            request.phase_opacity_percent
            if request.phase_opacity_percent is not None
            else _phase_opacity_percent(current_phase_opacity)
        )
        if request.phase_opacity_percent is not None:
            await asyncio.to_thread(
                app.state.profiles.set_app_setting,
                "phase_opacity_percent",
                str(phase_opacity_percent),
            )
        theme = request.theme or _theme_preference(current_theme)
        if request.theme is not None:
            await asyncio.to_thread(
                app.state.profiles.set_app_setting,
                "theme",
                theme,
            )
        username = request.login_username.strip() or current_username
        effective_login_enabled = current_enabled == "1"
        if request.login_enabled is True:
            if not username:
                raise HTTPException(
                    status_code=400,
                    detail="Für den Login ist ein Benutzername erforderlich",
                )
            existing_password = await asyncio.to_thread(
                app.state.profiles.get_app_setting,
                "auth_password",
                "",
            )
            if not request.login_password and not existing_password:
                raise HTTPException(
                    status_code=400,
                    detail="Für den ersten Login ist ein Passwort erforderlich",
                )
            if request.login_password and len(request.login_password) < 8:
                raise HTTPException(
                    status_code=400,
                    detail="Das Passwort muss mindestens 8 Zeichen lang sein",
                )
            await asyncio.to_thread(
                app.state.profiles.set_app_setting,
                "auth_username",
                username,
            )
            if request.login_password:
                await asyncio.to_thread(
                    app.state.profiles.set_app_setting,
                    "auth_password",
                    _hash_password(request.login_password),
                )
                await asyncio.to_thread(
                    app.state.profiles.set_app_setting,
                    "auth_session_secret",
                    secrets.token_hex(32),
                )
            await asyncio.to_thread(
                app.state.profiles.set_app_setting,
                "auth_enabled",
                "1",
            )
            effective_login_enabled = True
        elif request.login_enabled is False:
            await asyncio.to_thread(
                app.state.profiles.set_app_setting,
                "auth_enabled",
                "0",
            )
            effective_login_enabled = False
        return {
            "ok": True,
            "default_program": request.default_program,
            "phase_opacity_percent": phase_opacity_percent,
            "theme": theme,
            "login_enabled": effective_login_enabled,
            "login_username": username,
        }

    @app.post("/api/scan")
    async def scan() -> dict:
        try:
            discovered = await app.state.manager.scan()
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {"ok": True, "discovered": discovered}

    @app.post("/api/devices")
    async def enroll(request: EnrollRequest) -> dict:
        try:
            device = await app.state.manager.enroll(request.address, request.alias)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "device": device}

    @app.patch("/api/devices/{address}")
    async def rename(address: str, request: RenameRequest) -> dict:
        try:
            device = await app.state.manager.rename(address, request.alias)
        except KeyError as exc:
            raise HTTPException(
                status_code=404, detail="Gerät ist nicht registriert"
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "device": device}

    @app.put("/api/devices/{address}/details")
    async def update_device_details(
        address: str,
        request: DeviceDetailsRequest,
    ) -> dict:
        try:
            device = await app.state.manager.update_details(
                address,
                alias=request.alias,
                serial_number=request.serial_number,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=404, detail="Gerät ist nicht registriert"
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "device": device}

    @app.post("/api/devices/{address}/release")
    async def release(address: str) -> dict:
        try:
            device = await app.state.manager.set_released(address, True)
        except (KeyError, ValueError) as exc:
            raise HTTPException(
                status_code=404, detail="Gerät ist nicht registriert"
            ) from exc
        return {"ok": True, "device": device}

    @app.post("/api/devices/{address}/resume")
    async def resume(address: str) -> dict:
        try:
            device = await app.state.manager.set_released(address, False)
        except (KeyError, ValueError) as exc:
            raise HTTPException(
                status_code=404, detail="Gerät ist nicht registriert"
            ) from exc
        return {"ok": True, "device": device}

    @app.delete("/api/devices/{address}")
    async def remove_device(address: str) -> dict:
        try:
            removed = await app.state.manager.remove(address)
        except KeyError as exc:
            raise HTTPException(
                status_code=404, detail="Gerät ist nicht registriert"
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"ok": True, "removed": removed}

    @app.post("/api/devices/{address}/slots/{slot}/start")
    async def start_slot(address: str, slot: int) -> dict:
        session = _session_or_404(app, address)
        try:
            return await session.start_slot(slot)
        except (RuntimeError, TimeoutError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/devices/{address}/start-all")
    async def start_all(address: str) -> dict:
        session = _session_or_404(app, address)
        try:
            return await session.start_all()
        except (RuntimeError, TimeoutError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/devices/{address}/slots/{slot}/stop")
    async def stop_slot(address: str, slot: int) -> dict:
        session = _session_or_404(app, address)
        try:
            return await session.stop_slot(slot)
        except (RuntimeError, TimeoutError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/devices/{address}/stop-all")
    async def stop_all(address: str) -> dict:
        session = _session_or_404(app, address)
        try:
            return await session.stop_all()
        except (RuntimeError, TimeoutError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/profiles/options")
    async def profile_options() -> dict:
        return profile_options_payload()

    @app.get("/api/profiles")
    async def profiles() -> dict:
        stored = await asyncio.to_thread(app.state.profiles.list)
        return {"profiles": [profile.to_dict() for profile in stored]}

    @app.get("/api/profiles/export")
    async def download_profiles() -> Response:
        payload = await asyncio.to_thread(
            export_profiles,
            app.state.profiles,
            application_version=__version__,
        )
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        return Response(
            content=json.dumps(payload, ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="mc3000-profiles-{timestamp}.json"'
                ),
                "Cache-Control": "no-store",
            },
        )

    @app.post("/api/profiles/import")
    async def upload_profiles(request: Request) -> dict:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                declared_size = int(content_length)
            except ValueError as exc:
                raise HTTPException(
                    status_code=400,
                    detail="Ungültige Content-Length",
                ) from exc
            if declared_size > MAX_IMPORT_BYTES:
                raise HTTPException(status_code=413, detail="Die Importdatei ist zu groß")
        content = await request.body()
        if len(content) > MAX_IMPORT_BYTES:
            raise HTTPException(status_code=413, detail="Die Importdatei ist zu groß")
        try:
            payload = json.loads(content)
            result = await asyncio.to_thread(
                import_profiles,
                app.state.profiles,
                payload,
            )
        except (json.JSONDecodeError, UnicodeDecodeError, ProfileExchangeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "imported": result}

    @app.get("/api/profile-categories")
    async def profile_categories() -> dict:
        categories = await asyncio.to_thread(
            app.state.profiles.list_categories
        )
        return {"categories": categories}

    @app.post("/api/profile-categories")
    async def create_profile_category(request: ProfileCategoryRequest) -> dict:
        try:
            category = await asyncio.to_thread(
                app.state.profiles.create_category,
                request.name,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "category": category}

    @app.delete("/api/profile-categories/{category_key}")
    async def delete_profile_category(category_key: str) -> dict:
        try:
            await asyncio.to_thread(
                app.state.profiles.delete_category,
                category_key,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=404, detail="Profilkategorie wurde nicht gefunden"
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"ok": True}

    @app.post("/api/profiles")
    async def create_profile(request: ProfileRequest) -> dict:
        try:
            stored = await asyncio.to_thread(
                app.state.profiles.save,
                request.to_values(),
                category_key=request.category_key,
            )
        except (ProfileError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "profile": stored.to_dict()}

    @app.put("/api/profiles/{profile_id}")
    async def update_profile(profile_id: int, request: ProfileRequest) -> dict:
        try:
            stored = await asyncio.to_thread(
                app.state.profiles.save,
                request.to_values(),
                profile_id=profile_id,
                category_key=request.category_key,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=404, detail="Profil wurde nicht gefunden"
            ) from exc
        except (ProfileError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "profile": stored.to_dict()}

    @app.delete("/api/profiles/{profile_id}")
    async def delete_profile(profile_id: int) -> dict:
        try:
            await asyncio.to_thread(app.state.profiles.delete, profile_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=404, detail="Profil wurde nicht gefunden"
            ) from exc
        return {"ok": True}

    @app.post("/api/automatic-profiles")
    async def create_automatic_profile(
        request: AutomaticProfileRequest,
    ) -> dict:
        try:
            stored = await asyncio.to_thread(
                app.state.profiles.save_automatic,
                request.to_values(),
                category_key=request.category_key,
            )
        except (BatteryError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "profile": stored.to_dict()}

    @app.put("/api/automatic-profiles/{program_key}")
    async def update_automatic_profile(
        program_key: str,
        request: AutomaticProfileRequest,
    ) -> dict:
        try:
            stored = await asyncio.to_thread(
                app.state.profiles.save_automatic,
                request.to_values(),
                program_key=program_key,
                category_key=request.category_key,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail="Automatikprofil wurde nicht gefunden",
            ) from exc
        except (BatteryError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "profile": stored.to_dict()}

    @app.post("/api/profiles/{profile_id}/apply")
    async def apply_profile(profile_id: int, request: ApplyProfileRequest) -> dict:
        if request.confirmation != "PROFIL ANWENDEN":
            raise HTTPException(
                status_code=400,
                detail="Bestätigung muss exakt 'PROFIL ANWENDEN' lauten",
            )
        stored = await asyncio.to_thread(app.state.profiles.get, profile_id)
        if stored is None:
            raise HTTPException(status_code=404, detail="Profil wurde nicht gefunden")
        clean_slots = sorted(set(request.slots))
        if any(slot not in range(1, 5) for slot in clean_slots):
            raise HTTPException(
                status_code=400, detail="Slot muss zwischen 1 und 4 liegen"
            )
        slot_mask = sum(1 << (slot - 1) for slot in clean_slots)
        session = _session_or_404(app, request.address)
        if not await session.acquire_configuration():
            raise HTTPException(
                status_code=409,
                detail="Für dieses Ladegerät läuft bereits eine Konfiguration",
            )
        try:
            packet = build_profile_packet(stored.values, slot_mask)
            result = await session.apply_profile(packet, clean_slots)
            await asyncio.to_thread(
                app.state.profiles.assign,
                request.address,
                clean_slots,
                profile_id,
            )
            selected_at = datetime.now(UTC).isoformat()
            for slot in clean_slots:
                battery_id = session.snapshot()["battery_ids"].get(slot)
                await asyncio.to_thread(
                    app.state.profiles.set_slot_program,
                    request.address,
                    slot,
                    source="profile",
                    label=stored.values.name,
                    details=stored.to_dict(),
                    battery_id=battery_id,
                    profile_id=profile_id,
                )
            session.mark_profile_applied(
                clean_slots,
                profile_id,
                {
                    "source": "profile",
                    "label": stored.values.name,
                    "details": stored.to_dict(),
                    "battery_id": None,
                    "profile_id": profile_id,
                    "selected_at": selected_at,
                },
            )
            await app.state.manager.publish()
        except (KeyError, ProfileError, RuntimeError, TimeoutError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        finally:
            session.release_configuration()
        return {"ok": True, "profile": stored.to_dict(), "result": result}

    @app.get("/api/batteries/options")
    async def battery_options() -> dict:
        automatic_profiles = await asyncio.to_thread(
            app.state.profiles.list_automatic
        )
        return battery_options_payload(
            [profile.to_dict() for profile in automatic_profiles]
        )

    @app.get("/api/cell-catalog/sources")
    async def cell_catalog_sources() -> dict:
        sources = await asyncio.to_thread(app.state.cell_catalog.source_statuses)
        return {
            "sources": sources,
            "total_entries": sum(source["entry_count"] for source in sources),
        }

    @app.post("/api/cell-catalog/import")
    async def import_cell_catalog(request: CellCatalogImportRequest) -> dict:
        try:
            return await asyncio.to_thread(
                import_catalog_sources,
                app.state.cell_catalog,
                request.sources,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/cell-catalog/search")
    async def search_cell_catalog(
        q: str = Query(min_length=2, max_length=100),
        limit: int = Query(default=20, ge=1, le=50),
    ) -> dict:
        entries = await asyncio.to_thread(
            app.state.cell_catalog.search,
            q,
            limit=limit,
        )
        return {
            "entries": [entry.to_dict() for entry in entries],
            "query": q,
        }

    @app.get("/api/batteries")
    async def batteries(
        include_archived: bool = False,
        code: str | None = None,
    ) -> dict:
        if code is not None:
            stored = await asyncio.to_thread(app.state.batteries.get_by_code, code)
            if stored is None or (stored.values.archived and not include_archived):
                return {"batteries": []}
            batteries_with_stats = [
                await asyncio.to_thread(
                    _battery_with_statistics,
                    app.state.measurements,
                    stored,
                )
            ]
        else:
            stored_batteries = await asyncio.to_thread(
                app.state.batteries.list,
                include_archived=include_archived,
            )
            batteries_with_stats = await asyncio.gather(
                *(
                    asyncio.to_thread(
                        _battery_with_statistics,
                        app.state.measurements,
                        stored,
                    )
                    for stored in stored_batteries
                )
            )
        return {"batteries": batteries_with_stats}

    @app.post("/api/batteries")
    async def create_battery(request: BatteryRequest) -> dict:
        try:
            stored = await asyncio.to_thread(
                app.state.batteries.save,
                request.to_values(),
            )
        except (BatteryError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "ok": True,
            "battery": _battery_with_statistics(
                app.state.measurements,
                stored,
            ),
        }

    @app.post("/api/batteries/numbered")
    async def create_numbered_battery(request: NumberedBatteryRequest) -> dict:
        try:
            stored = await asyncio.to_thread(
                app.state.batteries.create_numbered,
                battery_type_code=request.battery_type_code,
                nominal_capacity_mah=request.nominal_capacity_mah,
            )
        except (BatteryError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "ok": True,
            "battery": _battery_with_statistics(
                app.state.measurements,
                stored,
            ),
        }

    @app.post("/api/batteries/pack-builder")
    async def pack_builder(request: PackBuilderRequest) -> dict:
        selected = []
        for battery_id in dict.fromkeys(request.battery_ids):
            stored = await asyncio.to_thread(app.state.batteries.get, battery_id)
            if stored is None or stored.values.archived:
                raise HTTPException(
                    status_code=404,
                    detail=f"Batterie-ID {battery_id} wurde nicht gefunden",
                )
            selected.append(
                await asyncio.to_thread(
                    _battery_with_statistics,
                    app.state.measurements,
                    stored,
                )
            )
        try:
            return await asyncio.to_thread(
                build_cell_groups,
                selected,
                cells_per_group=request.cells_per_group,
                group_count=request.group_count,
                max_capacity_spread_percent=request.max_capacity_spread_percent,
                max_resistance_spread_percent=request.max_resistance_spread_percent,
            )
        except PackBuilderError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/batteries/{battery_id}")
    async def battery_detail(battery_id: int) -> dict:
        stored = await asyncio.to_thread(app.state.batteries.get, battery_id)
        if stored is None:
            raise HTTPException(status_code=404, detail="Batterie wurde nicht gefunden")
        statistics, runs = await asyncio.gather(
            asyncio.to_thread(app.state.measurements.battery_statistics, battery_id),
            asyncio.to_thread(
                app.state.measurements.list_runs,
                battery_id=battery_id,
                limit=500,
            ),
        )
        return {
            "battery": {**stored.to_dict(), "statistics": statistics},
            "runs": runs,
        }

    @app.put("/api/batteries/{battery_id}")
    async def update_battery(battery_id: int, request: BatteryRequest) -> dict:
        existing = await asyncio.to_thread(app.state.batteries.get, battery_id)
        if existing is None:
            raise HTTPException(
                status_code=404, detail="Batterie wurde nicht gefunden"
            )
        try:
            values = request.to_values(existing.values)
            build_standard_profile(
                values,
                mode_code=values.standard_mode_code,
                charge_c_rate=values.standard_charge_c_rate,
                discharge_c_rate=values.standard_discharge_c_rate,
                cycle_count=values.standard_cycle_count,
                cycle_mode=values.standard_cycle_mode,
                time_limit_mode=values.standard_time_limit_mode,
                time_limit_min=values.standard_time_limit_min,
            )
            stored = await asyncio.to_thread(
                app.state.batteries.save,
                values,
                battery_id=battery_id,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=404, detail="Batterie wurde nicht gefunden"
            ) from exc
        except (BatteryError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "ok": True,
            "battery": _battery_with_statistics(
                app.state.measurements,
                stored,
            ),
        }

    @app.delete("/api/batteries/{battery_id}")
    async def archive_battery(battery_id: int) -> dict:
        for device in app.state.manager.snapshots():
            for slot_key, assigned_id in device["battery_ids"].items():
                if assigned_id != battery_id:
                    continue
                slot = int(slot_key)
                current = device["slots"][slot - 1]
                if current and current["active"]:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"Batterie ist noch in {device['alias']} Slot {slot} aktiv"
                        ),
                    )
        try:
            await asyncio.to_thread(app.state.batteries.archive, battery_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=404, detail="Batterie wurde nicht gefunden"
            ) from exc
        await asyncio.to_thread(
            app.state.profiles.clear_programs_for_battery,
            battery_id,
        )
        for session in app.state.manager.sessions.values():
            session.clear_battery_assignment(battery_id)
        await app.state.manager.publish()
        return {"ok": True}

    @app.delete("/api/batteries/{battery_id}/permanent")
    async def delete_battery_permanently(
        battery_id: int,
        request: PermanentBatteryDeleteRequest,
    ) -> dict:
        stored = await asyncio.to_thread(app.state.batteries.get, battery_id)
        if stored is None:
            raise HTTPException(
                status_code=404, detail="Batterie wurde nicht gefunden"
            )
        if not stored.values.archived:
            raise HTTPException(
                status_code=409,
                detail="Batterie muss vor dem endgültigen Löschen archiviert werden",
            )
        if request.confirmation.strip().upper() != stored.values.code:
            raise HTTPException(
                status_code=400,
                detail="Batterienummer zur Bestätigung stimmt nicht überein",
            )
        for device in app.state.manager.snapshots():
            for slot_key, assigned_id in device["battery_ids"].items():
                if assigned_id != battery_id:
                    continue
                slot = int(slot_key)
                current = device["slots"][slot - 1]
                if current and current["active"]:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"Batterie ist noch in {device['alias']} Slot {slot} aktiv"
                        ),
                    )
        try:
            deleted = await asyncio.to_thread(
                app.state.batteries.delete_permanently,
                battery_id,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=404, detail="Batterie wurde nicht gefunden"
            ) from exc
        except BatteryError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        for session in app.state.manager.sessions.values():
            session.clear_battery_assignment(battery_id)
        await app.state.manager.publish()
        return {
            "ok": True,
            "battery_id": battery_id,
            "battery_code": stored.values.code,
            "deleted": deleted,
        }

    @app.put("/api/batteries/{battery_id}/standard-program")
    async def save_standard_program(
        battery_id: int,
        request: StandardProgramRequest,
    ) -> dict:
        stored = await asyncio.to_thread(app.state.batteries.get, battery_id)
        if stored is None or stored.values.archived:
            raise HTTPException(status_code=404, detail="Batterie wurde nicht gefunden")
        try:
            values = replace(
                stored.values,
                standard_mode_code=request.mode_code,
                standard_charge_c_rate=request.charge_c_rate,
                standard_discharge_c_rate=request.discharge_c_rate,
                standard_cycle_count=request.cycle_count,
                standard_cycle_mode=request.cycle_mode,
                standard_time_limit_mode=request.time_limit_mode,
                standard_time_limit_min=request.time_limit_min,
            )
            _profile, standard = build_standard_profile(
                values,
                mode_code=request.mode_code,
                charge_c_rate=request.charge_c_rate,
                discharge_c_rate=request.discharge_c_rate,
                cycle_count=request.cycle_count,
                cycle_mode=request.cycle_mode,
                time_limit_mode=request.time_limit_mode,
                time_limit_min=request.time_limit_min,
            )
            stored = await asyncio.to_thread(
                app.state.batteries.save,
                values,
                battery_id=battery_id,
            )
        except (BatteryError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "ok": True,
            "battery": stored.to_dict(),
            "standard_program": standard,
        }

    @app.put("/api/devices/{address}/slots/{slot}/configuration")
    async def configure_slot(
        address: str,
        slot: int,
        request: SlotConfigurationRequest,
    ) -> dict:
        if slot not in range(1, 5):
            raise HTTPException(
                status_code=400, detail="Slot muss zwischen 1 und 4 liegen"
            )
        session = _session_or_404(app, address)
        current = session.slots[slot - 1]
        if current is None or current["voltage_v"] <= 0:
            raise HTTPException(
                status_code=409, detail=f"Slot {slot} erkennt keine Batterie"
            )
        if request.create_battery and request.battery_id is not None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Neue Batterie und vorhandene Batterienummer "
                    "dürfen nicht gleichzeitig gewählt werden"
                ),
            )

        battery = None
        if request.battery_id is not None:
            battery = await asyncio.to_thread(
                app.state.batteries.get,
                request.battery_id,
            )
            if battery is None or battery.values.archived:
                raise HTTPException(
                    status_code=404, detail="Batterie wurde nicht gefunden"
                )
            try:
                await asyncio.to_thread(
                    app.state.batteries.validate_assignments,
                    address,
                    {slot: battery.id},
                )
            except (BatteryError, KeyError, ValueError) as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc

        battery_id = battery.id if battery is not None else None
        battery_type_code = (
            battery.values.battery_type_code
            if battery is not None
            else _detected_battery_type(current, slot)
        )
        if request.create_battery:
            if request.capacity_mah is None or request.capacity_mah < 100:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Für die neue Batterie wird eine Kapazität "
                        "zwischen 100 und 50000 mAh benötigt"
                    ),
                )
            battery_values = BatteryValues(
                code="NEU",
                name="",
                battery_type_code=battery_type_code,
                nominal_capacity_mah=request.capacity_mah,
                notes="",
            )
        else:
            battery_values = battery.values if battery is not None else None

        profile_id: int | None = None
        if request.program_source == "standard":
            if battery_values is None:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Das Batterie-Standardprogramm benötigt eine "
                        "Batterienummer"
                    ),
                )
            try:
                profile, program = build_standard_profile(
                    battery_values,
                    mode_code=battery_values.standard_mode_code,
                    charge_c_rate=battery_values.standard_charge_c_rate,
                    discharge_c_rate=battery_values.standard_discharge_c_rate,
                    cycle_count=battery_values.standard_cycle_count,
                    cycle_mode=battery_values.standard_cycle_mode,
                    time_limit_mode=battery_values.standard_time_limit_mode,
                    time_limit_min=battery_values.standard_time_limit_min,
                )
            except BatteryError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            program_label = f"{program['mode']} · Standard"
        elif request.program_source == "automatic":
            if request.automatic_program is None or request.capacity_mah is None:
                raise HTTPException(
                    status_code=400,
                    detail="Automatikprogramm und Akkukapazität müssen angegeben werden",
                )
            automatic_template = await asyncio.to_thread(
                app.state.profiles.get_automatic,
                request.automatic_program,
            )
            if automatic_template is None:
                raise HTTPException(
                    status_code=404,
                    detail="Automatikprofil wurde nicht gefunden",
                )
            try:
                profile_battery = (
                    battery_values
                    if battery_values is not None
                    else BatteryValues(
                        code="ANONYM",
                        name="",
                        battery_type_code=battery_type_code,
                        nominal_capacity_mah=request.capacity_mah,
                        notes="",
                    )
                )
                profile, program = build_automatic_profile(
                    profile_battery,
                    request.automatic_program,
                    request.capacity_mah,
                    template=automatic_template.values,
                    time_limit_mode=request.time_limit_mode,
                    time_limit_min=request.time_limit_min,
                )
            except BatteryError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            program_label = f"{program['label']} · {request.capacity_mah} mAh"
        else:
            if request.profile_id is None:
                raise HTTPException(
                    status_code=400,
                    detail="Für ein Ladeprofil fehlt die Profil-ID",
                )
            stored_profile = await asyncio.to_thread(
                app.state.profiles.get,
                request.profile_id,
            )
            if stored_profile is None:
                raise HTTPException(
                    status_code=404, detail="Profil wurde nicht gefunden"
                )
            if stored_profile.values.battery_type_code != battery_type_code:
                raise HTTPException(
                    status_code=400,
                    detail="Profil und erkannter Akkutyp passen nicht zusammen",
                )
            profile = _profile_with_capacity(
                stored_profile.values,
                request.capacity_mah,
            )
            profile_id = stored_profile.id
            program = {
                **stored_profile.to_dict(),
                **profile.to_dict(),
            }
            program_label = (
                f"{stored_profile.values.name} · {profile.capacity_mah} mAh"
            )

        if not await session.acquire_configuration():
            raise HTTPException(
                status_code=409,
                detail="Für dieses Ladegerät läuft bereits eine Konfiguration",
            )
        try:
            packet = build_profile_packet(profile, 1 << (slot - 1))
            result = await session.apply_profile(packet, [slot])
            if request.create_battery:
                try:
                    battery = await asyncio.to_thread(
                        app.state.batteries.create_numbered,
                        battery_type_code=battery_type_code,
                        nominal_capacity_mah=request.capacity_mah,
                    )
                except (BatteryError, ValueError) as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc
                battery_id = battery.id
            if battery_id is None:
                await asyncio.to_thread(
                    app.state.batteries.clear_assignments,
                    address,
                    [slot],
                )
            else:
                await asyncio.to_thread(
                    app.state.batteries.assign,
                    address,
                    slot,
                    battery_id,
                )
            if profile_id is None:
                await asyncio.to_thread(
                    app.state.profiles.clear_assignments,
                    address,
                    [slot],
                )
            else:
                await asyncio.to_thread(
                    app.state.profiles.assign,
                    address,
                    [slot],
                    profile_id,
                )
            selected_at = datetime.now(UTC).isoformat()
            selected_program = {
                "source": request.program_source,
                "label": program_label,
                "details": program,
                "battery_id": battery_id,
                "profile_id": profile_id,
                "selected_at": selected_at,
            }
            await asyncio.to_thread(
                app.state.profiles.set_slot_program,
                address,
                slot,
                source=request.program_source,
                label=program_label,
                details=program,
                battery_id=battery_id,
                profile_id=profile_id,
            )
            session.mark_slot_configuration(
                slot,
                battery_id,
                profile_id,
                selected_program,
            )
            await app.state.manager.publish()
        except (KeyError, ProfileError, RuntimeError, TimeoutError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        finally:
            session.release_configuration()
        return {
            "ok": True,
            "battery": battery.to_dict() if battery is not None else None,
            "program": program,
            "result": result,
        }

    @app.put("/api/devices/{address}/configuration")
    async def configure_device_slots(
        address: str,
        request: BulkConfigurationRequest,
    ) -> dict:
        slots = [item.slot for item in request.slots]
        battery_ids = [
            item.battery_id
            for item in request.slots
            if item.battery_id is not None
        ]
        if len(set(slots)) != len(slots):
            raise HTTPException(status_code=400, detail="Jeder Slot darf nur einmal vorkommen")
        if len(set(battery_ids)) != len(battery_ids):
            raise HTTPException(
                status_code=400,
                detail="Jede Batterienummer darf nur einmal verwendet werden",
            )
        if any(
            item.create_battery and item.battery_id is not None
            for item in request.slots
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Neue Batterie und vorhandene Batterienummer "
                    "dürfen nicht gleichzeitig gewählt werden"
                ),
            )

        session = _session_or_404(app, address)
        batteries = []
        battery_types = []
        battery_values = []
        for item in request.slots:
            current = session.slots[item.slot - 1]
            if current is None or current["voltage_v"] <= 0:
                raise HTTPException(
                    status_code=409,
                    detail=f"Slot {item.slot} erkennt keine Batterie",
                )
            if current["active"]:
                raise HTTPException(
                    status_code=409,
                    detail=f"Slot {item.slot} ist bereits aktiv",
                )
            if current["status_code"] >= 128:
                raise HTTPException(
                    status_code=409,
                    detail=f"Slot {item.slot} meldet {current['status']}",
                )
            battery = None
            if item.battery_id is not None:
                battery = await asyncio.to_thread(
                    app.state.batteries.get,
                    item.battery_id,
                )
                if battery is None or battery.values.archived:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Batterie für Slot {item.slot} wurde nicht gefunden",
                    )
            battery_type_code = (
                battery.values.battery_type_code
                if battery is not None
                else _detected_battery_type(current, item.slot)
            )
            if item.create_battery:
                if item.capacity_mah is None or item.capacity_mah < 100:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Für die neue Batterie in Slot {item.slot} "
                            "wird eine Kapazität zwischen 100 und "
                            "50000 mAh benötigt"
                        ),
                    )
                values = BatteryValues(
                    code="NEU",
                    name="",
                    battery_type_code=battery_type_code,
                    nominal_capacity_mah=item.capacity_mah,
                    notes="",
                )
            else:
                values = battery.values if battery is not None else None
            batteries.append(battery)
            battery_types.append(battery_type_code)
            battery_values.append(values)

        assignments = {
            item.slot: battery.id
            for item, battery in zip(request.slots, batteries, strict=True)
            if battery is not None
        }
        if assignments:
            try:
                await asyncio.to_thread(
                    app.state.batteries.validate_assignments,
                    address,
                    assignments,
                )
            except (BatteryError, KeyError, ValueError) as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc

        automatic_template = None
        if request.program_source == "automatic":
            if request.automatic_program is None:
                raise HTTPException(
                    status_code=400,
                    detail="Automatikprofil muss angegeben werden",
                )
            automatic_template = await asyncio.to_thread(
                app.state.profiles.get_automatic,
                request.automatic_program,
            )
            if automatic_template is None:
                raise HTTPException(
                    status_code=404,
                    detail="Automatikprofil wurde nicht gefunden",
                )

        results = []
        created_batteries = []
        if not await session.acquire_configuration():
            raise HTTPException(
                status_code=409,
                detail="Für dieses Ladegerät läuft bereits eine Konfiguration",
            )
        try:
            if request.program_source == "profile":
                if request.profile_id is None:
                    raise ValueError("Für das gemeinsame Profil fehlt die Profil-ID")
                stored_profile = await asyncio.to_thread(
                    app.state.profiles.get,
                    request.profile_id,
                )
                if stored_profile is None:
                    raise KeyError("Profil wurde nicht gefunden")
                if any(
                    battery_type_code != stored_profile.values.battery_type_code
                    for battery_type_code in battery_types
                ):
                    raise BatteryError(
                        "Das gemeinsame Profil passt nicht zu allen Batterietypen"
                    )
                configured_profiles = []
                for item in request.slots:
                    profile = _profile_with_capacity(
                        stored_profile.values,
                        item.capacity_mah,
                    )
                    details = {
                        **stored_profile.to_dict(),
                        **profile.to_dict(),
                    }
                    label = (
                        f"{stored_profile.values.name} · "
                        f"{profile.capacity_mah} mAh"
                    )
                    configured_profiles.append((profile, details, label))

                results.extend(
                    await _apply_profile_groups(
                        session,
                        [
                            (item.slot, configured[0])
                            for item, configured in zip(
                                request.slots,
                                configured_profiles,
                                strict=True,
                            )
                        ],
                    )
                )
                batteries, created_batteries = await _materialize_new_batteries(
                    app.state.batteries,
                    request.slots,
                    batteries,
                    battery_types,
                )
                assignments = {
                    item.slot: battery.id
                    for item, battery in zip(
                        request.slots,
                        batteries,
                        strict=True,
                    )
                    if battery is not None
                }
                await asyncio.to_thread(
                    app.state.batteries.clear_assignments,
                    address,
                    slots,
                )
                if assignments:
                    await asyncio.to_thread(
                        app.state.batteries.assign_many,
                        address,
                        assignments,
                    )
                await asyncio.to_thread(
                    app.state.profiles.assign,
                    address,
                    slots,
                    stored_profile.id,
                )
                selected_at = datetime.now(UTC).isoformat()
                for item, battery, configured in zip(
                    request.slots,
                    batteries,
                    configured_profiles,
                    strict=True,
                ):
                    _profile, details, label = configured
                    battery_id = battery.id if battery is not None else None
                    program = {
                        "source": "profile",
                        "label": label,
                        "details": details,
                        "battery_id": battery_id,
                        "profile_id": stored_profile.id,
                        "selected_at": selected_at,
                    }
                    await asyncio.to_thread(
                        app.state.profiles.set_slot_program,
                        address,
                        item.slot,
                        source="profile",
                        label=label,
                        details=details,
                        battery_id=battery_id,
                        profile_id=stored_profile.id,
                    )
                    session.mark_slot_configuration(
                        item.slot,
                        battery_id,
                        stored_profile.id,
                        program,
                    )
            else:
                configured_programs = []
                for item, values, battery_type_code in zip(
                    request.slots,
                    battery_values,
                    battery_types,
                    strict=True,
                ):
                    if request.program_source == "automatic":
                        if (
                            request.automatic_program is None
                            or item.capacity_mah is None
                        ):
                            raise BatteryError(
                                "Für jeden Slot wird eine Akkukapazität benötigt"
                            )
                        profile_battery = (
                            values
                            if values is not None
                            else BatteryValues(
                                code="ANONYM",
                                name="",
                                battery_type_code=battery_type_code,
                                nominal_capacity_mah=item.capacity_mah,
                                notes="",
                            )
                        )
                        profile, details = build_automatic_profile(
                            profile_battery,
                            request.automatic_program,
                            item.capacity_mah,
                            template=automatic_template.values,
                            time_limit_mode=request.time_limit_mode,
                            time_limit_min=request.time_limit_min,
                        )
                        label = f"{details['label']} · {item.capacity_mah} mAh"
                    else:
                        if values is None:
                            raise BatteryError(
                                "Das Batterie-Standardprogramm benötigt für "
                                f"Slot {item.slot} eine Batterienummer"
                            )
                        profile, details = build_standard_profile(
                            values,
                            mode_code=values.standard_mode_code,
                            charge_c_rate=values.standard_charge_c_rate,
                            discharge_c_rate=values.standard_discharge_c_rate,
                            cycle_count=values.standard_cycle_count,
                            cycle_mode=values.standard_cycle_mode,
                            time_limit_mode=values.standard_time_limit_mode,
                            time_limit_min=values.standard_time_limit_min,
                        )
                        label = f"{details['mode']} · Standard"
                    configured_programs.append((profile, details, label))

                results.extend(
                    await _apply_profile_groups(
                        session,
                        [
                            (item.slot, configured[0])
                            for item, configured in zip(
                                request.slots,
                                configured_programs,
                                strict=True,
                            )
                        ],
                    )
                )
                batteries, created_batteries = await _materialize_new_batteries(
                    app.state.batteries,
                    request.slots,
                    batteries,
                    battery_types,
                )
                assignments = {
                    item.slot: battery.id
                    for item, battery in zip(
                        request.slots,
                        batteries,
                        strict=True,
                    )
                    if battery is not None
                }
                await asyncio.to_thread(
                    app.state.batteries.clear_assignments,
                    address,
                    slots,
                )
                if assignments:
                    await asyncio.to_thread(
                        app.state.batteries.assign_many,
                        address,
                        assignments,
                    )
                await asyncio.to_thread(
                    app.state.profiles.clear_assignments,
                    address,
                    slots,
                )
                selected_at = datetime.now(UTC).isoformat()
                for item, battery, configured in zip(
                    request.slots,
                    batteries,
                    configured_programs,
                    strict=True,
                ):
                    _profile, details, label = configured
                    battery_id = battery.id if battery is not None else None
                    program = {
                        "source": request.program_source,
                        "label": label,
                        "details": details,
                        "battery_id": battery_id,
                        "profile_id": None,
                        "selected_at": selected_at,
                    }
                    await asyncio.to_thread(
                        app.state.profiles.set_slot_program,
                        address,
                        item.slot,
                        source=request.program_source,
                        label=label,
                        details=details,
                        battery_id=battery_id,
                        profile_id=None,
                    )
                    session.mark_slot_configuration(
                        item.slot,
                        battery_id,
                        None,
                        program,
                    )
            await app.state.manager.publish()
        except (
            BatteryError,
            KeyError,
            ProfileError,
            RuntimeError,
            TimeoutError,
            ValueError,
        ) as exc:
            await app.state.manager.publish()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        finally:
            session.release_configuration()
        return {
            "ok": True,
            "slots": slots,
            "program_source": request.program_source,
            "results": results,
            "created_batteries": [
                battery.to_dict()
                for battery in created_batteries
            ],
            "started": False,
        }

    @app.get("/api/batteries/{battery_id}/compare")
    async def compare_battery_runs(
        battery_id: int,
        run_ids: str,
        limit: int = Query(default=1200, ge=50, le=3000),
    ) -> dict:
        try:
            clean_ids = [
                int(value)
                for value in run_ids.split(",")
                if value.strip()
            ]
            return await asyncio.to_thread(
                app.state.measurements.compare_runs,
                battery_id,
                clean_ids,
                limit=limit,
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/batteries/{battery_id}/qr.svg")
    async def battery_qr(battery_id: int, request: Request) -> Response:
        stored = await asyncio.to_thread(app.state.batteries.get, battery_id)
        if stored is None or stored.values.archived:
            raise HTTPException(status_code=404, detail="Batterie wurde nicht gefunden")
        target = str(request.base_url).rstrip("/") + f"/#battery={battery_id}"
        output = io.BytesIO()
        segno.make(target, error="m").save(
            output,
            kind="svg",
            scale=7,
            border=2,
            xmldecl=False,
        )
        return Response(
            content=output.getvalue(),
            media_type="image/svg+xml",
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": (
                    f'inline; filename="batterie-{stored.values.code}-qr.svg"'
                ),
            },
        )

    @app.get("/api/batteries/{battery_id}/sheet.pdf")
    async def battery_sheet(battery_id: int, request: Request) -> Response:
        stored = await asyncio.to_thread(app.state.batteries.get, battery_id)
        if stored is None:
            raise HTTPException(status_code=404, detail="Batterie wurde nicht gefunden")
        statistics = await asyncio.to_thread(
            app.state.measurements.battery_statistics,
            battery_id,
        )
        battery = {**stored.to_dict(), "statistics": statistics}
        target = str(request.base_url).rstrip("/") + f"/#battery={battery_id}"
        content = await asyncio.to_thread(
            battery_sheet_pdf,
            battery,
            qr_target=target,
        )
        return Response(
            content=content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="batterie-{stored.values.code}-steckblatt.pdf"'
                )
            },
        )

    @app.get("/api/batteries/{battery_id}/export.csv")
    async def export_battery(battery_id: int) -> StreamingResponse:
        stored = await asyncio.to_thread(app.state.batteries.get, battery_id)
        if stored is None:
            raise HTTPException(status_code=404, detail="Batterie wurde nicht gefunden")
        content = app.state.measurements.iter_battery_csv(battery_id)
        filename = f"mc3000-batterie-{stored.values.code}.csv"
        return StreamingResponse(
            content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/api/recordings/history")
    async def recording_history(
        address: str,
        slot: int,
        hours: float = Query(default=24, gt=0, le=24 * 365),
        start: str | None = Query(default=None, alias="from"),
        end: str | None = Query(default=None, alias="to"),
        limit: int = Query(default=2000, ge=10, le=5000),
    ) -> dict:
        since, until = _time_range(start, end, hours)
        try:
            return await asyncio.to_thread(
                app.state.measurements.history,
                address,
                slot,
                since,
                until,
                limit=limit,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/recordings/runs")
    async def recording_runs(
        address: str | None = None,
        slot: int | None = None,
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict:
        try:
            runs = await asyncio.to_thread(
                app.state.measurements.list_runs,
                address=address,
                slot=slot,
                limit=limit,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"runs": runs}

    @app.get("/api/recordings/runs/{run_id}/report")
    async def recording_run_report(run_id: int) -> dict:
        try:
            return await asyncio.to_thread(
                app.state.measurements.run_report,
                run_id,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail="Programmlauf wurde nicht gefunden",
            ) from exc

    @app.get("/api/recordings/runs/{run_id}/chart")
    async def recording_run_chart(run_id: int) -> dict:
        try:
            return await asyncio.to_thread(
                app.state.measurements.run_chart,
                run_id,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail="Programmlauf wurde nicht gefunden",
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/recordings/runs/{run_id}/report.pdf")
    async def recording_run_report_pdf(run_id: int, request: Request) -> Response:
        try:
            report, chart, phase_opacity = await asyncio.gather(
                asyncio.to_thread(app.state.measurements.run_report, run_id),
                asyncio.to_thread(app.state.measurements.run_chart, run_id),
                asyncio.to_thread(
                    app.state.profiles.get_app_setting,
                    "phase_opacity_percent",
                    "15",
                ),
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=404, detail="Programmlauf wurde nicht gefunden"
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        battery = None
        qr_target = None
        if report.get("battery_id") is not None:
            stored = await asyncio.to_thread(
                app.state.batteries.get,
                int(report["battery_id"]),
            )
            if stored is not None:
                statistics = await asyncio.to_thread(
                    app.state.measurements.battery_statistics,
                    stored.id,
                )
                battery = {**stored.to_dict(), "statistics": statistics}
                qr_target = (
                    str(request.base_url).rstrip("/")
                    + f"/#battery={stored.id}"
                )
        content = await asyncio.to_thread(
            run_report_pdf,
            report,
            chart,
            battery,
            qr_target=qr_target,
            phase_opacity_percent=_phase_opacity_percent(phase_opacity),
        )
        label = report.get("battery_code") or f"lauf-{run_id}"
        return Response(
            content=content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="pruefbericht-{label}-{run_id}.pdf"'
                )
            },
        )

    @app.delete("/api/recordings/runs/{run_id}")
    async def delete_recording_run(run_id: int) -> dict:
        try:
            deleted = await asyncio.to_thread(
                app.state.measurements.delete_run,
                run_id,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail="Programmlauf wurde nicht gefunden",
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"ok": True, "deleted": deleted}

    @app.get("/api/notifications")
    async def notifications(
        unread_only: bool = False,
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict:
        items = await asyncio.to_thread(
            app.state.measurements.list_notifications,
            unread_only=unread_only,
            limit=limit,
        )
        return {
            "notifications": items,
            "unread_count": sum(not item["read"] for item in items),
        }

    @app.post("/api/notifications/read")
    async def mark_notifications_read(request: NotificationReadRequest) -> dict:
        count = await asyncio.to_thread(
            app.state.measurements.mark_notifications_read,
            request.notification_ids,
        )
        return {"ok": True, "updated": count}

    @app.get("/api/admin/backup")
    async def download_backup() -> Response:
        try:
            content = await asyncio.to_thread(
                create_backup,
                app.state.database_path,
                version=__version__,
            )
        except BackupError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        return Response(
            content=content,
            media_type="application/zip",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="mc3000-control-{timestamp}.zip"'
                ),
                "Cache-Control": "no-store",
            },
        )

    @app.get("/api/admin/diagnostics")
    async def download_diagnostics() -> Response:
        profiles, batteries, runs = await asyncio.gather(
            asyncio.to_thread(app.state.profiles.list),
            asyncio.to_thread(app.state.batteries.list, include_archived=True),
            asyncio.to_thread(app.state.measurements.list_runs, limit=500),
        )
        content = await asyncio.to_thread(
            create_diagnostics,
            version=__version__,
            manager_payload=app.state.manager.payload(),
            profile_count=len(profiles),
            battery_count=len(batteries),
            run_count=len(runs),
        )
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        return Response(
            content=content,
            media_type="application/zip",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="mc3000-diagnostics-{timestamp}.zip"'
                ),
                "Cache-Control": "no-store",
            },
        )

    @app.post("/api/admin/restore")
    async def upload_backup(
        request: Request,
        confirmation: str = Query(default=""),
    ) -> dict:
        if confirmation != "WIEDERHERSTELLEN":
            raise HTTPException(
                status_code=400,
                detail="Bestätigung muss exakt WIEDERHERSTELLEN lauten",
            )
        content = await request.body()
        try:
            result = await asyncio.to_thread(
                restore_backup,
                app.state.database_path,
                content,
                current_version=__version__,
            )
        except BackupError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        asyncio.get_running_loop().call_later(
            0.5,
            os.kill,
            os.getpid(),
            signal.SIGTERM,
        )
        return result

    @app.get("/api/recordings/export.csv")
    async def export_recording(
        address: str,
        slot: int,
        hours: float = Query(default=24, gt=0, le=24 * 365),
        start: str | None = Query(default=None, alias="from"),
        end: str | None = Query(default=None, alias="to"),
    ) -> StreamingResponse:
        since, until = _time_range(start, end, hours)
        safe_address = address.replace(":", "")
        filename = f"mc3000-{safe_address}-slot-{slot}.csv"
        try:
            content = app.state.measurements.iter_csv(address, slot, since, until)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return StreamingResponse(
            content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/api/devices/{address}/slots/{slot}/curve")
    async def curve(address: str, slot: int) -> dict:
        session = _session_or_404(app, address)
        try:
            return await session.read_curve(slot)
        except (RuntimeError, TimeoutError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        origin = websocket.headers.get("origin")
        host = websocket.headers.get("host", "")
        if origin and not _origin_matches_host(origin, host):
            await websocket.close(code=4403)
            return
        auth_enabled, auth_secret = await asyncio.gather(
            asyncio.to_thread(
                app.state.profiles.get_app_setting,
                "auth_enabled",
                "0",
            ),
            asyncio.to_thread(
                app.state.profiles.get_app_setting,
                "auth_session_secret",
                "",
            ),
        )
        if auth_enabled == "1" and not _valid_session_cookie(
            websocket.cookies.get("mc3000_session", ""),
            auth_secret,
        ):
            await websocket.close(code=4401)
            return
        await websocket.accept()
        manager: DeviceManager = app.state.manager
        queue = manager.subscribe()
        try:
            await websocket.send_json(manager.payload())
            while True:
                update_task = asyncio.create_task(queue.get())
                receive_task = asyncio.create_task(websocket.receive())
                done, pending = await asyncio.wait(
                    (update_task, receive_task),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                if receive_task in done:
                    message = receive_task.result()
                    if message["type"] == "websocket.disconnect":
                        break
                if update_task in done:
                    await websocket.send_json(update_task.result())
        except WebSocketDisconnect:
            pass
        finally:
            manager.unsubscribe(queue)

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/manifest.webmanifest")
    async def web_manifest() -> FileResponse:
        return FileResponse(
            STATIC_DIR / "manifest.webmanifest",
            media_type="application/manifest+json",
        )

    @app.get("/sw.js")
    async def service_worker() -> FileResponse:
        return FileResponse(
            STATIC_DIR / "sw.js",
            media_type="application/javascript",
            headers={"Cache-Control": "no-cache"},
        )

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def _phase_opacity_percent(value: object) -> int:
    try:
        opacity = int(str(value))
    except (TypeError, ValueError):
        return 15
    return max(15, min(25, opacity))


def _theme_preference(value: object) -> str:
    theme = str(value)
    return theme if theme in {"system", "light", "dark"} else "system"


def _origin_matches_host(origin: str, host: str) -> bool:
    try:
        origin_host = urlsplit(origin).netloc.casefold()
    except ValueError:
        return False
    expected = host.casefold()
    return bool(origin_host and expected and hmac.compare_digest(origin_host, expected))


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )
    return f"scrypt${salt.hex()}${digest.hex()}"


def _verify_password(password: str, record: str) -> bool:
    try:
        algorithm, salt_hex, digest_hex = record.split("$", 2)
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=2**14,
            r=8,
            p=1,
            dklen=32,
        )
        return hmac.compare_digest(actual.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def _session_cookie(secret: str) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        b"mc3000-control-session",
        hashlib.sha256,
    ).hexdigest()


def _valid_session_cookie(cookie: str, secret: str) -> bool:
    return bool(
        cookie
        and secret
        and hmac.compare_digest(cookie, _session_cookie(secret))
    )


def _login_page() -> str:
    return """<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Anmelden · Open MC3000 Control</title>
  <script src="/static/theme-init.js?v=102"></script>
  <style>
    :root { color-scheme:light; font-family:Inter, system-ui, sans-serif; --page:#f2f4f5; --surface:#fff; --ink:#202427; --muted:#667078; --line:#cfd6d9; --input:#fff; --button:#16825d; --button-ink:#fff; --error:#b52b34; }
    :root[data-theme="dark"] { color-scheme:dark; --page:#10171a; --surface:#182125; --ink:#e8eef0; --muted:#a8b4ba; --line:#344249; --input:#11191d; --button:#4fc59a; --button-ink:#07110d; --error:#ff8991; }
    body { margin:0; min-height:100vh; display:grid; place-items:center; background:var(--page); color:var(--ink); }
    main { width:min(380px, calc(100% - 32px)); padding:28px; border:1px solid var(--line); border-radius:18px; background:var(--surface); box-shadow:0 22px 70px #0008; }
    p { color:var(--muted); line-height:1.5; }
    label { display:grid; gap:7px; margin-top:16px; font-weight:600; }
    input, button { box-sizing:border-box; width:100%; min-height:44px; padding:10px 12px; border-radius:9px; border:1px solid var(--line); font:inherit; }
    input { background:var(--input); color:var(--ink); }
    button { margin-top:22px; background:var(--button); color:var(--button-ink); border:0; font-weight:700; cursor:pointer; }
    #error { min-height:20px; color:var(--error); }
  </style>
</head>
<body>
  <main>
    <h1>Open MC3000 Control</h1>
    <p>Diese Oberfläche ist geschützt. Bitte anmelden.</p>
    <form id="login">
      <label>Benutzername<input id="username" autocomplete="username" required autofocus></label>
      <label>Passwort<input id="password" type="password" autocomplete="current-password" required></label>
      <button type="submit">Anmelden</button>
      <p id="error" role="alert"></p>
    </form>
  </main>
  <script src="/static/i18n.js?v=102"></script>
  <script src="/static/login.js?v=102"></script>
</body>
</html>"""


def _session_or_404(app: FastAPI, address: str):
    try:
        return app.state.manager.get_session(address)
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=404, detail="Gerät ist nicht registriert"
        ) from exc


def _profile_with_capacity(
    profile: ProfileValues,
    capacity_mah: int | None,
) -> ProfileValues:
    if capacity_mah is None or capacity_mah == profile.capacity_mah:
        return profile
    return replace(profile, capacity_mah=capacity_mah)


def _detected_battery_type(current: dict, slot: int) -> int:
    battery_type_code = current.get("battery_type_code")
    if not isinstance(battery_type_code, int):
        raise HTTPException(
            status_code=409,
            detail=f"Slot {slot} liefert noch keinen erkannten Akkutyp",
        )
    return battery_type_code


async def _materialize_new_batteries(
    store: BatteryStore,
    slot_requests,
    batteries: list,
    battery_types: list[int],
) -> tuple[list, list]:
    new_specs = [
        (battery_types[index], item.capacity_mah)
        for index, item in enumerate(slot_requests)
        if item.create_battery
    ]
    if not new_specs:
        return batteries, []
    created = await asyncio.to_thread(
        store.create_numbered_many,
        new_specs,
    )
    result = list(batteries)
    created_iterator = iter(created)
    for index, item in enumerate(slot_requests):
        if item.create_battery:
            result[index] = next(created_iterator)
    return result, created


async def _apply_profile_groups(
    session: DeviceSession,
    slot_profiles: list[tuple[int, ProfileValues]],
) -> list[dict]:
    groups: dict[bytes, tuple[ProfileValues, list[int]]] = {}
    for slot, profile in slot_profiles:
        signature = build_profile_packet(profile, 1)[3:]
        if signature in groups:
            groups[signature][1].append(slot)
        else:
            groups[signature] = (profile, [slot])

    results = []
    for profile, slots in groups.values():
        slot_mask = sum(1 << (slot - 1) for slot in slots)
        packet = build_profile_packet(profile, slot_mask)
        try:
            results.append(await session.apply_profile(packet, slots))
            continue
        except TimeoutError:
            LOGGER.warning(
                "%s: profile acknowledgement timed out for slots %s",
                session.address,
                ",".join(str(slot) for slot in slots),
            )

        # Repeating a profile transfer is safe: applying a profile does not start
        # a program. Some MC3000 connections occasionally omit the acknowledgement
        # for a combined slot mask, although individual slot transfers still work.
        retry_slots = slots if len(slots) > 1 else [slots[0]]
        for slot in retry_slots:
            single_packet = build_profile_packet(profile, 1 << (slot - 1))
            try:
                result = await session.apply_profile(single_packet, [slot])
            except TimeoutError as exc:
                LOGGER.warning(
                    "%s: profile acknowledgement timed out for slot %d",
                    session.address,
                    slot,
                )
                raise RuntimeError(
                    "Das Ladegerät hat die Profilübertragung für "
                    f"Slot {slot} nicht bestätigt. Verbindung prüfen und erneut versuchen."
                ) from exc
            results.append(result)
    return results


def _battery_with_statistics(
    measurements: MeasurementStore,
    stored,
) -> dict:
    return {
        **stored.to_dict(),
        "statistics": measurements.battery_statistics(stored.id),
    }


def _time_range(
    start: str | None,
    end: str | None,
    hours: float,
) -> tuple[str, str]:
    until = _parse_timestamp(end) if end else datetime.now(UTC)
    since = _parse_timestamp(start) if start else until - timedelta(hours=hours)
    if since >= until:
        raise HTTPException(
            status_code=400,
            detail="Der Startzeitpunkt muss vor dem Endzeitpunkt liegen",
        )
    return since.isoformat(), until.isoformat()


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="Ungültiger ISO-Zeitstempel"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


app = create_app()


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("MC3000_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # Listening on the LAN is the intended deployment model.
    uvicorn.run(
        "mc3000_control.app:app",
        host=os.environ.get("MC3000_HOST", "0.0.0.0"),  # nosec
        port=int(os.environ.get("MC3000_PORT", "8083")),
        log_level=os.environ.get("MC3000_LOG_LEVEL", "info").lower(),
    )


if __name__ == "__main__":
    main()
