# Architecture

## Design goals

Real Estate Watch should remain inexpensive to run, understandable to maintain and conservative when external data fail.

The application uses one web process and one relational database. Data collection is a short-lived command. Railway can run that command as a Cron Job; Docker users can enable the small scheduler profile or call the command from an existing scheduler.

## Layers

### Web layer

`app/main.py` contains FastAPI routes and renders Jinja templates. The browser receives ordinary HTML, a small stylesheet and a small JavaScript file used for the market chart. There is no separate frontend build pipeline.

### Service layer

`app/services/` contains market collection, FX collection, valuation, mortgage calculations, notifications, source health, job locking and self-healing.

A collector must not silently overwrite good data after a malformed response. Parsing and validation happen before the database transaction is committed.

### Country layer

`app/countries/` contains country-specific naming, tax and regulatory rules.

The Hungary implementation is in `app/countries/hu/`.

A future country should provide at least:

- country descriptor and local currency;
- geography list or geography provider;
- market provider(s);
- mortgage/regulatory rules;
- transaction-cost rules;
- translations for country-specific labels where needed.

Global web routes should not contain a growing list of `if country == ...` branches.

### Persistence

SQLAlchemy supports SQLite for development and PostgreSQL for production.

Current tables:

- `market_snapshots`
- `fx_snapshots`
- `source_health`
- `job_runs`
- `notification_events`

Market and FX observations have uniqueness constraints so that rerunning a collector is idempotent rather than producing duplicate history.

## Failure model

The application distinguishes three kinds of failure.

### Hard application failure

Examples: database cannot be queried; schema cannot be created. Readiness fails and the deployment should not receive traffic.

### Source degradation

Examples: KSH timeout, MNB response change, invalid FX value. The source is marked degraded, last known-good data remain visible and readiness stays up.

### Suspicious data

Values outside broad safety ranges, or an unusually large FX jump, are rejected. The app does not "self-heal" by guessing a replacement value.

## Self-healing boundaries

Automatic repair is deliberately limited to known-safe actions:

- recreate database tables if they do not exist;
- restore bundled reference market rows if the market table is empty;
- release a daily-job lock that has been left running for more than two hours;
- keep serving the last verified data after source failure.

Automatic code edits, schema guessing and acceptance of malformed external data are outside the self-healing model.

## Scaling

The first version does not need Redis or a worker queue. If collection later expands to millions of listings, move listing ingestion to a dedicated job service before adding infrastructure to the web process.

The `daily_collection` database lock is enough for the current single daily job. A future multi-worker ingestion system should use a database advisory lock or a proper job queue.
