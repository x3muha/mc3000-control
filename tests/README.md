# Automatische Tests

Die Dateien in diesem Ordner sind keine Benutzerdokumente und werden auf einem
Produktivsystem nicht ausgeführt. Es sind kleine, reproduzierbare Prüfprogramme für
Entwicklung und Releases. Sie stellen sicher, dass Änderungen an einem Bereich keine
bereits funktionierende Geräte-, Sicherheits- oder Datenbankfunktion beschädigen.

Die Tests arbeiten grundsätzlich mit temporären Datenbanken und simulierten
Bluetooth-Verbindungen. Sie starten kein reales Lade- oder Entladeprogramm.

## Testbereiche

- `test_protocol.py` prüft MC3000-Paketaufbau, Prüfsummen, Statuswerte und Kurvendaten.
- `test_profiles.py` prüft Profilgrenzen, Zeitlimits und das 40-Byte-Profilformat.
- `test_ble_profile.py` simuliert Profilübertragung, Start, Stopp und Slotzuordnungen.
- `test_device_manager.py` prüft Suche, Verbindungsverwaltung und sicheres Entfernen.
- `test_registry.py` prüft das Geräteverzeichnis und gültige Bluetooth-Adressen.
- `test_battery_manager.py` prüft Batterieakten, C-Raten und automatisch erzeugte
  Programme.
- `test_storage.py` prüft SQLite-Speicherung, Messwerte, Läufe, Berichte, SOH,
  Nummernvergabe, Datenaufbewahrung und Löschung.
- `test_backup.py` prüft Erzeugung, Kontrolle und Wiederherstellung von ZIP-Backups.
- `test_pack_builder.py` prüft die Gruppierung vergleichbarer Zellen.
- `test_app_configuration.py` prüft die API für Profile, Sammelkonfiguration,
  Einstellungen, Kategorien und Login.
- `test_app_features.py` prüft die integrierten Funktionen wie QR-Code, PDF-Bericht,
  Meldungen, Backup und endgültige Batterielöschung.

## Tests ausführen

Eine Entwicklungsumgebung einrichten:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
```

Alle Python-Tests:

```bash
python -m pytest -q
```

Nur eine Datei:

```bash
python -m pytest -q tests/test_protocol.py
```

Nur einen bestimmten Test anhand seines Namens:

```bash
python -m pytest -q -k profile
```

Zusätzlich sollte die JavaScript-Syntax geprüft werden:

```bash
node --check mc3000_control/static/app.js
```

Ein fehlgeschlagener Test bedeutet nicht automatisch, dass Hardware beschädigt wurde.
Er zeigt, dass tatsächliches Verhalten und erwartetes Verhalten auseinanderliegen. Vor
einem Release muss geklärt werden, ob der Programmcode oder die Erwartung im Test falsch
ist.
