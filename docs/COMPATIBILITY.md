# Compatibility

This matrix separates verified combinations from supported or expected ones. Reports
should include MC3000 hardware and firmware, Linux distribution, BlueZ version and the
Bluetooth adapter chipset. Do not publish Bluetooth addresses or serial numbers.

| Component | Version | Status |
| --- | --- | --- |
| SkyRC MC3000 | Hardware 2.2, firmware 1.25 | Verified with real devices |
| SkyRC MC3000 | Other firmware using the documented BLE GATT service | Expected; reports welcome |
| Raspberry Pi OS Lite 64-bit | Bookworm, Trixie | Supported by `install.sh` |
| Python | 3.11, 3.12, 3.13 | Tested in CI |
| BlueZ | 5.55 or newer | Supported |
| Chromium | Current version | Automated desktop and mobile browser checks |
| Firefox, Safari | Current versions | Intended; community reports welcome |
| Direct MC3000 USB connection | Any | Not supported |
| Bluetooth SPP | Any | Not supported |

The application talks directly to the MC3000 over Bluetooth Low Energy. Integrated and
USB Bluetooth LE adapters are supported by BlueZ; a USB cable between host and charger
is not. Only one BLE client can hold a charger connection at a time.
