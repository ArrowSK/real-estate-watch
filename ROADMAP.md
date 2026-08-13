# Roadmap

This file separates working features from work that still needs a reliable data source, more observation history or a product decision. Missing data is not presented as a bug and an experimental source is not presented as a complete market.

## 0.2 — current Hungary evidence build

Implemented:

- FastAPI/Jinja web application with English and Hungarian interfaces;
- distinctive server-rendered market-ledger UI and original SVG icon set, with no frontend build dependency;
- HUF-first market display with MNB EUR/USD comparisons;
- official quarterly KSH completed-transaction benchmarks for Budapest, broad Hungarian regions and the national total;
- matching official KSH quarterly transaction counts;
- separate new-build and second-hand series;
- granular KSH Ingatlanadattár collection for Budapest districts and available street/property-type observations;
- property classes for all dwellings, condominium apartments, houses and panel apartments where the source supports them;
- transparent second-hand transaction-value nowcast using the annual KSH local/property-type factor and the latest official Budapest quarterly second-hand benchmark;
- experimental Duna House factual asking-market observer using sitemap discovery, bounded incremental detail-page collection and aggregate-only public presentation;
- policy guard that pauses the Duna House collector after reviewed robots/policy changes or when the dated human review expires;
- daily observed asking aggregates with median, mean, P25/P75, sample, new observations, price reductions, operational coverage and conservative confidence;
- strict separation between the official transaction nowcast and observed asking median, plus an explicit asking/transaction gap;
- granular property valuation worksheet with optional Budapest street and optional asking-price comparison;
- visible property adjustment assumptions rather than hidden coefficients;
- Hungarian annuity mortgage and stress calculator;
- MNB HFM/JTM regulatory screen and general NAV transfer-tax calculation;
- PostgreSQL/SQLite persistence;
- Docker, Docker Compose and Railway deployment support;
- daily collection command and optional local scheduler;
- webhook, Telegram and SMTP email notifications;
- diagnostics for self-checks, source health, provider-policy state and recent jobs;
- bounded retries, source-health/freshness checks, last-known-good fallbacks and safe reference-data repair;
- normal GitHub Actions tests and Docker readiness smoke test;
- scheduled live source-contract checks for quarterly KSH, granular KSH, MNB FX and a non-bulk Duna House probe.

## Next — build asking-market history and measure representativeness

The Duna House observer starts collecting history only from the date a deployment enables it. It cannot manufacture six months of past daily asking prices.

The next analytical work should be based on accumulated observations rather than more scraping volume:

1. measure how quickly the bounded collector reaches stable coverage of the source sitemap;
2. separate stock median (all currently observed active listings) from flow median (newly observed listings);
3. quantify how sensitive the median is to property mix and source coverage;
4. add first-seen cohort charts and observed price-cut rates once enough history exists;
5. detect likely duplicate advertisements using factual fields without exposing source content;
6. add source-specific outlier diagnostics and sample-change alarms;
7. compare observed Duna House geography/property composition with official KSH transaction composition where comparable;
8. keep `removed` strictly separate from `sold` unless a future source supplies positive completion evidence.

A second lawful asking-market provider would be useful for representativeness and cross-source comparison, but it should be added only after the same source-access review used for Duna House.

## Next — calibrated valuation model

The property-condition coefficients remain transparent fallback assumptions, not a trained hedonic model.

The new official local KSH layer gives a better baseline, but the next valuation phase should wait for enough microdata/history to estimate effects defensibly:

- estimate local coefficients by geography and property class;
- distinguish building/location effects from listing-price effects;
- keep sample size and uncertainty with every coefficient;
- shrink or suppress estimates when data are weak;
- validate on a hold-out time period;
- version model methodology so historical outputs remain explainable;
- keep the plain-language adjustment trail in the UI.

The observed asking median should remain an independent comparison even after a better valuation model exists.

## Next — current mortgage products

Investigate a documented or otherwise maintainable data interface for current Hungarian products. The official MNB product finder and Certified Consumer-Friendly Housing Loan calculator are the preferred starting points, but the provider must not depend on a brittle undocumented private endpoint.

A product record should include at least:

- institution and product name;
- interest rate and THM/APR;
- fixed-rate period;
- permitted amount and term;
- eligibility information that can be represented reliably;
- source URL and source update date;
- last successful collection date.

Only then should the UI label a result as a current bank-product comparison.

## Next — acquisition-cost detail

Add only costs that can be sourced or entered explicitly: lawyer fee, valuation fee, bank charges, insurance and fact-specific tax reliefs. Do not silently assume a generic percentage where Hungarian practice varies by provider or transaction.

## Next — watchlists and user ownership

The application can notify on changes in supported benchmark series. Personal saved watchlists require an ownership model before a public deployment accepts arbitrary persistent user data.

Design this before adding public write endpoints:

- single-user/private deployment mode versus multi-user hosted mode;
- authentication and account recovery;
- per-user notification destinations;
- saved areas, property filters and thresholds;
- rate limiting and abuse protection;
- deletion/export of user data.

Desired watch conditions include market movement, mortgage-rate movement, new observed properties below a chosen HUF/m² threshold and a source listing materially below the app's adjusted estimate.

## Database migrations before destructive schema change

Version 0.2 adds new tables but does not alter existing production columns, so the current direct table-creation path remains safe for this release.

Before an update needs to rename/drop/change an existing column, before account data is introduced, or before multi-country data materially changes the schema, add Alembic migrations and a tested upgrade/rollback path. Production data must never depend on dropping and recreating tables during an application update.

## Additional countries

Do not add a country merely to populate a dropdown. A new country should have, at minimum:

- local-currency and geography provider;
- official transaction-market source;
- any asking-market source clearly separated from transaction data;
- source-access review and automatic stop boundary for non-open sources;
- local mortgage and affordability rules;
- local acquisition-tax/cost rules;
- source-health checks;
- translations where needed;
- tests for date-sensitive regulation and source parsing.

The second country should also be used to extract genuine common provider interfaces. Country-neutral abstractions should come from two working implementations rather than assumptions about markets that have not been built yet.
