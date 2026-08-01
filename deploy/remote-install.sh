#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="${1:-}"
APP_ROOT="/opt/mc3000-control"
DATA_DIR="/var/lib/mc3000-control"
SERVICE_USER="mc3000-control"
RELEASE_ID="$(date -u +%Y%m%d%H%M%S)-$$"
RELEASE_DIR="${APP_ROOT}/releases/${RELEASE_ID}"
PREVIOUS_RELEASE=""

if [[ -z "${SOURCE_DIR}" || ! -f "${SOURCE_DIR}/pyproject.toml" ]]; then
  echo "Aufruf: sudo bash deploy/remote-install.sh /pfad/zum/repository" >&2
  exit 2
fi

if [[ "${EUID}" -ne 0 ]]; then
  echo "Die Installation muss mit Root-Rechten ausgefuehrt werden." >&2
  exit 2
fi

if [[ "$(uname -s)" != "Linux" ]] || ! command -v systemctl >/dev/null 2>&1; then
  echo "Unterstuetzt wird ein Linux-System mit systemd." >&2
  exit 2
fi

if command -v apt-get >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y \
    bluez \
    ca-certificates \
    curl \
    git \
    python3 \
    python3-pip \
    python3-venv \
    rfkill
else
  echo "Kein apt-Paketmanager gefunden; vorhandene Systempakete werden geprueft."
  for required_command in bluetoothctl curl python3 rfkill; do
    if ! command -v "${required_command}" >/dev/null 2>&1; then
      echo "Fehlendes Programm: ${required_command}" >&2
      echo "Zuerst BlueZ, Python 3.11+, venv, curl, CA-Zertifikate und rfkill installieren." >&2
      exit 2
    fi
  done
fi

if ! python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 11))'; then
  echo "MC3000 Control benoetigt Python 3.11 oder neuer." >&2
  python3 --version >&2
  exit 2
fi

systemctl unmask bluetooth.service >/dev/null 2>&1 || true
systemctl enable --now bluetooth.service
rfkill unblock bluetooth >/dev/null 2>&1 || true

if ! getent group bluetooth >/dev/null; then
  groupadd --system bluetooth
fi

if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
  useradd \
    --system \
    --home-dir "${DATA_DIR}" \
    --shell /usr/sbin/nologin \
    --user-group \
    "${SERVICE_USER}"
fi

usermod -a -G bluetooth "${SERVICE_USER}"
install -d -o root -g root -m 0755 "${APP_ROOT}/releases"
install -d -o "${SERVICE_USER}" -g "${SERVICE_USER}" -m 0750 "${DATA_DIR}"
install -d -o root -g root -m 0755 "${RELEASE_DIR}"

install -o root -g root -m 0644 "${SOURCE_DIR}/pyproject.toml" "${RELEASE_DIR}/"
install -o root -g root -m 0644 "${SOURCE_DIR}/README.md" "${RELEASE_DIR}/"
install -o root -g root -m 0644 "${SOURCE_DIR}/INSTALL_RASPBERRY_PI.md" "${RELEASE_DIR}/"
install -o root -g root -m 0644 "${SOURCE_DIR}/INSTALL_LINUX.md" "${RELEASE_DIR}/"
install -o root -g root -m 0644 "${SOURCE_DIR}/LICENSE" "${RELEASE_DIR}/"
for optional_document in \
  README.en.md \
  INSTALL_RASPBERRY_PI.en.md \
  INSTALL_LINUX.en.md \
  CHANGELOG.md \
  CONTRIBUTING.md \
  SECURITY.md; do
  if [[ -f "${SOURCE_DIR}/${optional_document}" ]]; then
    install -o root -g root -m 0644 \
      "${SOURCE_DIR}/${optional_document}" \
      "${RELEASE_DIR}/"
  fi
done
cp -a "${SOURCE_DIR}/mc3000_control" "${RELEASE_DIR}/"
cp -a "${SOURCE_DIR}/deploy" "${RELEASE_DIR}/"
cp -a "${SOURCE_DIR}/docs" "${RELEASE_DIR}/"

python3 -m venv "${RELEASE_DIR}/.venv"
"${RELEASE_DIR}/.venv/bin/pip" install --no-cache-dir --upgrade pip
"${RELEASE_DIR}/.venv/bin/pip" install --no-cache-dir "${RELEASE_DIR}"
"${RELEASE_DIR}/.venv/bin/python" -c \
  'import bleak, fastapi, mc3000_control, reportlab, segno, uvicorn'

if [[ -L "${APP_ROOT}/current" ]]; then
  PREVIOUS_RELEASE="$(readlink -f "${APP_ROOT}/current")"
fi

ln -sfn "${RELEASE_DIR}" "${APP_ROOT}/current.new"
mv -Tf "${APP_ROOT}/current.new" "${APP_ROOT}/current"

install -o root -g root -m 0644 \
  "${RELEASE_DIR}/deploy/mc3000-control.service" \
  /etc/systemd/system/mc3000-control.service

systemctl daemon-reload
systemctl enable mc3000-control.service
systemctl restart mc3000-control.service

HEALTH_PORT=8083
for environment_value in $(systemctl show mc3000-control.service --property=Environment --value); do
  if [[ "${environment_value}" == MC3000_PORT=* ]]; then
    HEALTH_PORT="${environment_value#MC3000_PORT=}"
  fi
done

HEALTHY=0
for _attempt in {1..30}; do
  if curl --fail --silent "http://127.0.0.1:${HEALTH_PORT}/api/health" >/dev/null; then
    HEALTHY=1
    break
  fi
  sleep 1
done

if [[ "${HEALTHY}" -ne 1 ]]; then
  systemctl --no-pager --full status mc3000-control.service || true
  journalctl -u mc3000-control.service -n 80 --no-pager || true
  if [[ -n "${PREVIOUS_RELEASE}" && -d "${PREVIOUS_RELEASE}" ]]; then
    echo "Die neue Version ist nicht gestartet; vorheriges Release wird wieder aktiviert." >&2
    ln -sfn "${PREVIOUS_RELEASE}" "${APP_ROOT}/current.new"
    mv -Tf "${APP_ROOT}/current.new" "${APP_ROOT}/current"
    systemctl restart mc3000-control.service
  fi
  exit 1
fi

systemctl --no-pager --full status mc3000-control.service

if ! bluetoothctl list 2>/dev/null | grep -q '^Controller '; then
  echo >&2
  echo "HINWEIS: BlueZ laeuft, aber es wurde noch kein Bluetooth-Controller erkannt." >&2
  echo "Internes Bluetooth aktivieren oder einen Linux-kompatiblen BLE-Adapter anschliessen." >&2
fi
