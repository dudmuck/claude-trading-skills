# Economic Indicator Knowledge Base

Static reference. Each card below is parsed by `scripts/lookup_indicator.py`.

Keep `## What it is` and `## How it's measured` frozen — those don't change.
Update `## Reaction history` and `## Watch for today` when the macro regime shifts (cutting vs. hiking vs. holding).

All reaction-history numbers are textbook expectations from the post-COVID hiking/cutting cycles (2022–2026). Replace with your own logged data once you have ~10 prints per indicator under `state/reaction_history/`.

---
canonical: "Consumer Price Index (CPI) YoY"
short_name: "CPI"
category: "inflation"
country: "US"
release_time_et: "08:30"
frequency: "monthly"
release_source: "BLS"
importance: "tier-1"
fmp_aliases:
  - "Consumer Price Index (CPI) YoY"
  - "CPI YoY"
  - "Inflation Rate YoY"
  - "CPI MoM"
---

## What it is
Headline year-over-year change in prices for a basket of consumer goods and services. Includes food and energy — the "what households actually pay" number, versus Core CPI which strips those volatile components.

## How it's measured
BLS surveys ~80,000 prices monthly across 8 major categories (food, energy, housing, apparel, transportation, medical care, recreation, other). Shelter is the largest weight (~33%), driven by Owner's Equivalent Rent — a survey-based proxy that lags actual rent moves by ~12 months. Released ~10–15 days after month end, 8:30am ET.

## Why it matters
Direct input to Fed reaction function and the most-watched US inflation print. Hot CPI → fewer/later rate cuts priced in → front-end yields rise, USD strengthens, long-duration tech and gold sell off. Cool CPI does the reverse and is the cleanest "risk-on" catalyst in a hiking/holding regime.

## Reaction history (60-min after release)
- **Hot surprise (+0.2pp vs est):** SPY -0.6 to -1.5%, TLT -0.8 to -2.0%, DXY +0.4 to +0.8%, VIX +1 to +3
- **Cool surprise (-0.2pp vs est):** SPY +0.6 to +1.4%, TLT +0.8 to +1.5%, DXY -0.3 to -0.7%, VIX -1 to -2
- **In line:** Muted kneejerk; focus rotates to Core, shelter, and supercore subcomponents

## Watch for today
Subcomponents matter more than headline: shelter MoM (annualized), supercore (core services ex-housing), goods deflation pace. If headline cools but supercore stays hot, the Fed stays cautious. Cross-check with PCE released ~2 weeks later (Fed's preferred gauge — PCE typically runs ~0.3pp below CPI).

---
canonical: "Core CPI YoY"
short_name: "Core CPI"
category: "inflation"
country: "US"
release_time_et: "08:30"
frequency: "monthly"
release_source: "BLS"
importance: "tier-1"
fmp_aliases:
  - "Core Consumer Price Index (CPI) YoY"
  - "Core Inflation Rate YoY"
  - "Core CPI YoY"
  - "Core CPI MoM"
---

## What it is
CPI excluding food and energy — the underlying inflation trend, stripped of the most volatile components. Released simultaneously with headline CPI.

## How it's measured
Same BLS survey, but reweighted to exclude food (~14% of CPI) and energy (~7%). Shelter rises to ~42% of Core CPI weight, making the print mechanically sticky.

## Why it matters
Fed's eyes are on Core, not headline — it filters supply-shock noise (oil spikes, drought) and reveals the underlying pace of price-setting. A Core CPI sticky above 3% is the Fed's stated reason to keep rates restrictive; a sustained move below 2.5% opens the door to cuts.

## Reaction history (60-min after release)
- **Hot Core (+0.1pp vs est on MoM):** Bigger reaction than hot headline. SPY -0.8 to -1.7%, TLT -1.0 to -2.2%, DXY +0.5 to +0.9%
- **Cool Core (-0.1pp vs est):** SPY +0.8 to +1.5%, TLT +1.0 to +1.8%, DXY -0.4 to -0.8%
- **Supercore (services ex-housing) is the real signal:** Sub-0.3% MoM = dovish; >0.4% MoM = hawkish regardless of headline

## Watch for today
The MoM print matters more than YoY (base effects distort YoY). Annualize the 3-month MoM trend for the cleanest read. Shelter disinflation pace and supercore are the Fed's two key concerns post-2024.

---
canonical: "Producer Price Index (PPI) YoY"
short_name: "PPI"
category: "inflation"
country: "US"
release_time_et: "08:30"
frequency: "monthly"
release_source: "BLS"
importance: "tier-1"
fmp_aliases:
  - "Producer Price Index (PPI) YoY"
  - "PPI YoY"
  - "PPI MoM"
---

## What it is
Wholesale price inflation — what producers charge before goods reach consumers. Released ~1 day before or after CPI.

## How it's measured
BLS surveys ~25,000 establishments monthly. "Final demand" PPI (the headline number) covers goods + services + construction sold for final use. Excludes imports (unlike CPI).

## Why it matters
Leading indicator for CPI by ~1–3 months — input cost pressure eventually feeds consumer prices. Healthcare and trade services components of PPI feed directly into the PCE calculation, so traders use PPI to nowcast Core PCE (Fed's preferred gauge).

## Reaction history (60-min after release)
- Smaller market reaction than CPI in isolation (1/3 to 1/2 the move)
- BUT: when PPI and CPI surprise in the same direction same week, reaction is amplified
- Hot PPI: SPY -0.2 to -0.6%, TLT -0.3 to -0.8%, DXY +0.1 to +0.3%
- Watch the trade services and healthcare components for PCE nowcast (drives Friday's PCE algo flow)

## Watch for today
Focus on PPI Final Demand ex-Food/Energy/Trade Services — the BLS "core PPI" used for PCE nowcasts. Healthcare services PPI matters most for the Core PCE algorithm.

---
canonical: "Personal Consumption Expenditures (PCE) Price Index YoY"
short_name: "PCE"
category: "inflation"
country: "US"
release_time_et: "08:30"
frequency: "monthly"
release_source: "BEA"
importance: "tier-1"
fmp_aliases:
  - "PCE Price Index YoY"
  - "Personal Consumption Expenditures (PCE) YoY"
  - "PCE Price Index MoM"
---

## What it is
The Fed's preferred inflation gauge. Tracks prices of all goods and services consumed by households, weighted by *current* spending patterns (CPI uses fixed weights). Released ~2 weeks after CPI, so often a confirmation read rather than a surprise.

## How it's measured
BEA combines CPI data with PPI healthcare/financial services data, then reweights using current consumer spending (so PCE captures substitution effects — if beef gets expensive, consumers buy chicken). Released alongside Personal Income & Spending data, 8:30am ET, last business day of month.

## Why it matters
The Fed targets 2% on Core PCE, not CPI. Every FOMC statement references PCE specifically. Markets often "trade through" PCE because CPI + PPI already telegraphed the print — but a surprise vs. the implied nowcast still moves bonds and the dollar.

## Reaction history (60-min after release)
- **Surprise vs. nowcast (not vs. consensus) matters more:** Algos compute implied PCE from CPI/PPI 2 weeks earlier; deviation from THAT is the trade
- Reaction typically 1/2 the magnitude of CPI for same surprise size
- Releases on month-end — reaction can be amplified by quarter-end rebalancing flows in Mar/Jun/Sep/Dec

## Watch for today
Core PCE 3-month annualized trend. Real spending growth in same release (Personal Spending YoY adjusted for PCE deflator) doubles as a growth read. Services ex-housing PCE is the cleanest cut for Fed cuts/holds.

---
canonical: "Core PCE Price Index YoY"
short_name: "Core PCE"
category: "inflation"
country: "US"
release_time_et: "08:30"
frequency: "monthly"
release_source: "BEA"
importance: "tier-1"
fmp_aliases:
  - "Core PCE Price Index YoY"
  - "Core PCE MoM"
  - "PCE Price Index Excluding Food and Energy YoY"
---

## What it is
PCE excluding food and energy — the single number the Fed targets at 2%. The most-cited inflation gauge in FOMC communications.

## How it's measured
Same methodology as headline PCE, with food (~7%) and energy (~5%) removed. Released by BEA at 8:30am ET on the last business day of each month, alongside Personal Income & Spending.

## Why it matters
*The* number for monetary policy. The 3-month and 6-month annualized rates of Core PCE are explicitly cited in Fed speeches as the path back to 2%. A sustained move below 2.5% on 3-mo annualized opens the door to rate cuts; above 3% keeps the Fed on hold or hiking.

## Reaction history (60-min after release)
- Algos pre-compute Core PCE from CPI + PPI within ~5bps; the trade is the deviation from that nowcast
- Surprise of +0.1pp vs nowcast: TLT -0.5 to -1.2%, DXY +0.2 to +0.4%, gold -0.5 to -1.0%
- Surprise of -0.1pp vs nowcast: TLT +0.5 to +1.2%, equities +0.3 to +0.8%, gold +0.4 to +0.9%
- Reaction larger ahead of FOMC meetings

## Watch for today
3-mo and 6-mo annualized Core PCE — these are what the Fed cites. Supercore PCE (core services ex-housing) is the most reliable signal for the underlying inflation regime.

---
canonical: "Nonfarm Payrolls"
short_name: "NFP"
category: "labor"
country: "US"
release_time_et: "08:30"
frequency: "monthly"
release_source: "BLS"
importance: "tier-1"
fmp_aliases:
  - "Non Farm Payrolls"
  - "Nonfarm Payrolls"
  - "NFP"
  - "Non-Farm Payrolls"
---

## What it is
Monthly net change in US payroll employment, excluding farm workers, military, and household employees. Released as part of the Employment Situation Report alongside Unemployment Rate and Average Hourly Earnings, first Friday of each month.

## How it's measured
BLS Establishment Survey of ~144,000 businesses and government agencies. Seasonal adjustment is heavy and revisions in the next 2 months are routinely ±50K (sometimes ±200K post-COVID). Birth-death model adjusts for new/dying firms not yet in the sample — a key source of noise.

## Why it matters
Labor market is half the Fed's dual mandate. Strong NFP → economy too hot → fewer cuts → yields up, USD up. Weak NFP → recession risk → more cuts → yields down, USD down, equities rally on cut expectations ("bad news is good news") UNTIL print is so weak it signals recession ("bad news is bad news" — typically <50K or negative).

## Reaction history (60-min after release)
- **Strong beat (+100K vs est):** TLT -0.8 to -2.0%, DXY +0.4 to +0.8%, SPY mixed (depends on regime; -0.5% in hiking regime, +0.3% in cutting regime)
- **Big miss (-100K vs est):** TLT +1.0 to +2.0%, DXY -0.4 to -0.8%, SPY +0.3 to +1.0% on Fed cut hopes; flips negative if print suggests recession
- **Revisions to prior 2 months matter as much as current print** — algos sum (current + revisions)

## Watch for today
Three things: (1) headline net of revisions, (2) Unemployment Rate (separate Household Survey — can diverge from NFP for several months), (3) Average Hourly Earnings YoY (wage inflation proxy). When NFP and U-rate disagree, traders weigh U-rate higher because Sahm Rule recession indicator uses U-rate.

---
canonical: "Unemployment Rate"
short_name: "U-Rate"
category: "labor"
country: "US"
release_time_et: "08:30"
frequency: "monthly"
release_source: "BLS"
importance: "tier-1"
fmp_aliases:
  - "Unemployment Rate"
  - "US Unemployment Rate"
---

## What it is
Share of the civilian labor force that is unemployed and actively seeking work. Released with NFP.

## How it's measured
BLS Household Survey of ~60,000 households (different from NFP's Establishment Survey). U-3 is the headline; U-6 (broader: includes underemployed + discouraged workers) is the watched alternative.

## Why it matters
Driver of the **Sahm Rule** — a recession indicator triggered when the 3-mo avg U-rate rises 0.5pp from its 12-mo low. Sahm has correctly identified every US recession since 1948 with no false positives. Markets treat Sahm Rule triggers as the cleanest "recession is here" signal.

## Reaction history (60-min after release)
- **U-rate rises +0.2pp vs est:** TLT +0.6 to +1.4%, SPY -0.3 to +0.8% depending on regime, DXY -0.2 to -0.5%
- **U-rate falls -0.2pp vs est:** TLT -0.5 to -1.2%, DXY +0.3 to +0.6%, SPY mixed
- **Sahm Rule trigger:** Sharp risk-off; SPY -1 to -3% intraday, TLT +1 to +2%, VIX +3 to +5

## Watch for today
Is Sahm Rule active (3-mo avg U-rate minus 12-mo low)? Direction of U-6 — if U-3 holds but U-6 rises, labor market is softening beneath the surface. Labor Force Participation Rate — a rising U-rate driven by participation re-entry is healthier than one driven by job losses.

---
canonical: "Average Hourly Earnings YoY"
short_name: "AHE"
category: "labor"
country: "US"
release_time_et: "08:30"
frequency: "monthly"
release_source: "BLS"
importance: "tier-1"
fmp_aliases:
  - "Average Hourly Earnings YoY"
  - "Average Hourly Earnings MoM"
---

## What it is
Year-over-year change in average hourly pay for private-sector workers. Released with NFP.

## How it's measured
From the Establishment Survey (same source as NFP). Composition-distorted — if the mix of jobs shifts toward higher-paying sectors, AHE rises mechanically without per-worker pay rising. The Atlanta Fed Wage Tracker is a better composition-controlled gauge but only monthly with a lag.

## Why it matters
The Fed watches wage growth as the persistent driver of services inflation. AHE running >4% YoY is the Fed's red flag for wage-price spiral risk. AHE running <3.5% supports the disinflation narrative.

## Reaction history (60-min after release)
- Smaller standalone reaction than NFP, but amplifies the NFP reaction in same direction
- AHE hot + NFP hot = clearest hawkish combo: TLT -1.5 to -2.5%, DXY +0.5 to +1.0%
- AHE cool + U-rate up = clearest dovish combo: TLT +1.0 to +2.0%, SPY +0.5 to +1.5%

## Watch for today
Compare to Atlanta Fed Wage Tracker (released separately, mid-month). 3-mo annualized AHE matters more than YoY. Manufacturing vs. services wage growth split — services wage stickiness is the Fed's stated concern.

---
canonical: "JOLTS Job Openings"
short_name: "JOLTS"
category: "labor"
country: "US"
release_time_et: "10:00"
frequency: "monthly"
release_source: "BLS"
importance: "tier-2"
fmp_aliases:
  - "JOLTs Job Openings"
  - "JOLTS Job Openings"
  - "Job Openings"
---

## What it is
Job Openings and Labor Turnover Survey — reports total job openings, hires, quits, and layoffs. Watched primarily for the **vacancy-to-unemployed ratio** and the **quits rate** (workers voluntarily leaving = confidence proxy).

## How it's measured
BLS surveys ~21,000 business establishments. Released with a one-month lag (e.g. March data in early May). 10:00am ET, first or second Tuesday of the month.

## Why it matters
Fed Chair Powell explicitly cited the vacancy-to-unemployed ratio (peaked at 2.0 in 2022) as evidence of an "overheated" labor market. Quits rate is a leading indicator for wage pressure — high quits means workers see better outside options, forcing employers to raise pay.

## Reaction history (60-min after release)
- Smaller market reaction than NFP (1/3 the size)
- Surprise of +500K openings vs est: TLT -0.3 to -0.6%, DXY +0.1 to +0.3%
- Quits rate falling below 2.0% is the cleanest disinflation signal in the labor market

## Watch for today
Vacancy-to-unemployed ratio (job openings / unemployed persons). 2.0+ = tight, <1.2 = loose. Quits rate trend — declining quits = wage pressure easing. Layoffs ticking up is the early-recession signal.

---
canonical: "Initial Jobless Claims"
short_name: "Claims"
category: "labor"
country: "US"
release_time_et: "08:30"
frequency: "weekly"
release_source: "DOL"
importance: "tier-2"
fmp_aliases:
  - "Initial Jobless Claims"
  - "Jobless Claims"
  - "Continuing Jobless Claims"
---

## What it is
Weekly count of new applications for unemployment benefits. Released every Thursday at 8:30am ET. The most timely labor market indicator — only a 5-day lag.

## How it's measured
State UI offices report new claims to the DOL. Headline figure is seasonally adjusted weekly count; the 4-week moving average smooths noise. Continuing Claims (people still receiving benefits) released same day, lagged one extra week.

## Why it matters
Real-time recession indicator. Initial Claims sustained >300K historically precedes recessions; >400K is recession-confirming. Continuing Claims rising while Initial holds means people aren't finding new jobs — the cleanest "hiring is freezing" signal.

## Reaction history (60-min after release)
- Small standalone reaction; markets care about the 4-week moving average trend and Continuing Claims breakouts
- Initial Claims >250K (well above ~210K trend): TLT +0.2 to +0.5%, SPY +0.1 to +0.3% on dovish read
- Continuing Claims breakout to multi-year highs is the bigger catalyst than Initial

## Watch for today
4-week moving average vs. 6-month trend. Continuing Claims YoY change. Look for state-level surges (Texas, California — large samples) that telegraph national trends. Holiday seasonality (late Dec, early Jan) makes those prints noisy.

---
canonical: "Gross Domestic Product (GDP) QoQ"
short_name: "GDP"
category: "growth"
country: "US"
release_time_et: "08:30"
frequency: "quarterly"
release_source: "BEA"
importance: "tier-1"
fmp_aliases:
  - "GDP Growth Rate QoQ"
  - "GDP QoQ"
  - "GDP Growth Rate"
  - "GDP Advance"
---

## What it is
Total value of all goods and services produced in the US, annualized quarter-over-quarter rate. Released in 3 vintages: Advance (~30 days after quarter end), Second (~60 days), Final (~90 days). Markets primarily react to the Advance estimate.

## How it's measured
BEA combines expenditure-side data (consumer spending, investment, government, net exports) and income-side data. Revisions are routinely ±0.5pp between vintages and ±1pp on annual revisions. Real GDP (inflation-adjusted) is the headline; Nominal GDP is separate.

## Why it matters
Defines whether the economy is growing, slowing, or contracting. Two consecutive negative QoQ prints = technical recession (though NBER uses a broader framework). Markets watch the Atlanta Fed GDPNow nowcast in the 2-3 weeks before release — surprise vs. GDPNow matters more than vs. survey consensus.

## Reaction history (60-min after release)
- **Hot beat (+1pp vs GDPNow):** TLT -0.6 to -1.4%, DXY +0.3 to +0.7%, SPY mixed (regime-dependent)
- **Big miss (-1pp vs GDPNow):** TLT +0.5 to +1.2%, DXY -0.2 to -0.5%, SPY -0.5 to -1.5% on growth scare
- **Composition matters:** Strong inventory build is lower-quality growth; strong consumer + investment is higher-quality

## Watch for today
GDPNow nowcast in the days before release. Real Final Sales to Private Domestic Purchasers ("core GDP") strips inventories and government — the best gauge of underlying demand. GDP Price Deflator (released same time) is the third major US inflation gauge.

---
canonical: "Retail Sales MoM"
short_name: "Retail Sales"
category: "growth"
country: "US"
release_time_et: "08:30"
frequency: "monthly"
release_source: "Census Bureau"
importance: "tier-2"
fmp_aliases:
  - "Retail Sales MoM"
  - "Retail Sales YoY"
  - "Retail Sales Ex Autos MoM"
  - "Core Retail Sales MoM"
---

## What it is
Month-over-month change in total dollar sales at US retail stores and food services. Released mid-month for the prior month. The consumer-spending gauge with the lowest lag (~15 days).

## How it's measured
Census Bureau surveys ~5,500 retail businesses. Headline is nominal (not inflation-adjusted) — so a hot CPI month can produce a hot Retail Sales print mechanically. **Control Group** (excludes autos, gas, building materials, food services) is the cleanest gauge — it feeds directly into PCE / GDP nowcasts.

## Why it matters
Consumer spending = ~70% of US GDP. Retail Sales is the best monthly proxy for consumer health. Watched closely in cycles where recession is feared — a sudden Retail Sales drop is the canonical early warning.

## Reaction history (60-min after release)
- **Strong beat (+0.3pp vs est on Control):** TLT -0.3 to -0.7%, DXY +0.1 to +0.3%, SPY +0.2 to +0.5% ("economy still strong")
- **Big miss (-0.3pp on Control):** TLT +0.3 to +0.8%, DXY -0.2 to -0.4%, SPY -0.3 to -0.8% on growth scare
- Reaction larger after a string of weak labor data (compound recession risk)

## Watch for today
Control Group MoM is the number traders care about (not headline). Inflation-adjusted Retail Sales (Real Retail Sales — separate release) tells whether volume vs. just price is driving the number. Compare to Redbook Weekly Retail Sales for leading signal.

---
canonical: "Industrial Production MoM"
short_name: "IP"
category: "growth"
country: "US"
release_time_et: "09:15"
frequency: "monthly"
release_source: "Federal Reserve"
importance: "tier-2"
fmp_aliases:
  - "Industrial Production MoM"
  - "Industrial Production YoY"
  - "Manufacturing Production MoM"
---

## What it is
Month-over-month change in US output from manufacturing, mining, and utilities. Released mid-month, 9:15am ET. Capacity Utilization released alongside.

## How it's measured
Fed compiles physical output indices (tons of steel, vehicles assembled, megawatt-hours generated). Manufacturing is ~74% of the total. Released by the Federal Reserve, not BLS.

## Why it matters
Manufacturing is the most cyclical sector — IP turns down before headline GDP in recessions. Capacity Utilization >80% historically signals inflationary capacity constraints; <75% signals slack.

## Reaction history (60-min after release)
- Modest standalone reaction (smaller than ISM)
- Persistent IP weakness (3+ months negative MoM) amplifies recession trades: TLT bid, USD bid as safe haven, cyclicals (XLI, XLB) underperform
- Auto production swings can dominate the print (UAW strike effects, model changeovers)

## Watch for today
Manufacturing IP ex-autos is the cleanest signal. Capacity Utilization trend. Cross-reference with ISM Mfg PMI — if both are weak, the manufacturing recession is confirmed.

---
canonical: "Durable Goods Orders MoM"
short_name: "Durables"
category: "growth"
country: "US"
release_time_et: "08:30"
frequency: "monthly"
release_source: "Census Bureau"
importance: "tier-2"
fmp_aliases:
  - "Durable Goods Orders MoM"
  - "Durable Goods Orders Ex Transp MoM"
  - "Core Durable Goods Orders"
---

## What it is
Month-over-month change in new orders for US-manufactured durable goods (intended to last 3+ years). Released late-month for prior month. Boeing/Airbus aircraft orders create huge headline volatility — the ex-transportation number is the signal.

## How it's measured
Census Bureau surveys ~3,700 manufacturers. Headline is hugely volatile due to lumpy aircraft orders. Three key cuts: headline, ex-transportation, and Core Capital Goods Orders (nondefense ex-aircraft) — the last is the business investment proxy.

## Why it matters
Core Capital Goods Orders is the cleanest leading indicator for business investment (CapEx) component of GDP, with a ~6 month lead. A sustained turn down telegraphs weakening business confidence and earnings.

## Reaction history (60-min after release)
- Headline reaction is muted because traders discount aircraft volatility
- Surprise on Core Capital Goods Orders (±0.3pp vs est): TLT ±0.2-0.4%, DXY ±0.1-0.2%
- Reaction larger if confirms ISM Mfg PMI direction

## Watch for today
Core Capital Goods Orders (nondefense ex-aircraft) is the only durable signal. Core Capital Goods Shipments (separate cut, also in this release) feeds directly into GDP equipment investment nowcast.

---
canonical: "ISM Manufacturing PMI"
short_name: "ISM Mfg"
category: "sentiment"
country: "US"
release_time_et: "10:00"
frequency: "monthly"
release_source: "ISM"
importance: "tier-2"
fmp_aliases:
  - "ISM Manufacturing PMI"
  - "ISM Manufacturing Employment"
  - "ISM Manufacturing Prices"
  - "Manufacturing PMI"
---

## What it is
Diffusion index of US manufacturing activity. 50 = neutral; >50 = expansion, <50 = contraction. Released first business day of each month, 10:00am ET. The most timely US business survey — only a 1-day lag to the prior month end.

## How it's measured
ISM surveys ~300 purchasing managers across 18 manufacturing industries. Each respondent answers "better / same / worse" on 10 subcomponents (new orders, production, employment, prices, etc.). Diffusion index = % better + 0.5*% same.

## Why it matters
Leading indicator for manufacturing activity by 1–2 months and for GDP by ~3 months. Sub-50 readings for >3 consecutive months historically signal manufacturing recession. The **Prices Paid** subcomponent is a leading inflation indicator (correlates ~0.7 with CPI MoM 2 months out). **New Orders – Inventories** spread is a directional indicator for production.

## Reaction history (60-min after release)
- **Headline surprise ±3pp vs est:** TLT ±0.3-0.7%, DXY ±0.1-0.3%, SPY ±0.2-0.5%
- Prices Paid jump +5pp: TLT -0.4 to -0.8% on stagflation fears
- Sub-45 readings: Risk-off, recession trade activates
- Above-55 readings + Prices Paid up: Hawkish, stagflation risk

## Watch for today
Four subcomponents matter most: New Orders (leading), Prices Paid (inflation), Employment (jobs), and the New Orders–Inventories spread (production signal). Sub-industry breakdown matters — if only 3-4 of 18 industries are expanding, breadth is weak even if headline is OK.

---
canonical: "ISM Services PMI"
short_name: "ISM Svcs"
category: "sentiment"
country: "US"
release_time_et: "10:00"
frequency: "monthly"
release_source: "ISM"
importance: "tier-2"
fmp_aliases:
  - "ISM Services PMI"
  - "ISM Non-Manufacturing PMI"
  - "Services PMI"
  - "Non-Manufacturing PMI"
---

## What it is
Diffusion index of US services-sector activity. Same methodology as ISM Manufacturing PMI but covering ~70% of the economy. Released third business day of the month, 10:00am ET.

## How it's measured
Survey of ~300 services-sector purchasing managers across 18 industries. Same diffusion-index math as Mfg PMI.

## Why it matters
Services is the larger and stickier part of the economy — services inflation is the Fed's primary concern post-2023. The **Prices** subcomponent in ISM Services correlates with services PCE 2-3 months out. Headline sub-50 is rare and a significant recession signal (services rarely contracts — happened only briefly in 2020 and 2008).

## Reaction history (60-min after release)
- Bigger reaction than ISM Mfg because services drives Fed policy
- **Headline surprise ±3pp vs est:** TLT ±0.5-1.0%, DXY ±0.2-0.5%, SPY ±0.3-0.7%
- Prices Paid component move is the key inflation signal of the month
- Sub-50 reading: Strong risk-off; SPY -0.8 to -2%, TLT +0.8 to +1.5%

## Watch for today
Prices Paid (services inflation proxy). Employment (services hiring is where most US jobs sit). New Orders direction. Diffusion across the 18 subindustries (breadth).

---
canonical: "University of Michigan Consumer Sentiment"
short_name: "U-Mich"
category: "sentiment"
country: "US"
release_time_et: "10:00"
frequency: "monthly"
release_source: "University of Michigan"
importance: "tier-2"
fmp_aliases:
  - "Michigan Consumer Sentiment Prel"
  - "Michigan Consumer Sentiment"
  - "Michigan Consumer Sentiment Final"
  - "Michigan Inflation Expectations"
  - "Michigan 5 Year Inflation Expectations"
---

## What it is
Consumer sentiment survey covering current conditions and expectations. Two releases per month: preliminary (mid-month) and final (end of month). Most important for the **inflation expectations** subcomponents — specifically 1-year and 5-10-year expectations.

## How it's measured
Monthly phone survey of ~500-600 US households. Headline is a diffusion-style index. The inflation expectations component is the survey-based measure the Fed cites — a "unanchoring" of long-run expectations is one of the Fed's stated red lines.

## Why it matters
UMich 5-10 year inflation expectations are the most-watched single number for Fed credibility. If they break above 3.5% sustainably, the Fed loses inflation-targeting credibility and policy gets more restrictive. Preliminary release moves markets more than Final.

## Reaction history (60-min after release)
- Headline sentiment surprise has modest effect (±0.2-0.4% on TLT)
- **5-10yr inflation expectations move ±0.2pp:** TLT ±0.4-0.9%, DXY ±0.2-0.4%, gold reacts inversely
- Preliminary release on the second Friday of month has outsized effect

## Watch for today
5-10 year inflation expectations (the Fed's number). 1-year expectations (more volatile but reflects gas prices). Sentiment-Expectations gap (current minus expectations) is a recession leading indicator when expectations dive below current.

---
canonical: "Conference Board Consumer Confidence"
short_name: "CB Conf"
category: "sentiment"
country: "US"
release_time_et: "10:00"
frequency: "monthly"
release_source: "Conference Board"
importance: "tier-2"
fmp_aliases:
  - "CB Consumer Confidence"
  - "Consumer Confidence"
  - "Conference Board Consumer Confidence"
---

## What it is
Consumer confidence survey alternative to UMich. Released last Tuesday of each month, 10:00am ET. Weighted more toward labor market questions (e.g. "jobs plentiful" vs. "jobs hard to get") than UMich.

## How it's measured
Conference Board mails ~3,000 surveys to US households monthly. Components: Present Situation Index + Expectations Index. "Labor Differential" (jobs plentiful minus jobs hard to get) is a closely-watched leading indicator for the U-rate.

## Why it matters
Less Fed-relevant than UMich (no inflation expectations component) but better for labor market nowcasting. Expectations Index dropping below 80 historically precedes recessions by 6-12 months. Labor Differential turning negative (more people saying jobs hard to get) is the cleanest pre-recession signal.

## Reaction history (60-min after release)
- Smaller market reaction than UMich (1/2 the size)
- Big surprises in Expectations Index move TLT ±0.3-0.6%
- Reaction larger when paired with weak Retail Sales / soft NFP trend

## Watch for today
Labor Differential trend (jobs plentiful minus jobs hard to get). Expectations Index level (below 80 = recession warning). Plans-to-buy (autos, homes, appliances) for forward consumer demand signal.

---
canonical: "Philadelphia Fed Manufacturing Index"
short_name: "Philly Fed"
category: "sentiment"
country: "US"
release_time_et: "08:30"
frequency: "monthly"
release_source: "Federal Reserve Bank of Philadelphia"
importance: "tier-2"
fmp_aliases:
  - "Philadelphia Fed Manufacturing Index"
  - "Philly Fed Manufacturing Survey"
  - "Philly Fed Manufacturing Index"
---

## What it is
Monthly survey of manufacturers in the Philadelphia Fed district. Released third Thursday of the month, 8:30am ET. Diffusion index where 0 = neutral, positive = expansion, negative = contraction.

## How it's measured
Philly Fed surveys ~250 manufacturers. Same diffusion-style structure as ISM but with a 0 (not 50) neutral point. Released mid-month — ahead of ISM Mfg PMI for the same month, so used as a tell.

## Why it matters
Leading indicator for ISM Manufacturing PMI by ~2 weeks. The **6-Month Future Activity** subindex is also closely watched as a forward-looking indicator. **Prices Paid** is another short-leading inflation indicator.

## Reaction history (60-min after release)
- Modest standalone reaction (smaller than ISM)
- Magnitude amplifies when in line with Empire State Manufacturing (released earlier in same week) — the two regional Feds together telegraph national Mfg PMI
- Big swings (±10 points) can move TLT ±0.2-0.4%

## Watch for today
6-Month Future Activity. Prices Paid. New Orders. Read as a leading signal for ISM Mfg PMI due ~10 days later.

---
canonical: "Housing Starts"
short_name: "Starts"
category: "housing"
country: "US"
release_time_et: "08:30"
frequency: "monthly"
release_source: "Census Bureau"
importance: "tier-2"
fmp_aliases:
  - "Housing Starts"
  - "Housing Starts MoM"
---

## What it is
Number of new privately-owned housing units that started construction in the prior month. Released with Building Permits, mid-month, 8:30am ET. Reported as a seasonally-adjusted annual rate (SAAR).

## How it's measured
Census Bureau surveys building permit issuers and contacts builders monthly. Headline figure has ±10% monthly noise from weather, so the 3-month moving average is more reliable.

## Why it matters
Housing is the most interest-rate-sensitive sector. Starts collapsing telegraphs Fed-hike pain reaching the real economy. Starts re-accelerating signals housing-led recovery (and rates-cut transmission working). Single-family vs. multi-family split matters — single-family is more rate-sensitive; multi-family is more capital-flow-sensitive.

## Reaction history (60-min after release)
- Standalone reaction is small
- Building Permits (released same time) is the leading signal — permits lead starts by ~2 months
- Larger reaction in regime changes (e.g. starts spiking after Fed pivots)

## Watch for today
Building Permits direction (the forward-looking number). Single-family vs. multi-family split. Compare to NAHB Homebuilder Sentiment (released a few days earlier) and Existing Home Sales (released ~5 days later) for the housing-market trifecta.

---
canonical: "Building Permits"
short_name: "Permits"
category: "housing"
country: "US"
release_time_et: "08:30"
frequency: "monthly"
release_source: "Census Bureau"
importance: "tier-2"
fmp_aliases:
  - "Building Permits"
  - "Building Permits MoM"
---

## What it is
Number of new housing units authorized for construction. Released with Housing Starts. Leads Starts by ~2 months and Existing Home Sales by ~4-6 months.

## How it's measured
Census Bureau aggregates monthly permit issuances from ~20,000 local permit jurisdictions. SAAR reporting.

## Why it matters
The best forward-looking single-family construction indicator. Permits is in the Conference Board's Leading Economic Index (LEI) and was historically the single best recession-leading indicator pre-2020.

## Reaction history (60-min after release)
- Modest standalone reaction; combined with Starts it amplifies
- Persistent permit declines (3+ months negative MoM) are the cleanest housing-recession signal

## Watch for today
Single-family Permits direction. Regional breakdown (West, South, Midwest, Northeast). Compare YoY change in single-family permits to 30-year mortgage rate trend — the rate-sensitivity correlation is ~-0.8.

---
canonical: "Existing Home Sales"
short_name: "EHS"
category: "housing"
country: "US"
release_time_et: "10:00"
frequency: "monthly"
release_source: "National Association of Realtors"
importance: "tier-2"
fmp_aliases:
  - "Existing Home Sales"
  - "Existing Home Sales MoM"
---

## What it is
Monthly count of US existing single-family homes, townhomes, condos, and co-ops sold. Released ~20 days after month end, 10:00am ET. SAAR reported in millions of units.

## How it's measured
NAR aggregates MLS closing data nationally. Median Sales Price and Months of Supply released alongside.

## Why it matters
Largest segment of the housing market (vs. new home sales). Lagging indicator — reflects mortgage applications from ~60 days ago. Months of Supply <4 = tight (seller's market); >6 = loose. Median Price YoY is one of the cleanest "are home prices rising or falling" reads.

## Reaction history (60-min after release)
- Small market reaction — lagging indicator
- Median Price acceleration affects homebuilder stocks (XHB) and mortgage REITs more than broad market

## Watch for today
Months of Supply (inventory health). Median Price YoY. First-time buyer share (housing affordability proxy).

---
canonical: "FOMC Rate Decision"
short_name: "FOMC"
category: "monetary"
country: "US"
release_time_et: "14:00"
frequency: "8x per year"
release_source: "Federal Reserve"
importance: "tier-1"
fmp_aliases:
  - "Fed Interest Rate Decision"
  - "FOMC Rate Decision"
  - "Fed Funds Rate Decision"
  - "Federal Funds Rate"
---

## What it is
Federal Open Market Committee decision on the target federal funds rate. 8 scheduled meetings per year. Released 2:00pm ET on Wednesday, followed by Powell press conference at 2:30pm ET.

## How it's measured
12-member committee (7 Fed Governors + 5 rotating regional Fed presidents) votes on the target range. Decision plus written statement released at 2:00pm. Powell press conference 30 minutes later. SEP (Summary of Economic Projections / dot plot) released at March, June, September, December meetings only.

## Why it matters
The single highest-impact scheduled event. Every asset class re-prices. Three things matter: (1) the rate decision itself (cut/hold/hike), (2) the statement language changes vs. prior statement ("data dependent" → "prepared to cut" is a huge dovish shift), (3) Powell press conference tone.

## Reaction history (60-min after release)
- **As-expected hold + dovish statement:** TLT +0.5 to +1.5%, SPY +0.3 to +1.0%, DXY -0.2 to -0.5%
- **As-expected hold + hawkish statement:** TLT -0.5 to -1.5%, SPY -0.3 to -1.0%, DXY +0.3 to +0.6%
- **Surprise cut (vs. hold expected):** TLT +1.5 to +3.0%, SPY +1.0 to +2.5%, DXY -0.6 to -1.2%
- **Surprise hike:** Inverse of surprise cut, magnitude similar
- Powell press conference at 2:30pm typically moves markets MORE than the 2:00pm release; reaction often reverses

## Watch for today
Statement language vs. prior statement (the "redline" is crucial). Vote breakdown (any dissents shift dovish/hawkish lean). On SEP meetings: dot plot for terminal rate and 2026/27 path. Powell press conference — watch for specific phrasing on the path to 2% inflation, balance of risks, and any forward guidance.

---
canonical: "FOMC Minutes"
short_name: "Minutes"
category: "monetary"
country: "US"
release_time_et: "14:00"
frequency: "8x per year"
release_source: "Federal Reserve"
importance: "tier-1"
fmp_aliases:
  - "FOMC Minutes"
  - "FOMC Meeting Minutes"
---

## What it is
Detailed minutes of the prior FOMC meeting. Released 3 weeks after each meeting at 2:00pm ET. Reveals the committee's debate, divergent views, and discussion of risks not captured in the statement.

## How it's measured
Fed publishes structured minutes that follow a standard format: economic outlook, financial markets, monetary policy considerations, vote and reasoning.

## Why it matters
Minutes often reveal more dovish or hawkish bias than the statement let on. "Several participants" or "many participants" language matters — the count tells you the lean. Discussion of QT (balance sheet runoff), specific inflation/labor metrics the committee debated, and any pre-commitments to future actions all move markets.

## Reaction history (60-min after release)
- Reaction is typically half the size of the FOMC decision itself but can be sharp
- Hawkish surprise (e.g. discussion of higher-for-longer): TLT -0.4 to -1.0%, DXY +0.2 to +0.5%
- Dovish surprise (discussion of conditions for cuts): TLT +0.4 to +1.0%, SPY +0.2 to +0.6%
- Minutes released into thin afternoon liquidity — reaction can amplify and reverse next morning

## Watch for today
Language counts: how many "several / most / a few" qualifiers and on which positions. Any new discussion of QT pace, regulatory issues, or specific data points the committee is watching. Cross-reference with Fed speakers in the weeks since the meeting — if minutes are dovish-er than recent speeches, the speeches may have been walking back.

---
canonical: "FOMC SEP / Dot Plot"
short_name: "Dot Plot"
category: "monetary"
country: "US"
release_time_et: "14:00"
frequency: "quarterly"
release_source: "Federal Reserve"
importance: "tier-1"
fmp_aliases:
  - "FOMC Economic Projections"
  - "Summary of Economic Projections"
  - "Dot Plot"
---

## What it is
Quarterly release of FOMC member projections for the fed funds rate, GDP, unemployment, and inflation. Released at March, June, September, and December FOMC meetings only — along with the rate decision.

## How it's measured
Each of the 19 FOMC participants submits projections for year-end policy rate (2026, 2027, 2028, longer-run), GDP, U-rate, and PCE inflation. Median dot becomes the consensus path.

## Why it matters
The dot plot is the Fed's most explicit forward guidance. The median dot for year-end implied path is what markets price against. Shifts of even 25bps in the median dot move bond markets sharply.

## Reaction history (60-min after release)
- **Median dot shifts +25bps hawkish vs. prior SEP:** TLT -1.0 to -2.5%, DXY +0.4 to +0.8%, SPY -0.5 to -1.5%
- **Median dot shifts -25bps dovish:** TLT +1.0 to +2.5%, DXY -0.4 to -0.8%, SPY +0.5 to +1.5%
- Dispersion of dots also matters — wide dispersion = uncertain committee

## Watch for today
Median dot for current year, next year, longer-run. Number of dots moving from prior SEP (the dispersion shift). Long-run "neutral" rate — if it drifts up, the Fed thinks the equilibrium rate is higher and current policy is less restrictive than it looks.

---
canonical: "ECB Interest Rate Decision"
short_name: "ECB"
category: "monetary"
country: "EU"
release_time_et: "08:15"
frequency: "6 weeks"
release_source: "European Central Bank"
importance: "global"
fmp_aliases:
  - "ECB Interest Rate Decision"
  - "ECB Rate Decision"
  - "Deposit Facility Rate"
  - "Main Refinancing Rate"
---

## What it is
European Central Bank decision on the Deposit Facility Rate, Main Refinancing Rate, and Marginal Lending Rate. Every ~6 weeks (8x/year). Decision at 8:15am ET, Lagarde press conference at 8:45am ET.

## How it's measured
Governing Council (6 Executive Board members + 14 of 20 rotating NCB governors) decides. Press release + monetary policy statement + Lagarde press conference.

## Why it matters
EUR is the second-largest reserve currency. ECB-Fed divergence drives EUR/USD and (by composition) DXY. ECB cutting while Fed holds = EUR weakness / USD strength = headwind for US mega-cap tech (which has high overseas revenue exposure).

## Reaction history (60-min after release)
- ECB cuts while Fed holds: EUR/USD -0.5 to -1.0%, DXY +0.3 to +0.7%
- Hawkish surprise (no cut when cut priced): EUR/USD +0.4 to +0.9%, DXY -0.2 to -0.5%
- Lagarde press conference at 8:45am often dominates the decision

## Watch for today
Language on "data dependent" vs. pre-commitment. Discussion of services inflation in Europe. Lagarde's framing of the growth-inflation tradeoff. Stoxx and DAX reaction is the cleanest read on the decision's reception in Europe.

---
canonical: "BOJ Interest Rate Decision"
short_name: "BOJ"
category: "monetary"
country: "JP"
release_time_et: "varies (typically 22:00-02:00 prior day)"
frequency: "8x per year"
release_source: "Bank of Japan"
importance: "global"
fmp_aliases:
  - "BoJ Interest Rate Decision"
  - "BOJ Rate Decision"
  - "BoJ Press Conference"
---

## What it is
Bank of Japan monetary policy decision. 8 meetings per year. Release time varies (often Asia-evening US ET, so before US open). Ueda press conference follows ~3 hours later.

## How it's measured
9-member Policy Board (Governor + 2 Deputy + 6 members) votes on policy rate, YCC parameters, JGB purchases.

## Why it matters
JPY is third-largest reserve currency. BOJ policy regime shifts (YCC adjustments, rate hikes from negative territory) are global asset price catalysts via the **carry trade unwind** — hedge funds borrowing JPY to fund equity longs. A hawkish BOJ surprise can crash US equities through forced carry-trade unwinds (Aug 2024 "yen-carry" episode).

## Reaction history (60-min after release)
- Hawkish BOJ surprise (rate hike, YCC tightening): USD/JPY -1 to -3%, Nikkei -2 to -5%, US equities react Asia-overnight — SPX futures -0.5 to -2%, US 10Y yield down (safe haven)
- Dovish hold: muted reaction
- Carry-trade-unwind risk is the tail — Aug 5, 2024 saw VIX +180% in two sessions

## Watch for today
Any YCC changes. Forward guidance on next rate move. Ueda press-conference tone. Cross-reference with USD/JPY level entering meeting — if USD/JPY is at multi-decade highs (>155), MOF intervention threat amplifies BOJ-decision reactions.

---
canonical: "China CPI YoY"
short_name: "China CPI"
category: "inflation"
country: "CN"
release_time_et: "21:30 prior day"
frequency: "monthly"
release_source: "National Bureau of Statistics of China"
importance: "global"
fmp_aliases:
  - "China Inflation Rate YoY"
  - "China CPI YoY"
  - "China CPI MoM"
---

## What it is
China's headline consumer inflation. Released around 9:30pm ET (9:30am Beijing). Often in deflation territory post-2023.

## How it's measured
NBS surveys consumer prices. Pork prices are disproportionately weighted (~3% of CPI alone) and create headline volatility.

## Why it matters
China deflation is global disinflationary force — it suppresses commodity prices and tradable-goods inflation everywhere. Chronic deflation in China is a balance-sheet recession signal a la Japan post-1990. Surprise upside in China CPI tightens global commodity markets (especially copper, iron ore, oil).

## Reaction history (60-min after release — reaction is in Asia hours)
- China CPI surprise positive: copper +0.5 to +1.5%, AUD/USD +0.3 to +0.7%, USD/CNH down
- Persistent China deflation (sub-0%): bearish for global cyclicals (XLB, XLE), bearish AUD, bullish DXY

## Watch for today
Core China CPI (ex food and energy) for underlying signal. PPI direction (China PPI deflation = global goods deflation = US CPI imports cooling). Cross-reference with iron ore, copper, oil reactions overnight.

---
canonical: "China Manufacturing PMI"
short_name: "China PMI"
category: "sentiment"
country: "CN"
release_time_et: "21:00 prior day"
frequency: "monthly"
release_source: "NBS / Caixin"
importance: "global"
fmp_aliases:
  - "NBS Manufacturing PMI"
  - "Caixin Manufacturing PMI"
  - "China Manufacturing PMI"
  - "China NBS Manufacturing PMI"
  - "China Caixin Manufacturing PMI"
---

## What it is
Two separate manufacturing PMI prints for China. **NBS (Official) PMI** released last day of each month, ~9:00pm ET prior day — covers large state-owned enterprises. **Caixin Manufacturing PMI** released first business day of next month, ~9:45pm ET — covers smaller private-sector firms.

## How it's measured
Both use diffusion-index methodology like ISM. NBS surveys ~3,000 firms; Caixin surveys ~500. The two often diverge — NBS tilts state-owned/heavy industry; Caixin tilts private/light industry.

## Why it matters
China manufacturing growth drives global cyclical demand. Both PMIs above 50 = global growth tailwind for commodities, EM equities, and cyclicals. Both below 50 = headwind. The two diverging (one above, one below 50) = mixed signal often resolved by the average.

## Reaction history (60-min after release)
- Strong beat: copper +0.5 to +1.5%, oil +0.3 to +1.0%, AUD/USD +0.3 to +0.6%, US cyclicals (XLB, XLE) green at US open
- Big miss (both below 49): commodities -0.5 to -1.5%, DXY +0.2 to +0.4%, US cyclicals red

## Watch for today
Caixin (private sector) gives a cleaner read on actual demand. NBS is more policy-sensitive (state-owned firms respond to stimulus). Both directions agreeing = high-conviction signal; disagreeing = wait for next month.

---
canonical: "OPEC+ Meeting"
short_name: "OPEC+"
category: "energy"
country: "Global"
release_time_et: "varies (typically 06:00-12:00)"
frequency: "ad-hoc (monthly JMMC + quarterly full meetings)"
release_source: "OPEC Secretariat"
importance: "global"
fmp_aliases:
  - "OPEC Meeting"
  - "OPEC+ Meeting"
  - "JMMC Meeting"
  - "OPEC JMMC Meeting"
---

## What it is
OPEC+ (OPEC plus Russia and other partners) production policy decisions. JMMC (Joint Ministerial Monitoring Committee) meets ~monthly for production reviews; full ministerial meetings quarterly. Decisions released as official statements; reaction is in oil and energy equities.

## How it's measured
OPEC+ ministers vote on collective production quotas + individual country allocations + voluntary cuts. Decisions can be "roll over," "extend cuts," "add cuts," or "unwind cuts."

## Why it matters
OPEC+ controls ~40% of global oil supply and has effective price-setting power in the $70-90/bbl range. Surprise production cuts spike oil; surprise unwinds tank oil. Energy equities (XLE), inflation expectations (10Y breakevens), and Fed rate-cut expectations (gasoline component of CPI) all rip-tide on OPEC decisions.

## Reaction history (15-min after announcement)
- **Surprise additional cuts:** WTI +3 to +6%, XLE +1.5 to +3%, 10Y breakevens +5 to +10bps, TLT mildly lower
- **Surprise unwind / production increase:** WTI -3 to -6%, XLE -2 to -3.5%, breakevens lower, TLT bid
- **As-expected rollover:** muted; <0.5% oil move
- Saudi-Russia tension headlines pre-meeting can move oil more than the decision itself

## Watch for today
Whether decision matches the WSJ/Reuters-sourced pre-meeting leaks (which usually telegraph the outcome). Specifically: voluntary cuts extension dates, Saudi adherence vs. quota cheaters (Iraq, Kazakhstan historically). Cross-reference with US crude inventories (EIA) and SPR refill pace.

---
canonical: "EIA Crude Oil Inventories"
short_name: "EIA Crude"
category: "energy"
country: "US"
release_time_et: "10:30"
frequency: "weekly"
release_source: "US Energy Information Administration"
importance: "global"
fmp_aliases:
  - "EIA Crude Oil Stocks Change"
  - "Crude Oil Inventories"
  - "EIA Crude Oil Inventories"
---

## What it is
Weekly change in US commercial crude oil inventories. Released every Wednesday at 10:30am ET (Thursday if Monday holiday). Counterpart API report released Tuesday evening at 4:30pm ET often serves as a tell.

## How it's measured
EIA surveys US storage facilities, refineries, and pipelines. Reported in millions of barrels. Cushing OK inventories (WTI delivery point) released alongside — closely watched for technical squeezes.

## Why it matters
Largest weekly oil-price catalyst. Surprise build = bearish (more supply than expected); surprise draw = bullish. Cushing-specific moves matter for WTI calendar spread and roll cost.

## Reaction history (10-min after release)
- **Surprise build of 5M+ bbl vs est:** WTI -1 to -3%, XLE -0.5 to -1.5%
- **Surprise draw of 5M+ bbl vs est:** WTI +1 to +3%, XLE +0.5 to +1.5%
- API report Tuesday evening often previews direction; EIA confirmation amplifies or reverses

## Watch for today
Gasoline and distillate inventories (also in this release) — these drive crack spreads. Refinery utilization rate. Cushing inventories — sub-25M bbl is squeeze territory historically.

---
