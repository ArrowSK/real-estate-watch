from app.services.ksh_local import BUDAPEST_DISTRICTS, parse_ksh_local_json, street_key


def fixture_rows() -> list[dict]:
    rows: list[dict] = []
    for territory_id, district in BUDAPEST_DISTRICTS.items():
        rows.append(
            {
                "megye": "01",
                "telaz": territory_id,
                "szint": 3,
                "kozter": "együtt",
                "ev": 2024,
                "cshaz_ar": 900 if district == 6 else None,
                "cshaz_db": 4 if district == 6 else None,
                "tobbl_ar": 1420 if district == 6 else 1000 + district,
                "tobbl_db": 310 if district == 6 else 20,
                "panel_ar": 1100 if district == 6 else None,
                "panel_db": 8 if district == 6 else None,
                "total_ar": 1405 if district == 6 else 1000 + district,
                "total_db": 322 if district == 6 else 20,
                "szoras": 42.5 if district == 6 else 30,
                "idosor": 1,
            }
        )
    rows.append(
        {
            "megye": "01",
            "telaz": "16586",
            "szint": 2,
            "kozter": "Andrássy út",
            "ev": 2024,
            "tobbl_ar": 1542,
            "tobbl_db": 44,
            "total_ar": 1542,
            "total_db": 44,
            "szoras": 33.1,
            "idosor": 1,
        }
    )
    return rows


def test_parse_ksh_json_maps_all_budapest_district_totals():
    rows = parse_ksh_local_json(fixture_rows())
    district_rows = [
        row for row in rows if row["area_code"] == "BUDAPEST_06" and not row["street_name"]
    ]
    assert {row["property_type"] for row in district_rows} == {
        "house",
        "condominium",
        "panel",
        "all",
    }
    condo = next(row for row in district_rows if row["property_type"] == "condominium")
    assert condo["mean_huf_m2"] == 1_420_000
    assert condo["transaction_count"] == 310
    assert "ter=16586" in condo["source_url"]
    assert "year=2024" in condo["source_url"]


def test_parse_ksh_json_preserves_street_missing_categories():
    rows = parse_ksh_local_json(fixture_rows())
    street_rows = [row for row in rows if row["street_name"] == "Andrássy út"]
    assert {row["property_type"] for row in street_rows} == {"condominium", "all"}
    condo = next(row for row in street_rows if row["property_type"] == "condominium")
    assert condo["area_code"] == "BUDAPEST_06"
    assert condo["street_key"] == street_key(" ANDRÁSSY   ÚT ")
    assert condo["mean_huf_m2"] == 1_542_000
    assert condo["transaction_count"] == 44


def test_parse_ksh_json_can_skip_streets_but_keeps_all_districts():
    rows = parse_ksh_local_json(fixture_rows(), include_streets=False)
    assert not any(row["street_name"] for row in rows)
    assert {row["area_code"] for row in rows} == {
        f"BUDAPEST_{district:02d}" for district in range(1, 24)
    }
