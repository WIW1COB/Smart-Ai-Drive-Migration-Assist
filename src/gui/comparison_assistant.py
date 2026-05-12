"""Comparison-aware chatbot for offline and online results."""

import ast
import difflib
import json
import os
import re
import shutil
import subprocess
import threading
import tkinter as tk
import xml.etree.ElementTree as ET
from tkinter import filedialog, messagebox, scrolledtext

# Import dependency graph for chain connection and interface dependency analysis
try:
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from dependency_graph import DependencyGraphBuilder, DependencyGraph, ImpactAnalyzer, ImpactAnalysis
    DEPENDENCY_GRAPH_AVAILABLE = True
except ImportError:
    DEPENDENCY_GRAPH_AVAILABLE = False
    DependencyGraphBuilder = None
    DependencyGraph = None
    ImpactAnalyzer = None
    ImpactAnalysis = None


class ComparisonAssistantWindow:
    """Small agentic assistant grounded in the active comparison results."""

    MAX_CHAT_COPY_CHARS = 200_000
    MAX_FILE_READ_CHARS = 60_000
    MAX_DIFF_LINES = 220

    OUT_OF_SCOPE_REPLY = (
        "I'm specialized in migration analysis, code comparison, and RTC integration. "
        "This question is outside my focus area. Please ask about file differences, "
        "component analysis, migration risks, or code quality insights for this tool."
    )

    IN_SCOPE_TERMS = {
        "rtc", "snapshot", "baseline", "component", "components", "changeset", "changesets",
        "change", "changes", "changed", "difference", "differences", "diff", "compare",
        "comparison", "migration", "file", "files", "folder", "folders", "report", "reports",
        "csv", "excel", "html", "interface", "interfaces", "selected", "modified", "added",
        "removed", "platform", "project", "offline", "online", "source", "line", "lines",
        "risk", "risky", "inspect", "summary", "summarize", "overview", "status",
        # Dependency and chain connection terms
        "dependency", "dependencies", "depend", "depends", "dependent", "dependents",
        "include", "includes", "included", "header", "headers", "impact", "affects",
        "affected", "chain", "connection", "connections", "linked", "uses", "used",
        "relationship", "relationships", "require", "requires", "required",
        # Agentic action terms
        "open", "export", "navigate", "vscode", "filter", "search", "find", "show",
        "statistics", "stats", "count", "high", "risky"
    }
    
    # =========================================================================
    # AGENT TOOL DEFINITIONS - Enterprise Agentic Actions
    # =========================================================================
    AGENT_TOOLS = {
        "open_file": {
            "description": "Open a source file in the default editor",
            "triggers": ["open", "launch"],
            "requires_file": True,
        },
        "open_in_vscode": {
            "description": "Open a file in VS Code editor",
            "triggers": ["vscode", "code"],
            "requires_file": True,
        },
        "view_diff": {
            "description": "Open the HTML diff viewer for selected file",
            "triggers": ["diff", "html"],
            "requires_selection": True,
        },
        "export_report": {
            "description": "Export comparison results to CSV/Excel/HTML",
            "triggers": ["export", "save report", "generate report"],
            "formats": ["csv", "excel", "html"],
        },
        "navigate_to_file": {
            "description": "Select and highlight a file in the results table",
            "triggers": ["navigate", "go to", "select", "find"],
            "requires_file": True,
        },
        "open_dependency_viewer": {
            "description": "Open dependency analysis for a file",
            "triggers": ["dependency", "dependencies", "impact"],
            "requires_file": True,
        },
        "show_change_summary": {
            "description": "Display quick statistics about changes",
            "triggers": ["stats", "statistics", "count", "how many"],
        },
        "filter_results": {
            "description": "Filter comparison results by status or pattern",
            "triggers": ["filter", "show only"],
            "filters": ["modified", "added", "removed", "identical"],
        },
        "search_in_results": {
            "description": "Search for files matching a pattern",
            "triggers": ["search", "find", "look for"],
        },
        "open_reports": {
            "description": "Open the reports folder",
            "triggers": ["reports folder", "open reports"],
        },
        "run_interface_analysis": {
            "description": "Start interface analysis on selected components",
            "triggers": ["interface analysis", "analyze interface"],
        },
        "copy_file": {
            "description": "Copy file between source 1 and source 2",
            "triggers": ["copy", "sync"],
        },
        "show_high_impact_files": {
            "description": "Show files that affect many other files if changed",
            "triggers": ["high impact", "risky files", "critical files"],
        },
    }

    def __init__(self, parent, viewer):
        self.parent = parent
        self.viewer = viewer
        self.busy = False
        self.engine = self._build_chat_engine()
        
        # Conversation history & memory
        self.conversation_history = []  # List of {"role": "user"|"assistant", "content": "..."}
        self.max_history_turns = 10  # Keep last 10 turns for context
        
        self.last_question = ""
        self.last_context = ""
        self.last_reply = ""
        self.engine_tested = False  # Track if we've tested the engine
        self.engine_working = False  # Track if engine is actually working
        
        # Session context memory for agentic behavior
        self.session_context = {
            "last_file_discussed": None,
            "last_action_performed": None,
            "files_opened": [],  # Track which files user has opened
            "analysis_history": [],  # Track what analyses were run
            "user_preferences": {
                "preferred_editor": "notepad",  # or "vscode"
                "auto_navigate": True,  # Auto-select files when mentioned
            },
            "current_filter": None,  # Current filter applied to results
        }
        
        # Dependency graph for chain connection and interface dependency analysis
        self.dependency_graph_source1 = None
        self.dependency_graph_source2 = None
        self.impact_analyzer_source1 = None
        self.impact_analyzer_source2 = None
        self._dependency_graphs_built = False
        
        # Build dependency graphs lazily on first dependency-related query
        self._init_dependency_graphs()

        self.window = tk.Toplevel(parent)
        self.window.title("Migration Assistant")
        self.window.geometry(self._initial_geometry())
        self.window.minsize(760, 520)
        self.window.resizable(True, True)
        self.window.configure(bg="#ECF2F6")
        self.window.grid_columnconfigure(0, weight=1)
        self.window.grid_rowconfigure(1, weight=1)

        self._build_ui()
        self._show_startup_message()
        self.entry.focus_set()

    def _build_ui(self):
        header = tk.Frame(self.window, bg="#003366", height=78)
        header.grid(row=0, column=0, sticky="ew")
        header.pack_propagate(False)

        title_group = tk.Frame(header, bg="#003366")
        title_group.pack(side="left", padx=18, pady=12)

        tk.Label(title_group, text="Migration Assistant", font=("Segoe UI", 18, "bold"),
                 bg="#003366", fg="white").pack(anchor="w")
        tk.Label(title_group, text="Grounded in this comparison result", font=("Segoe UI", 9),
                 bg="#003366", fg="#B8D8FF").pack(anchor="w", pady=(2, 0))

        # Show only AI state in badge (cleaner display)
        ai_state = self._get_ai_state_label()
        badge = tk.Label(header, text=ai_state, font=("Segoe UI", 11, "bold"),
                         bg="#0F5C8C", fg="white", padx=14, pady=8)
        badge.pack(side="right", padx=18)

        body = tk.Frame(self.window, bg="#ECF2F6")
        body.grid(row=1, column=0, sticky="nsew", padx=12, pady=12)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        sidebar = tk.Frame(body, bg="#DDEAF3", width=235)
        sidebar.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        sidebar.grid_propagate(False)

        mode = "Online-Online" if self.viewer.online_context else "Offline"
        context_text = self._context_card_text(mode)
        tk.Label(sidebar, text=context_text, font=("Segoe UI", 9), bg="#CFE0EC",
                 fg="#17364A", justify="left", anchor="nw", wraplength=215,
                 padx=10, pady=10).pack(fill="x", padx=10, pady=(12, 8))

        tk.Label(
            sidebar,
            text="Agent Actions",
            font=("Segoe UI", 11, "bold"),
            bg="#DDEAF3",
            fg="#003366"
        ).pack(anchor="w", padx=12, pady=(14, 8))

        quick_prompts = [
            "Summarize this comparison",
            "Tell differences for selected file",
            "List modified files",
            "List files only in project",
            "Show file dependencies",
            "What files are affected by selected?",
            "What should I inspect next?",
            "Run interface analysis",
        ]
        for prompt in quick_prompts:
            tk.Button(
                sidebar,
                text=prompt,
                command=lambda p=prompt: self._ask(p),
                bg="#FFFFFF",
                fg="#003366",
                font=("Segoe UI", 9),
                relief="flat",
                anchor="w",
                padx=10,
                pady=7,
                wraplength=205,
                cursor="hand2"
            ).pack(fill="x", padx=10, pady=4)

        tk.Label(sidebar, text="Useful wording", font=("Segoe UI", 10, "bold"),
                 bg="#DDEAF3", fg="#003366").pack(anchor="w", padx=12, pady=(16, 6))
        for hint in [
            "Explain why selected changed",
            "What depends on this file?",
            "Show connection between A and B",
            "Which headers have most impact?",
            "Show include chain for selected",
        ]:
            tk.Label(sidebar, text=f"- {hint}", font=("Segoe UI", 9),
                     bg="#DDEAF3", fg="#425466").pack(anchor="w", padx=16, pady=1)

        chat_frame = tk.Frame(body, bg="white", highlightthickness=1, highlightbackground="#D0D7DE")
        chat_frame.grid(row=0, column=1, sticky="nsew")
        chat_frame.grid_rowconfigure(0, weight=1)
        chat_frame.grid_columnconfigure(0, weight=1)

        self.chat = scrolledtext.ScrolledText(
            chat_frame,
            wrap="word",
            state="normal",
            bg="#FFFFFF",
            fg="#17212B",
            font=("Segoe UI", 10),
            relief="flat",
            padx=18,
            pady=14
        )
        self.chat.grid(row=0, column=0, sticky="nsew")
        # Keep the transcript read-only while still allowing selection/copy.
        # Block only text-editing keys; allow selection and copy
        self.chat.bind("<Key>", self._on_chat_key)
        self.chat.bind("<<Paste>>", lambda _e: "break")
        self.chat.bind("<Control-v>", lambda _e: "break")
        self.chat.bind("<Control-c>", self._copy_chat_selection)
        self.chat.bind("<Control-a>", self._select_all_chat)
        self.chat.bind("<Button-3>", self._show_chat_menu)  # right-click
        # Avoid the "text disappears" effect on some themes when focus/hover changes.
        self.chat.config(
            selectbackground="#CDE8FF",
            inactiveselectbackground="#CDE8FF",
            selectforeground="#17212B",
        )

        self._chat_menu = tk.Menu(self.window, tearoff=0)
        self._chat_menu.add_command(label="Copy selection", command=self._copy_chat_selection)
        self._chat_menu.add_command(label="Copy last answer", command=self._copy_last_answer)
        self._chat_menu.add_command(label="Copy all", command=self._copy_all_chat)
        self._chat_menu.add_separator()
        self._chat_menu.add_command(label="Save last answer...", command=self._save_last_answer)

        # Keep the transcript read-only while still allowing selection/copy.
        # Block only text-editing keys; allow selection and copy
        self.chat.bind("<Key>", self._on_chat_key)
        self.chat.bind("<<Paste>>", lambda _e: "break")
        self.chat.bind("<Control-v>", lambda _e: "break")
        self.chat.bind("<Control-c>", self._copy_chat_selection)
        self.chat.bind("<Control-a>", self._select_all_chat)
        self.chat.bind("<Button-3>", self._show_chat_menu)  # right-click
        # Avoid the "text disappears" effect on some themes when focus/hover changes.
        self.chat.config(
            selectbackground="#CDE8FF",
            inactiveselectbackground="#CDE8FF",
            selectforeground="#17212B",
        )

        self._chat_menu = tk.Menu(self.window, tearoff=0)
        self._chat_menu.add_command(label="Copy selection", command=self._copy_chat_selection)
        self._chat_menu.add_command(label="Copy last answer", command=self._copy_last_answer)
        self._chat_menu.add_command(label="Copy all", command=self._copy_all_chat)
        self._chat_menu.add_separator()
        self._chat_menu.add_command(label="Save last answer...", command=self._save_last_answer)

        self.chat.tag_config("user_label", foreground="#007B3E", font=("Segoe UI", 9, "bold"), spacing1=8)
        self.chat.tag_config("bot_label", foreground="#003366", font=("Segoe UI", 9, "bold"), spacing1=8)
        self.chat.tag_config("user", background="#E8F5E9", lmargin1=24, lmargin2=24, rmargin=110, spacing1=4, spacing3=10)
        self.chat.tag_config("bot", background="#F4F7FB", lmargin1=24, lmargin2=24, rmargin=70, spacing1=4, spacing3=10)
        self.chat.tag_config("system", foreground="#666666", font=("Segoe UI", 9, "italic"), spacing1=6, spacing3=6)
        self.chat.tag_config("code", font=("Consolas", 9), background="#F6F8FA", lmargin1=28, lmargin2=28)

        self.suggestion_frame = tk.Frame(self.window, bg="#ECF2F6")
        self.suggestion_frame.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 6))
        self.suggestion_frame.grid_columnconfigure(1, weight=1)
        self._render_suggestions([
            "Summarize this comparison",
            "Tell differences for selected file",
            "List modified files",
        ])

        input_frame = tk.Frame(self.window, bg="#ECF2F6")
        input_frame.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 8))
        input_frame.grid_columnconfigure(0, weight=1)

        input_box = tk.Frame(input_frame, bg="#FFFFFF", highlightthickness=1, highlightbackground="#B7C3CC")
        input_box.grid(row=0, column=0, sticky="ew")
        input_box.grid_columnconfigure(0, weight=1)

        tk.Label(
            input_box,
            text="Ask about this comparison",
            font=("Segoe UI", 8, "bold"),
            bg="#FFFFFF",
            fg="#425466",
            anchor="w"
        ).grid(row=0, column=0, sticky="ew", padx=10, pady=(6, 0))

        self.entry = tk.Text(
            input_box,
            height=3,
            wrap="word",
            font=("Segoe UI", 10),
            relief="flat",
            bg="#FFFFFF",
            fg="#17212B",
            insertbackground="#003366",
            padx=10,
            pady=6
        )
        self.entry.grid(row=1, column=0, sticky="ew", padx=2, pady=(0, 2))
        self.entry.bind("<Control-Return>", lambda _e: self._ask())
        self.entry.bind("<Return>", self._on_entry_return)

        self.send_btn = tk.Button(
            input_frame,
            text="Ask",
            command=self._ask,
            bg="#007B3E",
            fg="white",
            font=("Segoe UI", 11, "bold"),
            padx=20,
            pady=19,
            relief="flat"
        )
        self.send_btn.grid(row=0, column=1, sticky="ns", padx=(8, 0))

        self.status_var = tk.StringVar(value="Ready")
        tk.Label(self.window, textvariable=self.status_var, font=("Segoe UI", 8),
                 bg="#ECF2F6", fg="#5C6B73", anchor="w").grid(row=4, column=0, sticky="ew", padx=14, pady=(0, 8))
        self.entry.focus_set()

    def _ask(self, prompt=None):
        if self.busy:
            return
        question = (prompt or self._get_query_text()).strip()
        if not question:
            return
        self._clear_query_text()
        self.last_question = question
        self._append_user(question)

        action_reply = self._maybe_run_action(question)
        if action_reply:
            self._append_bot(action_reply)
            self._after_reply(action_reply, question)
            return

        if not self._is_in_scope_question(question):
            self._append_bot(self.OUT_OF_SCOPE_REPLY)
            self._after_reply(self.OUT_OF_SCOPE_REPLY, question)
            return

        intent = self._classify_intent(question)
        local_context = self._build_context(question, intent=intent)
        self.last_context = local_context
        if not self.engine or self._should_answer_locally(intent):
            self._append_bot(local_context)
            self._after_reply(local_context, question)
            return

        self._set_busy(True)

        def worker():
            try:
                reply = self._ask_model(question, local_context, intent=intent)
            except Exception as exc:
                reply = local_context + f"\n\nAI polish unavailable: {exc}"
            self.window.after(0, lambda: self._finish_reply(reply))

        threading.Thread(target=worker, daemon=True).start()

    def _maybe_run_action(self, question):
        """Handle direct action commands without LLM involvement for speed."""
        q = question.lower()
        
        # === REPORT ACTIONS ===
        if "open" in q and "report" in q and "folder" in q:
            self.viewer.open_reports_folder()
            return "✓ Opened the reports folder."
        
        if "export" in q and ("excel" in q or "xlsx" in q):
            return self._action_export_report("excel")
        
        if "export" in q and "csv" in q:
            return self._action_export_report("csv")
        
        if "export" in q and "html" in q:
            return self._action_export_report("html")
        
        # === COPY/SAVE ACTIONS ===
        if "copy" in q and ("last" in q or "answer" in q):
            return self._copy_last_answer()
        
        if "save" in q and ("answer" in q or "chat" in q):
            return self._save_last_answer()
        
        # === FILE ACTIONS ===
        if "vscode" in q or ("code" in q and "open" in q):
            filename = self._extract_single_path_or_name(question)
            return self._action_open_in_vscode(filename)
        
        if ("run" in q or "open" in q or "start" in q) and "interface" in q:
            self.window.after(100, self.viewer.open_interface_analysis_tool)
            return "✓ Starting interface analysis. For online results, I will extract the selected RTC components first."
        
        if "open" in q and "diff" in q:
            self.viewer.open_diff()
            return "✓ Opened the selected row's HTML diff if one is available."
        
        # === NAVIGATION ACTIONS ===
        if "select" in q and ("changed" in q or "modified" in q or "different" in q):
            return self._select_first_changed_row()
        
        if ("navigate" in q or "go to" in q) and any(w in q for w in ["file", "row"]):
            filename = self._extract_single_path_or_name(question)
            if filename:
                return self._action_navigate_to_file(filename)
        
        # === ANALYSIS ACTIONS (Direct without LLM) ===
        if "show" in q and ("stats" in q or "statistics" in q or "change summary" in q):
            return self._action_show_change_summary()
        
        if "high impact" in q or ("show" in q and "risky" in q):
            return self._action_show_high_impact_files()
        
        # === FILTER/SEARCH ACTIONS ===
        if "filter" in q and "modified" in q:
            return self._action_filter_results("modified")
        
        if "filter" in q and ("added" in q or "new" in q):
            return self._action_filter_results("added")
        
        if "filter" in q and ("removed" in q or "deleted" in q):
            return self._action_filter_results("removed")
        
        if "search" in q or ("find" in q and "file" in q):
            # Extract search pattern
            pattern = self._extract_search_pattern(question)
            if pattern:
                return self._action_search_in_results(pattern)
        
        return None
    
    def _extract_search_pattern(self, question: str) -> str | None:
        """Extract search pattern from user question."""
        import re
        # Try to extract quoted pattern
        m = re.search(r"['\"]([^'\"]+)['\"]", question)
        if m:
            return m.group(1)
        # Try to extract pattern after 'for' or 'search'
        m = re.search(r"(?:for|search|find)\s+(\S+)", question, re.IGNORECASE)
        if m:
            return m.group(1).strip(".,;:")
        return None

    def _is_explicit_action_request(self, question: str) -> bool:
        """Return True only when the user is asking the tool to do something."""
        q = (question or "").lower()
        action_words = (
            "open", "launch", "start", "run", "execute", "save", "copy",
            "select", "choose", "export", "navigate", "go to", "find",
            "filter", "search", "show stats", "statistics", "vscode", "code"
        )
        if any(word in q for word in action_words):
            return True
        return q.strip().startswith(("/open", "/run", "/save", "/copy", "/select", "/export", "/navigate", "/filter", "/search"))

    def _should_execute_model_action(self, action_name: str, question: str) -> bool:
        """Gate model-suggested actions so explanation prompts do not open files."""
        if not self._is_explicit_action_request(question):
            return False

        q = (question or "").lower()
        
        # Map actions to their trigger conditions
        action_triggers = {
            "open_file": lambda: any(word in q for word in ("open", "launch")) and "vscode" not in q,
            "open_in_vscode": lambda: "vscode" in q or ("code" in q and "open" in q),
            "view_diff": lambda: "open" in q and ("diff" in q or "html" in q),
            "open_reports": lambda: "open" in q and "report" in q and "folder" in q,
            "run_interface_analysis": lambda: any(word in q for word in ("run", "start", "launch", "execute")) and "interface" in q,
            "select_changed_file": lambda: any(word in q for word in ("select", "choose")) and any(word in q for word in ("changed", "modified")),
            "copy_file": lambda: "copy" in q and "file" in q,
            "export_report": lambda: "export" in q or ("save" in q and "report" in q),
            "navigate_to_file": lambda: any(word in q for word in ("navigate", "go to", "find", "select")),
            "open_dependency_viewer": lambda: any(word in q for word in ("dependency", "dependencies", "impact")),
            "show_change_summary": lambda: any(word in q for word in ("stats", "statistics", "count", "how many")),
            "filter_results": lambda: "filter" in q or "show only" in q,
            "search_in_results": lambda: "search" in q or "find" in q,
            "show_high_impact_files": lambda: "high impact" in q or "risky" in q or "critical" in q,
        }
        
        trigger_fn = action_triggers.get(action_name)
        if trigger_fn:
            return trigger_fn()
        return False

    def _is_in_scope_question(self, question):
        """Return True when the question belongs to comparison/RTC analysis."""
        q = question.lower()
        if any(term in q for term in self.IN_SCOPE_TERMS):
            return True

        # A direct file/component name is also valid even if the wording is short.
        return self._find_best_result(question) is not None

    def _classify_intent(self, question: str) -> str:
        q = (question or "").lower()
        if self._is_list_files_request(q):
            side = self._requested_side(q)
            if side == "source1":
                return "list_source1_only" if "only" in q else "list_source1"
            if side == "source2":
                return "list_source2_only" if "only" in q else "list_source2"
            if any(w in q for w in ["modified", "changed", "different", "difference", "differences"]):
                return "list_changed"
            return "list_files"
        if any(w in q for w in ["syntax", "syntax error", "compile error", "parse error", "static check"]):
            return "syntax_check"
        if q.strip().startswith("/read") or ("read" in q and "file" in q):
            return "read_file"
        if q.strip().startswith("/diff") or ("diff" in q and "file" in q and ("between" in q or "and" in q)):
            return "diff_files"
        if q.strip().startswith("/review") or any(w in q for w in ["review", "lint", "syntax", "static check", "code review"]):
            return "review_file"
        if "difference" in q or "differences" in q or "diff" in q:
            return "diff_selected"
        if any(w in q for w in ["summary", "summarize", "overview", "status"]):
            return "summary"
        if any(w in q for w in ["modified", "different", "changed"]):
            return "list_changed"
        if any(w in q for w in ["risk", "risky", "inspect next", "priority"]):
            return "next_steps"
        # Dependency and chain connection intents
        if any(w in q for w in ["dependency", "dependencies", "depend on", "depends on"]):
            return "dependency_analysis"
        if any(w in q for w in ["impact", "affects", "affected", "what files"]):
            return "impact_analysis"
        if any(w in q for w in ["chain", "connection", "linked", "relationship"]):
            return "chain_connection"
        if any(w in q for w in ["include", "includes", "header", "headers"]) and any(w in q for w in ["what", "which", "show", "list"]):
            return "include_analysis"
        return "general"

    def _should_answer_locally(self, intent: str) -> bool:
        """Keep exact report/filter answers deterministic instead of model-dependent."""
        return intent in {
            "list_files",
            "list_source1",
            "list_source1_only",
            "list_source2",
            "list_source2_only",
            "list_changed",
            "diff_selected",
            "diff_files",
            "syntax_check",
            "review_file",
            "dependency_analysis",
            "impact_analysis",
            "chain_connection",
            "include_analysis",
        }

    def _is_list_files_request(self, q: str) -> bool:
        if not any(w in q for w in ["list", "show", "give", "which", "what"]):
            return False
        return any(w in q for w in ["file", "files", "component", "components", "items", "rows"])

    def _requested_side(self, q: str) -> str | None:
        """Map user wording to comparison source side."""
        if "snapshot 1" in q or "snapshot1" in q or "source 1" in q or "source1" in q or "platform" in q:
            return "source1"
        if "snapshot 2" in q or "snapshot2" in q or "source 2" in q or "source2" in q:
            return "source2"

        folder1 = str(getattr(self.viewer, "folder1_display", "")).lower()
        folder2 = str(getattr(self.viewer, "folder2_display", "")).lower()
        if "project" in q:
            if "project" in folder1 and "project" not in folder2:
                return "source1"
            return "source2"
        return None

    def _build_context(self, question, intent="general"):
        match = self._find_best_result(question)
        lowered = question.lower()

        if intent == "read_file":
            ctx = self._context_read_file(question)
            if ctx:
                return ctx

        if intent == "diff_files":
            ctx = self._context_diff_files(question)
            if ctx:
                return ctx

        if intent == "review_file":
            ctx = self._context_review_file(question)
            if ctx:
                return ctx

        if intent == "syntax_check":
            ctx = self._context_syntax_check(question)
            if ctx:
                return ctx

        if intent == "list_files":
            return self._list_all_files(question)

        if intent == "list_source1":
            return self._list_present_in_source("source1")

        if intent == "list_source1_only":
            return self._list_by_status(
                ("Only in Platform", "Only in Snapshot 1"),
                self._source_label("source1", only=True),
            )

        if intent == "list_source2":
            return self._list_present_in_source("source2")

        if intent == "list_source2_only":
            return self._list_by_status(
                ("Only in Project", "Only in Snapshot 2"),
                self._source_label("source2", only=True),
            )

        if intent == "list_changed":
            return self._list_by_status(("Different", "Modified", "Comments update only"), "changed")

        # Dependency and chain connection analysis
        if intent == "dependency_analysis":
            ctx = self._context_dependency_analysis(question)
            if ctx:
                return ctx

        if intent == "impact_analysis":
            ctx = self._context_impact_analysis(question)
            if ctx:
                return ctx

        if intent == "chain_connection":
            ctx = self._context_chain_connection(question)
            if ctx:
                return ctx

        if intent == "include_analysis":
            ctx = self._context_include_analysis(question)
            if ctx:
                return ctx

        if match:
            return self._describe_result(match, include_diff=True, include_dependencies=True)

        if any(word in lowered for word in ["summary", "summarize", "overview", "status"]):
            return self._comparison_summary()

        if any(phrase in lowered for phrase in ["inspect next", "next", "risk", "risky", "priority"]):
            return self._recommend_next_steps()

        if any(word in lowered for word in ["modified", "different", "changed"]):
            return self._list_by_status(("Different", "Modified", "Comments update only"), "changed")

        if "only in project" in lowered or "only in snapshot 2" in lowered:
            return self._list_by_status(("Only in Project", "Only in Snapshot 2"), "only in project/snapshot 2")

        if "only in platform" in lowered or "only in snapshot 1" in lowered:
            return self._list_by_status(("Only in Platform", "Only in Snapshot 1"), "only in platform/snapshot 1")

        if "selected" in lowered and self.viewer.current_file:
            selected = self._result_by_name(self.viewer.current_file)
            if selected:
                return self._describe_result(selected, include_diff=True)
        
        if self.viewer.online_context and "file" in lowered:
            selected = self.viewer.online_context.get("selected_components", [])
            sample = "\n".join(f"- {name}" for name in selected[:20])
            more = f"\n... and {len(selected) - 20} more selected components" if len(selected) > 20 else ""
            return (
                "This online-online result is currently stored at component/baseline level, not full file-content level.\n\n"
                "I can explain selected component baseline differences from this result. For file-level interface differences, use "
                "Run interface analysis; it extracts the selected RTC component files and opens the offline-style analyzer.\n\n"
                f"Selected online components:\n{sample}{more}"
            )

        return (
            self._comparison_summary()
            + "\n\nI could not identify a specific file/component in your question. "
            "Mention the file/component name, or select a row and ask about the selected file."
        )

    def _context_read_file(self, question: str) -> str | None:
        ref = self._extract_single_path_or_name(question)
        if not ref and self.viewer.current_file:
            ref = self.viewer.current_file
        if not ref:
            return "To read a file, mention a file name/path (or select a row and ask: 'read selected file')."

        paths = self._resolve_paths_from_reference(ref)
        if not paths:
            return f"I couldn't resolve '{ref}' to a local file in the compared sources."

        blocks = ["Read file"]
        for label, path in paths:
            content, note = self._safe_read_text(path)
            blocks.append(f"- {label}: {path}{note}")
            blocks.append("```\n" + content + "\n```")
        return "\n".join(blocks)

    def _context_diff_files(self, question: str) -> str | None:
        a, b = self._extract_two_paths_or_names(question)
        if not a and self.viewer.current_file:
            # Fallback: diff selected file across sources.
            a = self.viewer.current_file
            b = self.viewer.current_file
        if not a:
            return "To diff files, provide two paths/names (or ask: 'diff selected file')."

        left = self._resolve_single_path(a, side_preference="source1")
        right = self._resolve_single_path(b or a, side_preference="source2")
        if not left or not right:
            return f"Could not resolve both files for diff. Left={left or 'N/A'}, Right={right or 'N/A'}."

        explanation = self._make_diff_explanation(left, right)
        diff = self._make_text_diff(left, right, max_lines=self.MAX_DIFF_LINES)
        return "\n".join([
            "Plain-text file difference",
            f"- Left: {left}",
            f"- Right: {right}",
            "",
            explanation,
            "",
            diff,
        ])

    def _context_review_file(self, question: str) -> str | None:
        ref = self._extract_single_path_or_name(question)
        if not ref and self.viewer.current_file:
            ref = self.viewer.current_file
        if not ref:
            return "To review a file, mention a file name/path (or select a row and ask: 'review selected file')."

        path = self._resolve_single_path(ref)
        if not path:
            return f"I couldn't resolve '{ref}' to a local file path."

        content, note = self._safe_read_text(path)
        findings = self._basic_static_review(path, content)
        parts = ["Code review (local checks)", f"- File: {path}{note}"]
        parts.extend(findings)
        parts.append("\nFile excerpt:")
        parts.append("```\n" + content + "\n```")
        return "\n".join(parts)

    def _context_syntax_check(self, question: str) -> str | None:
        ref = self._extract_single_path_or_name(question)
        if not ref and self.viewer.current_file:
            ref = self.viewer.current_file
        if not ref:
            return "Select a row or mention a file name/path, then ask for a syntax check."

        paths = self._resolve_paths_from_reference(ref)
        if not paths:
            single = self._resolve_single_path(ref)
            paths = [("File", single)] if single else []
        if not paths:
            return f"I could not resolve '{ref}' to a local file for syntax checking."

        lines = ["Syntax/static check", f"- Requested file: {ref}"]
        for label, path in paths:
            content, note = self._safe_read_text(path)
            lines.append("")
            lines.append(f"{label}: {path}{note}")
            lines.extend(self._basic_static_review(path, content))
            snippet = self._focused_issue_excerpt(content)
            if snippet:
                lines.append("Relevant excerpt:")
                lines.append("```\n" + snippet + "\n```")
        return "\n".join(lines)

    def _extract_single_path_or_name(self, text: str) -> str | None:
        if not text:
            return None
        stripped = text.strip()
        # Slash-commands: /read path, /review path
        m = re.match(r"^/(read|review)\s+(.+)$", stripped, flags=re.IGNORECASE)
        if m:
            return m.group(2).strip().strip('"').strip("'")

        # Quoted path/name
        m = re.search(r"['\"]([^'\"]{2,})['\"]", text)
        if m:
            return m.group(1).strip()

        # Windows drive absolute path
        m = re.search(r"([A-Za-z]:\\[^\n\r\t]+)", text)
        if m:
            return m.group(1).strip().rstrip(".,;:")

        # Likely relative path tokens
        m = re.search(r"([\w][\w\-./\\]+\.[A-Za-z0-9]{1,6})", text)
        if m:
            return m.group(1).strip().rstrip(".,;:")

        # Fall back: try matching a comparison result by file/component name.
        match = self._find_best_result(text)
        if match:
            return str(match[0])
        return None

    def _extract_two_paths_or_names(self, text: str) -> tuple[str | None, str | None]:
        if not text:
            return (None, None)

        stripped = text.strip()
        m = re.match(r"^/diff\s+(.+)$", stripped, flags=re.IGNORECASE)
        if m:
            tail = m.group(1).strip()
            parts = re.split(r"\s+", tail, maxsplit=1)
            if len(parts) == 2:
                return (parts[0].strip().strip('"').strip("'"), parts[1].strip().strip('"').strip("'"))
            return (tail, None)

        # Try: diff A and B / diff A vs B / diff A between B
        for sep in [" vs ", " versus ", " and ", " between "]:
            if sep in text.lower():
                left, right = re.split(sep, text, maxsplit=1, flags=re.IGNORECASE)
                return (self._extract_single_path_or_name(left), self._extract_single_path_or_name(right))

        # Fallback: extract first two path-like tokens.
        tokens = re.findall(r"([A-Za-z]:\\[^\s]+|[\w][\w\-./\\]+\.[A-Za-z0-9]{1,6})", text)
        if len(tokens) >= 2:
            return (tokens[0], tokens[1])
        if len(tokens) == 1:
            return (tokens[0], None)
        return (None, None)

    def _project_root(self) -> str:
        here = os.path.abspath(os.path.dirname(__file__))
        return os.path.abspath(os.path.join(here, os.pardir, os.pardir))

    def _is_allowed_root(self, abs_path: str) -> bool:
        abs_path = os.path.abspath(abs_path)
        roots = []
        for attr in ["folder1_actual", "folder2_actual"]:
            root = getattr(self.viewer, attr, None)
            if root:
                roots.append(os.path.abspath(root))
        roots.append(self._project_root())
        return any(abs_path.startswith(r + os.sep) or abs_path == r for r in roots)

    def _confirm_external_read(self, abs_path: str) -> bool:
        if self._is_allowed_root(abs_path):
            return True
        return messagebox.askyesno(
            "Read External File?",
            "You asked to read a file outside the compared folders / project root:\n\n"
            f"{abs_path}\n\nProceed?",
            parent=self.window,
        )

    def _safe_read_text(self, path: str) -> tuple[str, str]:
        abs_path = os.path.abspath(path)
        if not os.path.isfile(abs_path):
            return (f"(File not found)\n{abs_path}", "")
        if not self._confirm_external_read(abs_path):
            return ("(Read cancelled by user)", "")

        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as handle:
                content = handle.read(self.MAX_FILE_READ_CHARS + 1)
            if len(content) > self.MAX_FILE_READ_CHARS:
                return (content[: self.MAX_FILE_READ_CHARS] + "\n...[truncated]...\n", " (truncated)")
            return (content, "")
        except Exception as exc:
            return (f"(Could not read file: {exc})\n{abs_path}", "")

    def _resolve_paths_from_reference(self, ref: str) -> list[tuple[str, str]]:
        if not ref:
            return []
        # Absolute path
        if os.path.isabs(ref) and os.path.isfile(ref):
            return [("File", ref)]

        # If it's a comparison result name, prefer mapping to both sources.
        row = self._result_by_name(ref)
        if row:
            name = str(row[0])
            out = []
            p1 = self.viewer.files1.get(name)
            p2 = self.viewer.files2.get(name)
            if p1:
                out.append(("Source 1", p1))
            if p2:
                out.append(("Source 2", p2))
            return out

        # Otherwise try to locate by file basename in both maps.
        needle = os.path.basename(ref).lower()
        out = []
        for label, mapping in [("Source 1", getattr(self.viewer, "files1", {})), ("Source 2", getattr(self.viewer, "files2", {}))]:
            for name, path in (mapping or {}).items():
                if os.path.basename(str(name)).lower() == needle and path:
                    out.append((label, path))
                    break
        return out

    def _resolve_single_path(self, ref: str, side_preference: str | None = None) -> str | None:
        if not ref:
            return None
        if os.path.isabs(ref):
            return ref

        paths = self._resolve_paths_from_reference(ref)
        if not paths:
            return None
        if side_preference == "source2":
            for label, path in paths:
                if label == "Source 2":
                    return path
        if side_preference == "source1":
            for label, path in paths:
                if label == "Source 1":
                    return path
        return paths[0][1]

    def _basic_static_review(self, path: str, content: str) -> list[str]:
        ext = os.path.splitext(path)[1].lower()
        findings = []
        if ext in (".py",):
            try:
                ast.parse(content)
                findings.append("- Python syntax: OK")
            except SyntaxError as exc:
                findings.append(f"- Python syntax: ERROR at line {exc.lineno}, col {exc.offset}: {exc.msg}")
        elif ext in (".json",):
            try:
                json.loads(content)
                findings.append("- JSON syntax: OK")
            except json.JSONDecodeError as exc:
                findings.append(f"- JSON syntax: ERROR at line {exc.lineno}, col {exc.colno}: {exc.msg}")
        elif ext in (".xml", ".xmi", ".arxml", ".launch", ".project", ".classpath"):
            try:
                ET.fromstring(content)
                findings.append("- XML syntax: OK")
            except ET.ParseError as exc:
                findings.append(f"- XML syntax: ERROR: {exc}")
        elif ext in (".c", ".h", ".cpp", ".hpp", ".cc", ".hh", ".java", ".js", ".ts", ".cs"):
            findings.extend(self._brace_balance_findings(content))
        else:
            findings.append(f"- Syntax check: not available for '{ext or 'no extension'}' (local).")

        if "<<<<<<<" in content or "=======" in content or ">>>>>>>" in content:
            findings.append("- Merge conflict markers detected.")
        if "\t" in content and "    " in content:
            findings.append("- Style note: mixed tabs/spaces detected.")
        if "TODO" in content or "FIXME" in content:
            findings.append("- Hygiene: TODO/FIXME markers present.")
        long_lines = [
            idx for idx, line in enumerate(content.splitlines(), start=1)
            if len(line) > 160
        ]
        if long_lines:
            sample = ", ".join(str(i) for i in long_lines[:5])
            more = "..." if len(long_lines) > 5 else ""
            findings.append(f"- Readability: {len(long_lines)} very long line(s), first at {sample}{more}.")
        if not findings:
            findings.append("- No local findings.")
        return findings

    def _brace_balance_findings(self, content: str) -> list[str]:
        findings = []
        pairs = [("{", "}"), ("(", ")"), ("[", "]")]
        for opener, closer in pairs:
            open_count = content.count(opener)
            close_count = content.count(closer)
            if open_count != close_count:
                findings.append(
                    f"- Structural check: possible unmatched '{opener}{closer}' count "
                    f"({open_count} open, {close_count} close)."
                )
        if not findings:
            findings.append("- Structural syntax check: bracket/brace counts look balanced.")
        findings.append("- Note: full compiler-level syntax validation is not available inside the assistant.")
        return findings

    def _focused_issue_excerpt(self, content: str) -> str:
        lines = content.splitlines()
        for idx, line in enumerate(lines, start=1):
            if any(token in line for token in ("<<<<<<<", "=======", ">>>>>>>", "TODO", "FIXME")):
                start = max(1, idx - 2)
                end = min(len(lines), idx + 2)
                return "\n".join(f"{n}: {lines[n - 1]}" for n in range(start, end + 1))
        return ""

    def _source_label(self, side: str, only: bool = False) -> str:
        if side == "source1":
            label = "source 1 / snapshot 1 / platform"
            if "project" in str(getattr(self.viewer, "folder1_display", "")).lower():
                label = "source 1 / snapshot 1 / project"
        else:
            label = "source 2 / snapshot 2 / project"
            if "platform" in str(getattr(self.viewer, "folder2_display", "")).lower():
                label = "source 2 / snapshot 2 / platform"
        return f"only in {label}" if only else label

    def _list_all_files(self, question: str) -> str:
        q = question.lower()
        if any(w in q for w in ["modified", "changed", "different", "difference", "differences"]):
            return self._list_by_status(("Different", "Modified", "Comments update only"), "changed")
        if "identical" in q or "same" in q:
            return self._list_by_status(("Identical",), "identical")

        rows = list(self.viewer.results)
        lines = [f"Files/components in this comparison: {len(rows)}"]
        for row in rows[:80]:
            lines.append(f"- {row[0]} ({row[4]})")
        if len(rows) > 80:
            lines.append(f"... and {len(rows) - 80} more.")
        return "\n".join(lines)

    def _list_present_in_source(self, side: str) -> str:
        if side == "source1":
            excluded = {"Only in Project", "Only in Snapshot 2"}
        else:
            excluded = {"Only in Platform", "Only in Snapshot 1"}

        rows = [r for r in self.viewer.results if str(r[4]) not in excluded]
        label = self._source_label(side)
        if not rows:
            return f"No files/components found in {label}."

        lines = [f"Files/components present in {label}: {len(rows)}"]
        grouped = {}
        for row in rows:
            grouped.setdefault(str(row[4]), []).append(row)
        for status, status_rows in sorted(grouped.items()):
            lines.append(f"\n{status}: {len(status_rows)}")
            for row in status_rows[:40]:
                lines.append(f"- {row[0]}")
            if len(status_rows) > 40:
                lines.append(f"... and {len(status_rows) - 40} more {status} row(s).")
        return "\n".join(lines)

    def _context_card_text(self, mode):
        counts = {}
        for row in self.viewer.results:
            counts[str(row[4])] = counts.get(str(row[4]), 0) + 1
        changed = counts.get("Different", 0) + counts.get("Modified", 0) + counts.get("Comments update only", 0)
        return (
            f"{mode} comparison\n"
            f"Rows: {len(self.viewer.results)}\n"
            f"Changed: {changed}\n"
            f"Only source 1: {counts.get('Only in Platform', 0) + counts.get('Only in Snapshot 1', 0)}\n"
            f"Only source 2: {counts.get('Only in Project', 0) + counts.get('Only in Snapshot 2', 0)}"
        )

    def _get_ai_state_label(self) -> str:
        """Return a human-readable AI state label based on the engine type."""
        if not self.engine:
            return "⚫ Local agent"
        
        engine_class_name = self.engine.__class__.__name__
        if "Groq" in engine_class_name:
            return "🤖 Groq AI"
        elif "ChatEngine" in engine_class_name:
            return "🔵 Azure OpenAI"
        else:
            return "✨ AI enabled"

    def _show_startup_message(self):
        """Display startup message showing AI readiness."""
        ai_status = self._get_ai_state_label()
        dep_status = "✓" if DEPENDENCY_GRAPH_AVAILABLE else "✗"
        
        if self.engine:
            greeting = (
                f"{ai_status}\n\n"
                "I'm your enterprise migration assistant with agentic capabilities.\n\n"
                "📋 ANALYSIS:\n"
                "• Explain file differences and migration risks\n"
                "• Analyze dependencies and show impact chains\n"
                "• Identify high-risk files that affect many others\n"
                "• Trace #include relationships for headers\n\n"
                "🔧 ACTIONS I CAN PERFORM:\n"
                "• Open files (in Notepad or VS Code)\n"
                "• Navigate to files in results table\n"
                "• Export reports (CSV, Excel, HTML)\n"
                "• Filter and search comparison results\n"
                "• Show change statistics and summaries\n\n"
                f"Dependency Analysis: {dep_status} {'Available' if DEPENDENCY_GRAPH_AVAILABLE else 'Not available'}\n\n"
                "Try commands like:\n"
                "• \"Show change statistics\"\n"
                "• \"Open app_main.c in VS Code\"\n"
                "• \"Show high impact files\"\n"
                "• \"Export report to Excel\"\n"
                "• \"Filter modified files\"\n"
                "• \"What depends on config.h?\""
            )
        else:
            greeting = (
                "⚫ Local agent (offline mode)\n\n"
                "AI engine unavailable. Running in local mode with agentic features.\n\n"
                "I can still help with:\n"
                "• Open files (Notepad/VS Code)\n"
                "• Export reports (CSV/Excel)\n"
                "• Navigate and filter results\n"
                "• Dependency and impact analysis\n"
                "• Show change statistics\n\n"
                f"Dependency Analysis: {dep_status} {'Available' if DEPENDENCY_GRAPH_AVAILABLE else 'Not available'}\n\n"
                "To enable Groq AI:\n"
                "1. Set GROQ_API_KEY in your .env file\n"
                "2. Restart the tool\n"
                "See GROQ_SETUP.md for details."
            )
        self._append_bot(greeting)

    def _comparison_summary(self):
        counts = {}
        for row in self.viewer.results:
            status = str(row[4])
            counts[status] = counts.get(status, 0) + 1

        lines = [
            "Comparison summary",
            f"- Source 1: {self.viewer.folder1_display}",
            f"- Source 2: {self.viewer.folder2_display}",
            f"- Total rows: {len(self.viewer.results)}",
        ]
        for status, count in sorted(counts.items()):
            lines.append(f"- {status}: {count}")

        changed = [r for r in self.viewer.results if str(r[4]) in ("Different", "Modified", "Comments update only")]
        if changed:
            lines.append("\nTop changed rows:")
            for row in changed[:10]:
                lines.append(f"- {row[0]} ({row[4]})")
        return "\n".join(lines)

    def _recommend_next_steps(self):
        changed = [r for r in self.viewer.results if str(r[4]) in ("Different", "Modified")]
        only2 = [r for r in self.viewer.results if str(r[4]) in ("Only in Project", "Only in Snapshot 2")]
        comments = [r for r in self.viewer.results if str(r[4]) == "Comments update only"]
        lines = ["Recommended next steps"]
        if changed:
            lines.append(f"- Inspect changed rows first: {len(changed)} row(s).")
            for row in changed[:5]:
                lines.append(f"  - {row[0]}")
        if only2:
            lines.append(f"- Review additions in source 2/project: {len(only2)} row(s).")
        if comments:
            lines.append(f"- Comments-only updates are lower risk but useful for documentation: {len(comments)} row(s).")
        if self.viewer.online_context:
            lines.append("- For file-level online analysis, run Interface Analysis so selected RTC components are extracted locally.")
        else:
            lines.append("- For API/header risk, run Interface Diff on the compared folders.")
        return "\n".join(lines)

    def _list_by_status(self, statuses, label):
        rows = [r for r in self.viewer.results if str(r[4]) in statuses]
        if not rows:
            return f"No rows found for {label}."
        lines = [f"Rows {label}: {len(rows)}"]
        for row in rows[:40]:
            lines.append(f"- {row[0]} ({row[4]})")
        if len(rows) > 40:
            lines.append(f"... and {len(rows) - 40} more.")
        return "\n".join(lines)

    def _describe_result(self, row, include_diff=False, include_dependencies=False):
        name = str(row[0])
        status = str(row[4])
        lines = [
            f"Result: {name}",
            f"- Status: {status}",
            f"- Metric/lines in source 1: {row[1]}",
            f"- Metric/lines in source 2: {row[2]}",
            f"- Detail: {row[3]}",
        ]

        path1 = self.viewer.files1.get(name)
        path2 = self.viewer.files2.get(name)
        if path1 or path2:
            lines.append(f"- Source 1 path/id: {path1 or 'not present'}")
            lines.append(f"- Source 2 path/id: {path2 or 'not present'}")

        if self.viewer.online_context:
            lines.extend(self._online_component_details(name))

        if include_diff and path1 and path2 and os.path.isfile(path1) and os.path.isfile(path2):
            explanation = self._make_diff_explanation(path1, path2)
            if explanation:
                lines.append("\nPlain-English diff summary:")
                lines.append(explanation)
            diff = self._make_text_diff(path1, path2)
            if diff:
                lines.append("\nFocused text diff:")
                lines.append(diff)

        # Add dependency information when requested
        if include_dependencies:
            dep_info = self._get_file_dependency_info(name)
            if dep_info:
                lines.append("\n" + dep_info)

        return "\n".join(lines)

    def _online_component_details(self, component_name):
        snap1 = {
            c.get("name"): c for c in self.viewer.online_context.get("snapshot1_components", [])
            if c.get("name")
        }.get(component_name)
        snap2 = {
            c.get("name"): c for c in self.viewer.online_context.get("snapshot2_components", [])
            if c.get("name")
        }.get(component_name)

        lines = ["- Online context: selected RTC snapshot component"]
        if snap1:
            lines.append(f"- Snapshot 1 baseline: {snap1.get('baseline_uuid', 'N/A')}")
            lines.append(f"- Snapshot 1 component UUID: {snap1.get('uuid', 'N/A')}")
        if snap2:
            lines.append(f"- Snapshot 2 baseline: {snap2.get('baseline_uuid', 'N/A')}")
            lines.append(f"- Snapshot 2 component UUID: {snap2.get('uuid', 'N/A')}")
        if snap1 and snap2 and snap1.get("baseline_uuid") != snap2.get("baseline_uuid"):
            lines.append("- Interpretation: the selected component points to different baselines between snapshots.")
        return lines

    # =========================================================================
    # DEPENDENCY GRAPH AND CHAIN CONNECTION ANALYSIS
    # =========================================================================

    def _init_dependency_graphs(self):
        """Initialize dependency graphs for both source folders."""
        if not DEPENDENCY_GRAPH_AVAILABLE:
            return
        
        try:
            folder1 = getattr(self.viewer, "folder1_actual", None)
            folder2 = getattr(self.viewer, "folder2_actual", None)
            
            if folder1 and os.path.isdir(folder1):
                builder = DependencyGraphBuilder()
                self.dependency_graph_source1 = builder.build_graph(folder1)
                if self.dependency_graph_source1:
                    self.impact_analyzer_source1 = ImpactAnalyzer(self.dependency_graph_source1)
            
            if folder2 and os.path.isdir(folder2):
                builder = DependencyGraphBuilder()
                self.dependency_graph_source2 = builder.build_graph(folder2)
                if self.dependency_graph_source2:
                    self.impact_analyzer_source2 = ImpactAnalyzer(self.dependency_graph_source2)
            
            self._dependency_graphs_built = True
        except Exception as e:
            print(f"[WARN] Failed to build dependency graphs: {e}")
            self._dependency_graphs_built = False

    def _ensure_dependency_graphs(self) -> bool:
        """Ensure dependency graphs are built, return True if available."""
        if not DEPENDENCY_GRAPH_AVAILABLE:
            return False
        if not self._dependency_graphs_built:
            self._init_dependency_graphs()
        return self.dependency_graph_source1 is not None or self.dependency_graph_source2 is not None

    def _get_file_dependency_info(self, file_name: str) -> str:
        """Get dependency information for a file."""
        if not self._ensure_dependency_graphs():
            return ""
        
        lines = []
        found_in_any_graph = False
        
        # Find file in graphs
        rel_path = self._find_rel_path_in_graph(file_name)
        
        # Check file extension - dependency analysis only works for C/C++ files
        file_ext = os.path.splitext(file_name)[1].lower()
        is_c_cpp = file_ext in ('.c', '.h', '.cpp', '.hpp', '.cc', '.hh', '.cxx', '.hxx')
        
        if not rel_path:
            # File not found in dependency graph
            if not is_c_cpp:
                return (
                    f"Dependency analysis is only available for C/C++ files.\n"
                    f"'{file_name}' is a {file_ext or 'non-source'} file.\n"
                    f"Try selecting a .c, .h, .cpp, or .hpp file."
                )
            
            # Check if graphs have any nodes at all
            graph1_count = len(self.dependency_graph_source1.nodes) if self.dependency_graph_source1 else 0
            graph2_count = len(self.dependency_graph_source2.nodes) if self.dependency_graph_source2 else 0
            
            if graph1_count == 0 and graph2_count == 0:
                return (
                    f"Dependency graphs are empty - no C/C++ files found in the compared folders.\n"
                    f"Make sure the folders contain .c, .h, .cpp files."
                )
            
            return (
                f"File '{file_name}' not found in dependency graph.\n\n"
                f"Graph contains {graph1_count} files from Source 1, {graph2_count} from Source 2.\n"
                f"The file may not have #include relationships or is outside the scanned folders."
            )
        
        lines.append(f"Dependency Analysis for: {file_name}")
        lines.append(f"(Matched to: {rel_path})")
        
        if self.dependency_graph_source1:
            node = self.dependency_graph_source1.get_node(rel_path)
            if node:
                found_in_any_graph = True
                lines.append(f"\n📁 Source 1 (Platform):")
                
                # What this file includes
                if node.resolved_includes:
                    lines.append(f"  Includes ({len(node.resolved_includes)} files):")
                    for inc in sorted(node.resolved_includes)[:10]:
                        lines.append(f"    → {inc}")
                    if len(node.resolved_includes) > 10:
                        lines.append(f"    ... and {len(node.resolved_includes) - 10} more")
                else:
                    lines.append(f"  Includes: none")
                
                # What includes this file
                if node.included_by:
                    lines.append(f"  Included by ({len(node.included_by)} files):")
                    for dep in sorted(node.included_by)[:10]:
                        lines.append(f"    ← {dep}")
                    if len(node.included_by) > 10:
                        lines.append(f"    ... and {len(node.included_by) - 10} more")
                else:
                    lines.append(f"  Included by: none (leaf node)")
                
                # Impact radius
                if self.impact_analyzer_source1:
                    try:
                        impact = self.dependency_graph_source1.get_impact_radius(rel_path)
                        if impact > 0:
                            lines.append(f"  ⚠️ Impact radius: {impact} files affected if changed")
                    except Exception:
                        pass
        
        if self.dependency_graph_source2:
            node = self.dependency_graph_source2.get_node(rel_path)
            if node:
                found_in_any_graph = True
                lines.append(f"\n📁 Source 2 (Project):")
                
                if node.resolved_includes:
                    lines.append(f"  Includes ({len(node.resolved_includes)} files):")
                    for inc in sorted(node.resolved_includes)[:10]:
                        lines.append(f"    → {inc}")
                    if len(node.resolved_includes) > 10:
                        lines.append(f"    ... and {len(node.resolved_includes) - 10} more")
                else:
                    lines.append(f"  Includes: none")
                
                if node.included_by:
                    lines.append(f"  Included by ({len(node.included_by)} files):")
                    for dep in sorted(node.included_by)[:10]:
                        lines.append(f"    ← {dep}")
                    if len(node.included_by) > 10:
                        lines.append(f"    ... and {len(node.included_by) - 10} more")
                else:
                    lines.append(f"  Included by: none (leaf node)")
                
                if self.impact_analyzer_source2:
                    try:
                        impact = self.dependency_graph_source2.get_impact_radius(rel_path)
                        if impact > 0:
                            lines.append(f"  ⚠️ Impact radius: {impact} files affected if changed")
                    except Exception:
                        pass
        
        if not found_in_any_graph:
            lines.append(f"\nFile path matched but no dependency data found.")
            lines.append(f"The file may not contain or be included by any other files.")
        
        return "\n".join(lines)

    def _find_rel_path_in_graph(self, file_name: str) -> str | None:
        """Find relative path matching file_name in dependency graphs.
        
        Tries multiple matching strategies:
        1. Exact match on basename
        2. Path ends with the provided file_name
        3. Compute relative path from source folder using viewer's current_path1/2
        4. Partial path match (any part of path contains file_name)
        """
        if not file_name:
            return None
            
        file_base = os.path.basename(file_name).lower()
        file_name_lower = file_name.lower().replace("\\", "/")
        
        # Strategy 1 & 2: Try basename and endswith match
        for graph in [self.dependency_graph_source1, self.dependency_graph_source2]:
            if not graph:
                continue
            for rel_path in graph.nodes:
                rel_path_normalized = rel_path.lower().replace("\\", "/")
                # Exact basename match
                if os.path.basename(rel_path).lower() == file_base:
                    return rel_path
                # Path ends with file_name
                if rel_path_normalized.endswith(file_name_lower):
                    return rel_path
        
        # Strategy 3: Compute relative path from source folder
        # If viewer has current_path1/2, derive relative path from folder1_actual/folder2_actual
        folder1 = getattr(self.viewer, "folder1_actual", None)
        folder2 = getattr(self.viewer, "folder2_actual", None)
        current_path1 = getattr(self.viewer, "current_path1", None)
        current_path2 = getattr(self.viewer, "current_path2", None)
        
        for folder, current_path, graph in [
            (folder1, current_path1, self.dependency_graph_source1),
            (folder2, current_path2, self.dependency_graph_source2)
        ]:
            if folder and current_path and graph:
                try:
                    # Compute relative path from source folder
                    abs_folder = os.path.abspath(folder).replace("\\", "/")
                    abs_path = os.path.abspath(current_path).replace("\\", "/")
                    if abs_path.startswith(abs_folder):
                        derived_rel = abs_path[len(abs_folder):].lstrip("/")
                        # Check if this exists in graph
                        for rel_path in graph.nodes:
                            if rel_path.replace("\\", "/") == derived_rel:
                                return rel_path
                            if rel_path.replace("\\", "/").endswith(derived_rel):
                                return rel_path
                except Exception:
                    pass
        
        # Strategy 4: Partial path match (file_name appears anywhere in path)
        for graph in [self.dependency_graph_source1, self.dependency_graph_source2]:
            if not graph:
                continue
            for rel_path in graph.nodes:
                rel_path_normalized = rel_path.lower().replace("\\", "/")
                # Check if any part of the path matches
                if file_base in rel_path_normalized:
                    return rel_path
        
        return None

    def _context_dependency_analysis(self, question: str) -> str | None:
        """Build context for dependency analysis questions."""
        if not self._ensure_dependency_graphs():
            return (
                "Dependency analysis is not available.\n"
                "Make sure the compared folders contain C/C++ source files.\n"
                "The dependency graph module analyzes #include relationships."
            )
        
        # Find file reference in question
        ref = self._extract_single_path_or_name(question)
        if not ref and self.viewer.current_file:
            ref = self.viewer.current_file
        
        if not ref:
            # Provide overview of dependency graph
            return self._dependency_overview()
        
        rel_path = self._find_rel_path_in_graph(ref)
        if not rel_path:
            return f"Could not find '{ref}' in the dependency graph.\nMention a specific file name or select a row."
        
        lines = [f"Dependency analysis for: {ref}"]
        
        # Analyze in both graphs
        for label, graph, analyzer in [
            ("Source 1 (Platform)", self.dependency_graph_source1, self.impact_analyzer_source1),
            ("Source 2 (Project)", self.dependency_graph_source2, self.impact_analyzer_source2),
        ]:
            if not graph:
                continue
            
            node = graph.get_node(rel_path)
            if not node:
                continue
            
            lines.append(f"\n{label}:")
            
            # Direct dependencies (what this file includes)
            deps = graph.get_dependencies(rel_path, recursive=False)
            if deps:
                lines.append(f"  Direct dependencies ({len(deps)}):")
                for d in sorted(deps)[:8]:
                    lines.append(f"    ← includes: {d}")
                if len(deps) > 8:
                    lines.append(f"    ... and {len(deps) - 8} more")
            else:
                lines.append("  Direct dependencies: None")
            
            # Transitive dependencies
            all_deps = graph.get_dependencies(rel_path, recursive=True)
            if len(all_deps) > len(deps):
                lines.append(f"  Transitive dependencies: {len(all_deps)} total")
            
            # Reverse dependencies (what depends on this file)
            dependents = graph.get_dependents(rel_path, recursive=False)
            if dependents:
                lines.append(f"  Direct dependents ({len(dependents)}):")
                for d in sorted(dependents)[:8]:
                    lines.append(f"    → included by: {d}")
                if len(dependents) > 8:
                    lines.append(f"    ... and {len(dependents) - 8} more")
            else:
                lines.append("  Direct dependents: None (no files include this)")
            
            # All dependents
            all_dependents = graph.get_dependents(rel_path, recursive=True)
            if len(all_dependents) > len(dependents):
                lines.append(f"  Transitive dependents: {len(all_dependents)} total")
            
            # Impact analysis
            if analyzer:
                impact = analyzer.analyze_impact(rel_path)
                if impact.all_dependents:
                    lines.append(f"  IMPACT: Changes to this file affect {len(impact.all_dependents)} files")
                    if impact.functional_areas:
                        areas = ", ".join(f"{k}: {v}" for k, v in sorted(impact.functional_areas.items())[:5])
                        lines.append(f"  Affected areas: {areas}")
        
        return "\n".join(lines)

    def _context_impact_analysis(self, question: str) -> str | None:
        """Build context for impact analysis questions."""
        if not self._ensure_dependency_graphs():
            return "Impact analysis requires the dependency graph module."
        
        ref = self._extract_single_path_or_name(question)
        if not ref and self.viewer.current_file:
            ref = self.viewer.current_file
        
        if not ref:
            # Show high-impact files
            return self._high_impact_files_report()
        
        rel_path = self._find_rel_path_in_graph(ref)
        if not rel_path:
            return f"Could not find '{ref}' in the dependency graph."
        
        lines = [f"Impact analysis for: {ref}"]
        
        for label, graph, analyzer in [
            ("Source 1 (Platform)", self.dependency_graph_source1, self.impact_analyzer_source1),
            ("Source 2 (Project)", self.dependency_graph_source2, self.impact_analyzer_source2),
        ]:
            if not analyzer:
                continue
            
            impact = analyzer.analyze_impact(rel_path)
            lines.append(f"\n{label}:")
            lines.append(f"  Direct files affected: {len(impact.direct_dependents)}")
            lines.append(f"  Total files affected: {len(impact.all_dependents)}")
            lines.append(f"  Headers affected: {impact.headers_affected}")
            lines.append(f"  Sources affected: {impact.sources_affected}")
            
            if impact.functional_areas:
                lines.append("  Functional areas affected:")
                for area, count in sorted(impact.functional_areas.items(), key=lambda x: -x[1]):
                    lines.append(f"    - {area}: {count} files")
            
            if impact.direct_dependents:
                lines.append("  Direct dependents:")
                for dep in impact.direct_dependents[:10]:
                    lines.append(f"    - {dep}")
                if len(impact.direct_dependents) > 10:
                    lines.append(f"    ... and {len(impact.direct_dependents) - 10} more")
        
        return "\n".join(lines)

    def _context_chain_connection(self, question: str) -> str | None:
        """Build context for chain connection analysis."""
        if not self._ensure_dependency_graphs():
            return "Chain connection analysis requires the dependency graph module."
        
        # Try to find two files mentioned
        parts = re.split(r'\s+(?:and|to|from|between)\s+', question, flags=re.IGNORECASE)
        
        ref1 = self._extract_single_path_or_name(parts[0]) if len(parts) > 0 else None
        ref2 = self._extract_single_path_or_name(parts[1]) if len(parts) > 1 else None
        
        if not ref1 and self.viewer.current_file:
            ref1 = self.viewer.current_file
        
        if ref1 and ref2:
            return self._analyze_connection_between(ref1, ref2)
        elif ref1:
            return self._analyze_file_connections(ref1)
        else:
            return self._dependency_chain_overview()

    def _analyze_connection_between(self, file1: str, file2: str) -> str:
        """Analyze connection between two files."""
        rel1 = self._find_rel_path_in_graph(file1)
        rel2 = self._find_rel_path_in_graph(file2)
        
        if not rel1:
            return f"Could not find '{file1}' in the dependency graph."
        if not rel2:
            return f"Could not find '{file2}' in the dependency graph."
        
        lines = [f"Connection analysis: {file1} ↔ {file2}"]
        
        for label, graph in [
            ("Source 1 (Platform)", self.dependency_graph_source1),
            ("Source 2 (Project)", self.dependency_graph_source2),
        ]:
            if not graph:
                continue
            
            lines.append(f"\n{label}:")
            
            # Check direct connection
            node1 = graph.get_node(rel1)
            node2 = graph.get_node(rel2)
            
            if node1 and rel2 in node1.resolved_includes:
                lines.append(f"  DIRECT: {file1} includes {file2}")
            elif node2 and rel1 in node2.resolved_includes:
                lines.append(f"  DIRECT: {file2} includes {file1}")
            else:
                # Check indirect connection
                deps1 = graph.get_dependencies(rel1, recursive=True)
                deps2 = graph.get_dependencies(rel2, recursive=True)
                
                if rel2 in deps1:
                    lines.append(f"  INDIRECT: {file1} transitively depends on {file2}")
                elif rel1 in deps2:
                    lines.append(f"  INDIRECT: {file2} transitively depends on {file1}")
                else:
                    # Check common dependencies
                    common = deps1 & deps2
                    if common:
                        lines.append(f"  SHARED DEPENDENCIES: Both files depend on {len(common)} common files")
                        for c in sorted(common)[:5]:
                            lines.append(f"    - {c}")
                    else:
                        lines.append("  No direct or indirect connection found")
        
        return "\n".join(lines)

    def _analyze_file_connections(self, file_ref: str) -> str:
        """Analyze all connections for a single file."""
        rel_path = self._find_rel_path_in_graph(file_ref)
        if not rel_path:
            return f"Could not find '{file_ref}' in the dependency graph."
        
        lines = [f"Connection analysis for: {file_ref}"]
        
        for label, graph in [
            ("Source 1 (Platform)", self.dependency_graph_source1),
            ("Source 2 (Project)", self.dependency_graph_source2),
        ]:
            if not graph:
                continue
            
            node = graph.get_node(rel_path)
            if not node:
                continue
            
            lines.append(f"\n{label}:")
            
            # Upstream (what this file depends on)
            upstream = graph.get_dependencies(rel_path, recursive=True)
            if upstream:
                lines.append(f"  Upstream chain ({len(upstream)} files):")
                for u in sorted(upstream)[:10]:
                    lines.append(f"    ↑ {u}")
                if len(upstream) > 10:
                    lines.append(f"    ... and {len(upstream) - 10} more")
            
            # Downstream (what depends on this file)
            downstream = graph.get_dependents(rel_path, recursive=True)
            if downstream:
                lines.append(f"  Downstream chain ({len(downstream)} files):")
                for d in sorted(downstream)[:10]:
                    lines.append(f"    ↓ {d}")
                if len(downstream) > 10:
                    lines.append(f"    ... and {len(downstream) - 10} more")
            
            if not upstream and not downstream:
                lines.append("  No connections found (standalone file)")
        
        return "\n".join(lines)

    def _context_include_analysis(self, question: str) -> str | None:
        """Build context for include/header analysis questions."""
        if not self._ensure_dependency_graphs():
            return "Include analysis requires the dependency graph module."
        
        ref = self._extract_single_path_or_name(question)
        if not ref and self.viewer.current_file:
            ref = self.viewer.current_file
        
        if not ref:
            # Show header statistics
            return self._header_analysis_overview()
        
        rel_path = self._find_rel_path_in_graph(ref)
        if not rel_path:
            return f"Could not find '{ref}' in the dependency graph."
        
        lines = [f"Include analysis for: {ref}"]
        
        for label, graph in [
            ("Source 1 (Platform)", self.dependency_graph_source1),
            ("Source 2 (Project)", self.dependency_graph_source2),
        ]:
            if not graph:
                continue
            
            node = graph.get_node(rel_path)
            if not node:
                continue
            
            lines.append(f"\n{label}:")
            lines.append(f"  Is header: {node.is_header}")
            lines.append(f"  Is source: {node.is_source}")
            
            # Raw includes (before resolution)
            if node.includes:
                lines.append(f"  #include statements ({len(node.includes)}):")
                for inc in sorted(node.includes)[:15]:
                    lines.append(f"    #include \"{inc}\"")
                if len(node.includes) > 15:
                    lines.append(f"    ... and {len(node.includes) - 15} more")
            
            # Resolved includes
            if node.resolved_includes:
                lines.append(f"  Resolved to local files ({len(node.resolved_includes)}):")
                for inc in sorted(node.resolved_includes)[:10]:
                    lines.append(f"    → {inc}")
                if len(node.resolved_includes) > 10:
                    lines.append(f"    ... and {len(node.resolved_includes) - 10} more")
            
            # Who includes this
            if node.included_by:
                lines.append(f"  Included by ({len(node.included_by)}):")
                for inc in sorted(node.included_by)[:10]:
                    lines.append(f"    ← {inc}")
                if len(node.included_by) > 10:
                    lines.append(f"    ... and {len(node.included_by) - 10} more")
        
        return "\n".join(lines)

    def _dependency_overview(self) -> str:
        """Provide overview of dependency graphs."""
        lines = ["Dependency Graph Overview"]
        
        for label, graph in [
            ("Source 1 (Platform)", self.dependency_graph_source1),
            ("Source 2 (Project)", self.dependency_graph_source2),
        ]:
            if not graph:
                lines.append(f"\n{label}: Not available")
                continue
            
            headers = sum(1 for n in graph.nodes.values() if n.is_header)
            sources = sum(1 for n in graph.nodes.values() if n.is_source)
            
            lines.append(f"\n{label}:")
            lines.append(f"  Total files: {len(graph.nodes)}")
            lines.append(f"  Headers: {headers}")
            lines.append(f"  Sources: {sources}")
            
            # Find most impactful files
            impact_list = [(p, graph.get_impact_radius(p)) for p in graph.nodes]
            impact_list.sort(key=lambda x: x[1], reverse=True)
            
            if impact_list and impact_list[0][1] > 0:
                lines.append("  Most impactful files (changes affect most files):")
                for path, impact in impact_list[:5]:
                    if impact > 0:
                        lines.append(f"    - {path}: affects {impact} files")
        
        lines.append("\nTip: Ask about a specific file to see its dependencies.")
        return "\n".join(lines)

    def _high_impact_files_report(self) -> str:
        """Report on high-impact files across both sources."""
        lines = ["High Impact Files Report"]
        lines.append("Files where changes would affect the most other files:\n")
        
        for label, graph, analyzer in [
            ("Source 1 (Platform)", self.dependency_graph_source1, self.impact_analyzer_source1),
            ("Source 2 (Project)", self.dependency_graph_source2, self.impact_analyzer_source2),
        ]:
            if not analyzer:
                continue
            
            high_impact = analyzer.get_high_impact_files(min_impact=3)
            if high_impact:
                lines.append(f"{label}:")
                for path, impact in high_impact[:10]:
                    lines.append(f"  - {path}: {impact} dependent files")
                if len(high_impact) > 10:
                    lines.append(f"  ... and {len(high_impact) - 10} more")
                lines.append("")
        
        if len(lines) <= 2:
            lines.append("No high-impact files found (no file affects 3+ other files).")
        
        return "\n".join(lines)

    def _dependency_chain_overview(self) -> str:
        """Provide overview of dependency chains."""
        lines = ["Dependency Chain Overview"]
        
        for label, graph in [
            ("Source 1 (Platform)", self.dependency_graph_source1),
            ("Source 2 (Project)", self.dependency_graph_source2),
        ]:
            if not graph:
                continue
            
            # Find files with most dependencies
            dep_counts = [(p, len(graph.get_dependencies(p, recursive=True))) for p in graph.nodes]
            dep_counts.sort(key=lambda x: x[1], reverse=True)
            
            lines.append(f"\n{label}:")
            if dep_counts and dep_counts[0][1] > 0:
                lines.append("  Files with longest dependency chains:")
                for path, count in dep_counts[:5]:
                    if count > 0:
                        lines.append(f"    - {path}: depends on {count} files")
            
            # Check for circular dependencies
            cycles = graph.find_circular_dependencies()
            if cycles:
                lines.append(f"  ⚠️ Circular dependencies found: {len(cycles)}")
                for cycle in cycles[:3]:
                    lines.append(f"    - {' → '.join(cycle)}")
        
        lines.append("\nTip: Ask 'what is the connection between file1 and file2' for specific analysis.")
        return "\n".join(lines)

    def _header_analysis_overview(self) -> str:
        """Provide overview of header file analysis."""
        lines = ["Header File Analysis Overview"]
        
        for label, graph in [
            ("Source 1 (Platform)", self.dependency_graph_source1),
            ("Source 2 (Project)", self.dependency_graph_source2),
        ]:
            if not graph:
                continue
            
            headers = [(p, n) for p, n in graph.nodes.items() if n.is_header]
            
            lines.append(f"\n{label}:")
            lines.append(f"  Total headers: {len(headers)}")
            
            # Most included headers
            header_usage = [(p, len(n.included_by)) for p, n in headers]
            header_usage.sort(key=lambda x: x[1], reverse=True)
            
            if header_usage and header_usage[0][1] > 0:
                lines.append("  Most used headers:")
                for path, count in header_usage[:5]:
                    if count > 0:
                        lines.append(f"    - {path}: included by {count} files")
            
            # Headers with most includes
            header_deps = [(p, len(n.resolved_includes)) for p, n in headers]
            header_deps.sort(key=lambda x: x[1], reverse=True)
            
            if header_deps and header_deps[0][1] > 0:
                lines.append("  Headers with most dependencies:")
                for path, count in header_deps[:5]:
                    if count > 0:
                        lines.append(f"    - {path}: includes {count} files")
        
        lines.append("\nTip: Ask about a specific header to see its include tree.")
        return "\n".join(lines)

    def _make_text_diff(self, path1, path2, max_lines=140):
        abs1 = os.path.abspath(path1)
        abs2 = os.path.abspath(path2)
        if os.path.isfile(abs1) and not self._confirm_external_read(abs1):
            return "(Diff cancelled by user for left file)"
        if os.path.isfile(abs2) and not self._confirm_external_read(abs2):
            return "(Diff cancelled by user for right file)"
        try:
            with open(path1, "r", encoding="utf-8", errors="replace") as f1:
                left = f1.readlines()
            with open(path2, "r", encoding="utf-8", errors="replace") as f2:
                right = f2.readlines()
        except Exception as exc:
            return f"Could not read files for diff: {exc}"

        diff = list(difflib.unified_diff(
            left,
            right,
            fromfile=os.path.basename(path1),
            tofile=os.path.basename(path2),
            n=3
        ))
        if not diff:
            return "No textual differences detected."
        if len(diff) > max_lines:
            diff = diff[:max_lines] + ["... diff truncated; open HTML diff for full view.\n"]
        if len(diff) > max_lines:
            diff = diff[:max_lines] + ["... diff truncated; open HTML diff for full view.\n"]
        return "```diff\n" + "".join(diff) + "\n```"

    def _make_diff_explanation(self, path1: str, path2: str) -> str:
        try:
            with open(path1, "r", encoding="utf-8", errors="replace") as f1:
                left = f1.readlines()
            with open(path2, "r", encoding="utf-8", errors="replace") as f2:
                right = f2.readlines()
        except Exception as exc:
            return f"Could not read both files for explanation: {exc}"

        matcher = difflib.SequenceMatcher(None, left, right)
        added = removed = replaced_left = replaced_right = 0
        hunks = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            if tag == "insert":
                added += j2 - j1
            elif tag == "delete":
                removed += i2 - i1
            elif tag == "replace":
                replaced_left += i2 - i1
                replaced_right += j2 - j1
            hunks.append((tag, i1 + 1, i2, j1 + 1, j2))

        if not hunks:
            return "No textual differences detected between the two local files."

        lines = [
            f"- Difference blocks: {len(hunks)}",
            f"- Added lines in right/source 2: {added}",
            f"- Removed lines from left/source 1: {removed}",
            f"- Changed lines: {replaced_left} left line(s) replaced by {replaced_right} right line(s)",
        ]

        lines.append("- Main changed areas:")
        for tag, i1, i2, j1, j2 in hunks[:8]:
            if tag == "insert":
                lines.append(f"  - Lines {j1}-{j2} added in source 2.")
            elif tag == "delete":
                lines.append(f"  - Lines {i1}-{i2} removed from source 1.")
            else:
                lines.append(f"  - Source 1 lines {i1}-{i2} changed to source 2 lines {j1}-{j2}.")
        if len(hunks) > 8:
            lines.append(f"  - {len(hunks) - 8} more changed area(s) not listed here.")
        return "\n".join(lines)

    def _find_best_result(self, question):
        if "selected" in question.lower() and self.viewer.current_file:
            return self._result_by_name(self.viewer.current_file)

        q = question.lower()
        best = None
        best_score = 0
        for row in self.viewer.results:
            name = str(row[0])
            name_l = name.lower()
            base_l = os.path.basename(name_l)
            score = 0
            if name_l in q:
                score = len(name_l) + 50
            elif base_l and base_l in q:
                score = len(base_l) + 30
            else:
                parts = [p for p in re.split(r"[/\\_.\-\s]+", name_l) if len(p) > 2]
                score = sum(1 for p in parts if p in q)
            if score > best_score:
                best = row
                best_score = score
        return best if best_score > 0 else None

    def _result_by_name(self, name):
        for row in self.viewer.results:
            if str(row[0]) == name:
                return row
        return None

    def _build_chat_engine(self):
        """Build chat engine: tries Groq first, then AOAI (if available)."""
        try:
            from src.config import settings
            print("Starting AI engine initialization")

            # ========== Try Groq (Primary) ==========
            groq_key = os.environ.get("GROQ_API_KEY", "")
            print("API Key Exists:", bool(groq_key))

            if groq_key and groq_key.strip():
                try:
                    from src.chatbot.chatbot import GroqChatEngine
                    groq_model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
                    
                    # Get proxy configuration (if corporate network). Prefer
                    groq_proxy_url = (
                        getattr(settings, "GROQ_PROXY_URL", "")
                        or getattr(settings, "PROXY_URL", "")
                    )
                    groq_proxy_user = (
                        getattr(settings, "GROQ_PROXY_USERNAME", "")
                        or getattr(settings, "PROXY_USER", "")
                    )
                    groq_proxy_pass = (
                        getattr(settings, "GROQ_PROXY_PASSWORD", "")
                        or getattr(settings, "PROXY_PASS", "")
                    )
                    groq_proxy_domain = getattr(settings, "PROXY_DOMAIN", "")
                    if (
                        groq_proxy_domain
                        and groq_proxy_user
                        and "\\" not in groq_proxy_user
                        and "/" not in groq_proxy_user
                    ):
                        groq_proxy_user = f"{groq_proxy_domain}\\{groq_proxy_user}"
                    
                    if groq_proxy_url and groq_proxy_url.strip():
                        print(f"[INFO] Groq configured with corporate proxy")
                    
                    engine = GroqChatEngine(
                        api_key=groq_key,
                        model=groq_model,
                        proxy_url=groq_proxy_url if groq_proxy_url and groq_proxy_url.strip() else None,
                        proxy_user=groq_proxy_user if groq_proxy_user and groq_proxy_user.strip() else None,
                        proxy_password=groq_proxy_pass if groq_proxy_pass and groq_proxy_pass.strip() else None
                    )
                    print("[INFO] ✅ Groq engine configured (will test on first use)")
                    return engine
                except Exception as groq_err:
                    # Fall through to AOAI if Groq fails
                    print(f"[WARN] Groq initialization failed: {groq_err}")
                    import traceback
                    traceback.print_exc()
            
            # ========== Fallback: Try AOAI (Bosch Farm; currently disabled) ==========
            # Uncomment below when AOAI Farm service is back online.
            # aoai_key = getattr(settings, "AOAI_FARM_SUBSCRIPTION_KEY", "")
            # if aoai_key and aoai_key.strip():
            #     try:
            #         from src.chatbot.chatbot import ChatConfig, ChatEngine
            #         endpoint_base = getattr(settings, "AOAI_FARM_ENDPOINT", "").rstrip("/")
            #         deployment = getattr(settings, "AOAI_CHAT_DEPLOYMENT", None) or getattr(settings, "AOAI_FARM_DEPLOYMENT", "")
            #         api_version = getattr(settings, "AOAI_CHAT_API_VERSION", None) or getattr(settings, "AOAI_FARM_API_VERSION", "")
            #         endpoint = f"{endpoint_base}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
            #         cfg = ChatConfig(
            #             api_key=aoai_key,
            #             endpoint=endpoint,
            #             temperature=None,
            #             max_tokens=None,
            #             timeout_sec=90
            #         )
            #         return ChatEngine(cfg)
            #     except Exception as aoai_err:
            #         print(f"[INFO] AOAI initialization failed: {aoai_err}")
            
            print("[INFO] No LLM engine available. Running in local agent mode.")
            return None
        except Exception as exc:
            print(f"[ERROR] Chat engine initialization failed: {exc}")
            return None

    def _ask_model(self, question, local_context, intent="general"):
        system = self._system_prompt(intent=intent)
        
        # Build messages with conversation history
        messages = []
        
        # Add system prompt
        messages.append({"role": "system", "content": system})
        
        # Add conversation history (last N turns)
        for msg in self.conversation_history[-self.max_history_turns:]:
            messages.append(msg)
        
        # Add current user question
        messages.append({
            "role": "user",
            "content": f"User question:\n{question}\n\nComparison/tool context:\n{local_context}"
        })
        
        try:
            reply = self.engine.complete(messages)
            # Add to history
            self.conversation_history.append({"role": "user", "content": question})
            self.conversation_history.append({"role": "assistant", "content": reply})
            # Trim history if too long
            if len(self.conversation_history) > self.max_history_turns * 2:
                self.conversation_history = self.conversation_history[-self.max_history_turns * 2:]
            return reply
        except Exception as exc:
            raise RuntimeError(f"Model call failed: {exc}") from exc

    def _execute_agent_action(self, action_name: str, args: dict = None) -> str:
        """Execute an agentic action (tool call). Called when the model requests an action."""
        args = args or {}
        
        # Update session context
        self.session_context["last_action_performed"] = action_name
        
        try:
            if action_name == "open_file":
                filename = args.get("filename", None)
                file_ref = args.get("file_ref", None)
                return self._action_open_file(filename=filename, file_ref=file_ref)
            elif action_name == "open_in_vscode":
                filename = args.get("filename", None)
                return self._action_open_in_vscode(filename=filename)
            elif action_name == "view_diff":
                return self._action_view_diff()
            elif action_name == "open_reports":
                self.viewer.open_reports_folder()
                return "✓ Opened reports folder."
            elif action_name == "run_interface_analysis":
                self.window.after(100, self.viewer.open_interface_analysis_tool)
                return "✓ Starting interface analysis..."
            elif action_name == "select_changed_file":
                return self._select_first_changed_row()
            elif action_name == "copy_file":
                src = args.get("source", "1")
                dst = args.get("destination", "2")
                return self._action_copy_file(src, dst)
            elif action_name == "export_report":
                fmt = args.get("format", "excel")
                return self._action_export_report(fmt)
            elif action_name == "navigate_to_file":
                filename = args.get("filename", None)
                return self._action_navigate_to_file(filename)
            elif action_name == "open_dependency_viewer":
                filename = args.get("filename", None)
                return self._action_open_dependency_viewer(filename)
            elif action_name == "show_change_summary":
                return self._action_show_change_summary()
            elif action_name == "filter_results":
                status = args.get("status", None)
                pattern = args.get("pattern", None)
                return self._action_filter_results(status, pattern)
            elif action_name == "search_in_results":
                pattern = args.get("pattern", None)
                return self._action_search_in_results(pattern)
            elif action_name == "show_high_impact_files":
                return self._action_show_high_impact_files()
            else:
                return f"Unknown action: {action_name}"
        except Exception as exc:
            return f"Action '{action_name}' failed: {exc}"

    def _action_open_file(self, filename: str = None, file_ref: str = None) -> str:
        """Open a file by filename or file_ref (f1/f2).
        
        Search strategy:
        1. If filename provided: search in files1/files2 dicts by basename
        2. If file_ref provided: use currently selected file paths
        3. Fall back to searching comparison results
        """
        import subprocess
        import platform as sys_platform
        
        path_to_open = None
        file_name_display = None
        source_label = None
        
        # Strategy 1: If filename is specified, search in the files dictionaries
        if filename:
            filename_clean = filename.strip("'\"")
            basename_clean = os.path.basename(filename_clean).lower()
            
            # Search in files1 (Platform/Source 1)
            for rel_path, abs_path in (self.viewer.files1 or {}).items():
                if os.path.basename(rel_path).lower() == basename_clean:
                    if os.path.exists(abs_path):
                        path_to_open = abs_path
                        source_label = "Source 1 (Platform)"
                        file_name_display = rel_path
                        break
            
            # If not found, search in files2 (Project/Source 2)
            if not path_to_open:
                for rel_path, abs_path in (self.viewer.files2 or {}).items():
                    if os.path.basename(rel_path).lower() == basename_clean:
                        if os.path.exists(abs_path):
                            path_to_open = abs_path
                            source_label = "Source 2 (Project)"
                            file_name_display = rel_path
                            break
            
            # Fallback: Search in comparison results
            if not path_to_open:
                for row in self.viewer.results:
                    name = str(row[0])
                    if os.path.basename(name).lower() == basename_clean:
                        path1 = str(row[1]) if len(row) > 1 else None
                        path2 = str(row[2]) if len(row) > 2 else None
                        
                        if path1 and os.path.exists(path1):
                            path_to_open = path1
                            source_label = "Source 1 (Platform)"
                            file_name_display = name
                        elif path2 and os.path.exists(path2):
                            path_to_open = path2
                            source_label = "Source 2 (Project)"
                            file_name_display = name
                        if path_to_open:
                            break
        
        # Strategy 2: If file_ref is specified, use current selection from results
        elif file_ref:
            file_ref_clean = file_ref.strip("'\"")
            if "f1" in file_ref_clean.lower() or "source 1" in file_ref_clean.lower() or "platform" in file_ref_clean.lower():
                if self.viewer.current_path1 and os.path.exists(self.viewer.current_path1):
                    path_to_open = self.viewer.current_path1
                    source_label = "Source 1 (Platform)"
                    file_name_display = self.viewer.current_file
            elif "f2" in file_ref_clean.lower() or "source 2" in file_ref_clean.lower() or "project" in file_ref_clean.lower():
                if self.viewer.current_path2 and os.path.exists(self.viewer.current_path2):
                    path_to_open = self.viewer.current_path2
                    source_label = "Source 2 (Project)"
                    file_name_display = self.viewer.current_file
        
        if not path_to_open:
            # Give helpful error message
            found_where = []
            if filename:
                found_where.append(f"file '{filename}' in comparison folders")
            if file_ref:
                found_where.append("selected row (nothing selected)")
            msg = f"Could not open {' or '.join(found_where) if found_where else 'file'}."
            msg += "\n\nTip: Select a row in the results table first, or ask to open a specific filename."
            return msg
        
        try:
            if sys_platform.system() == "Windows":
                subprocess.run(["notepad.exe", path_to_open], check=False)
            else:
                subprocess.run(["open", path_to_open], check=False)
            return f"✓ Opened: {file_name_display}\n({source_label})"
        except Exception as e:
            return f"Failed to open file: {e}"

    def _action_view_diff(self) -> str:
        """Open HTML diff viewer for selected file."""
        if not self.viewer.current_file:
            return "No file selected. Please select a row first."
        self.viewer.open_diff()
        return f"Opened HTML diff for: {self.viewer.current_file}"

    def _action_copy_file(self, src: str, dst: str) -> str:
        """Copy file between sources. src/dst can be '1' or '2'."""
        try:
            src_num = int(src) if src.isdigit() else 1
            dst_num = int(dst) if dst.isdigit() else 2
            if src_num == dst_num:
                return "Source and destination must be different."
            self.viewer.copy_file(src_num, dst_num)
            return f"✓ Copied file from source {src_num} to source {dst_num}: {self.viewer.current_file}"
        except Exception as e:
            return f"Copy failed: {e}"

    # =========================================================================
    # NEW ENTERPRISE AGENTIC ACTIONS
    # =========================================================================

    def _action_open_in_vscode(self, filename: str = None) -> str:
        """Open a file in VS Code editor."""
        import subprocess
        import shutil
        
        # Check if VS Code is available
        vscode_path = shutil.which("code")
        if not vscode_path:
            return "VS Code ('code' command) not found in PATH. Please install VS Code or use 'open file' instead."
        
        path_to_open = None
        file_name_display = None
        
        if filename:
            filename_clean = filename.strip("'\"")
            basename_clean = os.path.basename(filename_clean).lower()
            
            # Search in files1 and files2
            for mapping, label in [(self.viewer.files1, "Source 1"), (self.viewer.files2, "Source 2")]:
                for rel_path, abs_path in (mapping or {}).items():
                    if os.path.basename(rel_path).lower() == basename_clean:
                        if os.path.exists(abs_path):
                            path_to_open = abs_path
                            file_name_display = rel_path
                            break
                if path_to_open:
                    break
        elif self.viewer.current_path1:
            path_to_open = self.viewer.current_path1
            file_name_display = self.viewer.current_file
        
        if not path_to_open:
            return "Could not find file to open. Specify a filename or select a row first."
        
        try:
            subprocess.Popen(["code", path_to_open], shell=True)
            # Update session context
            self.session_context["files_opened"].append(file_name_display)
            self.session_context["user_preferences"]["preferred_editor"] = "vscode"
            return f"✓ Opened in VS Code: {file_name_display}"
        except Exception as e:
            return f"Failed to open VS Code: {e}"

    def _action_export_report(self, fmt: str = "excel") -> str:
        """Export comparison results to specified format."""
        fmt = fmt.lower().strip()
        
        try:
            if fmt == "csv":
                # Use viewer's CSV export
                if hasattr(self.viewer, 'open_csv_report'):
                    self.viewer.open_csv_report()
                    return "✓ Exported and opened CSV report"
                else:
                    return "CSV export not available"
            elif fmt in ("excel", "xlsx"):
                if hasattr(self.viewer, 'open_excel_report'):
                    self.viewer.open_excel_report()
                    return "✓ Exported and opened Excel report"
                else:
                    return "Excel export not available"
            elif fmt == "html":
                if hasattr(self.viewer, 'open_diff'):
                    self.viewer.open_diff()
                    return "✓ Opened HTML diff report"
                else:
                    return "HTML export not available"
            else:
                return f"Unknown format: {fmt}. Use 'csv', 'excel', or 'html'."
        except Exception as e:
            return f"Export failed: {e}"

    def _action_navigate_to_file(self, filename: str = None) -> str:
        """Navigate to and select a file in the results table."""
        if not filename:
            return "Please specify a filename to navigate to."
        
        filename_clean = filename.strip("'\"").lower()
        basename_clean = os.path.basename(filename_clean).lower()
        
        # Search in tree items
        for item in self.viewer.tree.get_children():
            values = self.viewer.tree.item(item, 'values')
            if values:
                item_name = str(values[0]).lower()
                item_basename = os.path.basename(item_name).lower()
                if item_basename == basename_clean or filename_clean in item_name:
                    self.viewer.tree.selection_set(item)
                    self.viewer.tree.see(item)
                    self.viewer.tree.focus(item)
                    self.viewer.on_file_select()
                    # Update session context
                    self.session_context["last_file_discussed"] = values[0]
                    return f"✓ Navigated to: {values[0]}"
        
        return f"File '{filename}' not found in comparison results."

    def _action_open_dependency_viewer(self, filename: str = None) -> str:
        """Show dependency analysis for a file."""
        if not self._ensure_dependency_graphs():
            return "Dependency analysis not available. Ensure C/C++ source files are present in compared folders."
        
        target_file = filename
        if not target_file and self.viewer.current_file:
            target_file = self.viewer.current_file
        
        if not target_file:
            return "Please specify a file or select one from the results."
        
        # Get dependency info - this now returns helpful messages even when file not found
        dep_info = self._get_file_dependency_info(target_file)
        if dep_info:
            self.session_context["analysis_history"].append({
                "type": "dependency",
                "file": target_file,
            })
            return f"📊 {dep_info}"
        else:
            # This shouldn't happen now since _get_file_dependency_info always returns something
            return f"Could not analyze dependencies for '{target_file}'."

    def _action_show_change_summary(self) -> str:
        """Display quick statistics about changes."""
        counts = {}
        for row in self.viewer.results:
            status = str(row[4])
            counts[status] = counts.get(status, 0) + 1
        
        total = len(self.viewer.results)
        modified = counts.get("Different", 0) + counts.get("Modified", 0)
        comments_only = counts.get("Comments update only", 0)
        only_source1 = counts.get("Only in Platform", 0) + counts.get("Only in Snapshot 1", 0)
        only_source2 = counts.get("Only in Project", 0) + counts.get("Only in Snapshot 2", 0)
        identical = counts.get("Identical", 0)
        
        summary = f"""📊 Change Statistics:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total files:        {total}
Modified:           {modified} ({(modified/total*100):.1f}% if total else 0)
Comments only:      {comments_only}
Only in Source 1:   {only_source1}
Only in Source 2:   {only_source2}
Identical:          {identical}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Risk Assessment:
• High risk: {modified} files need code review
• Medium risk: {only_source2} files are new additions
• Low risk: {comments_only} files have comment changes only"""
        
        return summary

    def _action_filter_results(self, status: str = None, pattern: str = None) -> str:
        """Filter comparison results by status or pattern."""
        if not status and not pattern:
            return "Please specify a status (modified, added, removed, identical) or pattern to filter."
        
        status_map = {
            "modified": ("Different", "Modified"),
            "changed": ("Different", "Modified", "Comments update only"),
            "added": ("Only in Project", "Only in Snapshot 2"),
            "removed": ("Only in Platform", "Only in Snapshot 1"),
            "identical": ("Identical",),
        }
        
        filtered = []
        filter_desc = ""
        
        if status:
            status_key = status.lower().strip()
            target_statuses = status_map.get(status_key, (status,))
            filtered = [r for r in self.viewer.results if str(r[4]) in target_statuses]
            filter_desc = f"status='{status}'"
        
        if pattern:
            pattern_lower = pattern.lower()
            if filtered:
                filtered = [r for r in filtered if pattern_lower in str(r[0]).lower()]
            else:
                filtered = [r for r in self.viewer.results if pattern_lower in str(r[0]).lower()]
            filter_desc += f" pattern='{pattern}'" if filter_desc else f"pattern='{pattern}'"
        
        if not filtered:
            return f"No files match filter: {filter_desc}"
        
        # Update session context
        self.session_context["current_filter"] = {"status": status, "pattern": pattern}
        
        lines = [f"📋 Filtered results ({filter_desc}): {len(filtered)} files"]
        for row in filtered[:20]:
            lines.append(f"  • {row[0]} ({row[4]})")
        if len(filtered) > 20:
            lines.append(f"  ... and {len(filtered) - 20} more")
        
        return "\n".join(lines)

    def _action_search_in_results(self, pattern: str = None) -> str:
        """Search for files matching a pattern in results."""
        if not pattern:
            return "Please specify a search pattern."
        
        pattern_lower = pattern.lower().strip()
        matches = []
        
        for row in self.viewer.results:
            name = str(row[0]).lower()
            if pattern_lower in name:
                matches.append(row)
        
        if not matches:
            return f"🔍 No files matching '{pattern}' found."
        
        lines = [f"🔍 Search results for '{pattern}': {len(matches)} files"]
        for row in matches[:15]:
            lines.append(f"  • {row[0]} ({row[4]})")
        if len(matches) > 15:
            lines.append(f"  ... and {len(matches) - 15} more")
        
        # Auto-navigate to first match if preference is set
        if self.session_context["user_preferences"].get("auto_navigate") and matches:
            first_match = str(matches[0][0])
            self._action_navigate_to_file(first_match)
            lines.append(f"\n✓ Auto-navigated to first match: {first_match}")
        
        return "\n".join(lines)

    def _action_show_high_impact_files(self) -> str:
        """Show files that have high impact (many dependents)."""
        if not self._ensure_dependency_graphs():
            return "Dependency analysis not available for impact assessment."
        
        high_impact = []
        
        # Analyze both source graphs
        for graph, label in [(self.dependency_graph_source1, "Source 1"), 
                             (self.dependency_graph_source2, "Source 2")]:
            if not graph:
                continue
            for rel_path, node in graph.nodes.items():
                if hasattr(node, 'included_by') and len(node.included_by) >= 3:
                    # Also check if file is in our comparison results
                    basename = os.path.basename(rel_path).lower()
                    for row in self.viewer.results:
                        if os.path.basename(str(row[0])).lower() == basename:
                            high_impact.append({
                                "file": rel_path,
                                "dependents": len(node.included_by),
                                "status": str(row[4]),
                                "source": label,
                            })
                            break
        
        if not high_impact:
            return "No high-impact files found (files with 3+ dependents)."
        
        # Sort by number of dependents
        high_impact.sort(key=lambda x: x["dependents"], reverse=True)
        
        lines = ["🔥 High Impact Files (changes affect many other files):"]
        for item in high_impact[:10]:
            risk = "⚠️" if item["status"] in ("Different", "Modified") else "✓"
            lines.append(f"  {risk} {item['file']} - {item['dependents']} dependents ({item['status']})")
        
        modified_high_impact = [f for f in high_impact if f["status"] in ("Different", "Modified")]
        if modified_high_impact:
            lines.append(f"\n⚠️ WARNING: {len(modified_high_impact)} high-impact files are modified!")
        
        return "\n".join(lines)

    def _extract_and_execute_actions(self, reply: str, question: str = "") -> list[str]:
        """Extract [ACTION: ...] patterns from the reply and execute them."""
        action_pattern = r"\[ACTION:\s*(\w+)\s*\((.*?)\)\s*\]"
        matches = re.findall(action_pattern, reply)
        
        results = []
        for action_name, args_str in matches:
            try:
                if not self._should_execute_model_action(action_name, question):
                    results.append(f"Skipped {action_name}: action was not explicitly requested.")
                    continue

                # Parse arguments from the string (improved key=value parsing)
                args = {}
                if args_str.strip():
                    # Handle formats like: filename='app_main.c', file_ref='f1', source='1', destination='2'
                    # Match key='value', key="value", or key=value (unquoted)
                    arg_pairs = re.findall(r"(\w+)=(?:'([^']*)'|\"([^\"]*)\"|([^,)]*))", args_str)
                    for key, single_q, double_q, unquoted in arg_pairs:
                        value = single_q or double_q or unquoted
                        if value:
                            args[key] = value.strip()
                
                result = self._execute_agent_action(action_name, args)
                results.append(f"✓ {action_name}: {result}")
            except Exception as e:
                results.append(f"✗ {action_name}: {e}")
        
        return results

    def _strip_action_tags(self, reply: str) -> str:
        """Hide internal action tags from the chat transcript."""
        cleaned = re.sub(r"\n?\[ACTION:\s*\w+\s*\(.*?\)\s*\]\s*", "", reply, flags=re.DOTALL)
        return cleaned.strip()

    def _system_prompt(self, intent: str = "general") -> str:
        # Enterprise-ready guardrails: grounded answers, explicit uncertainty, no hallucinations.
        # This prompt also teaches the model which knowledge sources are authoritative.
        intent_hint = {
            "summary": "Focus on a concise executive summary and next steps.",
            "diff_selected": "Explain differences and likely impact; keep it actionable.",
            "diff_files": "Explain the diff at a high level and call out risky changes.",
            "read_file": "Summarize what the file does based on the excerpt; note truncation.",
            "review_file": "Provide a code review: correctness, style, migration risk, and suggested edits.",
            "next_steps": "Prioritize what to inspect next and why.",
            "list_changed": "Summarize changed items and recommended triage.",
            "dependency_analysis": "Explain which files depend on this file and what it depends on. Highlight impact of changes.",
            "impact_analysis": "Explain how changes to this file would affect other files in the codebase.",
            "chain_connection": "Trace the dependency chain between files, showing include relationships.",
            "include_analysis": "Explain the #include structure and header dependencies.",
        }.get(intent, "")

        return (
            "You are an enterprise-grade migration-analysis assistant inside a desktop comparison tool.\n"
            "You MUST be grounded in the provided context only. If something is missing, say exactly what you need.\n\n"
            
            "CONVERSATION MEMORY:\n"
            "• You have access to the full conversation history in this session.\n"
            "• Reference previous exchanges when answering follow-up questions.\n"
            "• Build on prior context to provide more relevant and personalized answers.\n"
            "• If the user references earlier decisions or files mentioned before, remember them.\n\n"
            
            "DEPENDENCY & CHAIN ANALYSIS CAPABILITIES:\n"
            "You can analyze file dependencies and connection chains between project and platform folders:\n"
            "• Show which files depend on a given file (downstream impact)\n"
            "• Show what files a given file includes/depends on (upstream dependencies)\n"
            "• Trace connection chains between two files\n"
            "• Identify high-impact files (changes affect many other files)\n"
            "• Analyze #include relationships for C/C++ headers\n"
            "When the context includes dependency information, use it to explain:\n"
            "- Why a change in platform affects project files\n"
            "- Which interfaces are shared between folders\n"
            "- The ripple effect of modifications\n\n"
            
            "AVAILABLE TOOLS (Agentic Actions):\n"
            "You can suggest these actions when the user explicitly asks to perform them:\n\n"
            "FILE OPERATIONS:\n"
            "• open_file(filename='app_main.c') — Opens file in default editor\n"
            "• open_in_vscode(filename='app_main.c') — Opens file in VS Code\n"
            "• view_diff() — Opens HTML diff viewer for selected file\n"
            "• copy_file(source='1', destination='2') — Copies file between sources\n\n"
            "NAVIGATION:\n"
            "• navigate_to_file(filename='app_main.c') — Selects file in results table\n"
            "• select_changed_file() — Auto-selects first changed row\n"
            "• search_in_results(pattern='main') — Search files by pattern\n"
            "• filter_results(status='modified') — Filter by status (modified/added/removed/identical)\n\n"
            "ANALYSIS:\n"
            "• open_dependency_viewer(filename='header.h') — Show dependency analysis\n"
            "• show_high_impact_files() — List files that affect many others\n"
            "• show_change_summary() — Display change statistics\n"
            "• run_interface_analysis() — Start interface analysis on components\n\n"
            "REPORTS:\n"
            "• export_report(format='excel') — Export to CSV/Excel/HTML\n"
            "• open_reports() — Open the reports folder\n\n"
            
            "TO SUGGEST AN ACTION:\n"
            "Only include an [ACTION: ...] tag when the user explicitly asks to open, run, export, navigate, filter, search, or select something.\n"
            "If the user asks to explain, summarize, tell differences, assess risk, or say why something changed, answer in text only—do NOT include an action tag.\n"
            "Format: [ACTION: action_name(param='value')]\n"
            "Examples:\n"
            "  [ACTION: open_file(filename='app_main.c')]\n"
            "  [ACTION: export_report(format='excel')]\n"
            "  [ACTION: navigate_to_file(filename='config.h')]\n"
            "  [ACTION: filter_results(status='modified')]\n"
            "  [ACTION: show_high_impact_files()]\n\n"
            
            "Authoritative knowledge sources (in priority order):\n"
            "1) The comparison/tool context provided in the user message (statuses, paths, counts).\n"
            "2) Dependency analysis data showing #include relationships and impact chains.\n"
            "3) Any embedded file excerpts and unified diffs in that context.\n"
            "4) Online RTC component metadata if explicitly present.\n\n"
            "Rules:\n"
            f"- If the user asks anything unrelated, reply exactly: {self.OUT_OF_SCOPE_REPLY}\n"
            "- Do not invent file contents, baselines, paths, or metrics.\n"
            "- If a diff/excerpt is truncated, acknowledge it and suggest viewing the full HTML diff.\n"
            "- Prefer short, structured answers with bullet points and concrete next actions.\n"
            "- When proposing code changes, give precise edits (function/section names).\n"
            "- If you suggest an action, place it at the END of your message in [ACTION: ...] format.\n\n"
            f"Intent guidance: {intent_hint}"
        )

    def _set_busy(self, busy):
        self.busy = busy
        self.send_btn.config(state="disabled" if busy else "normal")
        self.status_var.set("Thinking..." if busy else "Ready")
        if busy:
            self._append_system("Assistant is thinking...")

    def _finish_reply(self, reply):
        self._set_busy(False)
        
        # Extract and execute suggested actions
        action_results = self._extract_and_execute_actions(reply, self.last_question)
        display_reply = self._strip_action_tags(reply)
        
        # Display reply
        self._append_bot(display_reply)
        
        # Display action results if any
        if action_results:
            executed = [item for item in action_results if not item.startswith("Skipped ")]
            skipped = [item for item in action_results if item.startswith("Skipped ")]
            if executed:
                self._append_system("\nActions executed:\n" + "\n".join(executed))
            if skipped and self._is_explicit_action_request(self.last_question):
                self._append_system("\nActions not run:\n" + "\n".join(skipped))
        
        self._after_reply(display_reply, self.last_question)

    def _after_reply(self, reply, question):
        self.last_reply = reply
        # Update session context with discussed file if any
        mentioned_file = self._extract_single_path_or_name(question)
        if mentioned_file:
            self.session_context["last_file_discussed"] = mentioned_file
        self._render_suggestions(self._suggest_followups(question, reply))
        self.status_var.set("Ready")

    def _suggest_followups(self, question, reply):
        """Generate context-aware follow-up suggestions."""
        q = question.lower()
        suggestions = []
        
        # Context-aware suggestions based on question type
        if "summary" in q or "overview" in q:
            suggestions.extend([
                "Show change statistics",
                "Show high impact files",
                "Export report to Excel",
                "List modified files"
            ])
        elif "depend" in q or "include" in q or "impact" in q or "chain" in q:
            suggestions.extend([
                "Show high impact files",
                "Open dependency viewer",
                "Filter modified files",
                "What files are affected?"
            ])
        elif "open" in q or "vscode" in q:
            suggestions.extend([
                "View diff for this file",
                "What depends on this file?",
                "Show change statistics",
                "Navigate to next file"
            ])
        elif "export" in q or "report" in q:
            suggestions.extend([
                "Export to CSV",
                "Export to Excel",
                "Open reports folder",
                "Show change statistics"
            ])
        elif "filter" in q or "search" in q:
            suggestions.extend([
                "Filter modified files",
                "Search for headers",
                "Show high impact files",
                "Clear filter"
            ])
        elif "selected" in q or self._find_best_result(question):
            suggestions.extend([
                "Open in VS Code",
                "What depends on this?",
                "View diff",
                "Show impact analysis"
            ])
        elif "modified" in q or "changed" in q:
            suggestions.extend([
                "Show high impact files",
                "Export modified to Excel",
                "Open first modified file",
                "Show dependencies"
            ])
        elif self.viewer.online_context:
            suggestions.extend([
                "Run interface analysis",
                "Show change statistics",
                "List selected components",
                "Export comparison"
            ])
        else:
            suggestions.extend([
                "Summarize this comparison",
                "Show change statistics",
                "Show high impact files",
                "List modified files"
            ])
        
        return suggestions[:4]

    def _render_suggestions(self, suggestions):
        for child in self.suggestion_frame.winfo_children():
            child.destroy()
        tk.Label(self.suggestion_frame, text="Suggested next:", font=("Segoe UI", 9, "bold"),
                 bg="#ECF2F6", fg="#425466").grid(row=0, column=0, sticky="w", padx=(0, 8))
        chips = tk.Frame(self.suggestion_frame, bg="#ECF2F6")
        chips.grid(row=0, column=1, sticky="ew")
        for idx, suggestion in enumerate(suggestions):
            tk.Button(
                chips,
                text=suggestion,
                command=lambda s=suggestion: self._ask(s),
                bg="#FFFFFF",
                fg="#003366",
                font=("Segoe UI", 8),
                relief="solid",
                bd=1,
                padx=10,
                pady=4,
                cursor="hand2",
                wraplength=150
            ).grid(row=idx // 2, column=idx % 2, sticky="w", padx=4, pady=2)

    def _initial_geometry(self):
        """Choose a size that fits the current screen and keeps the input visible."""
        try:
            screen_w = self.window.winfo_screenwidth()
            screen_h = self.window.winfo_screenheight()
            width = min(1120, max(760, int(screen_w * 0.86)))
            height = min(780, max(560, int(screen_h * 0.82)))
            x = max(0, (screen_w - width) // 2)
            y = max(0, (screen_h - height) // 2)
            return f"{width}x{height}+{x}+{y}"
        except Exception:
            return "1040x700"

    def _on_entry_return(self, event):
        """Enter sends; Shift+Enter inserts a newline."""
        if event.state & 0x0001:  # Shift pressed
            return None
        self._ask()
        return "break"

    def _get_query_text(self):
        return self.entry.get("1.0", "end-1c")

    def _clear_query_text(self):
        self.entry.delete("1.0", "end")

    def _select_first_changed_row(self):
        for item in self.viewer.tree.get_children():
            values = self.viewer.tree.item(item, 'values')
            if values and str(values[1]) in ("Different", "Modified", "Comments update only"):
                self.viewer.tree.selection_set(item)
                self.viewer.tree.see(item)
                self.viewer.on_file_select()
                return f"Selected first changed row: {values[0]}"
        return "No changed row was found to select."

    def _save_last_answer(self):
        if not self.last_reply:
            return "There is no assistant answer to save yet."
        path = filedialog.asksaveasfilename(
            parent=self.window,
            title="Save Assistant Answer",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("Markdown files", "*.md"), ("All files", "*.*")]
        )
        if not path:
            return "Save cancelled."
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(f"Question:\n{self.last_question}\n\nAnswer:\n{self.last_reply}\n")
            return f"Saved the last answer to:\n{path}"
        except Exception as exc:
            messagebox.showerror("Save Failed", str(exc), parent=self.window)
            return f"Could not save the answer: {exc}"

    def _append_user(self, text):
        self._write("\nYou\n", "user_label")
        self._write(text + "\n", "user")

    def _append_bot(self, text):
        self._write("\nAssistant\n", "bot_label")
        self._write_with_code_blocks(text + "\n", base_tag="bot")

    def _append_system(self, text):
        self._write("\n" + text + "\n", "system")

    def _write_with_code_blocks(self, text: str, base_tag: str) -> None:
        """Render simple fenced code blocks (```...```) using the `code` tag."""
        in_code = False
        for line in text.splitlines(keepends=True):
            if line.lstrip().startswith("```"):
                in_code = not in_code
                self._write(line, "system" if base_tag == "system" else base_tag)
                continue
            self._write(line, "code" if in_code else base_tag)

    def _write(self, text, tag):
        self.chat.insert("end", text, tag)
        self.chat.see("end")

    def _show_chat_menu(self, event=None):
        try:
            self._chat_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._chat_menu.grab_release()

    def _copy_chat_selection(self, _event=None):
        try:
            selection = self.chat.get("sel.first", "sel.last")
        except Exception:
            selection = ""
        if not selection.strip():
            self.status_var.set("No selection to copy")
            return "break"
        if len(selection) > self.MAX_CHAT_COPY_CHARS:
            selection = selection[: self.MAX_CHAT_COPY_CHARS] + "\n...[truncated for clipboard]...\n"
        self.window.clipboard_clear()
        self.window.clipboard_append(selection)
        self.status_var.set("Copied selection")
        return "break"

    def _copy_all_chat(self):
        content = self.chat.get("1.0", "end-1c")
        if len(content) > self.MAX_CHAT_COPY_CHARS:
            content = content[: self.MAX_CHAT_COPY_CHARS] + "\n...[truncated for clipboard]...\n"
        self.window.clipboard_clear()
        self.window.clipboard_append(content)
        self.status_var.set("Copied full transcript")
        return "Copied the full transcript to clipboard."

    def _copy_last_answer(self):
        if not self.last_reply:
            self.status_var.set("No answer to copy")
            return "There is no assistant answer to copy yet."
        text = self.last_reply
        if len(text) > self.MAX_CHAT_COPY_CHARS:
            text = text[: self.MAX_CHAT_COPY_CHARS] + "\n...[truncated for clipboard]...\n"
        self.window.clipboard_clear()
        self.window.clipboard_append(text)
        self.status_var.set("Copied last answer")
        return "Copied the last answer to clipboard."

    def _select_all_chat(self, _event=None):
        self.chat.tag_add("sel", "1.0", "end-1c")
        self.status_var.set("Selected all text")
        return "break"

    def _on_chat_key(self, event=None):
        """Handle key events: block editing but allow selection."""
        if not event:
            return None
        
        # Allow arrow keys, page up/down, shift for selection
        if event.keysym in ("Up", "Down", "Left", "Right", "Prior", "Next", "Home", "End"):
            return None  # Allow these
        
        # Block Delete, Backspace, and other editing keys
        if event.keysym in ("Delete", "BackSpace"):
            return "break"
        
        # Block any regular character input (text editing)
        if event.state & 0x0004:  # Control key pressed
            # Allow Ctrl+A, Ctrl+C (handled by their own bindings)
            return None
        if event.state & 0x0001:  # Shift key pressed
            # Allow Shift+Arrow for selection
            return None
        
        # Block regular character input
        if len(event.char) > 0 and event.char.isprintable():
            return "break"
        
        return None
