# Installation auf einem Linux-Rechner mit Bluetooth LE

MC3000 Control kann außer auf einem Raspberry Pi auch auf einem gewöhnlichen
Linux-PC, Mini-PC, Notebook oder Heimserver laufen. Der Rechner muss während der
Nutzung eingeschaltet sein, das MC3000 per Bluetooth Low Energy erreichen und aus
dem gewünschten lokalen Netzwerk erreichbar sein.

Für Raspberry Pi OS gibt es eine separate
[Schritt-für-Schritt-Anleitung](INSTALL_RASPBERRY_PI.md).

## 1. Systemanforderungen

Benötigt werden:

- Linux mit systemd
- Python 3.11 oder neuer
- BlueZ 5.55 oder neuer
- integriertes Bluetooth LE oder ein Linux-kompatibler USB-Bluetooth-Adapter
- Netzwerkzugang für die Weboberfläche und die Installation der Python-Pakete
- Rootrechte über `sudo` oder eine Root-Shell

Gut geeignet sind aktuelle Versionen von Debian, Ubuntu, Linux Mint und Fedora.
Eine Installation in Docker, LXC oder einer virtuellen Maschine ist möglich, erfordert
aber zusätzlich die Durchleitung des Bluetooth-Controllers und des System-D-Bus. Eine
native Installation auf dem Host ist deutlich einfacher und zuverlässiger.

Ein USB-Bluetooth-Adapter ist unterstützt. Nicht unterstützt werden eine direkte
USB-Verbindung zum MC3000 und Bluetooth SPP. Das Ladegerät wird ausschließlich über
Bluetooth Low Energy angesprochen.

## 2. Bluetooth-Hardware prüfen

Bei einem internen Adapter genügt zunächst:

```bash
lsusb
rfkill list bluetooth
```

Bei einem USB-Adapter diesen vor der Installation anschließen. Er sollte in `lsusb`
erscheinen. Sehr alte reine Bluetooth-2.x-Adapter sind ungeeignet; der Adapter muss
Bluetooth Low Energy unterstützen.

Auf einem stationären Rechner sind außerdem sinnvoll:

- ein kurzer USB-2.0-Verlängerer, wenn der Adapter direkt neben USB-3.0-Geräten sitzt,
- Abstand zu ungeschirmten USB-3.0-Kabeln,
- Ethernet statt 2,4-GHz-WLAN bei instabiler Funkverbindung und
- möglichst freie Sicht zwischen Adapter und Ladegerät.

## 3. Systempakete installieren

### Debian, Ubuntu und Linux Mint

```bash
sudo apt update
sudo apt install -y \
  bluez \
  ca-certificates \
  curl \
  git \
  python3 \
  python3-pip \
  python3-venv \
  rfkill
```

Die automatische Installationsroutine installiert diese Pakete auf Systemen mit APT
selbst. Bei der Installation aus einem Release-Archiv ist keine Vorbereitung nötig.

### Fedora

```bash
sudo dnf install -y \
  bluez \
  ca-certificates \
  curl \
  git \
  python3 \
  python3-pip \
  rfkill
```

### Arch Linux

```bash
sudo pacman -S --needed \
  bluez \
  bluez-utils \
  ca-certificates \
  curl \
  git \
  python \
  python-pip \
  rfkill
```

Auf anderen Distributionen werden die entsprechenden Pakete für BlueZ,
`bluetoothctl`, Python mit `venv`, `curl`, CA-Zertifikate, Git und `rfkill` benötigt.

Versionen kontrollieren:

```bash
python3 --version
bluetoothctl --version
```

Ist Python älter als 3.11, muss zuerst eine aktuelle, von der Distribution gepflegte
Python-Version installiert werden. Die System-Python-Installation darf nicht mit
`sudo pip` verändert werden; MC3000 Control verwendet eine eigene virtuelle Umgebung.

## 4. BlueZ starten und Controller aktivieren

```bash
sudo systemctl unmask bluetooth.service
sudo systemctl enable --now bluetooth.service
sudo rfkill unblock bluetooth
```

Danach prüfen:

```bash
systemctl is-active bluetooth.service
bluetoothctl list
bluetoothctl show
```

Erwartet werden ein Eintrag `Controller ...` und bei `bluetoothctl show` der Zustand
`Powered: yes`. Falls der Controller ausgeschaltet bleibt:

```bash
sudo bluetoothctl power on
```

### Fehlende Firmware

Wenn `lsusb` oder `lspci` einen Adapter zeigt, `bluetoothctl list` aber leer bleibt,
fehlt häufig Firmware:

- Debian: je nach Hardware beispielsweise `firmware-iwlwifi`; dafür muss in aktuellen
  Debian-Versionen die Paketkomponente `non-free-firmware` aktiviert sein.
- Ubuntu: das Paket `linux-firmware` installieren oder aktualisieren.
- Bei USB-Adaptern die Hersteller- und Chipsatzangaben mit der Linux-Unterstützung
  vergleichen.

Nach einer Firmwareinstallation den Rechner neu starten und die Prüfung wiederholen.

## 5. MC3000 per BLE finden

Am MC3000 Bluetooth im globalen Setup aktivieren und die offizielle Smartphone-App
vollständig schließen. Pro Ladegerät kann nur ein BLE-Client gleichzeitig verbunden
sein.

Ein zeitlich begrenzter Testscan:

```bash
bluetoothctl --timeout 15 scan on
```

Je nach Firmware erscheint das MC3000 beispielsweise als `Charger`,
`SimpleBLEPeripheral` oder `HitecCharger`.

Das MC3000 nicht mit `bluetoothctl pair`, `trust` oder `connect` koppeln. MC3000 Control
öffnet die benötigte BLE-GATT-Verbindung selbst.

## 6. MC3000 Control installieren

Das aktuelle Release-Archiv entpacken, in den Ordner wechseln und `./install.sh`
ausführen. Auf Debian-, Ubuntu- und Mint-Systemen installiert das Skript alle benötigten
Systempakete selbst. Auf anderen Distributionen müssen die in Abschnitt 3 genannten
Pakete vorhanden sein.

Das Skript fordert über `sudo` Administratorrechte an und führt anschließend aus:

1. System- und Python-Voraussetzungen prüfen.
2. BlueZ aktivieren und Bluetooth entsperren.
3. Eigenen Systembenutzer `mc3000-control` anlegen.
4. Den Benutzer in die Gruppe `bluetooth` aufnehmen.
5. Eine isolierte Python-Umgebung unter `/opt/mc3000-control` erstellen.
6. Den dauerhaften Datenordner `/var/lib/mc3000-control` anlegen.
7. Den abgesicherten systemd-Dienst installieren und aktivieren.
8. Auf eine erfolgreiche lokale Zustandsabfrage warten.

Jede Installation erzeugt ein eigenes Releaseverzeichnis. Erst nach erfolgreicher
Paketinstallation wird `/opt/mc3000-control/current` auf das neue Release umgeschaltet.
Startet die neue Version nicht, aktiviert das Skript bei einem Update wieder das vorherige
Release.

Installation kontrollieren:

```bash
./deploy/check-installation.sh
```

## 7. Weboberfläche aufrufen

Die IP-Adressen des Rechners anzeigen:

```bash
hostname -I
ip -brief address
```

Im Browser eines Geräts im selben Netzwerk öffnen:

```text
http://<IP-ADRESSE>:8083/
```

Auf dem Installationsrechner selbst funktioniert auch:

```text
http://127.0.0.1:8083/
```

MC3000 Control lauscht standardmäßig auf allen Netzwerkschnittstellen. Die Oberfläche
sollte nicht ungefiltert aus dem Internet erreichbar gemacht werden. Unter
`Einstellungen` kann ein Login aktiviert werden.

### Firewall

Bei aktiver UFW-Firewall kann Port 8083 nur für das eigene lokale Netz freigegeben werden.
Das Beispielnetz muss an die eigene Umgebung angepasst werden:

```bash
sudo ufw allow from 192.168.1.0/24 to any port 8083 proto tcp
```

Bei `firewalld` kann der Port für die dem lokalen Netz zugewiesene Zone freigegeben
werden, beispielsweise:

```bash
sudo firewall-cmd --permanent --zone=home --add-port=8083/tcp
sudo firewall-cmd --reload
```

## 8. Erstes Ladegerät einrichten

1. Weboberfläche öffnen.
2. Den Verbindungsmanager oben rechts öffnen.
3. `Neu suchen` wählen.
4. Das gefundene MC3000 auswählen und einen eindeutigen Gerätenamen vergeben.
5. Warten, bis Gerätedaten und alle vier Slots erscheinen.
6. Vor einem Start Akkutyp, Profil, Ströme, Spannungsgrenzen und Temperaturgrenze prüfen.

Eine Bluetooth-Adresse muss nicht in einer Konfigurationsdatei eingetragen werden. Die
registrierten Geräte werden in der lokalen SQLite-Datenbank gespeichert.

## 9. Verzeichnisse und Dienstbetrieb

Wichtige Pfade:

```text
/opt/mc3000-control/current/       aktuell ausgeführtes Release
/opt/mc3000-control/releases/      installierte Releases
/var/lib/mc3000-control/           Datenbank und Rückfall-Backups
/etc/systemd/system/mc3000-control.service
```

Nützliche Befehle:

```bash
systemctl status mc3000-control.service
journalctl -u mc3000-control.service -n 200 --no-pager
sudo systemctl restart mc3000-control.service
curl --fail http://127.0.0.1:8083/api/health
```

## 10. Updates

```bash
cd mc3000-control
git pull --ff-only
./install.sh
```

Die Datenbank liegt außerhalb des Quellcodes und außerhalb der Releaseverzeichnisse. Ein
Update überschreibt sie nicht. Vor größeren Änderungen empfiehlt sich trotzdem ein
ZIP-Backup über `Einstellungen`.

## 11. Fehlersuche

### Kein Bluetooth-Controller

```bash
rfkill list bluetooth
bluetoothctl list
journalctl -u bluetooth.service -n 100 --no-pager
```

Mögliche Ursachen sind eine Hardware-Sperre, fehlende Firmware, ein ungeeigneter Adapter,
ein deaktivierter Controller im BIOS oder fehlende USB-Durchleitung in einer virtuellen
Maschine.

### MC3000 wird nicht gefunden

- Bluetooth am MC3000 einschalten.
- Smartphone-App vollständig schließen.
- Abstand verkleinern.
- Sicherstellen, dass nicht bereits ein anderer Rechner verbunden ist.
- BlueZ und MC3000 Control neu starten.

```bash
sudo systemctl restart bluetooth.service
sudo systemctl restart mc3000-control.service
```

### Dienst startet nicht

```bash
systemctl --no-pager --full status mc3000-control.service
journalctl -u mc3000-control.service -n 200 --no-pager
```

Die Installationsprüfung fasst die wichtigsten Kontrollen zusammen:

```bash
./deploy/check-installation.sh
```

### Port ändern

```bash
sudo systemctl edit mc3000-control.service
```

Eintragen:

```ini
[Service]
Environment=MC3000_PORT=8090
```

Danach:

```bash
sudo systemctl daemon-reload
sudo systemctl restart mc3000-control.service
```

Die Firewallregel und die Browseradresse müssen ebenfalls auf den neuen Port angepasst
werden.
