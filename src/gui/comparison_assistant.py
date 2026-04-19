"""Comparison-aware chatbot for offline and online results."""

import difflib
import os
import re
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext


class ComparisonAssistantWindow:
    """Small agentic assistant grounded in the active comparison results."""

    def __init__(self, parent, viewer):
        self.parent = parent
        self.viewer = viewer
        self.busy = False
        self.engine = self._build_chat_engine()
        self.last_question = ""
        self.last_context = ""
        self.last_reply = ""

        self.window = tk.Toplevel(parent)
        self.window.title("Migration Assistant")
        self.window.geometry("1100x760")
        self.window.minsize(880, 620)
        self.window.configure(bg="#ECF2F6")
        self.window.transient(parent)

        self._build_ui()
        self._append_bot(
            "Hi. I can answer from this comparison result.\n\n"
            "Try:\n"
            "- Summarize this comparison\n"
            "- Tell differences for selected file\n"
            "- What changed in <file or component name>?\n"
            "- List modified files\n"
            "- Open reports folder\n"
            "- Run interface analysis"
        )

    def _build_ui(self):
        header = tk.Frame(self.window, bg="#003366", height=78)
        header.pack(fill="x")
        header.pack_propagate(False)

        title_group = tk.Frame(header, bg="#003366")
        title_group.pack(side="left", padx=18, pady=12)

        tk.Label(title_group, text="Migration Assistant", font=("Segoe UI", 18, "bold"),
                 bg="#003366", fg="white").pack(anchor="w")
        tk.Label(title_group, text="Grounded in this comparison result", font=("Segoe UI", 9),
                 bg="#003366", fg="#B8D8FF").pack(anchor="w", pady=(2, 0))

        mode = "Online-Online" if self.viewer.online_context else "Offline"
        ai_state = "AI polish on" if self.engine else "Local agent mode"
        badge = tk.Label(header, text=f"{mode} | {ai_state}", font=("Segoe UI", 10, "bold"),
                         bg="#0F5C8C", fg="white", padx=12, pady=7)
        badge.pack(side="right", padx=18)

        body = tk.Frame(self.window, bg="#ECF2F6")
        body.pack(fill="both", expand=True, padx=12, pady=12)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        sidebar = tk.Frame(body, bg="#DDEAF3", width=250)
        sidebar.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        sidebar.grid_propagate(False)

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
            "What should I inspect next?",
            "Run interface analysis",
            "Open reports folder",
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
            "Show a short diff",
            "Which files are risky?",
            "Save this answer",
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
            state="disabled",
            bg="#FFFFFF",
            fg="#17212B",
            font=("Segoe UI", 10),
            relief="flat",
            padx=18,
            pady=14
        )
        self.chat.grid(row=0, column=0, sticky="nsew")
        self.chat.tag_config("user_label", foreground="#007B3E", font=("Segoe UI", 9, "bold"), spacing1=8)
        self.chat.tag_config("bot_label", foreground="#003366", font=("Segoe UI", 9, "bold"), spacing1=8)
        self.chat.tag_config("user", background="#E8F5E9", lmargin1=24, lmargin2=24, rmargin=110, spacing1=4, spacing3=10)
        self.chat.tag_config("bot", background="#F4F7FB", lmargin1=24, lmargin2=24, rmargin=70, spacing1=4, spacing3=10)
        self.chat.tag_config("system", foreground="#666666", font=("Segoe UI", 9, "italic"), spacing1=6, spacing3=6)
        self.chat.tag_config("code", font=("Consolas", 9), background="#F6F8FA", lmargin1=28, lmargin2=28)

        self.suggestion_frame = tk.Frame(self.window, bg="#ECF2F6")
        self.suggestion_frame.pack(fill="x", padx=12, pady=(0, 8))
        self._render_suggestions([
            "Summarize this comparison",
            "Tell differences for selected file",
            "List modified files",
        ])

        input_frame = tk.Frame(self.window, bg="#ECF2F6")
        input_frame.pack(fill="x", padx=12, pady=(0, 12))

        self.input_var = tk.StringVar()
        self.entry = tk.Entry(input_frame, textvariable=self.input_var, font=("Segoe UI", 11), relief="solid", bd=1)
        self.entry.pack(side="left", fill="x", expand=True, ipady=8)
        self.entry.bind("<Return>", lambda _e: self._ask())

        self.send_btn = tk.Button(
            input_frame,
            text="Ask",
            command=self._ask,
            bg="#007B3E",
            fg="white",
            font=("Segoe UI", 11, "bold"),
            padx=20,
            pady=7,
            relief="flat"
        )
        self.send_btn.pack(side="left", padx=(8, 0))

        self.status_var = tk.StringVar(value="Ready")
        tk.Label(self.window, textvariable=self.status_var, font=("Segoe UI", 8),
                 bg="#ECF2F6", fg="#5C6B73", anchor="w").pack(fill="x", padx=14, pady=(0, 8))

    def _ask(self, prompt=None):
        if self.busy:
            return
        question = (prompt or self.input_var.get()).strip()
        if not question:
            return
        self.input_var.set("")
        self.last_question = question
        self._append_user(question)

        action_reply = self._maybe_run_action(question)
        if action_reply:
            self._append_bot(action_reply)
            self._after_reply(action_reply, question)
            return

        local_context = self._build_context(question)
        self.last_context = local_context
        if not self.engine:
            self._append_bot(local_context)
            self._after_reply(local_context, question)
            return

        self._set_busy(True)

        def worker():
            try:
                reply = self._ask_model(question, local_context)
            except Exception as exc:
                reply = local_context + f"\n\nAI polish unavailable: {exc}"
            self.window.after(0, lambda: self._finish_reply(reply))

        threading.Thread(target=worker, daemon=True).start()

    def _maybe_run_action(self, question):
        q = question.lower()
        if "open" in q and "report" in q:
            self.viewer.open_reports_folder()
            return "Opened the reports folder."
        if "save" in q and ("answer" in q or "chat" in q):
            return self._save_last_answer()
        if ("run" in q or "open" in q or "start" in q) and "interface" in q:
            self.window.after(100, self.viewer.open_interface_analysis_tool)
            return "Starting interface analysis. For online results, I will extract the selected RTC components first."
        if "open" in q and "diff" in q:
            self.viewer.open_diff()
            return "Opened the selected row's HTML diff if one is available."
        if "select" in q and ("changed" in q or "modified" in q or "different" in q):
            return self._select_first_changed_row()
        return None

    def _build_context(self, question):
        match = self._find_best_result(question)
        lowered = question.lower()

        if match:
            return self._describe_result(match, include_diff=True)

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

    def _describe_result(self, row, include_diff=False):
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
            diff = self._make_text_diff(path1, path2)
            if diff:
                lines.append("\nFocused text diff:")
                lines.append(diff)

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

    def _make_text_diff(self, path1, path2):
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
        if len(diff) > 140:
            diff = diff[:140] + ["... diff truncated; open HTML diff for full view.\n"]
        return "```diff\n" + "".join(diff) + "\n```"

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
        try:
            from src.config import settings
            key = getattr(settings, "AOAI_FARM_SUBSCRIPTION_KEY", "")
            if not key:
                return None
            from src.chatbot.chatbot import ChatConfig, ChatEngine
            endpoint_base = getattr(settings, "AOAI_FARM_ENDPOINT", "").rstrip("/")
            deployment = getattr(settings, "AOAI_CHAT_DEPLOYMENT", None) or getattr(settings, "AOAI_FARM_DEPLOYMENT", "")
            api_version = getattr(settings, "AOAI_CHAT_API_VERSION", None) or getattr(settings, "AOAI_FARM_API_VERSION", "")
            endpoint = f"{endpoint_base}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
            cfg = ChatConfig(
                api_key=key,
                endpoint=endpoint,
                # Bosch AOAI GPT-5 chat-completions deployments accept the
                # same minimal body that works in Postman: {"messages": ...}.
                # Legacy params like temperature/max_tokens can produce 400s.
                temperature=None,
                max_tokens=None,
                timeout_sec=90
            )
            return ChatEngine(cfg)
        except Exception:
            return None

    def _ask_model(self, question, local_context):
        system = (
            "You are a migration-analysis assistant inside a desktop comparison tool. "
            "Answer only from the provided comparison context. If the context is insufficient, say exactly what is missing. "
            "Be concise, practical, and mention whether the row is offline file-level data or online component/baseline data."
        )
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": f"User question:\n{question}\n\nComparison/tool context:\n{local_context}"
            }
        ]
        return self.engine.complete(messages)

    def _set_busy(self, busy):
        self.busy = busy
        self.send_btn.config(state="disabled" if busy else "normal")
        self.status_var.set("Thinking..." if busy else "Ready")
        if busy:
            self._append_system("Assistant is thinking...")

    def _finish_reply(self, reply):
        self._set_busy(False)
        self._append_bot(reply)
        self._after_reply(reply, self.last_question)

    def _after_reply(self, reply, question):
        self.last_reply = reply
        self._render_suggestions(self._suggest_followups(question, reply))
        self.status_var.set("Ready")

    def _suggest_followups(self, question, reply):
        q = question.lower()
        suggestions = []
        if "summary" in q or "overview" in q:
            suggestions.extend(["What should I inspect next?", "List modified files", "Run interface analysis"])
        elif "selected" in q or self._find_best_result(question):
            suggestions.extend(["Open selected diff", "Save this answer", "What is the risk?"])
        elif "modified" in q or "changed" in q:
            suggestions.extend(["Tell differences for selected file", "Which files are risky?", "Open reports folder"])
        elif self.viewer.online_context:
            suggestions.extend(["Run interface analysis", "Explain selected component", "List selected components"])
        else:
            suggestions.extend(["Summarize this comparison", "List files only in project", "What should I inspect next?"])
        return suggestions[:4]

    def _render_suggestions(self, suggestions):
        for child in self.suggestion_frame.winfo_children():
            child.destroy()
        tk.Label(self.suggestion_frame, text="Suggested next:", font=("Segoe UI", 9, "bold"),
                 bg="#ECF2F6", fg="#425466").pack(side="left", padx=(0, 8))
        for suggestion in suggestions:
            tk.Button(
                self.suggestion_frame,
                text=suggestion,
                command=lambda s=suggestion: self._ask(s),
                bg="#FFFFFF",
                fg="#003366",
                font=("Segoe UI", 8),
                relief="solid",
                bd=1,
                padx=10,
                pady=4,
                cursor="hand2"
            ).pack(side="left", padx=4)

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
        self._write(text + "\n", "bot")

    def _append_system(self, text):
        self._write("\n" + text + "\n", "system")

    def _write(self, text, tag):
        self.chat.config(state="normal")
        self.chat.insert("end", text, tag)
        self.chat.config(state="disabled")
        self.chat.see("end")
