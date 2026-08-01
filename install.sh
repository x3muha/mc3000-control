#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${EUID}" -ne 0 ]]; then
  if ! command -v sudo >/dev/null 2>&1; then
    echo "Fuer die Installation werden Root-Rechte benoetigt; sudo wurde nicht gefunden." >&2
    echo "Als root erneut starten: bash ${PROJECT_DIR}/install.sh" >&2
    exit 2
  fi
  echo "Die Installation benoetigt einmalig Administratorrechte."
  exec sudo -- bash "${PROJECT_DIR}/install.sh" "$@"
fi

if [[ ! -f "${PROJECT_DIR}/pyproject.toml" ]]; then
  echo "Das Skript muss aus dem MC3000-Control-Repository gestartet werden." >&2
  exit 2
fi

bash "${PROJECT_DIR}/deploy/remote-install.sh" "${PROJECT_DIR}"

HOST_ADDRESS="$(hostname -I 2>/dev/null | awk '{print $1}')"
if [[ -z "${HOST_ADDRESS}" ]]; then
  HOST_ADDRESS="$(hostname).local"
fi

echo
echo "Installation abgeschlossen."
echo "Oberflaeche: http://${HOST_ADDRESS}:8083/"
echo "Pruefung:    ${PROJECT_DIR}/deploy/check-installation.sh"
