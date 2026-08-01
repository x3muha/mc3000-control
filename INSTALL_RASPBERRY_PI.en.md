# Installation on a fresh Raspberry Pi

Use the current **Raspberry Pi OS Lite 64-bit** image offered by Raspberry Pi Imager.
The installer supports Bookworm and Trixie with Python 3.11 or newer.

## 1. Write and start the image

In Raspberry Pi Imager select the Pi model and Raspberry Pi OS Lite 64-bit. Configure a
user, strong password, unique hostname, locale and network. Enable SSH, preferably with
an SSH public key. Write and verify the image, boot the Pi, then connect:

```bash
ssh <USER>@<HOSTNAME>.local
```

## 2. Transfer the release

Download `mc3000-control-<VERSION>.tar.gz` from the
[GitHub Releases page](https://github.com/x3muha/mc3000-control/releases), transfer it
to the Pi and extract it. A graphical SSH client or `scp` from another computer can
transfer the file. No package needs to be prepared on the Pi.

An operating-system update is recommended but not required. If a kernel or firmware
update was installed, reboot before continuing.

## 3. Run the installer

Enter the extracted release directory and run exactly:

```bash
./install.sh
```

The script requests `sudo` itself and installs Git, BlueZ, CA certificates, curl,
Python, venv, pip and rfkill. It enables Bluetooth, creates the restricted
`mc3000-control` service account, installs releases below `/opt/mc3000-control`, stores
persistent data below `/var/lib/mc3000-control`, enables systemd startup and waits for a
successful health response. A failed update automatically switches back to the previous
release.

The final output contains the detected address. Normally the UI is available at:

```text
http://<RASPBERRY-PI-IP>:8083/
```

Run `./deploy/check-installation.sh` for a repeatable installation check.

## 4. Connect a charger

Enable Bluetooth in the MC3000 global setup and fully disconnect the official phone
app. Do not pair the charger with `bluetoothctl`; MC3000 Control opens the BLE GATT
connection itself.

Open the connection manager in the web UI, start a scan, add each charger and assign a
clear local name. Only one BLE client can hold a charger connection at a time.

## 5. First safe program

Create or select the correct battery record, choose a compatible profile, verify
chemistry, capacity, current, end voltages, temperature and time limit, and apply it to
an idle slot. Applying a profile does not start it. Recheck the physical cell and click
Start only afterward.

## 6. Operation and updates

Useful commands:

```bash
systemctl status mc3000-control
journalctl -u mc3000-control -n 100 --no-pager
sudo systemctl restart mc3000-control
```

Back up data from Settings before updates. Extract a new release and run its
`./install.sh`; persistent data remains in `/var/lib/mc3000-control`.

The service is designed for a trusted local network. Enable the built-in login and use
HTTPS or a trusted VPN before traffic crosses an untrusted network. Never expose port
8083 directly to the internet.
