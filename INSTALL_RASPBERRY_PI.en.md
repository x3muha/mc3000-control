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

## 2. Choose an installation source

MC3000 Control can be installed from a fixed release or directly from the current Git
revision. The release is recommended for normal use.

### Option A: install a stable release (recommended)

1. Open the
   [GitHub Releases page](https://github.com/x3muha/mc3000-control/releases/latest) and
   download `mc3000-control-<VERSION>.tar.gz` from `Assets`. The matching `.sha256` file
   is optional.
2. Transfer the archive to the Raspberry Pi. A graphical SSH client can do this, or use
   `scp` on another computer:

   ```bash
   scp mc3000-control-<VERSION>.tar.gz <USER>@<HOSTNAME>.local:~/
   ```

3. On the Raspberry Pi, extract the archive, enter the new directory and run the
   installer:

   ```bash
   cd ~
   tar -xzf mc3000-control-<VERSION>.tar.gz
   cd mc3000-control-<VERSION>
   ./install.sh
   ```

Replace `<VERSION>`, `<USER>` and `<HOSTNAME>` with the actual values. This path does
not require any package to be prepared on the Pi. If the checksum file was transferred
as well, verify the archive before extracting it:

```bash
sha256sum -c mc3000-control-<VERSION>.tar.gz.sha256
```

### Option B: install the current Git revision

This path downloads the newest revision from the `main` branch, which may be newer than
the last release. Git is needed only for downloading; `./install.sh` prepares all other
requirements.

```bash
sudo apt update
sudo apt install -y git
git clone https://github.com/x3muha/mc3000-control.git
cd mc3000-control
./install.sh
```

An operating-system update is recommended but not required. If a kernel or firmware
update was installed, reboot before continuing.

## 3. Automatic installation

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

Back up data from Settings before updates. For a release installation, extract the new
release and run its `./install.sh`. For a Git installation, update the clone and run the
installer again:

```bash
cd ~/mc3000-control
git pull --ff-only
./install.sh
```

Persistent data remains in `/var/lib/mc3000-control` with either path.

The service is designed for a trusted local network. Enable the built-in login and use
HTTPS or a trusted VPN before traffic crosses an untrusted network. Never expose port
8083 directly to the internet.
