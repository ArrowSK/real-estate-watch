from app.services.ksh_local import parse_ksh_local_page, street_key


ROOT_HTML = """
<html><body>
<select><option value="2023">2023</option><option value="2024" selected>2024</option></select>
<a href="/s/ingatlanadattar/adattar?ter=16586">Budapest 06. kerület</a>
<table>
<tr><th>Ingatlan helye</th><th>house price</th><th>house n</th><th>condo price</th><th>condo n</th><th>panel price</th><th>panel n</th><th>all price</th><th>all n</th><th>spread</th></tr>
<tr><td>Budapest 06. kerület</td><td>1200</td><td>4</td><td>1420</td><td>310</td><td>1100</td><td>8</td><td>1405</td><td>322</td><td>42.5</td></tr>
<tr><td>Budapest összesen</td><td>980</td><td>1100</td><td>1210</td><td>9800</td><td>1000</td><td>3100</td><td>1170</td><td>14000</td><td>55.0</td></tr>
</table></body></html>
"""

STREET_HTML = """
<html><body>
<select><option value="2024" selected>2024</option></select>
<table>
<tr><th>Ingatlan helye</th><th>house price</th><th>house n</th><th>condo price</th><th>condo n</th><th>panel price</th><th>panel n</th><th>all price</th><th>all n</th><th>spread</th></tr>
<tr><td>Andrássy út</td><td>–</td><td>–</td><td>1542</td><td>44</td><td>–</td><td>–</td><td>1542</td><td>44</td><td>33.1</td></tr>
</table></body></html>
"""


def test_parse_ksh_district_rows_and_links():
    year, rows, links = parse_ksh_local_page(
        ROOT_HTML,
        source_url="https://www.ksh.hu/s/ingatlanadattar/adattar?ter=01&year=2024",
    )
    assert year == 2024
    district = [row for row in rows if row["area_code"] == "BUDAPEST_06"]
    assert len(district) == 4
    condo = next(row for row in district if row["property_type"] == "condominium")
    assert condo["mean_huf_m2"] == 1_420_000
    assert condo["transaction_count"] == 310
    assert "BUDAPEST_06" in links


def test_parse_ksh_street_rows_preserves_missing_categories():
    year, rows, _ = parse_ksh_local_page(
        STREET_HTML,
        source_url="https://www.ksh.hu/s/ingatlanadattar/adattar?ter=16586&year=2024",
        fixed_area_code="BUDAPEST_06",
        fixed_area_name="Budapest 06. kerület",
    )
    assert year == 2024
    assert {row["property_type"] for row in rows} == {"condominium", "all"}
    condo = next(row for row in rows if row["property_type"] == "condominium")
    assert condo["street_name"] == "Andrássy út"
    assert condo["street_key"] == street_key(" ANDRÁSSY   ÚT ")
    assert condo["mean_huf_m2"] == 1_542_000
    assert condo["transaction_count"] == 44
