# MC3000 Control

[English documentation](README.en.md) · Demo nach Installation: `/?demo=1`

MC3000 Control ist eine lokale, responsive Weboberfläche für ein oder mehrere
SkyRC-MC3000-Ladegeräte. Ein Linux-Rechner mit Bluetooth LE hält die
Geräteverbindungen, zeichnet Messwerte auf und stellt Steuerung, Profile,
Batterieakten und Berichte im lokalen Netzwerk bereit. Der Browser benötigt
kein eigenes Bluetooth.

Das Projekt ist eine unabhängige Software und steht in keiner Verbindung zum
Hersteller SkyRC.

![Kurzdemo von Liveansicht, Profilen und Aufzeichnungen](docs/media/mc3000-control-demo.gif)

Weitere Ansichten: [Dashboard im Darkmode](docs/images/dashboard-dark.png) ·
[Profilbibliothek](docs/images/profiles.png) ·
[Aufzeichnungen](docs/images/recordings.png) ·
[WebM-Kurzdemo](docs/media/mc3000-control-demo.webm)

## Feature-Übersicht

### Ladegeräte und Slots

- Gleichzeitiger Betrieb mehrerer MC3000 über Bluetooth Low Energy
- Liveübersicht aller vier Slots pro Ladegerät
- Spannung, Strom, Kapazität, Temperatur, Innenwiderstand und Laufzeit
- Direkter Start und Stopp einzelner Slots sowie gemeinsamer Start und Stopp
- Automatische Wiederverbindung nach Funkunterbrechungen
- Verbindungsmanager zum Suchen, Einrichten, Umbenennen, Trennen und Entfernen
- Frei wählbare Gerätenamen und optionale Seriennummer vom Typenschild
- Anzeige von Verbindungsqualität, Eingangsspannung und BLE-Lüfterregelung
- Auslesen der im MC3000 gespeicherten Spannungskurve
- Freigabe einer BLE-Verbindung für die offizielle Smartphone-App

### Programme und Profile

- Lokale Profilbibliothek für Li-Ion, LiFePO4 und NiMH
- Eigene Profile und Kategorien mit Anlegen, Bearbeiten, Duplizieren und Löschen
- Profilübertragung auf einen oder mehrere frei wählbare Slots
- Getrennte Schritte für Konfiguration und Programmstart
- Individuelle Standardprogramme je Batterieakte
- Sammelkonfiguration mehrerer Slots
- Automatikprogramme für schonendes Laden, Standardladen, Kapazitätstest,
  Refresh und Zyklen
- Automatische Stromberechnung aus Nennkapazität und C-Rate
- Begrenzung berechneter Ströme auf 3 A Laden und 2 A Entladen
- Zeitlimit wahlweise automatisch berechnet, manuell festgelegt oder deaktiviert
- Schutz vor parallelen Konfigurationsaufträgen und doppelten Batterieakten
- Portabler JSON-Import und -Export kompletter Profilbibliotheken

### Liveansicht und Diagramme

- Rollende Livekurven für Spannung und Strom
- Historische Diagramme für Spannung, Strom, Temperatur, Innenwiderstand und
  Kapazität
- Programmphasen als farbige Flächen: Laden grün, Pause orange und Entladen rot
- Neutrale Darstellung von Messwerten außerhalb eines Programmlaufs
- Negative Darstellung von Entladestrom
- Exakte Tooltips mit Uhrzeit, Programmdauer und Messwertbezeichnung
- Synchroner Auswahl-Zoom für zusammengehörige Diagramme
- Einstellbare Deckkraft der Phasenflächen
- Helles, dunkles oder automatisch übernommenes Systemfarbschema

### Batterieakten

- Eindeutige Batterienummern und optionale automatische Nummernvergabe
- Chemie, Nennkapazität, Name, Hersteller, Modell, Bauform und Herkunft
- Datum „In Betrieb seit“, Protection-Kennzeichen und freie Notizen
- Eingabevorschläge aus vorhandenen Batterieakten
- Optionaler Betrieb ohne Batterieakte
- Archiv mit Wiederherstellung
- Bestätigte endgültige Löschung inklusive Messwerten, Läufen und Berichten
- Wiederverwendung endgültig gelöschter Batterienummern
- QR-Etiketten und Batterie-Steckblätter als PDF

### Auswertung und Berichte

- Automatische Erkennung und Speicherung von Programmläufen
- Kapazitäts-SOH aus geeigneten Entladetests
- Soll/Ist-Auswertung abgeschlossener Entladephasen
- Entwicklung des Innenwiderstands
- Vergleich von bis zu fünf Programmläufen
- Abschlussberichte mit Kapazität, Energie, Temperatur, Innenwiderstand,
  Laufzeit und Auffälligkeiten
- Soll- und Ist-Markierungen direkt im Kapazitätsdiagramm
- Prüfberichte als PDF
- Zellen-Sortierer für Gruppen mit ähnlicher Kapazität und ähnlichem
  Innenwiderstand

### Daten, Betrieb und Zugriff

- Lokale SQLite-Datenbank ohne externen Cloud-Dienst
- Konfigurierbare Aufzeichnungs- und Aufbewahrungsintervalle
- CSV-Export nach Gerät, Slot, Zeitraum oder Batterieakte
- ZIP-Backup und kontrollierte Wiederherstellung der vollständigen Datenbank
- Meldungszentrale und optionale Browser-Benachrichtigungen bei Programmende
- Optionaler Login für Oberfläche, API und Liveverbindung
- Passwortspeicherung mit scrypt und individuellem Salt
- Responsive Oberfläche für Desktop, Tablet und Smartphone
- Anklickbare Versionsanzeige mit den Änderungen der installierten Version
- Deutsche und englische Oberfläche
- Schreibgeschützter Demo-Modus mit realistischen Beispieldaten
- Anonymisiertes Diagnosepaket ohne Datenbank, Adressen oder private Metadaten
- Installierbare Progressive Web App; Steuerungs- und API-Antworten werden nie
  offline zwischengespeichert

## Voraussetzungen

- Raspberry Pi oder ein anderer Linux-Rechner mit Bluetooth LE
- BlueZ 5.55 oder neuer
- Python 3.11 oder neuer
- SkyRC MC3000 mit aktiviertem Bluetooth

Das MC3000 wird direkt als BLE-Gerät angesprochen und nicht über die normale
Bluetooth-Einstellungsseite gekoppelt. Pro Ladegerät kann immer nur ein BLE-Client
verbunden sein. Die offizielle Smartphone-App muss deshalb getrennt sein, solange
MC3000 Control das Gerät verwendet.

## Installation auf einem Raspberry Pi

Eine vollständige Anleitung für ein frisches Raspberry Pi OS Lite 64 Bit steht in
[INSTALL_RASPBERRY_PI.md](INSTALL_RASPBERRY_PI.md).

Das Release-Archiv auf den Raspberry Pi übertragen, entpacken und im entpackten Ordner
nur das Installationsskript starten:

```bash
./install.sh
```

Es müssen vorher weder Git noch Python, BlueZ oder Python-Pakete eingerichtet werden.
Das Skript fordert selbstständig Administratorrechte an, installiert alle benötigten
System- und Python-Abhängigkeiten, aktiviert Bluetooth, richtet einen eigenen
Systembenutzer sowie eine isolierte Python-Umgebung ein und prüft den gestarteten Dienst.
Die Oberfläche ist anschließend unter
`http://<IP-DES-RASPBERRY-PI>:8083/` erreichbar.

Für Debian, Ubuntu, Fedora, Arch Linux und andere Rechner mit Bluetooth LE siehe
[INSTALL_LINUX.md](INSTALL_LINUX.md).

## Demo

Mit `http://<HOST>:8083/?demo=1` wird eine schreibgeschützte Beispielsitzung im Browser
geöffnet. Sie enthält Lade-, Pausen- und Entladephasen, Batterieakten, Profile und einen
abgeschlossenen Kapazitätstest. Der Demo-Modus öffnet keine WebSocket- oder
Bluetooth-Verbindung und sendet keine Schreibbefehle an die API.

Für die Installation als PWA verlangen aktuelle Browser einen sicheren Kontext. Dafür
muss MC3000 Control über HTTPS bereitgestellt oder direkt als `localhost` geöffnet
werden; die normale Bedienung im lokalen Netz funktioniert weiterhin über HTTP.

## Kompatibilität

| Komponente | Status |
| --- | --- |
| MC3000 Hardware 2.2 / Firmware 1.25 | praktisch verifiziert |
| Andere MC3000-Versionen mit bekanntem BLE-GATT-Protokoll | vorgesehen; Rückmeldungen willkommen |
| Raspberry Pi OS Lite 64 Bit (Bookworm/Trixie) | automatische Installation unterstützt |
| Python 3.11, 3.12 und 3.13 | automatisiert getestet |
| BlueZ ab 5.55 | unterstützt |
| Direkte USB-Verbindung / Bluetooth SPP | nicht unterstützt |

Weitere Einzelheiten: [Kompatibilitätsmatrix](docs/COMPATIBILITY.md).

## Entwicklungsstart

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
mc3000-control
```

Standardmäßig läuft die Entwicklungsinstanz unter `http://127.0.0.1:8083/`.
Port und Datenverzeichnis lassen sich anpassen:

```bash
MC3000_PORT=8090 MC3000_DATA_DIR=./data mc3000-control
```

## Wichtige Betriebsgrenzen

- Der bekannte BLE-Datensatz enthält keine vollständige Rücklesefunktion für
  gespeicherte Profilparameter.
- Über BLE sind Lüfterregelung, aber keine verlässliche Lüfterdrehzahl und keine
  interne Systemtemperatur des Ladegeräts verfügbar.
- USB und Bluetooth SPP werden nicht unterstützt.
- Ein Profil wird beim Übertragen nicht automatisch gestartet.
- Ein automatischer Neustart der Anwendung startet keine Lade- oder
  Entladeprogramme selbstständig.

Vor jedem Programmstart müssen Akkutyp, Nennkapazität, Strom, Spannungsgrenzen,
Temperaturlimit und Batteriezuordnung geprüft werden. Die Auswertungen ersetzen
keine fachgerechte Sicherheitsprüfung einer Zelle oder eines Akkupacks.

## Tests

Die Dateien unter `tests/` sind automatisierte Prüfprogramme. Sie verwenden temporäre
Datenbanken und simulierte Bluetooth-Verbindungen; sie starten keine Programme auf einem
realen Ladegerät. Eine Beschreibung jedes Testbereichs steht in
[tests/README.md](tests/README.md).

```bash
python -m pytest -q
node --check mc3000_control/static/app.js
```

## Weitere Dokumentation

- [Installation und Betrieb](INSTALL_RASPBERRY_PI.md)
- [Installation auf anderen Linux-Systemen](INSTALL_LINUX.md)
- [English installation on Raspberry Pi](INSTALL_RASPBERRY_PI.en.md)
- [English installation on other Linux systems](INSTALL_LINUX.en.md)
- [Kompatibilitätsmatrix](docs/COMPATIBILITY.md)
- [BLE-Protokollnotizen](docs/BLE_PROTOCOL.md)
- [Automatische Tests](tests/README.md)
- [Änderungsprotokoll](CHANGELOG.md)
- [Beiträge](CONTRIBUTING.md)
- [Sicherheitsrichtlinie](SECURITY.md)
- [Sicherheitsprüfung für Version 1.0](docs/SECURITY_REVIEW.md)

## Lizenz

Dieses Projekt steht unter der [MIT-Lizenz](LICENSE).
