# The truelift synthetic market

`panel.csv` is a made-up market with a known answer. It powers the quickstart, the CI smoke run and the coverage benchmark (design D14, contract C14). It is a fictional snack brand sold in 8 regions of a fictional country, weekly, over 156 weeks from 2 January 2023. It resembles no real brand or dataset.

Regenerate it, or any other seed, with:

```text
uv run python -m truelift.sample generate --seed 1 --out data/sample
uv run python -m truelift.sample generate-bundle --seeds 1..20 --out build/sample
```

The same seed always gives the same bytes; `truth.yaml` records the panel's sha256. Only seed 1 is committed. The other 19 seeds of the coverage set take under a second to write.

## Columns

| Column | Meaning |
| --- | --- |
| `week` | Monday of the week (ISO date) |
| `region` | `R01` to `R08` |
| `population` | Region size, millions of people |
| `weighted_distribution` | Share of the category's sales made in stores that stock the brand |
| `media_grps` | TV gross rating points that week |
| `holiday` | 1 in the holiday season, the last 6 weeks of each year |
| `season_index` | Seasonal demand level, lowest in January and February |
| `competitor_promo` | Intensity of a competitor's promotion, 0 when there is none |
| `discount_rate` | The brand's discount, as a share of the shelf price (the treatment) |
| `discount_spend` | What the discount cost, in currency units |
| `store_traffic` | Store visits, thousands |
| `revenue` | The brand's sales, in currency units (the outcome) |
| `truth_baseline_revenue` | Ground truth: what the region would have sold that week with no discount |
| `truth_incremental_revenue` | Ground truth: revenue the discount added (`revenue` minus the baseline) |
| `truth_roi` | Ground truth: incremental revenue per unit of spend for that row |

The `truth_` columns are the answer key. They are listed in `truth.yaml` and must never be used as features, CATE covariates or anything sent to a model (contract C4).

## How the data are made

Each region has a size and a level of distribution that drifts slowly. The holiday season and the seasonal index set the level of demand in every region at once.

The brand plans promotions more often in the holiday season and in regions where it has wider distribution, and books TV around planned promotions. When a competitor runs a promotion, the brand discounts more deeply, and its sales drop a little. So the holiday season, the seasonal index, distribution, media and competitor promotions are all **confounders**: each one moves both the discount and sales. About 37% of region-weeks have a discount: 84% of holiday weeks and 23% of low-season weeks. A discount averages about 8% off.

Discount spend is the discount rate times the sales sold on deal (55% of the week's expected sales). Each unit of spend brings in `truth_roi` units of incremental revenue. That ROI depends on the time of year:

- in **holiday weeks** shoppers buy more when prices drop, so the ROI is high;
- in the **low season** (January and February) a discount mostly moves purchases shoppers would have made anyway, so the ROI is **negative**: the brand pays for the discount and sells less over the season than without it;
- in other weeks it sits in between, and each region's ROI differs by up to ±0.3.

Forty percent of the incremental revenue arrives through extra store visits: the discount brings people into stores, and they buy. So `store_traffic` is a **mediator**. It is caused by the discount, and controlling for it hides part of the effect.

Revenue is the baseline plus the incremental revenue, with weekly noise in both sales and store visits.

## The answer for seed 1

The true ROI is money over money: total incremental revenue divided by total discount spend (`truth.yaml`, `true_roi`). For seed 1 it is **2.01**. It differs by segment, which is the heterogeneity the benchmark has to find (G04/A6):

| Segment | True ROI |
| --- | ---: |
| All weeks | 2.01 |
| Holiday weeks | 2.67 |
| Other weeks | 1.60 |
| Low season | -0.53 |

## Why simple regression gets it wrong

Three ordinary least-squares estimates for seed 1, from `truelift.sample.diagnostics` (G04/A3, contract C3):

| Estimate | ROI | Bias |
| --- | ---: | ---: |
| True ROI, from the truth columns | 2.01 | — |
| Naive OLS: revenue on discount spend | 8.08 | +302% |
| OLS with the confounders, fixed effects and segment slopes | 2.13 | +6% |
| The same, plus the mediator `store_traffic` as a control | 1.25 | -38% |

- The **naive** regression credits the discount with sales that the holiday season, wider distribution and bigger regions would have brought anyway. It overstates ROI fourfold.
- The **adjusted** regression controls for every confounder, per head of population, with region and week fixed effects and one ROI for each segment. It matches how the data were made, so it lands close to the truth.
- Adding **`store_traffic`** to the controls removes the 40% of the effect that travels through store visits, so it understates ROI. This is the mediator trap: truelift's identification step blocks a run that controls for a descendant of the discount.

## Switches

- **Hidden confounder** (`--hidden-confounder`). The panel leaves out `competitor_promo`, and `truth.yaml` lists it under `hidden_confounders`. Without it, the adjusted regression on seed 1 reads 1.78 (-11%), because deeper discounts coincide with competitor promotions that also lower sales. truelift should ask for the data, a proxy or an explicit risk acceptance (C3 b).
- **No heterogeneity** (`--no-heterogeneity`). Every row has the same ROI, 1.8.

The default, used for the committed sample, is every confounder observed and heterogeneity on.
