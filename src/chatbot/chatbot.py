"""
Code Knowledge-Base Chatbot
============================
A conversational AI assistant that uses any source-code file (or plain-text
file) as its knowledge base.  Powered by the Bosch Azure OpenAI Farm.

Layered Architecture (each layer depends only on layers below it)
-----------------------------------------------------------------
  Layer 0 — ChatConfig          dataclass holding all settings; zero deps
  Layer 1 — CodeKnowledgeBase   loads & chunks the source file; pure logic
  Layer 2 — ChatEngine          calls Azure OpenAI via HTTP; pure I/O
  Layer 3 — CodeChatbot         ties KB + engine + history; callback-based
                                 (no UI import — thread-safe for Tkinter)
  Layer 4 — BaseInterface       abstract base class (ABC) for any UI
             ConsoleInterface   terminal REPL; depends only on CodeChatbot
             TkinterChatPanel   fully-implemented Tkinter panel; drop into
                                 any existing Tk root without modification

Usage (terminal)
----------------
  python chatbot.py                          # interactive REPL
  python chatbot.py --kb path/to/code.py     # custom knowledge base
  python chatbot.py --ask "What does X do?"  # single question, then exit
  python chatbot.py --no-proxy               # bypass corporate proxy

Tkinter integration
-------------------
  import tkinter as tk
  from chatbot import ChatConfig, build_chatbot, TkinterChatPanel

  root = tk.Tk()
  cfg  = ChatConfig()                        # or ChatConfig(kb_path=..., api_key=...)
  bot  = build_chatbot(cfg)
  panel = TkinterChatPanel(root, bot)
  panel.pack(fill="both", expand=True)
  root.mainloop()

  # In your existing Tk app — embed the panel in any Frame:
  panel = TkinterChatPanel(my_frame, bot, height=500)
  panel.grid(row=2, column=0, sticky="nsew")
"""

from __future__ import annotations

import abc
import argparse
import json
import os
import queue
import re
import sys
import textwrap
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple


# ===========================================================================
# LAYER 0 — Configuration (pure dataclass, no side-effects)
# ===========================================================================

@dataclass
class ChatConfig:
    """
    All tuneable settings in one place.
    Pass a ChatConfig instance to build_chatbot() to customise behaviour.
    Every field has a sensible default.
    """
    # --- Knowledge base ---
    kb_path: str = field(
        default_factory=lambda: os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "Migration_V2 5.py"
        )
    )
    top_k_sections: int = 6          # KB sections injected per query
    max_section_chars: int = 1_200   # chars per injected section snippet
    max_kb_context_chars: int = 7_000

    # --- Azure OpenAI ---
    api_key: str = field(
        default_factory=lambda: os.environ.get(
            "AOAI_FARM_KEY", "b0791760a2b44168ad31a9971ddb728f"
        )
    )
    endpoint: str = (
        "https://aoai-farm.bosch-temp.com/api/openai/deployments/"
        "askbosch-prod-farm-openai-gpt-4o-mini-2024-07-18/chat/completions"
        "?api-version=2024-08-01-preview"
    )
    temperature: float = 0.3
    max_tokens: int = 1_500
    timeout_sec: int = 90

    # --- Proxy ---
    proxy_url: str = field(
        default_factory=lambda: os.environ.get(
            "HTTPS_PROXY",
            os.environ.get("HTTP_PROXY", "http://rb-proxy-in.bosch.com:8080"),
        )
    )
    proxy_domain: str = field(
        default_factory=lambda: os.environ.get("PROXY_DOMAIN", "BOSCH")
    )
    proxy_user: str = field(
        default_factory=lambda: os.environ.get("PROXY_USER", "")
    )
    proxy_pass: str = field(
        default_factory=lambda: os.environ.get("PROXY_PASS", "")
    )

    # --- Conversation ---
    max_history_turns: int = 8       # past turns kept in the context window


# ===========================================================================
# LAYER 1 — Knowledge Base  (pure logic; only dependency: file I/O)
# ===========================================================================

_RE_FUNC_OR_CLASS = re.compile(
    r"^(def |class |async def )\s*(\w+)",
    re.MULTILINE,
)

_STOP_WORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "but",
    "by", "can", "could", "did", "do", "does", "for", "from", "had",
    "has", "have", "how", "i", "if", "in", "into", "is", "it", "its",
    "may", "might", "not", "of", "on", "or", "shall", "should", "that",
    "the", "this", "through", "to", "was", "we", "were", "what", "when",
    "where", "which", "who", "why", "will", "with", "would", "you",
})


def _tokenize(text: str) -> List[str]:
    return [
        w for w in re.findall(r"\b[a-zA-Z_]\w*\b", text.lower())
        if w not in _STOP_WORDS and len(w) > 1
    ]


class KBSection:
    """One logical section extracted from the knowledge-base file."""

    __slots__ = ("title", "content", "_tf")

    def __init__(self, title: str, content: str) -> None:
        self.title   = title
        self.content = content
        tokens = _tokenize(title + " " + content)
        total  = len(tokens) or 1
        freq   = Counter(tokens)
        self._tf: Dict[str, float] = {w: c / total for w, c in freq.items()}

    def score(self, query_tokens: List[str]) -> float:
        return sum(self._tf.get(t, 0.0) for t in query_tokens)

    def snippet(self, max_chars: int) -> str:
        if len(self.content) <= max_chars:
            return self.content
        half = max_chars // 2
        return self.content[:half] + "\n...[truncated]...\n" + self.content[-half:]


class CodeKnowledgeBase:
    """
    Loads a source/text file and exposes it as searchable sections.

    Splitting strategy (evaluated in order):
      1. Comment-banner blocks  ( # -----\\n# Title\\n# ----- )
      2. Top-level def / class definitions
      3. Fixed 80-line chunks (fallback)
    """

    def __init__(self, cfg: ChatConfig) -> None:
        self._cfg = cfg
        self.file_path = cfg.kb_path
        self.sections:  List[KBSection] = []
        self._overview: str = ""
        self._load()

    # ── public ───────────────────────────────────────────────────────────────

    def search(self, query: str) -> List[KBSection]:
        tokens = _tokenize(query)
        if not tokens:
            return []
        scored = sorted(
            ((s.score(tokens), s) for s in self.sections),
            key=lambda x: -x[0],
        )
        # Return top-k sections regardless of score so general queries still get context
        return [s for _, s in scored][: self._cfg.top_k_sections]

    def build_context(self, query: str) -> str:
        """Return concatenated snippets from the most relevant sections."""
        parts, used = [], 0
        for sec in self.search(query):
            snip = sec.snippet(self._cfg.max_section_chars)
            if used + len(snip) > self._cfg.max_kb_context_chars:
                remaining = self._cfg.max_kb_context_chars - used
                if remaining > 200:
                    snip = snip[:remaining] + "\n...[cut]..."
                else:
                    break
            parts.append(f"### {sec.title}\n{snip}")
            used += len(snip)
        return "\n\n".join(parts)

    @property
    def overview(self) -> str:
        return self._overview

    @property
    def total_sections(self) -> int:
        return len(self.sections)

    # ── private ──────────────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            with open(self.file_path, "r", encoding="utf-8", errors="replace") as fh:
                raw = fh.read()
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Knowledge-base file not found: {self.file_path}\n"
                "Set ChatConfig(kb_path=...) to point at a valid file."
            )
        self._overview = self._make_overview(raw)
        self.sections  = self._split(raw)

    def _make_overview(self, raw: str) -> str:
        lines = raw.splitlines()
        docstring = ""
        if lines and lines[0].startswith('"""'):
            end = next((i for i, ln in enumerate(lines[1:], 1) if '"""' in ln), -1)
            if end > 0:
                docstring = "\n".join(lines[: end + 1])
        defs     = _RE_FUNC_OR_CLASS.findall(raw)
        def_list = "\n".join(f"  {kw}{name}" for kw, name in defs[:60])
        if len(defs) > 60:
            def_list += f"\n  ... and {len(defs) - 60} more"
        return (
            f"File: {os.path.basename(self.file_path)}\n"
            f"Size: {len(lines)} lines\n\n"
            + (docstring + "\n\n" if docstring else "")
            + f"Top-level functions / classes:\n{def_list}"
        )

    def _split(self, raw: str) -> List[KBSection]:
        # Strategy 1: banner comments
        banner = re.compile(
            r"(?m)^# -{10,}\s*\n# (.+?)\n# -{10,}"
        )
        positions: List[Tuple[int, str]] = [
            (m.start(), m.group(1).strip()) for m in banner.finditer(raw)
        ]
        if positions:
            positions.append((len(raw), "__END__"))
            return [
                KBSection(title, raw[start: positions[i + 1][0]].strip())
                for i, (start, title) in enumerate(positions[:-1])
                if raw[start: positions[i + 1][0]].strip()
            ]

        # Strategy 2: top-level def / class
        func_pos: List[Tuple[int, str]] = [
            (m.start(), m.group(1).strip() + " " + m.group(2))
            for m in re.finditer(r"^(def |class |async def )(\w+)", raw, re.MULTILINE)
        ]
        if func_pos:
            func_pos.append((len(raw), "__END__"))
            return [
                KBSection(name, raw[start: func_pos[i + 1][0]].strip())
                for i, (start, name) in enumerate(func_pos[:-1])
                if raw[start: func_pos[i + 1][0]].strip()
            ]

        # Fallback: 80-line chunks
        lines = raw.splitlines()
        return [
            KBSection(
                f"Lines {i + 1}\u2013{min(i + 80, len(lines))}",
                "\n".join(lines[i: i + 80]),
            )
            for i in range(0, len(lines), 80)
        ]


# ===========================================================================
# LAYER 2 — Chat Engine  (pure HTTP; depends only on ChatConfig)
# ===========================================================================

class ChatEngine:
    """
    Thin HTTP wrapper around the Azure OpenAI chat-completions endpoint.
    No openai SDK required.

    Thread-safety: each call is stateless; the internal requests.Session is
    created once and reused (requests.Session IS thread-safe for concurrent
    reads once headers/proxies are set).
    """

    def __init__(self, cfg: ChatConfig) -> None:
        self._cfg     = cfg
        self._session = None   # lazy-initialised

    # ── public ───────────────────────────────────────────────────────────────

    def complete(self, messages: List[Dict]) -> str:
        """
        POST a messages list to the model, return the assistant text.
        Raises RuntimeError on any HTTP / network failure.
        """
        payload = json.dumps({
            "messages":    messages,
            "temperature": self._cfg.temperature,
            "max_tokens":  self._cfg.max_tokens,
        }).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "api-key":      self._cfg.api_key,
        }

        try:
            resp = self._session_().post(
                self._cfg.endpoint,
                data=payload,
                headers=headers,
                timeout=self._cfg.timeout_sec,
                verify=True,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            raise RuntimeError(f"Azure OpenAI request failed: {exc}") from exc

    # ── private ──────────────────────────────────────────────────────────────

    def _session_(self):
        if self._session is not None:
            return self._session
        try:
            import requests  # type: ignore
        except ImportError:
            raise ImportError("pip install requests")

        sess = requests.Session()
        if self._cfg.proxy_url and self._cfg.proxy_url.strip():
            proxies = {
                "http":  self._cfg.proxy_url,
                "https": self._cfg.proxy_url,
            }
            try:
                from requests_ntlm import HttpNtlmAuth  # type: ignore
                import getpass
                user = self._cfg.proxy_user or getpass.getuser()
                pw   = self._cfg.proxy_pass
                if pw:
                    sess.auth = HttpNtlmAuth(
                        f"{self._cfg.proxy_domain}\\{user}", pw
                    )
            except ImportError:
                pass  # run without NTLM if requests-ntlm not installed
            sess.proxies.update(proxies)

        self._session = sess
        return sess


# ===========================================================================
# LAYER 3 — CodeChatbot  (business logic; NO UI dependency)
# ===========================================================================

_SYSTEM_PROMPT = """\
You are an expert software-engineering assistant with deep knowledge of the
code-base described below.

=== KNOWLEDGE BASE OVERVIEW ===
{overview}

Rules:
• Cite function/class/section names from the code in your answers.
• Use code blocks (``` ```) for any code snippets.
• If the answer is not in the provided context, say so — do not hallucinate.
• For dependency questions answer: what this code depends on AND what depends
  on it.
• For logic questions trace the control flow step-by-step.
"""


class CodeChatbot:
    """
    Application layer: ties KB + engine + history together.

    Designed for interface independence:
    • Synchronous API:   reply = bot.chat(message)
    • Async/callback API: bot.chat_async(message, on_reply, on_error)
      — runs the network call on a daemon thread; safe to call from
        Tkinter's main thread without freezing the UI.

    Public API
    ----------
    chat(msg)                          → str   (blocking)
    chat_async(msg, on_reply, on_error) → None  (non-blocking)
    reset()                            → None
    history                            → List[Dict]
    turn_count                         → int
    kb                                 → CodeKnowledgeBase
    engine                             → ChatEngine
    """

    def __init__(
        self,
        kb:     CodeKnowledgeBase,
        engine: ChatEngine,
        cfg:    ChatConfig,
    ) -> None:
        self._kb     = kb
        self._engine = engine
        self._cfg    = cfg
        self._lock   = threading.Lock()
        self._history: List[Dict] = []
        self._sys_msg = {
            "role":    "system",
            "content": _SYSTEM_PROMPT.format(overview=kb.overview),
        }

    # ── synchronous ──────────────────────────────────────────────────────────

    def chat(self, user_message: str) -> str:
        """
        Blocking call.  Returns the assistant reply.
        Thread-safe: acquires an internal lock so concurrent callers queue up.
        """
        with self._lock:
            return self._do_chat(user_message)

    # ── async / callback (for Tkinter — keeps the UI responsive) ─────────────

    def chat_async(
        self,
        user_message: str,
        on_reply: Callable[[str], None],
        on_error: Callable[[str], None],
    ) -> None:
        """
        Non-blocking.  The network call runs on a daemon thread.
        on_reply(reply_text) and on_error(error_text) are called from
        that thread — schedule them onto the Tk main loop with
        root.after(0, callback) inside your TkinterChatPanel.
        """
        def _worker() -> None:
            try:
                reply = self._do_chat(user_message)
                on_reply(reply)
            except Exception as exc:
                on_error(str(exc))

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    # ── state management ─────────────────────────────────────────────────────

    def reset(self) -> None:
        with self._lock:
            self._history.clear()

    @property
    def history(self) -> List[Dict]:
        with self._lock:
            return list(self._history)

    @property
    def turn_count(self) -> int:
        with self._lock:
            return len(self._history) // 2

    @property
    def kb(self) -> CodeKnowledgeBase:
        return self._kb

    @property
    def engine(self) -> ChatEngine:
        return self._engine

    # ── private ──────────────────────────────────────────────────────────────

    def _do_chat(self, user_message: str) -> str:
        kb_context = self._kb.build_context(user_message)
        # Always call the AI — use overview as fallback so greetings/general
        # questions still get a helpful answer instead of "I'm sorry".
        if kb_context:
            context_block = f"--- Relevant code sections ---\n{kb_context}"
        else:
            context_block = f"--- Knowledge base overview ---\n{self._kb.overview}"

        augmented = f"{user_message}\n\n{context_block}"
        window = self._history[-(self._cfg.max_history_turns * 2):]
        messages = [self._sys_msg] + window + [
            {"role": "user", "content": augmented}
        ]
        reply = self._engine.complete(messages)
        self._history.append({"role": "user", "content": user_message})
        self._history.append({"role": "assistant", "content": reply})
        return reply


# ===========================================================================
# LAYER 4a — BaseInterface  (abstract contract for any UI)
# ===========================================================================

class BaseInterface(abc.ABC):
    """
    Abstract base for all UI implementations.
    Depends only on CodeChatbot — never on any specific UI toolkit.
    """

    def __init__(self, chatbot: CodeChatbot) -> None:
        self.bot = chatbot

    @abc.abstractmethod
    def run(self, **kwargs) -> None:
        """Start the interface (blocking for console, non-blocking for GUI)."""

    def handle_command(self, text: str) -> Optional[str]:
        """
        Process /slash commands shared by all interfaces.
        Returns a response string, or None if it was not a command.
        """
        cmd = text.strip().lower()
        if cmd in ("/reset", "reset"):
            self.bot.reset()
            return "[Conversation history cleared.]"
        if cmd in ("/kb", "kb"):
            return f"--- Knowledge Base Overview ---\n{self.bot.kb.overview}"
        if cmd == "/sections":
            lines = [f"  {i:3}. {s.title[:80]}"
                     for i, s in enumerate(self.bot.kb.sections, 1)]
            return (
                f"--- {self.bot.kb.total_sections} Sections ---\n"
                + "\n".join(lines)
            )
        if cmd in ("/help", "help"):
            return (
                "Commands:  /reset  /kb  /sections  /help  /exit\n"
                "Or just type your question."
            )
        return None  # not a command


# ===========================================================================
# LAYER 4b — ConsoleInterface  (terminal REPL)
# ===========================================================================

_CONSOLE_BANNER = (
    "\u2554" + "\u2550" * 62 + "\u2557\n"
    "\u2551   CODE KNOWLEDGE-BASE CHATBOT"
    "                               \u2551\n"
    "\u2551   Powered by Azure OpenAI (GPT-4o-mini)"
    "                    \u2551\n"
    "\u255a" + "\u2550" * 62 + "\u255d"
)


class ConsoleInterface(BaseInterface):
    """
    Terminal REPL.  Depends only on CodeChatbot (via BaseInterface).
    No tkinter import anywhere in this class.
    """

    def run(self, single_question: Optional[str] = None, **kwargs) -> None:
        print(_CONSOLE_BANNER)
        print(f"\n  KB file  : {self.bot.kb.file_path}")
        print(f"  Sections : {self.bot.kb.total_sections}")
        print(f"  Endpoint : ...{self.bot.engine._cfg.endpoint[-55:]}\n")

        if single_question:
            self._ask(single_question)
            return

        print("  Type your question. Commands: /reset /kb /sections /help /exit\n")

        while True:
            try:
                raw = input("You: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\n[Bye!]")
                break

            if not raw:
                continue
            if raw.lower() in ("/exit", "/quit", "exit", "quit"):
                print("[Bye!]")
                break

            response = self.handle_command(raw)
            if response is not None:
                print(f"\n{response}\n")
                continue

            self._ask(raw)

    # ── private ──────────────────────────────────────────────────────────────

    def _ask(self, text: str) -> None:
        print("\nBot: [thinking…]", flush=True)
        t0 = time.time()
        result_q: queue.Queue = queue.Queue()

        def on_reply(r: str)  -> None: result_q.put(("ok",  r))
        def on_error(e: str)  -> None: result_q.put(("err", e))

        self.bot.chat_async(text, on_reply, on_error)

        # Block the console thread until the worker thread delivers
        kind, payload = result_q.get()
        elapsed = time.time() - t0
        print("\r" + " " * 30 + "\r", end="")

        if kind == "ok":
            print("Bot:", _wrap_text(payload))
            print(f"     ({elapsed:.1f}s | turn {self.bot.turn_count})")
        else:
            print(f"[Error] {payload}")
        print()


def _wrap_text(text: str, width: int = 100, indent: str = "     ") -> str:
    parts = []
    for line in text.split("\n"):
        parts.extend(
            textwrap.wrap(line, width=width, subsequent_indent=indent)
            if len(line) > width else [line]
        )
    return "\n".join(parts)


# ===========================================================================
# LAYER 4c — TkinterChatPanel  (embeddable Tk widget)
# Depends only on tkinter + CodeChatbot.  Zero coupling to Migration_V2 5.py.
# ===========================================================================

class TkinterChatPanel:
    """
    A self-contained Tkinter chat panel that embeds into any Tk root or Frame.

    Usage
    -----
    Standalone window:
        root  = tk.Tk()
        panel = TkinterChatPanel(root, bot)
        panel.pack(fill="both", expand=True)
        root.mainloop()

    Embedded in existing app:
        panel = TkinterChatPanel(my_notebook_tab, bot, height=500)
        panel.grid(row=0, column=0, sticky="nsew")

    The panel uses bot.chat_async() so the UI never freezes during API calls.
    """

    # Colour scheme (Bosch-style, matches Migration_V2 5.py)
    _C_BG       = "#EAF3FB"
    _C_HEADER   = "#003366"
    _C_ACCENT   = "#007B3E"
    _C_ERROR    = "#C62828"
    _C_USER_BG  = "#DCF8C6"   # light green bubble
    _C_BOT_BG   = "#FFFFFF"   # white bubble
    _C_THINKING = "#FFF9C4"   # yellow thinking indicator

    def __init__(
        self,
        parent,                      # tk.Tk or tk.Frame or ttk.Frame
        chatbot: CodeChatbot,
        height: int = 600,
        width:  int = 800,
    ) -> None:
        # ── import tkinter here, not at the top — keeps the module importable
        #    even in headless environments (e.g. CI / console-only servers)
        import tkinter as tk
        from tkinter import ttk, scrolledtext

        self._bot    = chatbot
        self._tk     = tk
        self._parent = parent
        self._busy   = False   # True while waiting for API response

        # ── outer frame (this is what callers pack/grid) ─────────────────────
        self.frame = tk.Frame(parent, bg=self._C_BG)

        # ── header ───────────────────────────────────────────────────────────
        hdr = tk.Frame(self.frame, bg=self._C_HEADER, height=40)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(
            hdr,
            text="\U0001f916  Code Assistant  \u2014  "
                 f"{os.path.basename(chatbot.kb.file_path)}  "
                 f"({chatbot.kb.total_sections} sections)",
            font=("Segoe UI", 10, "bold"),
            bg=self._C_HEADER, fg="white",
        ).pack(side="left", padx=12, pady=8)

        # reset button
        tk.Button(
            hdr,
            text="Clear chat",
            command=self._on_reset,
            bg="#1A5276", fg="white",
            font=("Segoe UI", 8),
            relief="flat", cursor="hand2",
        ).pack(side="right", padx=8, pady=6)

        # ── chat display (scrolled text, read-only) ───────────────────────────
        self._chat_area = scrolledtext.ScrolledText(
            self.frame,
            state="disabled",
            wrap="word",
            bg=self._C_BG,
            font=("Segoe UI", 10),
            relief="flat",
            padx=10, pady=8,
            height=height // 22,
        )
        self._chat_area.pack(fill="both", expand=True, padx=4, pady=(4, 0))

        # Tag styles for message bubbles
        self._chat_area.tag_config(
            "user_label",  font=("Segoe UI", 9, "bold"),  foreground=self._C_ACCENT
        )
        self._chat_area.tag_config(
            "user_text",   background=self._C_USER_BG, font=("Segoe UI", 10),
            lmargin1=20, lmargin2=20, rmargin=80,
        )
        self._chat_area.tag_config(
            "bot_label",   font=("Segoe UI", 9, "bold"),  foreground=self._C_HEADER
        )
        self._chat_area.tag_config(
            "bot_text",    background=self._C_BOT_BG, font=("Segoe UI", 10),
            lmargin1=20, lmargin2=20, rmargin=80,
        )
        self._chat_area.tag_config(
            "thinking",    background=self._C_THINKING, font=("Segoe UI", 10, "italic"),
            foreground="#555555", lmargin1=20,
        )
        self._chat_area.tag_config(
            "error_text",  foreground=self._C_ERROR, font=("Segoe UI", 10, "italic"),
            lmargin1=20,
        )
        self._chat_area.tag_config(
            "sep",         foreground="#CCCCCC",
        )

        # ── status bar ────────────────────────────────────────────────────────
        self._status_var = tk.StringVar(value="Ready")
        tk.Label(
            self.frame,
            textvariable=self._status_var,
            bg=self._C_BG, fg="#555555",
            font=("Segoe UI", 8, "italic"),
            anchor="w",
        ).pack(fill="x", padx=8)

        # ── input row ────────────────────────────────────────────────────────
        inp_frame = tk.Frame(self.frame, bg=self._C_BG)
        inp_frame.pack(fill="x", padx=4, pady=(2, 6))

        self._input_var = tk.StringVar()
        self._entry = tk.Entry(
            inp_frame,
            textvariable=self._input_var,
            font=("Segoe UI", 11),
            relief="solid", bd=1,
        )
        self._entry.pack(side="left", fill="x", expand=True, ipady=6)
        self._entry.bind("<Return>",       self._on_send)
        self._entry.bind("<KP_Enter>",     self._on_send)
        self._entry.focus_set()

        self._send_btn = tk.Button(
            inp_frame,
            text="Send",
            command=self._on_send,
            bg=self._C_ACCENT, fg="white",
            font=("Segoe UI", 10, "bold"),
            relief="flat", cursor="hand2",
            padx=16, pady=6,
        )
        self._send_btn.pack(side="left", padx=(6, 0))

        # kb info button
        tk.Button(
            inp_frame,
            text="KB",
            command=self._on_show_kb,
            bg="#1A5276", fg="white",
            font=("Segoe UI", 10),
            relief="flat", cursor="hand2",
            padx=8, pady=6,
        ).pack(side="left", padx=(4, 0))

        # ── welcome message ───────────────────────────────────────────────────
        self._append_bot(
            f"Hello! I'm your code assistant for "
            f"**{os.path.basename(chatbot.kb.file_path)}**. "
            f"I have indexed {chatbot.kb.total_sections} sections.\n\n"
            f"Try asking:\n"
            f"  • What does this tool do?\n"
            f"  • How does the migration analysis work?\n"
            f"  • What is generate_purpose_of_change?\n"
            f"  • How are XML files compared?\n"
            f"  • What RTC functions are available?"
        )

        # reference to the root window (needed for root.after scheduling)
        self._root = self._find_root(parent)

    # ── public: pack/grid/place forwarded to the outer frame ─────────────────

    def pack(self, **kwargs)  -> None: self.frame.pack(**kwargs)
    def grid(self, **kwargs)  -> None: self.frame.grid(**kwargs)
    def place(self, **kwargs) -> None: self.frame.place(**kwargs)

    # ── event handlers ────────────────────────────────────────────────────────

    def _on_send(self, event=None) -> None:
        if self._busy:
            return
        text = self._input_var.get().strip()
        if not text:
            return
        self._input_var.set("")

        # Check for /commands via BaseInterface logic
        # (replicate handle_command without inheriting, to keep panel self-contained)
        cmd = text.lower()
        if cmd in ("/reset", "reset"):
            self._bot.reset()
            self._append_system("[Conversation history cleared.]")
            return
        if cmd in ("/kb", "kb"):
            self._append_system(self._bot.kb.overview)
            return
        if cmd == "/sections":
            lines = [f"  {i:3}. {s.title}"
                     for i, s in enumerate(self._bot.kb.sections, 1)]
            self._append_system("\n".join(lines))
            return

        # Normal question
        self._append_user(text)
        self._set_thinking(True)
        self._status_var.set("Thinking…")

        def on_reply(reply: str) -> None:
            # Schedule onto Tk main thread  ← KEY for thread safety
            self._root.after(0, self._deliver_reply, reply)

        def on_error(err: str) -> None:
            self._root.after(0, self._deliver_error, err)

        self._bot.chat_async(text, on_reply, on_error)

    def _on_reset(self) -> None:
        self._bot.reset()
        self._clear_chat()
        self._append_bot("Chat history cleared. Ask me anything!")

    def _on_show_kb(self) -> None:
        self._append_system(self._bot.kb.overview)

    def _deliver_reply(self, reply: str) -> None:
        self._set_thinking(False)
        self._append_bot(reply)
        self._status_var.set(f"Ready  (turn {self._bot.turn_count})")

    def _deliver_error(self, err: str) -> None:
        self._set_thinking(False)
        self._append_error(f"Error: {err}")
        self._status_var.set("Error — check connection / API key")

    # ── helpers ───────────────────────────────────────────────────────────────

    def _append_user(self, text: str) -> None:
        self._write("\nYou\n",   "user_label")
        self._write(text + "\n", "user_text")
        self._write("\n",        "sep")

    def _append_bot(self, text: str) -> None:
        self._write("\nAssistant\n", "bot_label")
        self._write(text + "\n",     "bot_text")
        self._write("\n",            "sep")

    def _append_system(self, text: str) -> None:
        self._write("\n" + text + "\n\n", "thinking")

    def _append_error(self, text: str) -> None:
        self._write("\n" + text + "\n\n", "error_text")

    def _set_thinking(self, on: bool) -> None:
        self._busy = on
        self._send_btn.config(state="disabled" if on else "normal")
        if on:
            self._write("\nAssistant is thinking…\n", "thinking")
        self._chat_area.see(self._tk.END)

    def _clear_chat(self) -> None:
        self._chat_area.config(state="normal")
        self._chat_area.delete("1.0", self._tk.END)
        self._chat_area.config(state="disabled")

    def _write(self, text: str, tag: str) -> None:
        self._chat_area.config(state="normal")
        self._chat_area.insert(self._tk.END, text, tag)
        self._chat_area.config(state="disabled")
        self._chat_area.see(self._tk.END)

    @staticmethod
    def _find_root(widget) -> object:
        """Walk up parent chain until we reach the Tk root."""
        w = widget
        while True:
            parent = w.master if hasattr(w, "master") else None
            if parent is None:
                return w
            w = parent


# ===========================================================================
# Factory  (wires all layers together from a single ChatConfig)
# ===========================================================================

def build_chatbot(cfg: Optional[ChatConfig] = None) -> CodeChatbot:
    """
    Build and return a ready-to-use CodeChatbot from a ChatConfig.

    Quick start:
        bot = build_chatbot()                          # all defaults
        bot = build_chatbot(ChatConfig(kb_path=...))   # custom KB
    """
    if cfg is None:
        cfg = ChatConfig()
    kb     = CodeKnowledgeBase(cfg)
    engine = ChatEngine(cfg)
    return CodeChatbot(kb, engine, cfg)


# ===========================================================================
# CLI entry point
# ===========================================================================

def main() -> None:
    # Resolve ChatConfig default before argparse so --kb default shows correctly
    _default_cfg = ChatConfig()

    parser = argparse.ArgumentParser(
        description="Code Knowledge-Base Chatbot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--kb",
        default=_default_cfg.kb_path,
        metavar="FILE",
        help="Source file to use as knowledge base",
    )
    parser.add_argument(
        "--key",
        default=None,
        metavar="API_KEY",
        help="Azure OpenAI api-key (overrides env var AOAI_FARM_KEY)",
    )
    parser.add_argument(
        "--endpoint",
        default=None,
        metavar="URL",
        help="Full Azure OpenAI chat-completions endpoint URL",
    )
    parser.add_argument(
        "--no-proxy",
        action="store_true",
        help="Disable corporate proxy",
    )
    parser.add_argument(
        "--ask",
        default=None,
        metavar="QUESTION",
        help="Ask a single question and exit (non-interactive)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=None,
        metavar="N",
        help="KB sections to inject per query",
    )
    parser.add_argument(
        "--history",
        type=int,
        default=None,
        metavar="N",
        help="Past conversation turns to keep in context",
    )
    parser.add_argument(
        "--tkinter",
        action="store_true",
        help="Launch the Tkinter chat panel instead of the console",
    )

    args = parser.parse_args()

    cfg = ChatConfig(kb_path=args.kb)
    if args.key:
        cfg.api_key = args.key
    if args.endpoint:
        cfg.endpoint = args.endpoint
    if args.no_proxy:
        cfg.proxy_url = ""
    if args.top_k is not None:
        cfg.top_k_sections = args.top_k
    if args.history is not None:
        cfg.max_history_turns = args.history

    try:
        bot = build_chatbot(cfg)
    except FileNotFoundError as exc:
        print(f"[!] {exc}")
        sys.exit(1)

    if args.tkinter:
        # ── Tkinter standalone window ────────────────────────────────────────
        import tkinter as tk
        root = tk.Tk()
        root.title("Code Knowledge-Base Chatbot")
        root.geometry("900x680")
        root.configure(bg="#EAF3FB")
        panel = TkinterChatPanel(root, bot, height=680)
        panel.pack(fill="both", expand=True)
        root.mainloop()
    else:
        # ── Console REPL ─────────────────────────────────────────────────────
        ui = ConsoleInterface(bot)
        ui.run(single_question=args.ask)


if __name__ == "__main__":
    main()
