import pytest

from app.config import Settings
from app.services.duna_house import (
    _external_id_from_url,
    _residential_entries,
    _robots_contract,
    parse_dh_listing,
    parse_sitemap,
)


ROBOTS = """User-agent: *
    Allow: /

    Sitemap: https://newdhapi01.dh.hu/api/getFileItem/sitemap_content
        Sitemap: https://newdhapi01.dh.hu/api/getFileItem/sitemap_properties
"""

SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://www.dh.hu/ingatlan/LK123456</loc><lastmod>2026-08-13</lastmod></url>
  <url><loc>https://dh.hu/ingatlan/HZ654321</loc><lastmod>2026-08-12T10:00:00Z</lastmod></url>
  <url><loc>https://dh.hu/ingatlan/AL046179/elado-altalanos-budapest-13-kerulet</loc></url>
</urlset>
"""

LISTING = """<!doctype html>
<html><head><title>Budapest apartment LK123456</title>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Residence",
  "floorSize": {"@type": "QuantitativeValue", "value": 83},
  "numberOfRooms": 3,
  "address": {"@type": "PostalAddress", "postalCode": "1065", "addressLocality": "Budapest"},
  "offers": {"@type": "Offer", "price": "99900000", "priceCurrency": "HUF"}
}
</script></head><body><h1>Eladó lakás LK123456</h1></body></html>"""

NON_RESIDENTIAL = """<!doctype html><html><head><title>Eladó Általános, Budapest 13 kerület</title></head>
<body>AL046179 186 000 000 Ft 1135 Budapest 13. kerület 653 m²</body></html>"""


def test_default_sitemap_matches_reviewed_indented_robots_contract():
    settings = Settings()
    allowed, sitemaps = _robots_contract(ROBOTS, settings.dh_sitemap_url)
    assert allowed
    assert settings.dh_sitemap_url in sitemaps
    assert len(sitemaps) == 2


def test_parse_property_sitemap_normalizes_host_and_lastmod():
    entries = parse_sitemap(SITEMAP)
    assert len(entries) == 3
    assert entries[0].url == "https://dh.hu/ingatlan/LK123456"
    assert entries[0].lastmod is not None
    assert entries[1].lastmod is not None


def test_residential_scope_uses_stable_source_reference_prefixes():
    entries = parse_sitemap(SITEMAP)
    residential = _residential_entries(entries)
    assert [entry.url for entry in residential] == [
        "https://dh.hu/ingatlan/LK123456",
        "https://dh.hu/ingatlan/HZ654321",
    ]
    assert _external_id_from_url(entries[2].url) == "AL046179"


def test_parse_listing_keeps_only_required_factual_fields():
    facts = parse_dh_listing(LISTING, "https://www.dh.hu/ingatlan/LK123456")
    assert facts.external_id == "LK123456"
    assert facts.asking_price_huf == 99_900_000
    assert facts.floor_area_m2 == 83
    assert facts.rooms == 3
    assert facts.area_code == "BUDAPEST_06"
    assert facts.property_type == "apartment"
    assert round(facts.price_huf_m2) == round(99_900_000 / 83)
    assert not hasattr(facts, "description")
    assert not hasattr(facts, "phone")


def test_non_residential_reference_is_rejected_even_when_price_and_area_exist():
    with pytest.raises(ValueError, match="outside the residential observer scope"):
        parse_dh_listing(
            NON_RESIDENTIAL,
            "https://dh.hu/ingatlan/AL046179/elado-altalanos-budapest-13-kerulet",
        )
