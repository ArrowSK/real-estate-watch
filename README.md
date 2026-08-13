# Real Estate Watch

Real Estate Watch is a small self-hosted application for residential market analysis, property valuation and mortgage affordability. Hungary is the first supported country, but country-specific geography, regulation and tax logic are kept out of the general web layer so another market can be added later.

The interface is bilingual. English is the default; Hungarian can be selected from the header.

Version 0.2.1 reconciles the useful work from the former `feat/live-market-intelligence` branch with the newer mainline analytics. It keeps three different kinds of evidence separate:

- official completed-transaction evidence from KSH;
- granular Budapest district/street evidence from KSH Ingatlanadattár;
- an experimental observed asking-market subset from Duna House.

Those layers can be compared, but they are never silently blended into one vague number called “market price”.

## Main workspaces

### Market

The main market page answers the broad question: what does the latest verified transaction evidence say, and what does the observed asking subset say beside it?

For Budapest second-hand homes, the current transaction-value nowcast can apply a local/property-type factor derived from annual KSH Ingatlanadattár data to the latest official Budapest quarterly second-hand benchmark.

The page can show, where data are available:

- current transaction-value nowcast in HUF/m²;
- observed asking median in HUF/m²;
- asking/transaction-value gap;
- six-month official transaction movement;
- observed asking movement after enough daily history has accumulated;
- official transaction count;
- asking sample size, P25/P75 and confidence;
- EUR/USD comparison values from MNB FX.

A missing asking layer does not replace or disable the official transaction layer.

### Live asking

`/live` is a dedicated workspace for the Duna House observed subset. It is intentionally not presented as the complete Hungarian asking market.

It adds signals that are difficult to understand from a single median alone:

- current observed asking median and P25–P75 range;
- usable active sample size;
- observed price-cut share;
- median price cut where a reduction has been observed;
- new observations during the last seven days;
- median time since this deployment first observed the listing;
- postcode drill-down where the sample permits publication;
- asking history accumulated by this deployment;
- comparison with the corresponding official transaction benchmark;
- coverage of short structured factual property attributes.

“Observed days” is not advertised days-on-market. The application does not know how long a listing existed before this deployment first saw it.

### Local evidence

`/local` is a separate KSH workbench for Budapest district and street evidence.

It exposes:

- annual published KSH local mean HUF/m²;
- transaction count where published;
- relative spread where published;
- same-year Budapest all-dwelling reference;
- local/property-type factor;
- current factor-based estimate using the latest Budapest second-hand benchmark;
- street rows ordered by the strongest available transaction sample;
- a simple confidence label so small or dispersed samples are not presented with the same authority as stronger ones.

The current second-hand local formula is deliberately inspectable:

```text
local factor
    = local annual KSH HUF/m²
      / same-year Budapest annual all-dwelling KSH HUF/m²

current local-factor estimate
    = latest Budapest quarterly SECOND-HAND KSH HUF/m²
      × local factor
```

The older feature branch used a different “local annual value × subsequent Budapest trend” formulation. That implementation was deliberately not merged back because the mainline method above is now the documented source-consistent approach.

### Property valuation

The valuation worksheet uses the same official baseline hierarchy rather than introducing a second valuation model. It can start from district or street evidence where supported, then apply visible property-specific fallback adjustments selected by the user.

An optional asking price can be compared with the estimate, but the observed Duna House median is not fed into the official transaction nowcast.

## Experimental Duna House asking observer

The Duna House provider is deliberately more cautious than an ordinary scraper.

At the project's manual review on 13 August 2026, Duna House's public `robots.txt` allowed crawling and declared a dedicated property sitemap. The reviewed legal/policy page was not treated as an open-data licence. The project therefore describes this source as an **experimental observed subset**, not open data and not the whole Hungarian asking market.

The collector stores only factual fields needed for market analysis:

- source reference number and URL;
- locality, postcode and Budapest district where identifiable;
- broad property class;
- new/second-hand status where determinable;
- rooms;
- asking price;
- floor area;
- first/last seen and source `lastmod` timestamps;
- short structured factual fields when they are explicitly present, such as building type, condition, construction year, floor, lift, balcony/terrace, view, orientation, heating and energy rating.

These optional facts are stored in a separate additive table. They are not yet used as trained valuation coefficients.

The collector does **not** store descriptions, photos, plans, seller/agent names, phone numbers or email addresses. Individual observed listings are not exposed through a public browsing API.

Before collection, a policy guard checks the reviewed robots/sitemap contract and source policy fingerprints. Collection pauses if those assumptions change unexpectedly or if the dated manual review expires. The collector does not try to evade a changed restriction.

### Disappearance is not a sale

A sitemap can change temporarily. Version 0.2.1 therefore no longer marks an observed listing inactive after one missing sitemap observation.

By default:

```text
first sitemap miss   -> keep active, record pending absence
second sitemap miss  -> mark inactive
reappearance         -> reset miss state and reactivate
```

`DH_INACTIVE_AFTER_MISSES` controls the threshold and defaults to `2`.

Even after a listing becomes inactive, the application records only that it disappeared from the observed source. **Removed does not mean sold.**

The full operational and compliance boundary is in [docs/DUNA_HOUSE_PROVIDER.md](docs/DUNA_HOUSE_PROVIDER.md).

## What works in 0.2.1

- English-first and Hungarian UI.
- Responsive market-ledger visual design with original SVG icon assets and no frontend build tool.
- Broad Market, dedicated Live Asking, dedicated Local Evidence, Property Value, Mortgage and Diagnostics views.
- Budapest districts, broad Hungarian statistical regions and national transaction views.
- Separate second-hand and new-build transaction series.
- Official KSH quarterly completed-transaction mean HUF/m².
- Official matching KSH transaction counts.
- KSH Ingatlanadattár district/street/property-class benchmarks for Budapest.
- Corrected transparent second-hand local-factor nowcast.
- Experimental Duna House asking observation with median, mean, P25/P75, sample, price cuts, new observations, coverage and confidence.
- Postcode-level observed asking aggregates when the publication sample threshold is met.
- Observed price-cut share, seven-day new-observation counts and median observed duration.
- Short structured factual listing attributes in an additive table.
- Two-observation default sitemap disappearance tolerance with automatic recovery on reappearance.
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
- Bounded transient retry and last-known-good behaviour.
- Experimental-source policy guard.
- Normal CI with lint/tests/Docker boot smoke test.
- Separate scheduled live source-contract workflow.

## What is still deliberately incomplete

### Current bank-product comparison

The mortgage calculator uses a rate entered by the user and applies the implemented regulatory screen. It does not invent bank products or label a manually entered rate as a current offer.

A future mortgage-product provider needs a maintainable interface that preserves institution, product, THM/APR, fixation, term, amount limits, eligibility conditions and source update date.

### Asking-market history before installation

The Duna House observer builds daily history prospectively. A deployment created today cannot legitimately display six months of its own daily asking history tomorrow. The chart grows as observations accumulate.

### Full-market asking median

The observed Duna House median is not presented as a median of all Hungarian portals. Adding more lawful providers later can improve representativeness, but each provider needs its own source-access review and health checks.

### Calibrated hedonic valuation coefficients

The market baseline is substantially more granular, and short factual listing attributes are now retained where available, but property-condition adjustments such as ground floor/no lift/renovation remain visible fallback assumptions rather than trained Hungarian coefficients.

Before structured Duna House attributes are used for a model, their coverage, stability and selection bias need to be measured. Source facts should not be turned into coefficients merely because the fields now exist.

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

Then inspect:

```text
http://localhost:8000/diagnostics
http://localhost:8000/live
http://localhost:8000/local
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
7. Add another service from the same repository with start command `python -m app.cli daily`.
8. Configure that second service as a Railway Cron Job once per day.

The collection process exits when finished. No queue or permanent worker is required for the current scale.

## Configuration

Copy `.env.example` to `.env` for local non-Docker use. Never commit `.env`.

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
| `DH_INACTIVE_AFTER_MISSES` | Consecutive sitemap absences before an observed listing becomes inactive; default 2 |
| `DH_POLICY_REVIEW_MAX_AGE_DAYS` | Pause the observer when its manual policy review is too old |
| `MARKET_NOTIFY_CHANGE_PERCENT` | Broad KSH benchmark movement notification threshold |
| `NOTIFY_WEBHOOK_URL` | Optional webhook channel |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Optional Telegram channel |
| `SMTP_*` / `NOTIFY_EMAIL_TO` | Optional STARTTLS email channel |
| `ADMIN_KEY` | Optional protection for manual `/ops/refresh` |

If `ADMIN_KEY` is not configured, the web refresh endpoint stays disabled. Scheduled CLI collection is unaffected.

## Operational commands

```bash
python -m app.cli seed
python -m app.cli collect-market
python -m app.cli collect-counts
python -m app.cli collect-local
python -m app.cli collect-fx
python -m app.cli probe-dh
python -m app.cli collect-dh
python -m app.cli collect-dh --limit 20
python -m app.cli daily
python -m app.cli self-check
python -m app.cli heal
```

`probe-dh` checks the policy/sitemap contract plus a deliberately small residential listing-page sample. It does not bulk-collect the market.

## Self-checks and self-healing

The application is meant to fail conservatively.

It can automatically:

- retry clearly transient network failures a small number of times;
- retain the last verified source values when a collector fails;
- restore missing bundled KSH bootstrap rows without overwriting later live revisions;
- reject implausible market/FX values;
- reject unexpectedly stale/future MNB fixing dates;
- mark a crashed daily-job lock abandoned after two hours;
- create newly introduced additive tables at startup;
- tolerate a transient single Duna House sitemap disappearance before marking an observation inactive;
- reactivate an observed listing and reset its absence state when it reappears;
- keep disappearance semantically separate from a completed sale;
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

## Property adjustments

Current fallback coefficients remain visible:

- ground floor: -6%
- top floor: -3%
- no lift: -4%
- needs renovation: -12%
- renovated: +8%
- courtyard-facing: -4%
- balcony/terrace: +5%

The combined adjustment is capped at ±40%, and the estimate uses a broad range. These are not claims about exact causal Budapest market effects. They remain placeholders until enough lawful microdata exist for calibrated, versioned local models.

## API and health endpoints

- `GET /`
- `GET /live`
- `GET /local`
- `GET /valuation`
- `GET /mortgage`
- `GET /diagnostics`
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
