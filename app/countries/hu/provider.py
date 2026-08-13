from app.countries.base import CountryDescriptor, CountryProvider


class HungaryProvider(CountryProvider):
    descriptor = CountryDescriptor(code="HU", name_en="Hungary", name_local="Magyarország", currency="HUF")

    def areas(self) -> list[dict[str, str]]:
        # These areas match rows that KSH publishes in the quarterly transaction-price table.
        # More granular city/district coverage belongs in a separate provider once a reliable
        # source with that resolution is available.
        return [
            {"code": "BUDAPEST", "name_en": "Budapest", "name_hu": "Budapest"},
            {"code": "PEST", "name_en": "Pest region", "name_hu": "Pest régió"},
            {
                "code": "CENTRAL_TRANSDANUBIA",
                "name_en": "Central Transdanubia",
                "name_hu": "Közép-Dunántúl",
            },
            {
                "code": "WESTERN_TRANSDANUBIA",
                "name_en": "Western Transdanubia",
                "name_hu": "Nyugat-Dunántúl",
            },
            {
                "code": "SOUTHERN_TRANSDANUBIA",
                "name_en": "Southern Transdanubia",
                "name_hu": "Dél-Dunántúl",
            },
            {
                "code": "NORTHERN_HUNGARY",
                "name_en": "Northern Hungary",
                "name_hu": "Észak-Magyarország",
            },
            {
                "code": "NORTHERN_GREAT_PLAIN",
                "name_en": "Northern Great Plain",
                "name_hu": "Észak-Alföld",
            },
            {
                "code": "SOUTHERN_GREAT_PLAIN",
                "name_en": "Southern Great Plain",
                "name_hu": "Dél-Alföld",
            },
            {"code": "HU", "name_en": "Hungary — national", "name_hu": "Magyarország — országos"},
        ]
