# Architecture

## Design goals

Real Estate Watch should remain inexpensive to run, understandable to maintain, explicit about provenance and conservative when external data fail.

The application uses one web process and one relational database. Data collection runs as short-lived commands. Railway can run the daily command as a Cron Job; Docker users can enable the scheduler profile or call the same command from an existing scheduler.

Version 0.2.1 adds live/local analytical depth without adding Redis, a message broker, a JavaScript framework or a permanent worker.

## Request and data flow

```text
                          ┌──────────────────────┐
                          │      FastAPI UI      │
                          │  HTML + small JS     │
                          └──────────┬───────────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              │                      │                      │
         Market / Value         Live Asking          Local Evidence
              │                      │                      │
        analytics.py          live_intelligence.py    live_intelligence.py
              │                      │                      │
      ┌───────┴────────┐             │              ┌───────┴─────────┐
      │                │             │              │                 │
 KSH quarterly   KSH Ingatlan-  Duna House     KSH local rows   KSH city factor
 price + counts   adattár JSON    observer
      │                │             │
      └────────────────┴─────────────┴──────────────────────┐
                                                           │
                                                       SQLAlchemy
                                                           │
                                                 SQLite / PostgreSQL
```

MNB FX, mortgage regulation and NAV transaction-cost rules are separate financial inputs. They do not alter the identity of the market datasets.

## Web layer

`app/main.py` contains FastAPI routes and renders Jinja templates. The browser receives ordinary HTML, an original SVG icon set, one stylesheet and a small JavaScript chart renderer. There is no separate frontend build pipeline.

The main workspaces are:

- `/` — broad transaction/asking comparison;
- `/live` — observed asking intelligence, including postcode drill-down and longitudinal local signals;
- `/local` — KSH district/street evidence and factor-based current estimates;
- `/valuation` — property-specific estimate from the official transaction baseline plus visible adjustments;
- `/mortgage` — affordability/regulatory calculator;
- `/diagnostics` — source, policy and self-check state.

The asking figure is never blended into the official transaction nowcast.

## Service layer

`app/services/` contains collection, analytics and operational safeguards.

Important modules:

- `market.py` — quarterly KSH completed-transaction mean HUF/m²;
- `transaction_counts.py` — matching KSH quarterly transaction counts;
- `ksh_local.py` — KSH Ingatlanadattár client JSON normalisation for Budapest city/district/street/property class;
- `duna_house.py` — experimental factual listing observer, policy guard, presence state and asking-market aggregates;
- `analytics.py` — official local-factor nowcast and asking/transaction comparison;
- `live_intelligence.py` — derived asking signals, postcode views, structured-field coverage and direct local street/district evidence;
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

The Hungary implementation is in `app/countries/hu/` and defines the country descriptor, Budapest districts and broad KSH statistical areas, HFM/JTM rules and general transfer-tax logic.

A future country should provide at least:

- country descriptor and local currency;
- geography provider;
- official transaction-market provider;
- optional asking-market providers;
- mortgage/regulatory rules;
- transaction-cost rules;
- source-specific compliance/review boundary;
- translations for country-specific labels where needed.

The second country should be used to extract genuinely common provider interfaces rather than inventing abstractions before two implementations exist.

## Persistence

SQLAlchemy supports SQLite for development and PostgreSQL for production.

Current tables:

- `market_snapshots` — quarterly official completed-transaction price series;
- `local_benchmarks` — annual granular KSH Budapest city/district/street/property-class observations;
- `observed_listings` — minimal factual listing identity;
- `listing_snapshots` — daily factual price/area observations;
- `asking_market_snapshots` — publishable daily source aggregates, including postcode groups when sample size permits;
- `observed_listing_presence` — consecutive sitemap-miss and recovery state;
- `observed_listing_attributes` — optional short factual building/property attributes;
- `provider_policy_state` — dated source-review status and policy fingerprints;
- `fx_snapshots`;
- `source_health`;
- `job_runs`;
- `notification_events`.

### Additive schema strategy

The reconciliation deliberately **does not add new columns to `observed_listings`**. Presence state and richer factual attributes use new tables keyed by listing ID.

That is important because current deployments still use `Base.metadata.create_all()` on startup. Creating an additional table is safe under that model; expecting `create_all()` to rewrite an existing production table is not.

This direct-create approach should not be stretched indefinitely. Before existing production columns need to change, before user accounts are added, or before another country introduces material schema evolution, the project should add versioned database migrations.

### Why factual listing observations are stored

Daily aggregates alone would make it impossible to identify observed price changes, avoid counting a listing twice on one day or rebuild an aggregate after a methodology correction.

The app therefore stores a deliberately minimal listing identity and daily factual snapshot. Short structured facts are isolated in a separate table. It does not store source descriptions, photographs or contact data. Individual observed listings are not exposed through a public browsing endpoint.

## Granular KSH ingestion

KSH's public Ingatlanadattár frontend currently loads a single official client dataset from `inga-data.json`. The application retrieves that dataset at a weekly interval by default and filters/materialises only supported Budapest hierarchy records.

The parser validates:

- JSON root shape and broad row count;
- supported Budapest hierarchy levels;
- observation-year range;
- price and transaction-count ranges;
- presence of Budapest city totals;
- presence of all 23 Budapest district totals.

Missing property fields remain absent. A live response that becomes unexpectedly small or incomplete is rejected and previous verified local observations remain available.

## Official transaction nowcast

For a Budapest second-hand district/street selection:

```text
local factor
    = annual local/property-type KSH HUF/m²
      / same-year Budapest all-dwelling KSH HUF/m²

current nowcast
    = latest Budapest quarterly second-hand KSH HUF/m²
      × local factor
```

The granular source does not have the same new/second-hand split, so new-build selections do not use the local factor. They remain on the directly published quarterly new-build benchmark.

Observed Duna House asking prices are not part of this formula. Regression tests protect that boundary.

## Live intelligence layer

`live_intelligence.py` is intentionally a derived-data service, not another source collector.

It reads the already persisted factual observations to calculate:

- latest observed asking aggregate;
- postcode options and postcode aggregate history;
- price-cut share from first locally observed price to latest locally observed price;
- median observed reduction among listings with a cut;
- first-seen counts for today and the last seven days;
- median elapsed days since local first observation;
- short factual-attribute coverage;
- district/street KSH rows with current local-factor estimates.

Keeping this logic separate from `duna_house.py` matters: collection decides what facts can safely be accepted; live intelligence decides how accepted facts are analysed.

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

## Presence-state self-healing

Sitemap absence is handled as a small state machine rather than a one-shot deletion signal.

Default behaviour:

```text
present -> active, miss count 0
one miss -> still active, pending absence
second miss -> inactive
reappears -> active, miss count reset
```

The threshold is configured by `DH_INACTIVE_AFTER_MISSES`.

This prevents one transient sitemap inconsistency from immediately removing a listing from the observed stock. It does not infer a sale. “Inactive” means only “absent from the eligible source discovery set for the configured number of consecutive observations”.

## Daily pipeline

`python -m app.cli daily` currently performs:

1. safe reference-data repair;
2. quarterly KSH price refresh;
3. KSH transaction-count refresh;
4. granular KSH client-dataset refresh if its weekly interval is due;
5. broad market-change detection/notification;
6. MNB FX refresh;
7. guarded Duna House observed-listing collection and aggregate rebuild;
8. self-checks;
9. job-state persistence and optional degraded-source notification.

The core job is considered operational if quarterly KSH, transaction counts and MNB FX succeed. Granular KSH or the experimental asking provider can degrade the job without making official broad market data disappear.

## Failure model

### Hard application failure

Database cannot be queried or required reference data cannot be loaded. Readiness fails.

### Core source degradation

Quarterly KSH or MNB contract breaks. Previously verified observations remain in place.

### Optional source degradation

Granular KSH changes unexpectedly or the Duna House policy guard pauses collection. The affected layer becomes stale/unavailable while other evidence remains usable.

### Suspicious data

Implausible price/m², malformed structured data or an unusually large FX jump. The observation is rejected. Self-healing never invents a replacement.

## Self-healing boundaries

Automatic repair is limited to known-safe actions:

- create required additive tables at startup;
- restore a missing bundled quarterly KSH reference row without replacing an existing live/revised value;
- retry clearly transient network failures a small number of times;
- release a daily-job lock left running for more than two hours;
- keep serving last verified data after source failure;
- tolerate a configured number of temporary sitemap absences;
- reactivate an observed listing when it reappears;
- expose degraded/stale source and policy state through Diagnostics.

Automatic code edits, schema guessing, fabricated substitute values, interpolation of missing KSH cells, automated bypass of source restrictions and acceptance of malformed external data are outside the self-healing model.

## Source-contract CI

Normal CI covers deterministic parsers, calculations, routes and a booted Docker health smoke test.

A second scheduled workflow checks live external contracts: quarterly KSH, transaction counts, granular KSH, MNB FX and a **Duna House probe** consisting of policy checks, sitemap discovery and one factual residential listing-page parse.

The live-source workflow deliberately does not bulk-collect Duna House listings.

## Scaling

The default Duna House collector is bounded rather than attempting to visit every discovered detail page daily. It prioritises unseen/changed pages and gradually improves source coverage while keeping request volume controlled.

The KSH granular layer needs only one official client-dataset request per scheduled refresh and local database upserts.

This version still does not need Redis or a worker queue. If listing ingestion later grows to multiple providers, millions of rows or high-frequency refreshes, move ingestion into dedicated short-lived job services before adding queue infrastructure to the web process.
