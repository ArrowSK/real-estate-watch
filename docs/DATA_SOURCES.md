# Data sources and provenance

The main rule is simple: every market or financial figure must have a source, an observation period and a clear statement of what the figure represents. Real Estate Watch does not use one generic number called "market price" for asking prices, completed sales and property estimates.

## KSH quarterly housing prices

Source: Hungarian Central Statistical Office (KSH), STADAT table 18.2.2.14.

`https://www.ksh.hu/stadat_files/lak/en/lak0052.html`

The application uses the quarterly **mean price per square metre** series for completed housing transactions. The source separates second-hand and new dwellings.

The broad selectable geographies published consistently in that quarterly table include Budapest, Pest region, the main statistical regions and Hungary as a national aggregate.

This is not a live asking-price feed and it is not a median. The UI states that explicitly.

KSH marks some recent data as preliminary and may revise them. The collector therefore upserts an existing KSH quarter only after the replacement passes validation.

The bundled files under `app/countries/hu/data/` exist for first start and recovery. They are source-attributed KSH reference observations, not independent market sources. Startup and self-healing insert only missing bundled rows. They never overwrite an existing row collected from live KSH, because that could replace a later official revision with an older bundled value.

Some new-build regional quarters are blank in KSH. Real Estate Watch leaves those quarters missing rather than interpolating them.

## KSH quarterly transaction counts

Source: KSH STADAT table 18.2.2.15.

`https://www.ksh.hu/stadat_files/lak/en/lak0053.html`

The app collects the number of housing transactions made by private persons for the same quarterly geography and new/second-hand split. When a count matches a stored price observation, it is attached as that observation's `sample_size`.

The count table is supplementary. A transaction count does not create a price observation when KSH has not published the corresponding mean price.

The price and count sources have separate health records, so a count-source failure remains visible without corrupting the price series.

## KSH Ingatlanadattár: district and street benchmarks

Source: KSH Ingatlanadattár.

`https://www.ksh.hu/s/ingatlanadattar/`

This is a separate official layer from the quarterly STADAT series. It uses completed property-transaction data and can provide much finer geography. In Budapest, the public data pages expose district-level and, where KSH publishes enough observations, street-level statistics.

The collector stores the factual columns that are useful for valuation:

- year;
- district and optional street;
- family-house mean HUF/m² and transaction count where published;
- multi-unit condominium mean HUF/m² and count where published;
- panel-housing mean HUF/m² and count where published;
- all-dwelling mean HUF/m² and count where published;
- relative dispersion where KSH publishes it;
- source URL.

The application discovers Budapest district pages from the public KSH page instead of hardcoding KSH's internal district identifiers.

Granular data are annual rather than quarterly. To make an older local benchmark useful today, Real Estate Watch can move it forward using the subsequent official Budapest quarterly transaction movement. The formula and limitations are documented in [METHODOLOGY.md](METHODOLOGY.md).

The granular collector normally refreshes once per week rather than every day because the source itself is annual. `KSH_LOCAL_REFRESH_HOURS` controls this interval.

A missing KSH street or property-type value remains missing. The parser does not fill it from neighbouring streets or another property class without explicitly falling back at the valuation layer.

## Duna House observed asking market

Source discovery: Duna House public property sitemap declared by its `robots.txt` at the project's manual review on 13 August 2026.

Technical access references reviewed by the project:

- `https://dh.hu/robots.txt`
- `https://dh.hu/jogi-nyilatkozat`
- property sitemap configured in `DH_SITEMAP_URL`/application defaults.

This source has a deliberately different status from KSH: **experimental observed subset**.

At the review date, the public robots file allowed ordinary crawling and declared a property sitemap. The legal/policy page reviewed by the project did not constitute an open-data licence. Real Estate Watch therefore does not describe Duna House data as open data and does not assume that `robots.txt` grants database-reuse rights.

The provider is designed to minimise what is taken and retained. It stores only factual fields needed for market statistics: listing reference, URL, locality/postcode/district, broad property class, new/second-hand status where determinable, rooms, asking price, floor area and observation timestamps. It does not store descriptions, photos, plans, agent/seller names, phone numbers or email addresses.

The public application exposes aggregates, not a reconstructed listing browser.

The collector runs through a policy guard before accessing listing pages. The guard checks the reviewed robots/sitemap contract, looks for explicit stop-language changes, fingerprints the policy bodies and expires the manual review after a configured period. A detected policy change pauses collection instead of attempting to work around it.

This mechanism reduces operational risk but is not legal advice and does not create a licence. See [DUNA_HOUSE_PROVIDER.md](DUNA_HOUSE_PROVIDER.md) for the exact collection and stop conditions.

### What the observed asking value means

The headline asking value is the median HUF/m² of the source listings that this deployment successfully observed and that passed validation for the selected area/property class.

It is **not** presented as the median of every active Hungarian listing. The source may differ from the full market by agency network, geography, property type and seller mix.

The app records a source-observation coverage ratio where the sitemap discovery count is available, but that ratio means "observed from this source", not "share of the Hungarian market".

A listing that disappears from the sitemap is marked inactive. It is not labelled sold.

## MNB exchange rates

Source: Magyar Nemzeti Bank, latest official exchange-rates page.

`https://www.mnb.hu/arfolyamok`

The collector retrieves the published EUR and USD rates expressed in HUF together with the fixing date printed by MNB. HUF remains the primary display currency. EUR and USD are secondary comparison values.

MNB also documents a SOAP web service for current and historic rates. The project's first live contract check in August 2026 found that the documented public `arfolyamok.asmx` POST route returned HTTP 404 from GitHub Actions. Rather than hide that failure or depend on an undocumented workaround, the application uses MNB's public latest-rates page for the two rates needed by the current UI. The source-contract workflow checks that parser directly.

The app stores the fixing date with each FX observation. Historical HUF market observations are not rewritten because today's FX rate changes.

Safety checks reject unsupported currencies, implausible values, a one-step change greater than 15% from the previous verified observation, a future fixing date or a purported latest fixing that is unexpectedly old. A rejected response leaves the previous verified rate in place and marks the source degraded.

## MNB debt-brake rules

Source: MNB borrower-based measures (HFM/JTM).

`https://www.mnb.hu/penzugyi-stabilitas/makroprudencialis-politika/makroprudencialis-eszkoztar/adossagfek-szabalyok-hfm-jtm`

The Hungary module implements the HUF mortgage limits relevant to the current calculator, including the HUF 800,000 monthly net-income JTM threshold effective from 1 January 2026 and the 90% HFM path for qualifying first-home/green cases.

The result is a regulatory screen, not bank approval. A lender can recognise a different property value or income amount and can apply stricter underwriting or product-specific conditions.

## NAV transfer tax

Source: Nemzeti Adó- és Vámhivatal (NAV), onerous property transfer tax rates.

`https://nav.gov.hu/ugyfeliranytu/adokulcsok_jarulekmertekek/illetekmertekek/visszterhes-vagyonatruhazasi-illetek`

The calculator implements the general rate: 4% up to HUF 1 billion, 2% on the portion above HUF 1 billion, capped at HUF 200 million per property.

Special exemptions and reliefs are not automatically assumed. Replacement purchases, family transactions and other fact-specific cases should be implemented only as explicit rule scenarios supported by an authoritative source.

## Source still needed: current mortgage products

The application calculates a mortgage from the interest rate supplied by the user and applies the MNB regulatory screen. It does not yet maintain a live bank-product catalogue.

Official MNB comparison tools are useful references:

- Hitel- és lízingtermék-kereső: `https://hitelvalaszto.mnb.hu/termekkereso`
- Minősített Fogyasztóbarát Lakáshitel calculator: `https://minositetthitel.mnb.hu/kalkulator`

The project does not currently rely on an undocumented machine endpoint behind either site. A future mortgage-product provider should have a maintainable interface and preserve update date, THM/APR, fixation, term, amount limits and eligibility details.

Until then, the UI asks for an interest rate and does not label the result a current bank offer.

## Source-contract testing

`.github/workflows/source-contract.yml` performs a scheduled live-source check separate from ordinary unit tests.

It checks:

- KSH quarterly price parsing;
- KSH transaction-count parsing;
- KSH granular district/street parsing;
- MNB FX parsing;
- the Duna House policy/sitemap contract and one factual listing-page parse;
- the resulting application self-checks.

The Duna House CI step is intentionally only a probe. It does not bulk-collect the property sitemap in GitHub Actions.
