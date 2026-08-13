# Architecture

## Design goals

Real Estate Watch should remain inexpensive to run, understandable to maintain, explicit about provenance and conservative when external data fail.

The application uses one web process and one relational database. Data collection runs as short-lived commands. Railway can run the daily command as a Cron Job; Docker users can enable the scheduler profile or call the same command from an existing scheduler.

Version 0.2 adds more data depth without adding Redis, a message broker, a JavaScript framework or a permanent worker.

## Request and data flow

```text
                          ┌──────────────────────┐
                          │      FastAPI UI      │
                          │  HTML + small JS     │
                          └──────────┬───────────┘
                                     │
                    ┌────────────────┴────────────────┐
                    │     comparison / valuation      │
                    │          analytics.py           │
                    └─────────┬──────────────┬─────────┘
                              │              │
                 completed transactions   observed asking
                              │              │
             ┌────────────────┴───┐      ┌───┴─────────────────┐
             │                    │      │                     │
       KSH quarterly      KSH Ingatlan-  Duna House      policy guard
       price + counts        adattár      observer        + sitemap
             │                    │      │                     │
             └────────────────────┴──────┴─────────────────────┘
                                     │
                                  SQLAlchemy
                                     │
                           SQLite / PostgreSQL
```

MNB FX, mortgage regulation and NAV transaction-cost rules are separate financial inputs. They do not alter the identity of the market-price datasets.

## Web layer

`app/main.py` contains FastAPI routes and renders Jinja templates. The browser receives ordinary HTML, an original SVG icon set, one stylesheet and a small JavaScript chart renderer. There is no separate frontend build pipeline.

The main market view deliberately displays two independent evidence cards:

1. official completed-transaction value / nowcast;
2. observed asking-market subset.

Their difference is calculated, but the asking figure is not blended into the official transaction nowcast.

The valuation route accepts district, property class and optional street. It asks the service layer for the finest verified official baseline available and exposes the fallback method used.

## Service layer

`app/services/` contains collection, analytics and operational safeguards.

Important modules:

- `market.py` — quarterly KSH completed-transaction mean HUF/m²;
- `transaction_counts.py` — matching KSH quarterly transaction counts;
- `ksh_local.py` — annual Budapest district/street/property-class KSH benchmarks;
- `duna_house.py` — experimental factual listing observer, policy guard and asking-market aggregates;
- `analytics.py` — official local-nowcast calculation and explicit asking/transaction comparison;
- `fx.py` — MNB EUR/HUF and USD/HUF fixing collection;
- `valuation.py` — explicit property-level fallback adjustments;
- `mortgage.py` — annuity and Hungary regulatory-screen calculations;
- `health.py` — database, data and provider self-checks;
- `source_health.py` — persistent source state;
- `http.py` — bounded retry for clearly transient failures;
- `self_heal.py` — limited safe restoration of bundled reference data;
- `notifications.py` — independent notification channels.

A collector must not silently overwrite good data after a malformed response. Parsing and validation happen before values are accepted. Only clearly transient network/HTTP failures are retried; a changed payload is treated as a source contract failure rather than retried until it happens to parse.

## Country layer

`app/countries/` contains country-specific naming, tax and regulatory rules.

The Hungary implementation is in `app/countries/hu/` and currently defines the country descriptor, Budapest districts and broad KSH statistical areas, HFM/JTM rules and general transfer-tax logic.

A future country should provide at least:

- country descriptor and local currency;
- geography provider;
- official transaction-market provider;
- any optional asking-market providers;
- mortgage/regulatory rules;
- transaction-cost rules;
- source-specific compliance manifest/review boundary;
- translations for country-specific labels where needed.

Global routes should not accumulate country-specific `if` chains. The current app is deliberately Hungary-first. The second country should be used to extract the interfaces that are genuinely common rather than inventing abstractions before two implementations exist.

## Persistence

SQLAlchemy supports SQLite for development and PostgreSQL for production.

Current tables:

- `market_snapshots` — quarterly official completed-transaction price series;
- `local_benchmarks` — annual granular KSH district/street/property-class observations;
- `observed_listings` — minimal factual identity for observed listing pages;
- `listing_snapshots` — daily factual price/area observations;
- `asking_market_snapshots` — publishable daily source aggregates;
- `provider_policy_state` — dated review status and policy fingerprints;
- `fx_snapshots`;
- `source_health`;
- `job_runs`;
- `notification_events`.

The new version 0.2 structures are additional tables only. Existing deployments can therefore create them through the current `Base.metadata.create_all()` startup path without rewriting existing columns.

This direct-create approach should not be stretched indefinitely. Before existing production columns need to change, before user accounts are added, or before another country introduces material schema evolution, the project should add versioned database migrations.

### Why raw factual listing observations are stored

Daily aggregates alone would make it impossible to identify observed price changes, avoid counting a listing twice on the same day or rebuild an aggregate after a methodology correction.

The app therefore stores a deliberately minimal listing identity and daily factual snapshot. It does not store the creative or personal content of the source advertisement. Individual listing records are not exposed through a public browsing endpoint.

## Official transaction nowcast

`analytics.py` keeps the nowcast deterministic and inspectable.

For a Budapest district/street local observation it uses:

```text
local annual KSH HUF/m²
× subsequent Budapest quarterly KSH completed-transaction movement
```

If an exact local class is unavailable, the fallback order is explicit and eventually reaches the broad Budapest quarterly series.

Observed Duna House asking prices are not part of the transaction-nowcast formula. The asking source appears only as an independent comparison layer.

See `docs/METHODOLOGY.md` for the statistical assumptions.

## Duna House provider boundary

The Duna House provider is optional and experimental.

Before detail-page collection it checks:

- whether the provider is enabled;
- whether the manual policy review is still within its allowed age;
- whether the reviewed `robots.txt` still permits the configured path;
- whether the configured property sitemap is still declared;
- whether the legal/policy page still passes minimum semantic checks;
- whether reviewed policy fingerprints changed.

An unexpected change pauses collection. The collector does not respond by changing user agents, rotating endpoints or bypassing a restriction.

The policy guard is deliberately not part of readiness. A public deployment must still serve official KSH/MNB functionality if the experimental asking provider pauses.

See `docs/DUNA_HOUSE_PROVIDER.md` for exact scope and limitations.

## Daily pipeline

`python -m app.cli daily` currently performs:

1. safe reference-data repair;
2. quarterly KSH price refresh;
3. KSH transaction-count refresh;
4. granular KSH refresh if its weekly interval is due;
5. broad market-change detection/notification;
6. MNB FX refresh;
7. guarded Duna House observed-listing collection;
8. self-checks;
9. job-state persistence and optional degraded-source notification.

The core job is considered operational if quarterly KSH, transaction counts and MNB FX succeed. Granular KSH or the experimental asking provider can degrade the job without making official market data disappear.

## Failure model

The application distinguishes four useful failure classes.

### Hard application failure

Examples: database cannot be queried or required reference data cannot be loaded. Readiness fails and the deployment should not receive traffic.

### Core source degradation

Examples: quarterly KSH or MNB contract breaks. The source is marked degraded and previously verified observations remain in place.

### Optional source degradation

Examples: the granular annual KSH page changes or the Duna House policy guard pauses collection. The affected layer becomes stale/unavailable, but the application remains usable with the other evidence layers.

### Suspicious data

Examples: implausible price/m², malformed structured data or an unusually large FX jump. The observation is rejected. Self-healing never invents a replacement.

## Self-healing boundaries

Automatic repair is deliberately limited to known-safe actions:

- create required tables at startup;
- restore a missing bundled KSH reference row without replacing an existing live/revised value;
- retry clearly transient network failures a small number of times;
- release a daily-job lock left running for more than two hours;
- keep serving the last verified data after source failure;
- mark disappeared observed listing URLs inactive without calling them sold;
- expose degraded/stale source and policy state through Diagnostics.

The bundled market files are bootstrap/recovery material, not an authority above live KSH. Regression tests verify that they cannot overwrite a later official revision.

Automatic code edits, schema guessing, fabricated substitute values, interpolation of missing KSH cells, automated bypass of source restrictions and acceptance of malformed external data are outside the self-healing model.

## Source-contract CI

Normal CI covers deterministic parsers, calculations, routes and a booted Docker health smoke test.

A second scheduled workflow checks the live external contracts. It runs the quarterly KSH collectors, granular KSH collector, MNB FX collector and a **Duna House probe** consisting of policy checks, the property sitemap and one listing-page parse.

The live-source workflow deliberately does not bulk-collect Duna House listings.

## Notifications

Notifications are a delivery layer, not the source of truth. The database and Diagnostics page retain source state even when all notification channels are disabled or a delivery fails.

The current channels are generic webhook, Telegram and SMTP email. Each configured channel is attempted independently. Credential-bearing delivery errors are sanitised before being written to notification history.

## Scaling

The default Duna House collector is intentionally bounded rather than trying to scan every discovered detail page daily. It prioritises unseen/changed pages and gradually improves source coverage while keeping request volume controlled.

This version still does not need Redis or a worker queue. If listing ingestion later grows to multiple providers, millions of rows or high-frequency refreshes, move ingestion into dedicated short-lived job services before adding queue infrastructure to the web process.

The current database job lock is sufficient for one daily collection pipeline. A multi-worker ingestion system should use a database advisory lock or a proper job queue.
