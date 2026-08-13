# Methodology

Real Estate Watch is built around one rule: numbers that answer different questions must not be collapsed into one vaguely labelled "market price".

For Hungary, version 0.2.1 keeps five analytical layers separate.

## 1. Quarterly completed-transaction benchmark

The broad official market layer comes from KSH STADAT housing-price tables. It is a quarterly **mean completed-transaction price per square metre**, split between second-hand and new dwellings.

This is the most current broad transaction benchmark used by the application. It is not a current asking-price median and it is not property-specific.

Transaction counts come from the matching KSH table and are attached only where period, geography and market segment match the stored price observation.

## 2. Granular local completed-transaction benchmark

KSH Ingatlanadattár supplies a separate annual layer with finer geography and broad dwelling-type fields.

The public KSH frontend currently loads its data from the official client dataset:

`https://www.ksh.hu/s/ingatlanadattar/inga-data.json`

Real Estate Watch downloads that dataset at the configured granular refresh interval and materialises only the Budapest records it needs. It does not crawl thousands of KSH street pages.

The current client dataset exposes Budapest city totals, 23 district totals and street observations, with annual fields for:

- family houses;
- multi-unit condominium dwellings;
- panel dwellings;
- all dwellings;
- transaction count where published;
- relative dispersion where published.

The collector converts KSH's thousand-HUF/m² values to HUF/m² and stores the source year and source page reference. Missing published values remain missing; the collector does not interpolate them.

The granular source is annual and, in the dataset used by this build, does **not** provide the same new/second-hand split as the quarterly STADAT series. That limitation determines how it is used.

## 3. Current transaction-value nowcast

For a Budapest **second-hand** property, the app uses the granular annual source as a local/property-type factor rather than pretending it is a current second-hand observation.

For a local observation from year `Y`:

```text
local/property-type factor
    = selected local KSH annual HUF/m²
      / Budapest all-dwelling KSH annual HUF/m² for the same year

current transaction-value nowcast
    = latest Budapest quarterly SECOND-HAND KSH mean HUF/m²
      × local/property-type factor
```

Illustrative structure only:

```text
2024 District VI condominium mean              1,500,000 HUF/m²
2024 Budapest all-dwelling mean                1,000,000 HUF/m²
Local/property-type factor                           1.50×
Latest Budapest second-hand quarterly mean      1,200,000 HUF/m²
                                                    ─────
Current transaction-value nowcast               1,800,000 HUF/m²
```

This is deliberately a **nowcast**, not a directly observed current district or street sale price. It assumes the annual local/property-type relationship to the Budapest market remains informative when applied to the latest broad second-hand transaction benchmark. That relationship can change over time, so the UI exposes the source year, local value, same-year Budapest reference, factor, transaction count and method.

The observed Duna House asking market is **not** an input to this formula. Regression tests protect that separation.

### Why the former feature-branch nowcast was not merged

The former `feat/live-market-intelligence` branch used another formulation: local annual KSH value multiplied by a subsequent Budapest transaction trend. While reconciling the branch, that implementation was rejected rather than merged wholesale.

The current formula uses the same-year annual Budapest denominator explicitly and then applies the local factor to the latest quarterly **second-hand** benchmark. This better reflects the fact that the granular annual source is not itself split into the same new/second-hand series.

### Why new-build stays broad

Applying a local factor from an annual all-segment source to a quarterly new-build series would introduce an unsupported segment-composition assumption.

For `new` selections, version 0.2.1 uses the directly published quarterly new-dwelling KSH benchmark and does not apply the granular local factor.

### Granular fallback order

For a Budapest second-hand district property, the valuation path tries:

1. exact street + selected KSH property class;
2. exact street + all dwellings;
3. district + selected KSH property class;
4. district + all dwellings;
5. latest Budapest quarterly second-hand benchmark.

If a local row is used, the denominator of its factor is always the same-year **Budapest all-dwelling** annual benchmark.

The dedicated `/local` page does not hide fallback behaviour inside one result. It lets the user inspect district and street rows directly. Its “current local-factor estimate” applies exactly the same factor method to each published local row.

### Local confidence labels

The Local Evidence page uses a deliberately simple display confidence label based on the published transaction count and relative spread:

- `high`: at least 100 transactions and relative spread no greater than 35%;
- `medium`: at least 30 transactions and relative spread no greater than 50%;
- otherwise `low`.

This is a display aid, not a formal confidence interval. It exists to stop a thin street sample from looking equally authoritative beside a much stronger district sample.

## 4. Observed asking market

The experimental Duna House provider produces an independent daily asking-market layer from factual listing observations.

The aggregate can contain:

- median asking HUF/m²;
- mean asking HUF/m²;
- 25th and 75th percentiles;
- usable sample size;
- newly observed listing count;
- observed price-cut count;
- median observed price cut where available;
- observed active-listing count;
- property-sitemap discovery count where available;
- operational source-observation coverage;
- confidence label.

The public page uses the **median** as the headline asking value because listing-price distributions can be skewed. The KSH completed-transaction series continues to use the statistic KSH actually publishes, which is a mean in the current tables.

Those headline numbers therefore use different statistics and populations. The UI identifies that explicitly.

### Postcode drill-down

Version 0.2.1 can also build a `POSTCODE_<code>` aggregate from the same observed Duna House rows. This is simply a finer grouping of the source subset.

A postcode aggregate is published only when it meets the same configured minimum sample rule. It must not be interpreted as a census of that postcode's active market.

### Asking-market confidence

The aggregate confidence rule is conservative:

- below the configured minimum sample: aggregate not published;
- otherwise `low` by default;
- at least 30 usable listings and roughly 5% or more observed sitemap coverage: `medium`;
- at least 100 usable listings and roughly 20% or more observed sitemap coverage: `high`.

These labels describe the quality of the observed source subset, not its representativeness of every Hungarian listing portal.

### Coverage is not market share

`coverage_ratio` is an operational measure:

```text
active usable residential listings observed by this deployment
──────────────────────────────────────────────────────────────
eligible residential URLs currently discovered in the source sitemap
```

It is not Duna House's share of the Hungarian property market and must never be described that way.

### Observed price-cut share

The dedicated Live Asking view adds a longitudinal signal based on this deployment's own history.

For each currently usable listing:

```text
observed cut = latest locally observed asking price
               < first locally observed asking price
```

Then:

```text
price-cut share = listings with an observed cut / usable active listings
```

The median cut is the median percentage change from first locally observed asking price to latest locally observed asking price among listings with a cut.

A reduction that occurred before this deployment first saw the listing cannot be recovered from this metric.

### New observations

`new_7d_count` means listings whose local `first_seen_at` falls within the last seven days. It does not claim those listings were published on the source within exactly that period.

### Median observed days

```text
observed days = current time - local first_seen_at
```

The UI deliberately calls this “observed days”, not days-on-market. A deployment cannot know how long an already-existing listing had been live before its first successful observation.

### Short factual attribute coverage

When explicitly labelled short values are present, the observer may store building type, condition, construction year, floor, lift, balcony/terrace, view, orientation, heating and energy rating in a separate factual-attribute table.

The Live view reports:

1. the share of usable active listings with at least one supported attribute;
2. populated supported fields divided by all supported fields across the usable sample.

These are completeness metrics only. The attributes are not currently used as trained valuation effects.

## 5. Property-specific estimate

The valuation worksheet starts from the transaction-value benchmark/nowcast above and then applies explicit property-specific fallback adjustments.

Version 0.2.1 still uses manually defined coefficients for factors such as ground floor, top floor, no lift, renovation state, courtyard orientation and balcony/terrace. These coefficients are visible to the user rather than hidden.

They are not yet a locally calibrated hedonic model. The application caps the combined adjustment and returns a deliberately broad estimate range.

When sufficient lawful microdata exist, these fallback coefficients can be replaced with versioned locally estimated effects and validation statistics. The newly stored Duna House factual attributes are a potential input only after their coverage, bias and stability have been measured.

## Asking price versus estimated property value

If the user enters a property's asking price in the valuation worksheet:

```text
asking premium/discount = asking price / estimated value - 1
```

This is a comparison. It does not imply that either number is the final negotiated sale price.

## Asking versus transaction gap

The market and Live Asking views can show:

```text
observed asking gap = observed asking median / transaction-value nowcast - 1
```

This can be useful as a market signal, but it is not a direct expected negotiation discount. The datasets can differ in property mix, timing, geography and source coverage.

## Time series and movement

The broad official chart uses the KSH quarterly series. District views use the Budapest quarterly series for current movement because the current official provider does not supply an equivalent quarterly district series.

The observed asking chart uses daily aggregate history accumulated by the deployment. It cannot reconstruct historical daily asking data from before collection began unless a lawful historical source is later added.

If there is insufficient history, a movement value remains unavailable rather than being extrapolated.

## First-seen, last-seen and disappearance

`first_seen_at` means the first time this deployment successfully observed a listing. It is not necessarily the original publication date.

`last_seen_at` means the latest successful detail-page observation.

The sitemap-presence state is separate. By default, a listing must be missing from **two consecutive sitemap observations** before it is marked inactive. A first miss records a pending absence but leaves the listing active. If the URL reappears, the miss count is reset and the listing is active again.

The threshold is configurable through `DH_INACTIVE_AFTER_MISSES`.

Even after the threshold is crossed, **removed does not mean sold**. No completed transaction is inferred from disappearance.

## Survivor and composition bias

A portal's active listings are not a random sample of all properties. Expensive, unusual or difficult-to-sell homes can remain visible longer, while quickly sold homes may disappear sooner. This can bias a stock median.

Likewise, movement in a raw median can come from a change in the mix of listed properties rather than a true like-for-like price change.

The UI therefore calls the Duna House measure an observed asking subset and does not call it a quality-adjusted house-price index.

A later analytical layer can add separate stock and new-listing flow medians and, when attribute coverage is sufficient, a versioned mix-adjusted or hedonic index.

## Currency conversion

HUF is canonical. EUR and USD values are secondary comparisons using the latest stored MNB fixing.

Market history itself remains stored in HUF. A historical HUF observation is not rewritten because a later EUR/HUF or USD/HUF rate changes.

A future foreign-currency historical chart should use contemporaneous FX snapshots rather than today's rate for every past observation.

## Precision and missing data

Real Estate Watch prefers a missing value over invented precision.

Collectors use safety ranges, narrow parsers and source-health records. Optional data-source failures do not erase the last verified data and do not cause another source to be silently relabelled as the missing one.

The consequence is visible gaps. That is preferable to an apparently complete chart built from undocumented interpolation, guessed categories or silent source substitution.
