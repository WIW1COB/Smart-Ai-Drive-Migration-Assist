"""Dialog windows for the Migration Analysis Tool"""

import tkinter as tk
from tkinter import messagebox


def show_comparison_results_dialog(results, folder1_name, folder2_name, folder1_path, folder2_path, files1, files2):
    """
    Show interactive results dialog with file listing and details.
    
    Args:
        results: List of comparison results
        folder1_name: Name/path of platform folder
        folder2_name: Name/path of project folder
        folder1_path: Actual path to folder 1
        folder2_path: Actual path to folder 2
        files1: Dict of files in folder 1
        files2: Dict of files in folder 2
    """
    # NOTE: This is a placeholder - Full implementation in test.py lines ~3000-3500
    # Should implement the complete interactive results dialog
    print("show_comparison_results_dialog - TODO: Implement from test.py")
    messagebox.showinfo("Results", f"Comparison complete!\n{len(results)} files processed.")


def show_component_selection_dialog(components1, components2):
    """
    Show dialog to select components for online-online snapshot comparison.

    Tabs:
      1. Common Components  — checkboxes to select which common ones to compare
      2. Only in Snapshot 1 — read-only info list
      3. Only in Snapshot 2 — read-only info list
      4. Map Components     — auto-suggest + searchable manual mapping of unmatched names

    Returns:
        dict: {
            'canceled': bool,
            'selected': list of selected common component names,
            'only_in_snap1': list,
            'only_in_snap2': list,
            'common': list,
            'component_mappings': {snap1_name: snap2_name, ...}
        }
    """
    import tkinter.ttk as ttk
    from difflib import SequenceMatcher

    names1 = set(c.get('name', str(c)) for c in (components1 or []))
    names2 = set(c.get('name', str(c)) for c in (components2 or []))

    common_components = sorted(names1 & names2)
    only_in_snap1     = sorted(names1 - names2)
    only_in_snap2     = sorted(names2 - names1)
    has_unmatched     = bool(only_in_snap1 or only_in_snap2)

    # ── Auto-suggest similar name pairs ───────────────────────────────────
    def _auto_suggest(a_list, b_list, threshold=0.45):
        candidates = []
        for a in a_list:
            for b in b_list:
                score = SequenceMatcher(None, a, b).ratio()
                if score >= threshold:
                    candidates.append((a, b, score))
        candidates.sort(key=lambda x: -x[2])
        used_a, used_b = set(), set()
        out = []
        for a, b, s in candidates:
            if a not in used_a and b not in used_b:
                out.append((a, b, s))
                used_a.add(a)
                used_b.add(b)
        return out

    suggestions = _auto_suggest(only_in_snap1, only_in_snap2)

    # ── Dialog window ──────────────────────────────────────────────────────
    dialog = tk.Toplevel()
    dialog.title("Select Components for Comparison - Online Mode")
    dialog.geometry("1150x800")
    dialog.minsize(900, 600)
    dialog.resizable(True, True)
    dialog.transient()
    dialog.grab_set()

    result = {
        'canceled': True,
        'selected': [],
        'only_in_snap1': only_in_snap1,
        'only_in_snap2': only_in_snap2,
        'common': common_components,
        'component_mappings': {},
    }

    # ── Header ─────────────────────────────────────────────────────────────
    hdr = tk.Frame(dialog, bg='#2c3e50')
    hdr.pack(fill=tk.X)
    tk.Label(hdr, text="📋  Component Selection  —  Online Snapshot Comparison",
             font=("Arial", 13, "bold"), bg='#2c3e50', fg='white').pack(pady=(8, 2))

    unmatched_total = len(only_in_snap1) + len(only_in_snap2)
    stats_parts = [
        f"Snapshot 1: {len(names1)} components",
        f"Snapshot 2: {len(names2)} components",
        f"Common: {len(common_components)}",
        f"Only in Snap1: {len(only_in_snap1)}",
        f"Only in Snap2: {len(only_in_snap2)}",
    ]
    if has_unmatched:
        stats_parts.append(f"⚠ {unmatched_total} unmatched  →  use the Map tab")
    tk.Label(hdr, text="   |   ".join(stats_parts),
             font=("Arial", 9), bg='#2c3e50', fg='#bdc3c7').pack(pady=(0, 8))

    # ── Notebook ───────────────────────────────────────────────────────────
    notebook = ttk.Notebook(dialog)
    notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    # ────────────────────────────────────────────────────────────────────────
    # Tab 1 – Common Components (selectable checkboxes)
    # ────────────────────────────────────────────────────────────────────────
    tab_common = ttk.Frame(notebook)
    notebook.add(tab_common, text=f"🔄 Common ({len(common_components)})")

    if has_unmatched:
        banner = tk.Frame(tab_common, bg='#fff3cd', bd=1, relief=tk.SOLID)
        banner.pack(fill=tk.X, padx=10, pady=(8, 0))
        tk.Label(banner,
                 text=(f"⚠  {len(only_in_snap1)} component(s) only in Snapshot 1 and "
                       f"{len(only_in_snap2)} only in Snapshot 2 are not compared by default.\n"
                       f"   Switch to the  🔗 Map Components  tab to pair them manually."),
                 font=("Arial", 9), bg='#fff3cd', fg='#856404',
                 justify=tk.LEFT).pack(anchor=tk.W, padx=8, pady=6)

    if common_components:
        tk.Label(tab_common,
                 text="Select which common components to compare:",
                 font=("Arial", 10), bg='white', justify=tk.LEFT).pack(anchor=tk.W, padx=10, pady=(8, 4))
        scrollframe = tk.Frame(tab_common)
        scrollframe.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        scrollbar = ttk.Scrollbar(scrollframe)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas = tk.Canvas(scrollframe, yscrollcommand=scrollbar.set, bg='white', highlightthickness=0)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=canvas.yview)
        inner_frame = tk.Frame(canvas, bg='white')
        canvas_window = canvas.create_window((0, 0), window=inner_frame, anchor=tk.NW)
    else:
        tk.Label(tab_common,
                 text="No common components found between the two snapshots.",
                 font=("Arial", 10, "italic"), fg='#888',
                 bg='white').pack(expand=True)
        inner_frame = None
        canvas = None
        canvas_window = None

    component_vars = {}
    if inner_frame is not None:
        for comp_name in common_components:
            var = tk.BooleanVar(value=True)
            component_vars[comp_name] = var
            tk.Checkbutton(inner_frame, text=comp_name, variable=var,
                           font=("Arial", 9), bg='white', activebackground='#ECF0F1',
                           anchor=tk.W).pack(fill=tk.X, padx=5, pady=2)

    def _on_frame_configure(event=None):
        if canvas and inner_frame:
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(canvas_window, width=canvas.winfo_width())

    if inner_frame:
        inner_frame.bind("<Configure>", _on_frame_configure)
    if canvas:
        canvas.bind("<Configure>", lambda e: _on_frame_configure())

    def _on_mousewheel(event):
        if canvas:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    dialog.bind_all("<MouseWheel>", _on_mousewheel)

    # ────────────────────────────────────────────────────────────────────────
    # Tab 2 – Only in Snapshot 1
    # ────────────────────────────────────────────────────────────────────────
    tab_snap1 = ttk.Frame(notebook)
    notebook.add(tab_snap1, text=f"📍 Only Snap1 ({len(only_in_snap1)})")
    tk.Label(tab_snap1,
             text="Components ONLY in Snapshot 1 (excluded unless mapped in the Map tab):",
             font=("Arial", 10), bg='white').pack(anchor=tk.W, padx=10, pady=8)
    text1 = tk.Text(tab_snap1, height=20, font=("Courier", 9), bg='#FFF3E0', fg='#E65100')
    text1.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
    text1.insert(tk.END, "\n".join(f"  • {c}" for c in only_in_snap1) if only_in_snap1 else "  (none)")
    text1.config(state=tk.DISABLED)

    # ────────────────────────────────────────────────────────────────────────
    # Tab 3 – Only in Snapshot 2
    # ────────────────────────────────────────────────────────────────────────
    tab_snap2 = ttk.Frame(notebook)
    notebook.add(tab_snap2, text=f"📍 Only Snap2 ({len(only_in_snap2)})")
    tk.Label(tab_snap2,
             text="Components ONLY in Snapshot 2 (excluded unless mapped in the Map tab):",
             font=("Arial", 10), bg='white').pack(anchor=tk.W, padx=10, pady=8)
    text2 = tk.Text(tab_snap2, height=20, font=("Courier", 9), bg='#E3F2FD', fg='#01579B')
    text2.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
    text2.insert(tk.END, "\n".join(f"  • {c}" for c in only_in_snap2) if only_in_snap2 else "  (none)")
    text2.config(state=tk.DISABLED)

    # ────────────────────────────────────────────────────────────────────────
    # Tab 4 – Component Mapping  (main panel, split: top=suggestions, bottom=manual+list)
    # ────────────────────────────────────────────────────────────────────────
    tab_map_outer = ttk.Frame(notebook)
    notebook.add(tab_map_outer, text="🔗 Map Components (0)")

    # Mutable state — list of [snap1_name, snap2_name]
    mapped_pairs = []

    # ── Helper: refresh the mappings list and tab label ───────────────────
    def _refresh_map_tab():
        mapped_list.delete(0, tk.END)
        for s1, s2 in mapped_pairs:
            mapped_list.insert(tk.END, f"  {s1}   ↔   {s2}")
        notebook.tab(tab_map_outer, text=f"🔗 Map Components ({len(mapped_pairs)})")
        map_count_lbl.config(text=f"{len(mapped_pairs)} pair(s) mapped — will be included in comparison")
        # rebuild filtered listboxes and live summary
        _filter_lb1()
        _filter_lb2()
        _update_summary()

    def _add_mapping(s1, s2):
        nonlocal mapped_pairs
        if not s1 or not s2:
            return
        mapped_pairs = [[a, b] for a, b in mapped_pairs if a != s1 and b != s2]
        mapped_pairs.append([s1, s2])
        _refresh_map_tab()

    def _remove_mapping():
        nonlocal mapped_pairs
        sel = mapped_list.curselection()
        if not sel:
            return
        mapped_pairs.pop(sel[0])
        _refresh_map_tab()

    def _apply_suggestions():
        for var, n1, n2 in suggestion_vars:
            if var.get():
                _add_mapping(n1, n2)

    def _apply_all_suggestions():
        for var, _, __ in suggestion_vars:
            var.set(True)
        _apply_suggestions()

    # ── Paned window: top = suggestions, bottom = manual + list ──────────
    pane = tk.PanedWindow(tab_map_outer, orient=tk.VERTICAL,
                          sashrelief=tk.RAISED, sashwidth=5,
                          bg='#dee2e6')
    pane.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

    # ── TOP PANE: Auto-suggestions ─────────────────────────────────────────
    sug_frame = tk.Frame(pane, bg='#eaf3fb')
    pane.add(sug_frame, minsize=80)

    sug_title_row = tk.Frame(sug_frame, bg='#1a5276')
    sug_title_row.pack(fill=tk.X)
    tk.Label(sug_title_row,
             text=f"  💡 Auto-Suggested Matches  ({len(suggestions)} pair(s) found by name similarity)",
             font=("Arial", 10, "bold"), bg='#1a5276', fg='white',
             anchor=tk.W).pack(side=tk.LEFT, pady=5, padx=6, fill=tk.X, expand=True)

    suggestion_vars = []

    if suggestions:
        # Scrollable canvas for suggestion rows
        sug_body = tk.Frame(sug_frame, bg='#eaf3fb')
        sug_body.pack(fill=tk.BOTH, expand=True)
        sug_sc = ttk.Scrollbar(sug_body, orient=tk.VERTICAL)
        sug_sc.pack(side=tk.RIGHT, fill=tk.Y)
        sug_cv = tk.Canvas(sug_body, bg='#eaf3fb', highlightthickness=0,
                           yscrollcommand=sug_sc.set)
        sug_cv.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sug_sc.config(command=sug_cv.yview)
        sug_inner = tk.Frame(sug_cv, bg='#eaf3fb')
        sug_cw = sug_cv.create_window((0, 0), window=sug_inner, anchor=tk.NW)

        def _sug_frame_cfg(e=None):
            sug_cv.configure(scrollregion=sug_cv.bbox('all'))
        def _sug_cv_cfg(e=None):
            sug_cv.itemconfig(sug_cw, width=sug_cv.winfo_width())
        sug_inner.bind('<Configure>', _sug_frame_cfg)
        sug_cv.bind('<Configure>', _sug_cv_cfg)

        for n1, n2, score in suggestions:
            pct = int(score * 100)
            var = tk.BooleanVar(value=pct >= 70)
            suggestion_vars.append((var, n1, n2))
            row_bg = '#dbeafe' if pct >= 70 else '#eaf3fb'
            row = tk.Frame(sug_inner, bg=row_bg, bd=0)
            row.pack(fill=tk.X, pady=1, padx=4)
            tk.Checkbutton(row, variable=var, bg=row_bg).pack(side=tk.LEFT)

            conf_color = '#117864' if pct >= 85 else ('#2980b9' if pct >= 70 else '#6e2990')
            pct_lbl = tk.Label(row, text=f"{pct}% match", width=10,
                               font=("Arial", 9, "bold"), bg=row_bg, fg=conf_color)
            pct_lbl.pack(side=tk.RIGHT, padx=(0, 8))

            tk.Label(row, text=n1, font=("Courier", 9), bg=row_bg, fg='#1a5276',
                     anchor=tk.W).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 4))
            tk.Label(row, text="↔", font=("Arial", 12, "bold"), bg=row_bg,
                     fg='#7d3c98').pack(side=tk.LEFT, padx=4)
            tk.Label(row, text=n2, font=("Courier", 9), bg=row_bg, fg='#014d80',
                     anchor=tk.W).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 2))

        sug_btn_row = tk.Frame(sug_frame, bg='#eaf3fb')
        sug_btn_row.pack(fill=tk.X, padx=6, pady=4)
        tk.Button(sug_btn_row, text="✓ Apply Checked",
                  font=("Arial", 9, "bold"), bg='#1a5276', fg='white',
                  padx=10, pady=3, command=_apply_suggestions).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(sug_btn_row, text="✓ Apply All",
                  font=("Arial", 9), bg='#2874a6', fg='white',
                  padx=10, pady=3, command=_apply_all_suggestions).pack(side=tk.LEFT, padx=(0, 6))
        tk.Label(sug_btn_row,
                 text="(pre-checked rows ≥70% similarity)",
                 font=("Arial", 8, "italic"), fg='#666', bg='#eaf3fb').pack(side=tk.LEFT)
    else:
        no_msg = ("All components matched by name — no cross-name mapping needed."
                  if not has_unmatched else
                  "No similar names found. Use manual mapping below.")
        tk.Label(sug_frame, text=f"  {no_msg}",
                 font=("Arial", 9, "italic"), bg='#eaf3fb', fg='#555').pack(anchor=tk.W, padx=10, pady=10)

    # ── BOTTOM PANE: Manual mapping + current mappings list ───────────────
    bot_frame = tk.Frame(pane, bg='#f5f5f5')
    pane.add(bot_frame, minsize=200)

    # Manual Mapping section
    man_lf = tk.LabelFrame(bot_frame, text="  🔧 Manual Mapping  —  Select one from each side, then click Map",
                            font=("Arial", 10, "bold"), bg='#fafafa',
                            fg='#4a235a', padx=6, pady=6)
    man_lf.pack(fill=tk.X, padx=8, pady=(6, 4))

    man_row_f = tk.Frame(man_lf, bg='#fafafa')
    man_row_f.pack(fill=tk.X, expand=True)

    # ── Left: Snap1 unmapped with search ──────────────────────────────────
    lf1 = tk.LabelFrame(man_row_f, text="Snapshot 1 — Unmatched",
                         font=("Arial", 9, "bold"), bg='#fff3e0', fg='#6e2600', padx=4, pady=4)
    lf1.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    s1_search = tk.StringVar()
    s1_ent = tk.Entry(lf1, textvariable=s1_search, font=("Arial", 9),
                      fg='#888', relief=tk.SOLID, bd=1)
    s1_ent.insert(0, "🔍 Search...")
    s1_ent.pack(fill=tk.X, padx=2, pady=(0, 2))

    lb1_sc = ttk.Scrollbar(lf1)
    lb1_sc.pack(side=tk.RIGHT, fill=tk.Y)
    lb1 = tk.Listbox(lf1, font=("Courier", 9), height=7, selectmode=tk.SINGLE,
                     bg='#fff3e0', fg='#6e2600', yscrollcommand=lb1_sc.set,
                     activestyle='dotbox', selectforeground='white',
                     selectbackground='#e65100', exportselection=False)
    lb1.pack(fill=tk.BOTH, expand=True)
    lb1_sc.config(command=lb1.yview)

    def _filter_lb1(*_):
        q = s1_search.get().lower().replace("🔍 search...", "")
        already = {p[0] for p in mapped_pairs}
        lb1.delete(0, tk.END)
        for n in only_in_snap1:
            if n not in already and q in n.lower():
                lb1.insert(tk.END, n)

    s1_search.trace_add('write', _filter_lb1)
    s1_ent.bind('<FocusIn>', lambda e: (s1_ent.delete(0, tk.END)
                                        if s1_ent.get() == "🔍 Search..." else None))
    for n in only_in_snap1:
        lb1.insert(tk.END, n)

    # ── Middle: arrow + Map button ────────────────────────────────────────
    mid_f = tk.Frame(man_row_f, bg='#fafafa', width=100)
    mid_f.pack(side=tk.LEFT, padx=6)
    mid_f.pack_propagate(False)
    tk.Label(mid_f, text="↔", font=("Arial", 20, "bold"),
             bg='#fafafa', fg='#7d3c98').pack(pady=(14, 4))

    def _do_manual_map():
        sel1 = lb1.curselection()
        sel2 = lb2.curselection()
        if not sel1 or not sel2:
            messagebox.showwarning("Selection needed",
                                   "Please select one component from each list.", parent=dialog)
            return
        _add_mapping(lb1.get(sel1[0]), lb2.get(sel2[0]))

    tk.Button(mid_f, text="Map ▶", font=("Arial", 10, "bold"),
              bg='#7d3c98', fg='white', padx=8, pady=6,
              command=_do_manual_map, relief=tk.RAISED, bd=2).pack(pady=4)
    tk.Label(mid_f, text="(or\ndbl-click)", font=("Arial", 8), bg='#fafafa',
             fg='#888').pack()

    # ── Right: Snap2 unmapped with search ─────────────────────────────────
    lf2 = tk.LabelFrame(man_row_f, text="Snapshot 2 — Unmatched",
                         font=("Arial", 9, "bold"), bg='#e3f2fd', fg='#014d80', padx=4, pady=4)
    lf2.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    s2_search = tk.StringVar()
    s2_ent = tk.Entry(lf2, textvariable=s2_search, font=("Arial", 9),
                      fg='#888', relief=tk.SOLID, bd=1)
    s2_ent.insert(0, "🔍 Search...")
    s2_ent.pack(fill=tk.X, padx=2, pady=(0, 2))

    lb2_sc = ttk.Scrollbar(lf2)
    lb2_sc.pack(side=tk.RIGHT, fill=tk.Y)
    lb2 = tk.Listbox(lf2, font=("Courier", 9), height=7, selectmode=tk.SINGLE,
                     bg='#e3f2fd', fg='#014d80', yscrollcommand=lb2_sc.set,
                     activestyle='dotbox', selectforeground='white',
                     selectbackground='#01579b', exportselection=False)
    lb2.pack(fill=tk.BOTH, expand=True)
    lb2_sc.config(command=lb2.yview)

    def _filter_lb2(*_):
        q = s2_search.get().lower().replace("🔍 search...", "")
        already = {p[1] for p in mapped_pairs}
        lb2.delete(0, tk.END)
        for n in only_in_snap2:
            if n not in already and q in n.lower():
                lb2.insert(tk.END, n)

    s2_search.trace_add('write', _filter_lb2)
    s2_ent.bind('<FocusIn>', lambda e: (s2_ent.delete(0, tk.END)
                                        if s2_ent.get() == "🔍 Search..." else None))
    for n in only_in_snap2:
        lb2.insert(tk.END, n)

    # Double-click to quick-map (selects matching row in other list + maps)
    def _on_lb1_dbl(event):
        sel = lb1.curselection()
        if sel:
            n1 = lb1.get(sel[0])
            # Try to auto-select the best match in lb2
            best, best_score = None, 0
            for i in range(lb2.size()):
                s = SequenceMatcher(None, n1, lb2.get(i)).ratio()
                if s > best_score:
                    best_score, best = s, i
            if best is not None:
                lb2.selection_clear(0, tk.END)
                lb2.selection_set(best)
                lb2.see(best)
            _do_manual_map()

    def _on_lb2_dbl(event):
        sel = lb2.curselection()
        if sel:
            n2 = lb2.get(sel[0])
            best, best_score = None, 0
            for i in range(lb1.size()):
                s = SequenceMatcher(None, n2, lb1.get(i)).ratio()
                if s > best_score:
                    best_score, best = s, i
            if best is not None:
                lb1.selection_clear(0, tk.END)
                lb1.selection_set(best)
                lb1.see(best)
            _do_manual_map()

    lb1.bind('<Double-Button-1>', _on_lb1_dbl)
    lb2.bind('<Double-Button-1>', _on_lb2_dbl)

    # ── Current Mappings list ──────────────────────────────────────────────
    mapped_lf = tk.LabelFrame(bot_frame, text="  ✅ Current Component Mappings (will be compared)",
                               font=("Arial", 10, "bold"), bg='#f0fff4', fg='#1a6b2a',
                               padx=6, pady=6)
    mapped_lf.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 4))

    mlist_frame = tk.Frame(mapped_lf, bg='#f0fff4')
    mlist_frame.pack(fill=tk.BOTH, expand=True)
    map_sc = ttk.Scrollbar(mlist_frame)
    map_sc.pack(side=tk.RIGHT, fill=tk.Y)
    mapped_list = tk.Listbox(mlist_frame, font=("Courier", 10), height=4,
                              bg='#f0fff4', fg='#1a6b2a', yscrollcommand=map_sc.set,
                              selectforeground='white', selectbackground='#1a6b2a')
    mapped_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    map_sc.config(command=mapped_list.yview)

    mbtn_row = tk.Frame(mapped_lf, bg='#f0fff4')
    mbtn_row.pack(anchor=tk.W, pady=(4, 0))
    tk.Button(mbtn_row, text="✗ Remove Selected", font=("Arial", 9),
              bg='#e74c3c', fg='white', padx=8, pady=3,
              command=_remove_mapping).pack(side=tk.LEFT, padx=(0, 8))
    tk.Button(mbtn_row, text="✗ Clear All", font=("Arial", 9),
              bg='#888', fg='white', padx=8, pady=3,
              command=lambda: (mapped_pairs.clear(), _refresh_map_tab())).pack(side=tk.LEFT)

    map_count_lbl = tk.Label(bot_frame, text="0 pair(s) mapped — will be included in comparison",
                              font=("Arial", 9, "italic"), fg='#1a6b2a', bg='#f5f5f5')
    map_count_lbl.pack(anchor=tk.W, padx=12, pady=(0, 4))

    # ── Bottom button bar ──────────────────────────────────────────────────
    button_frame = tk.Frame(dialog, bg='#2c3e50')
    button_frame.pack(fill=tk.X, padx=0, pady=0)

    quick_frame = tk.Frame(button_frame, bg='#2c3e50')
    quick_frame.pack(side=tk.LEFT, padx=12, pady=8)

    def _select_all():
        for v in component_vars.values():
            v.set(True)

    def _deselect_all():
        for v in component_vars.values():
            v.set(False)

    tk.Button(quick_frame, text="✓ Select All Common", command=_select_all,
              bg='#27ae60', fg='white', font=("Arial", 9), padx=8, pady=4).pack(side=tk.LEFT, padx=4)
    tk.Button(quick_frame, text="✗ Deselect All Common", command=_deselect_all,
              bg='#e74c3c', fg='white', font=("Arial", 9), padx=8, pady=4).pack(side=tk.LEFT, padx=4)

    action_frame = tk.Frame(button_frame, bg='#2c3e50')
    action_frame.pack(side=tk.RIGHT, padx=12, pady=8)

    # Summary label
    summary_lbl = tk.Label(action_frame,
                            text="", font=("Arial", 9), bg='#2c3e50', fg='#ecf0f1')
    summary_lbl.pack(side=tk.LEFT, padx=(0, 12))

    def _update_summary(*_):
        sel_count = sum(1 for v in component_vars.values() if v.get())
        map_count = len(mapped_pairs)
        total = sel_count + map_count
        summary_lbl.config(
            text=f"Will compare: {sel_count} common + {map_count} mapped = {total} component(s)"
        )

    # Trace component vars changes for live summary
    for v in component_vars.values():
        v.trace_add('write', _update_summary)
    _update_summary()

    def on_compare():
        result['selected'] = [comp for comp, var in component_vars.items() if var.get()]
        result['component_mappings'] = {s1: s2 for s1, s2 in mapped_pairs}
        result['canceled'] = False
        dialog.destroy()

    def on_cancel():
        result['canceled'] = True
        dialog.destroy()

    tk.Button(action_frame, text="▶  Compare Selected",
              command=on_compare,
              bg='#2980b9', fg='white', font=("Arial", 11, "bold"),
              padx=20, pady=6).pack(side=tk.LEFT, padx=6)
    tk.Button(action_frame, text="Cancel",
              command=on_cancel,
              bg='#95a5a6', fg='white', font=("Arial", 10),
              padx=16, pady=6).pack(side=tk.LEFT, padx=4)

    # Bind Enter key to "Compare"
    dialog.bind('<Return>', lambda e: on_compare())
    dialog.bind('<Escape>', lambda e: on_cancel())

    # ── Auto-navigate to Map tab when unmatched components exist ──────────
    if has_unmatched:
        dialog.after(50, lambda: notebook.select(tab_map_outer))

    # Centre on screen
    dialog.update_idletasks()
    x = (dialog.winfo_screenwidth()  // 2) - (dialog.winfo_width()  // 2)
    y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
    dialog.geometry(f"+{max(0, x)}+{max(0, y)}")

    dialog.wait_window()
    return result


def show_file_mapping_dialog(files1, files2, existing_mappings=None):
    """
    Show dialog for manual file mapping between two folders.
    
    Args:
        files1: Dict of files from folder 1
        files2: Dict of files from folder 2
        existing_mappings: Dict of existing custom mappings
    
    Returns:
        tuple: (confirmed, mappings_dict)
    """
    # NOTE: This is a placeholder - Full implementation in test.py
    # Should implement the complete file mapping dialog
    print("show_file_mapping_dialog - TODO: Implement from test.py")
    return False, {}
