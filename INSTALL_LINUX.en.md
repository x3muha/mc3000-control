# Installation on another Linux host with BLE

MC3000 Control can run on a desktop, mini PC, notebook or home server. The host must run
Linux with systemd, reach the charger over Bluetooth Low Energy and remain powered while
the charger is used.

## Requirements

- Python 3.11 or newer
- BlueZ 5.55 or newer
- integrated Bluetooth LE or a Linux-supported USB Bluetooth adapter
- systemd and administrator access
- network access during package installation

Direct USB from host to MC3000 and Bluetooth SPP are not supported. A USB Bluetooth LE
adapter is supported through BlueZ.

## Debian, Ubuntu and Linux Mint

Extract the release archive, enter the directory and run:

```bash
./install.sh
```

The script installs all required APT and Python packages itself, enables Bluetooth,
creates the restricted service account, starts the service and verifies its local health
endpoint.

## Fedora

Install the distribution packages first:

```bash
sudo dnf install -y bluez ca-certificates curl git python3 python3-pip rfkill
sudo systemctl enable --now bluetooth.service
sudo rfkill unblock bluetooth
./install.sh
```

## Arch Linux

```bash
sudo pacman -S --needed bluez bluez-utils ca-certificates curl git python python-pip rfkill
sudo systemctl enable --now bluetooth.service
sudo rfkill unblock bluetooth
./install.sh
```

For non-APT systems the installer checks the existing commands but does not invoke the
distribution package manager.

## BLE preparation and diagnosis

Check the controller:

```bash
rfkill list bluetooth
bluetoothctl list
bluetoothctl show
bluetoothctl --timeout 15 scan on
```

The MC3000 may advertise as `Charger`, `SimpleBLEPeripheral` or `HitecCharger`. Do not
pair, trust or connect it with `bluetoothctl`. Close the official app because a charger
accepts one BLE client at a time.

If a USB adapter appears in `lsusb` but BlueZ has no controller, install the firmware
package for its chipset. Keep small adapters away from USB 3 cables and ports; a short
USB 2 extension often improves 2.4 GHz reception.

## Access and security

Open `http://<HOST-IP>:8083/` on the trusted local network. Use the built-in login and
HTTPS or a trusted VPN on untrusted links. Do not forward port 8083 directly from the
internet.

The systemd unit writes only to `/var/lib/mc3000-control`, uses a dedicated account and
is hardened with systemd sandboxing. The Settings page can create a full backup and an
anonymized diagnostics bundle.
