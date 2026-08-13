from app.countries.base import CountryDescriptor, CountryProvider


class HungaryProvider(CountryProvider):
    descriptor = CountryDescriptor(code="HU", name_en="Hungary", name_local="Magyarország", currency="HUF")

    def areas(self) -> list[dict[str, str]]:
        return [
            {"code": "HU", "name_en": "Hungary", "name_hu": "Magyarország"},
            {"code": "BUDAPEST", "name_en": "Budapest", "name_hu": "Budapest"},
        ]
