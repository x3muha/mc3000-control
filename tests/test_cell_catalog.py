from __future__ import annotations

import io
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from httpx import ASGITransport, AsyncClient

from mc3000_control import cell_catalog
from mc3000_control.app import create_app
from mc3000_control.cell_catalog import (
    CATALOG_SOURCES,
    CatalogEntry,
    CatalogImportError,
    CellCatalogStore,
    fetch_catalog_url,
    import_catalog_sources,
    parse_betterbat,
    parse_lygte,
    parse_second_life_storage,
)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://zenodo.org/records/10679242",
        "https://example.com/catalog.xlsx",
        "https://zenodo.org:444/records/10679242",
    ],
)
def test_catalog_download_rejects_unapproved_urls(url: str) -> None:
    with pytest.raises(CatalogImportError, match="nicht freigegeben"):
        fetch_catalog_url(url)


def test_betterbat_xlsx_rejects_xml_entities() -> None:
    sheet = b"""<?xml version="1.0"?>
    <!DOCTYPE worksheet [<!ENTITY payload "not allowed">]>
    <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
      <sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>&payload;</t></is></c>
      </row></sheetData>
    </worksheet>"""
    output = io.BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("xl/worksheets/sheet1.xml", sheet)

    with pytest.raises(CatalogImportError, match="XLSX-Datei"):
        parse_betterbat(output.getvalue())


def test_betterbat_xlsx_rejects_oversized_xml(monkeypatch) -> None:
    monkeypatch.setattr(cell_catalog, "MAX_XLSX_XML_BYTES", 32)

    with pytest.raises(CatalogImportError, match="größer als erlaubt"):
        parse_betterbat(_xlsx(["Product_Number"], ["INR21700-40T"]))


def test_betterbat_xlsx_is_normalized_and_preserves_source_fields() -> None:
    payload = _xlsx(
        [
            "Index",
            "Company",
            "Chemistry_Detail",
            "Cell_Format",
            "Product_Number",
            "Capacity_Ah",
            "Weight_gr",
            "NomVoltage_Volt",
            "CutOff_Voltage_Volt",
            "OCV_Volt",
            "Charge_MaxConstant_A",
            "Discharge_MaxConstant_A",
            "CycleLife",
            "Diameter_mm",
            "Thickness_Height_mm",
            "Year",
        ],
        [
            "ISI-TEST",
            "Samsung SDI",
            "NMC",
            "Cylindrical",
            "INR21700-40T",
            "4",
            "70",
            "3.6",
            "2.5",
            "4.2",
            "6",
            "35",
            "500",
            "21.2",
            "70.3",
            "2020",
        ],
    )

    entry = parse_betterbat(payload)[0]

    assert entry.manufacturer == "Samsung SDI"
    assert entry.model == "INR21700-40T"
    assert entry.battery_type_code == 0
    assert entry.form_factor == "21700"
    assert entry.nominal_capacity_mah == 4000
    assert entry.weight_g == 70
    assert entry.nominal_voltage_v == 3.6
    assert entry.min_voltage_v == 2.5
    assert entry.max_voltage_v == 4.2
    assert entry.details["CycleLife"] == "500"


def test_second_life_storage_listing_is_imported_with_record_links() -> None:
    payload = b"""
    <table><tr><th>Brand</th><th>Model</th><th>Formfactor</th><th>Wrap</th>
    <th>Ring</th><th>Image</th><th>Cell Data</th></tr>
    <tr><td>Samsung</td><td>INR18650-30Q</td><td>18650</td>
    <td>Pink</td><td>White</td><td><img src='/cell.jpg'></td>
    <td><a href='index.php?threads/celldata.30/'>View Specifications</a></td>
    </tr></table>
    """

    entry = parse_second_life_storage(payload)[0]

    assert entry.manufacturer == "Samsung"
    assert entry.model == "INR18650-30Q"
    assert entry.form_factor == "18650"
    assert entry.source_url.endswith("index.php?threads/celldata.30/")
    assert entry.details == {
        "Wrap color": "Pink",
        "Ring color": "White",
        "Image URL": "https://secondlifestorage.com/cell.jpg",
    }


def test_lygte_test_table_is_normalized_and_keeps_measurements() -> None:
    payload = b"""
    <table><tr><th>Battery Name</th><th>Type</th><th>Size</th><th>Year</th>
    <th>Top</th><th>Prot.</th><th>Rated mAh</th><th>Diameter</th>
    <th>Length</th><th>X length</th><th>mAh 3.0V 3A</th></tr>
    <tr><td><a href='/review/batteries2012/Samsung-30Q.html'>
    Samsung INR18650-30Q 3000mAh (Pink)</a></td><td>LiIon</td><td>18650</td>
    <td>1-2020</td><td>flat</td><td>na</td><td>3000</td><td>18.3</td>
    <td>65</td><td>0</td><td>2875</td></tr></table>
    """

    entry = parse_lygte(payload)[0]

    assert entry.manufacturer == "Samsung"
    assert entry.model == "INR18650-30Q"
    assert entry.battery_type_code == 0
    assert entry.nominal_capacity_mah == 3000
    assert entry.dimensions == "Ø 18.3 × 65 mm"
    assert entry.details["mAh 3.0V 3A"] == "2875"


def test_catalog_refresh_search_and_failed_refresh_keep_last_data(tmp_path) -> None:
    store = CellCatalogStore(tmp_path / "mc3000.db")
    first = _entry("record-1", model="INR18650-30Q")
    second = _entry("record-2", model="INR18650-25R")

    initial = store.replace_source("lygte", [first, second, second])
    results = store.search("samsung inr 30q")
    failed = store.record_import_error("lygte", "Netzwerk nicht erreichbar")
    refreshed = store.replace_source(
        "lygte",
        [_entry("record-1", model="INR18650-30Q", capacity=2950)],
    )

    assert initial["entry_count"] == 2
    assert len(results) == 1
    assert results[0].values.model == "INR18650-30Q"
    assert failed["entry_count"] == 2
    assert refreshed["updated_count"] == 1
    assert refreshed["removed_count"] == 1
    assert store.search("25r") == []
    assert store.search("30q")[0].values.nominal_capacity_mah == 2950


def test_manual_import_can_select_sources_and_reports_partial_failures(
    tmp_path,
) -> None:
    store = CellCatalogStore(tmp_path / "mc3000.db")
    betterbat = _xlsx(
        ["Index", "Company", "Product_Number", "Capacity_Ah"],
        ["ONE", "Samsung", "INR21700-40T", "4"],
    )

    def fetcher(url: str) -> bytes:
        if url == CATALOG_SOURCES["betterbat"]["download_url"]:
            return betterbat
        raise RuntimeError("absichtlicher Testfehler")

    result = import_catalog_sources(
        store,
        ["betterbat", "lygte"],
        fetcher=fetcher,
    )

    assert result["ok"] is False
    assert result["results"][0]["status"] == "ok"
    assert result["results"][1]["status"] == "error"
    assert store.search("Samsung 40T")[0].values.nominal_capacity_mah == 4000


async def test_catalog_api_exposes_status_search_and_manual_import(
    tmp_path,
    monkeypatch,
) -> None:
    app = create_app(data_dir=tmp_path, scan_timeout=0.01)
    async with app.router.lifespan_context(app):
        app.state.cell_catalog.replace_source(
            "lygte",
            [_entry("api-record", model="INR18650-30Q")],
        )

        def fake_import(store, sources):
            assert store is app.state.cell_catalog
            assert sources == ["lygte"]
            return {"ok": True, "results": [], "total_entries": 1}

        monkeypatch.setattr(
            "mc3000_control.app.import_catalog_sources",
            fake_import,
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            statuses = await client.get("/api/cell-catalog/sources")
            search = await client.get(
                "/api/cell-catalog/search",
                params={"q": "samsung inr"},
            )
            imported = await client.post(
                "/api/cell-catalog/import",
                json={"sources": ["lygte"]},
            )

    assert statuses.status_code == 200
    assert statuses.json()["total_entries"] == 1
    assert search.status_code == 200
    assert search.json()["entries"][0]["model"] == "INR18650-30Q"
    assert imported.status_code == 200
    assert imported.json()["ok"] is True


def _entry(
    record_id: str,
    *,
    model: str,
    capacity: int = 3000,
) -> CatalogEntry:
    source = CATALOG_SOURCES["lygte"]
    return CatalogEntry(
        source_key="lygte",
        source_record_id=record_id,
        source_name=source["name"],
        source_url=f"https://example.com/{record_id}",
        title=f"Samsung {model}",
        manufacturer="Samsung",
        model=model,
        chemistry="LiIon",
        battery_type_code=0,
        form_factor="18650",
        nominal_capacity_mah=capacity,
        details={"Rated mAh": str(capacity)},
    )


def _xlsx(headers: list[str], values: list[str]) -> bytes:
    def row(number: int, items: list[str]) -> str:
        cells = "".join(
            f'<c r="{_column(index)}{number}" t="inlineStr"><is><t>{value}</t></is></c>'
            for index, value in enumerate(items, start=1)
        )
        return f'<row r="{number}">{cells}</row>'

    sheet = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{row(1, headers)}{row(2, values)}</sheetData>"
        "</worksheet>"
    )
    output = io.BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return output.getvalue()


def _column(number: int) -> str:
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result
