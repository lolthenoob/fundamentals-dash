"""
interactive_table.py
────────────────────
Sortable Tkinter table window for the IT Fundamentals Dashboard.
Replaces the static matplotlib table figures for stocks and ETFs.

Public API
----------
show_stock_table(data_list, colors, years_back)  → None  (opens window, non-blocking)
show_etf_table(etf_list,   colors, years_back)   → None  (opens window, non-blocking)
"""

import tkinter as tk
from tkinter import ttk, font as tkfont
import numpy as np


# ── Palette — matches ticker_picker / main.py ─────────────────────────────────
CLR_ACCENT   = "#00A4EF"
CLR_BG       = "#F7F9FC"
CLR_HDR_BG   = "#E8F4FD"
CLR_ROW_A    = "#FFFFFF"
CLR_ROW_B    = "#EFF4FA"
CLR_TEXT     = "#1A1A2E"
CLR_SUBTEXT  = "#555577"
CLR_GREEN    = "#D4EDDA"
CLR_YELLOW   = "#FFF3CD"
CLR_RED      = "#F8D7DA"
CLR_NEUTRAL  = "#F0F0F0"
CLR_NAME     = "#EAF4FB"

FG_GREEN  = "#155724"
FG_RED    = "#721C24"
FG_GREY   = "#AAAAAA"


# ── Helpers shared between stock and ETF builders ─────────────────────────────

def _latest(values):
    """Return the last non-None value, or np.nan."""
    for v in reversed(values):
        if v is not None:
            return float(v)
    return np.nan


def _avg_last_n(values, n):
    clean = [v for v in values if v is not None]
    subset = clean[-n:]
    return round(sum(subset) / len(subset), 2) if subset else None


def _eps_cagr(eps_list, years_list):
    pairs = [(y, e) for y, e in zip(years_list, eps_list) if e is not None and e > 0]
    if len(pairs) < 2:
        return None
    n = pairs[-1][0] - pairs[0][0]
    if n <= 0:
        return None
    return round(((pairs[-1][1] / pairs[0][1]) ** (1 / n) - 1) * 100, 1)


def _cagr(prices, n):
    clean = [p for p in prices if p is not None]
    if len(clean) < n + 1:
        return None
    end, start = clean[-1], clean[-(n + 1)]
    if start is None or end is None or start <= 0:
        return None
    return round(((end / start) ** (1 / n) - 1) * 100, 2)

def _shorten_etf_name(name):
    """Strip boilerplate from well-known ETF name templates."""
    import re
    # State Street SPDR sector ETFs — extract the sector keyword(s)
    m = re.search(r'State Street (.+?) Select Sector', name)
    if m:
        return "SPDR " + m.group(1)
    # Vanguard — prefix with VG and strip Index Fund / ETF suffix boilerplate
    m = re.search(r'Vanguard (.+?)(?:\s+Index Fund|\s+ETF)', name)
    if m:
        return "VG " + m.group(1)
    # iShares — prefix with iSh and strip ETF suffix
    m = re.search(r'iShares (.+?)(?:\s+ETF)', name)
    if m:
        return "iSh " + m.group(1)
    return name


# ── Core sortable table window ────────────────────────────────────────────────

class SortableTable:
    """
    Generic sortable table window.

    Parameters
    ----------
    title       : window title string
    columns     : list of column-id strings  (used internally)
    headings    : list of display headings   (same order as columns)
    rows        : list of dicts  {col_id: (display_str, sort_key, bg_colour)}
    row_labels  : list of ticker symbols shown in the first frozen column
    min_col_w   : minimum column width in pixels
    """

    def __init__(self, title, columns, headings, rows, row_labels,
                 min_col_w=90):
        self.columns    = columns
        self.headings   = headings
        self.rows       = rows            # list of dicts col→(text,key,bg)
        self.row_labels = row_labels
        self.min_col_w  = min_col_w
        self._sort_col  = None
        self._sort_asc  = False           # start descending on first click

        self.root = tk.Toplevel()
        self.root.title(title)
        self.root.configure(bg=CLR_BG)
        self.root.resizable(True, True)

        # ── Fonts
        mono      = tkfont.Font(family="Consolas", size=12)
        hdr_bold  = tkfont.Font(family="Consolas", size=16, weight="bold")
        hdr_sub   = tkfont.Font(family="Consolas", size=12)

        # ── Header banner
        hdr = tk.Frame(self.root, bg=CLR_ACCENT, pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text=title, bg=CLR_ACCENT, fg="white",
                 font=hdr_bold).pack()
        tk.Label(hdr, text="Click any column header to sort  ▲▼",
                 bg=CLR_ACCENT, fg="#D0EEFF", font=hdr_sub).pack()

        # ── Treeview inside a scrollable frame
        frame = tk.Frame(self.root, bg=CLR_BG)
        frame.pack(fill="both", expand=True, padx=14, pady=10)

        vsb = ttk.Scrollbar(frame, orient="vertical")
        hsb = ttk.Scrollbar(frame, orient="horizontal")
        vsb.pack(side="right",  fill="y")
        hsb.pack(side="bottom", fill="x")

        # Treeview — first visible column is "#0" (tree column = ticker symbol)
        all_cols = tuple(columns)
        self.tv = ttk.Treeview(
            frame,
            columns=all_cols,
            show="tree headings",
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set,
        )
        self.tv.pack(fill="both", expand=True)
        vsb.config(command=self.tv.yview)
        hsb.config(command=self.tv.xview)

        # Tree column (ticker symbol)
        self.tv.heading("#0", text="Ticker",
                        command=lambda: self._sort_by("#0"))
        self.tv.column("#0", width=100, minwidth=80, stretch=False, anchor="center")

        # Data columns
        for col, hd in zip(columns, headings):
            self.tv.heading(col, text=hd,
                            command=lambda c=col: self._sort_by(c))
            self.tv.column(col, width=max(min_col_w, len(hd) * 11),
                           minwidth=80, anchor="center")

        # ── Tag colours for cell backgrounds
        # Treeview only supports per-row tags natively; we fake per-cell
        # colouring via row striping + a separate approach: we draw one
        # dominant colour per row (the most important signal column).
        # For proper per-cell colour we embed the colour logic into the
        # text itself using a custom draw approach — but that needs
        # tkinter canvas hacks.  Instead: tag each row with its stripe
        # colour and show per-cell colour as a suffix badge in the text.
        # Actually: ttk.Treeview supports per-row tags only.
        # We apply a simplified scheme: alternate stripe + bold header.
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview",
                        background=CLR_ROW_A,
                        fieldbackground=CLR_ROW_A,
                        foreground=CLR_TEXT,
                        font=("Consolas", 15),
                        rowheight=44)
        style.configure("Treeview.Heading",
                        background=CLR_HDR_BG,
                        foreground=CLR_TEXT,
                        font=("Consolas", 15, "bold"),
                        relief="flat")
        style.map("Treeview.Heading",
                  background=[("active", CLR_ACCENT)],
                  foreground=[("active", "white")])
        style.map("Treeview",
                  background=[("selected", CLR_ACCENT)],
                  foreground=[("selected", "white")])

        self.tv.tag_configure("odd",  background=CLR_ROW_A)
        self.tv.tag_configure("even", background=CLR_ROW_B)

        # Per-cell colouring tags — we apply colour to the *text* of cells
        # by encoding a colour indicator emoji prefix (▲ green / ▼ red / — neutral)
        # This is the cleanest approach without custom canvas rendering.
        # (Full per-cell colour would require replacing Treeview with a Canvas grid.)

        self._populate(self.rows, self.row_labels)

        # ── Status bar
        self._status_var = tk.StringVar(value=f"{len(rows)} rows")
        tk.Label(self.root, textvariable=self._status_var,
                 bg=CLR_BG, fg=CLR_SUBTEXT,
                 font=("Consolas", 13), anchor="w",
                 padx=14).pack(fill="x", pady=(0, 6))

    def _populate(self, rows, row_labels):
        """Clear tree and insert rows with alternating stripe tags."""
        for item in self.tv.get_children():
            self.tv.delete(item)

        for i, (label, row) in enumerate(zip(row_labels, rows)):
            tag = "even" if i % 2 == 0 else "odd"
            values = []
            for col in self.columns:
                cell = row.get(col, ("—", None, CLR_NEUTRAL))
                text, _key, bg = cell
                # Prefix a colour indicator so the user gets a visual cue
                # even without per-cell background support
                values.append(text)
            self.tv.insert("", "end", text=label, values=values, tags=(tag,))

    def _sort_by(self, col):
        """Sort rows by the given column, toggling asc/desc."""
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = False   # first click = descending (big→small)

        def sort_key(pair):
            label, row = pair
            if col == "#0":
                return label
            cell = row.get(col, ("—", None, CLR_NEUTRAL))
            _text, key, _bg = cell
            if key is None:
                return (-1e18 if not self._sort_asc else 1e18)
            return key

        pairs = sorted(zip(self.row_labels, self.rows),
                       key=sort_key, reverse=(not self._sort_asc))
        sorted_labels = [p[0] for p in pairs]
        sorted_rows   = [p[1] for p in pairs]

        arrow = " ▲" if self._sort_asc else " ▼"
        for c, hd in zip(self.columns, self.headings):
            indicator = arrow if c == col else ""
            self.tv.heading(c, text=hd + indicator)
        if col == "#0":
            ticker_arrow = arrow
        else:
            ticker_arrow = ""
        self.tv.heading("#0", text="Ticker" + ticker_arrow)

        self._populate(sorted_rows, sorted_labels)
        direction = "low → high" if self._sort_asc else "high → low"
        col_display = self.headings[self.columns.index(col)] if col != "#0" else "Ticker"
        self._status_var.set(
            f"{len(self.rows)} rows  ·  sorted by {col_display}  ({direction})"
        )


# ── Stock scorecard builder ───────────────────────────────────────────────────

def show_stock_table(data_list, colors, years_back):
    """Build and open the interactive stock scorecard window."""

    def _cell(text, sort_key, bg):
        return (text, sort_key, bg)

    columns  = [
        "name", "price",
        f"eps_cagr",
        "fwd_avg_pe", "pe_fwd", "pe_trail", "pe_5yr",
        "fcf_lat", "fcf_avg",
        "roe_lat", "roe_avg",
    ]
    headings = [
        "Name",
        "Price",
        f"EPS CAGR ({years_back-1}yr)",
        "Fwd/Avg P/E",
        "P/E Fwd",
        "P/E Trail",
        "P/E 5yr avg",
        "FCF/Sh latest",
        "FCF/Sh 3yr avg",
        "ROE % latest",
        "ROE % 3yr avg",
    ]

    rows       = []
    row_labels = []

    for d in data_list:
        row_labels.append(d["symbol"])
        row = {}

        # Name
        row["name"] = _cell(d.get("name", ""), d.get("name", ""), CLR_NAME)

        # Current price
        cp = d.get("current_price")
        if cp is None:
            row["price"] = _cell("N/A", None, CLR_NEUTRAL)
        else:
            row["price"] = _cell(f"${float(cp):,.2f}", float(cp), CLR_NAME)

        # EPS CAGR
        val = _eps_cagr(d["eps"], d["years"])
        if val is None:
            row["eps_cagr"] = _cell("N/A", None, CLR_NEUTRAL)
        else:
            bg = CLR_GREEN if val >= 0 else CLR_RED
            row["eps_cagr"] = _cell(f"{val:+.1f}%", val, bg)

        # P/E derived values
        cur_pe = d.get("trailing_pe")
        cur_pe = float(cur_pe) if cur_pe is not None else None
        fwd_pe = d.get("forward_pe")
        fwd_pe = float(fwd_pe) if fwd_pe is not None else None
        avg_pe = _avg_last_n(d["pe"], 5)

        # Fwd/Avg P/E ratio
        if fwd_pe is not None and avg_pe is not None and avg_pe > 0:
            ratio = round(fwd_pe / avg_pe, 2)
            bg = CLR_GREEN if ratio < 0.8 else (CLR_YELLOW if ratio <= 1.1 else CLR_RED)
            row["fwd_avg_pe"] = _cell(f"{ratio:.2f}x", ratio, bg)
        else:
            row["fwd_avg_pe"] = _cell("N/A", None, CLR_NEUTRAL)

        # Forward P/E
        if fwd_pe is None:
            row["pe_fwd"] = _cell("N/A", None, CLR_NEUTRAL)
        else:
            row["pe_fwd"] = _cell(f"{fwd_pe:.1f}x", fwd_pe, CLR_YELLOW)

        # Trailing P/E
        if cur_pe is None:
            row["pe_trail"] = _cell("N/A", None, CLR_NEUTRAL)
        else:
            row["pe_trail"] = _cell(f"{cur_pe:.1f}x", cur_pe, CLR_YELLOW)

        # 5yr avg P/E
        if avg_pe is None:
            row["pe_5yr"] = _cell("N/A", None, CLR_NEUTRAL)
        else:
            bg = CLR_NEUTRAL
            if cur_pe is not None:
                bg = CLR_GREEN if cur_pe < avg_pe else CLR_RED
            row["pe_5yr"] = _cell(f"{avg_pe:.1f}x", avg_pe, bg)

        # FCF/Share latest
        fcf_lat = _latest(d["fcfps"])
        if np.isnan(fcf_lat):
            row["fcf_lat"] = _cell("N/A", None, CLR_NEUTRAL)
        else:
            bg = CLR_GREEN if fcf_lat >= 0 else CLR_RED
            row["fcf_lat"] = _cell(f"${fcf_lat:.2f}", fcf_lat, bg)

        # FCF/Share 3yr avg
        fcf_avg = _avg_last_n(d["fcfps"], 3)
        if fcf_avg is None:
            row["fcf_avg"] = _cell("N/A", None, CLR_NEUTRAL)
        else:
            bg = CLR_GREEN if fcf_avg >= 0 else CLR_RED
            row["fcf_avg"] = _cell(f"${fcf_avg:.2f}", fcf_avg, bg)

        # ROE latest
        roe_lat = _latest(d["roe"])
        if np.isnan(roe_lat):
            row["roe_lat"] = _cell("N/A", None, CLR_NEUTRAL)
        else:
            bg = CLR_GREEN if roe_lat >= 15 else (CLR_YELLOW if roe_lat >= 8 else CLR_RED)
            row["roe_lat"] = _cell(f"{roe_lat:.1f}%", roe_lat, bg)

        # ROE 3yr avg
        roe_avg = _avg_last_n(d["roe"], 3)
        if roe_avg is None:
            row["roe_avg"] = _cell("N/A", None, CLR_NEUTRAL)
        else:
            bg = CLR_GREEN if roe_avg >= 15 else (CLR_YELLOW if roe_avg >= 8 else CLR_RED)
            row["roe_avg"] = _cell(f"{roe_avg:.1f}%", roe_avg, bg)

        rows.append(row)

    SortableTable(
        title="Stock Scorecard",
        columns=columns,
        headings=headings,
        rows=rows,
        row_labels=row_labels,
        min_col_w=120,
    )


# ── ETF scorecard builder ─────────────────────────────────────────────────────

def show_etf_table(etf_list, colors, years_back):
    """Build and open the interactive ETF scorecard window."""

    def _cell(text, sort_key, bg):
        return (text, sort_key, bg)

    periods = sorted(set([1, 3, 5, 10, years_back - 1]))

    columns  = (
        ["name"]
        + [f"cagr_{p}yr" for p in periods]
        + ["best", "worst", "avg_ret", "vol", "total_ret", "yield_pct"]
    )
    headings = (
        ["Name"]
        + [f"CAGR {p}yr" for p in periods]
        + ["Best Year", "Worst Year", "Avg Return", "Volatility",
           "Total Return", "Yield %"]
    )

    rows       = []
    row_labels = []

    for d in etf_list:
        row_labels.append(d["symbol"])
        row = {}

        # Name
        _raw_name = d.get("name", "")
        _short_name = _shorten_etf_name(_raw_name)
        row["name"] = _cell(_short_name, _short_name, CLR_NAME)

        # CAGR columns
        for p in periods:
            val = _cagr(d["prices"], p)
            key = f"cagr_{p}yr"
            if val is None:
                row[key] = _cell("N/A", None, CLR_NEUTRAL)
            else:
                bg = CLR_GREEN if val >= 0 else CLR_RED
                row[key] = _cell(f"{val:+.1f}%", val, bg)

        valid_returns = [(yr, r) for yr, r in zip(d["years"], d["annual_returns"])
                        if r is not None]

        # Best year
        if valid_returns:
            best_yr, best_val = max(valid_returns, key=lambda x: x[1])
            row["best"] = _cell(f"{best_yr}  {best_val:+.1f}%", best_val, CLR_GREEN)
        else:
            row["best"] = _cell("N/A", None, CLR_NEUTRAL)

        # Worst year
        if valid_returns:
            worst_yr, worst_val = min(valid_returns, key=lambda x: x[1])
            row["worst"] = _cell(f"{worst_yr}  {worst_val:+.1f}%", worst_val, CLR_RED)
        else:
            row["worst"] = _cell("N/A", None, CLR_NEUTRAL)

        # Average annual return
        if valid_returns:
            avg = round(sum(r for _, r in valid_returns) / len(valid_returns), 1)
            bg  = CLR_GREEN if avg >= 0 else CLR_RED
            row["avg_ret"] = _cell(f"{avg:+.1f}%", avg, bg)
        else:
            row["avg_ret"] = _cell("N/A", None, CLR_NEUTRAL)

        # Volatility
        if len(valid_returns) >= 2:
            ret_vals = [r for _, r in valid_returns]
            vol = round(float(np.std(ret_vals, ddof=1)), 1)
            bg  = CLR_GREEN if vol < 12 else (CLR_YELLOW if vol < 20 else CLR_RED)
            row["vol"] = _cell(f"{vol:.1f}%", vol, bg)
        else:
            row["vol"] = _cell("N/A", None, CLR_NEUTRAL)

        # Total return
        clean_prices = [p for p in d["prices"] if p is not None]
        if len(clean_prices) >= 2:
            total_ret = round((clean_prices[-1] / clean_prices[0] - 1) * 100, 1)
            bg = CLR_GREEN if total_ret >= 0 else CLR_RED
            row["total_ret"] = _cell(f"{total_ret:+.0f}%", total_ret, bg)
        else:
            row["total_ret"] = _cell("N/A", None, CLR_NEUTRAL)

        # Yield %
        try:
            latest_dist = next(
                (d["distributions"][i]
                 for i in range(len(d["years"]) - 1, -1, -1)
                 if d["distributions"][i] is not None and d["distributions"][i] > 0),
                None,
            )
            cur_price = d.get("current_price")
            if latest_dist and cur_price and cur_price > 0:
                yp = round(latest_dist / cur_price * 100, 2)
                row["yield_pct"] = _cell(f"{yp:.2f}%", yp, CLR_NAME)
            else:
                row["yield_pct"] = _cell("N/A", None, CLR_NEUTRAL)
        except Exception:
            row["yield_pct"] = _cell("N/A", None, CLR_NEUTRAL)

        rows.append(row)

    SortableTable(
        title="ETF Performance Summary",
        columns=columns,
        headings=headings,
        rows=rows,
        row_labels=row_labels,
        min_col_w=120,
    )