# Architecture

## Design goals

Real Estate Watch should remain inexpensive to run, understandable to maintain, explicit about provenance and conservative when external data fail.

The application uses one web process and one relational database. Data collection runs as short-lived commands. Railway can run the daily command as a Cron Job; Docker users can enable the scheduler profile or call the same command from an existing scheduler.

Version 0.2 adds substantially deeper market data without adding Redis, a message broker, a JavaScript framework or a permanent worker.

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
       price + counts      adattár JSON   observer        + sitemap
             │                    │      │                     │
             └────────────────────┴──────┴─────────────────────┘
                                     │
                                  SQLAlchemy
                                     │
                           SQLite / PostgreSQL
```

MNB FX, mortgage regulation and NAV transaction-cost rules are separate financial inputs. They do not alter the identity of the market datasets.

## Web layer

`app/main.py` contains FastAPI routes and renders Jinja templates. The browser receives ordinary HTML, an original SVG icon set, one stylesheet and a small JavaScript chart renderer. There is no separate frontend build pipeline.

The main market view deliberately displays two independent evidence cards:

1. official completed-transaction value / nowcast;
2. observed asking-market subset.

Their difference can be calculated, but the asking figure is never blended into the official transaction nowcast.

The valuation route accepts district, property class and optional street. It asks the service layer for the finest verified official baseline available and exposes the fallback method used.

## Service layer

`app/services/` contains collection, analytics and operational safeguards.

Important modules:

- `market.py` — quarterly KSH completed-transaction mean HUF/m²;
- `transaction_counts.py` — matching KSH quarterly transaction counts;
- `ksh_local.py` — official KSH Ingatlanadattár client JSON normalisation for Budapest city/district/street/property class;
- `duna_house.py` — experimental factual listing observer, policy guard and asking-market aggregates;
- `analytics.py` — official local-factor nowcast and explicit asking/transaction comparison;
- `fx.py` — MNB EUR/HUF and USD/HUF fixing collection;
- `valuation.py` — explicit property-level fallback adjustments;
- `mortgage.py` — annuity and Hungary regulatory-screen calculations;
- `health.py` — database, data and provider self-checks;
- `source_health.py` — persistent source state;
- `http.py` — bounded retry for clearly transient failures;
- `self_heal.py` — limited safe restoration of bundled reference data;
- `notifications.py` — independent notification channels.

A collector must not silently overwrite good data after a malformed response. Parsing and validation happen before values are accepted. Only clearly transient network/HTTP failures are retried; a changed payload is treated as a source-contract failure rather than retried until it happens to parse.

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
- source-specific compliance/review boundary;
- translations for country-specific labels where needed.

The second country should be used to extract genuinely common provider interfaces rather than guessing abstractions before two implementations exist.

## Persistence

SQLAlchemy supports SQLite for development and PostgreSQL for production.

Current tables:

- `market_snapshots` — quarterly official completed-transaction price series;
- `local_benchmarks` — annual granular KSH Budapest city/district/street/property-class observations;
- `observed_listings` — minimal factual identity for observed listing pages;
- `listing_snapshots` — daily factual price/area observations;
- `asking_market_snapshots` — publishable daily source aggregates;
- `provider_policy_state` — dated review status and policy fingerprints;
- `fx_snapshots`;
- `source_health`;
- `job_runs`;
- `notification_events`.

Version 0.2 introduces additional tables rather than destructive changes to existing columns. Existing deployments can therefore create them through the current `Base.metadata.create_all()` startup path without rewriting existing data.

This direct-create approach should not be stretched indefinitely. Before existing production columns need to change, before user accounts are added, or before another country introduces material schema evolution, the project should add versioned database migrations.

### Why factual listing observations are stored

Daily aggregates alone would make it impossible to identify observed price changes, avoid counting a listing twice on one day or rebuild an aggregate after a methodology correction.

The app therefore stores a deliberately minimal listing identity and daily factual snapshot. It does not store source descriptions, photographs or contact data. Individual observed listings are not exposed through a public browsing endpoint.

## Granular KSH ingestion

KSH's public Ingatlanadattár frontend currently loads a single official client dataset from `inga-data.json`. The application retrieves that dataset at a weekly interval by default and filters/materialises only supported Budapest hierarchy records.

This is deliberately more efficient and less brittle than crawling rendered district and street pages. The parser validates:

- JSON root shape and broad row count;
- supported Budapest hierarchy levels;
- observation-year range;
- price and transaction-count ranges;
- presence of Budapest city totals;
- presence of all 23 Budapest district totals.

Missing property fields remain absent. A live response that becomes unexpectedly small or incomplete is rejected and the previous verified local observations remain available.

## Official transaction nowcast

`analytics.py` keeps the nowcast deterministic and inspectable.

For a Budapest second-hand district/street selection it calculates:

```text
local factor
    = annual local/property-type KSH HUF/m²
      / same-year Budapest all-dwelling KSH HUF/m²

current nowcast
    = latest Budapest quarterly second-hand KSH HUF/m²
      × local factor
```

This deliberately treats the annual granular data as a relative local/property-class signal and the quarterly second-hand table as the current segment anchor.

The granular source used here does not have the same new/second-hand split, so new-build selections do not use the local factor. They remain on the directly published quarterly new-build benchmark.

Observed Duna House asking prices are not part of this formula. They are an independent comparison layer and the separation has a regression test.

See `docs/METHODOLOGY.md` for assumptions and fallback order.

## Duna House provider boundary

The Duna House provider is optional and experimental.

Before detail-page collection it checks:

- whether the provider is enabled;
- whether the manual policy review is still within its allowed age;
- whether the reviewed `robots.txt` still permits the configured property path;
- whether the configured property sitemap is still declared;
- whether the legal/policy page still passes minimum semantic checks;
- whether reviewed policy fingerprints changed.

An unexpected change pauses collection. The collector does not respond by changing identities, rotating proxies or bypassing a restriction.

The policy guard is deliberately not a readiness dependency. A public deployment must still serve official KSH/MNB functionality if the experimental asking provider pauses.

See `docs/DUNA_HOUSE_PROVIDER.md` for exact scope and limitations.

## Daily pipeline

`python -m app.cli daily` currently performs:

1. safe reference-data repair;
2. quarterly KSH price refresh;
3. KSH transaction-count refresh;
4. granular KSH client-dataset refresh if its weekly interval is due;
5. broad market-change detection/notification;
6. MNB FX refresh;
7. guarded Duna House observed-listing collection;
8. self-checks;
9. job-state persistence and optional degraded-source notification.

The core job is considered operational if quarterly KSH, transaction counts and MNB FX succeed. Granular KSH or the experimental asking provider can degrade the job without making official broad market data disappear.

## Failure model

The application distinguishes four useful failure classes.

### Hard application failure

Examples: database cannot be queried or required reference data cannot be loaded. Readiness fails and the deployment should not receive traffic.

### Core source degradation

Examples: quarterly KSH or MNB contract breaks. The source is marked degraded and previously verified observations remain in place.

### Optional source degradation

Examples: the granular KSH client dataset changes unexpectedly or the Duna House policy guard pauses collection. The affected layer becomes stale/unavailable, but the application remains usable with other evidence layers.

### Suspicious data

Examples: implausible price/m², malformed structured data or an unusually large FX jump. The observation is rejected. Self-healing never invents a replacement.

## Self-healing boundaries

Automatic repair is deliberately limited to known-safe actions:

- create required tables at startup;
- restore a missing bundled quarterly KSH reference row without replacing an existing live/revised value;
- retry clearly transient network failures a small number of times;
- release a daily-job lock left running for more than two hours;
- keep serving last verified data after source failure;
- mark disappeared observed listing URLs inactive without calling them sold;
- expose degraded/stale source and policy state through Diagnostics.

The bundled market files are bootstrap/recovery material, not an authority above live KSH. Regression tests verify that they cannot overwrite a later official revision.

Automatic code edits, schema guessing, fabricated substitute values, interpolation of missing KSH cells, automated bypass of source restrictions and acceptance of malformed external data are outside the self-healing model.

## Source-contract CI

Normal CI covers deterministic parsers, calculations, routes and a booted Docker health smoke test.

A second scheduled workflow checks live external contracts: quarterly KSH, transaction counts, granular KSH, MNB FX and a **Duna House probe** consisting of policy checks, sitemap discovery and one factual listing-page parse. Each result is collected before the workflow enforces the combined outcome so one broken source cannot hide diagnostics for another.

The live-source workflow deliberately does not bulk-collect Duna House listings.

## Notifications

Notifications are a delivery layer, not the source of truth. The database and Diagnostics page retain source state even when notification channels are disabled or a delivery fails.

The current channels are generic webhook, Telegram and SMTP email. Each configured channel is attempted independently. Credential-bearing delivery errors are sanitised before being written to notification history.

## Scaling

The default Duna House collector is bounded rather than attempting to visit every discovered detail page daily. It prioritises unseen/changed pages and gradually improves source coverage while keeping request volume controlled.

The KSH granular layer needs only one official client-dataset request per scheduled refresh and local database upserts.

This version still does not need Redis or a worker queue. If listing ingestion later grows to multiple providers, millions of rows or high-frequency refreshes, move ingestion into dedicated short-lived job services before adding queue infrastructure to the web process.

The current database job lock is sufficient for one daily collection pipeline. A multi-worker ingestion system should use a database advisory lock or a proper job queue.
