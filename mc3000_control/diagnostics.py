from __future__ import annotations

import io
import json
import logging
import platform
import re
import shutil

# The only subprocess is a fixed local bluetoothctl version query.
import subprocess  # nosec B404
import zipfile
from collections import deque
from datetime import UTC, datetime
from typing import Any

_MAC = re.compile(r"(?i)\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b")
_IP = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_PATH = re.compile(r"(?<!\w)/(?:home|root|var/lib)/[^\s,:]+")
_SECRET = re.compile(r"(?i)(password|secret|token|cookie)=?\S+")


class DiagnosticLogHandler(logging.Handler):
    def __init__(self, capacity: int = 300) -> None:
        super().__init__(level=logging.INFO)
        self.messages: deque[str] = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
        except Exception:  # noqa: BLE001  # pragma: no cover - logging must not break app
            return
        self.messages.append(redact(message))


LOG_HANDLER = DiagnosticLogHandler()
LOG_HANDLER.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))


def install_log_collector() -> None:
    root = logging.getLogger()
    if LOG_HANDLER not in root.handlers:
        root.addHandler(LOG_HANDLER)


def create_diagnostics(
    *,
    version: str,
    manager_payload: dict[str, Any],
    profile_count: int,
    battery_count: int,
    run_count: int,
) -> bytes:
    devices = manager_payload.get("devices", [])
    safe_devices = []
    for index, device in enumerate(devices, start=1):
        basic = device.get("basic") if isinstance(device, dict) else None
        version_data = device.get("version") if isinstance(device, dict) else None
        slots = device.get("slots") if isinstance(device, dict) else []
        safe_devices.append(
            {
                "id": f"device-{index}",
                "state": device.get("state"),
                "connected": bool(device.get("connected")),
                "enabled": bool(device.get("enabled")),
                "released": bool(device.get("released")),
                "error": redact(str(device.get("error") or "")),
                "firmware": _safe_version(version_data),
                "hardware": _safe_basic(basic),
                "slots": [_safe_slot(slot) for slot in (slots or [])],
            }
        )

    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "application": {"name": "Open MC3000 Control", "version": version},
        "runtime": {
            "python": platform.python_version(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "bluez": _bluez_version(),
        },
        "counts": {
            "devices": len(safe_devices),
            "profiles": profile_count,
            "batteries": battery_count,
            "runs": run_count,
        },
        "devices": safe_devices,
        "privacy": {
            "device_addresses": "replaced",
            "device_names": "omitted",
            "serial_numbers": "omitted",
            "battery_and_profile_content": "omitted",
            "database": "not_included",
        },
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "diagnostics.json",
            json.dumps(summary, ensure_ascii=False, indent=2),
        )
        archive.writestr("recent.log", "\n".join(LOG_HANDLER.messages) + "\n")
        archive.writestr(
            "README.txt",
            "This archive is anonymized and does not contain the database, backups, "
            "network addresses, device names, serial numbers, battery records, profile "
            "contents, passwords, cookies, or session secrets.\n",
        )
    return output.getvalue()


def redact(value: str) -> str:
    value = _MAC.sub("[device-address]", value)
    value = _IP.sub("[ip-address]", value)
    value = _PATH.sub("[local-path]", value)
    return _SECRET.sub("[secret]", value)


def _bluez_version() -> str:
    executable = shutil.which("bluetoothctl")
    if executable is None:
        return "unavailable"
    try:
        # The executable comes from PATH lookup and accepts no user-provided arguments.
        result = subprocess.run(  # nosec B603
            [executable, "--version"],
            capture_output=True,
            check=False,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return "unavailable"
    return redact((result.stdout or result.stderr).strip()[:120]) or "unavailable"


def _safe_version(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    allowed = {
        "firmware",
        "hardware",
        "hardware_version",
        "software_version",
        "device_type",
    }
    return {key: value[key] for key in allowed if key in value}


def _safe_basic(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    allowed = {
        "input_voltage_v",
        "system_temperature_c",
        "fan_mode",
        "fan_level",
        "fan_percent",
    }
    return {key: value[key] for key in allowed if key in value}


def _safe_slot(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    allowed = {"slot", "status_code", "active", "battery_type_code", "mode_code"}
    return {key: value[key] for key in allowed if key in value}
