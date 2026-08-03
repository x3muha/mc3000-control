from __future__ import annotations

import argparse
import difflib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import quote

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOTICE_PATH = PROJECT_ROOT / "THIRD_PARTY_NOTICES.md"
PROJECT_METADATA_PATH = PROJECT_ROOT / "pyproject.toml"
SELF_PACKAGE = "mc3000-control"


def _run(command: list[str], *, environment: dict[str, str]) -> str:
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)
    return result.stdout


def _license_configuration() -> tuple[str, str]:
    configuration = tomllib.loads(PROJECT_METADATA_PATH.read_text(encoding="utf-8"))
    license_options = configuration.get("tool", {}).get("pip-licenses", {})
    source = str(license_options.get("from", "mixed"))
    allowed = str(license_options.get("allow-only", "")).strip()
    if not allowed:
        raise SystemExit("pyproject.toml enthält keine Lizenz-Allowlist")
    return source, allowed


def _runtime_packages() -> list[dict[str, str]]:
    checker_name = "pip-licenses.exe" if os.name == "nt" else "pip-licenses"
    adjacent_checker = Path(sys.executable).with_name(checker_name)
    checker = (
        str(adjacent_checker)
        if adjacent_checker.exists()
        else shutil.which(checker_name)
    )
    if checker is None:
        raise SystemExit("pip-licenses fehlt; zuerst python -m pip install '.[audit]' ausführen")
    source, allowed = _license_configuration()
    environment = os.environ.copy()
    environment["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    with tempfile.TemporaryDirectory(prefix="omc-license-check-") as temporary:
        runtime_environment = Path(temporary) / "runtime"
        _run(
            [sys.executable, "-m", "venv", str(runtime_environment)],
            environment=environment,
        )
        if os.name == "nt":
            runtime_python = runtime_environment / "Scripts" / "python.exe"
        else:
            runtime_python = runtime_environment / "bin" / "python"
        _run(
            [
                str(runtime_python),
                "-m",
                "pip",
                "install",
                "--quiet",
                str(PROJECT_ROOT),
            ],
            environment=environment,
        )
        payload = _run(
            [
                checker,
                f"--python={runtime_python}",
                f"--from={source}",
                f"--allow-only={allowed}",
                "--format=json",
            ],
            environment=environment,
        )
    decoded: Any = json.loads(payload)
    if not isinstance(decoded, list):
        raise SystemExit("pip-licenses lieferte keine Paketliste")
    packages: list[dict[str, str]] = []
    for item in decoded:
        if not isinstance(item, dict):
            raise SystemExit("pip-licenses lieferte einen ungültigen Paketeintrag")
        name = str(item.get("Name", "")).strip()
        if not name or name.casefold().replace("_", "-") == SELF_PACKAGE:
            continue
        packages.append(
            {
                "name": name,
                "license": str(item.get("License", "UNKNOWN")).strip(),
            }
        )
    return sorted(packages, key=lambda package: package["name"].casefold())


def _escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _render(packages: list[dict[str, str]]) -> str:
    lines = [
        "# Third-party notices / Hinweise zu Drittanbieterkomponenten",
        "",
        "This file is generated from a clean installation of the runtime dependencies.",
        "Do not edit the package table manually. Open MC3000 Control itself is licensed",
        "under the MIT license in `LICENSE`; the packages below retain their respective",
        "upstream licenses and copyright notices.",
        "",
        "Diese Datei wird aus einer sauberen Installation der Laufzeitabhängigkeiten",
        "erzeugt. Die Pakettabelle darf nicht manuell bearbeitet werden. Open MC3000",
        "Control selbst steht unter der MIT-Lizenz in `LICENSE`; für die folgenden Pakete",
        "gelten weiterhin deren jeweilige Upstream-Lizenzen und Copyright-Hinweise.",
        "",
        "OMC does not vendor these packages in its source tree or wheel. Installation",
        "tools resolve and install them separately. The authoritative license texts are",
        "included in the respective package distributions.",
        "",
        "OMC bettet diese Pakete weder in den Quellbaum noch in das Wheel ein. Die",
        "Installationswerkzeuge lösen sie separat auf und installieren sie. Die",
        "maßgeblichen Lizenztexte sind in den jeweiligen Paketdistributionen enthalten.",
        "",
        "## Runtime packages / Laufzeitpakete",
        "",
        "| Package / Paket | License / Lizenz | Package page / Paketseite |",
        "| --- | --- | --- |",
    ]
    for package in packages:
        package_url = "https://pypi.org/project/" + quote(package["name"]) + "/"
        lines.append(
            "| "
            + _escape_cell(package["name"])
            + " | "
            + _escape_cell(package["license"])
            + " | "
            + f"[PyPI]({package_url})"
            + " |"
        )
    lines.extend(
        [
            "",
            "## Regeneration / Aktualisierung",
            "",
            "```bash",
            "python -m pip install -e '.[audit]'",
            "python scripts/third_party_notices.py --write",
            "```",
            "",
            "CI runs the same resolver with `--check`. It fails if this file is stale or",
            "if a resolved package declares a license outside the allowlist in",
            "`pyproject.toml`.",
            "",
            "CI führt dieselbe Auflösung mit `--check` aus. Die Prüfung schlägt fehl, wenn",
            "diese Datei veraltet ist oder ein aufgelöstes Paket eine Lizenz außerhalb",
            "der Allowlist in `pyproject.toml` angibt.",
            "",
            "Imported cell-catalog data is not distributed with OMC and is not covered by",
            "the OMC MIT license. The terms of each selected data source apply separately.",
            "",
            "Importierte Zellkatalogdaten werden nicht mit OMC ausgeliefert und fallen",
            "nicht unter die OMC-MIT-Lizenz. Die Bedingungen jeder ausgewählten Datenquelle",
            "gelten davon unabhängig.",
            "",
        ]
    )
    return "\n".join(lines)


def _check(expected: str) -> int:
    current = NOTICE_PATH.read_text(encoding="utf-8") if NOTICE_PATH.exists() else ""
    if current == expected:
        print("Third-party notices are current and all runtime licenses are allowed.")
        return 0
    difference = difflib.unified_diff(
        current.splitlines(keepends=True),
        expected.splitlines(keepends=True),
        fromfile=str(NOTICE_PATH),
        tofile="generated THIRD_PARTY_NOTICES.md",
    )
    sys.stderr.writelines(difference)
    sys.stderr.write("Run: python scripts/third_party_notices.py --write\n")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate or verify runtime dependency license notices."
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true")
    action.add_argument("--write", action="store_true")
    arguments = parser.parse_args()
    content = _render(_runtime_packages())
    if arguments.write:
        NOTICE_PATH.write_text(content, encoding="utf-8")
        print(f"Updated {NOTICE_PATH}")
        return 0
    return _check(content)


if __name__ == "__main__":
    raise SystemExit(main())
