#!/usr/bin/env python3
"""
Fetch daily futures prices from the Data-Ngin Postgres DB → analysis-ready CSV.

- Auto-detects the OHLCV table & column names (now done in Python, not SQL ANY())
- Filters by commodity roots (CL,RB,GC,...) or by an optional contracts CSV of exact symbols
- Outputs: data/processed/futures_prices.csv with columns: date,symbol,root,settle

Requires:
  - config/.env with PG_URL=postgresql://USER:PASS@HOST:5432/algo_data
  - pip install pandas sqlalchemy python-dotenv psycopg2-binary
"""
import os, re, sys, argparse
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

DEFAULT_ROOTS = ["CL","RB","GC","SI","HG","PL","ZC","ZW","KE","ZS","ZM","ZL","LE","GF","HE","ZR"]

DATE_CANDIDATES   = ["date", "time", "ts_event", "ts", "timestamp"]
SYMBOL_CANDIDATES = ["symbol", "sym", "ticker"]
CLOSE_CANDIDATES  = ["close", "settle", "close_px", "px_close", "last"]

def derive_root(symbol: str) -> str:
    m = re.match(r"^([A-Z]+)", str(symbol).strip().upper())
    return m.group(1) if m else ""

def list_columns(engine):
    q = text("""
        SELECT table_schema, table_name, column_name
        FROM information_schema.columns
        WHERE table_schema NOT IN ('pg_catalog','information_schema')
        ORDER BY table_schema, table_name, ordinal_position
    """)
    with engine.begin() as conn:
        rows = conn.execute(q).fetchall()
    return rows

def score_table(schema, table, cols_lower):
    """Return a tuple used for ranking: lower is better."""
    name = table.lower()
    has_date  = any(any(dc in c for dc in DATE_CANDIDATES) for c in cols_lower)
    has_sym   = any(any(sc in c for sc in SYMBOL_CANDIDATES) for c in cols_lower)
    has_close = any(any(cc in c for cc in CLOSE_CANDIDATES) for c in cols_lower)
    if not (has_date and has_sym and has_close):
        return None
    # preferences: name contains 'ohlcv' first; schema futures_data, then public
    p1 = 0 if "ohlcv" in name else 1
    p2 = 0 if schema == "futures_data" else (1 if schema == "public" else 2)
    return (p1, p2, schema, table)

def autodetect_table_and_cols(engine):
    """
    Inspect information_schema in Python and pick the best candidate table.
    Returns (schema.table, date_col, symbol_col, close_col)
    """
    rows = list_columns(engine)
    by_table = {}
    for schema, table, col in rows:
        key = (schema, table)
        by_table.setdefault(key, []).append(col)

    candidates = []
    for (schema, table), cols in by_table.items():
        cols_lower = [c.lower() for c in cols]
        score = score_table(schema, table, cols_lower)
        if score is None:
            continue
        # pick first matching col names for each role
        def pick(cands):
            for cand in cands:
                for c in cols:
                    if cand in c.lower():
                        return c
            return None
        date_col   = pick(DATE_CANDIDATES)
        symbol_col = pick(SYMBOL_CANDIDATES)
        close_col  = pick(CLOSE_CANDIDATES)
        if date_col and symbol_col and close_col:
            candidates.append((score, schema, table, date_col, symbol_col, close_col))

    if not candidates:
        raise RuntimeError("Could not find a table with date/time, symbol, and close/settle columns.")
    candidates.sort(key=lambda x: x[0])
    _, schema, table, date_col, symbol_col, close_col = candidates[0]
    return f"{schema}.{table}", date_col, symbol_col, close_col

def load_contract_symbols(contracts_csv: str) -> set[str]:
    df = pd.read_csv(contracts_csv)
    cols = {c.lower(): c for c in df.columns}
    if "symbol" in cols:
        return set(df[cols["symbol"]].astype(str).str.upper())
    if "root" in cols:
        return set(df[cols["root"]].astype(str).str.upper())
    raise ValueError("contracts CSV must have a 'symbol' or 'root' column.")

def main():
    ap = argparse.ArgumentParser(description="Export futures prices CSV from Data-Ngin DB.")
    ap.add_argument("--start", default="2015-01-01")
    ap.add_argument("--end",   default="2025-09-01")
    ap.add_argument("--roots", default=",".join(DEFAULT_ROOTS),
                    help="Comma-separated roots (e.g., CL,RB,GC) — ignored if --contracts has symbols.")
    ap.add_argument("--contracts", default="",
                    help="Optional CSV with 'symbol' or 'root' to restrict output.")
    ap.add_argument("--out",   default="data/processed/futures_prices.csv")
    # manual overrides
    ap.add_argument("--table", default="")
    ap.add_argument("--date-col", default="")
    ap.add_argument("--symbol-col", default="")
    ap.add_argument("--close-col",  default="")
    args = ap.parse_args()

    load_dotenv("config/.env")
    pg_url = os.getenv("PG_URL")
    if not pg_url:
        print("❌ PG_URL missing in config/.env", file=sys.stderr); sys.exit(1)

    engine = create_engine(pg_url)

    # choose table/cols
    if args.table and args.date_col and args.symbol_col and args.close_col:
        table, date_col, symbol_col, close_col = args.table, args.date_col, args.symbol_col, args.close_col
    else:
        try:
            table, date_col, symbol_col, close_col = autodetect_table_and_cols(engine)
            print(f"ℹ️ Using {table} (date={date_col}, symbol={symbol_col}, close={close_col})")
        except Exception as e:
            print(f"❌ Autodetect failed: {e}", file=sys.stderr); sys.exit(1)

    # build filter
    symbol_list = None
    if args.contracts:
        syms_or_roots = load_contract_symbols(args.contracts)
        if any(re.search(r"\d", s) for s in syms_or_roots):
            symbol_list = sorted(syms_or_roots)
        else:
            roots = sorted(s.upper() for s in syms_or_roots)
            roots_regex = "^(" + "|".join(roots) + ")"
        print(f"ℹ️ Contracts filter loaded ({len(syms_or_roots)} entries)")
    else:
        roots = [r.strip().upper() for r in args.roots.split(",") if r.strip()]
        roots_regex = "^(" + "|".join(roots) + ")"

    # SQL
    if symbol_list:
        placeholders = ",".join([f":s{i}" for i in range(len(symbol_list))])
        sql = text(f"""
            SELECT {date_col} AS dt, UPPER({symbol_col}) AS sym, {close_col} AS close_px
            FROM {table}
            WHERE {date_col} BETWEEN :start AND :end
              AND UPPER({symbol_col}) IN ({placeholders})
            ORDER BY {date_col}, {symbol_col}
        """)
        params = {"start": args.start, "end": args.end}
        params.update({f"s{i}": v for i, v in enumerate(symbol_list)})
    else:
        sql = text(f"""
            SELECT {date_col} AS dt, UPPER({symbol_col}) AS sym, {close_col} AS close_px
            FROM {table}
            WHERE {date_col} BETWEEN :start AND :end
              AND UPPER({symbol_col}) ~ :regex
            ORDER BY {date_col}, {symbol_col}
        """)
        params = {"start": args.start, "end": args.end, "regex": roots_regex}

    # run
    try:
        with engine.begin() as conn:
            df = pd.read_sql_query(sql, con=conn, params=params)
    except Exception as e:
        print(f"❌ Query failed: {e}", file=sys.stderr); sys.exit(1)

    if df.empty:
        print("⚠️ No rows returned; check dates, table/columns, or filters.", file=sys.stderr); sys.exit(0)

    # normalize + write
    df["date"]   = pd.to_datetime(df["dt"]).dt.date.astype(str)
    df["symbol"] = df["sym"].astype(str)
    df["root"]   = df["symbol"].map(derive_root)
    df["settle"] = pd.to_numeric(df["close_px"], errors="coerce")
    out = df[["date","symbol","root","settle"]].dropna(subset=["settle"]).sort_values(["date","symbol"])

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    out.to_csv(args.out, index=False)
    print(f"✅ Wrote {args.out} with {len(out):,} rows.")

if __name__ == "__main__":
    main()
