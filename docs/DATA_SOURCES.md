# Data sources and provenance

Every market or financial figure in Real Estate Watch should have a source, an observation period and a clear statement of what the figure represents. Asking prices, completed sales and property estimates are not interchangeable.

## KSH quarterly housing prices

Source: Hungarian Central Statistical Office (KSH), STADAT table 18.2.2.14.

`https://www.ksh.hu/stadat_files/lak/en/lak0052.html`

The application uses the quarterly **mean price per square metre** series for completed housing transactions. The source separates second-hand and new dwellings. Broad selectable geographies include Budapest, Pest region, the main statistical regions and Hungary as a national aggregate.

This is not a live asking-price feed and it is not a median. Recent KSH observations can be preliminary and later revised, so the collector upserts an existing quarter only after validation.

The bundled files under `app/countries/hu/data/` are first-start/recovery material. They can fill a missing reference row but never overwrite a value already collected from live KSH.

Some new-build regional quarters are blank in KSH. They remain missing rather than being interpolated.

## KSH quarterly transaction counts

Source: KSH STADAT table 18.2.2.15.

`https://www.ksh.hu/stadat_files/lak/en/lak0053.html`

The app collects the number of housing transactions for the same quarterly geography and new/second-hand split. When a count matches a stored price observation, it is attached as `sample_size`.

The count table is supplementary. A published count does not create a price observation when KSH has not published a corresponding price. Price and count collectors have separate health records.

## KSH Ingatlanadattár: Budapest city, district and street benchmarks

Public application: `https://www.ksh.hu/s/ingatlanadattar/`

Official client dataset used by the KSH frontend:

`https://www.ksh.hu/s/ingatlanadattar/inga-data.json`

This is a separate official layer from the quarterly STADAT series. KSH describes Ingatlanadattár as being based on completed property-transfer information supplied from the tax authority's transaction records. The public product provides finer geography and dwelling-type information than the quarterly table.

The KSH frontend currently loads a single JSON dataset. The collector reads that official client dataset once at the configured granular refresh interval and normalises the Budapest records it needs. It does **not** crawl every district/street display page.

The live source contract examined in August 2026 exposes Budapest hierarchy records for:

- Budapest total;
- all 23 Budapest districts;
- street observations where KSH publishes them;
- annual observations currently present in the client dataset;
- family-house mean HUF/m² and transaction count;
- multi-unit condominium mean HUF/m² and transaction count;
- panel mean HUF/m² and transaction count;
- all-dwelling mean HUF/m² and transaction count;
- relative dispersion where published.

KSH publishes price values in thousand HUF/m² in this client dataset; Real Estate Watch converts them to HUF/m² on ingest. Missing fields remain missing.

The source uses KSH territorial identifiers internally. The 23 Budapest district identifiers in the provider were verified against KSH's own public frontend data rather than inferred from names.

### Important segment limitation

The Ingatlanadattár client dataset used here does not expose the same `new` versus `second_hand` split as the quarterly STADAT series. Real Estate Watch therefore does **not** call a granular row a district-level second-hand or new-build observation.

For second-hand Budapest nowcasting, the granular value is converted to a local/property-type factor relative to the same-year Budapest all-dwelling annual value and that factor is applied to the latest quarterly Budapest second-hand benchmark. For new-build selections, version 0.2 stays on the directly published quarterly new-build series instead of applying an unsupported granular segment assumption.

The exact formula and fallback order are in [METHODOLOGY.md](METHODOLOGY.md).

### Refresh behavior

The granular dataset is annual and substantially larger than the quarterly tables, so its collector normally refreshes weekly. `KSH_LOCAL_REFRESH_HOURS` controls the interval. Source-health data record success, failure and the normalised row count.

A malformed, unexpectedly small or incomplete response is rejected. The collector also requires all 23 Budapest district totals and a Budapest city total before accepting a live granular refresh.

## Duna House observed asking market

Source discovery: Duna House public property sitemap declared by its `robots.txt` at the project's manual review on 13 August 2026.

Technical access references reviewed by the project:

- `https://dh.hu/robots.txt`
- `https://dh.hu/jogi-nyilatkozat`
- the property sitemap configured in application settings.

This source has a deliberately different status from KSH: **experimental observed subset**.

At the review date, the public robots file allowed the reviewed property path and declared a property sitemap. That technical crawl signal is not treated as an open-data licence. Real Estate Watch does not claim the Duna House data are open data or that the observed subset represents every Hungarian listing portal.

The provider minimises retained data. It stores only factual fields needed for market statistics: listing reference, canonical URL, locality/postcode/district, broad property class, new/second-hand status when determinable, rooms, asking price, floor area and observation timestamps. It does not store descriptions, photographs, floor plans, seller/agent names, phone numbers or email addresses.

The public application exposes aggregates rather than a reconstructed listing browser.

Before detail-page collection, the policy guard verifies the reviewed robots/sitemap contract, looks for explicit automated-access stop-language changes, fingerprints the relevant policy material and enforces a dated manual-review expiry. An unexpected policy change pauses collection rather than triggering a workaround.

This guard is a technical safety mechanism, not legal advice and not a licence. See [DUNA_HOUSE_PROVIDER.md](DUNA_HOUSE_PROVIDER.md).

### What the observed asking value means

The headline asking figure is the median HUF/m² of source listings successfully observed by this deployment that pass validation for the selected area/property class.

It is not described as the median of all active Hungarian listings. Source composition can differ from the wider market by agency network, geography, property type and seller mix.

The app can record source-observation coverage against the currently discovered property sitemap. That is an operational coverage measure, not Hungarian market share.

A listing that disappears from the sitemap is marked inactive. It is never automatically labelled sold.

## MNB exchange rates

Source: Magyar Nemzeti Bank, latest official exchange-rates page.

`https://www.mnb.hu/arfolyamok`

The collector retrieves the published EUR and USD rates expressed in HUF together with the MNB fixing date. HUF remains the primary display currency; EUR and USD are secondary comparisons.

MNB also documents a SOAP service for current and historic exchange rates. The project's first live contract test in August 2026 found the documented public `arfolyamok.asmx` POST route returning HTTP 404 from GitHub Actions. The application therefore uses MNB's public latest-rates page for the two rates required by the current UI rather than hiding that failure or relying on an undocumented workaround.

The fixing date is stored with each observation. Historical HUF market values are not rewritten because today's FX rate changes.

Safety checks reject unsupported currencies, implausible values, a one-step movement greater than 15% from the previous verified observation, future fixing dates and unexpectedly old purported latest fixings. Rejected data leave the previous verified rate intact and mark the source degraded.

## MNB debt-brake rules

Source: MNB borrower-based measures (HFM/JTM).

`https://www.mnb.hu/penzugyi-stabilitas/makroprudencialis-politika/makroprudencialis-eszkoztar/adossagfek-szabalyok-hfm-jtm`

The Hungary module implements the HUF mortgage limits relevant to the current calculator, including the HUF 800,000 monthly net-income JTM threshold effective from 1 January 2026 and the qualifying 90% HFM paths implemented by the current rule module.

The result is a regulatory screen, not bank approval. A lender can recognise a different property value or income amount and can apply stricter/product-specific underwriting.

## NAV transfer tax

Source: Nemzeti Adó- és Vámhivatal (NAV), onerous property transfer tax rates.

`https://nav.gov.hu/ugyfeliranytu/adokulcsok_jarulekmertekek/illetekmertekek/visszterhes-vagyonatruhazasi-illetek`

The calculator implements the general rule currently represented by the Hungary module. Special exemptions and reliefs are not assumed automatically. Fact-specific reliefs should be added only as explicit scenarios backed by an authoritative source.

## Source still needed: current mortgage products

The application calculates a mortgage from the interest rate supplied by the user and applies the MNB regulatory screen. It does not yet maintain a live bank-product catalogue.

Official MNB comparison tools are useful references:

- Hitel- és lízingtermék-kereső: `https://hitelvalaszto.mnb.hu/termekkereso`
- Minősített Fogyasztóbarát Lakáshitel calculator: `https://minositetthitel.mnb.hu/kalkulator`

The project does not currently depend on an undocumented machine endpoint behind either site. A future product provider should preserve institution, product, source update date, THM/APR, fixation, term, amount limits and eligibility details.

Until then, the UI asks for an interest rate and does not label the result a current bank offer.

## Source-contract testing

`.github/workflows/source-contract.yml` is separate from ordinary deterministic CI. It periodically verifies live source contracts for:

- KSH quarterly price parsing;
- KSH quarterly transaction-count parsing;
- the KSH Ingatlanadattár client dataset and granular normalisation;
- MNB FX parsing;
- the Duna House policy/sitemap contract and one factual listing page;
- resulting application self-checks.

The Duna House step is intentionally a probe. GitHub Actions does not bulk-collect Duna House listings.
