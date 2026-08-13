from app.countries.base import CountryDescriptor, CountryProvider


class HungaryProvider(CountryProvider):
    descriptor = CountryDescriptor(
        code="HU",
        name_en="Hungary",
        name_local="Magyarország",
        currency="HUF",
    )

    def areas(self) -> list[dict[str, str]]:
        areas: list[dict[str, str]] = [
            {
                "code": "BUDAPEST",
                "name_en": "Budapest — city",
                "name_hu": "Budapest — főváros",
                "kind": "city",
                "parent": "HU",
            }
        ]
        for district in range(1, 24):
            areas.append(
                {
                    "code": f"BUDAPEST_{district:02d}",
                    "name_en": f"Budapest District {district}",
                    "name_hu": f"Budapest {district}. kerület",
                    "kind": "district",
                    "parent": "BUDAPEST",
                }
            )
        areas.extend(
            [
                {
                    "code": "PEST",
                    "name_en": "Pest region",
                    "name_hu": "Pest régió",
                    "kind": "quarterly_region",
                    "parent": "HU",
                },
                {
                    "code": "CENTRAL_TRANSDANUBIA",
                    "name_en": "Central Transdanubia",
                    "name_hu": "Közép-Dunántúl",
                    "kind": "quarterly_region",
                    "parent": "HU",
                },
                {
                    "code": "WESTERN_TRANSDANUBIA",
                    "name_en": "Western Transdanubia",
                    "name_hu": "Nyugat-Dunántúl",
                    "kind": "quarterly_region",
                    "parent": "HU",
                },
                {
                    "code": "SOUTHERN_TRANSDANUBIA",
                    "name_en": "Southern Transdanubia",
                    "name_hu": "Dél-Dunántúl",
                    "kind": "quarterly_region",
                    "parent": "HU",
                },
                {
                    "code": "NORTHERN_HUNGARY",
                    "name_en": "Northern Hungary",
                    "name_hu": "Észak-Magyarország",
                    "kind": "quarterly_region",
                    "parent": "HU",
                },
                {
                    "code": "NORTHERN_GREAT_PLAIN",
                    "name_en": "Northern Great Plain",
                    "name_hu": "Észak-Alföld",
                    "kind": "quarterly_region",
                    "parent": "HU",
                },
                {
                    "code": "SOUTHERN_GREAT_PLAIN",
                    "name_en": "Southern Great Plain",
                    "name_hu": "Dél-Alföld",
                    "kind": "quarterly_region",
                    "parent": "HU",
                },
                {
                    "code": "HU",
                    "name_en": "Hungary — national",
                    "name_hu": "Magyarország — országos",
                    "kind": "country",
                    "parent": "",
                },
            ]
        )
        return areas
