# Roadmap

This file separates the working first release from features that still need a reliable data source or a product decision. It is deliberately specific so that missing features do not get confused with bugs.

## 0.1 — current Hungary foundation

Implemented:

- FastAPI/Jinja web application with English and Hungarian interfaces;
- HUF-first market display with optional MNB EUR/USD comparisons;
- official KSH transaction-price benchmarks for Budapest, broad Hungarian regions and the national total;
- separate new-build and second-hand series;
- property adjustment worksheet with visible placeholder coefficients;
- Hungarian annuity mortgage and stress calculator;
- MNB HFM/JTM regulatory screen and general NAV transfer-tax calculation;
- PostgreSQL/SQLite persistence;
- Docker, Docker Compose and Railway deployment support;
- daily collection command and optional local scheduler;
- webhook, Telegram and SMTP email notifications;
- diagnostics, bounded retries, source-health/freshness checks, last-known-good fallbacks and safe reference-data repair;
- GitHub Actions tests plus a booted-container readiness smoke test.

## Next — live Hungarian asking market

This is the most important missing data layer.

Before implementation, select a listing source that is lawful to use, stable enough for a daily service and capable of providing the fields needed for comparison. Do not build the production application around a brittle undocumented scrape merely to obtain more numbers quickly.

Once a suitable source exists:

1. store listing identity, URL/source identity, first seen, last seen and asking-price history;
2. normalise property type, area, floor, condition, lift, balcony, orientation and other useful attributes;
3. detect likely duplicate advertisements for the same property;
4. calculate median and mean asking price per m² separately from transaction benchmarks;
5. measure inventory, new listings, days on market and price reductions;
6. add district/city/neighbourhood geography only where the source genuinely supports that resolution;
7. retain daily snapshots so six-month and one-year asking-market charts become our own consistent history.

## Next — current mortgage products

Investigate a documented or otherwise maintainable data interface for current Hungarian products. The official MNB product finder and Certified Consumer-Friendly Housing Loan calculator are the preferred starting points, but the production provider should not depend on an undocumented private endpoint.

A product record should include at least:

- institution and product name;
- interest rate and THM/APR;
- fixed-rate period;
- permitted amount and term;
- eligibility information that can be represented reliably;
- source URL and source update date;
- last successful collection date.

Only then should the UI label a result as a current product comparison.

## Next — watchlists and user ownership

The first release can notify on changes in supported benchmark series. Personal watchlists require an ownership model before the public app allows arbitrary users to create persistent data.

Design this before adding public write endpoints:

- single-user/private deployment mode versus multi-user hosted mode;
- authentication and account recovery;
- per-user notification destinations;
- saved areas, property filters and thresholds;
- rate limiting and abuse protection;
- deletion/export of user data.

Desired watch conditions include market movement, mortgage-rate movement, a newly listed property below a chosen HUF/m² threshold and a listing materially below the app's adjusted estimate.

## Next — calibrated valuation model

The visible fixed coefficients in 0.1 are placeholders, not a trained valuation model.

After enough listing or transaction microdata exist:

- estimate local coefficients by geography and property class;
- keep sample size and confidence with every coefficient;
- shrink or suppress estimates when data are weak;
- validate on a hold-out period;
- compare predicted values with later asking-price changes and completed transactions where available;
- keep a plain-language explanation of every adjustment in the UI.

## Next — acquisition-cost detail

Add only costs that can be sourced or entered explicitly, for example lawyer fees, valuation fees, bank charges, insurance and fact-specific tax reliefs. Do not silently assume a generic percentage where Hungarian practice varies by provider or transaction.

## Before schema growth

The initial release can create its small schema directly. Before listing history, users or multi-country data materially expand the database, add Alembic migrations and a tested upgrade path. Production data should never depend on dropping and recreating tables during an application update.

## Additional countries

Do not add a country merely to populate a country dropdown. A new country should have, at minimum:

- a local-currency and geography provider;
- a documented market-data source and clear distinction between asking and transaction data;
- local mortgage and affordability rules;
- local acquisition-tax/cost rules;
- source-health checks;
- interface translations where needed;
- tests for date-sensitive regulation and source parsing.

The shared application should remain country-neutral; local legal, market and product rules belong in country modules.
