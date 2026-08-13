# Methodology

Real Estate Watch is designed around a simple rule: numbers that answer different questions must not be collapsed into one vaguely labelled "market price".

For Hungary, version 0.2 keeps five analytical layers separate.

## 1. Quarterly completed-transaction benchmark

The broad official market layer comes from KSH STADAT housing-price tables. It is a quarterly **mean completed-transaction price per square metre**, split between second-hand and new dwellings.

This is the best current broad transaction benchmark in the application. It is not a current asking-price median and it is not property-specific.

Transaction counts come from the matching KSH count table and are attached only where period, geography and market segment match the stored price observation.

## 2. Granular local completed-transaction benchmark

KSH Ingatlanadattár supplies a different and more granular annual layer. For Budapest it can provide district-level and, where published, street-level completed-transaction information with property-type breakdowns.

The current provider stores:

- annual mean HUF/m²;
- transaction count where published;
- relative dispersion where published;
- geography;
- street name where available;
- broad property class: family house, multi-unit condominium, panel or all dwellings.

Missing published values remain missing. The collector does not interpolate a blank cell.

## 3. Current transaction-value nowcast

An annual street or district benchmark can be more locally relevant than the newest broad quarterly figure but less current. Real Estate Watch therefore moves a local Budapest benchmark forward using the subsequent official Budapest completed-transaction trend.

For a local observation from year `Y`:

```text
current local transaction nowcast
    = local KSH annual mean HUF/m²
      × (latest Budapest quarterly KSH mean
         / latest Budapest quarterly KSH mean at or before 31 Dec Y)
```

Example structure only:

```text
2024 district apartment mean                  1,500,000 HUF/m²
Budapest quarterly mean at 2024 year-end      1,000,000 HUF/m²
Latest Budapest quarterly mean                 1,200,000 HUF/m²
Subsequent transaction movement                     1.20×
                                                   ─────
Current transaction-value nowcast              1,800,000 HUF/m²
```

This method deliberately assumes that the selected local segment moved proportionally with the subsequent Budapest-wide completed-transaction series. That may not hold perfectly, so the UI exposes the local year, the trend factor, the source and the method rather than presenting the result as a directly observed current transaction price.

The observed asking-market source is **not** used in this formula. That separation is covered by a regression test.

### Fallback order

For a Budapest district property the application tries, in order:

1. exact street + selected KSH property class;
2. exact street + all dwellings;
3. district + selected KSH property class;
4. district + all dwellings;
5. Budapest quarterly completed-transaction benchmark.

For non-district areas currently supported by the quarterly KSH provider, the latest available quarterly benchmark is used directly.

## 4. Observed asking market

The experimental Duna House provider produces an independent daily asking-market layer from factual listing observations.

The aggregate contains:

- median asking HUF/m²;
- mean asking HUF/m²;
- 25th and 75th percentiles;
- usable sample size;
- newly observed listing count;
- observed price-cut count;
- median observed price cut where available;
- observed active-listing count;
- property-sitemap discovery count where available;
- an approximate source-observation coverage ratio;
- confidence label.

The public page uses the **median** as the headline asking value because listing-price distributions can be skewed. The KSH completed-transaction series continues to use the statistic KSH actually publishes, which is a mean in the current tables.

These two headline numbers therefore use different statistics and different populations. That is intentional and visibly labelled.

### Asking-market confidence

The initial confidence rule is deliberately conservative:

- below the configured minimum sample: aggregate not published;
- otherwise `low` by default;
- at least 30 usable listings and at least roughly 5% observed sitemap coverage: `medium`;
- at least 100 usable listings and at least roughly 20% observed sitemap coverage: `high`.

These labels describe the quality of the observed source subset, not its representativeness of the entire Hungarian market. A large Duna House sample can still differ systematically from properties advertised elsewhere.

### Coverage is not market share

`coverage_ratio` is an operational measure:

```text
active usable listings observed by this app / property URLs discovered in the source sitemap
```

It is not Duna House's share of the Hungarian property market and must never be shown as such.

## 5. Property-specific estimate

The valuation worksheet starts from the current transaction-value nowcast described above and then applies explicit property-specific fallback adjustments.

The first release still uses manually defined coefficients for factors such as ground floor, top floor, no lift, renovation state, courtyard orientation and balcony/terrace. These coefficients are shown to the user rather than hidden.

They are not yet a locally calibrated hedonic model. The application caps the combined adjustment and returns a deliberately broad estimate range.

When sufficient lawful listing-level or transaction microdata become available, these fallback coefficients can be replaced by modelled local effects with model versioning and validation.

## Asking price versus estimated property value

If the user enters a property's asking price in the valuation worksheet, Real Estate Watch calculates the premium or discount against the property estimate:

```text
asking premium/discount = asking price / estimated value - 1
```

This is a comparison, not evidence that either number is the final negotiated sale price.

## Asking versus transaction gap

The main market page can also show:

```text
observed asking gap = observed asking median / transaction-value nowcast - 1
```

This is useful as a market signal but must be interpreted carefully. The two datasets may differ in property mix, timing and coverage. A positive gap does not directly equal an expected negotiation discount.

## Time series and movement

The broad official chart uses the KSH quarterly series. District pages use the Budapest quarterly series for the current movement axis because there is no equivalent quarterly district series in the current official provider.

The observed asking chart uses the daily aggregate history accumulated by this deployment. It cannot reconstruct historical daily asking data from before the deployment began unless a lawful historical source is later added.

The app can calculate:

- six-month completed-transaction movement from the broad quarterly series;
- approximately 30-day asking-median movement when enough daily asking history exists.

If there is insufficient history, the value is left unavailable rather than extrapolated.

## First-seen, last-seen and removal

`first_seen_at` means the first time this deployment successfully observed a listing. It is not necessarily the listing's original publication date.

`last_seen_at` means the latest successful observation.

A URL disappearing from the source sitemap means only that the application no longer sees it there. It is marked inactive. **Removed does not mean sold.** No completed transaction is inferred from disappearance.

## Survivor and composition bias

A portal's active listings are not a random sample of all properties. Expensive, unusual or difficult-to-sell properties can remain visible for longer, while quickly sold properties may disappear sooner. This can bias a stock median.

Likewise, movements in a raw median can result from changes in the mix of listed properties rather than a true change in like-for-like prices.

The current UI therefore calls the Duna House metric an observed asking subset and does not label it a quality-adjusted house-price index.

A later analytical layer can add separate stock and new-listing flow medians and, when enough features are available, a versioned mix-adjusted or hedonic index.

## Currency conversion

HUF is canonical. EUR and USD values are secondary comparisons using the latest stored MNB fixing.

Market history itself remains stored in HUF. A historical HUF observation is not rewritten because a later EUR/HUF or USD/HUF rate changes.

A future foreign-currency historical chart should use contemporaneous FX snapshots rather than today's rate for every past observation.

## Precision and missing data

Real Estate Watch prefers a missing value over invented precision.

Collectors use safety ranges, narrow parsers and source-health records. Optional data-source failures do not erase the last verified data and do not cause a different source to be silently relabelled as the missing one.

The methodological consequence is visible gaps. That is preferable to an apparently complete chart built from undocumented interpolation or guessed categories.
