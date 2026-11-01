"""
Generate an example CSV with 5 years of daily company data.

Columns: Date, Revenue, Spending, Daily App Visits

The numbers are synthetic but behave like a real business:
- steady growth over time
- yearly seasonality (stronger Q4, weaker summer)
- weekly pattern (more app visits and sales on weekends)
- occasional marketing campaigns: spending spikes, visits and revenue follow
- a few loss-making stretches so the Revenue - Spending chart is interesting

Run:  python scripts/generate_example_csv.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent.parent / "data" / "raw" / "example_company.csv"
END_DATE = "2026-10-29"
YEARS = 5
SEED = 42


def main() -> None:
    rng = np.random.default_rng(SEED)
    end = pd.Timestamp(END_DATE)
    dates = pd.date_range(end - pd.DateOffset(years=YEARS) + pd.Timedelta(days=1), end, freq="D")
    n = len(dates)
    t = np.arange(n) / 365.25  # time in years

    # --- Visits -------------------------------------------------------------
    growth_visits = 4_000 * (1.28 ** t)                       # ~28 % growth / year
    yearly = 1 + 0.12 * np.cos(2 * np.pi * (dates.dayofyear.to_numpy() - 340) / 365.25)  # peak in December
    weekly = np.where(dates.dayofweek.to_numpy() >= 5, 1.18, 0.95)        # weekends busier

    # Marketing campaigns: ~4 per year, 10-21 days each
    campaign = np.zeros(n)
    for start in rng.choice(np.arange(30, n - 30), size=YEARS * 4, replace=False):
        length = rng.integers(10, 22)
        campaign[start:start + length] = 1.0
    # Effect on visits lingers a bit after the campaign ends
    campaign_effect = pd.Series(campaign).rolling(10, min_periods=1).mean().to_numpy()

    visits = growth_visits * yearly * weekly * (1 + 0.35 * campaign_effect)
    visits *= rng.lognormal(0, 0.08, n)
    visits = np.round(visits).astype(int)

    # --- Revenue ------------------------------------------------------------
    revenue_per_visit = 2.4 * (1.04 ** t)                      # monetisation improves slowly
    revenue = visits * revenue_per_visit * rng.lognormal(0, 0.10, n)

    # --- Spending -----------------------------------------------------------
    fixed_costs = 7_500 * (1.12 ** t)                          # salaries, servers, rent
    variable_costs = 0.9 * visits                              # infrastructure / support per visit
    marketing = 1_500 + campaign * rng.uniform(6_000, 11_000, n)
    spending = (fixed_costs + variable_costs + marketing) * rng.lognormal(0, 0.06, n)

    # A rough first year: one big one-off investment quarter
    invest = (t > 0.55) & (t < 0.80)
    spending[invest] *= 1.35

    df = pd.DataFrame({
        "Date": dates.strftime("%Y-%m-%d"),
        "Revenue": revenue.round(2),
        "Spending": spending.round(2),
        "Daily App Visits": visits,
    })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f"Wrote {len(df):,} rows to {OUT}")


if __name__ == "__main__":
    main()
