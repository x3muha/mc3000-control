from __future__ import annotations

import io
import json
import re
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from http.client import HTTPException as HTTPClientError
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zipfile import BadZipFile, ZipFile

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

MAX_CATALOG_DOWNLOAD_BYTES = 12 * 1024 * 1024
MAX_XLSX_XML_BYTES = 32 * 1024 * 1024
CATALOG_TIMEOUT_SECONDS = 30
USER_AGENT = "OMC/1.0 (+https://github.com/x3muha/mc3000-control)"

CATALOG_SOURCES = {
    "betterbat": {
        "name": "BetterBat / Fraunhofer ISI & TUM",
        "database_url": "https://zenodo.org/records/10679242",
        "download_url": (
            "https://zenodo.org/api/records/10679242/files/"
            "StateOfTheArt_BatteryCells_ISI_TUM.xlsx/content"
        ),
        "parser": "betterbat",
    },
    "second_life_storage": {
        "name": "Second Life Storage Cell Database",
        "database_url": (
            "https://secondlifestorage.com/index.php?pages/cell-database/"
        ),
        "download_url": (
            "https://secondlifestorage.com/index.php?pages/cell-database/"
        ),
        "parser": "second_life_storage",
    },
    "lygte": {
        "name": "Lygte tested batteries",
        "database_url": "https://lygte-info.dk/info/batteryIndex.html",
        "download_url": "https://lygte-info.dk/info/batteryIndex.html",
        "parser": "lygte",
    },
}
CATALOG_SOURCE_HOSTS = frozenset(
    urlsplit(source["download_url"]).hostname
    for source in CATALOG_SOURCES.values()
)


class CatalogImportError(RuntimeError):
    pass


class _CatalogRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_catalog_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    source_key: str
    source_record_id: str
    source_name: str
    source_url: str
    title: str
    manufacturer: str = ""
    model: str = ""
    chemistry: str = ""
    battery_type_code: int | None = None
    form_factor: str = ""
    nominal_capacity_mah: int | None = None
    weight_g: float | None = None
    nominal_voltage_v: float | None = None
    min_voltage_v: float | None = None
    max_voltage_v: float | None = None
    max_charge_current_a: float | None = None
    max_discharge_current_a: float | None = None
    cycle_life: int | None = None
    manufacture_year: int | None = None
    dimensions: str = ""
    details: dict[str, str] | None = None


@dataclass(frozen=True, slots=True)
class StoredCatalogEntry:
    id: int
    values: CatalogEntry
    imported_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            **{
                field: getattr(self.values, field)
                for field in self.values.__dataclass_fields__
            },
            "details": dict(self.values.details or {}),
            "imported_at": self.imported_at,
        }


class CellCatalogStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=10000")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS cell_catalog (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_key TEXT NOT NULL,
                    source_record_id TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    manufacturer TEXT NOT NULL DEFAULT '',
                    model TEXT NOT NULL DEFAULT '',
                    chemistry TEXT NOT NULL DEFAULT '',
                    battery_type_code INTEGER,
                    form_factor TEXT NOT NULL DEFAULT '',
                    nominal_capacity_mah INTEGER,
                    weight_g REAL,
                    nominal_voltage_v REAL,
                    min_voltage_v REAL,
                    max_voltage_v REAL,
                    max_charge_current_a REAL,
                    max_discharge_current_a REAL,
                    cycle_life INTEGER,
                    manufacture_year INTEGER,
                    dimensions TEXT NOT NULL DEFAULT '',
                    details_json TEXT NOT NULL DEFAULT '{}',
                    search_text TEXT NOT NULL,
                    imported_at TEXT NOT NULL,
                    UNIQUE(source_key, source_record_id)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS cell_catalog_source_idx
                ON cell_catalog(source_key)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS cell_catalog_search_idx
                ON cell_catalog(search_text)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS cell_catalog_imports (
                    source_key TEXT PRIMARY KEY,
                    source_name TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    status TEXT NOT NULL,
                    entry_count INTEGER NOT NULL DEFAULT 0,
                    added_count INTEGER NOT NULL DEFAULT 0,
                    updated_count INTEGER NOT NULL DEFAULT 0,
                    removed_count INTEGER NOT NULL DEFAULT 0,
                    last_imported_at TEXT NOT NULL DEFAULT '',
                    last_error TEXT NOT NULL DEFAULT ''
                )
                """
            )

    def replace_source(
        self,
        source_key: str,
        entries: list[CatalogEntry],
        *,
        imported_at: str | None = None,
    ) -> dict[str, Any]:
        if source_key not in CATALOG_SOURCES:
            raise ValueError("Unbekannte Katalogquelle")
        entries = list(
            {
                entry.source_record_id: entry
                for entry in entries
                if entry.source_record_id.strip()
            }.values()
        )
        if not entries:
            raise CatalogImportError("Die Quelle enthielt keine Zelleneinträge")
        if any(entry.source_key != source_key for entry in entries):
            raise ValueError("Katalogeintrag gehört zur falschen Quelle")

        timestamp = imported_at or datetime.now(UTC).isoformat()
        source = CATALOG_SOURCES[source_key]
        with self._lock, self._connect() as connection:
            existing_ids = {
                str(row["source_record_id"])
                for row in connection.execute(
                    "SELECT source_record_id FROM cell_catalog WHERE source_key = ?",
                    (source_key,),
                ).fetchall()
            }
            incoming_ids = {entry.source_record_id for entry in entries}
            added = len(incoming_ids - existing_ids)
            updated = len(incoming_ids & existing_ids)
            removed = len(existing_ids - incoming_ids)

            connection.execute(
                "CREATE TEMP TABLE catalog_seen_ids(record_id TEXT PRIMARY KEY)"
            )
            connection.executemany(
                "INSERT INTO catalog_seen_ids(record_id) VALUES (?)",
                ((record_id,) for record_id in incoming_ids),
            )
            for entry in entries:
                details = {
                    str(key): str(value)
                    for key, value in (entry.details or {}).items()
                    if str(key).strip() and str(value).strip()
                }
                values = (
                    entry.source_key,
                    entry.source_record_id,
                    entry.source_name,
                    entry.source_url,
                    entry.title,
                    entry.manufacturer,
                    entry.model,
                    entry.chemistry,
                    entry.battery_type_code,
                    entry.form_factor,
                    entry.nominal_capacity_mah,
                    entry.weight_g,
                    entry.nominal_voltage_v,
                    entry.min_voltage_v,
                    entry.max_voltage_v,
                    entry.max_charge_current_a,
                    entry.max_discharge_current_a,
                    entry.cycle_life,
                    entry.manufacture_year,
                    entry.dimensions,
                    json.dumps(details, ensure_ascii=False, sort_keys=True),
                    _search_text(entry),
                    timestamp,
                )
                connection.execute(
                    """
                    INSERT INTO cell_catalog(
                        source_key, source_record_id, source_name, source_url,
                        title, manufacturer, model, chemistry, battery_type_code,
                        form_factor, nominal_capacity_mah, weight_g,
                        nominal_voltage_v, min_voltage_v, max_voltage_v,
                        max_charge_current_a, max_discharge_current_a,
                        cycle_life, manufacture_year, dimensions, details_json,
                        search_text, imported_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_key, source_record_id) DO UPDATE SET
                        source_name = excluded.source_name,
                        source_url = excluded.source_url,
                        title = excluded.title,
                        manufacturer = excluded.manufacturer,
                        model = excluded.model,
                        chemistry = excluded.chemistry,
                        battery_type_code = excluded.battery_type_code,
                        form_factor = excluded.form_factor,
                        nominal_capacity_mah = excluded.nominal_capacity_mah,
                        weight_g = excluded.weight_g,
                        nominal_voltage_v = excluded.nominal_voltage_v,
                        min_voltage_v = excluded.min_voltage_v,
                        max_voltage_v = excluded.max_voltage_v,
                        max_charge_current_a = excluded.max_charge_current_a,
                        max_discharge_current_a = excluded.max_discharge_current_a,
                        cycle_life = excluded.cycle_life,
                        manufacture_year = excluded.manufacture_year,
                        dimensions = excluded.dimensions,
                        details_json = excluded.details_json,
                        search_text = excluded.search_text,
                        imported_at = excluded.imported_at
                    """,
                    values,
                )
            connection.execute(
                """
                DELETE FROM cell_catalog
                WHERE source_key = ?
                  AND source_record_id NOT IN (
                      SELECT record_id FROM catalog_seen_ids
                  )
                """,
                (source_key,),
            )
            connection.execute("DROP TABLE catalog_seen_ids")
            connection.execute(
                """
                INSERT INTO cell_catalog_imports(
                    source_key, source_name, source_url, status, entry_count,
                    added_count, updated_count, removed_count,
                    last_imported_at, last_error
                )
                VALUES (?, ?, ?, 'ok', ?, ?, ?, ?, ?, '')
                ON CONFLICT(source_key) DO UPDATE SET
                    source_name = excluded.source_name,
                    source_url = excluded.source_url,
                    status = 'ok',
                    entry_count = excluded.entry_count,
                    added_count = excluded.added_count,
                    updated_count = excluded.updated_count,
                    removed_count = excluded.removed_count,
                    last_imported_at = excluded.last_imported_at,
                    last_error = ''
                """,
                (
                    source_key,
                    source["name"],
                    source["database_url"],
                    len(entries),
                    added,
                    updated,
                    removed,
                    timestamp,
                ),
            )
        return {
            "source_key": source_key,
            "source_name": source["name"],
            "source_url": source["database_url"],
            "status": "ok",
            "entry_count": len(entries),
            "added_count": added,
            "updated_count": updated,
            "removed_count": removed,
            "last_imported_at": timestamp,
            "last_error": "",
        }

    def record_import_error(self, source_key: str, message: str) -> dict[str, Any]:
        if source_key not in CATALOG_SOURCES:
            raise ValueError("Unbekannte Katalogquelle")
        source = CATALOG_SOURCES[source_key]
        clean_message = message.strip()[:500]
        with self._lock, self._connect() as connection:
            count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM cell_catalog WHERE source_key = ?",
                    (source_key,),
                ).fetchone()[0]
            )
            connection.execute(
                """
                INSERT INTO cell_catalog_imports(
                    source_key, source_name, source_url, status, entry_count,
                    last_error
                )
                VALUES (?, ?, ?, 'error', ?, ?)
                ON CONFLICT(source_key) DO UPDATE SET
                    source_name = excluded.source_name,
                    source_url = excluded.source_url,
                    status = 'error',
                    entry_count = excluded.entry_count,
                    last_error = excluded.last_error
                """,
                (
                    source_key,
                    source["name"],
                    source["database_url"],
                    count,
                    clean_message,
                ),
            )
        return {
            "source_key": source_key,
            "source_name": source["name"],
            "source_url": source["database_url"],
            "status": "error",
            "entry_count": count,
            "added_count": 0,
            "updated_count": 0,
            "removed_count": 0,
            "last_imported_at": "",
            "last_error": clean_message,
        }

    def source_statuses(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as connection:
            rows = {
                str(row["source_key"]): row
                for row in connection.execute(
                    "SELECT * FROM cell_catalog_imports"
                ).fetchall()
            }
        result = []
        for key, source in CATALOG_SOURCES.items():
            row = rows.get(key)
            result.append(
                {
                    "source_key": key,
                    "source_name": source["name"],
                    "source_url": source["database_url"],
                    "status": str(row["status"]) if row else "never",
                    "entry_count": int(row["entry_count"]) if row else 0,
                    "added_count": int(row["added_count"]) if row else 0,
                    "updated_count": int(row["updated_count"]) if row else 0,
                    "removed_count": int(row["removed_count"]) if row else 0,
                    "last_imported_at": str(row["last_imported_at"]) if row else "",
                    "last_error": str(row["last_error"]) if row else "",
                }
            )
        return result

    def search(self, query: str, *, limit: int = 20) -> list[StoredCatalogEntry]:
        tokens = [_normalize_search(token) for token in query.split()]
        tokens = [token for token in tokens if token]
        if not tokens:
            return []
        clean_limit = max(1, min(int(limit), 100))
        where = " AND ".join("search_text LIKE ?" for _ in tokens)
        parameters: list[Any] = [f"%{token}%" for token in tokens]
        parameters.append(clean_limit)
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM cell_catalog
                WHERE {where}
                ORDER BY
                    CASE WHEN search_text LIKE ? THEN 0 ELSE 1 END,
                    manufacturer COLLATE NOCASE,
                    model COLLATE NOCASE,
                    source_name COLLATE NOCASE
                LIMIT ?
                """,
                [*parameters[:-1], f"{''.join(tokens)}%", parameters[-1]],
            ).fetchall()
        return [_catalog_entry_from_row(row) for row in rows]


FetchFunction = Callable[[str], bytes]


def import_catalog_sources(
    store: CellCatalogStore,
    source_keys: list[str] | None = None,
    *,
    fetcher: FetchFunction | None = None,
) -> dict[str, Any]:
    selected = source_keys or list(CATALOG_SOURCES)
    if not selected or len(selected) != len(set(selected)):
        raise ValueError("Mindestens eine eindeutige Katalogquelle auswählen")
    unknown = [key for key in selected if key not in CATALOG_SOURCES]
    if unknown:
        raise ValueError(f"Unbekannte Katalogquelle: {unknown[0]}")

    fetch = fetcher or fetch_catalog_url
    results = []
    for source_key in selected:
        source = CATALOG_SOURCES[source_key]
        try:
            payload = fetch(source["download_url"])
            parser = source["parser"]
            if parser == "betterbat":
                entries = parse_betterbat(payload)
            elif parser == "second_life_storage":
                entries = parse_second_life_storage(payload)
            else:
                entries = parse_lygte(payload)
            results.append(store.replace_source(source_key, entries))
        except (OSError, RuntimeError, sqlite3.Error, ValueError) as exc:
            results.append(store.record_import_error(source_key, str(exc)))
    return {
        "ok": all(result["status"] == "ok" for result in results),
        "results": results,
        "total_entries": sum(
            status["entry_count"] for status in store.source_statuses()
        ),
    }


def fetch_catalog_url(url: str) -> bytes:
    _validate_catalog_url(url)
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    opener = build_opener(_CatalogRedirectHandler())
    try:
        with opener.open(request, timeout=CATALOG_TIMEOUT_SECONDS) as response:
            _validate_catalog_url(response.geturl())
            declared_size = response.headers.get("Content-Length")
            if declared_size and int(declared_size) > MAX_CATALOG_DOWNLOAD_BYTES:
                raise CatalogImportError("Katalogdatei ist größer als erlaubt")
            payload = response.read(MAX_CATALOG_DOWNLOAD_BYTES + 1)
    except CatalogImportError:
        raise
    except (HTTPClientError, OSError, ValueError) as exc:
        raise CatalogImportError(f"Quelle konnte nicht geladen werden: {exc}") from exc
    if len(payload) > MAX_CATALOG_DOWNLOAD_BYTES:
        raise CatalogImportError("Katalogdatei ist größer als erlaubt")
    return payload


def _validate_catalog_url(url: str) -> None:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise CatalogImportError("Katalogquelle hat eine ungültige URL") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname not in CATALOG_SOURCE_HOSTS
        or port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise CatalogImportError("Katalogquelle ist nicht freigegeben")


def parse_betterbat(payload: bytes) -> list[CatalogEntry]:
    rows = _xlsx_rows(payload)
    if not rows or "Product_Number" not in rows[0]:
        raise CatalogImportError("BetterBat-Tabelle hat ein unbekanntes Format")
    source = CATALOG_SOURCES["betterbat"]
    entries = []
    for row in rows:
        record_id = _useful(row.get("Index"))
        model = _useful(row.get("Product_Number"))
        manufacturer = _useful(row.get("Company"))
        if not record_id or not model:
            continue
        chemistry = _useful(row.get("Chemistry_Detail")) or _useful(
            row.get("Chemistry")
        )
        capacity_ah = _number(row.get("Capacity_Ah"))
        capacity_mah = round(capacity_ah * 1000) if capacity_ah is not None else None
        year = _integer(row.get("Year"))
        if year is not None and not 1900 <= year <= 2100:
            year = None
        entries.append(
            CatalogEntry(
                source_key="betterbat",
                source_record_id=record_id,
                source_name=source["name"],
                source_url=source["database_url"],
                title=f"{manufacturer} {model}".strip(),
                manufacturer=manufacturer,
                model=model,
                chemistry=chemistry,
                battery_type_code=_battery_type_code(chemistry),
                form_factor=_betterbat_form_factor(row, model),
                nominal_capacity_mah=capacity_mah,
                weight_g=_number(row.get("Weight_gr")),
                nominal_voltage_v=_number(row.get("NomVoltage_Volt")),
                min_voltage_v=_number(row.get("CutOff_Voltage_Volt")),
                max_voltage_v=_number(row.get("OCV_Volt")),
                max_charge_current_a=_number(row.get("Charge_MaxConstant_A")),
                max_discharge_current_a=_number(row.get("Discharge_MaxConstant_A")),
                cycle_life=_integer(row.get("CycleLife")),
                manufacture_year=year,
                dimensions=_betterbat_dimensions(row),
                details={key: value for key, value in row.items() if value},
            )
        )
    if not entries:
        raise CatalogImportError("BetterBat-Tabelle enthielt keine Zelleneinträge")
    return entries


def parse_second_life_storage(payload: bytes) -> list[CatalogEntry]:
    source = CATALOG_SOURCES["second_life_storage"]
    parser = _TableParser()
    parser.feed(_decode_html(payload))
    entries = []
    for row in parser.rows:
        if len(row) < 7:
            continue
        link = next(
            (href for href in row[6].links if "threads/" in href),
            "",
        )
        manufacturer = row[0].text.strip()
        model = row[1].text.strip()
        form_factor = row[2].text.strip()
        if not link or not manufacturer or not model:
            continue
        source_url = urljoin(source["database_url"], link)
        details = {
            "Wrap color": row[3].text.strip(),
            "Ring color": row[4].text.strip(),
        }
        if row[5].images:
            details["Image URL"] = urljoin(source["database_url"], row[5].images[0])
        entries.append(
            CatalogEntry(
                source_key="second_life_storage",
                source_record_id=source_url,
                source_name=source["name"],
                source_url=source_url,
                title=f"{manufacturer} {model}",
                manufacturer=manufacturer,
                model=model,
                form_factor=form_factor,
                details=details,
            )
        )
    if not entries:
        raise CatalogImportError(
            "Second-Life-Storage-Seite enthielt keine Zelleneinträge"
        )
    return entries


def parse_lygte(payload: bytes) -> list[CatalogEntry]:
    source = CATALOG_SOURCES["lygte"]
    parser = _TableParser()
    parser.feed(_decode_html(payload))
    headers = _lygte_headers(parser.rows)
    entries = []
    for row in parser.rows:
        if len(row) < 10:
            continue
        link = next(
            (href for href in row[0].links if "/review/batteries" in href),
            "",
        )
        title = row[0].text.strip()
        if not link or not title:
            continue
        values = [cell.text.strip() for cell in row]
        details = {
            header: value
            for header, value in zip(headers, values, strict=False)
            if header and value
        }
        manufacturer, model = _lygte_identity(title)
        chemistry = values[1]
        form_factor = values[2]
        diameter = _number(values[7])
        length = _number(values[8])
        dimensions = (
            f"Ø {_compact_number(diameter)} × {_compact_number(length)} mm"
            if diameter is not None and length is not None
            else ""
        )
        source_url = urljoin(source["database_url"], link)
        entries.append(
            CatalogEntry(
                source_key="lygte",
                source_record_id=source_url,
                source_name=source["name"],
                source_url=source_url,
                title=title,
                manufacturer=manufacturer,
                model=model,
                chemistry=chemistry,
                battery_type_code=_battery_type_code(chemistry),
                form_factor=form_factor,
                nominal_capacity_mah=_integer(values[6]),
                dimensions=dimensions,
                details=details,
            )
        )
    if not entries:
        raise CatalogImportError("Lygte-Tabelle enthielt keine Zelleneinträge")
    return entries


@dataclass(slots=True)
class _HtmlCell:
    text: str
    links: list[str]
    images: list[str]


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[_HtmlCell]] = []
        self._row: list[_HtmlCell] | None = None
        self._text: list[str] | None = None
        self._links: list[str] = []
        self._images: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = dict(attrs)
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._text = []
            self._links = []
            self._images = []
        elif self._text is not None and tag == "a" and attributes.get("href"):
            self._links.append(str(attributes["href"]))
        elif self._text is not None and tag == "img" and attributes.get("src"):
            self._images.append(str(attributes["src"]))
        elif self._text is not None and tag in {"br", "p", "div"}:
            self._text.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._row is not None and self._text is not None:
            text = " ".join("".join(self._text).split())
            self._row.append(_HtmlCell(text, self._links, self._images))
            self._text = None
            self._links = []
            self._images = []
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._text is not None:
            self._text.append(data)


def _xlsx_rows(payload: bytes) -> list[dict[str, str]]:
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    try:
        with ZipFile(io.BytesIO(payload)) as archive:
            shared = []
            if "xl/sharedStrings.xml" in archive.namelist():
                shared_root = ElementTree.fromstring(
                    _read_xlsx_member(archive, "xl/sharedStrings.xml")
                )
                shared = [
                    "".join(node.itertext())
                    for node in shared_root.findall(f"{namespace}si")
                ]
            sheet = ElementTree.fromstring(
                _read_xlsx_member(archive, "xl/worksheets/sheet1.xml")
            )
    except (BadZipFile, KeyError, ElementTree.ParseError, DefusedXmlException) as exc:
        raise CatalogImportError("XLSX-Datei konnte nicht gelesen werden") from exc

    raw_rows: list[dict[str, str]] = []
    for row in sheet.findall(f".//{namespace}row"):
        values: dict[str, str] = {}
        for cell in row.findall(f"{namespace}c"):
            reference = cell.get("r", "")
            column_match = re.match(r"[A-Z]+", reference)
            if column_match is None:
                continue
            raw = cell.findtext(f"{namespace}v") or ""
            if cell.get("t") == "s" and raw:
                try:
                    raw = shared[int(raw)]
                except (IndexError, ValueError):
                    raw = ""
            elif cell.get("t") == "inlineStr":
                inline = cell.find(f"{namespace}is")
                raw = "" if inline is None else "".join(inline.itertext())
            values[column_match.group()] = " ".join(raw.split())
        if values:
            raw_rows.append(values)
    if not raw_rows:
        return []
    headers = raw_rows[0]
    return [
        {header: row.get(column, "") for column, header in headers.items() if header}
        for row in raw_rows[1:]
    ]


def _read_xlsx_member(archive: ZipFile, name: str) -> bytes:
    member = archive.getinfo(name)
    if member.file_size > MAX_XLSX_XML_BYTES:
        raise CatalogImportError("XLSX-Inhalt ist größer als erlaubt")
    return archive.read(member)


def _catalog_entry_from_row(row: sqlite3.Row) -> StoredCatalogEntry:
    try:
        details = json.loads(str(row["details_json"]))
    except (TypeError, ValueError):
        details = {}
    if not isinstance(details, dict):
        details = {}
    return StoredCatalogEntry(
        id=int(row["id"]),
        values=CatalogEntry(
            source_key=str(row["source_key"]),
            source_record_id=str(row["source_record_id"]),
            source_name=str(row["source_name"]),
            source_url=str(row["source_url"]),
            title=str(row["title"]),
            manufacturer=str(row["manufacturer"]),
            model=str(row["model"]),
            chemistry=str(row["chemistry"]),
            battery_type_code=(
                int(row["battery_type_code"])
                if row["battery_type_code"] is not None
                else None
            ),
            form_factor=str(row["form_factor"]),
            nominal_capacity_mah=(
                int(row["nominal_capacity_mah"])
                if row["nominal_capacity_mah"] is not None
                else None
            ),
            weight_g=float(row["weight_g"]) if row["weight_g"] is not None else None,
            nominal_voltage_v=(
                float(row["nominal_voltage_v"])
                if row["nominal_voltage_v"] is not None
                else None
            ),
            min_voltage_v=(
                float(row["min_voltage_v"])
                if row["min_voltage_v"] is not None
                else None
            ),
            max_voltage_v=(
                float(row["max_voltage_v"])
                if row["max_voltage_v"] is not None
                else None
            ),
            max_charge_current_a=(
                float(row["max_charge_current_a"])
                if row["max_charge_current_a"] is not None
                else None
            ),
            max_discharge_current_a=(
                float(row["max_discharge_current_a"])
                if row["max_discharge_current_a"] is not None
                else None
            ),
            cycle_life=int(row["cycle_life"])
            if row["cycle_life"] is not None
            else None,
            manufacture_year=(
                int(row["manufacture_year"])
                if row["manufacture_year"] is not None
                else None
            ),
            dimensions=str(row["dimensions"]),
            details={str(key): str(value) for key, value in details.items()},
        ),
        imported_at=str(row["imported_at"]),
    )


def _search_text(entry: CatalogEntry) -> str:
    return _normalize_search(
        f"{entry.manufacturer} {entry.model} {entry.title} "
        f"{entry.chemistry} {entry.form_factor} {entry.source_name}"
    )


def _normalize_search(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _decode_html(payload: bytes) -> str:
    for encoding in ("utf-8", "windows-1252", "latin-1"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="replace")


def _number(value: str | None) -> float | None:
    useful = _useful(value)
    if not useful:
        return None
    try:
        return float(useful.replace(",", "."))
    except ValueError:
        return None


def _integer(value: str | None) -> int | None:
    number = _number(value)
    return round(number) if number is not None else None


def _useful(value: str | None) -> str:
    clean = " ".join(str(value or "").split())
    if clean.casefold() in {
        "",
        "-",
        "x",
        "(x)",
        "na",
        "n/a",
        "not defined",
        "not applicable",
    }:
        return ""
    return clean


def _battery_type_code(chemistry: str) -> int | None:
    normalized = re.sub(r"[^a-z0-9]", "", chemistry.casefold())
    if normalized in {"lifepo4", "lfp"}:
        return 1
    if normalized in {"liion", "nmc", "nca", "lco", "lmo", "nirich"}:
        return 0
    return None


def _betterbat_form_factor(row: dict[str, str], model: str) -> str:
    model_match = re.search(r"(?<!\d)(\d{5})(?!\d)", model)
    if model_match:
        return model_match.group(1)
    cell_format = _useful(row.get("Cell_Format"))
    if cell_format.casefold() != "cylindrical":
        return cell_format
    diameter = _number(row.get("Diameter_mm"))
    length = _number(row.get("Thickness_Height_mm"))
    if diameter is None or length is None:
        return cell_format
    return f"{round(diameter):02d}{round(length):03d}"


def _betterbat_dimensions(row: dict[str, str]) -> str:
    diameter = _number(row.get("Diameter_mm"))
    height = _number(row.get("Thickness_Height_mm"))
    if diameter is not None and height is not None:
        return f"Ø {_compact_number(diameter)} × {_compact_number(height)} mm"
    values = [
        _number(row.get("Length_mm")),
        _number(row.get("Width_mm")),
        height,
    ]
    if all(value is not None for value in values):
        return " × ".join(_compact_number(value) for value in values) + " mm"
    return ""


def _compact_number(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _lygte_headers(rows: list[list[_HtmlCell]]) -> list[str]:
    for row in rows:
        values = [cell.text.strip() for cell in row]
        if values and values[0] == "Battery Name" and "Rated mAh" in values:
            return values
    return [
        "Battery Name",
        "Type",
        "Size",
        "Year",
        "Top",
        "Prot.",
        "Rated mAh",
        "Diameter",
        "Length",
        "X length",
    ]


def _lygte_identity(title: str) -> tuple[str, str]:
    parts = title.split(maxsplit=1)
    manufacturer = parts[0] if parts else ""
    model = parts[1] if len(parts) > 1 else title
    model = re.split(r"\s+\d+(?:[.,]\d+)?\s*mAh\b", model, maxsplit=1)[0]
    return manufacturer.strip(), model.strip()
