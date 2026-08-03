# Third-party notices / Hinweise zu Drittanbieterkomponenten

This file is generated from a clean installation of the runtime dependencies.
Do not edit the package table manually. Open MC3000 Control itself is licensed
under the MIT license in `LICENSE`; the packages below retain their respective
upstream licenses and copyright notices.

Diese Datei wird aus einer sauberen Installation der Laufzeitabhängigkeiten
erzeugt. Die Pakettabelle darf nicht manuell bearbeitet werden. Open MC3000
Control selbst steht unter der MIT-Lizenz in `LICENSE`; für die folgenden Pakete
gelten weiterhin deren jeweilige Upstream-Lizenzen und Copyright-Hinweise.

OMC does not vendor these packages in its source tree or wheel. Installation
tools resolve and install them separately. The authoritative license texts are
included in the respective package distributions.

OMC bettet diese Pakete weder in den Quellbaum noch in das Wheel ein. Die
Installationswerkzeuge lösen sie separat auf und installieren sie. Die
maßgeblichen Lizenztexte sind in den jeweiligen Paketdistributionen enthalten.

## Runtime packages / Laufzeitpakete

| Package / Paket | License / Lizenz | Package page / Paketseite |
| --- | --- | --- |
| annotated-doc | MIT | [PyPI](https://pypi.org/project/annotated-doc/) |
| annotated-types | MIT | [PyPI](https://pypi.org/project/annotated-types/) |
| anyio | MIT | [PyPI](https://pypi.org/project/anyio/) |
| bleak | MIT | [PyPI](https://pypi.org/project/bleak/) |
| charset-normalizer | MIT | [PyPI](https://pypi.org/project/charset-normalizer/) |
| click | BSD-3-Clause | [PyPI](https://pypi.org/project/click/) |
| dbus-fast | MIT License | [PyPI](https://pypi.org/project/dbus-fast/) |
| defusedxml | Python Software Foundation License | [PyPI](https://pypi.org/project/defusedxml/) |
| fastapi | MIT | [PyPI](https://pypi.org/project/fastapi/) |
| h11 | MIT License | [PyPI](https://pypi.org/project/h11/) |
| httptools | MIT | [PyPI](https://pypi.org/project/httptools/) |
| idna | BSD-3-Clause | [PyPI](https://pypi.org/project/idna/) |
| pillow | MIT-CMU | [PyPI](https://pypi.org/project/pillow/) |
| pydantic | MIT | [PyPI](https://pypi.org/project/pydantic/) |
| pydantic_core | MIT | [PyPI](https://pypi.org/project/pydantic_core/) |
| python-dotenv | BSD-3-Clause | [PyPI](https://pypi.org/project/python-dotenv/) |
| PyYAML | MIT License | [PyPI](https://pypi.org/project/PyYAML/) |
| reportlab | BSD License | [PyPI](https://pypi.org/project/reportlab/) |
| segno | BSD License | [PyPI](https://pypi.org/project/segno/) |
| starlette | BSD-3-Clause | [PyPI](https://pypi.org/project/starlette/) |
| typing-inspection | MIT | [PyPI](https://pypi.org/project/typing-inspection/) |
| typing_extensions | PSF-2.0 | [PyPI](https://pypi.org/project/typing_extensions/) |
| uvicorn | BSD-3-Clause | [PyPI](https://pypi.org/project/uvicorn/) |
| uvloop | Apache Software License; MIT License | [PyPI](https://pypi.org/project/uvloop/) |
| watchfiles | MIT License | [PyPI](https://pypi.org/project/watchfiles/) |
| websockets | BSD-3-Clause | [PyPI](https://pypi.org/project/websockets/) |

## Regeneration / Aktualisierung

```bash
python -m pip install -e '.[audit]'
python scripts/third_party_notices.py --write
```

CI runs the same resolver with `--check`. It fails if this file is stale or
if a resolved package declares a license outside the allowlist in
`pyproject.toml`.

CI führt dieselbe Auflösung mit `--check` aus. Die Prüfung schlägt fehl, wenn
diese Datei veraltet ist oder ein aufgelöstes Paket eine Lizenz außerhalb
der Allowlist in `pyproject.toml` angibt.

Imported cell-catalog data is not distributed with OMC and is not covered by
the OMC MIT license. The terms of each selected data source apply separately.

Importierte Zellkatalogdaten werden nicht mit OMC ausgeliefert und fallen
nicht unter die OMC-MIT-Lizenz. Die Bedingungen jeder ausgewählten Datenquelle
gelten davon unabhängig.
