# Methodology

Real Estate Watch is built around one rule: numbers that answer different questions must not be collapsed into one vaguely labelled "market price".

For Hungary, version 0.2 keeps five analytical layers separate.

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

The granular source is annual and, in the dataset used by this build, does **not** provide the same new/second-hand split as the quarterly STADAT series. That limitation changes how it is used.

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

This is deliberately a **nowcast**, not a directly observed current district sale price. It assumes that the annual local/property-type relationship to the Budapest market is still informative when applied to the latest broad second-hand transaction benchmark. That relationship can change over time, so the UI exposes the local year, local value, same-year Budapest reference, factor, transaction count and method.

The observed Duna House asking market is **not** an input to this formula. A regression test protects that separation.

### Why new-build stays broad

The granular KSH client dataset used here is not split into new and second-hand dwellings in the same way as the quarterly price series. Applying its local factor to a new-build series would therefore add an unsupported assumption about segment composition.

For `new` selections, version 0.2 uses the directly published quarterly new-dwelling KSH benchmark and does not apply the granular local factor.

### Granular fallback order

For a Budapest second-hand district property, the application tries:

1. exact street + selected KSH property class;
2. exact street + all dwellings;
3. district + selected KSH property class;
4. district + all dwellings;
5. latest Budapest quarterly second-hand benchmark.

If a local row is used, the denominator of its factor is always the same-year **Budapest all-dwelling** annual benchmark. This intentionally preserves both the location and selected property-class premium/discount relative to the city-wide annual market.

For non-district areas currently supported by the quarterly KSH provider, the latest available quarterly benchmark is used directly.

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

### Asking-market confidence

The initial confidence rule is conservative:

- below the configured minimum sample: aggregate not published;
- otherwise `low` by default;
- at least 30 usable listings and roughly 5% or more observed sitemap coverage: `medium`;
- at least 100 usable listings and roughly 20% or more observed sitemap coverage: `high`.

These labels describe the quality of the observed source subset, not its representativeness of every Hungarian listing portal. A large Duna House sample can still differ systematically from properties advertised elsewhere.

### Coverage is not market share

`coverage_ratio` is an operational measure:

```text
active usable listings observed by this deployment
──────────────────────────────────────────────────
property URLs currently discovered in the source sitemap
```

It is not Duna House's share of the Hungarian property market and must never be described that way.

## 5. Property-specific estimate

The valuation worksheet starts from the transaction-value benchmark/nowcast above and then applies explicit property-specific fallback adjustments.

Version 0.2 still uses manually defined coefficients for factors such as ground floor, top floor, no lift, renovation state, courtyard orientation and balcony/terrace. These coefficients are visible to the user rather than hidden.

They are not yet a locally calibrated hedonic model. The application caps the combined adjustment and returns a deliberately broad estimate range.

When sufficient lawful microdata exist, these fallback coefficients can be replaced with versioned locally estimated effects and validation statistics.

## Asking price versus estimated property value

If the user enters a property's asking price in the valuation worksheet, Real Estate Watch calculates the premium or discount against the property estimate:

```text
asking premium/discount = asking price / estimated value - 1
```

This is a comparison. It does not imply that either number is the final negotiated sale price.

## Asking versus transaction gap

The main market page can show:

```text
observed asking gap = observed asking median / transaction-value nowcast - 1
```

This can be useful as a market signal, but it is not a direct expected negotiation discount. The datasets can differ in property mix, timing, geography and source coverage.

## Time series and movement

The broad official chart uses the KSH quarterly series. District pages use the Budapest quarterly series for the current movement axis because the current official provider does not supply an equivalent quarterly district series.

The observed asking chart uses daily aggregate history accumulated by the deployment. It cannot reconstruct historical daily asking data from before collection began unless a lawful historical source is later added.

The app can calculate:

- six-month completed-transaction movement from the broad quarterly series;
- approximately 30-day asking-median movement when enough daily asking history exists.

If there is insufficient history, the value remains unavailable rather than being extrapolated.

## First-seen, last-seen and removal

`first_seen_at` means the first time this deployment successfully observed a listing. It is not necessarily the original publication date.

`last_seen_at` means the latest successful observation.

A URL disappearing from the source sitemap means only that the application no longer sees it there. It is marked inactive. **Removed does not mean sold.** No completed transaction is inferred from disappearance.

## Survivor and composition bias

A portal's active listings are not a random sample of all properties. Expensive, unusual or difficult-to-sell homes can remain visible longer, while quickly sold homes may disappear sooner. This can bias a stock median.

Likewise, movement in a raw median can come from a change in the mix of listed properties rather than a true like-for-like price change.

The current UI therefore calls the Duna House measure an observed asking subset and does not call it a quality-adjusted house-price index.

A later analytical layer can add separate stock and new-listing flow medians and, when enough attributes are available, a versioned mix-adjusted or hedonic index.

## Currency conversion

HUF is canonical. EUR and USD values are secondary comparisons using the latest stored MNB fixing.

Market history itself remains stored in HUF. A historical HUF observation is not rewritten because a later EUR/HUF or USD/HUF rate changes.

A future foreign-currency historical chart should use contemporaneous FX snapshots rather than today's rate for every past observation.

## Precision and missing data

Real Estate Watch prefers a missing value over invented precision.

Collectors use safety ranges, narrow parsers and source-health records. Optional data-source failures do not erase the last verified data and do not cause another source to be silently relabelled as the missing one.

The consequence is visible gaps. That is preferable to an apparently complete chart built from undocumented interpolation or guessed categories.
