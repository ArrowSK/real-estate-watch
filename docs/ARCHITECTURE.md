# Architecture

## Design goals

Real Estate Watch should remain inexpensive to run, understandable to maintain and conservative when external data fail.

The application uses one web process and one relational database. Data collection is a short-lived command. Railway can run that command as a Cron Job; Docker users can enable the small scheduler profile or call the command from an existing scheduler.

## Layers

### Web layer

`app/main.py` contains FastAPI routes and renders Jinja templates. The browser receives ordinary HTML, a small stylesheet and a small JavaScript file used for the market chart. There is no separate frontend build pipeline.

### Service layer

`app/services/` contains market collection, FX collection, valuation, mortgage calculations, notifications, source health, bounded HTTP retry, job locking and self-healing.

A collector must not silently overwrite good data after a malformed response. Parsing and validation happen before the database transaction is committed. Only clearly transient network/HTTP failures are retried; an invalid payload is treated as a source problem rather than retried until it happens to parse.

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

Global web routes should not contain a growing list of `if country == ...` branches. The current release is intentionally Hungary-first; further country-neutralisation should happen as the second country is implemented, when the common interface can be based on two real providers rather than guessed in advance.

### Persistence

SQLAlchemy supports SQLite for development and PostgreSQL for production.

Current tables:

- `market_snapshots`
- `fx_snapshots`
- `source_health`
- `job_runs`
- `notification_events`

Market and FX observations have uniqueness constraints so that rerunning a collector is idempotent rather than producing duplicate history.

The initial schema is small enough to create directly. Before listing history, user accounts or multiple countries materially expand the database, add versioned migrations rather than relying on table creation alone.

## Failure model

The application distinguishes three kinds of failure.

### Hard application failure

Examples: database cannot be queried; schema cannot be created. Readiness fails and the deployment should not receive traffic.

### Source degradation

Examples: KSH timeout, MNB response change, invalid FX value. Clearly transient failures receive a short bounded retry. If the source still fails, it is marked degraded, last known-good data remain visible and readiness stays up.

### Suspicious data

Values outside broad safety ranges, or an unusually large FX jump, are rejected. The app does not "self-heal" by guessing a replacement value.

## Self-healing boundaries

Automatic repair is deliberately limited to known-safe actions:

- create required database tables when the application starts;
- restore a missing bundled KSH reference row without replacing an existing live/revised KSH value;
- retry clearly transient network failures a small number of times;
- release a daily-job lock that has been left running for more than two hours;
- keep serving the last verified data after source failure;
- expose degraded/stale source state through diagnostics instead of hiding it.

The bundled market files are bootstrap/recovery material, not an authority above live KSH. This is enforced in code and regression tests: startup and self-healing may fill a missing row, but must never overwrite a stored official revision.

Automatic code edits, schema guessing, fabricated substitute values and acceptance of malformed external data are outside the self-healing model.

## Notifications

Notifications are a delivery layer, not the source of truth. The database and Diagnostics page retain source state even when all notification channels are disabled or a delivery fails.

The current channels are generic webhook, Telegram and SMTP email. Each configured channel is attempted independently so that, for example, a Telegram outage does not prevent email delivery. Credential-bearing delivery errors are deliberately sanitised before being written to notification history.

## Scaling

The first version does not need Redis or a worker queue. If collection later expands to millions of listings, move listing ingestion to a dedicated job service before adding infrastructure to the web process.

The `daily_collection` database lock is enough for the current single daily job. A future multi-worker ingestion system should use a database advisory lock or a proper job queue.
