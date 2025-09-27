#!/usr/bin/env python3
import os, sys, time, argparse
import requests
import pandas as pd
from dotenv import load_dotenv

SERIESID_BASE = "https://api.eia.gov/v2/seriesid"

DEFAULT_SERIES = [
    "PET.WCRSTUS1.W",   # crude stocks
    "PET.WGTSTUS1.W",   # gasoline stocks
    "PET.WDISTUS1.W",   # distillate stocks
    "PET.WCRSUPUS2.W",  # crude supplied (consumption proxy)
]

def fetch_series_v2(series_id: str, api_key: str, start: str, end: str) -> pd.DataFrame:
    url = f"{SERIESID_BASE}/{series_id}"
    params = {"api_key": api_key, "start": start, "end": end}
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            j = r.json()
            break
        except requests.HTTPError as e:
            if 500 <= r.status_code < 600 and attempt < 2:
                time.sleep(1.5 * (attempt + 1)); continue
            raise RuntimeError(f"HTTP {r.status_code} for {series_id}: {e}\n{r.text[:300]}")
        except Exception as e:
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1)); continue
            raise RuntimeError(f"Request failed for {series_id}: {e}")

    data = []
    if isinstance(j, dict):
        resp = j.get("response")
        if isinstance(resp, dict) and isinstance(resp.get("data"), list):
            data = resp["data"]
        elif isinstance(j.get("data"), list):
            data = j["data"]
    if not data:
        return pd.DataFrame(columns=["date","series_id","value"])

    df = pd.DataFrame(data)
    date_col = "period" if "period" in df.columns else ("date" if "date" in df.columns else None)
    if not date_col:
        raise RuntimeError(f"Unexpected payload for {series_id}: {list(df.columns)}")
    df["date"] = pd.to_datetime(df[date_col], errors="coerce").dt.date.astype(str)
    if "value" in df.columns:
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
    else:
        num_cols = [c for c in df.columns if c not in ("period","date") and pd.api.types.is_numeric_dtype(df[c])]
        df["value"] = pd.to_numeric(df[num_cols[0]], errors="coerce") if num_cols else pd.NA
    df["series_id"] = series_id
    return df[["date","series_id","value"]].dropna(subset=["date"])

def main():
    ap = argparse.ArgumentParser(description="Fetch EIA (v2) weekly series → CSVs.")
    ap.add_argument("--series", default=",".join(DEFAULT_SERIES))
    ap.add_argument("--start", default="2015-01-01")
    ap.add_argument("--end",   default="2025-09-01")
    ap.add_argument("--out-long", default="data/processed/eia_long.csv")
    ap.add_argument("--out-wide", default="data/processed/eia_wide.csv")
    args = ap.parse_args()

    load_dotenv("config/.env")
    api_key = os.getenv("EIA_API_KEY")
    if not api_key:
        sys.stderr.write("Missing EIA_API_KEY in config/.env\n"); sys.exit(1)

    series_ids = [s.strip() for s in args.series.split(",") if s.strip()]
    frames = []
    for sid in series_ids:
        try:
            df = fetch_series_v2(sid, api_key, args.start, args.end)
            if df.empty:
                sys.stderr.write(f"No rows for {sid}\n")
            else:
                frames.append(df)
        except Exception as e:
            sys.stderr.write(f"failed {sid}: {e}\n")

    if not frames:
        sys.stderr.write("No data fetched\n"); sys.exit(0)

    long_df = pd.concat(frames, ignore_index=True).dropna(subset=["value"]).sort_values(["date","series_id"])
    wide_df = long_df.pivot(index="date", columns="series_id", values="value").reset_index()
    wide_df.columns = [str(c) for c in wide_df.columns]

    os.makedirs("data/processed", exist_ok=True)
    long_df.to_csv(args.out_long, index=False)
    wide_df.to_csv(args.out_wide, index=False)
    print(f"wrote {args.out_long} ({len(long_df):,} rows)")
    print(f"wrote {args.out_wide} ({len(wide_df):,} rows)")
    print(f"series in wide: {', '.join(c for c in wide_df.columns if c!='date')}")

if __name__ == "__main__":
    main()
