"""
Fetch the latest data from the company API and add it to the CSV.

For every company in config.json whose "api" block has "enabled": true, this script
  1. asks the API for the last `days_back` days of data
  2. converts the response to the same columns as the CSV
  3. merges it into the CSV: new days are added, days that already exist are
     replaced by the newer values (today's numbers change during the day)

The CSV is the permanent history; the dashboard is then rebuilt from it by
build_data.py, exactly as before.

The API key is NEVER written in this file or in config.json. It is read from an
environment variable whose name is given in config.json ("key_secret"):
  - on GitHub: a repository secret with that name (see README)
  - locally:   set the variable before running, e.g.
                 Windows (PowerShell):  $env:COMPANY_API_KEY = "your-key"
                 macOS/Linux:           export COMPANY_API_KEY="your-key"
               or in Spyder:  import os; os.environ["COMPANY_API_KEY"] = "your-key"
               (don't save that line in a file you upload)

If the API can't be reached, the script keeps the existing data, prints a
warning, and the dashboard is still rebuilt with the last good data.

>>> The two places you will most likely need to adapt to your API are marked
>>> with "ADAPT": how the request is authenticated, and how the response is read.

Run:  python scripts/fetch_api.py
"""

import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config.json"


# ---------------------------------------------------------------------------
# ADAPT 1: the request
# ---------------------------------------------------------------------------
def request_data(url: str, api_key: str, start: date, end: date) -> object:
    """Call the API and return the decoded JSON."""
    response = requests.get(
        url,
        # Most APIs use one of these; keep the one your API documentation shows.
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
        # headers={"X-API-Key": api_key},
        params={"from": start.isoformat(), "to": end.isoformat()},
        timeout=30,
    )
    response.raise_for_status()  # turns HTTP errors (401, 500, ...) into exceptions
    return response.json()


# ---------------------------------------------------------------------------
# ADAPT 2: reading the response
# ---------------------------------------------------------------------------
def parse_response(payload: object) -> pd.DataFrame:
    """
    Convert the API response into a table with the standard columns
    date, revenue, spending, visits.

    This version expects a JSON list like
        [{"date": "2026-11-01", "revenue": 41234.5, "spending": 28100.0, "visits": 14211}, ...]
    or the same list wrapped as {"data": [...]}. Change the field names below to
    match your API.
    """
    records = payload["data"] if isinstance(payload, dict) and "data" in payload else payload
    df = pd.DataFrame(records)
    df = df.rename(columns={
        "date": "date",          # API field name  ->  standard name
        "revenue": "revenue",
        "spending": "spending",
        "visits": "visits",
    })
    return df[["date", "revenue", "spending", "visits"]]


# ---------------------------------------------------------------------------
# Below here you normally don't need to change anything
# ---------------------------------------------------------------------------
def fetch_with_retry(url, api_key, start, end, attempts=3):
    for i in range(1, attempts + 1):
        try:
            return request_data(url, api_key, start, end)
        except requests.RequestException as err:
            status = getattr(err.response, "status_code", None)
            permanent = status is not None and 400 <= status < 500 and status != 429
            if i == attempts or permanent:  # wrong key / bad URL won't fix itself by retrying
                raise
            wait = 10 * i
            print(f"  attempt {i} failed ({err}); retrying in {wait}s")
            time.sleep(wait)


def merge_into_csv(new: pd.DataFrame, cfg: dict) -> int:
    """Add/replace rows in the company CSV. Returns the number of rows added or changed."""
    cols = cfg["columns"]               # standard name -> CSV column name
    path = ROOT / cfg["file"]

    new = new.copy()
    new["date"] = pd.to_datetime(new["date"]).dt.strftime("%Y-%m-%d")
    for c in ["revenue", "spending", "visits"]:
        new[c] = pd.to_numeric(new[c], errors="coerce")
    new = new.dropna(subset=["date"]).rename(columns=cols)

    if path.exists():
        old = pd.read_csv(path, dtype={cols["date"]: str})
    else:
        old = pd.DataFrame(columns=new.columns)

    merged = (pd.concat([old, new], ignore_index=True)
                .drop_duplicates(subset=cols["date"], keep="last")
                .sort_values(cols["date"])
                .reset_index(drop=True))

    # Count what actually changed so we don't rewrite the file for nothing
    before = old.set_index(cols["date"]).round(2)
    after = merged.set_index(cols["date"]).round(2)
    changed = sum(
        1 for d in new[cols["date"]]
        if d not in before.index or not before.loc[d].equals(after.loc[d])
    )
    if changed:
        merged[cols["visits"]] = merged[cols["visits"]].round().astype("Int64")
        merged.to_csv(path, index=False)
    return changed


def main() -> int:
    config = json.loads(CONFIG.read_text())
    failures = 0
    for cfg in config["companies"]:
        api = cfg.get("api", {})
        if not api.get("enabled"):
            continue
        name = cfg["name"]
        api_key = os.environ.get(api["key_secret"], "").strip()
        if not api_key:
            print(f"::warning::{name}: no API key found in ${api['key_secret']}; skipping.")
            continue

        end = date.today()
        start = end - timedelta(days=api.get("days_back", 7))
        print(f"{name}: fetching {start} → {end}")
        try:
            payload = fetch_with_retry(api["url"], api_key, start, end)
            new = parse_response(payload)
        except Exception as err:  # keep the last good data, but make the failure visible
            failures += 1
            print(f"::warning::{name}: API fetch failed, keeping existing data. {type(err).__name__}: {err}")
            continue

        changed = merge_into_csv(new, cfg)
        print(f"  received {len(new)} rows, {changed} new or changed")

    if failures:
        print(f"{failures} API fetch(es) failed; the dashboard will show the last good data.")
    return 0  # never block the rebuild; failures show up as warnings in the Actions log


if __name__ == "__main__":
    sys.exit(main())
