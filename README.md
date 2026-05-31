# fundamentals-dash

> Annual fundamentals tracker for equity research — powered by yfinance, matplotlib, and SQLite.

A desktop dashboard that downloads, caches, and charts 10+ years of per-share fundamentals for any set of tickers or ETFs. Built for IT/tech sector analysis but works with any Yahoo Finance–listed stock.

---

## Quick start

**1. Clone the repo**
```bash
git clone https://github.com/lolthenoob/fundamentals-dash.git
cd fundamentals-dash
pip install -r requirements.txt
```

**2. Download the seed database**

Go to the [Releases](https://github.com/lolthenoob/fundamentals-dash/releases) page and download `fundamentals.db` from the latest release. Place it in the `tickers/` folder:

```
fundamentals-dash/
└── tickers/
    └── fundamentals.db   ← put it here
```

This gives you 10 years of pre-populated fundamentals for the included tickers, built from manual data entry (see note below about Yahoo Finance's data limits).

**3. Run**
```bash
python main.py
```

The ticker picker will open pre-populated with all the tickers from the database. Select what you want and click Go.

---

## Data sources & limits

Yahoo Finance (via `yfinance`) only returns approximately **4–5 years** of annual fundamental history. The seed database included in Releases extends this to **10 years** using manually sourced data.

When you add a new ticker not in the seed database, Yahoo Finance will supply what it can (~5 years). The seed database is updated periodically — re-download it from Releases to get the latest.

---

## Features

- **Ticker picker GUI** — select from previously saved tickers, search, or add new ones
- **ETF support** — price history, annual distributions, and annual return %
- **Auto-downloads** annual fundamentals from Yahoo Finance via `yfinance`
- **SQLite cache** — data persists locally; re-runs skip the download unless stale (>90 days)
- **Per-share metrics** — EPS, P/E, ROE, BV/Share, OCF/Share, FCF/Share, Revenue/Share, Dividends
- **Three chart views:**
  - Individual ticker deep-dive (6-panel)
  - Side-by-side comparison across all selected tickers
  - Latest-year snapshot bar chart
- **ETF chart view** — price, distributions, and annual return
- **CSV + text exports** for every run (`output/` folder)
- **Analyst data** — consensus rating, target price, low/high from Yahoo Finance

---

## Usage

```bash
python main.py
```

**Force a data refresh:**
```bash
python main.py --refresh
```

---

## Output files

| File                      | Contents                                         |
|---------------------------|--------------------------------------------------|
| `tickers/fundamentals.db` | SQLite database — all downloaded fundamentals    |
| `output/db_summary.txt`   | Quick summary of stored tickers and update times |
| `output/db_full.csv`      | Full flat export of all annual data              |

---

## Metrics tracked

| Metric      | Description                     |
|-------------|---------------------------------|
| EPS         | Diluted earnings per share      |
| P/E         | Price-to-earnings ratio         |
| ROE         | Return on equity (%)            |
| BV/Share    | Book value per share            |
| OCF/Share   | Operating cash flow per share   |
| FCF/Share   | Free cash flow per share        |
| Rev/Share   | Revenue per share               |
| Div/Share   | Annual dividends per share      |
| Debt/Assets | Total debt as % of total assets |

---

## Building a standalone executable

```bash
pip install pyinstaller
python -m PyInstaller --onefile --windowed --name "IT-Dashboard" \
  --hidden-import "matplotlib.backends.backend_tkagg" \
  --hidden-import "mplcursors" \
  --hidden-import "dateutil.parser" \
  --hidden-import "yfinance" \
  --hidden-import "numpy" \
  --collect-all yfinance \
  --collect-all mplcursors \
  main.py
```

Output: `dist/IT-Dashboard.exe` (Windows) or `dist/IT-Dashboard` (Mac/Linux).

---

## Data source

All data is sourced from [Yahoo Finance](https://finance.yahoo.com) via the [`yfinance`](https://github.com/ranaroussi/yfinance) library. For personal and research use only.

---

## License

MIT
