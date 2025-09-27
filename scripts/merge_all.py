#!/usr/bin/env python3
"""
Merge your processed datasets (futures, FRED, EIA) into one analysis-ready CSV.

Inputs (expected if you've run the fetchers):
  - data/processed/futures_prices.csv     (date,symbol,root,settle)
  - data/processed/fred_wide.csv          (date, DTWEXBGS, T5YIFR[, VIXCLS])
  - data/processed/eia_wide.csv           (date, PET.WCRSTUS1.W, PET.WGTSTUS1.W, PET.WDISTUS1.W, PET.WRPUPUS2.W)

Output (renamed per your request):
  - data/processed/all_data.csv

Behavior:
  - Dates parsed as daily
  - EIA weekly series forward-filled to daily calendar (so daily rows have values)
  - Outer-merge FRED+EIA (macro), then left-join onto per-(date,symbol) futures panel
"""

import os
import sys
import argparse
import pandas as pd

DATA_DIR = "data/processed"
FUTURES_CSV = f"{DATA_DIR}/futures_prices.csv"
FRED_CSV    = f"{DATA_DIR}/fred_wide.csv"
EIA_CSV     = f"{DATA_DIR}/eia_wide.csv"
OUT_CSV     = f"{DATA_DIR}/all_data.csv"

def load_csv(path: str, date_col="date") -> pd.DataFrame | None:
    if not os.path.exists(path):
        print(f"⚠️  Missing {path} — continuing without it.")
        return None
    df = pd.read_csv(path)
    if date_col in df.columns:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    return df

def to_daily_ffill(df: pd.DataFrame, date_col="date") -> pd.DataFrame:
    """
    Reindex to daily and forward-fill. Keeps only date + data columns.
    """
    if df is None or df.empty:
        return df
    df = df.copy()
    df = df.sort_values(date_col)
    # build full daily index
    full_idx = pd.date_range(df[date_col].min(), df[date_col].max(), freq="D")
    df = df.set_index(date_col).reindex(full_idx)  # introduces NaNs on missing days
    df = df.ffill()  # forward-fill weekly values to daily
    df = df.reset_index().rename(columns={"index": date_col})
    return df

def main():
    ap = argparse.ArgumentParser(description="Merge futures + FRED + EIA into one CSV.")
    ap.add_argument("--out", default=OUT_CSV, help="Output CSV path")
    ap.add_argument("--ffill-eia", action="store_true", default=True,
                    help="Forward-fill weekly EIA to daily (default on)")
    ap.add_argument("--no-ffill-eia", dest="ffill_eia", action="store_false",
                    help="Disable forward-fill for EIA")
    args = ap.parse_args()

    # Load
    futures = load_csv(FUTURES_CSV)   # expected columns: date,symbol,root,settle
    fred    = load_csv(FRED_CSV)      # date + macro cols
    eia     = load_csv(EIA_CSV)       # date + weekly series

    # Early exit if we don't even have futures
    if futures is None or futures.empty:
        print("❌ futures file missing or empty:", FUTURES_CSV, file=sys.stderr)
        sys.exit(1)

    # Ensure correct dtypes/sorting
    futures = futures.copy()
    futures["date"] = pd.to_datetime(futures["date"], errors="coerce")
    futures = futures.dropna(subset=["date"]).sort_values(["date","symbol"])

    # Prepare macro: FRED + (optionally ffilled) EIA
    if eia is not None and not eia.empty and args.ffill_eia:
        eia = to_daily_ffill(eia, "date")

    macro = None
    if fred is not None and not fred.empty and eia is not None and not eia.empty:
        macro = pd.merge(fred, eia, on="date", how="outer").sort_values("date")
    elif fred is not None and not fred.empty:
        macro = fred.sort_values("date")
    elif eia is not None and not eia.empty:
        macro = eia.sort_values("date")

    # Merge futures with macro
    merged = futures if macro is None else pd.merge(futures, macro, on="date", how="left")

    # Final tidy-up
    merged = merged.sort_values(["date","symbol"]).reset_index(drop=True)

    os.makedirs(DATA_DIR, exist_ok=True)
    merged.to_csv(args.out, index=False)
    print(f"✅ Wrote {args.out} with {len(merged):,} rows and {len(merged.columns)} columns.")
    # quick preview of columns
    print("   Columns:", ", ".join(merged.columns[:12]) + ("..." if merged.shape[1] > 12 else ""))

if __name__ == "__main__":
    main()
