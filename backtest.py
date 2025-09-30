#!/usr/bin/env python3
# backtest.py
#
# Simple multi-factor L/S backtest with common performance metrics.

import argparse
from dataclasses import dataclass
import numpy as np
import pandas as pd

# ---------- Args ----------
def get_args():
    ap = argparse.ArgumentParser(description="Multi-factor long/short backtest")
    ap.add_argument("--csv", default="data/processed/all_data.csv",
                    help="Input merged CSV (date,symbol,price,volume,carry)")
    ap.add_argument("--rebalance", default="M",
                    help="Rebalance frequency ('M' monthly, 'W' weekly, 'D' daily)")
    ap.add_argument("--lookback", type=int, default=60,
                    help="Momentum lookback (trading days)")
    ap.add_argument("--topk", type=float, default=0.20,
                    help="Fraction for long & short buckets (e.g., 0.2 => top 20%% and bottom 20%%)")
    ap.add_argument("--cost_bps", type=float, default=2.0,
                    help="Round-trip cost in basis points per 100%% turnover (applied on weight change)")
    ap.add_argument("--split_date", default=None,
                    help="Optional split date like '2021-01-01' for IS/OOS split. "
                         "If omitted, uses 80/20 split by time.")
    return ap.parse_args()

# ---------- Helpers ----------
def ann_factor(freq="D"):
    return {"D": 252, "W": 52, "M": 12}.get(freq, 252)

def to_rebalance_alias(alias):
    alias = alias.upper()
    if alias.startswith("M"): return "M"
    if alias.startswith("W"): return "W"
    if alias.startswith("D"): return "D"
    return "M"

def cagr(series: pd.Series, periods_per_year=252):
    if series.empty: return np.nan
    tot = series.iloc[-1]
    yrs = len(series) / periods_per_year
    return np.sign(tot) * (abs(tot) ** (1/yrs) - 1) if yrs > 0 and tot > 0 else np.nan

def max_drawdown(equity: pd.Series):
    if equity.empty: return np.nan
    peak = equity.cummax()
    dd = equity/peak - 1.0
    return dd.min()

def sortino_ratio(returns: pd.Series, periods_per_year=252):
    if returns.empty: return np.nan
    downside = returns[returns < 0]
    denom = downside.std(ddof=0)
    if denom == 0 or np.isnan(denom): return np.nan
    return returns.mean() / denom * np.sqrt(periods_per_year)

@dataclass
class Metrics:
    cagr: float
    vol: float
    sharpe: float
    sortino: float
    maxdd: float
    calmar: float
    avg_turnover: float
    tot_cost_bps: float

def summarize(returns: pd.Series, weights: pd.DataFrame, cost_bps_per_abs_weight_change: float, freq_alias="D") -> Metrics:
    periods = ann_factor(freq_alias)
    eq = (1 + returns).cumprod()
    ann_ret = cagr(eq, periods)
    vol = returns.std(ddof=0) * np.sqrt(periods)
    sharpe = (returns.mean() / returns.std(ddof=0) * np.sqrt(periods)) if returns.std(ddof=0) > 0 else np.nan
    sortino = sortino_ratio(returns, periods)
    mdd = max_drawdown(eq)
    calmar = (ann_ret / abs(mdd)) if (mdd is not None and mdd < 0) else np.nan

    # Turnover (sum of |Δweights| / 2 for long/short? We'll just use sum |Δw| across names)
    w_prev = weights.shift(1).fillna(0)
    dW = (weights - w_prev).abs().sum(axis=1)  # daily absolute weight change
    avg_turn = dW.mean()

    # Cost in bps = dW * cost_bps_per_abs_weight_change per day; convert to total bps
    tot_cost_bps = dW.sum() * cost_bps_per_abs_weight_change

    return Metrics(ann_ret, vol, sharpe, sortino, mdd, calmar, avg_turn, tot_cost_bps)

# ---------- Core backtest ----------
def main():
    args = get_args()
    rb = to_rebalance_alias(args.rebalance)
    periods = ann_factor("D")  # data expected daily

    df = pd.read_csv(args.csv)
    # Expected columns already: symbol, date, price, volume, carry
    for col in ["symbol", "date", "price"]:
        if col not in df.columns:
            raise ValueError(f"Missing column '{col}' in {args.csv}")
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["date", "symbol"])

    # Pivot to panel (prices & volume)
    px = df.pivot(index="date", columns="symbol", values="price").sort_index()
    vol = df.pivot(index="date", columns="symbol", values="volume").sort_index()
    carry = df.pivot(index="date", columns="symbol", values="carry").sort_index()

    # Daily returns (close-to-close)
    rets = px.pct_change()

    # Factors
    look = args.lookback
    mom = px.pct_change(look)   # simple L-day momentum
    vol_z = (vol - vol.rolling(look, min_periods=look//2).mean()) / vol.rolling(look, min_periods=look//2).std()
    # carry already level; standardize cross-sectionally each day for comparability
    def zscore_xs(X): 
        mu = X.mean(axis=1)
        sd = X.std(axis=1).replace(0, np.nan)
        return (X.sub(mu, axis=0)).div(sd, axis=0)

    mom_z   = zscore_xs(mom)
    carry_z = zscore_xs(carry)
    vol_z   = zscore_xs(vol_z)

    # Composite score
    score = mom_z.fillna(0) + carry_z.fillna(0) + vol_z.fillna(0)

    # Rebalance schedule
    if rb == "M":
        rb_dates = score.resample("M").last().index
    elif rb == "W":
        rb_dates = score.resample("W-FRI").last().index
    else:
        rb_dates = score.index

    # Build weights each rebalance date: long top k, short bottom k (equal-weight within buckets)
    topk = args.topk
    all_syms = px.columns.tolist()
    weights = pd.DataFrame(0.0, index=score.index, columns=all_syms)

    for dt in rb_dates:
        if dt not in score.index: 
            continue
        s = score.loc[dt].dropna()
        if s.empty: 
            continue
        n = len(s)
        k = max(1, int(np.ceil(topk * n)))
        longs = s.sort_values(ascending=False).head(k).index
        shorts = s.sort_values(ascending=True).head(k).index

        w = pd.Series(0.0, index=all_syms)
        if k > 0:
            w.loc[longs] =  0.5 / k
            w.loc[shorts] = -0.5 / k
        weights.loc[dt] = w

    # Hold weights until next rebalance (forward-fill)
    weights = weights.replace(0, np.nan).ffill().fillna(0.0)
    weights = weights.reindex(rets.index).fillna(0.0)

    # Transaction costs: apply on absolute weight change * cost_per_unit
    # Convert cost from bps to decimal
    cost_per_abs_dW = args.cost_bps / 10000.0
    dW = (weights - weights.shift(1).fillna(0)).abs().sum(axis=1)
    cost = dW * cost_per_abs_dW

    # Portfolio returns (sum w_t-1 * r_t); then subtract costs on rebalance change day
    port_ret_gross = (weights.shift(1) * rets).sum(axis=1).fillna(0.0)
    port_ret = port_ret_gross - cost

    # Equity curve
    equity = (1 + port_ret).cumprod()

    # In-sample / Out-of-sample split
    if args.split_date:
        split_dt = pd.to_datetime(args.split_date)
    else:
        # 80/20 by time
        split_dt = equity.index[int(len(equity) * 0.8)] if len(equity) > 0 else None

    def section(s, start=None, end=None):
        if start is None and end is None: return s
        if start is None: return s.loc[:end]
        if end is None: return s.loc[start:]
        return s.loc[start:end]

    # Metrics overall / IS / OOS
    mx_all = summarize(port_ret, weights, args.cost_bps, "D")
    mx_is  = summarize(section(port_ret, end=split_dt), section(weights, end=split_dt), args.cost_bps, "D") if split_dt is not None else None
    mx_oos = summarize(section(port_ret, start=(split_dt + pd.Timedelta(days=1)) if split_dt is not None else None),
                       section(weights, start=(split_dt + pd.Timedelta(days=1)) if split_dt is not None else None),
                       args.cost_bps, "D") if split_dt is not None else None

    # Volatility regime analysis (based on rolling 21D realized vol of an equal-weight index)
    bench = rets.mean(axis=1).fillna(0.0)
    roll_vol = bench.rolling(21).std() * np.sqrt(252)
    threshold = roll_vol.median()
    low_mask = roll_vol <= threshold
    high_mask = roll_vol > threshold
    mx_low  = summarize(port_ret[low_mask], weights[low_mask], args.cost_bps, "D")
    mx_high = summarize(port_ret[high_mask], weights[high_mask], args.cost_bps, "D")

    # ---------- Report ----------
    def fmt(x, pct=False):
        if x is None or np.isnan(x): return "n/a"
        return f"{x*100:6.2f}%" if pct else f"{x:6.2f}"

    print("\nBacktest Results")
    print("================")
    print(f"Rebalance      : {rb}    | Lookback: {look}d | Top/Bottom: {int(topk*100)}%")
    print(f"Txn Cost       : {args.cost_bps:.2f} bps per 100% abs weight change\n")

    print("Overall")
    print("-------")
    print(f"CAGR           : {fmt(mx_all.cagr, pct=True)}")
    print(f"Vol (ann.)     : {fmt(mx_all.vol,  pct=True)}")
    print(f"Sharpe         : {fmt(mx_all.sharpe)}")
    print(f"Sortino        : {fmt(mx_all.sortino)}")
    print(f"Max Drawdown   : {fmt(mx_all.maxdd, pct=True)}")
    print(f"Calmar         : {fmt(mx_all.calmar)}")
    print(f"Avg Daily Turn : {fmt(mx_all.avg_turnover, pct=True)}")
    print(f"Total Cost     : {fmt(mx_all.tot_cost_bps/10000.0, pct=True)} (equity drag over sample)\n")

    if split_dt is not None:
        print(f"In-Sample (<= {split_dt.date()})")
        print("-------------------------------")
        print(f"CAGR           : {fmt(mx_is.cagr, pct=True)}")
        print(f"Vol (ann.)     : {fmt(mx_is.vol,  pct=True)}")
        print(f"Sharpe         : {fmt(mx_is.sharpe)}")
        print(f"Sortino        : {fmt(mx_is.sortino)}")
        print(f"Max Drawdown   : {fmt(mx_is.maxdd, pct=True)}")
        print(f"Calmar         : {fmt(mx_is.calmar)}\n")

        print(f"Out-of-Sample (>= {(split_dt + pd.Timedelta(days=1)).date()})")
        print("---------------------------------------------")
        print(f"CAGR           : {fmt(mx_oos.cagr, pct=True)}")
        print(f"Vol (ann.)     : {fmt(mx_oos.vol,  pct=True)}")
        print(f"Sharpe         : {fmt(mx_oos.sharpe)}")
        print(f"Sortino        : {fmt(mx_oos.sortino)}")
        print(f"Max Drawdown   : {fmt(mx_oos.maxdd, pct=True)}")
        print(f"Calmar         : {fmt(mx_oos.calmar)}\n")

    print("Volatility Regimes (by rolling 21D bench vol)")
    print("---------------------------------------------")
    print(" Low-Vol Regime")
    print(f"  Sharpe       : {fmt(mx_low.sharpe)}   | CAGR: {fmt(mx_low.cagr, pct=True)}   | MaxDD: {fmt(mx_low.maxdd, pct=True)}")
    print(" High-Vol Regime")
    print(f"  Sharpe       : {fmt(mx_high.sharpe)}  | CAGR: {fmt(mx_high.cagr, pct=True)}  | MaxDD: {fmt(mx_high.maxdd, pct=True)}\n")

    # Quick final line for your spec:
    print("Summary:")
    print(f" Cumulative Return (x): {fmt((1+port_ret).cumprod().iloc[-1], pct=False)}")
    print(f" Annualized Sharpe    : {fmt(mx_all.sharpe)}")

if __name__ == "__main__":
    main()
