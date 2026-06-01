# Changelog — Fundamentals Dashboard

## [0.1.3] - 2026-06-01

### Added
- **Bulk ticker entry** — type comma-separated symbols (e.g. `aapl,msft,xle`)
  in the search box to add multiple tickers at once. Each row is individually
  toggleable before committing with Add All.
- **Persistent status window** — after clicking Go, the picker transitions to
  a live progress log showing each download and processing step. The window
  stays open after charts close.
- **Run Again button** — returns to the ticker picker from the status window
  without restarting the app.
- **Exit button** — closes the app cleanly from the status window, sitting at
  the opposite end of the bar from Run Again.

### Fixed
- ETF yield now calculated from full prior-year distributions instead of the
  single latest payment.
- ETFs no longer re-download when a valid cached version exists.
- Run Again no longer freezes on the second selection.
- Staleness check now uses `years_stored` and `history_exhausted` so tickers
  with naturally short histories are not re-downloaded on every run.
- Status log text is selectable for copy/paste.
- ETF names shortened for cleaner display.
- Unified suggestion row UX — session-added tickers follow the same
  tick/untick flow as DB tickers.

## [0.1.2] - 2026-05-31

### Added
- Interactive sortable scorecard tables for stocks and ETFs, replacing the
  static matplotlib tables. Click any column header to sort high→low, click
  again to flip. Powered by a new file: `interactive_table.py`.
- Yahoo Finance autocomplete in the ticker picker — type a symbol and
  matching suggestions appear below the DB list with an orange ＋ Add button.
- All / Selected / Unselected filter toggle in the ticker picker, so you can
  review exactly what you've chosen before hitting Go.
- DB health report written to `output/db_health.txt` on every run — flags
  missing fields, stale data, and years with NULL values per ticker.
- Console stays open after crash or normal exit (Press Enter to close),
  making pyinstaller builds easier to debug.

### Fixed
- Ticker search now matches symbol prefixes (typing XL shows XLE, XLF, XLK…).
- Add new ticker button now always visible when search text doesn't exactly
  match an existing DB symbol — fixes the TMUS/MU interference bug.
- Column headers in scorecard tables now display correctly (newlines in
  heading strings were causing all P/E columns to show as "P/E").
- Scorecard table font size increased for readability.
- Duplicate print statement removed from main ticker processing loop.
- Ticker suggestion rows now match DB row height and alignment — same
  checkbox, same font, same padding throughout.
- Clicking a suggestion ticks it and moves it above the divider; clicking
  again removes the row and re-fires Yahoo so it reappears in suggestions.
- Search text no longer clears after selecting a suggestion, allowing
  multiple picks in one pass.
- Yahoo suggestions label updated to note the 7-result cap.

---

## [0.1.1] - 2026-05-31

### Added
- **Stock Scorecard** — a dedicated table figure for every selected stock.
  Columns cover current price, EPS CAGR, forward/trailing/5yr avg P/E, a
  Fwd vs Avg P/E valuation ratio, FCF per share, and ROE — all colour coded
  so cheap, profitable, and cash-generative stocks stand out immediately.
  Trailing and forward P/E are pulled live from Yahoo Finance.
- **ETF overhaul** — the ETF view is now two separate figures. The overview
  is a 2×2 grid: price history, annual return, annual distributions, and a
  cumulative total return chart indexed to 100. The performance summary is a
  standalone table with CAGR at multiple periods, best/worst year, average
  return, volatility, total return, and yield %.
- **Export system** — tick Export Files before clicking Go and the app saves
  everything to a dated session folder under `output/`. Each stock chart,
  scorecard, comparison, snapshot, and ETF figure saved as PNG. Stock and ETF
  summary data saved as CSV.
- Re-download and Export Files toggles added to the bottom bar of the ticker
  picker, styled with the same custom ☑ tick as the ticker list.
- Matplotlib windows now show meaningful titles (`GOOGL — Alphabet Inc.`,
  `Stock Scorecard`, `ETF Overview`) instead of `Figure 1`, `Figure 2`.

### Changed
- Ticker picker window wider by default.
- Refresh is no longer a command-line argument — everything is controlled
  from the GUI.

### Database
- `trailing_pe` and `forward_pe` columns added to the `tickers` table.
  Existing databases are migrated automatically on first run.

---

## [0.1.0] - 2026-05-31

### Initial release
- 10 years of annual fundamentals data for selected IT sector stocks.
- Auto-downloads data from Yahoo Finance via yfinance.
- Saves and updates all ticker data to `tickers/fundamentals.db` (SQLite).
- Standalone `.exe` — no Python installation needed.
