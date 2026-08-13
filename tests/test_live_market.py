from app.countries.hu.providers.duna_house import (
    REVIEWED_LEGAL_MARKERS,
    REVIEWED_ROBOTS_LINES,
    evaluate_policy_text,
    parse_listing_page,
    parse_sitemap,
    validate_listing,
)
from app.services.ksh_local import parse_ksh_local_table


def test_duna_policy_gate_accepts_only_reviewed_markers():
    robots = "\n".join(REVIEWED_ROBOTS_LINES)
    legal = "<html><body>" + " ".join(REVIEWED_LEGAL_MARKERS) + "</body></html>"
    ok, detail = evaluate_policy_text(robots, legal)
    assert ok
    assert not detail["missing_robots"]
    assert not detail["missing_legal"]

    changed, _ = evaluate_policy_text("User-agent: *\nDisallow: /", legal)
    assert not changed


def test_duna_sitemap_keeps_only_property_urls():
    xml = """<?xml version="1.0"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://dh.hu/ingatlan/LK123/test</loc><lastmod>2026-08-13</lastmod></url>
      <url><loc>https://dh.hu/blog/not-a-property</loc></url>
    </urlset>
    """
    items = parse_sitemap(xml)
    assert len(items) == 1
    assert items[0].url.endswith("/ingatlan/LK123/test")
    assert items[0].lastmod == "2026-08-13"


def test_duna_listing_parser_extracts_facts_without_content_copy():
    html = """
    <html><head><script type="application/ld+json">
    {"@type":"Apartment","floorSize":{"value":"52"},"numberOfRooms":"2",
     "offers":{"price":"72595000","priceCurrency":"HUF"}}
    </script></head><body>
      <h1>Eladó lakás</h1><div>Újépítésű | 4031 Debrecen</div>
      <div>Épület szerkezete: Tégla | Építés éve: 2026 | Emelet: 2 | Lift: Van</div>
      <div>Erkély: 8 m² | Tájolás: Dél | Fűtés: Hőszivattyú | Energetikai besorolás: A+</div>
    </body></html>
    """
    item = parse_listing_page(
        "https://www.dh.hu/ingatlan/PR073859-LK-25159/example",
        html,
    )
    assert item.external_id == "PR073859-LK-25159"
    assert item.price_huf == 72_595_000
    assert item.area_m2 == 52
    assert item.rooms == 2
    assert item.market_segment == "new"
    assert item.market_class == "condominium"
    assert item.postal_code == "4031"
    assert validate_listing(item) == (True, None)


def test_ksh_local_parser_extracts_district_property_classes():
    html = """
    <table><tr>
      <td>Budapest 06. kerület</td><td>–</td><td>–</td>
      <td>1 132</td><td>1 163</td><td>–</td><td>–</td>
      <td>1 132</td><td>1 163</td><td>31</td>
    </tr></table>
    """
    rows = parse_ksh_local_table(html, year=2024, level="district")
    condo = next(row for row in rows if row["property_type"] == "condominium")
    assert condo["area_code"] == "BUDAPEST-06"
    assert condo["price_huf_m2"] == 1_132_000
    assert condo["transactions"] == 1163
    assert condo["relative_std_pct"] == 31
