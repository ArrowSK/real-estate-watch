# Duna House observed asking-market provider

Real Estate Watch treats Duna House as an **experimental observed-market source**, not as an open-data feed and not as a substitute for KSH completed-transaction statistics.

This distinction matters. The public website can be reached by ordinary crawlers and, at the time of the project's manual review on 13 August 2026, its `robots.txt` allowed crawling and declared a dedicated property sitemap. That is useful evidence about technical access. It is **not** a licence granting unrestricted database reuse.

The provider is therefore intentionally narrow, conservative and easy to disable.

## Residential scope

The source property sitemap contains more than residential dwellings. It also exposes categories such as general-purpose property, commercial space, storage and hospitality. A raw median across that sitemap would therefore be analytically wrong even if every page parsed correctly.

The observer restricts collection to Duna House reference families that the reviewed pages use consistently for residential dwellings:

- `LK` — apartment/lakás;
- `HZ` and the legacy/general `H` house prefix — house.

Other source reference families are ignored. A project, commercial or mixed-use reference does not enter a residential aggregate merely because its page contains a price and an area.

This is fail-closed. If the source introduces another residential reference family, it must be reviewed and covered by tests before being added.

## What the collector stores

For each observed residential listing, the core identity/snapshot layer may store only factual fields needed for market analysis:

- source listing reference number;
- canonical listing URL;
- first-seen and last-seen timestamps;
- source `lastmod` timestamp when supplied by the sitemap;
- active/inactive observation state;
- locality, postcode and derived Budapest district where available;
- broad property class: apartment or house;
- new/second-hand classification when determinable without guessing;
- room count where available;
- asking price;
- floor area;
- calculated asking price per square metre.

Version 0.2.1 also has an **additive factual-attribute table**. When a short explicitly labelled value is present, the parser may retain:

- building type/construction;
- condition;
- construction year;
- floor;
- lift;
- balcony/terrace;
- view;
- orientation;
- heating;
- energy rating;
- a short source status flag such as an observed price-drop label.

These fields are deliberately separate from the core listing identity. They are currently used to measure structured-data coverage, not to train or silently alter the property valuation model.

The provider does **not** store listing descriptions, photographs, plans, agent biographies, seller names, telephone numbers, email addresses or other contact data. The application also does not expose an endpoint for browsing a reconstructed copy of Duna House's individual listings.

## Discovery and request behaviour

Discovery uses the property sitemap declared by Duna House. Search-engine result pages are not used as the market dataset.

A normal run:

1. checks the provider policy guard;
2. retrieves the property sitemap;
3. filters discovery to reviewed residential reference families;
4. compares those URLs with previously observed listing identities;
5. updates presence state for already observed URLs;
6. prioritises unseen URLs, then URLs whose sitemap `lastmod` advanced, then the oldest observed pages;
7. visits no more than `DH_MAX_LISTINGS_PER_RUN` detail pages;
8. waits at least `DH_REQUEST_DELAY_SECONDS` between detail-page requests;
9. parses structured data first and uses narrow visible-text fallbacks only for factual fields;
10. validates residential class, price, area and price/m² ranges before writing;
11. creates at most one price/area snapshot for a listing per calendar day;
12. updates the optional factual-attribute table;
13. rebuilds publishable aggregates only where the configured minimum sample is met.

The defaults are 250 detail pages per run, a 0.20-second delay, and a minimum aggregate sample of 12. These can be made more conservative by deployment configuration.

The collector has bounded network retries. It does not respond to blocks by rotating identities, bypassing anti-bot controls or increasing request pressure.

## Presence state and self-healing

The former feature branch contained a useful safeguard: a listing should not become inactive merely because it is absent from one sitemap fetch. Version 0.2.1 keeps that idea but implements it in a separate additive `observed_listing_presence` table so existing installations do not need a risky rewrite of the core listing table.

Default state transition:

```text
observed in sitemap
    -> active
    -> miss count 0

first consecutive absence
    -> remain active
    -> miss count 1
    -> missing_since recorded

second consecutive absence (default)
    -> inactive
    -> inactive_at recorded

reappears later
    -> active again
    -> miss count reset to 0
    -> missing/inactive timestamps cleared
```

The threshold is configured by `DH_INACTIVE_AFTER_MISSES` and defaults to `2`.

This is a small self-healing mechanism for transient source/sitemap inconsistency. It is not an attempt to infer transaction outcomes.

## `removed` does not mean `sold`

An inactive observation means only that the listing has crossed the configured consecutive-absence threshold in the eligible source discovery set.

A listing can disappear because it was sold, withdrawn, duplicated, replaced, temporarily unpublished, moved to another URL or removed for another reason. The application never converts disappearance into a completed transaction. Any future sold-status model must use separate positive evidence.

## Policy guard

Before collection, `check_dh_policy()` fetches the reviewed `robots.txt` and legal/policy page.

The guard checks:

- the reviewed property path remains crawlable for the project's user agent;
- the configured property sitemap is still declared, including legal whitespace around the `Sitemap:` directive;
- the legal/policy body is large enough to resemble the expected document rather than an error page;
- a small set of explicit automated-collection prohibition patterns has not appeared;
- fingerprints of the reviewed robots and policy bodies have not changed unexpectedly;
- the manual review date embedded in the provider has not become older than `DH_POLICY_REVIEW_MAX_AGE_DAYS`.

If a reviewed fingerprint changes, the collector pauses. A maintainer must inspect the source material and explicitly advance the dated review in code before collection is accepted again. If the review simply becomes too old, collection also pauses.

The policy guard is a technical safety mechanism, not legal advice. It cannot turn a public website into open data and it cannot guarantee that every possible right or contractual issue has been identified.

## Aggregate scope

Duna House aggregates are labelled `observed_subset` in storage and in the UI.

They answer a limited question:

> What do the residential listings that this deployment successfully observed on this source look like now?

They do not answer:

> What is the median asking price of every active property in Hungary?

Aggregates can be built for the source area, Budapest, a Budapest district and — once the minimum sample is met — a postcode. Postcode aggregation is a drill-down of the same observed source subset; it does not imply greater market representativeness.

The operational coverage ratio is calculated against the eligible residential URLs discovered in the current source sitemap. It is not Duna House market share and not coverage of all Hungarian listings.

Confidence remains deliberately conservative and depends on usable sample size and source-observation coverage.

## Live intelligence metrics

The dedicated `/live` page reconciles several useful ideas from the former feature branch with the current source model.

### Observed price-cut share

The live signal compares the latest locally stored asking price with the **first price observed by this deployment** for each currently usable listing.

```text
price-cut share
    = active usable listings whose latest observed price
      is lower than their first observed price
      / active usable listings in the selected subset
```

The median cut is calculated across those observed reductions.

This is not the same as a source-provided lifetime price history: a reduction that happened before this deployment first saw a listing is unknown.

### New observations

`new_7d_count` means listings first seen by this deployment during the last seven days. It is not necessarily the source's publication-date count.

### Median observed days

The application reports the median elapsed time from local `first_seen_at` to now for the currently observed subset. The UI deliberately calls this **observed days**, not days-on-market.

### Structured factual coverage

The Live view reports two separate completeness measures:

- share of usable active listings for which at least one supported short factual attribute was parsed;
- populated supported attribute fields divided by all supported fields across the selected usable sample.

These are parser/data-availability measures. They are not measures of valuation-model quality.

## Source-contract probe

The scheduled source-contract job does not run the production bulk collection merely to test upstream compatibility. It checks the policy guard, discovers the sitemap and tries a bounded group of recent **residential** URLs until it obtains one valid factual parse.

The probe reports only factual parser status such as source reference, area class and whether required numeric fields were found. It does not print or retain descriptions or contact details.

## Operational commands

Probe the source contract without bulk collection:

```bash
python -m app.cli probe-dh
```

Run a deliberately small collection during development:

```bash
python -m app.cli collect-dh --limit 20
```

Run the configured normal collector:

```bash
python -m app.cli collect-dh
```

The scheduled GitHub source-contract workflow uses `probe-dh`; CI does not bulk-collect listings.

## When the provider must remain disabled

Set `DH_ENABLED=false` if the deployment owner is not comfortable running the experimental observer, if the source's access conditions become unclear, or while a policy change is under review.

The rest of Real Estate Watch remains functional with KSH and MNB data. A live asking-market feed is an optional evidence layer, not a dependency required for the application to start.
