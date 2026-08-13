from app.services.market import parse_ksh_benchmarks


def test_ksh_parser_extracts_core_and_regional_rows():
    html = """
    <table>
      <tr><th>Second hand dwellings</th></tr>
      <tr><td>Budapest</td><td>capital</td><td>662</td></tr>
      <tr><td>Pest</td><td>together</td><td>397</td></tr>
      <tr><td>Country</td><td>total</td><td>332</td></tr>
      <tr><th>New dwellings</th></tr>
      <tr><td>Budapest</td><td>capital</td><td>852</td></tr>
      <tr><td>Pest</td><td>together</td><td>541</td></tr>
      <tr><td>Country</td><td>total</td><td>662</td></tr>
    </table>
    """
    rows = parse_ksh_benchmarks(html)
    assert len(rows) == 6
    assert rows[0]["period"] == "2021-Q1"
    assert rows[0]["price_huf_m2"] == 662_000
    pest = [row for row in rows if row["area_code"] == "PEST"]
    assert {row["property_market"] for row in pest} == {"second_hand", "new"}
