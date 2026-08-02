# MC3000 BLE-Protokoll

## GATT

- Gerätenamen: `Charger`, `SimpleBLEPeripheral`, `HitecCharger`
- Service: `0000FFE0-0000-1000-8000-00805F9B34FB`
- Schreib-, Lese- und Notify-Charakteristik:
  `0000FFE1-0000-1000-8000-00805F9B34FB`
- Kopplung ist nicht erforderlich.
- Das Ladegerät sendet keine regelmäßigen Daten von selbst. Statuswerte müssen abgefragt
  werden.

## Normales Paket

Ein normales Paket ist 20 Byte lang:

| Byte | Bedeutung |
| --- | --- |
| 0 | Startwert `0x0F` |
| 1 | Befehl |
| 2-18 | Nutzdaten |
| 19 | Summe der Bytes 0-18 modulo 256 |

## Verwendete Befehle

| Befehl | Wert | Nutzdaten |
| --- | ---: | --- |
| Start | `0x05` | Slot-Bitmaske |
| Profil setzen | `0x11` | 40 Byte in zwei 20-Byte-Blöcken |
| Slotstatus | `0x55` | Slotnummer 0 bis 3 |
| Spannungskurve | `0x56` | Slotnummer 0 bis 3 |
| Version | `0x57` | optional Geräteadresse |
| Grunddaten | `0x61` | keine |
| Grunddaten setzen | `0x63` | Geräteeinstellungen |
| Stop | `0xFE` | Slot-Bitmaske |

Die Slot-Bitmaske verwendet `1`, `2`, `4` und `8` für Slot 1 bis 4. Mehrere Bits dürfen
gemeinsam gesetzt werden.

## Ladeprofile

Die Profilbibliothek der Hersteller-App wird lokal in deren SQLite-Datenbank gespeichert.
Das Ladegerät erhält beim Anwenden einen 40-Byte-Datensatz. Es gibt keinen bekannten
BLE-Befehl, mit dem dieser Datensatz vollständig zurückgelesen werden kann.

| Byte | Bedeutung |
| --- | --- |
| 0 | Startwert `0x0F` |
| 1 | Befehl `0x11` |
| 2 | Slot-Bitmaske |
| 3 | Akkutyp |
| 4 | Programm |
| 5-6 | Kapazität in Milliamperestunden |
| 7-8 | Ladestrom in Milliampere |
| 9-10 | Entladestrom in Milliampere |
| 11-12 | Ladeschlussspannung in Millivolt |
| 13-14 | Entladeschlussspannung in Millivolt |
| 15-16 | Lade-Endstrom in Milliampere |
| 17-18 | Entlade-Endstrom in Milliampere |
| 19 | Pause nach dem Laden in Minuten |
| 20 | Zykluszahl |
| 21 | Zyklusmodus |
| 22 | Delta-Peak in Millivolt |
| 23 | Erhaltungsladestrom in Schritten zu 10 Milliampere |
| 24-25 | Erhaltungsspannung in Millivolt |
| 26 | Temperaturgrenze in Grad Celsius |
| 27-28 | Zeitgrenze in Minuten |
| 29 | Pause nach dem Entladen in Minuten |
| 30-38 | reserviert |
| 39 | Summe der Bytes 0-38 modulo 256 |

Vor dem Profil wird ein Stop-Paket für dieselbe Slot-Bitmaske gesendet. Nach 500 ms folgen
die Bytes 0-19 und nach weiteren 50 ms die Bytes 20-39. Diese drei Schreibvorgänge müssen
ohne GATT-Schreibbestätigung erfolgen. Das Ladegerät quittiert das Profil anschließend mit
dem Befehl `0x11`.

Open MC3000 Control sendet nach dieser Quittung absichtlich keinen Start-Befehl. Das Profil ist
damit eingestellt, der Start bleibt aber eine getrennte Bedienhandlung.

## Slotstatus

Die Antwort auf `0x55` enthält:

| Byte | Bedeutung |
| --- | --- |
| 2 | Slot 0 bis 3 |
| 3 | Akkutyp |
| 4 | Programm |
| 5 | Zykluszahl |
| 6 | Status |
| 7-8 | Laufzeit in Sekunden |
| 9-10 | Spannung in Millivolt |
| 11-12 | Strom in Milliampere |
| 13-14 | Kapazität in Milliamperestunden |
| 15 | Temperatur |
| 16-17 | Innenwiderstand in Milliohm |
| 18 | LED-Bitmaske |

## Spannungskurve

Die Antwort auf `0x56` ist 245 Byte lang und wird über mehrere Notifications übertragen.
Byte 3-4 enthalten das Zeitintervall. Ab Byte 5 folgen bis zu 120 Spannungswerte in
Millivolt.

## Mehrere Ladegeräte

Jedes Ladegerät benötigt:

- eine eigene BLE-Verbindung
- eine eigene Notification-Queue
- genau einen gleichzeitig laufenden Befehl
- eine eigene Wiederverbindungslogik

Vor dem Verbindungsaufbau wird einmal zentral gescannt. Die dabei erhaltenen BLE-Objekte
werden direkt an die jeweiligen Clients übergeben. So löst ein Verbindungsaufbau keinen
zusätzlichen Scan aus.
