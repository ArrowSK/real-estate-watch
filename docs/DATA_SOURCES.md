# Data sources and provenance

The main rule is simple: every market or financial figure must have a source, an observation period and a clear statement of what the figure actually represents.

## KSH housing prices

Source: Hungarian Central Statistical Office (KSH), STADAT table 18.2.2.14.

`https://www.ksh.hu/stadat_files/lak/en/lak0052.html`

The application currently uses the quarterly **mean price per square metre** series for completed housing transactions. The source separates second-hand and new dwellings and includes Budapest and national aggregates.

This is not a live asking-price feed. It is also not a median. The UI says this explicitly.

KSH marks some recent data as preliminary and may revise them. The collector therefore upserts an existing KSH quarter after the replacement value passes basic validation.

The bundled seed file under `app/countries/hu/data/market_seed.json` exists for resilience and first start. It is source-attributed reference data, not a second independent source.

## MNB exchange rates

Source: Magyar Nemzeti Bank exchange-rate SOAP service.

`https://www.mnb.hu/arfolyamok.asmx`

The collector retrieves current EUR and USD rates expressed in HUF. HUF remains the primary display currency. EUR and USD are smaller comparison values only.

The app stores the rate date together with each observation. Historical HUF market observations are not rewritten merely because today's FX rate changed.

Safety checks reject unsupported currencies, values outside a broad plausible range and a one-step change greater than 15% from the previous stored observation. A rejected rate leaves the previous verified rate in place.

## MNB debt-brake rules

Source: MNB borrower-based measures (HFM/JTM).

`https://www.mnb.hu/penzugyi-stabilitas/makroprudencialis-politika/makroprudencialis-eszkoztar/adossagfek-szabalyok-hfm-jtm`

The Hungary module currently implements the HUF mortgage limits relevant to the calculator, including the HUF 800,000 monthly net-income JTM threshold effective from 1 January 2026 and the 90% HFM path for qualifying first-home/green cases.

The calculator does not claim bank approval. Banks can apply stricter underwriting and can recognise a different property value or income amount.

## NAV transfer tax

Source: Nemzeti Adó- és Vámhivatal (NAV), onerous property transfer tax rates.

`https://nav.gov.hu/ugyfeliranytu/adokulcsok_jarulekmertekek/illetekmertekek/visszterhes-vagyonatruhazasi-illetek`

The calculator implements the general rate: 4% up to HUF 1 billion, 2% on the portion above HUF 1 billion, capped at HUF 200 million per property.

Special exemptions and reliefs are not automatically assumed. Examples include replacement purchases, family transactions and other fact-specific cases. A later rule module can add those as explicit user-selected scenarios.

## Sources still needed

### Asking-price and listing history

The planned product needs a lawful, stable source for active Hungarian residential listings. That source must support enough fields to deduplicate listings, calculate asking-price medians, follow price cuts and estimate days on market.

Until such a feed is selected, Real Estate Watch does not label KSH transaction means as "current asking prices".

### Mortgage products

The current build calculates a mortgage from the interest rate supplied by the user and applies MNB regulatory screens. It does not maintain a bank-product catalogue yet.

A production mortgage-product provider needs an authoritative or contractually stable source with product update dates, APR/THM, fixation, term, amount limits and eligibility details. The provider must preserve the source date and should never present a cached offer as current after the source has gone stale.
