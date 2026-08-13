# Contributing

Keep changes small enough to review and keep data provenance visible.

## Local checks

```bash
pip install -e '.[dev]'
ruff check app tests
pytest -q
```

If a change affects deployment, also build the container:

```bash
docker build -t real-estate-watch:test .
```

## Data changes

Do not add a market number without its source and observation period. Do not convert an asking price into a transaction price, or a mean into a median, merely to fill a missing field.

When a source parser changes, add a parser test that demonstrates the expected structure and a failure case. A parser should fail closed when column meaning becomes uncertain.

## Country modules

Country-specific tax and lending rules belong under `app/countries/<code>/`. Include the authoritative source URL in the module or source documentation and date-sensitive tests where practical.

## Language

English is the default interface language. Hungarian is maintained as a full user-facing option. New user-facing text should be added to both dictionaries in `app/i18n.py`.
