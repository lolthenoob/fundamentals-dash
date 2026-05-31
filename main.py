"""
IT Sector Fundamentals Dashboard
=================================
Auto-downloads data from Yahoo Finance via yfinance.
Saves/updates all ticker data to tickers/fundamentals.db (SQLite).

CONFIGURE YOUR TICKERS HERE:
"""

'TICKERS = ["MSFT", "AAPL", "NVDA", "AVGO", "ORCL", "AMD", "QCOM", "TXN", "ACN", "IBM"]'
'TICKERS = ["MSFT"]'

# How many years of annual history to show
'YEARS_BACK = 11'

# ─────────────────────────────────────────────────────────────────────────────
from ticker_picker import pick_tickers
import warnings
warnings.filterwarnings("ignore")

import csv
import dateutil.parser

import sys
import os
import sqlite3
import json
import numpy as np
import matplotlib
matplotlib.use("TkAgg")          # change to "Qt5Agg" if TkAgg isn't available
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.lines import Line2D
import yfinance as yf
from datetime import datetime
import mplcursors


# ── Colour palette (cycles if more tickers than colours) ─────────────────────
PALETTE = [
    "#00A4EF","#555555","#76B900","#CC0000","#F80000",
    "#ED1C24","#3253DC","#E4002B","#A100FF","#1F70C1",
    "#F59E0B","#10B981","#8B5CF6","#EC4899","#06B6D4",
]

def get_color(i):
    return PALETTE[i % len(PALETTE)]

# ─────────────────────────────────────────────────────────────────────────────
# 1. DATABASE  (tickers/fundamentals.db)
# ─────────────────────────────────────────────────────────────────────────────

_BASE = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
DB_DIR    = os.path.join(_BASE, "tickers")
DB_OUTPUT = os.path.join(_BASE, "output")
DB_PATH = os.path.join(DB_DIR, "fundamentals.db")

def get_db():
    """Return a connection to the SQLite database, creating it if needed."""
    os.makedirs(DB_DIR, exist_ok=True)
    os.makedirs(DB_OUTPUT, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    _create_tables(conn)
    return conn

def _create_tables(conn):
    conn.executescript("""
        -- One row per ticker (live/analyst data)
        CREATE TABLE IF NOT EXISTS tickers (
            symbol          TEXT PRIMARY KEY,
            name            TEXT,
            current_price   REAL,
            analyst_tp      REAL,
            analyst_low     REAL,
            analyst_high    REAL,
            consensus       TEXT,
            last_updated    TEXT
        );

        -- One row per ticker × fiscal year (all per-share fundamentals)
        CREATE TABLE IF NOT EXISTS annual_data (
            symbol          TEXT    NOT NULL,
            fiscal_year     INTEGER NOT NULL,
            price           REAL,
            eps             REAL,
            pe              REAL,
            roe             REAL,
            bvps            REAL,
            debt_assets     REAL,
            ocfps           REAL,
            fcfps           REAL,
            revps           REAL,
            divps           REAL,
            PRIMARY KEY (symbol, fiscal_year),
            FOREIGN KEY (symbol) REFERENCES tickers(symbol)
        );
        CREATE TABLE IF NOT EXISTS etf_data (
            symbol          TEXT    NOT NULL,
            fiscal_year     INTEGER NOT NULL,
            price           REAL,
            distribution    REAL,
            annual_return   REAL,
            PRIMARY KEY (symbol, fiscal_year),
            FOREIGN KEY (symbol) REFERENCES tickers(symbol)
        );
    """)

    conn.commit()

def upsert_ticker(conn, d):
    """
    Insert or replace a ticker's data.
    Called once per successfully downloaded ticker.
    """
    now = datetime.now().isoformat(timespec="seconds")

    conn.execute("""
        INSERT INTO tickers
            (symbol, name, current_price, analyst_tp, analyst_low, analyst_high,
             consensus, last_updated)
        VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(symbol) DO UPDATE SET
            name          = excluded.name,
            current_price = excluded.current_price,
            analyst_tp    = excluded.analyst_tp,
            analyst_low   = excluded.analyst_low,
            analyst_high  = excluded.analyst_high,
            consensus     = excluded.consensus,
            last_updated  = excluded.last_updated
    """, (
        d["symbol"], d["name"], d["current_price"],
        d["analyst_tp"], d["analyst_low"], d["analyst_high"],
        d["consensus"], now,
    ))

    # Upsert each fiscal year row
    rows = zip(
        d["years"],  d["prices"], d["eps"],   d["pe"],
        d["roe"],    d["bvps"],   d["debt_assets"],
        d["ocfps"],  d["fcfps"],  d["revps"],  d["divps"],
    )
    conn.executemany("""
        INSERT INTO annual_data
            (symbol, fiscal_year, price, eps, pe, roe, bvps,
             debt_assets, ocfps, fcfps, revps, divps)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(symbol, fiscal_year) DO UPDATE SET
            price       = excluded.price,
            eps         = excluded.eps,
            pe          = excluded.pe,
            roe         = excluded.roe,
            bvps        = excluded.bvps,
            debt_assets = excluded.debt_assets,
            ocfps       = excluded.ocfps,
            fcfps       = excluded.fcfps,
            revps       = excluded.revps,
            divps       = excluded.divps
    """, [(d["symbol"], yr, p, e, pe, roe, bvps, da, ocf, fcf, rev, div)
          for yr, p, e, pe, roe, bvps, da, ocf, fcf, rev, div in rows])

    conn.commit()
    print(f"    → Saved {d['symbol']} to DB ({len(d['years'])} years)")

def load_ticker_from_db(conn, symbol):
    """
    Reload a previously saved ticker dict from the database.
    Returns None if the symbol isn't stored yet.
    """
    row = conn.execute(
        "SELECT * FROM tickers WHERE symbol = ?", (symbol,)
    ).fetchone()
    if row is None:
        return None

    rows = conn.execute(
        "SELECT * FROM annual_data WHERE symbol = ? ORDER BY fiscal_year",
        (symbol,)
    ).fetchall()
    if not rows:
        return None

    def col(field):
        return [r[field] for r in rows]

    return {
        "symbol":        row["symbol"],
        "name":          row["name"],
        "years":         col("fiscal_year"),
        "prices":        col("price"),
        "eps":           col("eps"),
        "pe":            col("pe"),
        "roe":           col("roe"),
        "bvps":          col("bvps"),
        "debt_assets":   col("debt_assets"),
        "ocfps":         col("ocfps"),
        "fcfps":         col("fcfps"),
        "revps":         col("revps"),
        "divps":         col("divps"),
        "current_price": row["current_price"],
        "analyst_tp":    row["analyst_tp"],
        "analyst_low":   row["analyst_low"],
        "analyst_high":  row["analyst_high"],
        "consensus":     row["consensus"],
    }

def upsert_etf(conn, d):
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute("""
        INSERT INTO tickers (symbol, name, current_price, analyst_tp,
            analyst_low, analyst_high, consensus, last_updated)
        VALUES (?,?,?,NULL,NULL,NULL,?,?)
        ON CONFLICT(symbol) DO UPDATE SET
            name          = excluded.name,
            current_price = excluded.current_price,
            consensus     = excluded.consensus,
            last_updated  = excluded.last_updated
    """, (d["symbol"], d["name"], d["current_price"], "ETF", now))

    conn.executemany("""
        INSERT INTO etf_data (symbol, fiscal_year, price, distribution, annual_return)
        VALUES (?,?,?,?,?)
        ON CONFLICT(symbol, fiscal_year) DO UPDATE SET
            price         = excluded.price,
            distribution  = excluded.distribution,
            annual_return = excluded.annual_return
    """, [(d["symbol"], yr, p, dist, ret)
          for yr, p, dist, ret in zip(
              d["years"], d["prices"], d["distributions"], d["annual_returns"])])
    conn.commit()
    print(f"    → Saved {d['symbol']} (ETF) to DB ({len(d['years'])} years)")


def load_etf_from_db(conn, symbol):
    row = conn.execute(
        "SELECT * FROM tickers WHERE symbol = ?", (symbol,)
    ).fetchone()
    if row is None or row["consensus"] != "ETF":
        return None

    rows = conn.execute(
        "SELECT * FROM etf_data WHERE symbol = ? ORDER BY fiscal_year",
        (symbol,)
    ).fetchall()
    if not rows:
        return None

    return {
        "symbol":        row["symbol"],
        "name":          row["name"],
        "quote_type":    "ETF",
        "years":         [r["fiscal_year"]   for r in rows],
        "prices":        [r["price"]         for r in rows],
        "distributions": [r["distribution"]  for r in rows],
        "annual_returns":[r["annual_return"] for r in rows],
        "current_price": row["current_price"],
        "expense_ratio": None,
        "aum":           None,
        "category":      "",
    }

def print_db_summary(conn):
    """Print a quick summary of what's in the database."""
    tickers = conn.execute(
        "SELECT symbol, name, last_updated FROM tickers ORDER BY symbol"
    ).fetchall()
    if not tickers:
        print("  (database is empty)")
        return
    print(f"  {'Symbol':<8} {'Last Updated':<22} Name")
    print(f"  {'-'*8} {'-'*22} {'-'*30}")
    for t in tickers:
        print(f"  {t['symbol']:<8} {t['last_updated']:<22} {t['name']}")


# ─────────────────────────────────────────────────────────────────────────────
# 1b. DEBUG EXPORTS
# ─────────────────────────────────────────────────────────────────────────────

def export_summary_txt(conn):
    """
    Write tickers/db_summary.txt — the same Symbol / Last Updated / Name
    table that prints to the console, plus a row count footer.
    Overwrites on every run so it always reflects the current DB state.
    """
    path = os.path.join(DB_OUTPUT, "db_summary.txt")
    tickers = conn.execute(
        "SELECT symbol, name, last_updated FROM tickers ORDER BY symbol"
    ).fetchall()
    annual_count = conn.execute("SELECT COUNT(*) FROM annual_data").fetchone()[0]

    with open(path, "w", encoding="utf-8") as f:
        f.write(f"fundamentals.db  —  exported {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 62 + "\n\n")
        f.write(f"  {'Symbol':<8} {'Last Updated':<22} Name\n")
        f.write(f"  {'-'*8} {'-'*22} {'-'*30}\n")
        for t in tickers:
            f.write(f"  {t['symbol']:<8} {t['last_updated']:<22} {t['name']}\n")
        f.write(f"\n  {len(tickers)} tickers  ·  {annual_count} annual rows\n")

    print(f"  → db_summary.txt  ({len(tickers)} tickers)")


def export_full_csv(conn):
    """
    Write tickers/db_full.csv — every annual_data row joined to its
    ticker metadata, one flat row per symbol × fiscal_year.
    Columns: symbol, name, fiscal_year, current_price, analyst_tp,
             analyst_low, analyst_high, consensus, last_updated,
             price, eps, pe, roe, bvps, debt_assets,
             ocfps, fcfps, revps, divps
    Overwrites on every run.
    """
    path = os.path.join(DB_OUTPUT, "db_full.csv")
    rows = conn.execute("""
        SELECT
            t.symbol, t.name, a.fiscal_year,
            t.current_price, t.analyst_tp, t.analyst_low, t.analyst_high,
            t.consensus, t.last_updated,
            a.price, a.eps, a.pe, a.roe, a.bvps, a.debt_assets,
            a.ocfps, a.fcfps, a.revps, a.divps
        FROM annual_data a
        JOIN tickers t ON t.symbol = a.symbol
        ORDER BY t.symbol, a.fiscal_year
    """).fetchall()

    fieldnames = [
        "symbol", "name", "fiscal_year",
        "current_price", "analyst_tp", "analyst_low", "analyst_high",
        "consensus", "last_updated",
        "price", "eps", "pe", "roe", "bvps", "debt_assets",
        "ocfps", "fcfps", "revps", "divps",
    ]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(zip(fieldnames, row)))

    print(f"  → db_full.csv     ({len(rows)} rows)")


# ─────────────────────────────────────────────────────────────────────────────
# 2. DATA DOWNLOAD
# ─────────────────────────────────────────────────────────────────────────────

def safe_row(df, *candidates):
    """Return first matching row from a DataFrame, or None."""
    for name in candidates:
        if name in df.index:
            return df.loc[name]
    return None

def download_ticker(symbol, years_back):
    """
    Pull annual fundamentals + price history from Yahoo Finance.
    Returns a dict with aligned year arrays, or None on failure.
    """
    print(f"  Downloading {symbol} ...", end=" ", flush=True)
    try:
        t = yf.Ticker(symbol)
        info  = t.info
        inc   = t.income_stmt
        bs    = t.balance_sheet
        cf    = t.cashflow
        hist  = t.history(period="max", interval="1mo")

        if inc.empty:
            print("FAILED (no income data)")
            return None

        dates = sorted(inc.columns)[-years_back:]
        years = [d.year for d in dates]

        shares_row = safe_row(inc,
            "Diluted Average Shares", "Basic Average Shares",
            "DilutedAverageShares",   "BasicAverageShares")

        def per_share(row, fallback=None):
            if row is None:
                return [None] * len(dates)
            vals = []
            for d in dates:
                try:
                    total  = float(row[d])
                    shares = float(shares_row[d]) if shares_row is not None else None
                    if shares and shares > 0:
                        vals.append(round(total / shares, 4))
                    elif fallback is not None:
                        vals.append(fallback)
                    else:
                        vals.append(None)
                except Exception:
                    vals.append(None)
            return vals

        eps_row = safe_row(inc,
            "Diluted EPS", "DilutedEPS", "Basic EPS", "BasicEPS")
        if eps_row is not None:
            eps = [round(float(eps_row[d]), 4) if d in eps_row.index and eps_row[d] is not None
                   else None for d in dates]
        else:
            ni_row = safe_row(inc, "Net Income", "NetIncome",
                              "Net Income Common Stockholders")
            eps = per_share(ni_row)

        prices = []
        for yr in years:
            mask = hist.index.year == yr
            sub  = hist[mask]
            if not sub.empty:
                prices.append(round(float(sub["Close"].iloc[-1]), 2))
            else:
                prices.append(None)

        pe = []
        for p, e in zip(prices, eps):
            if p is not None and e and e > 0:
                pe.append(round(p / e, 2))
            else:
                pe.append(None)

        ni_row  = safe_row(inc, "Net Income", "NetIncome",
                           "Net Income Common Stockholders")
        eq_row  = safe_row(bs,
            "Stockholders Equity", "StockholdersEquity",
            "Total Equity Gross Minority Interest",
            "Common Stock Equity")
        roe = []
        for d in dates:
            try:
                ni = float(ni_row[d])
                eq = float(eq_row[d])
                roe.append(round(ni / eq * 100, 2) if eq and eq != 0 else None)
            except Exception:
                roe.append(None)

        bvps = per_share(eq_row)

        debt_row   = safe_row(bs, "Total Debt", "TotalDebt",
                               "Long Term Debt", "LongTermDebt")
        assets_row = safe_row(bs, "Total Assets", "TotalAssets")
        debt_assets = []
        for d in dates:
            try:
                debt   = float(debt_row[d])
                assets = float(assets_row[d])
                debt_assets.append(round(debt / assets, 4) if assets else None)
            except Exception:
                debt_assets.append(None)

        ocf_row  = safe_row(cf,
            "Operating Cash Flow", "OperatingCashFlow",
            "Cash Flow From Continuing Operating Activities")
        capex_row = safe_row(cf,
            "Capital Expenditure", "CapitalExpenditure",
            "Purchase Of PPE", "PurchaseOfPPE")

        ocfps = per_share(ocf_row)
        fcfps = []
        for i2, d in enumerate(dates):
            try:
                ocf   = float(ocf_row[d])
                capex = float(capex_row[d]) if capex_row is not None else 0
                shares = float(shares_row[d]) if shares_row is not None else None
                if shares and shares > 0:
                    fcf = (ocf + capex) / shares
                    fcfps.append(round(fcf, 4))
                else:
                    fcfps.append(None)
            except Exception:
                fcfps.append(None)

        rev_row = safe_row(inc, "Total Revenue", "TotalRevenue", "Revenue")
        revps = per_share(rev_row)

        divs = t.dividends
        divps = []
        for yr in years:
            annual = divs[divs.index.year == yr].sum()
            divps.append(round(float(annual), 4))

        current_price = info.get("currentPrice") or info.get("regularMarketPrice")
        analyst_tp    = info.get("targetMeanPrice")
        analyst_low   = info.get("targetLowPrice")
        analyst_high  = info.get("targetHighPrice")
        consensus     = info.get("recommendationKey", "").replace("_", " ").title()

        print("OK")
        return {
            "symbol":        symbol,
            "name":          info.get("longName", symbol),
            "years":         years,
            "prices":        prices,
            "eps":           eps,
            "pe":            pe,
            "roe":           roe,
            "bvps":          bvps,
            "debt_assets":   debt_assets,
            "ocfps":         ocfps,
            "fcfps":         fcfps,
            "revps":         revps,
            "divps":         divps,
            "current_price": current_price,
            "analyst_tp":    analyst_tp,
            "analyst_low":   analyst_low,
            "analyst_high":  analyst_high,
            "consensus":     consensus,
        }

    except Exception as e:
        print(f"FAILED ({e})")
        return None

def download_etf(symbol):
    """Pull ETF price history and distributions from Yahoo Finance."""
    print(f"  Downloading {symbol} (ETF) ...", end=" ", flush=True)
    try:
        t    = yf.Ticker(symbol)
        info = t.info
        hist = t.history(period="max", interval="1mo")
        divs = t.dividends

        if hist.empty:
            print("FAILED (no price data)")
            return None

        years = sorted(set(hist.index.year))[-YEARS_BACK:]
        prices, distributions, annual_returns = [], [], []

        prev_price = None
        for yr in years:
            mask = hist.index.year == yr
            sub  = hist[mask]
            if not sub.empty:
                p = round(float(sub["Close"].iloc[-1]), 2)
                prices.append(p)
                ret = round((p / prev_price - 1) * 100, 2) if prev_price else None
                annual_returns.append(ret)
                prev_price = p
            else:
                prices.append(None)
                annual_returns.append(None)

            annual_div = divs[divs.index.year == yr].sum()
            distributions.append(round(float(annual_div), 4))

        print("OK")
        return {
            "symbol":       symbol,
            "name":         info.get("longName", symbol),
            "quote_type":   "ETF",
            "years":        years,
            "prices":       prices,
            "distributions": distributions,
            "annual_returns": annual_returns,
            "expense_ratio": info.get("annualReportExpenseRatio") or info.get("expenseRatio"),
            "aum":           info.get("totalAssets"),
            "category":      info.get("category", ""),
            "current_price": info.get("regularMarketPrice") or info.get("currentPrice"),
        }
    except Exception as e:
        print(f"FAILED ({e})")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 3. HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def clean(arr):
    return [np.nan if (v is None or (isinstance(v, float) and np.isnan(v))) else v
            for v in arr]

def latest(arr):
    for v in reversed(arr):
        if v is not None and not np.isnan(v):
            return v
    return np.nan

def year_labels(years):
    return [str(y) for y in years]

def add_zero_line(ax):
    ax.axhline(0, color="#ccc", linewidth=0.8, zorder=0)


# ─────────────────────────────────────────────────────────────────────────────
# 4. PLOT HELPERS
# ─────────────────────────────────────────────────────────────────────────────

STYLE = {
    "font.family":       "monospace",
    "axes.spines.top":   False,
    "axes.spines.right": False,
    "axes.grid":         True,
    "grid.color":        "#f0f0f0",
    "grid.linewidth":    0.8,
    "axes.facecolor":    "white",
    "figure.facecolor":  "white",
    "patch.linewidth":   0,          # kills white seams on all bar charts
    "patch.edgecolor":   "none",
}

def apply_style():
    plt.rcParams.update(STYLE)

def ticker_legend(ax, data_list, colors):
    handles = [Line2D([0],[0], color=c, linewidth=2, label=d["symbol"])
               for d, c in zip(data_list, colors)]
    ax.legend(handles=handles, fontsize=8, framealpha=0.9,
              loc="upper left", ncol=max(1, len(data_list)//5))


# ─────────────────────────────────────────────────────────────────────────────
# 5. INDIVIDUAL-TICKER CHARTS
# ─────────────────────────────────────────────────────────────────────────────

def plot_single_ticker(d, color):
    apply_style()
    fig = plt.figure(figsize=(16, 10), facecolor="white")
    fig.suptitle(f"{d['symbol']} — {d['name']}  |  Fundamentals 2015–2025",
                 fontsize=14, fontweight="bold", y=0.98)

    gs = gridspec.GridSpec(2, 3, figure=fig, hspace=0.45, wspace=0.38)
    yrs  = year_labels(d["years"])
    x    = np.arange(len(yrs))

    ax1 = fig.add_subplot(gs[0, 0])
    ax1.plot(yrs, clean(d["prices"]), color=color, linewidth=2, marker="o", markersize=4)
    if d["current_price"]:
        ax1.axhline(d["current_price"], color=color, linestyle="--", linewidth=1,
                    label=f"Current ${d['current_price']:,.2f}")
    if d["analyst_tp"]:
        ax1.axhline(d["analyst_tp"], color="#888", linestyle=":", linewidth=1,
                    label=f"TP ${d['analyst_tp']:,.2f}")
    ax1.set_title("Share Price ($)", fontsize=10, fontweight="bold")
    ax1.set_xticks(x[::2]); ax1.set_xticklabels(yrs[::2], fontsize=8)
    ax1.legend(fontsize=7)
    add_zero_line(ax1)

    ax2 = fig.add_subplot(gs[0, 1])
    ax2.set_axisbelow(True)
    ax2b = ax2.twinx()
    ax2b.set_axisbelow(True)
    ax2b.grid(False)
    ax2.bar(yrs, clean(d["eps"]), color=color, alpha=0.50, linewidth=0, edgecolor="none", label="EPS ($)")
    ax2b.plot(yrs, clean(d["pe"]), color="#F59E0B", linewidth=2, marker="s", markersize=6, label="P/E")
    ax2.set_title("EPS ($) & P/E Ratio", fontsize=10, fontweight="bold")
    ax2.set_xticks(x[::2]); ax2.set_xticklabels(yrs[::2], fontsize=8)
    ax2.tick_params(axis="y", labelsize=8)
    ax2b.tick_params(axis="y", labelsize=8, colors="#F59E0B")
    ax2b.set_ylabel("P/E", fontsize=8, color="#F59E0B")
    lines = [Line2D([0],[0], color=color, linewidth=6, alpha=0.75, label="EPS ($)"),
             Line2D([0],[0], color="#F59E0B", linewidth=2, label="P/E")]
    ax2.legend(handles=lines, fontsize=7)
    add_zero_line(ax2)

    ax3 = fig.add_subplot(gs[0, 2])
    ax3.set_axisbelow(True)
    ax3b = ax3.twinx()
    ax3b.set_axisbelow(True)
    ax3b.grid(False)

    ax3.bar(yrs, clean(d["bvps"]), color=color, alpha=0.50, linewidth=0, edgecolor="none", label="BV/Share ($)")
    ax3b.plot(yrs, clean(d["roe"]), color="#EF4444", linewidth=2,marker="s", markersize=6, label="ROE (%)")
    ax3.set_title("Book Value/Share & ROE (%)", fontsize=10, fontweight="bold")
    ax3.set_xticks(x[::2]); ax3.set_xticklabels(yrs[::2], fontsize=8)
    ax3.tick_params(axis="y", labelsize=8)
    ax3b.tick_params(axis="y", labelsize=8, colors="#EF4444")
    ax3b.set_ylabel("ROE %", fontsize=8, color="#EF4444")
    lines = [Line2D([0],[0], color=color, linewidth=6, alpha=0.75, label="BV/Sh ($)"),
             Line2D([0],[0], color="#EF4444", linewidth=2, label="ROE (%)")]
    ax3.legend(handles=lines, fontsize=7)
    add_zero_line(ax3)

    ax4 = fig.add_subplot(gs[1, 0])
    ax4.set_axisbelow(True)
    ax4.bar(yrs, clean(d["ocfps"]), color=color, alpha=0.50, linewidth=0, edgecolor="none", label="OCF/Sh ($)")
    ax4.plot(yrs, clean(d["fcfps"]), color="#10B981", linewidth=2.5,
             marker="o", markersize=6, label="FCF/Sh ($)")
    ax4.set_title("OCF/Share & FCF/Share ($)", fontsize=10, fontweight="bold")
    ax4.set_xticks(x[::2]); ax4.set_xticklabels(yrs[::2], fontsize=8)
    ax4.tick_params(axis="y", labelsize=8)
    ax4.legend(fontsize=7)
    add_zero_line(ax4)

    ax5 = fig.add_subplot(gs[1, 1])
    ax5.set_axisbelow(True)
    ax5b = ax5.twinx()
    ax5b.set_axisbelow(True)
    ax5b.grid(False)
    ax5.bar(yrs, clean(d["revps"]), color=color, alpha=0.50, linewidth=0, edgecolor="none", label="Rev/Sh ($)")
    if any(v and v > 0 for v in d["divps"]):
        ax5b.plot(yrs, clean(d["divps"]), color="#7C3AED", linewidth=2.5, marker="D", markersize=6, label="Div/Sh ($)")
        ax5b.tick_params(axis="y", labelsize=8, colors="#8B5CF6")
        ax5b.set_ylabel("Div/Sh ($)", fontsize=8, color="#8B5CF6")
    ax5.set_title("Revenue/Share & Div/Share ($)", fontsize=10, fontweight="bold")
    ax5.set_xticks(x[::2]); ax5.set_xticklabels(yrs[::2], fontsize=8)
    ax5.tick_params(axis="y", labelsize=8)
    lines = [Line2D([0],[0], color=color, linewidth=6, alpha=0.75, label="Rev/Sh ($)"),
             Line2D([0],[0], color="#8B5CF6", linewidth=2, label="Div/Sh ($)")]
    ax5.legend(handles=lines, fontsize=7)
    add_zero_line(ax5)

    ax6 = fig.add_subplot(gs[1, 2])
    da_pct = [v * 100 if v is not None else None for v in d["debt_assets"]]
    ax6.fill_between(yrs, clean(da_pct), alpha=0.35, color=color)
    ax6.plot(yrs, clean(da_pct), color=color, linewidth=2, marker="o", markersize=4)
    ax6.set_title("Debt / Assets (%)", fontsize=10, fontweight="bold")
    ax6.set_xticks(x[::2]); ax6.set_xticklabels(yrs[::2], fontsize=8)
    ax6.tick_params(axis="y", labelsize=8)
    ax6.set_ylim(0, 105)

    consensus_str = d.get("consensus", "")
    tp_str  = f"  TP ${d['analyst_tp']:,.2f}" if d.get("analyst_tp") else ""
    low_str = f"  Low ${d['analyst_low']:,.2f}" if d.get("analyst_low") else ""
    hi_str  = f"  High ${d['analyst_high']:,.2f}" if d.get("analyst_high") else ""
    fig.text(0.5, 0.01,
             f"Analyst Consensus: {consensus_str}{tp_str}{low_str}{hi_str}",
             ha="center", fontsize=9, color="#555", fontfamily="monospace")

    plt.tight_layout(rect=[0, 0.03, 1, 0.97])

    for ax in fig.axes:
        mplcursors.cursor(ax, hover=True)
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# 6. COMPARISON CHARTS
# ─────────────────────────────────────────────────────────────────────────────

def plot_comparison(data_list, colors):
    apply_style()
    fig, axes = plt.subplots(3, 3, figsize=(18, 14), facecolor="white")
    fig.suptitle("All Tickers — Side-by-Side Comparison",
                 fontsize=14, fontweight="bold", y=0.99)

    base_years = data_list[0]["years"]
    yrs = year_labels(base_years)
    x   = np.arange(len(yrs))

    panels = [
        (axes[0,0], "prices",      "Share Price ($)"),
        (axes[0,1], "eps",         "EPS ($)"),
        (axes[0,2], "pe",          "P/E Ratio"),
        (axes[1,0], "ocfps",       "OCF / Share ($)"),
        (axes[1,1], "fcfps",       "FCF / Share ($)"),
        (axes[1,2], "revps",       "Revenue / Share ($)"),
        (axes[2,0], "roe",         "ROE (%)"),
        (axes[2,1], "debt_assets", "Debt / Assets (%)"),
        (axes[2,2], "divps",       "Div / Share ($)"),
    ]

    for ax, field, title in panels:
        for d, col in zip(data_list, colors):
            vals = []
            for yr in base_years:
                if yr in d["years"]:
                    idx = d["years"].index(yr)
                    v = d[field][idx]
                    if field == "debt_assets" and v is not None:
                        v = v * 100
                    vals.append(v)
                else:
                    vals.append(None)
            ax.plot(yrs, clean(vals), color=col, linewidth=1.8,
                    marker="o", markersize=3, label=d["symbol"])
        ax.set_title(title, fontsize=10, fontweight="bold")
        ax.set_xticks(x[::2]); ax.set_xticklabels(yrs[::2], fontsize=8, rotation=30)
        ax.tick_params(axis="y", labelsize=8)
        add_zero_line(ax)
        ticker_legend(ax, data_list, colors)

    plt.tight_layout(rect=[0, 0, 1, 0.97], h_pad=3.0)
    for ax in fig.axes:
        mplcursors.cursor(ax, hover=True)
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# 7. SNAPSHOT BAR CHART
# ─────────────────────────────────────────────────────────────────────────────

def plot_snapshot(data_list, colors):
    apply_style()

    metrics = [
        ("eps",         "EPS ($)",           "$"),
        ("pe",          "P/E Ratio",         "x"),
        ("roe",         "ROE (%)",           "%"),
        ("debt_assets", "Debt/Assets (%)",   "%"),
        ("ocfps",       "OCF/Share ($)",     "$"),
        ("fcfps",       "FCF/Share ($)",     "$"),
        ("revps",       "Revenue/Share ($)", "$"),
        ("divps",       "Div/Share ($)",     "$"),
    ]

    fig, axes = plt.subplots(2, 4, figsize=(18, 9), facecolor="white")
    fig.suptitle("Latest Year — All Tickers Snapshot",
                 fontsize=14, fontweight="bold", y=1.00)

    syms = [d["symbol"] for d in data_list]
    x    = np.arange(len(syms))

    for ax, (field, title, unit) in zip(axes.flat, metrics):
        vals = []
        for d in data_list:
            v = latest(d[field])
            if field == "debt_assets" and not np.isnan(v):
                v = v * 100
            vals.append(v)

        bar_colors = [c if not np.isnan(v) else "#ddd"
                      for c, v in zip(colors, vals)]
        vals_plot = [0 if np.isnan(v) else v for v in vals]
        ax.bar(x, vals_plot, color=bar_colors, alpha=1.0, width=0.6, linewidth=0, edgecolor="none")
        ax.set_xticks(x);
        ax.set_xticklabels(syms, fontsize=11, fontweight="bold", rotation=45, ha="right")
        ax.set_title(title, fontsize=10, fontweight="bold")
        ax.tick_params(axis="y", labelsize=8)
        add_zero_line(ax)
        ax.grid(False)


        for xi, v in enumerate(vals_plot):
            if v == 0:
                continue
            label = f"{v:.1f}" if abs(v) < 1000 else f"{v/1000:.1f}k"
            ax.text(xi, v + (max(vals_plot) * 0.02 if v >= 0 else min(vals_plot) * 0.02),
                    label, ha="center", va="bottom" if v >= 0 else "top",
                    fontsize=11, fontweight="bold", fontfamily="monospace")

    plt.tight_layout()
    for ax in fig.axes:
        mplcursors.cursor(ax, hover=True)
    return fig

def plot_etf(etf_list, colors):
    apply_style()
    n = len(etf_list)
    fig, axes = plt.subplots(1, 3, figsize=(18, 6), facecolor="white")
    fig.suptitle("ETF Overview — Price, Distributions & Annual Return",
                 fontsize=14, fontweight="bold", y=1.01)

    base_years = etf_list[0]["years"]
    yrs = year_labels(base_years)
    x   = np.arange(len(yrs))

    # Panel 1 — Price history
    ax = axes[0]
    for d, col in zip(etf_list, colors):
        vals = []
        for yr in base_years:
            if yr in d["years"]:
                vals.append(d["prices"][d["years"].index(yr)])
            else:
                vals.append(None)
        ax.plot(yrs, clean(vals), color=col, linewidth=2,
                marker="o", markersize=4, label=d["symbol"])
    ax.set_title("Price ($)", fontsize=10, fontweight="bold")
    ax.set_xticks(x[::2]); ax.set_xticklabels(yrs[::2], fontsize=8, rotation=30)
    ticker_legend(ax, etf_list, colors)
    add_zero_line(ax)

    # Panel 2 — Annual distributions
    ax = axes[1]
    width = 0.8 / max(n, 1)
    for idx, (d, col) in enumerate(zip(etf_list, colors)):
        vals = []
        for yr in base_years:
            if yr in d["years"]:
                vals.append(d["distributions"][d["years"].index(yr)])
            else:
                vals.append(0)
        offset = (idx - n / 2 + 0.5) * width
        ax.bar(x + offset, vals, width=width, color=col,
               alpha=0.85, label=d["symbol"], linewidth=0)
    ax.set_title("Annual Distributions ($)", fontsize=10, fontweight="bold")
    ax.set_xticks(x[::2]); ax.set_xticklabels(yrs[::2], fontsize=8, rotation=30)
    ticker_legend(ax, etf_list, colors)
    add_zero_line(ax)

    # Panel 3 — Annual return %
    ax = axes[2]
    for d, col in zip(etf_list, colors):
        vals = []
        for yr in base_years:
            if yr in d["years"]:
                vals.append(d["annual_returns"][d["years"].index(yr)])
            else:
                vals.append(None)
        ax.plot(yrs, clean(vals), color=col, linewidth=2,
                marker="o", markersize=4, label=d["symbol"])
    ax.set_title("Annual Return (%)", fontsize=10, fontweight="bold")
    ax.set_xticks(x[::2]); ax.set_xticklabels(yrs[::2], fontsize=8, rotation=30)
    ticker_legend(ax, etf_list, colors)
    add_zero_line(ax)

    plt.tight_layout()
    for ax in fig.axes:
        mplcursors.cursor(ax, hover=True)
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# 8. MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*60}")
    print(f"\n{'='*60}")
    print(f"  Fundamental Dashboard — starting up")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    conn = get_db()

    print("Database contents before this run:")
    print_db_summary(conn)
    print()


    force_refresh = "--refresh" in sys.argv

    selected, YEARS_BACK = pick_tickers(DB_PATH)
    if not selected:
        print("No tickers selected. Exiting.")
        sys.exit(0)

    stock_list, stock_colors = [], []
    etf_list, etf_colors = [], []

    for i, sym in enumerate(selected):
        col = get_color(i)

        # Check if already known as ETF in DB
        cached_etf = load_etf_from_db(conn, sym)
        if cached_etf and not force_refresh and not is_stale(conn, sym, YEARS_BACK):
            print(f"  {sym}: loaded from DB as ETF")
            etf_list.append(cached_etf)
            etf_colors.append(col)
            continue

        cached = load_ticker_from_db(conn, sym)
        if cached and not force_refresh and not is_stale(conn, sym, YEARS_BACK):
            print(f"  {sym}: loaded from DB (use --refresh to update)")
            stock_list.append(cached)
            stock_colors.append(col)
            continue

        # Need to download — detect type first
        t = yf.Ticker(sym)
        quote_type = t.info.get("quoteType", "EQUITY")

        if quote_type == "ETF":
            d = download_etf(sym)
            if d:
                upsert_etf(conn, d)
                etf_list.append(d)
                etf_colors.append(col)
        else:
            d = download_ticker(sym)
            if d:
                upsert_ticker(conn, d)
                stock_list.append(d)
                stock_colors.append(col)

    # ── Debug exports (always written, reflect full DB state) ─────────────
    print("\nExporting debug files:")
    export_summary_txt(conn)
    export_full_csv(conn)

    conn.close()

    if not stock_list and not etf_list:
        print("\nNo data to display.")
        sys.exit(1)

    all_loaded = [d['symbol'] for d in stock_list] + [d['symbol'] for d in etf_list]
    print(f"\nSuccessfully loaded: {all_loaded}")
    print(f"Database: {DB_PATH}")
    print("Generating charts...\n")

    apply_style()
    figs = []

    for d, col in zip(stock_list, stock_colors):
        figs.append(plot_single_ticker(d, col))

    if len(stock_list) > 1:
        figs.append(plot_comparison(stock_list, stock_colors))
        figs.append(plot_snapshot(stock_list, stock_colors))

    if etf_list:
        figs.append(plot_etf(etf_list, etf_colors))

    if not figs:
        print("\nNo data to display.")
        sys.exit(1)

    print(f"Showing {len(figs)} figure(s). Close each window to continue.")
    plt.show()

def is_stale(conn, symbol, years_back, days=90):
    row = conn.execute(
        "SELECT last_updated FROM tickers WHERE symbol = ?", (symbol,)
    ).fetchone()
    if not row:
        return True

    # Check if we have enough years of data
    count = conn.execute(
        "SELECT COUNT(*) FROM annual_data WHERE symbol = ?", (symbol,)
    ).fetchone()[0]
    if count < years_back:
        return True

    parsed = dateutil.parser.parse(row["last_updated"])
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    age = datetime.now() - parsed
    return age.total_seconds() > days * 86400


if __name__ == "__main__":
    main()