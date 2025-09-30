#!/usr/bin/env python3
"""
Merge futures, FRED, and EIA datasets into one analysis-ready CSV.

Output will be: data/processed/all_data.csv
Columns: symbol, date, price, volume, carry
"""

import os
import sys
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(__file__))   # ensures correct relative path
FUTURES_CSV = os.path.join(DATA_DIR, "futures_prices.csv")
FRED_CSV    = os.path.join(DATA_DIR, "fred_wide.csv")
EIA_CSV     = os.path.join(DATA_DIR, "eia_wide.csv")
OUT_CSV     = os.path.join(DATA_DIR, "all_data.csv")

def load_csv(path: str, date_col="date") -> pd.DataFrame | None:
    if not os.path.exists(path):
        print(f"⚠️  Missing {path} — continuing without it.")
        return None
    df = pd.read_csv(path)
    if date_col in df.columns:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    return df

def to_daily_ffill(df: pd.DataFrame, date_col="date") -> pd.DataFrame:
    if df is None or df.empty:
        return df
    df = df.copy().sort_values(date_col)
    full_idx = pd.date_range(df[date_col].min(), df[date_col].max(), freq="D")
    df = df.set_index(date_col).reindex(full_idx)
    df = df.ffill().reset_index().rename(columns={"index": date_col})
    return df

def main():
    futures = load_csv(FUTURES_CSV)   # expected: date,symbol,root,settle
    fred    = load_csv(FRED_CSV)      # date + macro cols
    eia     = load_csv(EIA_CSV)       # date + weekly series

    if futures is None or futures.empty:
        print("❌ futures file missing or empty:", FUTURES_CSV, file=sys.stderr)
        sys.exit(1)

    futures["date"] = pd.to_datetime(futures["date"], errors="coerce")
    futures = futures.dropna(subset=["date"]).sort_values(["date","symbol"])

    if eia is not None and not eia.empty:
        eia = to_daily_ffill(eia, "date")

    macro = None
    if fred is not None and not fred.empty and eia is not None and not eia.empty:
        macro = pd.merge(fred, eia, on="date", how="outer").sort_values("date")
    elif fred is not None and not fred.empty:
        macro = fred.sort_values("date")
    elif eia is not None and not eia.empty:
        macro = eia.sort_values("date")

    merged = futures if macro is None else pd.merge(futures, macro, on="date", how="left")
    merged = merged.sort_values(["date","symbol"]).reset_index(drop=True)

    # ✅ Normalize column names for C++ strategy
    merged = merged.rename(columns={
        "settle": "price",
        "PET.WCRSTUS1.W": "volume",
        "T5YIFR": "carry"
    })
    keep = ["symbol", "date", "price", "volume", "carry"]
    merged = merged[[c for c in keep if c in merged.columns]]

    merged.to_csv(OUT_CSV, index=False)
    print(f"✅ Wrote {OUT_CSV} with {len(merged):,} rows and {len(merged.columns)} columns.")
    print("   Columns:", ", ".join(merged.columns))

if __name__ == "__main__":
    main()


