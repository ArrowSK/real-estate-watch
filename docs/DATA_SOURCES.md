# Data sources and provenance

The main rule is simple: every market or financial figure must have a source, an observation period and a clear statement of what the figure actually represents.

## KSH housing prices

Source: Hungarian Central Statistical Office (KSH), STADAT table 18.2.2.14.

`https://www.ksh.hu/stadat_files/lak/en/lak0052.html`

The application currently uses the quarterly **mean price per square metre** series for completed housing transactions. The source separates second-hand and new dwellings.

The selectable areas currently match rows that the quarterly KSH table actually publishes at a consistent level:

- Budapest;
- Pest region;
- Central Transdanubia;
- Western Transdanubia;
- Southern Transdanubia;
- Northern Hungary;
- Northern Great Plain;
- Southern Great Plain;
- Hungary as a national aggregate.

These are not counties, Budapest districts or neighbourhoods. Those need a different data source and should not be inferred from the broad regional series.

This is not a live asking-price feed. It is also not a median. The UI says this explicitly.

KSH marks some recent data as preliminary and may revise them. The live collector therefore upserts an existing KSH quarter after the replacement value passes validation.

The bundled files under `app/countries/hu/data/` exist for first start and recovery. They are source-attributed KSH reference observations, not independent market sources. Startup and self-healing only insert a bundled observation when that database row is missing. They never overwrite a row already collected from live KSH, because doing so could replace a later official revision with an older bundled value.

Some regional new-build quarters are blank in KSH because no publishable value is available. Real Estate Watch leaves those quarters missing instead of interpolating them.

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

Until such a feed is selected, Real Estate Watch does not label KSH transaction means as "current asking prices" and does not manufacture district-level estimates from national or regional averages.

### Mortgage products

The current build calculates a mortgage from the interest rate supplied by the user and applies MNB regulatory screens. It does not maintain a bank-product catalogue yet.

Two official MNB tools are useful candidates for the product-provider stage:

- Hitel- és lízingtermék-kereső: `https://hitelvalaszto.mnb.hu/termekkereso`
- Minősített Fogyasztóbarát Lakáshitel calculator: `https://minositetthitel.mnb.hu/kalkulator`

They are suitable official comparison references, but the project does not currently rely on an undocumented machine endpoint behind either site. Before automating product collection, the provider needs a documented or otherwise maintainable data interface with product update dates, THM/APR, fixation, term, amount limits and eligibility details.

Until that exists, the app asks for an interest rate and labels the result as a calculation and regulatory screen, not a live bank offer.
