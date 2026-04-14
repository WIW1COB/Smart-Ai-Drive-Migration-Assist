"""
C/H Dependency Analyzer
=======================
Scans a C/C++ workspace, builds an include + function-call dependency graph,
and reports the blast radius every time a file changes.

Usage
-----
Demo mode (simulates 2 file changes and restores them):
    python dependency_analyzer.py --demo  <workspace>  [--scope  <sub-folder>]

Live file-watch mode (polls for saves from your editor):
    python dependency_analyzer.py  <workspace>  [--scope  <sub-folder>]

Optional flags:
    --model    <name>   Label shown in the AI section header
    --key      <key>    Azure OpenAI subscription key
                        (can also be set via GENAIPLATFORM_FARM_SUBSCRIPTION_KEY)
    --no-ai             Skip the AI impact analysis section
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from collections import defaultdict, deque
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Pretty-print helpers
# ---------------------------------------------------------------------------
W = 72  # total line width


def _banner(text: str = "") -> str:
    return "=" * W


def _section(text: str) -> str:
    return "-" * W


def _box_title(text: str) -> str:
    padding = W - 2 - len(text)
    left = padding // 2
    right = padding - left
    return "|" + " " * left + text + " " * right + "|"


def _hdr(*lines: str) -> None:
    print(_banner())
    for ln in lines:
        print(ln)
    print(_banner())


def _sub() -> None:
    print(_section(""))


# ---------------------------------------------------------------------------
# Index: build include graph + function-definition / call maps
# ---------------------------------------------------------------------------

# Regex: #include "file.h"  or  #include <file.h>
_RE_INCLUDE = re.compile(
    r'^\s*#\s*include\s+[<"]([^>"]+)[>"]',
    re.MULTILINE,
)

# Regex: C/C++ function *definition* (very liberal – covers most embedded code)
#   [storage] [qualifiers] return_type  name  (params)  {
_RE_FUNC_DEF = re.compile(
    r"""
    (?:^|\n)                                  # start of line
    [ \t]*                                    # optional indent
    (?:(?:static|inline|extern|__attribute__\s*\(\([^)]*\)\))\s+)*  # storage/qualifier
    (?:const\s+)?                             # optional const
    [\w\s\*]+?                                # return type (greedy-light)
    \b([\w]+)\s*                              # FUNCTION NAME  ← group 1
    \(                                        # open paren
    [^;{]*?                                   # params (no ; or {)
    \)\s*                                     # close paren
    (?:const\s*)?                             # optional trailing const
    \{                                        # opening brace  → definition
    """,
    re.VERBOSE | re.MULTILINE,
)

# Regex: function *declaration* (ends with ;)  — used for headers
_RE_FUNC_DECL = re.compile(
    r"""
    (?:^|\n)
    [ \t]*
    (?:(?:static|inline|extern|__attribute__\s*\(\([^)]*\)\))\s+)*
    (?:const\s+)?
    [\w\s\*]+?
    \b([\w]+)\s*
    \(
    [^;{]*?
    \)\s*
    (?:const\s*)?
    ;                                         # ends with semicolon → declaration
    """,
    re.VERBOSE | re.MULTILINE,
)

# C/C++ extensions to scan
_C_EXTS = {".c", ".h", ".cpp", ".hpp", ".cc", ".cxx", ".hxx"}

# Noise identifiers that look like functions but aren't user functions
_NOISE = frozenset({
    "if", "for", "while", "switch", "return", "sizeof", "typeof",
    "offsetof", "assert", "defined", "alignof", "alignas",
    "static_assert", "nullptr", "NULL", "TRUE", "FALSE",
    "uint8_t", "uint16_t", "uint32_t", "uint64_t",
    "int8_t",  "int16_t",  "int32_t",  "int64_t",
    "size_t",  "ptrdiff_t", "bool", "void",
})


def _strip_comments(text: str) -> str:
    """Remove C/C++ block and line comments (leaves line structure intact)."""
    # block comments  /* ... */
    text = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group().count("\n"), text, flags=re.S)
    # line comments  //
    text = re.sub(r"//[^\n]*", "", text)
    return text


def _extract_func_names(content: str, is_header: bool) -> List[str]:
    """Return list of function names defined/declared in the file."""
    clean = _strip_comments(content)
    names = set()
    for m in _RE_FUNC_DEF.finditer(clean):
        n = m.group(1)
        if n and n not in _NOISE:
            names.add(n)
    if is_header:
        for m in _RE_FUNC_DECL.finditer(clean):
            n = m.group(1)
            if n and n not in _NOISE:
                names.add(n)
    return sorted(names)


def _find_calls_in_file(content: str, func_names: Set[str]) -> List[str]:
    """Return list of func_names that appear as calls inside content."""
    if not func_names:
        return []
    clean = _strip_comments(content)
    # Build single pattern matching any of the names followed by '('
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(f) for f in sorted(func_names)) + r")\s*\(",
        re.MULTILINE,
    )
    found = {m.group(1) for m in pattern.finditer(clean)}
    return sorted(found)


# ---------------------------------------------------------------------------
# FileNode & CHIndex
# ---------------------------------------------------------------------------

class FileNode:
    """Per-file metadata stored in the index."""

    __slots__ = (
        "abs_path", "rel_path", "is_header",
        "includes_raw",          # set of raw include strings  (#include "x")
        "resolved_includes",     # set of rel_paths of files this file includes
        "included_by",           # set of rel_paths of files that include this file
        "func_names",            # list[str] – functions defined/declared here
        "mtime",                 # float – last modification time
    )

    def __init__(self, abs_path: str, rel_path: str) -> None:
        self.abs_path = abs_path
        self.rel_path = rel_path
        ext = os.path.splitext(rel_path)[1].lower()
        self.is_header = ext in {".h", ".hpp", ".hxx", ".hh"}
        self.includes_raw: Set[str] = set()
        self.resolved_includes: Set[str] = set()
        self.included_by: Set[str] = set()
        self.func_names: List[str] = []
        self.mtime: float = 0.0


class CHIndex:
    """
    Index of C/H files in a workspace folder.

    Provides:
      • include dependency graph (forward + reverse)
      • function → file  mapping
      • reachable-files (files that will recompile) with depth info
      • caller map (which files call functions from a given file)
    """

    def __init__(self, root: str, scope: Optional[str] = None) -> None:
        self.root = os.path.normpath(root)
        self.scope_path = os.path.normpath(os.path.join(root, scope)) if scope else self.root
        self.scope_label = scope or ""
        self.nodes: Dict[str, FileNode] = {}        # rel_path → FileNode
        self._fname_idx: Dict[str, List[str]] = {}  # basename → [rel_paths]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self, progress_cb=None) -> None:
        """Scan workspace and build the full index."""
        all_files = self._collect_files()
        total = len(all_files)

        self._fname_idx = defaultdict(list)
        for i, (rel, abs_p) in enumerate(all_files.items(), 1):
            node = self._parse_node(abs_p, rel)
            self.nodes[rel] = node
            self._fname_idx[os.path.basename(rel).lower()].append(rel)
            if progress_cb:
                progress_cb(i, total)

        self._resolve_all()
        self._build_reverse()

    def reindex_file(self, rel_path: str) -> None:
        """Re-parse a single file and rebuild its include edges."""
        node = self.nodes.get(rel_path)
        if not node:
            return
        # Remove old reverse edges contributed by this file
        for dep in node.resolved_includes:
            dep_node = self.nodes.get(dep)
            if dep_node:
                dep_node.included_by.discard(rel_path)

        # Re-parse
        updated = self._parse_node(node.abs_path, rel_path)
        node.includes_raw = updated.includes_raw
        node.func_names = updated.func_names
        node.mtime = updated.mtime

        # Re-resolve this file's includes
        node.resolved_includes = set()
        for inc in node.includes_raw:
            resolved = self._resolve_one(inc, os.path.dirname(rel_path))
            if resolved:
                node.resolved_includes.add(resolved)

        # Rebuild reverse edges for this file
        for dep in node.resolved_includes:
            dep_node = self.nodes.get(dep)
            if dep_node:
                dep_node.included_by.add(rel_path)

    def affected_files_with_depth(self, rel_path: str) -> List[Tuple[str, int]]:
        """
        BFS over included_by edges starting from rel_path.
        Returns list of (rel_path, depth) sorted by depth then path.
        """
        visited: Dict[str, int] = {}
        queue: deque = deque()
        node = self.nodes.get(rel_path)
        if node:
            for dep in sorted(node.included_by):
                queue.append((dep, 1))

        while queue:
            cur, depth = queue.popleft()
            if cur in visited:
                continue
            visited[cur] = depth
            cur_node = self.nodes.get(cur)
            if cur_node:
                for next_dep in sorted(cur_node.included_by):
                    if next_dep not in visited:
                        queue.append((next_dep, depth + 1))

        return sorted(visited.items(), key=lambda x: (x[1], x[0]))

    def caller_map(self, rel_path: str) -> Dict[str, List[str]]:
        """
        Find every indexed file that calls functions defined in rel_path.
        Returns dict of caller_rel_path → [func_names_called].
        """
        node = self.nodes.get(rel_path)
        if not node or not node.func_names:
            return {}
        func_set = set(node.func_names)
        result: Dict[str, List[str]] = {}

        for other_rel, other_node in self.nodes.items():
            try:
                with open(other_node.abs_path, "r", encoding="utf-8", errors="ignore") as fh:
                    content = fh.read()
            except Exception:
                continue
            calls = _find_calls_in_file(content, func_set)
            if calls:
                result[other_rel] = calls

        return result

    def total_edges(self) -> int:
        return sum(len(n.resolved_includes) for n in self.nodes.values())

    def total_functions(self) -> int:
        return sum(len(n.func_names) for n in self.nodes.values())

    def mtimes_snapshot(self) -> Dict[str, float]:
        return {r: n.mtime for r, n in self.nodes.items()}

    def refresh_mtimes(self) -> Dict[str, float]:
        """Re-stat all files, update mtime in nodes, return snapshot."""
        snap: Dict[str, float] = {}
        for rel, node in self.nodes.items():
            try:
                mtime = os.path.getmtime(node.abs_path)
            except OSError:
                mtime = node.mtime
            node.mtime = mtime
            snap[rel] = mtime
        return snap

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _collect_files(self) -> Dict[str, str]:
        files: Dict[str, str] = {}
        for root_dir, dirs, filenames in os.walk(self.scope_path):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fname in filenames:
                if os.path.splitext(fname)[1].lower() in _C_EXTS:
                    abs_p = os.path.join(root_dir, fname)
                    rel = os.path.relpath(abs_p, self.root)
                    files[rel] = abs_p
        return files

    def _parse_node(self, abs_path: str, rel_path: str) -> FileNode:
        node = FileNode(abs_path, rel_path)
        try:
            node.mtime = os.path.getmtime(abs_path)
            with open(abs_path, "r", encoding="utf-8", errors="ignore") as fh:
                content = fh.read()
        except Exception:
            return node
        for m in _RE_INCLUDE.finditer(content):
            node.includes_raw.add(m.group(1))
        node.func_names = _extract_func_names(content, node.is_header)
        return node

    def _resolve_all(self) -> None:
        for rel, node in self.nodes.items():
            file_dir = os.path.dirname(rel)
            for inc in node.includes_raw:
                resolved = self._resolve_one(inc, file_dir)
                if resolved:
                    node.resolved_includes.add(resolved)

    def _resolve_one(self, include_path: str, file_dir: str) -> Optional[str]:
        include_path = include_path.replace("\\", "/")
        fname = os.path.basename(include_path).lower()

        # Strategy 1: relative to current file
        candidate = os.path.normpath(os.path.join(file_dir, include_path))
        candidate = candidate.replace("\\", "/")
        if candidate in self.nodes:
            return candidate

        # Strategy 2: exact filename match
        candidates = self._fname_idx.get(fname, [])
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            # prefer same directory tree
            for c in candidates:
                if file_dir and (file_dir in c or c.startswith(file_dir)):
                    return c
            return candidates[0]

        return None

    def _build_reverse(self) -> None:
        for rel, node in self.nodes.items():
            for dep in node.resolved_includes:
                dep_node = self.nodes.get(dep)
                if dep_node:
                    dep_node.included_by.add(rel)


# ---------------------------------------------------------------------------
# AI impact analysis
# ---------------------------------------------------------------------------

def _ai_impact(
    changed_file: str,
    func_names: List[str],
    affected: List[Tuple[str, int]],
    caller_map: Dict[str, List[str]],
    model_label: str,
    subscription_key: Optional[str],
) -> str:
    """Call Azure OpenAI for impact analysis. Returns formatted string."""

    # Build the user prompt
    affected_summary = "\n".join(
        f"  depth {d}  {p}" for p, d in affected[:30]
    ) or "  (none)"
    callers_summary = "\n".join(
        f"  {caller} --> calls: {', '.join(fns)}"
        for caller, fns in list(caller_map.items())[:20]
    ) or "  (none)"
    funcs_summary = ", ".join(func_names) if func_names else "none"

    system_prompt = (
        "You are an expert embedded-software impact-analysis assistant. "
        "Given a changed C/C++ file and its dependency data, produce a concise "
        "structured impact analysis with five sections:\n"
        "  1. Direct Impact\n"
        "  2. Functional Risk\n"
        "  3. Regression Scope\n"
        "  4. Breaking Change Assessment\n"
        "  5. Summary (one sentence with Risk Level: Low / Medium / High)\n"
        "Be specific. Use Markdown headers and bullet points."
    )
    user_prompt = (
        f"Changed file: {changed_file}\n"
        f"Functions in file: {funcs_summary}\n\n"
        f"Files that will recompile (include chain):\n{affected_summary}\n\n"
        f"Files that call functions from this file:\n{callers_summary}\n"
    )

    try:
        # Try to use the existing azure_openai_farm helper if available
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
        from src.config import settings as _cfg  # noqa: F401
        from src.ai.azure_openai_farm import _chat_completion  # noqa: F401
        return _chat_completion(system_prompt, user_prompt, subscription_key=subscription_key)
    except ImportError:
        pass
    except Exception as exc:
        return f"[AI error: {exc}]"

    # Fallback: try openai package directly
    try:
        from openai import AzureOpenAI  # type: ignore

        api_key = (subscription_key or os.environ.get("GENAIPLATFORM_FARM_SUBSCRIPTION_KEY", "")).strip()
        if not api_key:
            return "[AI skipped – GENAIPLATFORM_FARM_SUBSCRIPTION_KEY not set]"

        endpoint = os.environ.get("AOAI_FARM_ENDPOINT", "https://aoai-farm.bosch-temp.com/api")
        deployment = os.environ.get(
            "AOAI_FARM_DEPLOYMENT",
            "askbosch-prod-farm-openai-gpt-41-mini-2025-04-14",
        )
        api_version = os.environ.get("AOAI_FARM_API_VERSION", "2025-04-14-preview")

        client = AzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            azure_deployment=deployment,
            api_version=api_version,
        )
        resp = client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=2048,
            timeout=120,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as exc:
        return f"[AI error: {exc}]"


# ---------------------------------------------------------------------------
# Impact report printer
# ---------------------------------------------------------------------------

def _print_change_report(
    idx: CHIndex,
    rel_path: str,
    model_label: str,
    subscription_key: Optional[str],
    no_ai: bool,
    step_label: str = "",
) -> None:
    """Print the full impact report for a detected change."""

    node = idx.nodes.get(rel_path)
    if not node:
        print(f"  [!] File not found in index: {rel_path}")
        return

    fname = os.path.basename(rel_path)
    full_path = node.abs_path
    func_names = node.func_names
    funcs_display = ", ".join(func_names) if func_names else "none detected"

    # Include chain
    affected = idx.affected_files_with_depth(rel_path)

    # Caller map
    callers = idx.caller_map(rel_path)

    # ---- header ----
    _hdr(f"  >> CHANGE DETECTED -->  {fname}")

    print(f"  FILE      : {fname}")
    print(f"  FULL PATH : {full_path}")
    print(f"  FUNCTIONS : {funcs_display}")
    print(f"  AFFECTED  : {len(affected)} file(s) will recompile")
    print(f"  CALLERS   : {len(callers)} file(s) call functions from this file")
    print()

    # ---- include dependency chain ----
    _sub()
    print("  INCLUDE DEPENDENCY CHAIN  (files that will need recompilation)")
    _sub()
    if affected:
        for dep_rel, depth in affected:
            indent = "  " * depth
            print(f"    depth {depth}{indent}  {dep_rel}")
    else:
        print("  [No transitive include chain within indexed scope]")
    print()

    # ---- function caller map ----
    _sub()
    print("  FUNCTION CALLER MAP  (who calls what from this file)")
    _sub()
    if callers:
        for caller_rel, called_fns in sorted(callers.items()):
            print(f"    {caller_rel}")
            print(f"       --> calls: {', '.join(called_fns)}")
    else:
        print("  [No callers detected within indexed scope]")
    print()

    # ---- AI impact analysis ----
    if not no_ai:
        _sub()
        print(f"  AI IMPACT ANALYSIS  [{model_label}]")
        _sub()
        print("  Contacting AI (please wait)...")
        print()
        analysis = _ai_impact(
            fname, func_names, affected, callers, model_label, subscription_key
        )
        # Indent each line by 2 spaces
        for line in analysis.splitlines():
            print(f"  {line}")
        print()


# ---------------------------------------------------------------------------
# Demo mode
# ---------------------------------------------------------------------------

DEMO_COMMENT = "/* DEMO CHANGE — auto-generated; will be reverted */\n"


def _pick_demo_files(idx: CHIndex) -> Tuple[Optional[str], Optional[str]]:
    """
    Pick one header with many dependents and one .c file with many callers
    for the demo. Falls back gracefully if the index is sparse.
    """
    headers = [
        (r, len(n.included_by), n)
        for r, n in idx.nodes.items()
        if n.is_header and n.included_by
    ]
    sources = [
        (r, len(n.func_names), n)
        for r, n in idx.nodes.items()
        if not n.is_header and n.func_names
    ]

    headers.sort(key=lambda x: -x[1])
    sources.sort(key=lambda x: -x[1])

    hdr_file = headers[0][0] if headers else None
    src_file = sources[0][0] if sources else None
    return hdr_file, src_file


def run_demo(
    workspace: str,
    scope: Optional[str],
    model_label: str,
    subscription_key: Optional[str],
    no_ai: bool,
) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    scope_display = scope or "(all files)"

    # ---- Main banner ----
    print(_banner())
    print(_box_title("C/H DEPENDENCY ANALYZER  -  LIVE DEMO"))
    print(_banner())
    print()
    print(f"  Date/Time  : {now}")
    print(f"  Workspace  : {workspace}")
    print(f"  Scope      : {scope_display}")
    print(f"  Model      : {model_label}")
    print()

    # ---- Step 1: Build index ----
    _hdr(f"  STEP 1 OF 3 : Indexing workspace ({scope_display})...")

    idx = CHIndex(workspace, scope)
    scope_abs = idx.scope_path

    print(f"[*] Scanning workspace: {scope_abs}")

    file_count_box = [0]
    total_box = [0]

    def _progress(done: int, total: int) -> None:
        file_count_box[0] = done
        total_box[0] = total
        pct = int(done * 100 / total) if total else 100
        print(f"\r  Parsing {done}/{total}  ({pct}%)", end="", flush=True)

    idx.build(progress_cb=_progress)
    print()  # newline after progress

    total_files = len(idx.nodes)
    total_funcs = idx.total_functions()
    total_edges = idx.total_edges()

    print(f"[*] Found {total_files} C/H source files. Parsing\u2026")
    print(f"[+] Index complete \u2014 {total_files} files, {total_funcs} functions tracked.")
    print()
    print("  [OK] Index complete:")
    print(f"       Files indexed      : {total_files}")
    print(f"       Functions tracked  : {total_funcs}")
    print(f"       Dependencies mapped: {total_edges} edges")
    print()

    # ---- Pick demo files ----
    demo_h, demo_c = _pick_demo_files(idx)
    demo_files = [f for f in [demo_h, demo_c] if f]
    if not demo_files:
        print("[!] No suitable files found for demo in the indexed scope.")
        return

    total_steps = len(demo_files) + 1  # +1 for indexing

    for step_num, rel_path in enumerate(demo_files, start=2):
        node = idx.nodes[rel_path]
        fname = os.path.basename(rel_path)

        # ---- Step header ----
        print(_banner())
        print(f"  STEP {step_num} OF {total_steps} : DEMO CHANGE {step_num - 1}/{len(demo_files)}")
        print(f"  File  : {fname}")
        print(_banner())
        print()

        # ---- Modify file ----
        try:
            with open(node.abs_path, "r", encoding="utf-8", errors="ignore") as fh:
                original = fh.read()
            with open(node.abs_path, "w", encoding="utf-8") as fh:
                fh.write(DEMO_COMMENT + original)
            print("  [+] File physically modified on disk (demo comment prepended)")
        except Exception as exc:
            print(f"  [!] Could not modify file: {exc}")
            original = None

        # ---- Re-index ----
        print("  [+] Re-indexing changed file in dependency graph...")
        idx.reindex_file(rel_path)
        print("  [+] Re-index done")
        print()

        # ---- Impact report ----
        _print_change_report(
            idx, rel_path, model_label, subscription_key, no_ai,
            step_label=f"DEMO CHANGE {step_num - 1}/{len(demo_files)}",
        )

        # ---- Restore file ----
        if original is not None:
            try:
                with open(node.abs_path, "w", encoding="utf-8") as fh:
                    fh.write(original)
                print("  [+] File restored to original content")
                # Re-index back to original state
                idx.reindex_file(rel_path)
            except Exception as exc:
                print(f"  [!] Could not restore file: {exc}")
        print()

    # ---- Footer ----
    print(_banner())
    print("  DEMO COMPLETE")
    print("  Both files have been restored to their original state.")
    print()
    print("  To use LIVE file-watch mode (auto-detects saves from your editor):")
    print(f'    cd "{workspace}"')
    print("    python dependency_analyzer.py .")
    print(_banner())


# ---------------------------------------------------------------------------
# Live file-watch mode
# ---------------------------------------------------------------------------

def run_live(
    workspace: str,
    scope: Optional[str],
    model_label: str,
    subscription_key: Optional[str],
    no_ai: bool,
    poll_interval: float = 1.0,
) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    scope_display = scope or "(all files)"

    print(_banner())
    print(_box_title("C/H DEPENDENCY ANALYZER  -  LIVE MODE"))
    print(_banner())
    print()
    print(f"  Date/Time  : {now}")
    print(f"  Workspace  : {workspace}")
    print(f"  Scope      : {scope_display}")
    print(f"  Model      : {model_label}")
    print()

    # ---- Build initial index ----
    _hdr(f"  Indexing workspace ({scope_display})...")

    idx = CHIndex(workspace, scope)
    scope_abs = idx.scope_path
    print(f"[*] Scanning workspace: {scope_abs}")

    def _progress(done: int, total: int) -> None:
        pct = int(done * 100 / total) if total else 100
        print(f"\r  Parsing {done}/{total}  ({pct}%)", end="", flush=True)

    idx.build(progress_cb=_progress)
    print()

    total_files = len(idx.nodes)
    total_funcs = idx.total_functions()
    total_edges = idx.total_edges()

    print(f"[+] Index complete — {total_files} files, {total_funcs} functions tracked.")
    print()
    print("  [OK] Index complete:")
    print(f"       Files indexed      : {total_files}")
    print(f"       Functions tracked  : {total_funcs}")
    print(f"       Dependencies mapped: {total_edges} edges")
    print()

    print("[*] Watching for file changes (Ctrl+C to stop)...")
    print()

    prev_snap = idx.refresh_mtimes()

    try:
        while True:
            time.sleep(poll_interval)
            # Check all known files for mtime changes
            for rel, node in list(idx.nodes.items()):
                try:
                    current_mtime = os.path.getmtime(node.abs_path)
                except OSError:
                    continue
                if current_mtime != prev_snap.get(rel, 0.0):
                    prev_snap[rel] = current_mtime
                    node.mtime = current_mtime
                    print(f"[*] Change detected: {rel}")
                    idx.reindex_file(rel)
                    _print_change_report(
                        idx, rel, model_label, subscription_key, no_ai
                    )

            # Also check for new files
            for root_dir, dirs, files in os.walk(idx.scope_path):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for fname in files:
                    if os.path.splitext(fname)[1].lower() not in _C_EXTS:
                        continue
                    abs_p = os.path.join(root_dir, fname)
                    rel = os.path.relpath(abs_p, idx.root)
                    if rel not in idx.nodes:
                        print(f"[*] New file detected: {rel}")
                        node = idx._parse_node(abs_p, rel)
                        idx.nodes[rel] = node
                        idx._fname_idx[fname.lower()].append(rel)
                        idx._resolve_all()
                        idx._build_reverse()
                        prev_snap[rel] = node.mtime
                        _print_change_report(
                            idx, rel, model_label, subscription_key, no_ai
                        )

    except KeyboardInterrupt:
        print()
        print("[*] Live watch stopped.")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="C/H Dependency Analyzer — impact analysis for C/C++ workspaces",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "workspace",
        nargs="?",
        default=".",
        help="Root workspace directory to scan (default: current directory)",
    )
    parser.add_argument(
        "--scope",
        default=None,
        metavar="SUBDIR",
        help="Restrict scan to a sub-folder inside workspace",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run demo mode (simulates 2 file changes, then restores them)",
    )
    parser.add_argument(
        "--model",
        default="Azure OpenAI GPT-4o-mini",
        metavar="LABEL",
        help="Model label shown in the AI section header",
    )
    parser.add_argument(
        "--key",
        default=None,
        metavar="API_KEY",
        help="Azure OpenAI subscription key (overrides env var)",
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        dest="no_ai",
        help="Skip AI impact analysis",
    )
    parser.add_argument(
        "--poll",
        type=float,
        default=1.0,
        metavar="SECONDS",
        help="Poll interval in seconds for live mode (default: 1.0)",
    )

    args = parser.parse_args()

    workspace = os.path.abspath(args.workspace)
    if not os.path.isdir(workspace):
        print(f"[!] Workspace directory not found: {workspace}")
        sys.exit(1)

    subscription_key = args.key or os.environ.get("GENAIPLATFORM_FARM_SUBSCRIPTION_KEY", "")
    model_label = args.model

    if args.demo:
        run_demo(workspace, args.scope, model_label, subscription_key, args.no_ai)
    else:
        run_live(workspace, args.scope, model_label, subscription_key, args.no_ai, args.poll)


if __name__ == "__main__":
    main()
