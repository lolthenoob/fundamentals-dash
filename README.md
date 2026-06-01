# fundamentals-dashboard

> Annual fundamentals tracker for equity research — powered by yfinance, matplotlib, and SQLite.

A desktop dashboard that downloads, caches, and charts 10+ years of per-share fundamentals for any set of stocks or ETFs. Built for IT/tech sector analysis but works with any Yahoo Finance–listed ticker.

---

## Releases

**[⬇ Download the latest release](https://github.com/lolthenoob/fundamentals-dashboard/releases/latest)**

The seed database (`fundamentals.db`) ships as a release asset. It contains 10+ years of pre-populated fundamentals built from manually sourced data, extending well beyond Yahoo Finance's ~4–5 year limit. Re-download it periodically to pick up the latest additions.

---

## Quick start

**1. Clone the repo**
```bash
git clone https://github.com/lolthenoob/fundamentals-dashboard.git
cd fundamentals-dashboard
pip install -r requirements.txt
```

**2. Download the seed database**

Go to the [Releases](https://github.com/lolthenoob/fundamentals-dashboard/releases) page and download `fundamentals.db`. Place it in the `tickers/` folder:

```
fundamentals-dashboard/
└── tickers/
    └── fundamentals.db   ← put it here
```

**3. Run**
```bash
python main.py
```

---

## Features

### Ticker picker
- Select from all tickers in the local database, with live search/filter
- **Yahoo Finance autocomplete** — type a symbol and matching suggestions appear instantly with a one-click Add button
- **Bulk entry** — type comma-separated symbols (e.g. `aapl,msft,xle`) to add multiple tickers at once
- **All / Selected / Unselected** filter toggle to review your selection before running
- **Re-download** and **Export Files** toggles in the bottom bar
- **Run Again** button returns to the picker from the status window without restarting
- **Exit** button closes cleanly from the status window

### Status window
- After clicking Go, the picker transitions to a live progress log showing each download and processing step
- Window stays open after charts close, ready for Run Again or Exit

### Stock charts
Each selected stock gets:
- **6-panel deep-dive** — EPS, P/E, ROE, BV/Share, OCF/Share, FCF/Share over 10+ years
- **Side-by-side comparison** across all selected tickers
- **Latest-year snapshot** bar chart
- **Interactive scorecard table** — current price, EPS CAGR, trailing/forward/5yr avg P/E, Fwd vs Avg P/E ratio, FCF/Share, ROE. Click any column header to sort; click again to reverse.

### ETF charts
Each selected ETF gets:
- **2×2 overview** — price history, annual return %, annual distributions, cumulative total return (indexed to 100)
- **Interactive performance table** — CAGR at multiple periods, best/worst year, average return, volatility, total return, yield %

### Data & caching
- Auto-downloads annual fundamentals from Yahoo Finance via `yfinance`
- SQLite cache — data persists locally; re-runs skip the download unless stale
- Smart staleness check using `years_stored` and `history_exhausted` — tickers with naturally short histories are not re-downloaded needlessly
- DB health report written to `output/db_health.txt` on every run — flags missing fields, stale data, and years with NULL values

### Export
Tick **Export Files** before clicking Go to save everything to a dated session folder under `output/`:
- Each stock chart, scorecard, comparison, and snapshot saved as PNG
- Each ETF overview and performance table saved as PNG
- Stock and ETF summary data saved as CSV

---

## Output files

| File | Contents |
|------|----------|
| `tickers/fundamentals.db` | SQLite database — all downloaded fundamentals |
| `output/db_summary.txt` | Quick summary of stored tickers and update times |
| `output/db_health.txt` | Per-ticker health report — missing fields, stale data, NULLs |
| `output/db_full.csv` | Full flat export of all annual data |
| `output/<date>/` | Session export folder — PNGs and CSVs (when Export Files is ticked) |

---

## Metrics tracked

| Metric | Description |
|--------|-------------|
| EPS | Diluted earnings per share |
| P/E | Price-to-earnings ratio (trailing, forward, 5yr avg) |
| ROE | Return on equity (%) |
| BV/Share | Book value per share |
| OCF/Share | Operating cash flow per share |
| FCF/Share | Free cash flow per share |
| Rev/Share | Revenue per share |
| Div/Share | Annual dividends per share |
| Debt/Assets | Total debt as % of total assets |
| EPS CAGR | Compound annual growth rate of EPS |

---

## Data sources & limits

Yahoo Finance (via `yfinance`) returns approximately **4–5 years** of annual fundamental history. The seed database extends this to **10+ years** using manually sourced data. When you add a new ticker not in the seed database, Yahoo Finance supplies what it can. Re-download the seed database from Releases periodically to get the latest additions.

---

## Building a standalone executable

```bash
pip install pyinstaller
python -m PyInstaller --onefile --name "Fundamentals-Dashboard" ^
  --hidden-import "matplotlib.backends.backend_tkagg" ^
  --hidden-import "mplcursors" ^
  --hidden-import "dateutil.parser" ^
  --hidden-import "yfinance" ^
  --hidden-import "numpy" ^
  --hidden-import "ticker_picker" ^
  --hidden-import "interactive_table" ^
  --collect-all yfinance ^
  --collect-all mplcursors ^
  main.py
```

Output: `dist/Fundamentals-Dashboard.exe`

---

## Data source

All data is sourced from [Yahoo Finance](https://finance.yahoo.com) via the [`yfinance`](https://github.com/ranaroussi/yfinance) library. For personal and research use only.

---

## License

MIT
