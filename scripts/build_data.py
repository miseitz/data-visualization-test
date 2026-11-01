"""
Turn the raw company CSVs into JSON the dashboard can display.

For every company listed in config.json this script:
  1. reads the CSV and renames its columns to standard names
     (date, revenue, spending, visits) using the mapping in config.json
  2. computes derived values: net = revenue - spending, rolling averages
  3. aggregates to weekly and monthly totals
  4. computes text insights (growth, best/worst month, break-even, ...)
  5. writes site/data/<company-id>.json and site/data/index.json

Run:  python scripts/build_data.py
No AI or external services are involved: it's plain pandas.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config.json"
OUT_DIR = ROOT / "site" / "data"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def load_company(cfg: dict) -> pd.DataFrame:
    cols = cfg["columns"]
    df = pd.read_csv(ROOT / cfg["file"])
    missing = [c for c in cols.values() if c not in df.columns]
    if missing:
        raise ValueError(f"{cfg['file']}: columns not found: {missing}. Check config.json.")

    df = df.rename(columns={v: k for k, v in cols.items()})[list(cols.keys())]
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").drop_duplicates("date", keep="last").set_index("date")

    # Fill gaps in the calendar so rolling windows are true day counts
    df = df.asfreq("D")
    for c in ["revenue", "spending", "visits"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


# ---------------------------------------------------------------------------
# Derived values
# ---------------------------------------------------------------------------
def add_derived(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["net"] = df["revenue"] - df["spending"]
    df["net_30d"] = df["net"].rolling(30, min_periods=15).mean()
    df["visits_7d"] = df["visits"].rolling(7, min_periods=4).mean()
    df["visits_30d"] = df["visits"].rolling(30, min_periods=15).mean()
    df["revenue_30d"] = df["revenue"].rolling(30, min_periods=15).mean()
    df["spending_30d"] = df["spending"].rolling(30, min_periods=15).mean()
    return df


def aggregate(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    g = df.resample(rule)
    out = pd.DataFrame({
        "revenue": g["revenue"].sum(min_count=1),
        "spending": g["spending"].sum(min_count=1),
        "visits": g["visits"].sum(min_count=1),
        "days": g["visits"].count(),
    })
    out["net"] = out["revenue"] - out["spending"]
    out["visits_per_day"] = out["visits"] / out["days"].replace(0, np.nan)
    return out


# ---------------------------------------------------------------------------
# Insights
# ---------------------------------------------------------------------------
def pct(a: float, b: float) -> float | None:
    if b is None or b == 0 or pd.isna(a) or pd.isna(b):
        return None
    return (a - b) / abs(b) * 100


def fmt_money(x: float, cur: str) -> str:
    sign = "−" if x < 0 else ""
    x = abs(x)
    if x >= 1e6:
        return f"{sign}{cur} {x / 1e6:.2f}M"
    if x >= 1e3:
        return f"{sign}{cur} {x / 1e3:.0f}k"
    return f"{sign}{cur} {x:.0f}"


def fmt_pct(p: float | None) -> str:
    if p is None:
        return "n/a"
    return f"{'+' if p >= 0 else '−'}{abs(p):.1f}%"


def compute_insights(df: pd.DataFrame, monthly: pd.DataFrame, cur: str) -> list[dict]:
    insights = []
    end = df.index.max()
    last12 = df[df.index > end - pd.Timedelta(days=365)]
    prev12 = df[(df.index <= end - pd.Timedelta(days=365)) & (df.index > end - pd.Timedelta(days=730))]

    # 1. Net result: last 12 months vs the 12 before
    n_last, n_prev = last12["net"].sum(), prev12["net"].sum()
    margin = n_last / last12["revenue"].sum() * 100 if last12["revenue"].sum() else None
    insights.append({
        "id": "net-12m",
        "title": "Net result, last 12 months",
        "value": fmt_money(n_last, cur),
        "detail": (f"{fmt_pct(pct(n_last, n_prev))} vs the previous 12 months ({fmt_money(n_prev, cur)}). "
                   f"Net margin: {margin:.1f}% of revenue." if margin is not None else ""),
        "tone": "good" if n_last >= 0 else "critical",
    })

    # 2. Break-even: first month after which the 3-month rolling net stayed positive
    roll3 = monthly["net"].rolling(3).sum()
    positive = roll3 > 0
    breakeven = None
    if positive.iloc[-1]:
        # last month where it was <= 0, then the next one
        neg = positive[~positive]
        breakeven = positive.index[0] if neg.empty else positive.index[positive.index > neg.index[-1]][0]
    if breakeven is not None:
        insights.append({
            "id": "breakeven",
            "title": "Sustained profitability since",
            "value": breakeven.strftime("%b %Y"),
            "detail": "The rolling 3-month net result has stayed positive since this month.",
            "tone": "good",
        })
    else:
        insights.append({
            "id": "breakeven",
            "title": "Sustained profitability",
            "value": "Not yet",
            "detail": "The rolling 3-month net result is currently negative.",
            "tone": "critical",
        })

    # 3. Revenue and spending growth
    r_g = pct(last12["revenue"].sum(), prev12["revenue"].sum())
    s_g = pct(last12["spending"].sum(), prev12["spending"].sum())
    insights.append({
        "id": "growth",
        "title": "Revenue growth (12 months, year over year)",
        "value": fmt_pct(r_g),
        "detail": (f"Spending grew {fmt_pct(s_g)} over the same period"
                   + (", so revenue is outgrowing costs." if (r_g or 0) > (s_g or 0)
                      else ", so costs are growing faster than revenue.")),
        "tone": "good" if (r_g or 0) > (s_g or 0) else "warning",
    })

    # 4. App visits growth
    v_g = pct(last12["visits"].mean(), prev12["visits"].mean())
    insights.append({
        "id": "visits",
        "title": "Average daily app visits, last 12 months",
        "value": f"{last12['visits'].mean():,.0f}",
        "detail": f"{fmt_pct(v_g)} vs the previous 12 months ({prev12['visits'].mean():,.0f} per day).",
        "tone": "good" if (v_g or 0) >= 0 else "warning",
    })

    # 5. Revenue per visit
    rpv_last = last12["revenue"].sum() / last12["visits"].sum()
    rpv_prev = prev12["revenue"].sum() / prev12["visits"].sum() if prev12["visits"].sum() else np.nan
    insights.append({
        "id": "rpv",
        "title": "Revenue per app visit",
        "value": f"{cur} {rpv_last:.2f}",
        "detail": f"{fmt_pct(pct(rpv_last, rpv_prev))} vs the previous 12 months ({cur} {rpv_prev:.2f}).",
        "tone": "neutral",
    })

    # 6. Correlation visits ↔ revenue
    corr = df[["visits", "revenue"]].dropna().corr().iloc[0, 1]
    strength = "strong" if corr >= 0.7 else "moderate" if corr >= 0.4 else "weak"
    insights.append({
        "id": "corr",
        "title": "Visits vs revenue",
        "value": f"r = {corr:.2f}",
        "detail": f"There is a {strength} correlation between daily app visits and daily revenue.",
        "tone": "neutral",
    })

    # 7. Best and worst month (complete months only)
    full = monthly[monthly["days"] >= 28]
    best, worst = full["net"].idxmax(), full["net"].idxmin()
    insights.append({
        "id": "best-worst",
        "title": "Best and worst month (net)",
        "value": best.strftime("%b %Y"),
        "detail": (f"Best: {best.strftime('%b %Y')} at {fmt_money(full.loc[best, 'net'], cur)}. "
                   f"Worst: {worst.strftime('%b %Y')} at {fmt_money(full.loc[worst, 'net'], cur)}."),
        "tone": "neutral",
    })

    # 8. Weekend effect
    wk = df.dropna(subset=["visits"])
    weekend = wk[wk.index.dayofweek >= 5]["visits"].mean()
    weekday = wk[wk.index.dayofweek < 5]["visits"].mean()
    insights.append({
        "id": "weekend",
        "title": "Weekend effect on app visits",
        "value": fmt_pct(pct(weekend, weekday)),
        "detail": f"Weekends average {weekend:,.0f} visits per day vs {weekday:,.0f} on weekdays.",
        "tone": "neutral",
    })

    # 9. Loss-making days
    loss_last = (last12["net"] < 0).mean() * 100
    loss_prev = (prev12["net"] < 0).mean() * 100 if len(prev12) else np.nan
    insights.append({
        "id": "loss-days",
        "title": "Loss-making days, last 12 months",
        "value": f"{loss_last:.0f}%",
        "detail": f"Down from {loss_prev:.0f}% in the previous 12 months." if loss_last < loss_prev
                  else f"Up from {loss_prev:.0f}% in the previous 12 months.",
        "tone": "good" if loss_last < loss_prev else "warning",
    })

    return insights


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def series_to_json(df: pd.DataFrame, cols: list[str], decimals: int = 2) -> dict:
    out = {"date": df.index.strftime("%Y-%m-%d").tolist()}
    for c in cols:
        out[c] = [None if pd.isna(v) else round(float(v), decimals) for v in df[c]]
    return out


def build_company(cfg: dict) -> dict:
    cur = cfg.get("currency", "")
    df = add_derived(load_company(cfg))
    weekly = aggregate(df, "W-SUN")  # Monday–Sunday weeks, labelled by their Sunday
    monthly = aggregate(df, "MS")    # months labelled by their first day

    return {
        "id": cfg["id"],
        "name": cfg["name"],
        "currency": cur,
        "start": df.index.min().strftime("%Y-%m-%d"),
        "end": df.index.max().strftime("%Y-%m-%d"),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "daily": series_to_json(df, ["revenue", "spending", "net", "visits", "net_30d",
                                     "visits_7d", "visits_30d", "revenue_30d", "spending_30d"]),
        "weekly": series_to_json(weekly, ["revenue", "spending", "net", "visits", "visits_per_day", "days"]),
        "monthly": series_to_json(monthly, ["revenue", "spending", "net", "visits", "visits_per_day", "days"]),
        "insights": compute_insights(df, monthly, cur),
    }


def main() -> None:
    config = json.loads(CONFIG.read_text())
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index = []
    for cfg in config["companies"]:
        data = build_company(cfg)
        path = OUT_DIR / f"{cfg['id']}.json"
        path.write_text(json.dumps(data, separators=(",", ":"), allow_nan=False))
        index.append({"id": data["id"], "name": data["name"], "start": data["start"], "end": data["end"]})
        print(f"{data['name']}: {data['start']} → {data['end']}  →  {path.relative_to(ROOT)}"
              f"  ({path.stat().st_size / 1024:.0f} KB)")
    (OUT_DIR / "index.json").write_text(json.dumps({"companies": index}, indent=2))


if __name__ == "__main__":
    main()
