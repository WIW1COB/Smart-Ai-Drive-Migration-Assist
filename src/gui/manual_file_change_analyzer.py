"""
Manual File Change Analyzer
===========================
Interactive AI-powered tool for analyzing the impact of manual file changes.

Tabs:
  1. File Editor      – select file, edit content, compare with original
  2. Dependency Map   – direct & indirect includes; files that depend on this
  3. Impact Analysis  – APIs exposed/used, call hierarchy, impacted files
  4. Validation       – syntax checks, interface mismatches, config issues
  5. AI Suggestions   – AI-generated recommendations for dependent-file updates
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import difflib

# ---------------------------------------------------------------------------
# Dependency graph (optional – graceful fallback when not available)
# ---------------------------------------------------------------------------
try:
    _GUI_DIR = os.path.dirname(os.path.abspath(__file__))
    _SRC_DIR = os.path.dirname(_GUI_DIR)
    if _SRC_DIR not in sys.path:
        sys.path.insert(0, _SRC_DIR)
    from dependency_graph import DependencyGraphBuilder, DependencyGraph, ImpactAnalyzer
    _DEP_AVAILABLE = True
except ImportError:
    _DEP_AVAILABLE = False
    DependencyGraphBuilder = None
    DependencyGraph = None
    ImpactAnalyzer = None


# ---------------------------------------------------------------------------
# Helper – lightweight C/C++ syntax validator
# ---------------------------------------------------------------------------

class _CValidator:
    """Heuristic syntax/interface validator for C/C++ files."""

    BRACE_RE   = re.compile(r'[{}]')
    PAREN_RE   = re.compile(r'[()]')
    BRACKET_RE = re.compile(r'[\[\]]')
    FUNC_RE    = re.compile(r'^\s*\w[\w\s\*]+\s+(\w+)\s*\(', re.MULTILINE)
    INCLUDE_RE = re.compile(r'^\s*#include\s+[<"](.+?)[>"]', re.MULTILINE)

    @classmethod
    def validate(cls, content: str, filename: str = "") -> List[Dict]:
        """Return list of {line, severity, message} dicts."""
        issues: List[Dict] = []

        lines = content.splitlines()

        # -- brace balancing --
        depth = 0
        for lno, ln in enumerate(lines, 1):
            stripped = cls._strip_comments(ln)
            for ch in stripped:
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth < 0:
                        issues.append({"line": lno, "severity": "error",
                                        "message": "Unmatched closing brace '}'."})
                        depth = 0
        if depth > 0:
            issues.append({"line": len(lines), "severity": "error",
                            "message": f"{depth} unclosed brace(s) at end of file."})

        # -- missing semicolons after struct/enum blocks --
        for lno, ln in enumerate(lines, 1):
            stripped = ln.strip()
            if stripped == '}' and lno < len(lines):
                next_ln = lines[lno].strip() if lno < len(lines) else ""
                if next_ln and not next_ln.startswith(('/', '*', '#', '}', ';')):
                    pass  # heuristic – skip complex case

        # -- long lines --
        for lno, ln in enumerate(lines, 1):
            if len(ln) > 200:
                issues.append({"line": lno, "severity": "warning",
                                "message": f"Line very long ({len(ln)} chars); may affect readability."})

        # -- functions without return type --
        for match in cls.FUNC_RE.finditer(content):
            lno = content[:match.start()].count('\n') + 1
            func_name = match.group(1)
            if func_name in ('if', 'for', 'while', 'switch', 'return', 'sizeof'):
                continue
            lead = match.group(0).strip()
            if lead.startswith(('if', 'for', 'while', 'switch')):
                continue

        # -- duplicate #include guards check --
        includes_seen: Set[str] = set()
        for match in cls.INCLUDE_RE.finditer(content):
            inc = match.group(1)
            if inc in includes_seen:
                lno = content[:match.start()].count('\n') + 1
                issues.append({"line": lno, "severity": "warning",
                                "message": f"Duplicate #include: {inc}"})
            includes_seen.add(inc)

        return issues

    @staticmethod
    def _strip_comments(line: str) -> str:
        """Remove inline // comments from a line."""
        in_str = False
        i = 0
        while i < len(line):
            if line[i] == '"' and (i == 0 or line[i-1] != '\\'):
                in_str = not in_str
            if not in_str and line[i:i+2] == '//':
                return line[:i]
            i += 1
        return line


# ---------------------------------------------------------------------------
# Lightweight API extractor
# ---------------------------------------------------------------------------

class _APIExtractor:
    """Extract exported and imported APIs from C/C++ source."""

    FUNC_DEF_RE = re.compile(
        r'^(?!(?:if|for|while|switch|return)\s)'
        r'(?:(?:static|inline|extern|const|volatile)\s+)*'
        r'([\w\*]+(?:\s+[\w\*]+)*)\s+'
        r'(\w+)\s*\([^)]*\)\s*\{',
        re.MULTILINE
    )
    FUNC_DECL_RE = re.compile(
        r'^(?:(?:extern)\s+)?'
        r'([\w\*]+(?:\s+[\w\*]+)*)\s+'
        r'(\w+)\s*\([^)]*\)\s*;',
        re.MULTILINE
    )
    CALL_RE = re.compile(r'\b(\w+)\s*\(')
    INCLUDE_RE = re.compile(r'^\s*#include\s+[<"](.+?)[>"]', re.MULTILINE)

    _KEYWORDS = frozenset({
        'if', 'for', 'while', 'switch', 'return', 'sizeof', 'typedef',
        'struct', 'enum', 'union', 'else', 'case', 'break', 'continue',
        'goto', 'do', 'void', 'int', 'char', 'unsigned', 'signed',
        'long', 'short', 'double', 'float',
    })

    @classmethod
    def extract(cls, content: str) -> Dict:
        defined_funcs: List[Dict] = []
        declared_funcs: List[Dict] = []
        calls: List[str] = []
        includes: List[str] = []

        for m in cls.FUNC_DEF_RE.finditer(content):
            name = m.group(2)
            if name in cls._KEYWORDS:
                continue
            lno = content[:m.start()].count('\n') + 1
            defined_funcs.append({"name": name, "return_type": m.group(1).strip(), "line": lno})

        for m in cls.FUNC_DECL_RE.finditer(content):
            name = m.group(2)
            if name in cls._KEYWORDS:
                continue
            lno = content[:m.start()].count('\n') + 1
            declared_funcs.append({"name": name, "return_type": m.group(1).strip(), "line": lno})

        defined_names = {f["name"] for f in defined_funcs}
        for m in cls.CALL_RE.finditer(content):
            name = m.group(1)
            if name not in cls._KEYWORDS and name not in defined_names:
                calls.append(name)

        for m in cls.INCLUDE_RE.finditer(content):
            includes.append(m.group(1))

        return {
            "defined": defined_funcs,
            "declared": declared_funcs,
            "calls": sorted(set(calls) - cls._KEYWORDS),
            "includes": includes,
        }


# ---------------------------------------------------------------------------
# Main window class
# ---------------------------------------------------------------------------

class ManualFileChangeAnalyzer:
    """
    Main window for Manual File Change Analysis.

    Open with:
        ManualFileChangeAnalyzer(parent, workspace_path="<optional>")
    """

    # Colours (Bosch palette)
    _BG      = "#EAF3FB"
    _HDR     = "#003366"
    _ACCENT  = "#007B3E"
    _WARN    = "#E65100"
    _ERR     = "#B71C1C"
    _INFO    = "#0D47A1"

    def __init__(self, parent, workspace_path: str = ""):
        self._parent = parent
        self._workspace_path = workspace_path

        # State
        self._file_path: str = ""
        self._original_content: str = ""
        self._dep_graph: Optional["DependencyGraph"] = None
        self._impact_analyzer: Optional["ImpactAnalyzer"] = None
        self._graph_loading = False
        self._api_info: Optional[Dict] = None

        # Build UI
        self.window = tk.Toplevel(parent)
        self.window.title("Manual File Change Analyzer")
        self.window.geometry("1280x820")
        self.window.minsize(1000, 650)
        self.window.configure(bg=self._BG)
        self.window.grid_rowconfigure(1, weight=1)
        self.window.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_workspace_bar()
        self._build_notebook()
        self._build_status_bar()

        if workspace_path and os.path.isdir(workspace_path):
            self._schedule_graph_build(workspace_path)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_header(self):
        hdr = tk.Frame(self.window, bg=self._HDR, height=64)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)

        tk.Label(
            hdr, text="🛠  Manual File Change Analyzer",
            font=("Segoe UI", 16, "bold"), bg=self._HDR, fg="white"
        ).pack(side="left", padx=20, pady=14)

        tk.Label(
            hdr, text="Select a file, edit it, and analyse the full impact before committing changes",
            font=("Segoe UI", 9), bg=self._HDR, fg="#B8D8FF"
        ).pack(side="left", padx=8, pady=14)

    def _build_workspace_bar(self):
        bar = tk.Frame(self.window, bg="#D6E8F7", pady=6)
        bar.grid(row=1, column=0, sticky="ew")

        tk.Label(bar, text="Workspace:", font=("Segoe UI", 10, "bold"),
                 bg="#D6E8F7").pack(side="left", padx=(12, 4))

        self._ws_var = tk.StringVar(value=self._workspace_path)
        ws_entry = tk.Entry(bar, textvariable=self._ws_var, font=("Segoe UI", 9), width=55,
                            state="readonly")
        ws_entry.pack(side="left", padx=4)

        tk.Button(bar, text="Browse…", bg=self._ACCENT, fg="white",
                  font=("Segoe UI", 9), padx=10,
                  command=self._browse_workspace).pack(side="left", padx=4)

        tk.Label(bar, text="File:", font=("Segoe UI", 10, "bold"),
                 bg="#D6E8F7").pack(side="left", padx=(14, 4))

        self._file_var = tk.StringVar()
        file_entry = tk.Entry(bar, textvariable=self._file_var, font=("Segoe UI", 9), width=45,
                              state="readonly")
        file_entry.pack(side="left", padx=4)

        tk.Button(bar, text="Select File…", bg=self._INFO, fg="white",
                  font=("Segoe UI", 9), padx=10,
                  command=self._select_file).pack(side="left", padx=4)

        self._dep_status_var = tk.StringVar(value="⚫ Graph: not built")
        tk.Label(bar, textvariable=self._dep_status_var, font=("Segoe UI", 8, "italic"),
                 bg="#D6E8F7", fg="#444444").pack(side="right", padx=12)

    def _build_notebook(self):
        self._notebook = ttk.Notebook(self.window)
        self._notebook.grid(row=2, column=0, sticky="nsew", padx=8, pady=(4, 0))
        self.window.grid_rowconfigure(2, weight=1)

        # Tab 1 – Editor
        self._tab_editor = tk.Frame(self._notebook, bg=self._BG)
        self._notebook.add(self._tab_editor, text="  📝 File Editor  ")
        self._build_editor_tab()

        # Tab 2 – Dependency Map
        self._tab_deps = tk.Frame(self._notebook, bg=self._BG)
        self._notebook.add(self._tab_deps, text="  🔗 Dependency Map  ")
        self._build_deps_tab()

        # Tab 3 – Impact Analysis
        self._tab_impact = tk.Frame(self._notebook, bg=self._BG)
        self._notebook.add(self._tab_impact, text="  📡 Impact Analysis  ")
        self._build_impact_tab()

        # Tab 4 – Validation
        self._tab_validation = tk.Frame(self._notebook, bg=self._BG)
        self._notebook.add(self._tab_validation, text="  ✅ Validation  ")
        self._build_validation_tab()

        # Tab 5 – AI Suggestions
        self._tab_ai = tk.Frame(self._notebook, bg=self._BG)
        self._notebook.add(self._tab_ai, text="  🤖 AI Suggestions  ")
        self._build_ai_tab()

    def _build_status_bar(self):
        bar = tk.Frame(self.window, bg="#D0D7DE", height=22)
        bar.grid(row=3, column=0, sticky="ew")
        bar.grid_propagate(False)

        self._status_var = tk.StringVar(value="Ready. Select a workspace and file to begin.")
        tk.Label(bar, textvariable=self._status_var, font=("Segoe UI", 8),
                 bg="#D0D7DE", fg="#24292e", anchor="w").pack(side="left", padx=8)

    # ------------------------------------------------------------------
    # Tab 1 – File Editor
    # ------------------------------------------------------------------

    def _build_editor_tab(self):
        f = self._tab_editor
        f.grid_rowconfigure(1, weight=1)
        f.grid_columnconfigure(0, weight=1)
        f.grid_columnconfigure(1, weight=1)

        # Toolbar
        toolbar = tk.Frame(f, bg=self._BG)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(6, 4), padx=8)

        tk.Button(toolbar, text="💾 Save Changes", bg=self._ACCENT, fg="white",
                  font=("Segoe UI", 9, "bold"), padx=12,
                  command=self._save_file).pack(side="left", padx=4)

        tk.Button(toolbar, text="↩ Revert", bg="#546E7A", fg="white",
                  font=("Segoe UI", 9), padx=10,
                  command=self._revert_file).pack(side="left", padx=4)

        tk.Button(toolbar, text="🔍 Analyse Changes", bg="#1565C0", fg="white",
                  font=("Segoe UI", 9, "bold"), padx=12,
                  command=self._run_full_analysis).pack(side="left", padx=8)

        self._changed_lbl = tk.Label(toolbar, text="", font=("Segoe UI", 9, "italic"),
                                      bg=self._BG, fg=self._WARN)
        self._changed_lbl.pack(side="left", padx=6)

        # Original pane (left)
        orig_frame = tk.LabelFrame(f, text="  Original (read-only)  ",
                                    font=("Segoe UI", 9, "bold"), bg=self._BG, fg=self._HDR)
        orig_frame.grid(row=1, column=0, sticky="nsew", padx=(8, 4), pady=4)
        orig_frame.grid_rowconfigure(0, weight=1)
        orig_frame.grid_columnconfigure(0, weight=1)

        self._orig_editor = scrolledtext.ScrolledText(
            orig_frame, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4",
            wrap="none", state="disabled", insertbackground="white"
        )
        self._orig_editor.grid(row=0, column=0, sticky="nsew")

        # Modified pane (right)
        mod_frame = tk.LabelFrame(f, text="  Modified (editable)  ",
                                   font=("Segoe UI", 9, "bold"), bg=self._BG, fg=self._ACCENT)
        mod_frame.grid(row=1, column=1, sticky="nsew", padx=(4, 8), pady=4)
        mod_frame.grid_rowconfigure(0, weight=1)
        mod_frame.grid_columnconfigure(0, weight=1)

        self._mod_editor = scrolledtext.ScrolledText(
            mod_frame, font=("Consolas", 10), bg="#1e2d1e", fg="#d4f0d4",
            wrap="none", insertbackground="lime"
        )
        self._mod_editor.grid(row=0, column=0, sticky="nsew")
        self._mod_editor.bind("<<Modified>>", self._on_editor_change)

        # Diff summary row
        diff_row = tk.Frame(f, bg=self._BG)
        diff_row.grid(row=2, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 4))

        self._diff_lbl = tk.Label(diff_row, text="No file loaded.",
                                   font=("Segoe UI", 9), bg=self._BG, fg="#555555")
        self._diff_lbl.pack(side="left", padx=4)

    # ------------------------------------------------------------------
    # Tab 2 – Dependency Map
    # ------------------------------------------------------------------

    def _build_deps_tab(self):
        f = self._tab_deps
        f.grid_rowconfigure(1, weight=1)
        f.grid_columnconfigure(0, weight=1)
        f.grid_columnconfigure(1, weight=1)

        toolbar = tk.Frame(f, bg=self._BG)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(6, 4), padx=8)

        tk.Button(toolbar, text="🔄 Refresh", bg=self._INFO, fg="white",
                  font=("Segoe UI", 9), padx=10,
                  command=self._refresh_deps).pack(side="left", padx=4)

        # Left – files this file depends on (includes)
        left = tk.LabelFrame(f, text="  📥 This file DEPENDS ON (includes)  ",
                              font=("Segoe UI", 9, "bold"), bg=self._BG, fg=self._HDR)
        left.grid(row=1, column=0, sticky="nsew", padx=(8, 4), pady=4)
        left.grid_rowconfigure(0, weight=1)
        left.grid_columnconfigure(0, weight=1)

        self._deps_out_tree = self._make_tree(left, ("File", "Type", "Depth"))

        # Right – files that depend ON this file
        right = tk.LabelFrame(f, text="  📤 Files that DEPEND ON this file (impacted)  ",
                               font=("Segoe UI", 9, "bold"), bg=self._BG, fg=self._WARN)
        right.grid(row=1, column=1, sticky="nsew", padx=(4, 8), pady=4)
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)

        self._deps_in_tree = self._make_tree(right, ("File", "Type", "Depth"))

        # Summary row
        self._dep_summary_lbl = tk.Label(f, text="", font=("Segoe UI", 9, "italic"),
                                          bg=self._BG, fg="#555")
        self._dep_summary_lbl.grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 4))

    # ------------------------------------------------------------------
    # Tab 3 – Impact Analysis
    # ------------------------------------------------------------------

    def _build_impact_tab(self):
        f = self._tab_impact
        f.grid_rowconfigure(1, weight=1)
        f.grid_columnconfigure(0, weight=1)
        f.grid_columnconfigure(1, weight=1)

        toolbar = tk.Frame(f, bg=self._BG)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(6, 4), padx=8)

        tk.Button(toolbar, text="📡 Run Impact Analysis", bg=self._WARN, fg="white",
                  font=("Segoe UI", 9, "bold"), padx=12,
                  command=self._run_impact_analysis).pack(side="left", padx=4)

        # APIs panel
        apis_frame = tk.LabelFrame(f, text="  🔌 APIs & Interfaces  ",
                                    font=("Segoe UI", 9, "bold"), bg=self._BG, fg=self._HDR)
        apis_frame.grid(row=1, column=0, sticky="nsew", padx=(8, 4), pady=4)
        apis_frame.grid_rowconfigure(0, weight=1)
        apis_frame.grid_columnconfigure(0, weight=1)

        self._api_tree = self._make_tree(apis_frame, ("Name", "Kind", "Line"))

        # Impacted files panel
        impact_frame = tk.LabelFrame(f, text="  ⚡ Files Potentially Impacted  ",
                                      font=("Segoe UI", 9, "bold"), bg=self._BG, fg=self._ERR)
        impact_frame.grid(row=1, column=1, sticky="nsew", padx=(4, 8), pady=4)
        impact_frame.grid_rowconfigure(0, weight=1)
        impact_frame.grid_columnconfigure(0, weight=1)

        self._impact_tree = self._make_tree(impact_frame, ("File", "Impact Type", "Distance"))

        # Call hierarchy panel (full width)
        call_frame = tk.LabelFrame(f, text="  📞 Call Hierarchy / Usage References  ",
                                    font=("Segoe UI", 9, "bold"), bg=self._BG, fg="#5C3317")
        call_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=8, pady=4)

        self._call_text = scrolledtext.ScrolledText(
            call_frame, font=("Consolas", 9), bg="#FAFAFA", fg="#24292e",
            height=7, wrap="none", state="disabled"
        )
        self._call_text.pack(fill="both", expand=True, padx=4, pady=4)

    # ------------------------------------------------------------------
    # Tab 4 – Validation
    # ------------------------------------------------------------------

    def _build_validation_tab(self):
        f = self._tab_validation
        f.grid_rowconfigure(1, weight=1)
        f.grid_columnconfigure(0, weight=1)

        toolbar = tk.Frame(f, bg=self._BG)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(6, 4), padx=8)

        tk.Button(toolbar, text="✅ Run Validation", bg=self._ACCENT, fg="white",
                  font=("Segoe UI", 9, "bold"), padx=12,
                  command=self._run_validation).pack(side="left", padx=4)

        self._validation_count_lbl = tk.Label(toolbar, text="",
                                               font=("Segoe UI", 9, "italic"),
                                               bg=self._BG, fg=self._HDR)
        self._validation_count_lbl.pack(side="left", padx=6)

        # Issues treeview
        issue_frame = tk.LabelFrame(f, text="  Validation Issues  ",
                                     font=("Segoe UI", 9, "bold"), bg=self._BG, fg=self._HDR)
        issue_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)
        issue_frame.grid_rowconfigure(0, weight=1)
        issue_frame.grid_columnconfigure(0, weight=1)

        self._issue_tree = self._make_tree(issue_frame, ("Line", "Severity", "Message"),
                                            widths=(60, 100, 600))
        self._issue_tree.tag_configure("error",   background="#FFCDD2", foreground="#B71C1C")
        self._issue_tree.tag_configure("warning", background="#FFF9C4", foreground="#827717")
        self._issue_tree.tag_configure("info",    background="#E3F2FD", foreground="#0D47A1")
        self._issue_tree.bind("<<TreeviewSelect>>", self._on_issue_select)

        # Details pane
        detail_frame = tk.LabelFrame(f, text="  Recommendations  ",
                                      font=("Segoe UI", 9, "bold"), bg=self._BG, fg=self._HDR)
        detail_frame.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 4))

        self._validation_detail = scrolledtext.ScrolledText(
            detail_frame, font=("Segoe UI", 9), bg="#F9F9F9", fg="#24292e",
            height=6, wrap="word", state="disabled"
        )
        self._validation_detail.pack(fill="both", expand=True, padx=4, pady=4)

    # ------------------------------------------------------------------
    # Tab 5 – AI Suggestions
    # ------------------------------------------------------------------

    def _build_ai_tab(self):
        f = self._tab_ai
        f.grid_rowconfigure(1, weight=1)
        f.grid_columnconfigure(0, weight=1)

        toolbar = tk.Frame(f, bg=self._BG)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(6, 4), padx=8)

        tk.Button(toolbar, text="🤖 Generate AI Suggestions", bg="#6A0DAD", fg="white",
                  font=("Segoe UI", 9, "bold"), padx=12,
                  command=self._run_ai_suggestions).pack(side="left", padx=4)

        tk.Button(toolbar, text="📋 Copy Suggestions", bg="#546E7A", fg="white",
                  font=("Segoe UI", 9), padx=10,
                  command=self._copy_suggestions).pack(side="left", padx=4)

        # AI output area
        ai_frame = tk.LabelFrame(f, text="  AI-Based Change Suggestions  ",
                                  font=("Segoe UI", 9, "bold"), bg=self._BG, fg="#6A0DAD")
        ai_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)
        ai_frame.grid_rowconfigure(0, weight=1)
        ai_frame.grid_columnconfigure(0, weight=1)

        self._ai_text = scrolledtext.ScrolledText(
            ai_frame, font=("Segoe UI", 10), bg="#FAFAFA", fg="#24292e",
            wrap="word", state="disabled"
        )
        self._ai_text.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

        # Tag styles
        self._ai_text.tag_config("heading",  font=("Segoe UI", 11, "bold"), foreground="#003366")
        self._ai_text.tag_config("subhead",  font=("Segoe UI", 10, "bold"), foreground="#5C3317")
        self._ai_text.tag_config("code",     font=("Consolas", 9),          background="#F0F0F0")
        self._ai_text.tag_config("warning",  foreground="#E65100",          font=("Segoe UI", 9, "italic"))
        self._ai_text.tag_config("ok",       foreground="#1B5E20",          font=("Segoe UI", 9))

        self._set_ai_placeholder()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_tree(self, parent, columns: Tuple[str, ...],
                   widths: Optional[Tuple[int, ...]] = None) -> ttk.Treeview:
        frame = tk.Frame(parent, bg="white")
        frame.pack(fill="both", expand=True)
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        vsb = tk.Scrollbar(frame, orient="vertical")
        hsb = tk.Scrollbar(frame, orient="horizontal")

        tree = ttk.Treeview(frame, columns=columns, show="headings",
                             yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.config(command=tree.yview)
        hsb.config(command=tree.xview)

        for i, col in enumerate(columns):
            w = widths[i] if widths and i < len(widths) else 200
            tree.heading(col, text=col, anchor="w")
            tree.column(col, width=w, anchor="w")

        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        return tree

    def _set_status(self, msg: str):
        self._status_var.set(msg)
        self.window.update_idletasks()

    def _set_ai_placeholder(self):
        self._ai_text.config(state="normal")
        self._ai_text.delete("1.0", "end")
        self._ai_text.insert("end", "AI Suggestions\n", "heading")
        self._ai_text.insert("end",
            "Load a file and run 'Analyse Changes' to see AI-powered recommendations.\n\n"
            "The AI will:\n"
            "  • Identify all files that may need corresponding updates\n"
            "  • Suggest specific code changes in dependent files\n"
            "  • Highlight integration risks introduced by the change\n"
            "  • Provide a change impact summary with priority ordering\n"
        )
        self._ai_text.config(state="disabled")

    # ------------------------------------------------------------------
    # Workspace / file selection
    # ------------------------------------------------------------------

    def _browse_workspace(self):
        path = filedialog.askdirectory(title="Select Workspace Folder")
        if not path:
            return
        self._workspace_path = path
        self._ws_var.set(path)
        self._dep_status_var.set("⏳ Building dependency graph…")
        self._schedule_graph_build(path)

    def _select_file(self):
        ws = self._workspace_path
        init_dir = ws if ws and os.path.isdir(ws) else os.getcwd()
        path = filedialog.askopenfilename(
            initialdir=init_dir,
            title="Select File to Analyse",
            filetypes=[
                ("C/C++ Source & Headers", "*.c *.h *.cpp *.cc *.cxx *.hpp *.hxx"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        self._load_file(path)

    def _load_file(self, path: str):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except Exception as exc:
            messagebox.showerror("Load Error", f"Cannot read file:\n{exc}", parent=self.window)
            return

        self._file_path = path
        self._original_content = content
        self._file_var.set(path)

        # Populate both editors
        for editor, state in [(self._orig_editor, "disabled"), (self._mod_editor, "normal")]:
            editor.config(state="normal")
            editor.delete("1.0", "end")
            editor.insert("1.0", content)
            editor.config(state=state)

        self._mod_editor.edit_modified(False)
        self._changed_lbl.config(text="")
        self._diff_lbl.config(text=f"Loaded: {os.path.basename(path)}  ({len(content.splitlines())} lines)")
        self._set_status(f"File loaded: {path}")

        # Auto-extract APIs
        self._api_info = _APIExtractor.extract(content)

        # Auto-refresh deps if graph is ready
        if self._dep_graph:
            self._refresh_deps()

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def _save_file(self):
        if not self._file_path:
            messagebox.showinfo("No file", "No file loaded.", parent=self.window)
            return
        new_content = self._mod_editor.get("1.0", "end-1c")
        if new_content == self._original_content:
            messagebox.showinfo("No changes", "The file has not been modified.", parent=self.window)
            return
        confirm = messagebox.askyesno(
            "Confirm Save",
            f"Overwrite the original file?\n\n{self._file_path}",
            parent=self.window
        )
        if not confirm:
            return
        try:
            with open(self._file_path, "w", encoding="utf-8") as fh:
                fh.write(new_content)
            self._original_content = new_content
            self._orig_editor.config(state="normal")
            self._orig_editor.delete("1.0", "end")
            self._orig_editor.insert("1.0", new_content)
            self._orig_editor.config(state="disabled")
            self._mod_editor.edit_modified(False)
            self._changed_lbl.config(text="")
            self._set_status("File saved successfully.")
        except Exception as exc:
            messagebox.showerror("Save Error", str(exc), parent=self.window)

    def _revert_file(self):
        if not self._file_path:
            return
        self._mod_editor.config(state="normal")
        self._mod_editor.delete("1.0", "end")
        self._mod_editor.insert("1.0", self._original_content)
        self._mod_editor.edit_modified(False)
        self._changed_lbl.config(text="")
        self._set_status("Reverted to original.")

    def _on_editor_change(self, _event=None):
        if self._mod_editor.edit_modified():
            self._changed_lbl.config(text="● Unsaved changes", fg=self._WARN)

    # ------------------------------------------------------------------
    # Dependency graph
    # ------------------------------------------------------------------

    def _schedule_graph_build(self, workspace: str):
        if self._graph_loading or not _DEP_AVAILABLE:
            if not _DEP_AVAILABLE:
                self._dep_status_var.set("⚫ Dependency graph unavailable")
            return
        self._graph_loading = True
        self._dep_status_var.set("⏳ Building dependency graph…")
        t = threading.Thread(target=self._build_graph, args=(workspace,), daemon=True)
        t.start()

    def _build_graph(self, workspace: str):
        try:
            builder = DependencyGraphBuilder()
            graph = builder.build(workspace)
            self._dep_graph = graph
            try:
                self._impact_analyzer = ImpactAnalyzer(graph)
            except Exception:
                self._impact_analyzer = None
            n = len(graph.nodes) if graph else 0
            self.window.after(0, lambda: self._dep_status_var.set(
                f"✅ Graph: {n} files indexed"
            ))
            if self._file_path:
                self.window.after(0, self._refresh_deps)
        except Exception as exc:
            self.window.after(0, lambda: self._dep_status_var.set(
                f"⚠ Graph error: {exc}"
            ))
        finally:
            self._graph_loading = False

    def _refresh_deps(self):
        if not self._file_path:
            return
        self._clear_tree(self._deps_out_tree)
        self._clear_tree(self._deps_in_tree)

        if not self._dep_graph:
            self._dep_summary_lbl.config(
                text="Dependency graph not available. Select a workspace first.")
            return

        ws = self._workspace_path or ""
        try:
            rel = os.path.relpath(self._file_path, ws).replace("\\", "/") if ws else \
                os.path.basename(self._file_path)
        except ValueError:
            rel = os.path.basename(self._file_path)

        # Dependencies (what this file includes)
        dep_set = self._dep_graph.get_dependencies(rel, recursive=True)
        direct_deps = self._dep_graph.get_dependencies(rel, recursive=False)

        for dep in sorted(dep_set):
            depth = "direct" if dep in direct_deps else "transitive"
            tag = "header" if dep.endswith(('.h', '.hpp', '.hxx')) else "source"
            self._deps_out_tree.insert("", "end", values=(dep, tag, depth))

        # Dependents (what depends ON this file)
        dep_in_set = self._dep_graph.get_dependents(rel, recursive=True)
        direct_in   = self._dep_graph.get_dependents(rel, recursive=False)

        for dep in sorted(dep_in_set):
            depth = "direct" if dep in direct_in else "transitive"
            tag = "header" if dep.endswith(('.h', '.hpp', '.hxx')) else "source"
            self._deps_in_tree.insert("", "end", values=(dep, tag, depth))

        self._dep_summary_lbl.config(
            text=(
                f"Depends on {len(dep_set)} files ({len(direct_deps)} direct)  |  "
                f"Depended on by {len(dep_in_set)} files ({len(direct_in)} direct)"
            )
        )

    # ------------------------------------------------------------------
    # Impact analysis
    # ------------------------------------------------------------------

    def _run_impact_analysis(self):
        if not self._file_path:
            messagebox.showinfo("No file", "Please load a file first.", parent=self.window)
            return
        self._set_status("Running impact analysis…")
        threading.Thread(target=self._do_impact_analysis, daemon=True).start()

    def _do_impact_analysis(self):
        self.window.after(0, self._clear_impact_ui)
        content = self._mod_editor.get("1.0", "end-1c")
        api = _APIExtractor.extract(content)
        self._api_info = api

        # --- API tree ---
        rows = []
        for fn in api["defined"]:
            rows.append((fn["name"], f"defines (returns {fn['return_type']})", str(fn["line"])))
        for fn in api["declared"]:
            rows.append((fn["name"], f"declares (returns {fn['return_type']})", str(fn["line"])))
        for inc in api["includes"]:
            rows.append((inc, "includes", ""))
        for call in api["calls"][:60]:
            rows.append((call, "calls", ""))

        self.window.after(0, lambda: self._populate_api_tree(rows))

        # --- Impact via dep graph ---
        impact_rows = []
        call_lines = []
        if self._dep_graph:
            ws = self._workspace_path or ""
            try:
                rel = os.path.relpath(self._file_path, ws).replace("\\", "/") if ws else \
                    os.path.basename(self._file_path)
            except ValueError:
                rel = os.path.basename(self._file_path)

            dependents_direct = self._dep_graph.get_dependents(rel, recursive=False)
            dependents_all    = self._dep_graph.get_dependents(rel, recursive=True)

            for dep in sorted(dependents_all):
                dist = "1 – direct" if dep in dependents_direct else "2+ – transitive"
                impact_rows.append((dep, "include dependency", dist))

            # Call hierarchy text
            defined_names = {f["name"] for f in api["defined"]}
            call_lines.append("=== Exported functions (defined in this file) ===")
            for fn in api["defined"]:
                call_lines.append(f"  ► {fn['return_type']} {fn['name']}()  [line {fn['line']}]")
            call_lines.append("")
            call_lines.append("=== Functions called by this file (external dependencies) ===")
            for c in api["calls"][:40]:
                call_lines.append(f"  → {c}()")
            call_lines.append("")
            call_lines.append(f"=== Impact radius: {len(dependents_all)} file(s) affected ===")
            for dep in sorted(dependents_all)[:20]:
                call_lines.append(f"  ⚡ {dep}")
            if len(dependents_all) > 20:
                call_lines.append(f"  … and {len(dependents_all) - 20} more")
        else:
            call_lines.append("Dependency graph not built — impact radius unavailable.")
            call_lines.append("Select a workspace folder to build the graph.")

        self.window.after(0, lambda: self._populate_impact_ui(impact_rows, call_lines))
        self.window.after(0, lambda: self._set_status("Impact analysis complete."))

    def _clear_impact_ui(self):
        self._clear_tree(self._api_tree)
        self._clear_tree(self._impact_tree)
        self._call_text.config(state="normal")
        self._call_text.delete("1.0", "end")
        self._call_text.config(state="disabled")

    def _populate_api_tree(self, rows):
        for row in rows:
            self._api_tree.insert("", "end", values=row)

    def _populate_impact_ui(self, impact_rows, call_lines):
        for row in impact_rows:
            self._impact_tree.insert("", "end", values=row)

        self._call_text.config(state="normal")
        self._call_text.delete("1.0", "end")
        self._call_text.insert("end", "\n".join(call_lines))
        self._call_text.config(state="disabled")

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _run_validation(self):
        if not self._file_path:
            messagebox.showinfo("No file", "Please load a file first.", parent=self.window)
            return
        content = self._mod_editor.get("1.0", "end-1c")
        fname = os.path.basename(self._file_path)
        self._set_status("Running validation…")

        self._clear_tree(self._issue_tree)
        self._validation_detail.config(state="normal")
        self._validation_detail.delete("1.0", "end")
        self._validation_detail.config(state="disabled")

        issues = _CValidator.validate(content, fname)

        # Additional: compare includes with original
        orig_api = _APIExtractor.extract(self._original_content)
        new_api  = _APIExtractor.extract(content)

        removed_includes = set(orig_api["includes"]) - set(new_api["includes"])
        added_includes   = set(new_api["includes"]) - set(orig_api["includes"])
        removed_funcs    = {f["name"] for f in orig_api["defined"]} - \
                           {f["name"] for f in new_api["defined"]}
        added_funcs      = {f["name"] for f in new_api["defined"]} - \
                           {f["name"] for f in orig_api["defined"]}

        for inc in removed_includes:
            issues.append({"line": "–", "severity": "warning",
                            "message": f"Removed #include: {inc}  — dependent code may break."})
        for inc in added_includes:
            issues.append({"line": "–", "severity": "info",
                            "message": f"New #include added: {inc}"})
        for fn in removed_funcs:
            issues.append({"line": "–", "severity": "error",
                            "message": f"Function removed: {fn}()  — callers will break!"})
        for fn in added_funcs:
            issues.append({"line": "–", "severity": "info",
                            "message": f"New function added: {fn}()"})

        # Populate
        for iss in issues:
            tag = iss["severity"]
            self._issue_tree.insert("", "end",
                                     values=(str(iss["line"]), iss["severity"].upper(),
                                             iss["message"]),
                                     tags=(tag,))

        errors   = sum(1 for i in issues if i["severity"] == "error")
        warnings = sum(1 for i in issues if i["severity"] == "warning")
        infos    = sum(1 for i in issues if i["severity"] == "info")

        self._validation_count_lbl.config(
            text=f"Errors: {errors}  |  Warnings: {warnings}  |  Info: {infos}",
            fg=self._ERR if errors else (self._WARN if warnings else self._ACCENT)
        )

        recs = self._build_recommendations(issues, removed_funcs, removed_includes)
        self._validation_detail.config(state="normal")
        self._validation_detail.insert("end", recs)
        self._validation_detail.config(state="disabled")

        self._set_status(f"Validation complete — {errors} errors, {warnings} warnings.")

    def _build_recommendations(self, issues, removed_funcs, removed_includes) -> str:
        lines = []
        if not issues:
            return "✅ No issues found. The modified file looks clean."
        if removed_funcs:
            lines.append(f"⚠ Removed functions: {', '.join(removed_funcs)}")
            lines.append("  → Search all dependent files for calls to these functions and update or remove them.")
        if removed_includes:
            lines.append(f"⚠ Removed includes: {', '.join(removed_includes)}")
            lines.append("  → Ensure no symbols from these headers are used elsewhere in dependent files.")
        errors = [i for i in issues if i["severity"] == "error"]
        if errors:
            lines.append(f"\n{len(errors)} syntax/structural error(s) detected:")
            for e in errors[:5]:
                lines.append(f"  Line {e['line']}: {e['message']}")
        lines.append("\nRecommendation: Run 'Impact Analysis' to see which files are affected.")
        return "\n".join(lines)

    def _on_issue_select(self, _event=None):
        sel = self._issue_tree.selection()
        if not sel:
            return
        vals = self._issue_tree.item(sel[0], "values")
        if not vals:
            return
        line_str = vals[0]
        if line_str.isdigit():
            lno = int(line_str)
            self._mod_editor.see(f"{lno}.0")
            self._mod_editor.tag_remove("sel", "1.0", "end")
            self._mod_editor.tag_add("sel", f"{lno}.0", f"{lno}.end")

    # ------------------------------------------------------------------
    # AI suggestions
    # ------------------------------------------------------------------

    def _run_ai_suggestions(self):
        if not self._file_path:
            messagebox.showinfo("No file", "Please load and modify a file first.",
                                parent=self.window)
            return
        self._set_status("Generating AI suggestions…")
        self._ai_text.config(state="normal")
        self._ai_text.delete("1.0", "end")
        self._ai_text.insert("end", "⏳ Generating AI-based suggestions…\n\n")
        self._ai_text.config(state="disabled")
        threading.Thread(target=self._do_ai_suggestions, daemon=True).start()

    def _do_ai_suggestions(self):
        content_orig = self._original_content
        content_new  = self._mod_editor.get("1.0", "end-1c")
        fname = os.path.basename(self._file_path)

        # Build diff summary
        diff_lines = list(difflib.unified_diff(
            content_orig.splitlines(), content_new.splitlines(),
            fromfile=f"original/{fname}", tofile=f"modified/{fname}",
            lineterm=""
        ))[:120]
        diff_summary = "\n".join(diff_lines) or "(no changes detected)"

        # API info
        api = self._api_info or _APIExtractor.extract(content_new)
        defined  = [f["name"] for f in api["defined"]]
        declared = [f["name"] for f in api["declared"]]
        calls    = api["calls"][:30]

        # Dep info
        dep_count = 0
        impacted_files: List[str] = []
        if self._dep_graph:
            ws = self._workspace_path or ""
            try:
                rel = os.path.relpath(self._file_path, ws).replace("\\", "/") if ws else fname
            except ValueError:
                rel = fname
            impacted = self._dep_graph.get_dependents(rel, recursive=True)
            dep_count = len(impacted)
            impacted_files = sorted(impacted)[:20]

        # Try to call AOAI
        ai_result = self._call_aoai(fname, diff_summary, defined, calls, impacted_files)

        if ai_result:
            self.window.after(0, lambda r=ai_result: self._display_ai_result(r))
        else:
            # Fallback: heuristic suggestions
            result = self._heuristic_suggestions(
                fname, diff_summary, defined, declared, calls,
                dep_count, impacted_files
            )
            self.window.after(0, lambda r=result: self._display_ai_result(r))

        self.window.after(0, lambda: self._set_status("AI suggestions ready."))

    def _call_aoai(self, fname, diff_summary, defined, calls, impacted_files) -> Optional[str]:
        """Try Bosch AOAI Farm; return text or None on failure."""
        try:
            aoai_key = (os.environ.get("GENAIPLATFORM_FARM_SUBSCRIPTION_KEY", "") or
                        os.environ.get("AOAI_FARM_KEY", ""))
            if not aoai_key:
                return None

            from src.chatbot.chatbot import ChatConfig, ChatEngine
            endpoint_base = os.environ.get("AOAI_FARM_ENDPOINT",
                                            "https://aoai-farm.bosch-temp.com/api").rstrip("/")
            deployment   = os.environ.get("AOAI_CHAT_DEPLOYMENT",
                                           "gpt-5-nano-2025-08-07")
            api_version  = os.environ.get("AOAI_CHAT_API_VERSION", "2025-04-01-preview")
            endpoint = (f"{endpoint_base}/openai/deployments/{deployment}"
                        f"/chat/completions?api-version={api_version}")

            from src.config import settings
            cfg = ChatConfig(
                api_key=aoai_key,
                endpoint=endpoint,
                temperature=0.2,
                max_tokens=2000,
                timeout_sec=90,
                proxy_url=getattr(settings, "PROXY_URL", ""),
                proxy_domain=getattr(settings, "PROXY_DOMAIN", "BOSCH"),
                proxy_user=getattr(settings, "PROXY_USER", ""),
                proxy_pass=getattr(settings, "PROXY_PASS", ""),
            )
            engine = ChatEngine(cfg)

            impacted_str = "\n".join(f"  - {f}" for f in impacted_files) or "  (none detected)"
            system_msg = (
                "You are an expert embedded-software C/C++ code reviewer. "
                "Analyse the provided file diff and dependency context, then give "
                "concise, actionable recommendations for all dependent files that "
                "may need updates. Highlight integration risks."
            )
            user_msg = (
                f"File changed: {fname}\n\n"
                f"=== Unified diff (first 120 lines) ===\n{diff_summary}\n\n"
                f"=== Exported functions ===\n" + ", ".join(defined or ["(none)"]) + "\n\n"
                f"=== External calls made ===\n" + ", ".join(calls or ["(none)"]) + "\n\n"
                f"=== Files that depend on this file (impacted) ===\n{impacted_str}\n\n"
                "Please provide:\n"
                "1. Change impact summary (what changed and why it matters)\n"
                "2. Files that likely need updates, and what changes are needed in each\n"
                "3. Potential integration risks\n"
                "4. Recommended testing steps\n"
            )
            messages = [
                {"role": "system", "content": system_msg},
                {"role": "user",   "content": user_msg},
            ]
            return engine.complete(messages)
        except Exception as exc:
            print(f"[WARN] AOAI call failed in ManualFileChangeAnalyzer: {exc}")
            return None

    def _heuristic_suggestions(self, fname, diff_summary, defined, declared,
                                calls, dep_count, impacted_files) -> str:
        """Offline heuristic when AI is unavailable."""
        lines = [
            f"=== Change Impact Summary for {fname} ===\n",
            "AI engine not available — showing heuristic analysis.\n",
        ]

        if defined:
            lines.append(f"\n📌 Exported functions ({len(defined)} defined):")
            for fn in defined[:10]:
                lines.append(f"   • {fn}()")
            if len(defined) > 10:
                lines.append(f"   … and {len(defined)-10} more")

        if declared:
            lines.append(f"\n📋 Declared (extern) interfaces ({len(declared)}):")
            for fn in declared[:10]:
                lines.append(f"   • {fn}()")

        if calls:
            lines.append(f"\n🔗 External calls made ({len(calls)}):")
            for fn in calls[:10]:
                lines.append(f"   → {fn}()")

        lines.append(f"\n⚡ Impact Radius: {dep_count} file(s) will be recompiled/affected.")

        if impacted_files:
            lines.append("\nFiles that depend on this file and may need review:")
            for f in impacted_files[:15]:
                lines.append(f"   • {f}")
            if dep_count > 15:
                lines.append(f"   … and {dep_count - 15} more")

        lines.append("\n\n📋 Recommended Actions:")
        lines.append("  1. Run full build to check for compilation errors.")
        lines.append("  2. Review each impacted file for call-site compatibility.")
        if defined:
            lines.append(f"  3. Check all callers of: {', '.join(defined[:5])}()")
        lines.append("  4. Run unit tests for impacted modules.")
        lines.append("  5. Update interface documentation if API signature changed.")

        return "\n".join(lines)

    def _display_ai_result(self, text: str):
        self._ai_text.config(state="normal")
        self._ai_text.delete("1.0", "end")

        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("===") and stripped.endswith("==="):
                self._ai_text.insert("end", line + "\n", "heading")
            elif stripped.startswith(("##", "**")) or (stripped and stripped[0].isdigit()
                                                        and len(stripped) > 2
                                                        and stripped[1] in ".):"):
                self._ai_text.insert("end", line + "\n", "subhead")
            elif stripped.startswith(("⚠", "⚡", "❌")):
                self._ai_text.insert("end", line + "\n", "warning")
            elif stripped.startswith(("✅", "✓", "☑")):
                self._ai_text.insert("end", line + "\n", "ok")
            elif stripped.startswith(("  ", "\t")) and stripped:
                self._ai_text.insert("end", line + "\n", "code")
            else:
                self._ai_text.insert("end", line + "\n")

        self._ai_text.config(state="disabled")

    def _copy_suggestions(self):
        text = self._ai_text.get("1.0", "end-1c")
        if text.strip():
            self.window.clipboard_clear()
            self.window.clipboard_append(text)
            self._set_status("Suggestions copied to clipboard.")

    # ------------------------------------------------------------------
    # Run all analysis
    # ------------------------------------------------------------------

    def _run_full_analysis(self):
        if not self._file_path:
            messagebox.showinfo("No file", "Please load a file first.", parent=self.window)
            return
        self._set_status("Running full analysis…")
        self._refresh_deps()
        self._run_impact_analysis()
        self._run_validation()
        self._notebook.select(1)   # Switch to Dependency Map

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _clear_tree(self, tree: ttk.Treeview):
        for item in tree.get_children():
            tree.delete(item)
