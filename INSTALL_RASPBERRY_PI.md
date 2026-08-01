# Installation auf einem neuen Raspberry Pi

Diese Anleitung führt von einem frisch geschriebenen Raspberry-Pi-Image bis zur
laufenden Weboberfläche. Empfohlen wird das im Raspberry Pi Imager als aktuell
gekennzeichnete **Raspberry Pi OS Lite 64 Bit**. Die automatische Installation
unterstützt Raspberry Pi OS Trixie und Bookworm mit Python 3.11 oder neuer.

Für Debian, Ubuntu und andere Linux-Rechner steht eine eigene
[Linux- und BLE-Anleitung](INSTALL_LINUX.md) bereit.

## 1. Raspberry Pi vorbereiten

Benötigt werden:

- Raspberry Pi 3B+, 4, 5 oder Zero 2 W
- zuverlässiges Netzteil
- Netzwerkzugang über Ethernet oder WLAN
- integriertes Bluetooth oder ein Linux-kompatibler USB-Bluetooth-Adapter
- Raspberry Pi OS Lite 64 Bit

Im Raspberry Pi Imager:

1. Das Raspberry-Pi-Modell auswählen.
2. Unter `Raspberry Pi OS (other)` die aktuelle Ausgabe von
   `Raspberry Pi OS Lite (64-bit)` auswählen.
3. In der Betriebssystem-Anpassung einen Benutzer, ein sicheres Passwort und einen
   eindeutigen Hostnamen festlegen, beispielsweise `mc3000-pi`.
4. Unter `Dienste` SSH aktivieren, bevorzugt mit einem vorhandenen SSH-Schlüssel.
5. Bei WLAN-Nutzung SSID, Passwort und WLAN-Land eintragen.
6. Zeitzone und Tastaturlayout kontrollieren.
7. Image schreiben, prüfen lassen und den Pi starten.

Anschließend per SSH anmelden:

```bash
ssh pi@mc3000-pi.local
```

## 2. Grundsystem vorbereiten

Nach dem ersten Start werden nur Git und aktuelle Paketlisten benötigt. Alle weiteren
Abhängigkeiten richtet `install.sh` automatisch ein:

```bash
sudo apt update
sudo apt install -y git
```

Ein vollständiges Systemupdate ist empfehlenswert, aber keine Voraussetzung für die
Installation:

```bash
sudo apt full-upgrade -y
```

Falls dabei Kernel- oder Firmwarepakete aktualisiert wurden, anschließend neu starten:

```bash
sudo reboot
```

Die spätere Installationsroutine installiert BlueZ, Python, die virtuelle Python-Umgebung,
`curl`, `rfkill` und alle Python-Abhängigkeiten. Sie aktiviert außerdem den
Bluetooth-Dienst und hebt eine vorhandene Bluetooth-Sperre auf.

## 3. Anwendung installieren

Den öffentlichen Quellcode abrufen und die Installation starten:

```bash
git clone https://github.com/x3muha/mc3000-control.git
cd mc3000-control
./install.sh
```

`install.sh` fordert selbstständig über `sudo` Administratorrechte an. Das Skript:

- installiert fehlende Systempakete,
- prüft Python 3.11 oder neuer,
- aktiviert BlueZ,
- richtet den abgeschotteten Benutzer `mc3000-control` ein,
- installiert die Anwendung unter `/opt/mc3000-control`,
- legt dauerhafte Daten unter `/var/lib/mc3000-control` ab,
- aktiviert den automatischen Start und
- wartet auf eine erfolgreiche Zustandsabfrage der Webanwendung.

Danach kann die Installation erneut geprüft werden:

```bash
./deploy/check-installation.sh
```

Die Weboberfläche ist anschließend erreichbar unter:

```text
http://mc3000-pi.local:8083/
```

Falls `.local` im verwendeten Netzwerk nicht aufgelöst wird, zeigt `hostname -I` die
IP-Adresse des Raspberry Pi:

```bash
hostname -I
```

## 4. Ladegeräte vorbereiten

Für jedes MC3000:

1. Ladegerät über sein Netzteil einschalten.
2. Bluetooth im globalen Setup des MC3000 aktivieren.
3. Die offizielle Handy-App vollständig schließen oder deren Verbindung trennen.
4. Ladegerät in Funkreichweite des Raspberry Pi aufstellen.

Keine Kopplung über `bluetoothctl pair` durchführen. Das Ladegerät wird direkt über BLE
angesprochen.

Ein Testscan kann so gestartet werden:

```bash
bluetoothctl
```

In der Eingabeaufforderung:

```text
scan on
```

Nach einigen Sekunden sollte mindestens ein Gerät mit dem Namen `Charger`,
`SimpleBLEPeripheral` oder `HitecCharger` erscheinen. Scan anschließend mit `scan off`
beenden und `quit` eingeben.

## 5. Ladegeräte einrichten

1. Weboberfläche öffnen.
2. Oben rechts den Verbindungsmanager öffnen.
3. Falls nötig `Neu suchen` wählen. Die Suche trennt bereits verbundene Ladegeräte nicht.
4. Bei jedem neuen Ladegerät `Verbinden` wählen.
5. Aussagekräftige Namen vergeben, zum Beispiel `Werkbank links` und `Werkbank rechts`.
6. Warten, bis bei beiden Geräten `Verbunden` angezeigt wird.

Die Geräteadresse wird nur lokal in SQLite gespeichert. Sie muss nicht manuell in eine
Konfigurationsdatei geschrieben werden. Im selben Manager lassen sich getrennte Geräte
wieder verbinden und nicht mehr benötigte Registrierungen entfernen. Ein Ladegerät mit
laufendem Programm ist gegen das Entfernen geschützt; Messdaten und Batterieakten werden
dabei grundsätzlich nicht gelöscht.

## 6. Ladeprofile verwalten

Die Profile der offiziellen Handy-App werden auf dem Handy gespeichert. Sie lassen sich
nicht aus dem Ladegerät in MC3000 Control importieren. Die Weboberfläche verwaltet deshalb
eine eigene Profilbibliothek auf dem Raspberry Pi:

1. `Profile` öffnen.
2. Über `Alle Profile`, `Automatische Profile`, `Lithium-Profile` oder
   `Eigene Profile` die gewünschte Unterkategorie wählen.
3. Ein vorhandenes Beispiel bearbeiten, mit `Duplizieren` als vorausgefüllte und
   unabhängig bearbeitbare Kopie öffnen oder `Profil anlegen` wählen.
4. Ein Automatikprogramm kann über `Bei Slot wählen` vorgemerkt und anschließend beim
   gewünschten Ladegerät über `Programm wählen` übernommen werden.
5. Akkutyp und Programm festlegen.
6. Ströme, Spannungsgrenzen und Abschaltbedingungen kontrollieren.
7. Profil speichern.
8. `Anwenden` wählen, Ladegerät und freie Slots markieren und die Bestätigung eingeben.
9. Akkudaten und Slotzustand nochmals prüfen.
10. Den gewünschten Slot anschließend mit `Start` direkt starten.

Das Anwenden startet keinen Ladevorgang. Aktive Slots lassen sich nicht mit einem anderen
Profil überschreiben. Alternativ kann ein Profil direkt in der Ladegeräteansicht über
`Programm wählen` zusammen mit einer Batterienummer für genau einen Slot ausgewählt
werden. Dabei wird die Profilkapazität vorausgefüllt und kann nur für diese Zuweisung
geändert werden; das gespeicherte Profil bleibt unverändert. Unter `Alle Programme` ist
dieser Kapazitätswert für jeden Slot separat einstellbar.

## 7. Batteriemanager verwenden

Jede physische Batterie kann eine dauerhafte Akte erhalten:

1. `Batterien` öffnen.
2. `Neue Batterie` wählen.
3. Eine eindeutige Nummer eintragen, beispielsweise `001`.
4. Li-Ion oder LiFePO4 und die aufgedruckte Nennkapazität eintragen.
5. Batterie speichern.
6. `Standardprogramm` öffnen.
7. Programm und C-Raten auswählen.
8. Bei einem Zyklusprogramm zusätzlich Anzahl und Reihenfolge festlegen.
9. Berechnete Ströme und Spannungsgrenzen prüfen.
10. Standardprogramm speichern.

Das Standardprogramm gehört zur Batterieakte. Es enthält weder ein Ladegerät noch einen
Slot und kann daher auch geändert werden, wenn kein MC3000 verbunden ist.

Die Batterie kann anschließend direkt am belegten Slot ausgewählt werden:

1. `Ladegeräte` öffnen.
2. Beim gewünschten Slot `Programm wählen` wählen.
3. Die eingelegte Batterienummer auswählen oder für einen nicht katalogisierten Akku
   `Keine Batterie · ohne Langzeitakte` beibehalten. Mit
   `Neue Batterie automatisch anlegen` die Anlage einer neuen Akte vormerken und rechts
   die tatsächliche Nennkapazität eintragen. Die nächste fortlaufende Batterienummer
   wird erst beim Übernehmen erzeugt und dem Slot zugeordnet.
4. Das Standardprogramm der Batterie, ein Automatikprogramm oder ein kompatibles
   Ladeprofil auswählen.
5. Bei einem Automatikprogramm die auf dem Akku angegebene Kapazität in mAh eintragen.
6. Das Zeitlimit wählen. Für Tests ist zunächst `Manuell · 6 Stunden` vorausgewählt.
7. Vorschau prüfen und `Für Slot übernehmen` wählen.
8. Den Slot mit `Start` sofort starten.

Nach dem Übernehmen erscheint direkt am Slot `Batteriedaten`. Darüber können Name,
Chemie, Hersteller, Typ oder Modell, Bauform, Herkunft und Notizen ergänzt werden. Die
Bearbeitung bleibt auch während eines laufenden Programms möglich und stoppt die Messung
nicht.

Die Automatikprogramme berechnen den Strom aus der eingegebenen Kapazität:

- `Schonend laden`: 0,5 C laden
- `Standard laden`: 1 C laden
- `Kapazitätstest`: 1 C entladen
- `Refresh`: 0,5 C laden, 1 C entladen und anschließend erneut mit 0,5 C laden
- `Zyklus C-D-C`: 0,5 C laden, 1 C entladen und erneut laden

Bei 2000 mAh entsprechen 0,5 C einem Ladestrom von 1000 mA und 1 C einem
Entladestrom von 2000 mA. Überschreitet die Berechnung 3 A Ladestrom oder 2 A
Entladestrom, wird sie automatisch auf die jeweilige Gerätegrenze reduziert.

Das Zeitlimit kann für Profile und automatisch erzeugte Programme eingestellt werden:

- `Automatisch` berechnet jede benötigte Lade- und Entladephase als
  `Kapazität / tatsächlicher Strom × 1,5` und addiert die Pausen.
- `Manuell` überträgt die eingestellte Dauer. Standardmäßig sind 6 Stunden eingetragen.
- `Aus` überträgt 0 und deaktiviert den Zeitabbruch.

Sollen mehrere eingelegte Batterien gemeinsam beginnen, zuerst jeden Slot wie oben
einrichten und danach beim Ladegerät `Alle starten` wählen. So kann jeder Slot ein eigenes
Programm verwenden.

Alternativ beim Ladegerät `Alle Programme` öffnen:

1. Für jeden erkannten, belegten Slot optional die richtige Batterienummer auswählen.
   Für normale Akkus `Keine Batterie · ohne Langzeitakte` verwenden. Neue Akten können
   hier je Slot direkt mit fortlaufender Nummer angelegt werden.
2. `Standardprogramm jeder Batterie` wählen, wenn Kapazität, C-Rate oder Ladeart je
   Batterie unterschiedlich sind.
3. Alternativ ein gemeinsames Automatikprogramm wählen und die Kapazität je Slot
   eintragen.
4. Bei einem Automatikprogramm das gemeinsame Zeitlimit kontrollieren.
5. Oder ein gemeinsames Ladeprofil wählen, das unverändert auf alle aufgeführten Slots
   übertragen wird. Es werden nur Profile angeboten, die zu allen ausgewählten
   Batterietypen passen.
6. Vorschau kontrollieren und `Programme übernehmen` wählen.
7. Danach `Alle starten` wählen.

Eine gespeicherte Batterienummer darf nur einem Slot zugeordnet sein. `Keine Batterie`
darf für mehrere Slots verwendet werden. Das Standardprogramm einer Batterie steht nur
mit Batterieakte zur Verfügung; Automatikprogramme und passende Profile funktionieren
auch ohne Aktenzuordnung. `Alle Programme` startet noch nichts.
Der anschließende Sammelstart verwendet alle belegten, noch nicht laufenden und
fehlerfreien Slots dieses Ladegeräts. Leere und bereits aktive Slots werden ausgelassen.
Weder Einzel- noch Sammelstart verlangen eine zusätzliche Texteingabe. Ist beim
Einzelstart noch kein Programm gewählt, öffnet sich automatisch die Slot-Auswahl. Beim
Sammelstart öffnet sich entsprechend die Auswahl für die noch nicht vorbereiteten Slots.

Das gewählte Startprogramm wird direkt in jeder Slot-Karte angezeigt. Unter
`Einstellungen` kann optional eine Vorauswahl für neue Programmfenster festgelegt werden.
Standardmäßig ist dort `Kein Programm vorauswählen` eingestellt. Auch eine konfigurierte
Vorauswahl wird erst nach ausdrücklichem Übernehmen an das Ladegerät gesendet.
Das Farbschema der gesamten Oberfläche kann dort außerdem auf `Systemeinstellung
verwenden`, `Hell` oder `Dunkel` gestellt werden. Die Auswahl umfasst auch Dialoge und
Diagramme und bleibt nach einem Neuladen erhalten.

Die C-Rate wird mit der Nennkapazität multipliziert. Bei 2000 mAh entsprechen 0,5 C einem
Strom von 1000 mA und 1 C einem Strom von 2000 mA. Das MC3000 erlaubt höchstens 3 A
Ladestrom und 2 A Entladestrom. Höhere berechnete Werte werden automatisch auf diese
Grenzen reduziert; die Vorschau zeigt den tatsächlich verwendeten Strom.

Das MC3000 erkennt nicht, welche physische Batterie eingelegt wurde. Beim erneuten Einlegen
muss deshalb am betreffenden Slot wieder die richtige Nummer über `Programm wählen`
ausgewählt werden. Die Nummer bleibt auch bei führenden Nullen erhalten.

### SOH und Vergleich

Nach jeder abgeschlossenen Entladephase zeigt die Batteriehistorie den Soll/Ist-Faktor:

```text
Soll/Ist = gemessene Entladekapazität / beim Lauf gespeicherte Nennkapazität * 100
```

Dieser Wert ist auch bei Refresh- und Zyklusprogrammen verfügbar. Beispielsweise ergeben
1600 mAh Ist bei 2600 mAh Soll einen Faktor von 61,5 Prozent. Der Sollwert wird beim
Start des Programmlaufs gespeichert, sodass eine spätere Änderung der Batteriestammdaten
alte Ergebnisse nicht verändert.

Der Kapazitäts-SOH wird nur aus einem abgeschlossenen Programm
`Kapazitätstest (Entladen)` berechnet:

```text
SOH = gemessene Entladekapazität / Nennkapazität * 100
```

Ein Ergebnis von 1800 mAh bei 2000 mAh Nennkapazität ergibt 90 Prozent. Der Wert ist ein
Kapazitätsvergleich und keine vollständige Sicherheits- oder Laborbewertung. Temperatur,
Entladestrom und Entladeschlussspannung müssen für aussagekräftige Vergleiche möglichst
gleich bleiben.

Der Innenwiderstand wird getrennt angezeigt, weil Kontaktwiderstand, Temperatur und
Ladezustand die Messung beeinflussen. In der Tabelle können bis zu fünf Läufe ausgewählt
und für Spannung, Strom, Kapazität, Temperatur oder Innenwiderstand übereinandergelegt
werden.

Messpunkte mit Batterienummer werden nicht nach 90 Tagen gelöscht. `CSV exportieren` in
der Batterieakte exportiert alle gespeicherten Läufe dieser Batterie. `Archivieren`
entfernt die Batterie aus der aktiven Liste. Die bisherigen Messungen bleiben danach
standardmäßig noch 30 Tage erhalten; die Batterieakte selbst bleibt im Archiv. Dort kann
sie nach Eingabe ihrer Batterienummer endgültig gelöscht werden. Diese Aktion entfernt
auch sämtliche Messwerte, Läufe und Berichte unwiderruflich und gibt die Nummer wieder
frei.

### QR-Etiketten und Zellen sortieren

`QR-Etikett` in einer Batterieakte öffnet eine druckbare Seite. Der QR-Code enthält keine
Messdaten, sondern nur den lokalen Link zur Batterieakte. Der Scan funktioniert deshalb
nur, wenn das verwendete Handy das Netz des Raspberry Pi erreichen kann.

Der aufklappbare `Zellen-Sortierer / Pack-Builder` berücksichtigt Batterien erst nach
einem abgeschlossenen Kapazitätstest:

1. Gewünschte Zellen markieren.
2. Zellen pro Gruppe und Anzahl der Gruppen eintragen.
3. Zulässige Abweichungen für Kapazität und Innenwiderstand festlegen.
4. `Passende Gruppen berechnen` wählen.
5. Warnungen und nicht verwendete Zellen prüfen.

Es werden nur Zellen derselben gespeicherten Chemie gruppiert. Die Funktion ersetzt keine
Prüfung von Bauform, Schutzbeschaltung, Temperaturverhalten oder mechanischem Zustand.

### Abschlussberichte und Meldungen

In der Batteriehistorie und unter `Aufzeichnungen` öffnet `Bericht` die Auswertung eines
Programmlaufs. Enthalten sind unter anderem Kapazität, Soll/Ist-Faktor, Energie, Laufzeit,
Spannungsbereich, Temperatur, Innenwiderstand, letzter Ladegerätestatus und erkennbare
Auffälligkeiten. `Diagramm` zeigt Spannung, Strom, Temperatur, Innenwiderstand und
Kapazität von fünf Minuten vor Programmstart bis eine Stunde nach dem Programmende.
Refresh- und Zyklusberichte markieren Laden, Pause und Entladen als transparente grüne,
orange und rote Phasenflächen. Ihre Deckkraft ist unter `Einstellungen` zwischen 15 und
25 Prozent wählbar und gilt auch für PDF-Berichte. Ein Klick neben das geöffnete
Diagramm-Popup schließt es; Klicks und Zoombewegungen im Diagramm bleiben aktiv. Das
Kapazitätsdiagramm zeichnet Soll und Ist als eigene Linien ein und zeigt den Faktor
direkt in Prozent. Durch horizontales Ziehen oder zwei Klicks wird der ausgewählte
Zeitbereich in allen zusammengehörigen Diagrammen synchron vergrößert. Doppelklick oder
`Zoom zurücksetzen` zeigt wieder den gesamten Zeitraum. `Löschen`
entfernt einen abgeschlossenen Bericht zusammen mit seinen zugehörigen Messpunkten und
der Abschlussmeldung. Ein noch laufender Programmlauf kann nicht gelöscht werden.

Der Punkt oben rechts öffnet die Meldungszentrale. `Browser-Meldungen aktivieren` erlaubt
lokale Desktop-Benachrichtigungen. Der Browser muss dafür geöffnet sein; es werden keine
Daten an einen externen Benachrichtigungsdienst übertragen.

## 8. Aufzeichnung und Export

Die Aufzeichnung beginnt automatisch, sobald ein eingerichtetes Ladegerät verbunden ist.
Für jeden Slot werden Zeitstempel, Akkutyp, Programm, Status, Laufzeit, Spannung, Strom,
Kapazität, Temperatur, Innenwiderstand und Zyklus gespeichert.

Unter `Aufzeichnungen` Gerät, Slot und Zeitraum wählen. Die Diagramme aktualisieren sich
automatisch. `CSV exportieren` lädt genau den ausgewählten Zeitraum herunter. Die
Semikolon-getrennte Datei ist UTF-8-kodiert und kann direkt in LibreOffice Calc oder Excel
importiert werden.
Messpunkte eines Programmlaufs werden auch hier als Phasenflächen dargestellt: Laden
grün, Pause orange und Entladen rot. Leerlauf bleibt neutral. Dieselbe Kennzeichnung
erscheint in den rollenden Livekurven der Slotkarten; die reine Geräte-Spannungskurve
bleibt neutral, weil das MC3000 dafür keine Statusdaten liefert.

Standardwerte:

- aktiver Lade-, Entlade- oder Refresh-Vorgang: Messpunkt alle 2 Sekunden
- inaktiver Slot: Messpunkt alle 30 Sekunden
- Aufzeichnungen ohne Batterieakte: 90 Tage
- aktive Batterieakten: unbegrenzt
- Messhistorie archivierter Batterien: 30 Tage nach der Archivierung

Diese Werte können mit einem systemd-Override geändert werden:

```bash
sudo systemctl edit mc3000-control
```

Beispiel:

```ini
[Service]
Environment=MC3000_RECORD_ACTIVE_INTERVAL=5
Environment=MC3000_RECORD_IDLE_INTERVAL=60
Environment=MC3000_RETENTION_DAYS=180
Environment=MC3000_ARCHIVED_BATTERY_RETENTION_DAYS=30
```

Danach:

```bash
sudo systemctl daemon-reload
sudo systemctl restart mc3000-control
```

Profile, Gerätenamen und Aufzeichnungen liegen gemeinsam unter
`/var/lib/mc3000-control/mc3000-control.db`. Unter `Einstellungen` kann jederzeit ein
konsistentes ZIP-Backup heruntergeladen werden. Zur Wiederherstellung dort die ZIP-Datei
auswählen und die angezeigte Bestätigung eingeben. Die Anwendung prüft das Archiv und die
SQLite-Datenbank, legt automatisch ein Rückfall-Backup unter
`/var/lib/mc3000-control/backups` an und startet den Dienst neu.

Für eine zusätzliche manuelle Offline-Sicherung zuerst den Dienst anhalten:

```bash
sudo systemctl stop mc3000-control
sudo cp -a /var/lib/mc3000-control/mc3000-control.db \
  /var/lib/mc3000-control/mc3000-control.db.backup
sudo systemctl start mc3000-control
```

Bei einer manuellen Wiederherstellung muss der Dienst ebenfalls angehalten sein.
Eigentümer der zurückkopierten Datei muss `mc3000-control:mc3000-control` bleiben.

## 9. Handy-App verwenden

Ein MC3000 kann nur eine BLE-Verbindung gleichzeitig halten. In der Weboberfläche beim
gewünschten Ladegerät den Verbindungsmanager öffnen und `Bluetooth trennen` wählen. Erst
danach die Handy-App öffnen.

Nach dem Schließen der Handy-App im Verbindungsmanager wieder `Verbinden` wählen.

## 10. Updates

Im lokalen Repository aktualisieren und erneut installieren:

```bash
git pull --ff-only
./install.sh
```

Jede Installation erzeugt ein neues Release-Verzeichnis. Das vorherige Release bleibt für
eine manuelle Rückkehr erhalten. Die SQLite-Datenbank liegt außerhalb der Releases und wird
nicht überschrieben.

## 11. Fehlersuche

Dienstprotokoll anzeigen:

```bash
journalctl -u mc3000-control -n 200 --no-pager
```

Live mitlesen:

```bash
journalctl -u mc3000-control -f
```

Bluetooth-Zustand:

```bash
bluetoothctl show
rfkill list bluetooth
```

Wenn Geräte gefunden werden, Verbindungen aber gelegentlich abbrechen:

- Abstand zwischen Pi und Ladegeräten verringern.
- USB-3.0-Kabel und ungeschirmte USB-3.0-Geräte vom Bluetooth-Adapter entfernen.
- Bei gleichzeitig aktivem 2,4-GHz-WLAN testweise Ethernet verwenden.
- Bei mehreren Ladegeräten einen separaten USB-Bluetooth-Adapter erwägen.

Nach Änderungen:

```bash
sudo systemctl restart bluetooth
sudo systemctl restart mc3000-control
```

## 12. Port ändern

Die systemd-Unit kopieren und bearbeiten:

```bash
sudo systemctl edit mc3000-control
```

Eintragen:

```ini
[Service]
Environment=MC3000_PORT=8090
```

Danach:

```bash
sudo systemctl daemon-reload
sudo systemctl restart mc3000-control
```
