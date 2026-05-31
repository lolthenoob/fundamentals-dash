"""
ticker_picker.py
────────────────
Drop-in ticker selection GUI for the IT Dashboard.
Returns (selected_tickers, years_back, force_refresh, do_export) tuple.

Bulk entry: typing comma-separated symbols (e.g. aapl,msft,xle) switches
the search box into bulk mode — Yahoo suggestions are replaced with a
preview list that looks identical to the DB rows. Each row is individually
toggleable. "Add All" ticks the checked ones and clears the box.
"""

import os
import re
import sqlite3
import tkinter as tk
from tkinter import ttk, font as tkfont
import urllib.request
import urllib.parse
import json
import threading


CLR_ACCENT  = "#00A4EF"
CLR_BG      = "#F7F9FC"
CLR_ROW_A   = "#FFFFFF"
CLR_ROW_B   = "#EFF4FA"
CLR_TEXT    = "#1A1A2E"
CLR_SUBTEXT = "#555577"
CLR_BTN_FG  = "#FFFFFF"

TICK_FONT_SIZE = 16
ROW_PADY       = 0
ROW_PADX       = 8
WINDOW_WIDTH   = 950
WINDOW_HEIGHT  = 0.88
WINDOW_X       = None
WINDOW_Y       = 20
YEARS_DEFAULT  = 11

# Maximum symbol length — anything longer is likely a paste artefact
_SYM_MAX_LEN = 6
_SYM_RE      = re.compile(r'^[A-Z0-9.\-]{1,6}$')


# ── Input helpers ─────────────────────────────────────────────────────────────

def _parse_bulk(raw: str) -> list[str]:
    """
    Split a comma-separated string into clean, deduplicated, valid ticker symbols.
    Returns an empty list if the input contains no comma (single-ticker mode).
    """
    tokens = [t.strip().upper() for t in raw.split(",")]
    seen, result = set(), []
    for t in tokens:
        if not t:
            continue                       # trailing comma / double comma
        if not _SYM_RE.match(t):
            continue                       # garbage / too long / bad chars
        if t in seen:
            continue                       # duplicate
        seen.add(t)
        result.append(t)
    return result


def pick_tickers(db_path: str) -> tuple[list[str], int, bool, bool]:
    available: list[tuple[str, str]] = []

    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            rows = conn.execute(
                "SELECT symbol, name FROM tickers ORDER BY symbol"
            ).fetchall()
            conn.close()
            available = [(r[0], r[1] or r[0]) for r in rows]
        except Exception:
            pass

    if not available:
        return _manual_entry_fallback()

    # ── Result holders ────────────────────────────────────────────────────
    result_tickers: list[str] = []
    result_years:   int       = YEARS_DEFAULT
    result_refresh: bool      = False
    result_export:  bool      = False

    root = tk.Tk()
    root.title("📈  Select Tickers")
    root.configure(bg=CLR_BG)
    root.resizable(True, True)

    root.update_idletasks()
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    w = WINDOW_WIDTH
    h = int(sh * WINDOW_HEIGHT)
    x = (sw - w) // 2 if WINDOW_X is None else WINDOW_X
    root.geometry(f"{w}x{h}+{x}+{WINDOW_Y}")
    root.minsize(500, 400)

    mono      = tkfont.Font(family="Consolas", size=11)
    bold      = tkfont.Font(family="Consolas", size=11, weight="bold")
    hdr_bold  = tkfont.Font(family="Consolas", size=13, weight="bold")
    hdr_sub   = tkfont.Font(family="Consolas", size=10)
    sel_font  = tkfont.Font(family="Consolas", size=11, weight="bold")
    tick_font = tkfont.Font(family="Segoe UI Symbol", size=TICK_FONT_SIZE)

    # ── Header ────────────────────────────────────────────────────────────
    hdr = tk.Frame(root, bg=CLR_ACCENT, pady=12)
    hdr.pack(fill="x")
    tk.Label(hdr, text="Fundamentals Dashboard",
             bg=CLR_ACCENT, fg="white", font=hdr_bold).pack()
    tk.Label(hdr, text="Choose tickers to chart",
             bg=CLR_ACCENT, fg="#D0EEFF", font=hdr_sub).pack()

    # ── Selected tickers summary bar ──────────────────────────────────────
    summary_frame = tk.Frame(root, bg="#E8F4FD", pady=6, padx=14)
    summary_frame.pack(fill="x")
    tk.Label(summary_frame, text="Selected: ", bg="#E8F4FD",
             fg=CLR_SUBTEXT, font=bold).pack(side="left")
    summary_var = tk.StringVar(value="—")
    tk.Label(summary_frame, textvariable=summary_var, bg="#E8F4FD",
             fg=CLR_ACCENT, font=sel_font, anchor="w",
             wraplength=520, justify="left").pack(side="left", fill="x", expand=True)

    # ── Filter toggle (All / Selected / Unselected) ───────────────────────
    toggle_frame = tk.Frame(root, bg=CLR_BG, pady=4, padx=14)
    toggle_frame.pack(fill="x")
    filter_var = tk.StringVar(value="all")
    _filter_btns = {}

    def _set_filter(val):
        filter_var.set(val)
        for v, (btn, lbl) in _filter_btns.items():
            active = (v == val)
            btn.config(text="☑" if active else "☐",
                       fg=CLR_ACCENT if active else "#AAAAAA")
        _apply_filter()

    for label, val in [("All", "all"), ("Selected", "selected"), ("Unselected", "unselected")]:
        container = tk.Frame(toggle_frame, bg=CLR_BG)
        container.pack(side="left", padx=(0, 16))
        btn = tk.Button(container, text="☑" if val == "all" else "☐",
                        font=tick_font, fg=CLR_ACCENT if val == "all" else "#AAAAAA",
                        bg=CLR_BG, activebackground=CLR_BG,
                        relief="flat", bd=0, cursor="hand2", padx=0, pady=0,
                        command=lambda v=val: _set_filter(v))
        btn.pack(side="left")
        lbl = tk.Label(container, text=label, bg=CLR_BG, fg=CLR_TEXT, font=bold)
        lbl.pack(side="left")
        lbl.bind("<Button-1>", lambda e, v=val: _set_filter(v))
        _filter_btns[val] = (btn, lbl)

    # ── Search bar ────────────────────────────────────────────────────────
    search_frame = tk.Frame(root, bg=CLR_BG, pady=8, padx=14)
    search_frame.pack(fill="x")
    tk.Label(search_frame, text="🔍  Search / Add:", bg=CLR_BG,
             fg=CLR_TEXT, font=bold).pack(side="left")
    search_var = tk.StringVar()
    search_entry = tk.Entry(search_frame, textvariable=search_var,
                            font=mono, relief="flat", bg="white", fg=CLR_TEXT,
                            insertbackground=CLR_ACCENT,
                            highlightthickness=1,
                            highlightcolor=CLR_ACCENT,
                            highlightbackground="#CCCCCC")
    search_entry.pack(side="left", fill="x", expand=True, padx=(8, 0))

    # "Add as new" button for single-ticker mode
    add_new_btn = tk.Button(search_frame, text="", bg="#E06C00", fg="white",
                            font=bold, relief="flat", padx=12, pady=4,
                            cursor="hand2")

    search_entry.focus_set()

    # ── Scrollable main list ──────────────────────────────────────────────
    list_outer = tk.Frame(root, bg=CLR_BG, padx=14)
    list_outer.pack(fill="both", expand=True)

    canvas = tk.Canvas(list_outer, bg=CLR_BG, highlightthickness=0)
    scrollbar = ttk.Scrollbar(list_outer, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)

    inner = tk.Frame(canvas, bg=CLR_BG)
    canvas_window = canvas.create_window((0, 0), window=inner, anchor="nw")

    def _on_canvas_resize(event):
        canvas.itemconfig(canvas_window, width=event.width)
    canvas.bind("<Configure>", _on_canvas_resize)

    def _on_frame_resize(event):
        canvas.configure(scrollregion=canvas.bbox("all"))
    inner.bind("<Configure>", _on_frame_resize)

    def _scroll(event):
        if event.num == 4:
            canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            canvas.yview_scroll(1, "units")
        else:
            canvas.yview_scroll(int(-event.delta / 60), "units")
    canvas.bind_all("<MouseWheel>", _scroll)
    canvas.bind_all("<Button-4>",   _scroll)
    canvas.bind_all("<Button-5>",   _scroll)

    check_vars:   dict[str, tk.BooleanVar] = {}
    row_frames:   dict[str, tk.Frame]      = {}
    tick_buttons: dict[str, tk.Button]     = {}
    _session_added: set[str]               = set()

    # ── DB rows ───────────────────────────────────────────────────────────
    def _make_toggle(v, b):
        def _toggle():
            v.set(not v.get())
            b.config(text="☑" if v.get() else "☐",
                     fg=CLR_ACCENT if v.get() else "#AAAAAA")
        return _toggle

    for i, (sym, name) in enumerate(available):
        var = tk.BooleanVar(value=False)
        check_vars[sym] = var

        bg = CLR_ROW_A if i % 2 == 0 else CLR_ROW_B
        row = tk.Frame(inner, bg=bg, pady=ROW_PADY, padx=ROW_PADX)
        row.pack(fill="x")
        row_frames[sym] = row

        btn = tk.Button(row, text="☐", font=tick_font,
                        fg="#AAAAAA", bg=bg, activebackground=bg,
                        relief="flat", bd=0, cursor="hand2", padx=0, pady=0)
        btn.pack(side="left")
        tick_buttons[sym] = btn
        btn.config(command=_make_toggle(var, btn))

        tk.Label(row, text=f"{sym:<8}", font=bold,
                 bg=bg, fg=CLR_ACCENT, anchor="w").pack(side="left")
        tk.Label(row, text=name, font=mono,
                 bg=bg, fg=CLR_SUBTEXT, anchor="w").pack(side="left", fill="x")

    # ── Summary / count helpers ───────────────────────────────────────────
    def _update_summary(*_):
        selected = [sym for sym, v in check_vars.items() if v.get()]
        summary_var.set(", ".join(selected) if selected else "—")

    def _update_count(*_):
        n = sum(v.get() for v in check_vars.values())
        count_var.set(f"{n} selected")

    for v in check_vars.values():
        v.trace_add("write", _update_summary)
        v.trace_add("write", _update_count)

    # ─────────────────────────────────────────────────────────────────────
    # BULK MODE
    # ─────────────────────────────────────────────────────────────────────

    # Container that sits above the DB rows, hidden when not in bulk mode
    bulk_frame = tk.Frame(inner, bg=CLR_BG)
    # (packed/unpacked dynamically — do NOT pack here)

    _bulk_vars:    dict[str, tk.BooleanVar] = {}   # sym → checked in preview
    _bulk_btns:    dict[str, tk.Button]     = {}
    _bulk_rows:    list[tk.Frame]           = []   # all child frames inside bulk_frame
    _bulk_active   = [False]                        # mutable flag
    _bulk_resolve_id = [None]                       # after() id for debounce

    def _clear_bulk_ui():
        for w in _bulk_rows:
            try:
                w.destroy()
            except Exception:
                pass
        _bulk_rows.clear()
        _bulk_vars.clear()
        _bulk_btns.clear()

    def _hide_bulk():
        _bulk_active[0] = False
        _clear_bulk_ui()
        bulk_frame.pack_forget()

    def _show_bulk_loading(symbols: list[str]):
        """Replace bulk area with a 'Resolving N tickers…' spinner row."""
        _clear_bulk_ui()
        bulk_frame.pack(fill="x", before=list(row_frames.values())[0]
                        if row_frames else None)

        lbl = tk.Label(bulk_frame,
                       text=f"  Resolving {len(symbols)} ticker{'s' if len(symbols) != 1 else ''}…",
                       bg="#FFF9E6", fg="#8B6914", font=bold,
                       anchor="w", pady=6, padx=14)
        lbl.pack(fill="x")
        _bulk_rows.append(lbl)

    def _render_bulk_preview(resolved: list[tuple[str, str, bool]]):
        """
        resolved: list of (symbol, name, in_db)
        Renders the preview list + Add All button inside bulk_frame.
        """
        _clear_bulk_ui()

        if not resolved:
            lbl = tk.Label(bulk_frame,
                           text="  No valid tickers found in input.",
                           bg="#FFF0F0", fg="#8B1414", font=bold,
                           anchor="w", pady=6, padx=14)
            lbl.pack(fill="x")
            _bulk_rows.append(lbl)
            return

        # ── Header row with Add All button ────────────────────────────────
        hdr_row = tk.Frame(bulk_frame, bg="#E8F4FD", pady=5, padx=14)
        hdr_row.pack(fill="x")
        _bulk_rows.append(hdr_row)

        tk.Label(hdr_row,
                 text=f"  {len(resolved)} ticker{'s' if len(resolved) != 1 else ''} ready to add — tick/untick individually or:",
                 bg="#E8F4FD", fg=CLR_SUBTEXT, font=bold).pack(side="left")

        add_all_btn = tk.Button(
            hdr_row,
            text=f"＋  Add all {len(resolved)}",
            bg=CLR_ACCENT, fg="white",
            font=bold, relief="flat", padx=10, pady=4,
            cursor="hand2",
            command=_commit_bulk,
        )
        add_all_btn.pack(side="right", padx=(0, 4))

        # ── Divider ───────────────────────────────────────────────────────
        div = tk.Frame(bulk_frame, bg="#CCCCCC", height=1)
        div.pack(fill="x")
        _bulk_rows.append(div)

        # ── One row per resolved symbol ───────────────────────────────────
        for i, (sym, name, in_db) in enumerate(resolved):
            bg = CLR_ROW_A if i % 2 == 0 else CLR_ROW_B
            row = tk.Frame(bulk_frame, bg=bg, pady=ROW_PADY, padx=ROW_PADX)
            row.pack(fill="x")
            _bulk_rows.append(row)

            var = tk.BooleanVar(value=True)
            _bulk_vars[sym] = var

            sym_colour = CLR_ACCENT if in_db else "#E06C00"

            btn = tk.Button(row, text="☑", font=tick_font,
                            fg=CLR_ACCENT, bg=bg, activebackground=bg,
                            relief="flat", bd=0, cursor="hand2", padx=0, pady=0)
            btn.pack(side="left")
            _bulk_btns[sym] = btn

            def _make_bulk_toggle(v, b):
                def _toggle():
                    v.set(not v.get())
                    b.config(text="☑" if v.get() else "☐",
                             fg=CLR_ACCENT if v.get() else "#AAAAAA")
                return _toggle

            btn.config(command=_make_bulk_toggle(var, btn))

            tk.Label(row, text=f"{sym:<8}", font=bold,
                     bg=bg, fg=sym_colour, anchor="w").pack(side="left")

            name_display = name if name else "(unknown)"
            name_suffix  = "  ✦ in DB" if in_db else "  ↓ will download"
            tk.Label(row, text=name_display, font=mono,
                     bg=bg, fg=CLR_SUBTEXT, anchor="w").pack(side="left")
            tk.Label(row, text=name_suffix, font=mono,
                     bg=bg, fg="#AAAAAA" if in_db else "#E06C00",
                     anchor="w").pack(side="left")

    def _commit_bulk():
        """Tick all checked bulk-preview symbols into the main list, then clear."""
        for sym, var in _bulk_vars.items():
            if var.get():
                _add_ticker_sym(sym, _bulk_name_cache.get(sym, ""))
        _hide_bulk()
        search_var.set("")
        _update_summary()
        _update_count()

    _bulk_name_cache: dict[str, str] = {}   # sym → resolved name

    def _resolve_bulk(symbols: list[str]):
        """
        Worker: resolve names for each symbol via Yahoo, one thread per symbol.
        Collects all results then calls _render_bulk_preview on the main thread.
        """
        db_syms = {sym for sym, _ in available}
        db_name = {sym: name for sym, name in available}

        resolved_lock   = threading.Lock()
        resolved_results: list[tuple[str, str, bool]] = []
        pending         = [len(symbols)]

        def _fetch_one(sym):
            name   = ""
            in_db  = sym in db_syms

            if in_db:
                name = db_name[sym]
            else:
                try:
                    url = (
                        "https://query1.finance.yahoo.com/v1/finance/search"
                        f"?q={urllib.parse.quote(sym)}&quotesCount=5&newsCount=0"
                        f"&enableFuzzyQuery=false&enableEnhancedTrivialQuery=true"
                    )
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=4) as resp:
                        data = json.loads(resp.read())
                    for quote in data.get("quotes", []):
                        if quote.get("symbol", "").upper() == sym:
                            name = quote.get("longname") or quote.get("shortname") or ""
                            break
                except Exception:
                    name = ""

            with resolved_lock:
                _bulk_name_cache[sym] = name
                resolved_results.append((sym, name, in_db))
                pending[0] -= 1
                if pending[0] == 0:
                    # Preserve original input order
                    order = {s: i for i, s in enumerate(symbols)}
                    resolved_results.sort(key=lambda t: order.get(t[0], 999))
                    root.after(0, lambda r=list(resolved_results): _render_bulk_preview(r))

        for sym in symbols:
            threading.Thread(target=_fetch_one, args=(sym,), daemon=True).start()

    def _trigger_bulk_mode(symbols: list[str]):
        """Entry point when comma detected. Show loading, kick off resolve."""
        _bulk_active[0] = True
        add_new_btn.pack_forget()          # hide single-add button
        # Clear any old Yahoo suggestion rows
        for w in _ac_rows:
            try:
                w.destroy()
            except Exception:
                pass
        _ac_rows.clear()

        _show_bulk_loading(symbols)
        _resolve_bulk(symbols)

    # ── Single-ticker add (unchanged logic, factored to shared fn) ────────
    def _make_session_toggle(sym, var, btn):
        def _toggle():
            if var.get():
                var.set(False)
                if sym in row_frames:
                    row_frames[sym].destroy()
                    del row_frames[sym]
                if sym in tick_buttons:
                    del tick_buttons[sym]
                if sym in check_vars:
                    del check_vars[sym]
                _session_added.discard(sym)
                _update_summary()
                _update_count()
                q = search_var.get().strip()
                if q and "," not in q:
                    threading.Thread(target=_yahoo_search, args=(q,), daemon=True).start()
            else:
                var.set(True)
                btn.config(text="☑", fg=CLR_ACCENT)
        return _toggle

    def _add_ticker_sym(sym: str, name: str = ""):
        """Tick an existing DB ticker or add a new session ticker row."""
        if sym in check_vars:
            check_vars[sym].set(True)
            if sym in tick_buttons:
                tick_buttons[sym].config(text="☑", fg=CLR_ACCENT)
            return

        # New ticker — add a row
        if not name:
            name = _bulk_name_cache.get(sym, "(new — will download)")

        var = tk.BooleanVar(value=True)
        check_vars[sym] = var
        _session_added.add(sym)

        bg = CLR_ROW_A if len(check_vars) % 2 == 0 else CLR_ROW_B
        row = tk.Frame(inner, bg=bg, pady=ROW_PADY, padx=ROW_PADX)
        row.pack(fill="x")
        row_frames[sym] = row

        btn = tk.Button(row, text="☑", font=tick_font,
                        fg=CLR_ACCENT, bg=bg, activebackground=bg,
                        relief="flat", bd=0, cursor="hand2", padx=0, pady=0)
        btn.pack(side="left")
        tick_buttons[sym] = btn
        btn.config(command=_make_session_toggle(sym, var, btn))

        tk.Label(row, text=f"{sym:<8}", font=bold,
                 bg=bg, fg="#E06C00", anchor="w").pack(side="left")
        tk.Label(row, text=name, font=mono,
                 bg=bg, fg=CLR_SUBTEXT, anchor="w").pack(side="left")

        var.trace_add("write", _update_summary)
        var.trace_add("write", _update_count)
        var.trace_add("write", _apply_filter)

    # ── Yahoo autocomplete (single-ticker mode) ───────────────────────────
    _ac_after        = None
    _ac_rows         = []
    _ac_last_results = []

    def _clear_suggestions():
        for w in _ac_rows:
            try:
                w.destroy()
            except Exception:
                pass
        _ac_rows.clear()

    def _yahoo_search(q):
        try:
            url = (
                "https://query1.finance.yahoo.com/v1/finance/search"
                f"?q={urllib.parse.quote(q)}&quotesCount=20&newsCount=0"
                f"&enableFuzzyQuery=false&enableCccBoost=false&enableEnhancedTrivialQuery=true"
            )
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read())
            quotes = data.get("quotes", [])
            results = [
                (r.get("symbol", ""),
                 r.get("longname") or r.get("shortname") or "",
                 r.get("symbol") in check_vars)
                for r in quotes if r.get("symbol")
            ]
        except Exception:
            results = []
        root.after(0, lambda: _show_suggestions(results))

    def _show_suggestions(results):
        nonlocal _ac_last_results
        _ac_last_results = results
        _clear_suggestions()
        if not results:
            return
        div = tk.Frame(inner, bg="#CCCCCC", height=1)
        div.pack(fill="x", pady=(6, 0))
        _ac_rows.append(div)
        lbl = tk.Label(inner, text="  Yahoo suggestions (max 7)",
                       bg=CLR_BG, fg=CLR_SUBTEXT, font=bold, anchor="w")
        lbl.pack(fill="x")
        _ac_rows.append(lbl)

        for i, (sym, name, in_db) in enumerate(results):
            bg = CLR_ROW_A if i % 2 == 0 else CLR_ROW_B
            row = tk.Frame(inner, bg=bg, pady=ROW_PADY, padx=ROW_PADX)
            row.pack(fill="x")
            _ac_rows.append(row)

            if in_db:
                existing_var = check_vars.get(sym)
                is_checked = existing_var.get() if existing_var else False
                btn = tk.Button(row, text="☑" if is_checked else "☐",
                                font=tick_font,
                                fg=CLR_ACCENT if is_checked else "#AAAAAA",
                                bg=bg, activebackground=bg,
                                relief="flat", bd=0, cursor="hand2", padx=0, pady=0)
                btn.pack(side="left")
                def _make_db_toggle(s):
                    def _toggle():
                        _add_ticker_sym(s)
                    return _toggle
                btn.config(command=_make_db_toggle(sym))
                tk.Label(row, text=f"{sym:<8}", font=bold,
                         bg=bg, fg=CLR_ACCENT, anchor="w").pack(side="left")
            else:
                btn = tk.Button(row, text="☐", font=tick_font,
                                fg="#AAAAAA", bg=bg, activebackground=bg,
                                relief="flat", bd=0, cursor="hand2", padx=0, pady=0)
                btn.pack(side="left")
                def _make_new_toggle(s, n):
                    def _toggle():
                        _add_ticker_sym(s, n)
                    return _toggle
                btn.config(command=_make_new_toggle(sym, name))
                tk.Label(row, text=f"{sym:<8}", font=bold,
                         bg=bg, fg="#E06C00", anchor="w").pack(side="left")

            tk.Label(row, text=name, font=mono,
                     bg=bg, fg=CLR_SUBTEXT, anchor="w").pack(side="left", fill="x")

    # ── Master search-change handler ──────────────────────────────────────
    def _on_search_change(*_):
        nonlocal _ac_after
        if _ac_after:
            root.after_cancel(_ac_after)
        q = search_var.get().strip()

        # ── Bulk mode: comma detected ─────────────────────────────────────
        if "," in q:
            _clear_suggestions()
            add_new_btn.pack_forget()
            symbols = _parse_bulk(q)
            if symbols:
                if _bulk_resolve_id[0]:
                    root.after_cancel(_bulk_resolve_id[0])
                _bulk_resolve_id[0] = root.after(
                    400, lambda s=symbols: _trigger_bulk_mode(s)
                )
            else:
                _hide_bulk()
            return

        # ── Single mode ───────────────────────────────────────────────────
        if _bulk_active[0]:
            _hide_bulk()

        _clear_suggestions()
        if len(q) < 1:
            add_new_btn.pack_forget()
            return

        _ac_after = root.after(350, lambda: threading.Thread(
            target=_yahoo_search, args=(q,), daemon=True
        ).start())

        exact_match = q.upper() in {sym.upper() for sym, _ in available}
        if not exact_match:
            add_new_btn.config(text=f"＋  Add \"{q.upper()}\" as new ticker")
            add_new_btn.pack(side="left", padx=(8, 0))
        else:
            add_new_btn.pack_forget()

    search_var.trace_add("write", _on_search_change)

    def _add_new_ticker():
        sym = search_var.get().strip().upper()
        if sym and "," not in sym:
            _add_ticker_sym(sym)

    add_new_btn.config(command=_add_new_ticker)

    # ── Filter (applies to DB rows only; bulk preview sits above) ─────────
    def _apply_filter(*_):
        q    = search_var.get().strip().upper()
        filt = filter_var.get()
        for sym, name in available:
            if sym not in row_frames:
                continue
            text_match = (
                not q or "," in q          # in bulk mode show all DB rows
                or sym.upper().startswith(q)
                or q in sym.upper()
                or q in name.upper()
            )
            if filt == "selected":
                sel_match = check_vars.get(sym, tk.BooleanVar()).get()
            elif filt == "unselected":
                sel_match = not check_vars.get(sym, tk.BooleanVar()).get()
            else:
                sel_match = True
            if text_match and sel_match:
                row_frames[sym].pack(fill="x")
            else:
                row_frames[sym].pack_forget()
        canvas.yview_moveto(0)

    search_var.trace_add("write", _apply_filter)
    for v in check_vars.values():
        v.trace_add("write", _apply_filter)

    # ── Bottom bar ────────────────────────────────────────────────────────
    ctrl = tk.Frame(root, bg=CLR_BG, pady=10, padx=14)
    ctrl.pack(fill="x")

    btn_cfg = dict(font=bold, relief="flat", bd=0, padx=12, pady=7, cursor="hand2")

    def _sync_all_buttons():
        for sym, v in check_vars.items():
            if sym in tick_buttons:
                tick_buttons[sym].config(
                    text="☑" if v.get() else "☐",
                    fg=CLR_ACCENT if v.get() else "#AAAAAA"
                )

    def _select_all():
        for sym in list(row_frames):
            if row_frames[sym].winfo_ismapped():
                check_vars[sym].set(True)
        _sync_all_buttons()

    def _clear_all():
        for v in check_vars.values():
            v.set(False)
        _sync_all_buttons()

    tk.Button(ctrl, text="✔  Select All", bg="#10B981", fg=CLR_BTN_FG,
              activebackground="#0D9E6E",
              command=_select_all, **btn_cfg).pack(side="left", padx=(0, 8))
    tk.Button(ctrl, text="✖  Clear All", bg="#EF4444", fg=CLR_BTN_FG,
              activebackground="#CC3333",
              command=_clear_all, **btn_cfg).pack(side="left")

    count_var = tk.StringVar(value="0 selected")
    tk.Label(ctrl, textvariable=count_var, bg=CLR_BG,
             fg=CLR_SUBTEXT, font=mono).pack(side="left", padx=14)

    years_frame = tk.Frame(ctrl, bg=CLR_BG)
    years_frame.pack(side="left", padx=(0, 14))
    tk.Label(years_frame, text="History:", bg=CLR_BG,
             fg=CLR_SUBTEXT, font=bold).pack(side="left", padx=(0, 6))
    years_var = tk.StringVar(value=str(YEARS_DEFAULT))
    tk.Entry(years_frame, textvariable=years_var, font=mono,
             width=4, relief="flat",
             highlightthickness=1,
             highlightcolor=CLR_ACCENT,
             highlightbackground="#CCCCCC").pack(side="left")
    tk.Label(years_frame, text="yrs", bg=CLR_BG,
             fg=CLR_SUBTEXT, font=mono).pack(side="left", padx=(4, 0))

    refresh_var = tk.BooleanVar(value=False)
    export_var  = tk.BooleanVar(value=False)

    def _go():
        nonlocal result_tickers, result_years, result_refresh, result_export
        result_tickers = [sym for sym, v in check_vars.items() if v.get()]
        try:
            result_years = max(1, int(years_var.get()))
        except ValueError:
            result_years = YEARS_DEFAULT
        result_refresh = refresh_var.get()
        result_export  = export_var.get()
        root.destroy()

    def _make_toggle_btn(frame, label, var, side="right", padx=(0, 8)):
        container = tk.Frame(frame, bg=CLR_BG)
        container.pack(side=side, padx=padx)
        btn = tk.Button(container, text="☐", font=tick_font,
                        fg="#AAAAAA", bg=CLR_BG, activebackground=CLR_BG,
                        relief="flat", bd=0, cursor="hand2", padx=0, pady=0)
        btn.pack(side="left")
        tk.Label(container, text=label, bg=CLR_BG,
                 fg=CLR_SUBTEXT, font=bold).pack(side="left")

        def _toggle():
            var.set(not var.get())
            btn.config(text="☑" if var.get() else "☐",
                       fg=CLR_ACCENT if var.get() else "#AAAAAA")

        btn.config(command=_toggle)

    tk.Button(ctrl, text="▶  Go", bg=CLR_ACCENT, fg=CLR_BTN_FG,
              activebackground="#0082C8",
              command=_go, **btn_cfg).pack(side="right")
    _make_toggle_btn(ctrl, "Re-download", refresh_var, side="right", padx=(0, 8))
    _make_toggle_btn(ctrl, "Export files", export_var,  side="right", padx=(0, 8))

    root.bind("<Return>", lambda e: _go())
    root.mainloop()
    return result_tickers, result_years, result_refresh, result_export


# ── Manual entry fallback (no DB) ─────────────────────────────────────────────

def _manual_entry_fallback() -> tuple[list[str], int, bool, bool]:
    result_tickers: list[str] = []
    result_years:   int       = YEARS_DEFAULT

    root = tk.Tk()
    root.title("Enter Tickers")
    root.configure(bg=CLR_BG)
    root.resizable(False, False)
    root.geometry("440x220")
    root.eval("tk::PlaceWindow . center")

    mono = tkfont.Font(family="Consolas", size=11)
    bold = tkfont.Font(family="Consolas", size=11, weight="bold")

    tk.Label(root,
             text="No saved tickers found.\nEnter symbols separated by commas:",
             bg=CLR_BG, fg=CLR_TEXT, font=bold, pady=14).pack()

    entry_var = tk.StringVar()
    entry = tk.Entry(root, textvariable=entry_var, font=mono,
                     width=36, relief="flat",
                     highlightthickness=1,
                     highlightcolor=CLR_ACCENT,
                     highlightbackground="#CCCCCC")
    entry.pack(pady=4)
    entry.focus_set()

    yf = tk.Frame(root, bg=CLR_BG)
    yf.pack(pady=6)
    tk.Label(yf, text="History:", bg=CLR_BG, fg=CLR_TEXT, font=bold).pack(side="left", padx=(0, 6))
    years_var = tk.StringVar(value=str(YEARS_DEFAULT))
    tk.Entry(yf, textvariable=years_var, font=mono,
             width=4, relief="flat",
             highlightthickness=1,
             highlightcolor=CLR_ACCENT,
             highlightbackground="#CCCCCC").pack(side="left")
    tk.Label(yf, text="yrs", bg=CLR_BG, fg=CLR_TEXT, font=mono).pack(side="left", padx=(4, 0))

    def _go():
        nonlocal result_tickers, result_years
        result_tickers = _parse_bulk(entry_var.get()) or [
            s.strip().upper() for s in entry_var.get().split(",") if s.strip()
        ]
        try:
            result_years = max(1, int(years_var.get()))
        except ValueError:
            result_years = YEARS_DEFAULT
        root.destroy()

    tk.Button(root, text="▶  Go", bg=CLR_ACCENT, fg="white",
              font=bold, relief="flat", padx=16, pady=8,
              command=_go).pack(pady=10)
    root.bind("<Return>", lambda e: _go())
    root.mainloop()
    return result_tickers, result_years, False, False