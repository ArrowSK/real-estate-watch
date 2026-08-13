from dataclasses import dataclass


@dataclass(frozen=True)
class CountryDescriptor:
    code: str
    name_en: str
    name_local: str
    currency: str


class CountryProvider:
    descriptor: CountryDescriptor

    def areas(self) -> list[dict[str, str]]:
        raise NotImplementedError
