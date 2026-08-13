# Real Estate Watch

Real Estate Watch is a small self-hosted application for residential market analysis, property valuation and mortgage affordability. Hungary is the first supported country, but country-specific geography, regulation and tax logic are kept out of the general web layer so another market can be added later.

The interface is bilingual. English is the default; Hungarian can be selected from the header.

Version 0.2 changes the market model substantially: it no longer stops at a broad Budapest transaction benchmark. It combines **official completed-transaction evidence**, **granular Budapest district/street evidence**, and a separately labelled **observed asking-market subset**. Those layers are compared, never silently blended.

## What the application shows

The main market page separates two questions.

**Transaction-value evidence** comes from KSH. For Budapest second-hand homes, the app can use annual district or street-level KSH Ingatlanadattár statistics to measure a local/property-type factor relative to the same-year Budapest annual market, then apply that factor to the latest official Budapest quarterly second-hand benchmark.

**Observed asking-market evidence** comes from an experimental Duna House observer. It uses the source's property sitemap for discovery, keeps only factual fields required for statistics, and publishes aggregate medians/ranges rather than rebuilding a listing portal.

The dashboard can therefore show, where data are available:

- current transaction-value nowcast in HUF/m²;
- observed asking median in HUF/m²;
- the asking/transaction-value gap;
- six-month official transaction movement;
- observed asking movement after enough daily history has accumulated;
- official transaction count;
- asking sample size, P25/P75 and confidence;
- EUR/USD comparison values from MNB FX.

A missing asking layer does not replace or disable the official transaction layer.

## Granular Budapest analysis

KSH Ingatlanadattár is collected separately from the quarterly KSH series. For Budapest it can provide district and, where published, street-level completed-sale statistics by broad property class:

- family house;
- multi-unit condominium apartment;
- panel apartment;
- all dwellings.

The valuation worksheet can therefore start from a much more local source than a city-wide average. It exposes exactly which fallback was used and which year the local benchmark belongs to.

The current local nowcast formula is intentionally simple and inspectable:

```text
(local annual KSH HUF/m² / same-year Budapest annual all-dwelling HUF/m²)
× latest Budapest quarterly SECOND-HAND KSH HUF/m²
= current transaction-value nowcast
```

The observed asking median is **not** an input to that formula. It is shown as an independent comparison.

The statistical assumptions and fallback order are documented in [docs/METHODOLOGY.md](docs/METHODOLOGY.md).

## Experimental Duna House asking observer

The Duna House provider is deliberately more cautious than an ordinary scraper.

At the project's manual review on 13 August 2026, Duna House's public `robots.txt` allowed crawling and declared a dedicated property sitemap. The reviewed legal/policy page was not treated as an open-data licence. The project therefore describes this source as an **experimental observed subset**, not open data and not the whole Hungarian asking market.

The collector stores only factual fields needed for aggregation:

- source reference number and URL;
- locality/postcode/district;
- broad property class;
- new/second-hand status when determinable;
- rooms;
- asking price;
- floor area;
- first/last seen and source `lastmod` timestamps.

It does **not** store descriptions, photos, plans, seller/agent names, phone numbers or email addresses. Individual observed listings are not exposed through a public browsing API.

Before collection, a policy guard checks the reviewed robots/sitemap contract and source policy fingerprints. Collection pauses if those assumptions change unexpectedly or if the dated manual review expires. The collector does not try to evade a changed restriction.

The full operational and compliance boundary is in [docs/DUNA_HOUSE_PROVIDER.md](docs/DUNA_HOUSE_PROVIDER.md).

## What works in 0.2

- English-first and Hungarian UI.
- Responsive market-ledger visual design with original SVG icon assets and no frontend build tool.
- Budapest districts, broad Hungarian statistical regions and national market views.
- Separate second-hand and new-build transaction series.
- Official KSH quarterly completed-transaction mean HUF/m².
- Official matching KSH transaction counts.
- KSH Ingatlanadattár district/street/property-class benchmarks for Budapest.
- Transparent local transaction-value nowcast.
- Experimental Duna House asking-market observation with median, mean, P25/P75, sample, price cuts, new observations, coverage and confidence.
- Strict asking-versus-transaction separation and explicit gap calculation.
- Property valuation worksheet with optional Budapest street and optional property asking price.
- Visible fallback property-adjustment coefficients.
- HUF as the main currency with MNB EUR/USD comparison values.
- Hungarian mortgage calculator with annuity payment, total interest and +1/+2/+3 percentage-point stress scenarios.
- Indicative MNB HFM/JTM debt-brake screen.
- General NAV property-transfer-tax calculation.
- SQLite development and PostgreSQL production persistence.
- Docker, Docker Compose and Railway deployment paths.
- Short-lived daily collection job; no permanent worker required.
- Generic webhook, Telegram and SMTP notification channels.
- Self-checks, source health, source freshness and job history.
- Bounded transient retry and last-known-good behavior.
- Experimental-source policy guard.
- Normal CI with lint/tests/Docker boot smoke test.
- Separate scheduled live source-contract workflow.

## What is still deliberately incomplete

### Current bank-product comparison

The mortgage calculator uses a rate entered by the user and applies the current implemented regulatory screen. It does not invent bank products or label a manually entered rate as a current offer.

A future mortgage-product provider needs a maintainable interface that preserves institution, product, THM/APR, fixation, term, amount limits, eligibility conditions and source update date.

### Asking-market history before installation

The Duna House observer builds daily history prospectively. A deployment created today cannot legitimately display six months of its own daily asking history tomorrow. The chart grows as observations accumulate.

### Full-market asking median

The observed Duna House median is not presented as a median of all Hungarian portals. Adding more lawful providers later can improve representativeness, but each provider needs its own source-access review and health checks.

### Calibrated hedonic valuation coefficients

The market baseline is now substantially more granular, but property-condition adjustments such as ground floor/no lift/renovation remain visible fallback assumptions rather than trained Hungarian coefficients. They are kept separate from source-derived market evidence.

### Personal public watchlists

Benchmark notifications exist, but persistent per-user watchlists need authentication and ownership before a public hosted deployment should accept them.

The remaining sequence is in [ROADMAP.md](ROADMAP.md).

## Data sources

Current Hungary sources:

- KSH STADAT 18.2.2.14 — quarterly completed-transaction mean HUF/m²: `https://www.ksh.hu/stadat_files/lak/en/lak0052.html`
- KSH STADAT 18.2.2.15 — quarterly transaction counts: `https://www.ksh.hu/stadat_files/lak/en/lak0053.html`
- KSH Ingatlanadattár — granular completed-transaction statistics; the frontend client dataset used by the collector is `https://www.ksh.hu/s/ingatlanadattar/inga-data.json`
- MNB latest official exchange rates: `https://www.mnb.hu/arfolyamok`
- MNB HFM/JTM debt-brake rules: `https://www.mnb.hu/penzugyi-stabilitas/makroprudencialis-politika/makroprudencialis-eszkoztar/adossagfek-szabalyok-hfm-jtm`
- NAV general transfer-tax rates: `https://nav.gov.hu/ugyfeliranytu/adokulcsok_jarulekmertekek/illetekmertekek/visszterhes-vagyonatruhazasi-illetek`
- Duna House public property discovery/listing pages — experimental factual observed subset; see the dedicated provider documentation before enabling it.

See [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) for provenance and limitations.

## Quick start with Docker

You need Docker with Compose support.

```bash
git clone https://github.com/ArrowSK/real-estate-watch.git
cd real-estate-watch
docker compose up -d --build
```

Open:

```text
http://localhost:8000
```

The web application starts with bundled KSH reference data for resilience. Run the live collectors once:

```bash
docker compose exec app python -m app.cli daily
```

Then open:

```text
http://localhost:8000/diagnostics
```

The first granular KSH refresh downloads KSH Ingatlanadattár’s official client JSON dataset once and materialises the supported Budapest city, district, street and property-class rows locally. The Duna House observer is bounded by `DH_MAX_LISTINGS_PER_RUN`, so source coverage builds over multiple runs rather than attempting a full detail-page sweep at once.

### Optional Docker scheduler

```bash
docker compose --profile scheduler up -d
```

The scheduler runs the same idempotent daily command. If you already have a NAS/host scheduler, leave this profile disabled and schedule:

```bash
python -m app.cli daily
```

once per day.

## Run without Docker

Python 3.12 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
python -m app.cli seed
uvicorn app.main:app --reload
```

SQLite is the development default. Use PostgreSQL for a persistent production deployment by setting `DATABASE_URL`.

## Railway

The root `Dockerfile` and `railway.toml` are intended for Railway deployment.

A practical setup:

1. Create a Railway project from this repository.
2. Add PostgreSQL.
3. Set `DATABASE_URL` to the PostgreSQL connection string.
4. Deploy the web service from the repository.
5. Use `/health/ready` as the health check.
6. Generate a public domain.
7. Add another service from the same repository with start command:

   ```bash
   python -m app.cli daily
   ```

8. Configure that second service as a Railway Cron Job once per day.

The collection process exits when finished. No queue or permanent worker is required for the current scale.

## Configuration

Copy `.env.example` to `.env` for local non-Docker use. Never commit `.env`.

Important variables:

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | SQLite or PostgreSQL SQLAlchemy URL |
| `APP_DEFAULT_LANGUAGE` | `en` or `hu` |
| `APP_TIMEZONE` | Local scheduler timezone; default `Europe/Budapest` |
| `SOURCE_STALE_HOURS` | General source-freshness warning threshold |
| `SELF_HEAL_ENABLED` | Allow safe restoration of missing bundled KSH reference rows |
| `KSH_LOCAL_REFRESH_HOURS` | Minimum interval between granular KSH refreshes; default 168 |
| `DH_ENABLED` | Enable/disable the experimental Duna House observer |
| `DH_MAX_LISTINGS_PER_RUN` | Maximum listing detail pages visited in one normal run |
| `DH_REQUEST_DELAY_SECONDS` | Delay between Duna House detail-page requests |
| `DH_MIN_AGGREGATE_SAMPLE` | Minimum usable rows before an asking aggregate is published |
| `DH_POLICY_REVIEW_MAX_AGE_DAYS` | Pause the observer when its manual policy review is too old |
| `MARKET_NOTIFY_CHANGE_PERCENT` | Broad KSH benchmark movement notification threshold |
| `NOTIFY_WEBHOOK_URL` | Optional webhook channel |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Optional Telegram channel |
| `SMTP_*` / `NOTIFY_EMAIL_TO` | Optional STARTTLS email channel |
| `ADMIN_KEY` | Optional protection for manual `/ops/refresh` |

If `ADMIN_KEY` is not configured, the web refresh endpoint stays disabled. Scheduled CLI collection is unaffected.

## Operational commands

```bash
# Restore only missing bundled quarterly reference rows
python -m app.cli seed

# Official broad market
python -m app.cli collect-market
python -m app.cli collect-counts

# Official granular Budapest market
python -m app.cli collect-local

# MNB currency comparison
python -m app.cli collect-fx

# Check Duna House policy/sitemap plus one listing page, without bulk collection
python -m app.cli probe-dh

# Bounded asking-market observation
python -m app.cli collect-dh
python -m app.cli collect-dh --limit 20

# Complete scheduled pipeline
python -m app.cli daily

# Application checks / safe recovery
python -m app.cli self-check
python -m app.cli heal
```

## Self-checks and self-healing

The application is meant to fail conservatively.

It can automatically:

- retry clearly transient network failures a small number of times;
- retain the last verified source values when a collector fails;
- restore missing bundled KSH bootstrap rows without overwriting later live revisions;
- reject implausible market/FX values;
- reject unexpectedly stale/future MNB fixing dates;
- mark a crashed daily-job lock abandoned after two hours;
- create newly introduced tables at startup;
- mark a disappeared observed listing inactive without calling it sold;
- pause the experimental asking collector after a source-policy change or expired review;
- surface degraded/stale state through Diagnostics.

It does **not** automatically edit its own code, guess a changed source schema, interpolate missing KSH values, rotate around access restrictions or accept malformed data because a number happens to look plausible.

That boundary is intentional: self-healing should restore known-safe state, not manufacture new truth.

## Mortgage calculations

The Hungary calculator currently includes:

- standard annuity repayment;
- HUF mortgage HFM/LTV limits;
- JTM/DSTI limits for the selected fixation category;
- the implemented HUF 800,000 monthly net-income threshold effective from 1 January 2026;
- qualifying 90% HFM path for selected first-home/green scenarios;
- +1/+2/+3 percentage-point payment stress tests;
- the implemented general NAV transfer-tax rule.

The output is indicative, not an approval. A lender can use a different appraised property value, recognise a different income amount and impose stricter or product-specific underwriting.

The displayed cash requirement includes the entered down payment and the general transfer-tax calculation. Lawyer, valuation, bank and insurance charges are not guessed.

## Property adjustments

Current fallback coefficients remain visible:

- ground floor: -6%
- top floor: -3%
- no lift: -4%
- needs renovation: -12%
- renovated: +8%
- courtyard-facing: -4%
- balcony/terrace: +5%

The combined adjustment is capped at ±40%, and the estimate uses a broad range. These are not claims about exact causal Budapest market effects. They are placeholders until enough lawful microdata exist for calibrated, versioned local models.

## API and health endpoints

- `GET /api/market?area=BUDAPEST_06&market=second_hand&property_type=apartment`
- `GET /api/health`
- `GET /health/live`
- `GET /health/ready`
- `POST /ops/refresh` — requires `X-Admin-Key` if enabled.

The market API returns the official nowcast and observed asking layer as separate objects.

## Tests

```bash
pip install -e '.[dev]'
ruff check app tests
pytest -q
```

Normal GitHub Actions CI also validates Docker Compose, builds the image and boots a container until `/health/ready` succeeds.

A separate scheduled source-contract workflow checks the live KSH/MNB parsers, granular KSH district/street source and a deliberately small Duna House policy/sitemap/listing probe. It does not bulk-collect Duna House in CI.

## Public-repository safety

This repository is public. Credentials, personal data and deployment secrets do not belong in it.

`.env` is ignored, `.env.example` contains no credentials, and the listing observer intentionally avoids storing contact data and source creative content.

Please use [SECURITY.md](SECURITY.md) for security disclosures rather than posting credentials or exploit details in a public issue.

## More documentation

- [Data sources and provenance](docs/DATA_SOURCES.md)
- [Market and valuation methodology](docs/METHODOLOGY.md)
- [Duna House provider boundary](docs/DUNA_HOUSE_PROVIDER.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Roadmap](ROADMAP.md)

## Licence

MIT. See [LICENSE](LICENSE).
