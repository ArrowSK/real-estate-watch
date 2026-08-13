# Real Estate Watch

Real Estate Watch is a small web application for checking residential property benchmarks, testing property-specific adjustments and calculating mortgage affordability. Hungary is the first supported country. The country-specific parts are isolated so that another market can be added later without replacing the application itself.

The interface is bilingual. English is the default; Hungarian can be selected from the header.

## What works in the first release

- Hungary and Budapest market views.
- Separate second-hand and new-build transaction benchmarks.
- Historical HUF/m² chart using official KSH quarterly data.
- HUF as the main currency, with smaller EUR and USD comparison values after the MNB FX collector has run.
- A property valuation worksheet with explicit, visible adjustment assumptions.
- A Hungarian mortgage calculator with annuity payments, total interest and +1/+2/+3 percentage-point stress tests.
- Indicative MNB HFM/JTM debt-brake checks using the current 2026 thresholds.
- General Hungarian property transfer-tax calculation under the NAV rule.
- Docker and Railway-ready deployment.
- Daily collection command and a low-overhead local scheduler.
- Source diagnostics, readiness/liveness endpoints, last-known-good fallbacks and data sanity checks.
- English and Hungarian UI.

## What is deliberately not faked

Two parts of the full product are not yet presented as complete:

1. **Live asking-price median and listing intelligence.** The current build uses KSH completed-transaction data. KSH's table provides a mean price per m², not a median. A live listing feed will be added only when there is a source we can use reliably and on acceptable terms. The app does not scrape a portal simply to make the dashboard look complete.
2. **Current bank offers.** The mortgage calculator applies the user's entered rate and the current MNB debt-brake framework. It does not invent a list of bank products. A bank-product provider belongs behind the existing provider boundary once a maintainable source is selected.

This distinction is intentional. A stale or invented financial number is worse than a clearly marked missing feature.

## Market data included with the application

The repository contains a small KSH reference dataset so that the application is useful immediately after first start, even if the live KSH page is temporarily unavailable. It covers Hungary and Budapest, second-hand and new dwellings, through 2026 Q1 where the corresponding KSH series is available.

The daily collector then attempts to refresh the official KSH table and the current MNB EUR/HUF and USD/HUF rates. Verified observations are stored in the database. If a source fails, the application keeps the last known-good observation and marks the source as degraded in Diagnostics.

Official sources used by the Hungary module:

- KSH STADAT 18.2.2.14, mean price per m² by region and settlement type: `https://www.ksh.hu/stadat_files/lak/en/lak0052.html`
- MNB exchange-rate web service: `https://www.mnb.hu/arfolyamok.asmx`
- MNB HFM/JTM debt-brake rules: `https://www.mnb.hu/penzugyi-stabilitas/makroprudencialis-politika/makroprudencialis-eszkoztar/adossagfek-szabalyok-hfm-jtm`
- NAV transfer-tax rates: `https://nav.gov.hu/ugyfeliranytu/adokulcsok_jarulekmertekek/illetekmertekek/visszterhes-vagyonatruhazasi-illetek`

More detail is in [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md).

## Quick start with Docker

You need Docker with Compose support.

```bash
git clone https://github.com/ArrowSK/real-estate-watch.git
cd real-estate-watch
docker compose up -d --build
```

Open `http://localhost:8000`.

The web container starts with the bundled KSH reference data. Run the live collectors once:

```bash
docker compose exec app python -m app.cli daily
```

Then check `http://localhost:8000/diagnostics`.

### Daily scheduler in Docker

The scheduler is an optional Compose profile. It wakes once a day, runs the same idempotent daily collection job, then sleeps again.

```bash
docker compose --profile scheduler up -d
```

It runs at approximately 04:15 in `Europe/Budapest`. If you already have a host scheduler, NAS scheduler or another job runner, leave the scheduler profile off and call:

```bash
python -m app.cli daily
```

once per day instead.

## Run without Docker

Python 3.12 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
python -m app.cli seed
uvicorn app.main:app --reload
```

SQLite is used by default for local development. Production deployments should use PostgreSQL by setting `DATABASE_URL`.

## Railway deployment

The root `Dockerfile` and `railway.toml` are ready for Railway.

A practical setup is:

1. Create a Railway project from this GitHub repository.
2. Add PostgreSQL.
3. Set `DATABASE_URL` to the PostgreSQL connection string. Both `postgres://` and `postgresql://` are normalised by the app to the psycopg driver.
4. Deploy the web service from the repository. Railway will use the root `Dockerfile`.
5. Set the web health-check path to `/health/ready` if it is not picked up from `railway.toml`.
6. Generate a public domain for the web service.
7. Add a second service from the same repository for daily collection. Its start command is:

   ```bash
   python -m app.cli daily
   ```

8. Configure that second service as a Railway Cron Job, for example once per day. Railway cron schedules use UTC and do not guarantee minute-perfect execution; this application does not require an exact collection minute.

The cron process exits after collection. No background worker is required on Railway.

## Configuration

Copy `.env.example` to `.env` for local non-Docker use. Do not commit `.env`.

Important variables:

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | SQLite or PostgreSQL SQLAlchemy URL |
| `APP_DEFAULT_LANGUAGE` | `en` or `hu` |
| `APP_TIMEZONE` | Local scheduler timezone; defaults to `Europe/Budapest` |
| `SOURCE_STALE_HOURS` | Reserved staleness threshold for source policy |
| `SELF_HEAL_ENABLED` | Restores bundled reference data if the market table is empty |
| `NOTIFY_WEBHOOK_URL` | Optional webhook for market-change and source-degradation notices |
| `MARKET_NOTIFY_CHANGE_PERCENT` | Notify when a refreshed tracked benchmark changes by at least this percentage; a new KSH quarter also notifies |
| `ADMIN_KEY` | Optional key protecting the manual `/ops/refresh` endpoint |

If `ADMIN_KEY` is not configured, the web refresh endpoint is disabled. Scheduled CLI collection still works.

## Self-checks and self-healing

The application is designed to fail conservatively.

- Database operations use transactions. A failed collection is rolled back before source health is updated.
- Market and FX values pass sanity ranges before they can replace a stored observation.
- FX movements above 15% from the last stored rate are rejected rather than silently accepted.
- The KSH parser supports a deliberately narrow set of table rows. If the table structure changes enough that those rows cannot be identified, the collector fails and keeps the previous data instead of guessing column meanings.
- Daily jobs use a database job record to avoid overlapping runs. A lock left behind by a crashed job is marked abandoned after two hours.
- A configured webhook receives a notice when a tracked KSH series moves past the configured threshold or advances to a new quarter, and when a live source degrades.
- If the market table is empty, the self-healer restores the bundled, source-attributed KSH reference data.
- `/health/live` checks that the process is alive.
- `/health/ready` checks the database and minimum reference data. Optional live sources may be degraded without taking the whole site offline.
- `/diagnostics` shows source failures and the last successful refresh.

"Self-healing" here means restoring known-safe local reference state and continuing from last known-good data. It does **not** mean modifying application code automatically or accepting unverified external values.

## Mortgage calculations

The mortgage calculator currently implements:

- standard annuity repayment;
- HUF mortgage HFM/LTV limits;
- JTM/DSTI limits for the selected interest-fixation category;
- the HUF 800,000 monthly net-income threshold effective from 1 January 2026;
- the qualifying 90% HFM path for first-home and green cases;
- the general NAV transfer-tax calculation: 4% up to HUF 1 billion of property value, 2% above that, capped at HUF 200 million per property.

The result is indicative. A lender can use a different appraised property value, recognise a different income amount, impose stricter underwriting or apply product-specific rules. The app therefore labels the result as a regulatory screen, not an approval.

The displayed "cash required" currently includes the entered down payment and the calculated general transfer tax. Lawyer, valuation, bank and insurance charges are not guessed. They should be added once their amount is known from a reliable source or a selected product.

## Property adjustments

The first release exposes the adjustment coefficients instead of hiding them:

- ground floor: -6%
- top floor: -3%
- no lift: -4%
- needs renovation: -12%
- renovated: +8%
- courtyard-facing: -4%
- balcony/terrace: +5%

They are placeholders for a future calibrated model, not claims about the exact Budapest market effect. The total adjustment is capped at ±40%, and the estimate is shown with a broad ±7% range. Once listing-level or transaction microdata are available, these coefficients should be replaced by locally estimated factors by area and property type.

## API and operational endpoints

- `GET /api/market?area=BUDAPEST&market=second_hand`
- `GET /api/health`
- `GET /health/live`
- `GET /health/ready`
- `POST /ops/refresh` — requires `X-Admin-Key` and a configured `ADMIN_KEY`

CLI operations:

```bash
python -m app.cli seed
python -m app.cli collect-market
python -m app.cli collect-fx
python -m app.cli daily
python -m app.cli self-check
python -m app.cli heal
```

## Architecture

The application is intentionally small:

```text
FastAPI + Jinja templates
        |
   service layer
        |
 country providers
        |
 SQLAlchemy
        |
SQLite (development) / PostgreSQL (production)
```

There is no Redis, message broker, JavaScript framework or permanent worker requirement.

Country-specific rules live under `app/countries/<country-code>/`. The Hungary module contains local market naming and current regulatory/tax logic. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) before adding another country.

## Development checks

```bash
pip install -e '.[dev]'
ruff check app tests
pytest -q
```

GitHub Actions runs the same Python checks and builds the Docker image for every push and pull request.

## Public-repository safety

This repository is public. Credentials, personal data and deployment secrets do not belong in it. `.env` is ignored, `.env.example` contains placeholders only, and operational write access can be protected with `ADMIN_KEY`.

If you find a security issue, use the process in [SECURITY.md](SECURITY.md) rather than posting credentials or exploitable details in a public issue.

## Licence

MIT. See [LICENSE](LICENSE).
