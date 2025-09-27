#!/usr/bin/env python3
"""
Fetch daily series from FRED and write clean CSVs you can use in backtests.

Defaults pull:
- USD index proxy (FRED broad dollar index): DTWEXBGS  (daily)
- 5y5y inflation expectations:                T5YIFR    (daily)

Outputs:
- data/processed/fred_long.csv   (date, series_id, value)
- data/processed/fred_wide.csv   (date, DTWEXBGS, T5YIFR)

Usage:
  python scripts/fetch_fred.py
  python scripts/fetch_fred.py --start 2015-01-01 --end 2025-09-01
  python scripts/fetch_fred.py --series DTWEXBGS,T5YIFR,T5YIE

Requirements:
  - config/.env with: FRED_API_KEY=your_key_here
  - packages: requests, pandas, python-dotenv
"""
import os, argparse, sys, json
from typing import List, Dict
import requests
import pandas as pd
from dotenv import load_dotenv

FRED_API = "https://api.stlouisfed.org/fred/series/observations"

# default series:
# - DTWEXBGS: Trade Weighted U.S. Dollar Index: Broad, Goods (daily)
# - T5YIFR:  5-Year, 5-Year Forward Inflation Expectation Rate (daily)
DEFAULT_SERIES = ["DTWEXBGS", "T5YIFR"]

def fetch_series(series_id: str, start: str, end: str, api_key: str) -> pd.DataFrame:
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start,
        "observation_end": end,
        "frequency": "d",   # daily if available; FRED will handle if not
        "units": "lin"      # level
    }
    r = requests.get(FRED_API, params=params, timeout=30)
    try:
        r.raise_for_status()
    except Exception as e:
        sys.stderr.write(f"❌ HTTP error for {series_id}: {e}\n{r.text[:300]}\n")
        raise
    data = r.json()
    if "observations" not in data:
        raise RuntimeError(f"Unexpected response for {series_id}: {json.dumps(data)[:300]}")
    obs = pd.DataFrame(data["observations"])
    if obs.empty:
        return pd.DataFrame(columns=["date","series_id","value"])
    # FRED uses 'value' with '.' for missing
    obs["value"] = pd.to_numeric(obs["value"].replace(".", pd.NA), errors="coerce")
    out = obs[["date","value"]].copy()
    out["series_id"] = series_id
    return out[["date","series_id","value"]]

def main():
    parser = argparse.ArgumentParser(description="Fetch FRED series to CSV.")
    parser.add_argument("--start", default="2015-01-01", help="YYYY-MM-DD")
    parser.add_argument("--end",   default="2025-09-01", help="YYYY-MM-DD")
    parser.add_argument("--series", default=",".join(DEFAULT_SERIES),
                        help="Comma-separated FRED series IDs (e.g., DTWEXBGS,T5YIFR)")
    parser.add_argument("--out-long", default="data/processed/fred_long.csv")
    parser.add_argument("--out-wide", default="data/processed/fred_wide.csv")
    args = parser.parse_args()

    load_dotenv("config/.env")
    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        sys.stderr.write("❌ FRED_API_KEY not found in config/.env\n")
        sys.stderr.write("   Add a line like: FRED_API_KEY=your_key_here\n")
        sys.exit(1)

    series_list = [s.strip().upper() for s in args.series.split(",") if s.strip()]
    frames = []
    for sid in series_list:
        try:
            df = fetch_series(sid, args.start, args.end, api_key)
        except Exception as e:
            sys.stderr.write(f"⚠️ Skipping {sid}: {e}\n")
            continue
        frames.append(df)

    if not frames:
        sys.stderr.write("⚠️ No series fetched. Check series IDs / date range / API key.\n")
        sys.exit(0)

    long_df = pd.concat(frames, ignore_index=True)
    long_df["date"] = pd.to_datetime(long_df["date"]).dt.date.astype(str)
    long_df = long_df.dropna(subset=["value"]).sort_values(["date","series_id"])

    # wide pivot
    wide_df = long_df.pivot_table(index="date", columns="series_id", values="value", aggfunc="last").reset_index()
    # ensure columns are simple strings (no pandas CategoricalIndex nonsense)
    wide_df.columns = [c if isinstance(c, str) else str(c) for c in wide_df.columns]

    # write
    os.makedirs("data/processed", exist_ok=True)
    long_df.to_csv(args.out_long, index=False)
    wide_df.to_csv(args.out_wide, index=False)

    print(f"✅ Wrote {args.out_long} (rows: {len(long_df):,})")
    print(f"✅ Wrote {args.out_wide} (rows: {len(wide_df):,})")
    print(f"   columns in wide: {', '.join([c for c in wide_df.columns if c != 'date'])}")

if __name__ == "__main__":
    main()

