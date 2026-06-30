"""
Switch Comparison Tool
======================
Scans source files (.h / .c) for ``#define`` switches and compares their
values between two folder trees (or pre-fetched content from RTC snapshots).

Typical usage from main_window.py::

    from src.gui.switch_comparison import SwitchComparisonViewer
    SwitchComparisonViewer(
        parent=self.root,
        folder1_path=...,
        folder2_path=...,
        source1_name="Platform (Snapshot 1)",
        source2_name="Project  (Snapshot 2)",
    )
"""

import html as _html
import logging
import os
import re
import subprocess
import threading
import webbrowser
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Extensions scanned for #define switches
# ---------------------------------------------------------------------------
SCAN_EXTENSIONS = {".h", ".c", ".hpp", ".cpp"}

# ---------------------------------------------------------------------------
# Regex – captures simple #define NAME VALUE lines.
# Excludes function-like macros (name immediately followed by '(').
# Group 1 = macro name, Group 2 = raw value (may contain trailing comment).
# ---------------------------------------------------------------------------
_DEFINE_RE = re.compile(
    r"^\s*#\s*define\s+"       # #define keyword
    r"([A-Za-z_][A-Za-z0-9_]*)"  # name (no '(' immediately after → not function macro)
    r"(?!\s*\()"               # negative look-ahead: NOT a function macro
    r"[ \t]+"                  # mandatory whitespace before value
    r"([^\\\n]+)",             # value up to end-of-line (no line-continuation)
    re.MULTILINE,
)

# Strip inline // and /* */ comments from a value string
_INLINE_COMMENT_RE = re.compile(r"\s*//.*$|/\*.*?\*/", re.DOTALL)


def _clean_value(raw: str) -> str:
    """Remove inline comments and surrounding whitespace from a #define value."""
    cleaned = _INLINE_COMMENT_RE.sub("", raw).strip()
    return cleaned


# ---------------------------------------------------------------------------
# Core scanning / comparison helpers
# ---------------------------------------------------------------------------

def extract_switches_from_folder(
    folder_path: str,
    progress_callback=None,
) -> Dict[str, dict]:
    """
    Walk *folder_path* and collect every simple ``#define NAME VALUE`` entry
    found in SCAN_EXTENSIONS files.

    If the same macro is defined in multiple files the **first** occurrence
    (alphabetical file order) is kept.

    Returns
    -------
    dict  ``{macro_name: {'value', 'file', 'line', 'full_path'}}``
    """
    switches: Dict[str, dict] = {}

    if not os.path.isdir(folder_path):
        logger.warning(f"extract_switches_from_folder: not a directory: {folder_path}")
        return switches

    all_files: List[str] = []
    for dirpath, _dirs, fnames in os.walk(folder_path):
        for fname in fnames:
            if os.path.splitext(fname)[1].lower() in SCAN_EXTENSIONS:
                all_files.append(os.path.join(dirpath, fname))

    all_files.sort()
    total = len(all_files)

    for idx, filepath in enumerate(all_files):
        if progress_callback:
            progress_callback(idx + 1, total, os.path.basename(filepath))
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read()

            rel_path = os.path.relpath(filepath, folder_path)

            for match in _DEFINE_RE.finditer(content):
                name = match.group(1)
                value = _clean_value(match.group(2))
                if not value:
                    continue
                if name not in switches:
                    line_num = content[: match.start()].count("\n") + 1
                    switches[name] = {
                        "value": value,
                        "file": rel_path,
                        "line": line_num,
                        "full_path": filepath,
                    }
        except Exception as exc:
            logger.debug(f"Skipping {filepath}: {exc}")

    logger.info(
        f"extract_switches_from_folder: {len(switches)} defines in {total} files "
        f"under {folder_path!r}"
    )
    return switches


def extract_switches_from_content(
    content_map: Dict[str, str],
    source_label: str = "snapshot",
) -> Dict[str, dict]:
    """
    Extract switches from a dict of ``{virtual_path: text_content}`` pairs.
    Used when file text has already been fetched from an RTC snapshot.

    Parameters
    ----------
    content_map : dict
        ``{relative_file_path: file_text_content}``
    source_label : str
        Human-readable label used in log messages only.

    Returns
    -------
    Same format as :func:`extract_switches_from_folder`.
    """
    switches: Dict[str, dict] = {}

    for rel_path, content in sorted(content_map.items()):
        ext = os.path.splitext(rel_path)[1].lower()
        if ext not in SCAN_EXTENSIONS:
            continue
        for match in _DEFINE_RE.finditer(content):
            name = match.group(1)
            value = _clean_value(match.group(2))
            if not value:
                continue
            if name not in switches:
                line_num = content[: match.start()].count("\n") + 1
                switches[name] = {
                    "value": value,
                    "file": rel_path,
                    "line": line_num,
                    "full_path": "",  # no local path for snapshot content
                }

    logger.info(
        f"extract_switches_from_content: {len(switches)} defines "
        f"from {len(content_map)} files ({source_label})"
    )
    return switches


def compare_switches(
    switches1: Dict[str, dict],
    switches2: Dict[str, dict],
) -> List[dict]:
    """
    Compare two switch dictionaries.

    Returns
    -------
    list of dicts with keys:
        ``name, value1, value2, file1, line1, full_path1,
          file2, line2, full_path2, status``
    where ``status`` is one of ``'different' | 'only_in_1' | 'only_in_2'``.
    """
    diffs: List[dict] = []
    all_names = sorted(set(switches1) | set(switches2))

    for name in all_names:
        s1 = switches1.get(name)
        s2 = switches2.get(name)

        if s1 and s2:
            if s1["value"] != s2["value"]:
                diffs.append(
                    dict(
                        name=name,
                        value1=s1["value"],
                        value2=s2["value"],
                        file1=s1["file"],
                        line1=s1["line"],
                        full_path1=s1.get("full_path", ""),
                        file2=s2["file"],
                        line2=s2["line"],
                        full_path2=s2.get("full_path", ""),
                        status="different",
                    )
                )
        elif s1:
            diffs.append(
                dict(
                    name=name,
                    value1=s1["value"],
                    value2="(not found)",
                    file1=s1["file"],
                    line1=s1["line"],
                    full_path1=s1.get("full_path", ""),
                    file2="",
                    line2=0,
                    full_path2="",
                    status="only_in_1",
                )
            )
        else:  # only in switches2
            diffs.append(
                dict(
                    name=name,
                    value1="(not found)",
                    value2=s2["value"],
                    file1="",
                    line1=0,
                    full_path1="",
                    file2=s2["file"],
                    line2=s2["line"],
                    full_path2=s2.get("full_path", ""),
                    status="only_in_2",
                )
            )

    return diffs


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class SwitchComparisonViewer:
    """
    Tkinter window for scanning and comparing ``#define`` switches between
    two folder trees.

    Parameters
    ----------
    parent
        Parent Tk widget.
    folder1_path, folder2_path : str
        Pre-filled paths (may be empty — user can browse).
    source1_name, source2_name : str
        Display labels used in headers and the HTML report.
    """

    def __init__(
        self,
        parent,
        folder1_path: str = "",
        folder2_path: str = "",
        source1_name: str = "Folder 1 / Snapshot 1",
        source2_name: str = "Folder 2 / Snapshot 2",
        auto_run: bool = False,
    ):
        self.parent = parent
        self.source1_name = source1_name
        self.source2_name = source2_name
        self.auto_run = auto_run
        self._all_diffs: List[dict] = []
        self._visible_diffs: List[dict] = []
        self._sw1: Dict[str, dict] = {}
        self._sw2: Dict[str, dict] = {}

        self._build_ui(folder1_path, folder2_path)

        if auto_run and folder1_path and folder2_path:
            self.win.after(150, self._run)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self, f1: str, f2: str) -> None:
        win = tk.Toplevel(self.parent)
        win.title("🔀 Switch Comparison")
        win.geometry("1150x750")
        win.config(bg="#EAF3FB")
        win.minsize(900, 500)
        self.win = win

        # ── Header ────────────────────────────────────────────────────
        hdr = tk.Frame(win, bg="#003366")
        hdr.pack(fill="x")
        tk.Label(
            hdr,
            text="🔀  Switch Comparison  (#define values)",
            font=("Segoe UI", 14, "bold"),
            bg="#003366",
            fg="white",
        ).pack(side="left", padx=20, pady=12)

        # ── Input rows ────────────────────────────────────────────────
        inp = tk.Frame(win, bg="#EAF3FB")
        inp.pack(fill="x", padx=10, pady=(8, 0))

        for row_idx, (label, default, attr) in enumerate(
            [
                ("Source 1 (Platform / Snapshot 1):", f1, "folder1_var"),
                ("Source 2 (Project  / Snapshot 2):", f2, "folder2_var"),
            ]
        ):
            row = tk.Frame(inp, bg="#EAF3FB")
            row.pack(fill="x", pady=2)
            tk.Label(
                row,
                text=label,
                bg="#EAF3FB",
                font=("Segoe UI", 10, "bold"),
                width=35,
                anchor="w",
            ).pack(side="left")
            var = tk.StringVar(value=default)
            setattr(self, attr, var)
            tk.Entry(row, textvariable=var, width=65).pack(side="left", padx=4)
            tk.Button(
                row,
                text="Browse",
                bg="#007B3E",
                fg="white",
                font=("Segoe UI", 9),
                command=lambda v=var: self._browse(v),
            ).pack(side="left", padx=2)

        # ── Options + action buttons ──────────────────────────────────
        opt = tk.Frame(win, bg="#EAF3FB")
        opt.pack(fill="x", padx=10, pady=(6, 0))

        # Status filter vars — always-on when auto_run (show everything)
        self.show_only_diff_var = tk.BooleanVar(value=True)
        self.show_only_in_1_var = tk.BooleanVar(value=True)
        self.show_only_in_2_var = tk.BooleanVar(value=True)
        self.filter_var = tk.StringVar()

        if not self.auto_run:
            # Manual mode: show filter controls and Run button
            tk.Label(
                opt, text="Filter (name contains):", bg="#EAF3FB", font=("Segoe UI", 10)
            ).pack(side="left", padx=(0, 4))
            self.filter_var.trace_add("write", lambda *_: self._apply_filter())
            tk.Entry(opt, textvariable=self.filter_var, width=22).pack(side="left", padx=(0, 8))

            self.show_only_diff_var.set(True)
            self.show_only_in_1_var.set(False)
            self.show_only_in_2_var.set(False)

            tk.Checkbutton(
                opt,
                text="Show only changed values",
                variable=self.show_only_diff_var,
                bg="#EAF3FB",
                font=("Segoe UI", 10),
                command=self._apply_filter,
            ).pack(side="left", padx=4)

            tk.Checkbutton(
                opt,
                text="Include only-in-S1",
                variable=self.show_only_in_1_var,
                bg="#EAF3FB",
                font=("Segoe UI", 10),
                command=self._apply_filter,
            ).pack(side="left", padx=4)

            tk.Checkbutton(
                opt,
                text="Include only-in-S2",
                variable=self.show_only_in_2_var,
                bg="#EAF3FB",
                font=("Segoe UI", 10),
                command=self._apply_filter,
            ).pack(side="left", padx=4)

            tk.Button(
                opt,
                text="▶  Run Comparison",
                bg="#003366",
                fg="white",
                font=("Segoe UI", 10, "bold"),
                padx=12,
                pady=4,
                command=self._run,
            ).pack(side="right", padx=4)

        tk.Button(
            opt,
            text="💾 Export HTML",
            bg="#0066CC",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            padx=10,
            pady=4,
            command=self._export_html,
        ).pack(side="right", padx=4)

        # ── Progress ──────────────────────────────────────────────────
        prog_frame = tk.Frame(win, bg="#EAF3FB")
        prog_frame.pack(fill="x", padx=10, pady=(4, 0))

        self.progress_label = tk.Label(
            prog_frame,
            text="Scanning…" if self.auto_run else "Ready. Select folders and click  ▶ Run Comparison.",
            bg="#EAF3FB",
            font=("Segoe UI", 9),
            fg="#555555",
        )
        self.progress_label.pack(anchor="w")

        self.progress_bar = ttk.Progressbar(
            prog_frame, length=700, mode="determinate"
        )
        self.progress_bar.pack(anchor="w", pady=(2, 0))

        # ── Stats banner ──────────────────────────────────────────────
        self.stats_label = tk.Label(
            win, text="", bg="#EAF3FB", font=("Segoe UI", 9, "bold"), fg="#003366"
        )
        self.stats_label.pack(anchor="w", padx=12, pady=(2, 0))

        # ── Results tree ──────────────────────────────────────────────
        tree_frame = tk.Frame(win)
        tree_frame.pack(fill="both", expand=True, padx=10, pady=4)

        cols = ("switch_name", "value1", "value2", "status", "file1_info", "file2_info")
        self.tree = ttk.Treeview(
            tree_frame,
            columns=cols,
            show="headings",
            selectmode="browse",
        )

        s1_hdr = (self.source1_name[:25] + "…") if len(self.source1_name) > 27 else self.source1_name
        s2_hdr = (self.source2_name[:25] + "…") if len(self.source2_name) > 27 else self.source2_name

        self.tree.heading("switch_name", text="Switch Name")
        self.tree.heading("value1",      text=f"Value  ◀  {s1_hdr}")
        self.tree.heading("value2",      text=f"Value  ▶  {s2_hdr}")
        self.tree.heading("status",      text="Status")
        self.tree.heading("file1_info",  text=f"File in {s1_hdr} (dbl-click to open)")
        self.tree.heading("file2_info",  text=f"File in {s2_hdr} (dbl-click to open)")

        self.tree.column("switch_name", width=230, anchor="w", stretch=False)
        self.tree.column("value1",      width=195, anchor="w", stretch=False)
        self.tree.column("value2",      width=195, anchor="w", stretch=False)
        self.tree.column("status",      width=100, anchor="center", stretch=False)
        self.tree.column("file1_info",  width=250, anchor="w")
        self.tree.column("file2_info",  width=250, anchor="w")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical",   command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        self.tree.tag_configure("different", background="#FFF3CD")
        self.tree.tag_configure("only_in_1", background="#D4EDDA")
        self.tree.tag_configure("only_in_2", background="#F8D7DA")

        self.tree.bind("<Double-1>", self._on_double_click)

        # ── Footer hint ───────────────────────────────────────────────
        tk.Label(
            win,
            text=(
                "Only RBFS_ switches are shown.   "
                "Double-click a row to open its source file.   "
                "🟡 Changed value   🟢 Only in Source 1   🔴 Only in Source 2"
            ),
            bg="#EAF3FB",
            font=("Segoe UI", 8),
            fg="#888888",
        ).pack(pady=(0, 4))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _browse(self, var: tk.StringVar) -> None:
        path = filedialog.askdirectory(title="Select Folder", parent=self.win)
        if path:
            var.set(path)

    def _run(self) -> None:
        f1 = self.folder1_var.get().strip()
        f2 = self.folder2_var.get().strip()

        if not f1 or not f2:
            messagebox.showerror(
                "Missing Input", "Please provide both folder paths.", parent=self.win
            )
            return
        if not os.path.isdir(f1):
            messagebox.showerror(
                "Invalid Path", f"Source 1 folder not found:\n{f1}", parent=self.win
            )
            return
        if not os.path.isdir(f2):
            messagebox.showerror(
                "Invalid Path", f"Source 2 folder not found:\n{f2}", parent=self.win
            )
            return

        self.progress_bar["value"] = 0
        self.stats_label.config(text="")
        self.progress_label.config(text="Scanning Source 1…")
        for item in self.tree.get_children():
            self.tree.delete(item)

        def _worker() -> None:
            try:
                # ── Scan Source 1 ──────────────────────────────────────
                def _cb1(cur, total, msg):
                    pct = int(cur / total * 50) if total else 0
                    self.win.after(
                        0,
                        lambda: (
                            self.progress_bar.config(value=pct),
                            self.progress_label.config(
                                text=f"[Source 1]  {cur}/{total}  {msg}"
                            ),
                        ),
                    )

                sw1 = extract_switches_from_folder(f1, progress_callback=_cb1)

                # ── Scan Source 2 ──────────────────────────────────────
                self.win.after(
                    0, lambda: self.progress_label.config(text="Scanning Source 2…")
                )

                def _cb2(cur, total, msg):
                    pct = 50 + int(cur / total * 50) if total else 50
                    self.win.after(
                        0,
                        lambda: (
                            self.progress_bar.config(value=pct),
                            self.progress_label.config(
                                text=f"[Source 2]  {cur}/{total}  {msg}"
                            ),
                        ),
                    )

                sw2 = extract_switches_from_folder(f2, progress_callback=_cb2)

                diffs = compare_switches(sw1, sw2)
                self._all_diffs = diffs
                self._sw1 = sw1
                self._sw2 = sw2

                self.win.after(
                    0, lambda: self._finish(diffs, len(sw1), len(sw2))
                )

            except Exception as exc:
                logger.error(f"Switch comparison thread error: {exc}", exc_info=True)
                self.win.after(
                    0,
                    lambda: messagebox.showerror(
                        "Error", str(exc), parent=self.win
                    ),
                )

        threading.Thread(target=_worker, daemon=True).start()

    def _finish(self, diffs: List[dict], total1: int, total2: int) -> None:
        self.progress_bar["value"] = 100
        n_diff  = sum(1 for d in diffs if d["status"] == "different")
        n_only1 = sum(1 for d in diffs if d["status"] == "only_in_1")
        n_only2 = sum(1 for d in diffs if d["status"] == "only_in_2")
        self.stats_label.config(
            text=(
                f"Defines scanned: {total1} in Source 1,  {total2} in Source 2   │   "
                f"Differences: {n_diff} changed,  {n_only1} only in S1,  {n_only2} only in S2"
            )
        )
        self.progress_label.config(text="✅ Scan complete.")
        self._apply_filter()

    def _apply_filter(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)

        if not self._all_diffs:
            return

        filter_text  = self.filter_var.get().strip().lower()
        only_diff    = self.show_only_diff_var.get()
        inc_only1    = self.show_only_in_1_var.get()
        inc_only2    = self.show_only_in_2_var.get()

        visible: List[dict] = []
        for d in self._all_diffs:
            # Mandatory prefix filter: only RBFS_ switches are shown
            if not d["name"].startswith("RBFS_"):
                continue
            st = d["status"]
            # Status filter
            if st == "different":
                if not only_diff:
                    continue
            elif st == "only_in_1":
                if not inc_only1:
                    continue
            elif st == "only_in_2":
                if not inc_only2:
                    continue
            # Name filter (additional user text filter on top of RBFS_ prefix)
            if filter_text and filter_text not in d["name"].lower():
                continue
            visible.append(d)

        self._visible_diffs = visible

        for idx, d in enumerate(visible):
            st = d["status"]
            if st == "different":
                tag        = "different"
                status_txt = "🟡 Changed"
            elif st == "only_in_1":
                tag        = "only_in_1"
                status_txt = "🟢 Only S1"
            else:
                tag        = "only_in_2"
                status_txt = "🔴 Only S2"

            f1_info = (
                f"{d['file1']}  (line {d['line1']})" if d.get("file1") else "—"
            )
            f2_info = (
                f"{d['file2']}  (line {d['line2']})" if d.get("file2") else "—"
            )

            self.tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(
                    d["name"],
                    d["value1"],
                    d["value2"],
                    status_txt,
                    f1_info,
                    f2_info,
                ),
                tags=(tag,),
            )

    def _on_double_click(self, event) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        iid = int(sel[0])
        if iid >= len(self._visible_diffs):
            return
        d = self._visible_diffs[iid]

        # Decide which file to open based on clicked column
        col = self.tree.identify_column(event.x)   # "#1" … "#6"
        col_idx = int(col.replace("#", "")) if col.startswith("#") else 0

        # col 5 = file1_info, col 6 = file2_info; default open source-1 file
        if col_idx == 6:
            fp = d.get("full_path2", "")
        else:
            fp = d.get("full_path1", "") or d.get("full_path2", "")

        if fp and os.path.isfile(fp):
            try:
                os.startfile(fp)
            except Exception:
                try:
                    subprocess.Popen(["notepad", fp])
                except Exception:
                    messagebox.showinfo(
                        "File Path", f"File:\n{fp}", parent=self.win
                    )
        else:
            # For snapshot-fetched content (no local file) show the path info
            info = d.get("file1") or d.get("file2") or "(no file path)"
            messagebox.showinfo(
                "Switch Location",
                f"Switch: {d['name']}\n\n"
                f"Source 1:  {d['file1'] or '—'}  (line {d['line1']})\n"
                f"Source 2:  {d['file2'] or '—'}  (line {d['line2']})",
                parent=self.win,
            )

    def _export_html(self) -> None:
        if not self._all_diffs:
            messagebox.showinfo(
                "No Data", "Run a comparison first.", parent=self.win
            )
            return

        path = filedialog.asksaveasfilename(
            title="Save Switch Comparison Report",
            defaultextension=".html",
            filetypes=[("HTML file", "*.html"), ("All files", "*.*")],
            parent=self.win,
        )
        if not path:
            return

        try:
            _write_html_report(
                path,
                self._all_diffs,
                self.source1_name,
                self.source2_name,
            )
            messagebox.showinfo(
                "Exported", f"Report saved to:\n{path}", parent=self.win
            )
            webbrowser.open(path)
        except Exception as exc:
            messagebox.showerror("Export Error", str(exc), parent=self.win)


# ---------------------------------------------------------------------------
# HTML report generator (standalone function so it can be called headlessly)
# ---------------------------------------------------------------------------

def _write_html_report(
    html_path: str,
    diffs: List[dict],
    source1_name: str,
    source2_name: str,
) -> None:
    """Write a self-contained HTML Switch Comparison report to *html_path*."""

    s1 = _html.escape(source1_name)
    s2 = _html.escape(source2_name)

    different = [d for d in diffs if d["status"] == "different"]
    only1     = [d for d in diffs if d["status"] == "only_in_1"]
    only2     = [d for d in diffs if d["status"] == "only_in_2"]

    rows_html = ""
    for d in diffs:
        if d["status"] == "different":
            bg, label = "#fff3cd", "Changed"
        elif d["status"] == "only_in_1":
            bg, label = "#d4edda", "Only in S1"
        else:
            bg, label = "#f8d7da", "Only in S2"

        fp1 = d.get("full_path1", "")
        fp2 = d.get("full_path2", "")
        file1_cell = (
            f'<a href="file:///{_html.escape(fp1)}" title="{_html.escape(d["file1"])}">'
            f'{_html.escape(d["file1"])} (L{d["line1"]})</a>'
            if fp1 else _html.escape(d.get("file1") or "—")
        )
        file2_cell = (
            f'<a href="file:///{_html.escape(fp2)}" title="{_html.escape(d["file2"])}">'
            f'{_html.escape(d["file2"])} (L{d["line2"]})</a>'
            if fp2 else _html.escape(d.get("file2") or "—")
        )

        rows_html += (
            f'<tr style="background:{bg}">'
            f'<td><code>{_html.escape(d["name"])}</code></td>'
            f'<td><code>{_html.escape(d["value1"])}</code></td>'
            f'<td><code>{_html.escape(d["value2"])}</code></td>'
            f'<td style="text-align:center">{_html.escape(label)}</td>'
            f'<td>{file1_cell}</td>'
            f'<td>{file2_cell}</td>'
            f'</tr>\n'
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Switch Comparison Report</title>
  <style>
    body  {{ font-family: "Segoe UI", Arial, sans-serif; margin: 0;
             background: #f0f4f8; color: #24292e; }}
    header {{ background: #003366; color: white; padding: 18px 30px; }}
    header h1 {{ margin: 0 0 4px; font-size: 20px; }}
    header p  {{ margin: 0; font-size: 12px; color: #b0c4de; }}
    .summary {{ display: flex; gap: 14px; padding: 14px 30px; flex-wrap: wrap; }}
    .card {{ background: white; border-radius: 8px; padding: 12px 18px;
              border-left: 4px solid; min-width: 130px;
              box-shadow: 0 1px 4px rgba(0,0,0,.1); }}
    .card .num {{ font-size: 28px; font-weight: 700; }}
    .card .lbl {{ font-size: 11px; color: #57606a; margin-top: 2px; }}
    .c-amber {{ border-color: #9a6700; }} .c-amber .num {{ color: #9a6700; }}
    .c-green {{ border-color: #1a7f37; }} .c-green .num {{ color: #1a7f37; }}
    .c-red   {{ border-color: #cf222e; }} .c-red .num   {{ color: #cf222e; }}
    table {{ border-collapse: collapse;
              width: calc(100% - 60px); margin: 0 30px 30px;
              background: white; border-radius: 8px; overflow: hidden;
              box-shadow: 0 1px 4px rgba(0,0,0,.1); }}
    thead tr {{ background: #003366; color: white; }}
    th {{ padding: 9px 10px; text-align: left; font-size: 12px; font-weight: 600; }}
    td {{ padding: 7px 10px; border-bottom: 1px solid #e8eaed; font-size: 12px; }}
    tbody tr:hover {{ opacity: .85; }}
    code {{ font-family: "Courier New", monospace; }}
    a    {{ color: #0969da; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .ts  {{ font-size: 10px; color: #888; padding: 0 30px 20px; }}
  </style>
</head>
<body>
<header>
  <h1>🔀 Switch Comparison Report</h1>
  <p>Source 1: <strong>{s1}</strong> &nbsp;|&nbsp; Source 2: <strong>{s2}</strong></p>
</header>

<div class="summary">
  <div class="card c-amber">
    <div class="num">{len(different)}</div>
    <div class="lbl">Changed values</div>
  </div>
  <div class="card c-green">
    <div class="num">{len(only1)}</div>
    <div class="lbl">Only in Source 1</div>
  </div>
  <div class="card c-red">
    <div class="num">{len(only2)}</div>
    <div class="lbl">Only in Source 2</div>
  </div>
</div>

<table>
  <thead>
    <tr>
      <th>Switch Name</th>
      <th>Value in {s1}</th>
      <th>Value in {s2}</th>
      <th>Status</th>
      <th>File in {s1}</th>
      <th>File in {s2}</th>
    </tr>
  </thead>
  <tbody>
{rows_html}
  </tbody>
</table>

<p class="ts">Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
</body>
</html>"""

    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(html)

    logger.info(f"Switch comparison HTML report written: {html_path}")
