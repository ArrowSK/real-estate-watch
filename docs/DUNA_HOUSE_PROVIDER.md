# Duna House observed asking-market provider

Real Estate Watch treats Duna House as an **experimental observed-market source**, not as an open-data feed and not as a substitute for KSH completed-transaction statistics.

This distinction matters. The public website can be reached by ordinary crawlers and, at the time of the project's manual review on 13 August 2026, its `robots.txt` allowed crawling and declared a dedicated property sitemap. That is useful evidence about technical access. It is **not** a licence granting unrestricted database reuse.

The provider is therefore intentionally narrow, conservative and easy to disable.

## What the collector stores

For each observed listing the application may store only factual fields required to calculate market statistics:

- source listing reference number;
- canonical listing URL;
- first-seen and last-seen timestamps;
- source `lastmod` timestamp when the sitemap supplies one;
- active/inactive observation state;
- locality, postcode and derived Budapest district where available;
- broad property class such as apartment or house;
- new/second-hand classification when it can be determined without guessing;
- room count where available;
- asking price;
- floor area;
- calculated asking price per square metre.

The provider does **not** store listing descriptions, photographs, plans, agent biographies, seller names, telephone numbers, email addresses or other contact data. The application also does not expose an endpoint for browsing a reconstructed copy of Duna House's individual listings.

The public product uses these observations to create daily aggregates: sample size, median and mean HUF/m², P25/P75, new observations and observed price reductions.

## Discovery and request behaviour

Discovery uses the property sitemap declared by Duna House. Search-engine result pages are not used as the market dataset.

A normal run:

1. checks the provider policy guard;
2. retrieves the property sitemap;
3. compares sitemap URLs with previously observed listing identities;
4. prioritises unseen URLs, then URLs whose sitemap `lastmod` advanced, then the oldest observed pages;
5. visits no more than `DH_MAX_LISTINGS_PER_RUN` detail pages;
6. waits at least `DH_REQUEST_DELAY_SECONDS` between detail-page requests;
7. parses structured data first and uses narrow visible-text fallbacks only for factual fields;
8. validates price, area and price/m² ranges before writing;
9. creates at most one price/area snapshot for a listing per calendar day;
10. rebuilds publishable aggregates only where the configured minimum sample is met.

The defaults are 250 detail pages per run, a 0.20-second delay, and a minimum aggregate sample of 12. These values can be made more conservative by deployment configuration.

The collector has bounded network retries. It does not respond to blocks by rotating identities, bypassing anti-bot controls or increasing request pressure.

## Policy guard

Before the listing collector runs, `check_dh_policy()` fetches the reviewed `robots.txt` and legal/policy page.

The guard checks several things:

- the reviewed property path remains crawlable for the project's user agent;
- the configured property sitemap is still declared;
- the legal/policy body is large enough to look like the expected document rather than an error page;
- a small set of explicit automated-collection prohibition patterns has not appeared;
- fingerprints of the reviewed robots and policy bodies have not changed unexpectedly;
- the manual review date embedded in the provider has not become older than `DH_POLICY_REVIEW_MAX_AGE_DAYS`.

If the fingerprint changes, the collector pauses. A maintainer must review the changed source material and explicitly advance `DH_POLICY_REVIEWED_ON` in code before the new fingerprint is accepted. If the review simply becomes too old, collection also pauses.

This is intentionally inconvenient. A provider silently continuing after its access conditions change would be a worse failure mode.

### Fresh-install limitation

The first run of a fresh database records the current policy fingerprints after the semantic guard checks pass. The source code still contains the dated human review boundary, so the provider expires automatically, but a fingerprint alone cannot establish legal permission.

The guard is a technical safety mechanism, not legal advice. It cannot turn a public website into open data and it cannot guarantee that every possible right or contractual issue has been identified.

## `removed` does not mean `sold`

When a previously observed URL disappears from the property sitemap, Real Estate Watch marks the observation inactive. It does not label the property sold.

A listing can disappear because it was sold, withdrawn, duplicated, replaced, temporarily unpublished, moved to another URL or removed for another reason. Any future sold-status model must use separate evidence and must never infer a completed transaction merely from disappearance.

## Aggregate scope

Duna House aggregates are labelled `observed_subset` in storage and shown as an observed Duna House subset in the UI.

They answer a limited question:

> What do the residential listings that this application successfully observed on this source look like today?

They do not answer:

> What is the median asking price of every active property in Hungary?

Coverage is measured against the source's current property-sitemap discovery count where possible. Confidence remains deliberately conservative and depends on both usable sample size and observed coverage.

An observed asking median is never silently fed into the official transaction-value nowcast. The two series are shown side by side and their gap is calculated explicitly.

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
