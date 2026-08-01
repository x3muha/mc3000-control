#!/usr/bin/env bash
set -euo pipefail

FAILED=0
SERVICE_PORT=8083

for environment_value in $(systemctl show mc3000-control.service --property=Environment --value 2>/dev/null); do
  if [[ "${environment_value}" == MC3000_PORT=* ]]; then
    SERVICE_PORT="${environment_value#MC3000_PORT=}"
  fi
done

check() {
  local label="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    printf 'OK   %s\n' "${label}"
  else
    printf 'FEHLER %s\n' "${label}"
    FAILED=1
  fi
}

in_bluetooth_group() {
  id -nG mc3000-control | tr ' ' '\n' | grep -qx bluetooth
}

bluetooth_controller_present() {
  bluetoothctl list 2>/dev/null | grep -q '^Controller '
}

supported_python() {
  /opt/mc3000-control/current/.venv/bin/python -c \
    'import sys; raise SystemExit(sys.version_info < (3, 11))'
}

check "Bluetooth-Dienst aktiv" systemctl is-active --quiet bluetooth
check "Bluetooth-Controller erkannt" bluetooth_controller_present
check "MC3000-Control-Dienst aktiv" systemctl is-active --quiet mc3000-control
check "HTTP-Zustandsabfrage" curl --fail --silent "http://127.0.0.1:${SERVICE_PORT}/api/health"
check "Datenordner vorhanden" test -d /var/lib/mc3000-control
check "Dienstbenutzer in Bluetooth-Gruppe" in_bluetooth_group
check "Python-Version mindestens 3.11" supported_python

echo
systemctl --no-pager --full status mc3000-control.service || true
echo
curl --silent "http://127.0.0.1:${SERVICE_PORT}/api/health" || true
echo

exit "${FAILED}"
