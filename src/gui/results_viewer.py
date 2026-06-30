"""
Enhanced Results viewer dialog - Interactive comparison results with AI features
Complete implementation with copy, edit, AI suggest, and AI merge capabilities
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import webbrowser
import shutil
import tempfile
import logging
import subprocess
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


class ToolTip:
    """Simple tooltip helper"""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        widget.bind("<Enter>", self.showtip)
        widget.bind("<Leave>", self.hidetip)
    
    def showtip(self, event=None):
        if self.tipwindow or not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + 20
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(tw, text=self.text, background="#FFFFE0", relief="solid", borderwidth=1,
                font=("Segoe UI", 8)).pack(ipadx=1, ipady=1)
    
    def hidetip(self, event=None):
        if self.tipwindow:
            self.tipwindow.destroy()
            self.tipwindow = None


class ComparisonResultsDialog:
    """
    Interactive results viewer dialog with full features:
    - Color-coded file list with filters
    - Copy files between folders (F1→F2, F2→F1)
    - AI Suggest (which version to keep)
    - AI Smart Merge (Azure OpenAI Farm)
    - File editor tabs
    - View HTML diffs
    """
    
    def __init__(self, parent, results, folder1_display, folder2_display, 
                 folder1_actual, folder2_actual, files1, files2, report_paths):
        """
        Initialize the enhanced results dialog.
        
        Args:
            parent: Parent window
            results: List of comparison results
            folder1_display: Display name for folder 1
            folder2_display: Display name for folder 2
            folder1_actual: Actual path to folder 1
            folder2_actual: Actual path to folder 2
            files1: Dict of files in folder 1 {rel_path: abs_path}
            files2: Dict of files in folder 2 {rel_path: abs_path}
            report_paths: Dict with 'csv', 'excel', 'output_dir' paths
        """
        self.results = results
        self.folder1_display = folder1_display
        self.folder2_display = folder2_display
        self.folder1_actual = folder1_actual
        self.folder2_actual = folder2_actual
        self.files1 = files1
        self.files2 = files2
        self.report_paths = report_paths
        self.online_context = report_paths.get('online_context', {}) if isinstance(report_paths, dict) else {}
        
        # Current selection state
        self.current_file = None
        self.current_status = None
        self.current_path1 = None
        self.current_path2 = None
        
        # Create dialog
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Comparison Results - Interactive Viewer with AI")
        self.dialog.geometry("1600x1000")
        self.dialog.configure(bg="#f0f4f7")
        self.dialog.grab_set()  # Modal
        
        self.create_ui()
        self.populate_results()
    
    def create_ui(self):
        """Create the UI components"""
        # Header with AI status
        header = tk.Frame(self.dialog, bg="#003366", height=60)
        header.pack(fill="x")
        header.pack_propagate(False)
        
        tk.Label(
            header,
            text="📊 Comparison Results - Interactive Viewer with AI Features",
            font=("Segoe UI", 14, "bold"),
            bg="#003366",
            fg="white"
        ).pack(pady=15)
        
        # AI Status bar
        self.create_ai_status_bar()
        
        # Statistics bar
        self.create_stats_bar()
        
        # Action buttons bar (moved to top for visibility)
        button_frame = self.create_bottom_buttons()
        button_frame.pack(fill="x", padx=10, pady=5, expand=False)
        
        # CONTAINER FRAME for main content (expands to fill available space)
        content_container = tk.Frame(self.dialog, bg="white")
        content_container.pack(fill="both", expand=True, padx=8, pady=5)
        
        # Main paned window (left: file list, right: editor/actions) - inside container
        main_paned = tk.PanedWindow(content_container, orient="horizontal", 
                                    bg="#b0bec5", sashwidth=5, sashrelief="raised")
        main_paned.pack(fill="both", expand=True)
        
        # LEFT PANE: File list
        left_pane = self.create_file_list_pane()
        main_paned.add(left_pane, minsize=600)
        
        # RIGHT PANE: Actions and editor
        right_pane = self.create_action_pane()
        main_paned.add(right_pane, minsize=700)
    
    def create_ai_status_bar(self):
        """Create AI status indicator bar"""
        from src.config import settings

        aoai_ready = bool(
            hasattr(settings, 'AOAI_FARM_SUBSCRIPTION_KEY')
            and settings.AOAI_FARM_SUBSCRIPTION_KEY
            and str(settings.AOAI_FARM_SUBSCRIPTION_KEY).strip().lower() != "none"
        )
        openai_ready = bool(hasattr(settings, 'OPENAI_API_KEY') and 
                           settings.OPENAI_API_KEY and 
                           settings.OPENAI_API_KEY.strip().startswith("sk-"))

        ai_bar = tk.Frame(self.dialog, bg="#1B5E20" if aoai_ready else "#B71C1C", height=28)
        ai_bar.pack(fill="x")
        ai_bar.pack_propagate(False)

        aoai_status = "Azure OpenAI Farm ✔ READY" if aoai_ready else "Azure OpenAI Farm ✘ Key not set"
        openai_status = "OpenAI GPT-4o-mini ✔ READY" if openai_ready else "OpenAI (heuristics only)"
        
        tk.Label(
            ai_bar,
            text=f"  🤖 AI Features:  {aoai_status}  |  {openai_status}",
            font=("Segoe UI", 8, "bold"),
            bg="#1B5E20" if aoai_ready else "#B71C1C",
            fg="white"
        ).pack(side="left", padx=12, pady=5)
    
    def create_stats_bar(self):
        """Create statistics bar"""
        total = len(self.results)
        identical = sum(1 for r in self.results if r[4] == "Identical")
        different = sum(1 for r in self.results if r[4] == "Different")
        comments = sum(1 for r in self.results if r[4] == "Comments update only")
        only1 = sum(1 for r in self.results if r[4] == "Only in Platform")
        only2 = sum(1 for r in self.results if r[4] == "Only in Project")
        errors = sum(1 for r in self.results if r[4] == "Error")
        
        stats_frame = tk.Frame(self.dialog, bg="#E3F2FD", height=40)
        stats_frame.pack(fill="x")
        stats_frame.pack_propagate(False)
        
        stats_text = (
            f"Total: {total}   |   "
            f"Identical: {identical}   |   "
            f"Modified: {different}   |   "
            f"Comments Only: {comments}   |   "
            f"Only in Platform: {only1}   |   "
            f"Only in Project: {only2}"
        )
        
        if errors > 0:
            stats_text += f"   |   Errors: {errors}"
        
        tk.Label(
            stats_frame,
            text=stats_text,
            font=("Segoe UI", 9, "bold"),
            bg="#E3F2FD",
            fg="#003366"
        ).pack(side="left", padx=15, pady=10)
    
    def create_file_list_pane(self):
        """Create left pane with file list"""
        left_frame = tk.Frame(self.dialog, bg="#ffffff")
        
        # Header
        tk.Label(
            left_frame,
            text=" Compared Files",
            font=("Segoe UI", 10, "bold"),
            bg="#003366",
            fg="white",
            anchor="w"
        ).pack(fill="x")
        
        # Info labels
        info_frame = tk.Frame(left_frame, bg="white")
        info_frame.pack(fill="x", padx=5, pady=5)
        
        tk.Label(
            info_frame,
            text=f"Platform: {self.folder1_display}",
            font=("Segoe UI", 9, "bold"),
            bg="white",
            fg="#003366"
        ).pack(anchor="w")
        
        tk.Label(
            info_frame,
            text=f"Project: {self.folder2_display}",
            font=("Segoe UI", 9, "bold"),
            bg="white",
            fg="#003366"
        ).pack(anchor="w")
        
        # Filter frame
        filter_frame = tk.Frame(left_frame, bg="white")
        filter_frame.pack(fill="x", padx=5, pady=5)
        
        tk.Label(
            filter_frame,
            text="Filter:",
            font=("Segoe UI", 9),
            bg="white"
        ).pack(side="left", padx=5)
        
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", self.on_filter_change)
        
        tk.Entry(
            filter_frame,
            textvariable=self.filter_var,
            font=("Segoe UI", 9),
            width=25
        ).pack(side="left", padx=5)
        
        tk.Label(
            filter_frame,
            text="Status:",
            font=("Segoe UI", 9),
            bg="white"
        ).pack(side="left", padx=(10, 5))
        
        self.status_filter = tk.StringVar(value="All")
        status_options = ["All", "Different", "Identical", "Only in Platform", 
                         "Only in Project", "Comments update only", "Error"]
        
        status_combo = ttk.Combobox(
            filter_frame,
            textvariable=self.status_filter,
            values=status_options,
            state="readonly",
            width=20,
            font=("Segoe UI", 9)
        )
        status_combo.pack(side="left", padx=5)
        status_combo.bind("<<ComboboxSelected>>", self.on_filter_change)
        
        # Tree view
        tree_frame = tk.Frame(left_frame, bg="white")
        tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        vsb = tk.Scrollbar(tree_frame, orient="vertical")
        hsb = tk.Scrollbar(tree_frame, orient="horizontal")
        
        columns = ("File Path", "Status", "Lines F1", "Lines F2")
        self.tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set
        )
        
        vsb.config(command=self.tree.yview)
        hsb.config(command=self.tree.xview)
        
        self.tree.heading("File Path", text="File Path")
        self.tree.heading("Status", text="Status")
        self.tree.heading("Lines F1", text="Lines F1")
        self.tree.heading("Lines F2", text="Lines F2")
        
        self.tree.column("File Path", width=350, anchor="w")
        self.tree.column("Status", width=180, anchor="center")
        self.tree.column("Lines F1", width=80, anchor="center")
        self.tree.column("Lines F2", width=80, anchor="center")
        
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        
        # Color tags
        self.tree.tag_configure("identical", background="#C8E6C9", foreground="#1B5E20")
        self.tree.tag_configure("different", background="#FFF9C4", foreground="#827717")
        self.tree.tag_configure("only1", background="#BBDEFB", foreground="#0D47A1")
        self.tree.tag_configure("only2", background="#FFE0B2", foreground="#BF360C")
        self.tree.tag_configure("comments", background="#E8F5E9", foreground="#2E7D32")
        self.tree.tag_configure("error", background="#FFCDD2", foreground="#B71C1C")
        
        # Bind selection
        self.tree.bind("<<TreeviewSelect>>", self.on_file_select)
        self.tree.bind("<Double-Button-1>", self.on_tree_double_click)
        
        return left_frame
    
    def create_action_pane(self):
        """Create right pane with actions and editor"""
        right_frame = tk.Frame(self.dialog, bg="#f8f9fa")
        
        # Selection info label
        self.selection_label = tk.Label(
            right_frame,
            text="Select a file from the list to view details and take actions",
            font=("Segoe UI", 10),
            bg="#f8f9fa",
            fg="#666666",
            wraplength=650,
            justify="left"
        )
        self.selection_label.pack(fill="x", padx=10, pady=10)
        
        # Action buttons frame
        action_frame = tk.LabelFrame(
            right_frame,
            text="  Actions  ",
            font=("Segoe UI", 9, "bold"),
            bg="#f8f9fa",
            fg="#003366"
        )
        action_frame.pack(fill="x", padx=10, pady=5)
        
        # Row 1: File operations
        row1 = tk.Frame(action_frame, bg="#f8f9fa")
        row1.pack(fill="x", padx=5, pady=5)
        
        self.btn_open_f1 = tk.Button(
            row1,
            text="📂 Open File 1",
            command=self.open_file_1,
            bg="#1565C0",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            width=15,
            state="disabled"
        )
        self.btn_open_f1.pack(side="left", padx=3)
        
        self.btn_open_f2 = tk.Button(
            row1,
            text="📂 Open File 2",
            command=self.open_file_2,
            bg="#1565C0",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            width=15,
            state="disabled"
        )
        self.btn_open_f2.pack(side="left", padx=3)
        
        self.btn_copy_1_to_2 = tk.Button(
            row1,
            text="📋 Copy F1 → F2",
            command=lambda: self.copy_file(1, 2),
            bg="#2E7D32",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            width=18,
            state="disabled"
        )
        self.btn_copy_1_to_2.pack(side="left", padx=3)
        
        self.btn_copy_2_to_1 = tk.Button(
            row1,
            text="📋 Copy F2 → F1",
            command=lambda: self.copy_file(2, 1),
            bg="#6A1B9A",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            width=18,
            state="disabled"
        )
        self.btn_copy_2_to_1.pack(side="left", padx=3)
        
        self.btn_view_diff = tk.Button(
            row1,
            text="🔍 View HTML Diff",
            command=self.open_diff,
            bg="#00695C",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            width=18,
            state="disabled"
        )
        self.btn_view_diff.pack(side="left", padx=3)
        
        # Row 2: AI operations
        row2 = tk.Frame(action_frame, bg="#f8f9fa")
        row2.pack(fill="x", padx=5, pady=5)
        
        self.btn_ai_suggest = tk.Button(
            row2,
            text="🤖 AI Suggest: Which to Keep",
            command=self.run_ai_suggest,
            bg="#4527A0",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            width=30,
            state="disabled"
        )
        self.btn_ai_suggest.pack(side="left", padx=3)
        
        self.btn_ai_merge = tk.Button(
            row2,
            text="🔀 AI Smart Merge (Azure OpenAI Farm)",
            command=self.run_ai_merge,
            bg="#006064",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            width=30,
            state="disabled"
        )
        self.btn_ai_merge.pack(side="left", padx=3)
        
        # File content viewer/editor
        editor_frame = tk.LabelFrame(
            right_frame,
            text="  File Content Viewer  ",
            font=("Segoe UI", 9, "bold"),
            bg="#f8f9fa",
            fg="#003366"
        )
        editor_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Tabbed editor
        self.editor_tabs = ttk.Notebook(editor_frame)
        self.editor_tabs.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Tab 1: Folder 1 file
        tab_f1 = tk.Frame(self.editor_tabs, bg="#1e1e1e")
        self.editor_tabs.add(tab_f1, text="  Platform File (F1)  ")
        
        self.editor_f1, self.editor_f1_scroll = self.create_editor(tab_f1)
        
        # Tab 2: Folder 2 file
        tab_f2 = tk.Frame(self.editor_tabs, bg="#1e1e1e")
        self.editor_tabs.add(tab_f2, text="  Project File (F2)  ")
        
        self.editor_f2, self.editor_f2_scroll = self.create_editor(tab_f2)
        
        return right_frame
    
    def create_editor(self, parent):
        """Create text editor widget"""
        editor = tk.Text(
            parent,
            wrap="none",
            font=("Consolas", 10),
            bg="#1e1e1e",
            fg="#d4d4d4",
            insertbackground="white",
            selectbackground="#264f78"
        )
        
        vsb = tk.Scrollbar(parent, orient="vertical", command=editor.yview)
        hsb = tk.Scrollbar(parent, orient="horizontal", command=editor.xview)
        editor.config(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        editor.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        
        return editor, vsb
    
    def create_bottom_buttons(self):
        """Create bottom action buttons - returns frame for caller to pack"""
        button_frame = tk.Frame(self.dialog, bg="#f0f4f7", relief="raised", bd=1)
        # ✅ Do NOT pack here - let caller handle packing
        
        # Single row with all buttons (compact sizing)
        button_row = tk.Frame(button_frame, bg="#f0f4f7")
        button_row.pack(fill="x", padx=5, pady=3)
        
        tk.Button(
            button_row,
            text="📁 Reports",
            command=self.open_reports_folder,
            bg="#1976D2",
            fg="white",
            font=("Segoe UI", 8),
            padx=8,
            pady=4
        ).pack(side="left", padx=2)

        tk.Button(
            button_row,
            text="🔍 Beyond Compare",
            command=self.open_master_report,
            bg="#6A0DAD",
            fg="white",
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=4
        ).pack(side="left", padx=2)
        
        tk.Button(
            button_row,
            text="📊 Excel",
            command=self.open_excel_report,
            bg="#27ae60",
            fg="white",
            font=("Segoe UI", 8),
            padx=8,
            pady=4
        ).pack(side="left", padx=2)
        
        tk.Button(
            button_row,
            text="📄 CSV",
            command=self.open_csv_report,
            bg="#f39c12",
            fg="white",
            font=("Segoe UI", 8),
            padx=8,
            pady=4
        ).pack(side="left", padx=2)
        
        tk.Button(
            button_row,
            text="🔍 Interface Diff",
            command=self.show_interface_diff,
            bg="#9C27B0",
            fg="white",
            font=("Segoe UI", 8),
            padx=8,
            pady=4
        ).pack(side="left", padx=2)
        
        
        self.analysis_tool_btn = tk.Button(
            button_row,
            text="🔬 Analysis Tool",
            command=self.open_interface_analysis_tool,
            bg="#1565c0",
            fg="white",
            font=("Segoe UI", 8),
            padx=8,
            pady=4,
            state="normal"
        )
        self.analysis_tool_btn.pack(side="left", padx=2)
        ToolTip(self.analysis_tool_btn, "Analyze interface differences (extracts snapshot files if needed)")
        
        self.assistant_btn = tk.Button(
            button_row,
            text="💬 Assistant",
            command=self.open_comparison_assistant,
            bg="#00838F",
            fg="white",
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=4,
            state="normal"
        )
        self.assistant_btn.pack(side="left", padx=2)
        ToolTip(self.assistant_btn, "Ask questions about this comparison, selected file, reports, or online components")

        tk.Button(
            button_row,
            text="🛠 File Change",
            command=self.open_manual_file_change_analyzer,
            bg="#6A0DAD",
            fg="white",
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=4,
        ).pack(side="left", padx=2)

        tk.Button(
            button_row,
            text="🔀 Switch\nComparison",
            command=self.open_switch_comparison,
            bg="#8B4513",
            fg="white",
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=4,
        ).pack(side="left", padx=2)

        tk.Button(
            button_row,
            text="✕ Close",
            command=self.dialog.destroy,
            bg="#c62828",
            fg="white",
            font=("Segoe UI", 8),
            padx=10,
            pady=4
        ).pack(side="right", padx=2)
        
        # ✅ IMPORTANT: Return the button frame so caller can pack it
        return button_frame
    
    def open_comparison_assistant(self):
        """Open a comparison-aware chatbot assistant."""
        try:
            from src.gui.comparison_assistant import ComparisonAssistantWindow
            ComparisonAssistantWindow(self.dialog, self)
        except Exception as e:
            messagebox.showerror(
                "Assistant Error",
                f"Could not open the comparison assistant:\n\n{str(e)}"
            )

    def open_switch_comparison(self):
        """Open Switch Comparison tool pre-filled with the current comparison folders."""
        try:
            from src.gui.switch_comparison import SwitchComparisonViewer
            SwitchComparisonViewer(
                parent=self.dialog,
                folder1_path=self.folder1_actual or "",
                folder2_path=self.folder2_actual or "",
                source1_name=self.folder1_display or "Source 1",
                source2_name=self.folder2_display or "Source 2",
                auto_run=True,
            )
        except Exception as e:
            messagebox.showerror(
                "Switch Comparison Error",
                f"Could not open the Switch Comparison tool:\n\n{str(e)}"
            )

    def open_manual_file_change_analyzer(self):
        """Open Manual File Change Analyzer pre-loaded with the current workspace."""
        try:
            from src.gui.manual_file_change_analyzer import ManualFileChangeAnalyzer
            # Prefer folder1 as the workspace context
            ws = getattr(self, "folder1", "") or ""
            ManualFileChangeAnalyzer(self.dialog, workspace_path=str(ws))
        except Exception as e:
            messagebox.showerror(
                "Analyzer Error",
                f"Could not open the Manual File Change Analyzer:\n\n{str(e)}"
            )
    
    def populate_results(self):
        """Populate the tree with results"""
        self.all_items = []
        
        for result in self.results:
            file_path = result[0]
            lines1 = result[1]
            lines2 = result[2]
            status = result[4]
            
            tag = {
                "Identical": "identical",
                "Different": "different",
                "Only in Platform": "only1",
                "Only in Project": "only2",
                "Comments update only": "comments",
                "Error": "error"
            }.get(status, "different")
            
            item_id = self.tree.insert(
                "",
                "end",
                values=(file_path, status, lines1, lines2),
                tags=(tag,)
            )
            
            self.all_items.append({
                'id': item_id,
                'file_path': file_path,
                'status': status,
                'result': result
            })
    
    def on_filter_change(self, *args):
        """Handle filter changes"""
        filter_text = self.filter_var.get().lower()
        status_filter = self.status_filter.get()
        
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        for item_data in self.all_items:
            file_path = item_data['file_path']
            status = item_data['status']
            result = item_data['result']
            
            if filter_text and filter_text not in file_path.lower():
                continue
            
            if status_filter != "All" and status != status_filter:
                continue
            
            tag = {
                "Identical": "identical",
                "Different": "different",
                "Only in Platform": "only1",
                "Only in Project": "only2",
                "Comments update only": "comments",
                "Error": "error"
            }.get(status, "different")
            
            self.tree.insert(
                "",
                "end",
                values=(result[0], result[4], result[1], result[2]),
                tags=(tag,)
            )
    
    def on_file_select(self, event=None):
        """Handle file selection in tree"""
        selection = self.tree.selection()
        if not selection:
            return
        
        item = selection[0]
        values = self.tree.item(item, 'values')
        
        if not values:
            return
        
        file_path = values[0]
        status = values[1]
        lines1 = values[2]
        lines2 = values[3]
        
        # Store current selection
        self.current_file = file_path
        self.current_status = status
        self.current_path1 = self.files1.get(file_path)
        self.current_path2 = self.files2.get(file_path)
        
        # Update selection label
        self.selection_label.config(
            text=f"📄 Selected: {file_path}\n"
                 f"Status: {status}  |  Lines F1: {lines1}  |  Lines F2: {lines2}"
        )
        
        # Enable/disable buttons based on status
        self.btn_open_f1.config(state="normal" if self.current_path1 else "disabled")
        self.btn_open_f2.config(state="normal" if self.current_path2 else "disabled")
        self.btn_copy_1_to_2.config(state="normal" if self.current_path1 else "disabled")
        self.btn_copy_2_to_1.config(state="normal" if self.current_path2 else "disabled")
        self.btn_view_diff.config(state="normal" if status in ("Different", "Modified", "Comments update only") else "disabled")
        self.btn_ai_suggest.config(state="normal")
        self.btn_ai_merge.config(state="normal" if status in ("Different", "Modified", "Comments update only") else "disabled")
        
        # Load file contents into editors
        self.load_file_content(self.editor_f1, self.current_path1, "Platform")
        self.load_file_content(self.editor_f2, self.current_path2, "Project")
    
    def load_file_content(self, editor, file_path, label):
        """Load file content into editor"""
        editor.config(state="normal")
        editor.delete("1.0", "end")
        
        if not file_path or not os.path.isfile(file_path):
            editor.insert("1.0", f"File not available in {label} folder")
            editor.config(state="disabled")
            return
        
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            editor.insert("1.0", content)
        except Exception as e:
            editor.insert("1.0", f"Error reading file: {str(e)}")
        
        editor.config(state="disabled")
    
    def on_tree_double_click(self, event):
        """Handle double-click on tree item - open HTML diff"""
        self.open_diff()
    
    def copy_file(self, src_num, dst_num):
        """Copy file from source to destination folder"""
        if not self.current_file:
            messagebox.showwarning("No Selection", "Please select a file first")
            return
        
        src_path = self.current_path1 if src_num == 1 else self.current_path2
        dst_folder = self.folder2_actual if dst_num == 2 else self.folder1_actual
        src_label = "Platform (F1)" if src_num == 1 else "Project (F2)"
        dst_label = "Project (F2)" if dst_num == 2 else "Platform (F1)"
        
        if not src_path or not os.path.isfile(src_path):
            messagebox.showerror("Error", f"Source file not found in {src_label}")
            return
        
        # Confirm action
        if not messagebox.askyesno(
            "Confirm Copy",
            f"Copy file from {src_label} to {dst_label}?\n\n"
            f"File: {self.current_file}\n\n"
            f"This will overwrite the file in {dst_label} if it exists."
        ):
            return
        
        try:
            dst_path = os.path.join(dst_folder, self.current_file)
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            
            shutil.copy2(src_path, dst_path)
            
            messagebox.showinfo(
                "Success",
                f"File copied successfully!\n\n"
                f"From: {src_label}\n"
                f"To: {dst_label}\n"
                f"File: {self.current_file}"
            )
            
            # Reload the destination file in editor
            if dst_num == 1:
                self.current_path1 = dst_path
                self.load_file_content(self.editor_f1, dst_path, "Platform")
            else:
                self.current_path2 = dst_path
                self.load_file_content(self.editor_f2, dst_path, "Project")
                
        except Exception as e:
            messagebox.showerror("Copy Failed", f"Error copying file:\n\n{str(e)}")
    
    def open_file_1(self):
        """Open file 1 in external editor"""
        if not self.current_file:
            messagebox.showwarning("No Selection", "Please select a file first")
            return
        
        if not self.current_path1 or not os.path.exists(self.current_path1):
            messagebox.showwarning("File Not Found", f"File 1 not found:\n{self.current_path1}")
            return
        
        try:
            # Open file in default system editor
            import subprocess
            import platform
            
            if platform.system() == "Windows":
                subprocess.run(["notepad.exe", self.current_path1], check=False)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", self.current_path1], check=False)
            else:  # Linux
                subprocess.run(["xdg-open", self.current_path1], check=False)
                
            messagebox.showinfo("File Opened", f"File 1 opened in external editor:\n{self.current_file}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open file:\n\n{str(e)}")
    
    def open_file_2(self):
        """Open file 2 in external editor"""
        if not self.current_file:
            messagebox.showwarning("No Selection", "Please select a file first")
            return
        
        if not self.current_path2 or not os.path.exists(self.current_path2):
            messagebox.showwarning("File Not Found", f"File 2 not found:\n{self.current_path2}")
            return
        
        try:
            # Open file in default system editor
            import subprocess
            import platform
            
            if platform.system() == "Windows":
                subprocess.run(["notepad.exe", self.current_path2], check=False)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", self.current_path2], check=False)
            else:  # Linux
                subprocess.run(["xdg-open", self.current_path2], check=False)
                
            messagebox.showinfo("File Opened", f"File 2 opened in external editor:\n{self.current_file}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open file:\n\n{str(e)}")
    
    def open_diff(self):
        """Open HTML diff in browser"""
        if not self.current_file:
            messagebox.showwarning("No Selection", "Please select a file first")
            return
        
        # Find HTML diff link from results
        html_link = None
        for result in self.results:
            if result[0] == self.current_file:
                html_link = result[5]  # HTML diff report column
                break
        
        if html_link and html_link not in ["N/A", "N/A (Identical)", ""]:
            # html_link may be an absolute path (online snapshot reports) or a
            # relative path (offline reports).  os.path.join returns the absolute
            # argument unchanged on both Windows and POSIX, so this handles both.
            html_full_path = (
                html_link if os.path.isabs(html_link)
                else os.path.join(self.report_paths.get('output_dir', ''), html_link)
            )
            if os.path.exists(html_full_path):
                webbrowser.open(f'file:///{os.path.abspath(html_full_path).replace(os.sep, "/")}')
            else:
                messagebox.showwarning("File Not Found", f"HTML diff file not found:\n{html_full_path}")
        else:
            messagebox.showinfo(
                "No Diff Available",
                f"No HTML diff available for this file.\n\n"
                f"Status: {self.current_status}\n"
                f"File: {self.current_file}"
            )
    
    def run_ai_suggest(self):
        """Run AI analysis on selected file"""
        if not self.current_file:
            messagebox.showwarning("No Selection", "Please select a file first")
            return
        
        # Get line counts
        lines1 = 0
        lines2 = 0
        for result in self.results:
            if result[0] == self.current_file:
                lines1 = result[1] if isinstance(result[1], int) else 0
                lines2 = result[2] if isinstance(result[2], int) else 0
                break
        
        try:
            from src.ai import ai_analyze_file
            from src.config import settings
            
            # Show progress
            progress_win = tk.Toplevel(self.dialog)
            progress_win.title("AI Analysis")
            progress_win.geometry("400x100")
            progress_win.configure(bg="white")
            progress_win.transient(self.dialog)
            
            tk.Label(
                progress_win,
                text="🤖 Analyzing files with AI...",
                font=("Segoe UI", 11, "bold"),
                bg="white"
            ).pack(pady=30)
            
            progress_win.update()
            
            # Run AI analysis
            openai_key = settings.OPENAI_API_KEY if hasattr(settings, 'OPENAI_API_KEY') else ""
            recommendation = ai_analyze_file(
                self.current_path1,
                self.current_path2,
                self.current_status,
                lines1,
                lines2,
                openai_key=openai_key
            )
            
            progress_win.destroy()
            
            # Show result
            result_win = tk.Toplevel(self.dialog)
            result_win.title(f"AI Analysis: {self.current_file}")
            result_win.geometry("900x700")
            result_win.configure(bg="white")
            
            # Header
            header = tk.Frame(result_win, bg="#4527A0", height=50)
            header.pack(fill="x")
            header.pack_propagate(False)
            
            tk.Label(
                header,
                text=f"🤖 AI Recommendation: {os.path.basename(self.current_file)}",
                font=("Segoe UI", 13, "bold"),
                bg="#4527A0",
                fg="white"
            ).pack(pady=12)
            
            # Content
            text_frame = tk.Frame(result_win, bg="white")
            text_frame.pack(fill="both", expand=True, padx=10, pady=10)
            
            text = tk.Text(
                text_frame,
                wrap="word",
                font=("Consolas", 10),
                bg="#FFFDE7",
                fg="#333333"
            )
            scroll = tk.Scrollbar(text_frame, command=text.yview)
            text.config(yscrollcommand=scroll.set)
            
            text.pack(side="left", fill="both", expand=True)
            scroll.pack(side="right", fill="y")
            
            text.insert("1.0", recommendation)
            text.config(state="disabled")
            
            # Close button
            tk.Button(
                result_win,
                text="Close",
                command=result_win.destroy,
                bg="#666666",
                fg="white",
                font=("Segoe UI", 10, "bold"),
                width=15
            ).pack(pady=10)
            
        except Exception as e:
            messagebox.showerror("AI Analysis Error", f"Error during AI analysis:\n\n{str(e)}")
    
    def run_ai_merge(self):
        """Run AI Smart Merge on selected file"""
        if not self.current_file:
            messagebox.showwarning("No Selection", "Please select a file first")
            return
        
        if self.current_status not in ("Different", "Modified", "Comments update only"):
            messagebox.showinfo(
                "Not Applicable",
                "AI Smart Merge is only available for modified/different files"
            )
            return
        
        if not self.current_path1 or not self.current_path2:
            messagebox.showerror("Error", "Cannot find both file versions")
            return
        
        # Confirm action
        if not messagebox.askyesno(
            "Confirm AI Merge",
            f"Run AI Smart Merge on:\n{self.current_file}\n\n"
            "This will use Azure OpenAI (Farm) to intelligently merge both versions.\n"
            "The process may take 30-60 seconds.\n\n"
            "Note: Requires env var GENAIPLATFORM_FARM_SUBSCRIPTION_KEY"
        ):
            return
        
        try:
            from src.ai import ai_merge_with_azure_openai
            from src.config import settings
            import threading

            if (not hasattr(settings, 'AOAI_FARM_SUBSCRIPTION_KEY')
                or not settings.AOAI_FARM_SUBSCRIPTION_KEY
                or str(settings.AOAI_FARM_SUBSCRIPTION_KEY).strip().lower() == 'none'):
                messagebox.showerror(
                    "API Key Missing",
                    "Azure OpenAI Farm subscription key not configured.\n\n"
                    "Set environment variable:\n"
                    "  GENAIPLATFORM_FARM_SUBSCRIPTION_KEY\n\n"
                    "Restart the app after setting it."
                )
                return
            
            # Show progress window with status label
            progress_win = tk.Toplevel(self.dialog)
            progress_win.title("AI Smart Merge")
            progress_win.geometry("550x150")
            progress_win.configure(bg="white")
            progress_win.transient(self.dialog)
            progress_win.grab_set()
            
            tk.Label(
                progress_win,
                text="🔀 Merging files with Azure OpenAI (Farm)...",
                font=("Segoe UI", 12, "bold"),
                bg="white"
            ).pack(pady=15)
            
            status_label = tk.Label(
                progress_win,
                text="Sending request to Azure OpenAI...",
                font=("Segoe UI", 9),
                bg="white",
                fg="gray"
            )
            status_label.pack(pady=5)
            
            progress_bar = ttk.Progressbar(progress_win, mode='indeterminate', length=400)
            progress_bar.pack(pady=10)
            progress_bar.start(10)
            
            progress_win.update()
            
            # Container for result
            result_container = {'merged': None, 'report': None, 'warnings': None, 'error': None}
            
            def run_merge():
                """Run merge in background thread"""
                try:
                    merged_content, dep_report, warnings_list = ai_merge_with_azure_openai(
                        self.current_path1,
                        self.current_path2,
                        self.current_status,
                        self.current_file,
                        self.files1,
                        self.files2,
                        self.folder1_actual,
                        self.folder2_actual,
                        settings.AOAI_FARM_SUBSCRIPTION_KEY
                    )
                    result_container['merged'] = merged_content
                    result_container['report'] = dep_report
                    result_container['warnings'] = warnings_list
                except Exception as e:
                    result_container['error'] = str(e)
            
            # Start merge in background
            merge_thread = threading.Thread(target=run_merge, daemon=True)
            merge_thread.start()
            
            # Wait for completion with status updates
            elapsed = 0
            while merge_thread.is_alive():
                progress_win.update()
                merge_thread.join(timeout=0.5)
                elapsed += 0.5
                
                # Update status based on elapsed time
                if elapsed < 10:
                    status_label.config(text="Sending request to Azure OpenAI...")
                elif elapsed < 30:
                    status_label.config(text="Analyzing files and generating merge... (this may take a while)")
                elif elapsed < 60:
                    status_label.config(text="Still processing... model is working on it...")
                else:
                    status_label.config(text="Taking longer than expected... Almost done...")
            
            progress_bar.stop()
            progress_win.destroy()
            
            # Check for errors
            if result_container['error']:
                error_msg = result_container['error']
                messagebox.showerror("AI Merge Error", f"Error during AI merge:\n\n{error_msg}")
                return
            
            # Show merged result
            self.show_merge_result(
                result_container['merged'],
                result_container['report'],
                result_container['warnings']
            )
            
        except Exception as e:
            messagebox.showerror("AI Merge Error", f"Error during AI merge:\n\n{str(e)}")
    
    def show_merge_result(self, merged_content, dep_report, warnings):
        """Show AI merge result in a new window"""
        result_win = tk.Toplevel(self.dialog)
        result_win.title(f"AI Merged: {self.current_file}")
        result_win.geometry("1200x800")
        result_win.configure(bg="white")
        
        # Header
        header = tk.Frame(result_win, bg="#006064", height=50)
        header.pack(fill="x")
        header.pack_propagate(False)
        
        tk.Label(
            header,
            text=f"🔀 AI Smart Merge Result: {os.path.basename(self.current_file)}",
            font=("Segoe UI", 13, "bold"),
            bg="#006064",
            fg="white"
        ).pack(pady=12)
        
        # Tabbed interface
        notebook = ttk.Notebook(result_win)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Tab 1: Merged Content
        merged_frame = tk.Frame(notebook, bg="white")
        notebook.add(merged_frame, text="  Merged File  ")
        
        merged_text = tk.Text(merged_frame, wrap="none", font=("Consolas", 10))
        merged_vsb = tk.Scrollbar(merged_frame, orient="vertical", command=merged_text.yview)
        merged_hsb = tk.Scrollbar(merged_frame, orient="horizontal", command=merged_text.xview)
        merged_text.config(yscrollcommand=merged_vsb.set, xscrollcommand=merged_hsb.set)
        
        merged_text.grid(row=0, column=0, sticky="nsew")
        merged_vsb.grid(row=0, column=1, sticky="ns")
        merged_hsb.grid(row=1, column=0, sticky="ew")
        merged_frame.grid_rowconfigure(0, weight=1)
        merged_frame.grid_columnconfigure(0, weight=1)
        
        merged_text.insert("1.0", merged_content)
        
        # Tab 2: Dependency Report
        dep_frame = tk.Frame(notebook, bg="white")
        notebook.add(dep_frame, text="  Dependency Report  ")
        
        dep_text = tk.Text(dep_frame, wrap="word", font=("Segoe UI", 10), bg="#FFF9C4")
        dep_scroll = tk.Scrollbar(dep_frame, command=dep_text.yview)
        dep_text.config(yscrollcommand=dep_scroll.set)
        dep_text.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        dep_scroll.pack(side="right", fill="y")
        
        dep_text.insert("1.0", dep_report)
        dep_text.config(state="disabled")
        
        # Warnings if any
        if warnings:
            warning_frame = tk.Frame(result_win, bg="#FFEBEE")
            warning_frame.pack(fill="x", padx=10, pady=5)
            
            tk.Label(
                warning_frame,
                text="⚠️ Warnings:",
                font=("Segoe UI", 10, "bold"),
                bg="#FFEBEE",
                fg="#C62828"
            ).pack(anchor="w", padx=10, pady=5)
            
            for w in warnings:
                tk.Label(
                    warning_frame,
                    text=f"  • {w}",
                    font=("Segoe UI", 9),
                    bg="#FFEBEE",
                    fg="#B71C1C",
                    wraplength=1100,
                    justify="left"
                ).pack(anchor="w", padx=20)
        
        # Bottom buttons
        btn_frame = tk.Frame(result_win, bg="white")
        btn_frame.pack(fill="x", pady=10)
        
        def save_merged():
            save_path = filedialog.asksaveasfilename(
                defaultextension=os.path.splitext(self.current_file)[1],
                initialfile=os.path.basename(self.current_file),
                title="Save Merged File"
            )
            if save_path:
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(merged_content)
                messagebox.showinfo("Saved", f"Merged file saved to:\n{save_path}")
        
        tk.Button(
            btn_frame,
            text="💾 Save Merged File",
            command=save_merged,
            bg="#1976D2",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            width=20
        ).pack(side="left", padx=10)
        
        tk.Button(
            btn_frame,
            text="Close",
            command=result_win.destroy,
            bg="#666666",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            width=15
        ).pack(side="right", padx=10)
    
    def show_interface_diff(self):
        """Show interface differences between folders (C/C++ interfaces)"""
        try:
            from src.utils.interface_diff import InterfaceDiffEngine, Severity, ChangeType
            import threading
            
            if self._is_online_snapshot_result():
                self._extract_and_analyze_snapshots()
                return
            
            # Show progress
            progress_win = tk.Toplevel(self.dialog)
            progress_win.title("Interface Analysis")
            progress_win.geometry("500x120")
            progress_win.configure(bg="white")
            progress_win.transient(self.dialog)
            progress_win.grab_set()
            
            tk.Label(
                progress_win,
                text="🔍 Analyzing C/C++ interfaces...",
                font=("Segoe UI", 12, "bold"),
                bg="white"
            ).pack(pady=15)
            
            status_label = tk.Label(
                progress_win,
                text="Parsing source files and extracting interfaces...",
                font=("Segoe UI", 9),
                bg="white",
                fg="gray"
            )
            status_label.pack(pady=5)
            
            progress_bar = ttk.Progressbar(progress_win, mode='indeterminate', length=400)
            progress_bar.pack(pady=10)
            progress_bar.start(10)
            
            progress_win.update()
            
            # Container for result
            result_container = {'diff': None, 'error': None}
            
            def run_analysis():
                """Run interface diff in background thread"""
                try:
                    engine = InterfaceDiffEngine()
                    baseline_diff = engine.compare_baselines(
                        self.folder1_actual,
                        self.folder2_actual
                    )
                    result_container['diff'] = baseline_diff
                except Exception as e:
                    result_container['error'] = str(e)
            
            # Start analysis in background
            analysis_thread = threading.Thread(target=run_analysis, daemon=True)
            analysis_thread.start()
            
            # Wait for completion with status updates
            elapsed = 0
            while analysis_thread.is_alive():
                progress_win.update()
                analysis_thread.join(timeout=0.5)
                elapsed += 0.5
                
                # Update status based on elapsed time
                if elapsed < 5:
                    status_label.config(text="Parsing source files and extracting interfaces...")
                elif elapsed < 10:
                    status_label.config(text="Comparing functions, structs, enums, macros...")
                else:
                    status_label.config(text="Analyzing changes and categorizing severity...")
            
            progress_bar.stop()
            progress_win.destroy()
            
            # Check for errors
            if result_container['error']:
                messagebox.showerror("Analysis Error", 
                                   f"Error analyzing interfaces:\n\n{result_container['error']}")
                return
            
            # Show results
            self.show_interface_diff_results(result_container['diff'])
            
        except ImportError as e:
            messagebox.showerror(
                "Module Not Found",
                "Interface analysis modules not found.\n\n"
                "Make sure interface_parser.py and interface_diff.py\n"
                "are in src/utils/ directory."
            )
        except Exception as e:
            messagebox.showerror("Error", f"Error running interface analysis:\n\n{str(e)}")
    
    def show_interface_diff_results(self, baseline_diff):
        """Show interface diff results in a new window"""
        from src.utils.interface_diff import Severity, ChangeType
        
        result_win = tk.Toplevel(self.dialog)
        result_win.title("Interface Differences - C/C++ Analysis")
        result_win.geometry("1400x850")
        result_win.configure(bg="white")
        
        # Header
        header = tk.Frame(result_win, bg="#9C27B0", height=60)
        header.pack(fill="x")
        header.pack_propagate(False)
        
        tk.Label(
            header,
            text="🔍 Interface Differences Analysis",
            font=("Segoe UI", 14, "bold"),
            bg="#9C27B0",
            fg="white"
        ).pack(side="left", padx=20, pady=15)
        
        # Summary bar
        summary_frame = tk.Frame(result_win, bg="#F5F5F5", height=80)
        summary_frame.pack(fill="x")
        summary_frame.pack_propagate(False)
        
        summary_text = (
            f"Total Files: {baseline_diff.total_files}  |  "
            f"Modified: {baseline_diff.files_modified}  |  "
            f"Added: {baseline_diff.files_added}  |  "
            f"Removed: {baseline_diff.files_removed}\n"
            f"🔴 Breaking Changes: {baseline_diff.breaking_changes}  |  "
            f"🟡 Review Needed: {baseline_diff.review_needed}  |  "
            f"🟢 Safe Changes: {baseline_diff.safe_changes}"
        )
        
        tk.Label(
            summary_frame,
            text=summary_text,
            font=("Segoe UI", 10, "bold"),
            bg="#F5F5F5",
            fg="#333333",
            justify="left"
        ).pack(side="left", padx=20, pady=15)
        
        # Main content
        content_frame = tk.Frame(result_win, bg="white")
        content_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Filter frame
        filter_frame = tk.Frame(content_frame, bg="white")
        filter_frame.pack(fill="x", padx=5, pady=5)
        
        tk.Label(filter_frame, text="Filter:", font=("Segoe UI", 9), bg="white").pack(side="left", padx=5)
        
        filter_var = tk.StringVar()
        tk.Entry(filter_frame, textvariable=filter_var, font=("Segoe UI", 9), width=30).pack(side="left", padx=5)
        
        severity_var = tk.StringVar(value="All")
        severity_combo = ttk.Combobox(
            filter_frame,
            textvariable=severity_var,
            values=["All", "Breaking", "Review", "Safe"],
            state="readonly",
            width=15,
            font=("Segoe UI", 9)
        )
        severity_combo.pack(side="left", padx=10)
        
        # Tree view
        tree_frame = tk.Frame(content_frame, bg="white")
        tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        vsb = tk.Scrollbar(tree_frame, orient="vertical")
        hsb = tk.Scrollbar(tree_frame, orient="horizontal")
        
        columns = ("File", "Interface", "Type", "Change", "Severity", "Details")
        tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set
        )
        
        vsb.config(command=tree.yview)
        hsb.config(command=tree.xview)
        
        tree.heading("File", text="File")
        tree.heading("Interface", text="Interface Name")
        tree.heading("Type", text="Type")
        tree.heading("Change", text="Change")
        tree.heading("Severity", text="Severity")
        tree.heading("Details", text="Details")
        
        tree.column("File", width=250, anchor="w")
        tree.column("Interface", width=200, anchor="w")
        tree.column("Type", width=100, anchor="center")
        tree.column("Change", width=100, anchor="center")
        tree.column("Severity", width=100, anchor="center")
        tree.column("Details", width=400, anchor="w")
        
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        
        # Configure tags with actual Severity enum
        tree.tag_configure("breaking", background="#FFCDD2", foreground="#B71C1C")
        tree.tag_configure("review", background="#FFF9C4", foreground="#F57F17")
        tree.tag_configure("safe", background="#C8E6C9", foreground="#1B5E20")
        tree.tag_configure("info", background="#E3F2FD", foreground="#0D47A1")
        
        # Populate tree
        all_items = []
        for file_path, file_diff in sorted(baseline_diff.file_diffs.items()):
            for diff in file_diff.diffs:
                severity_tag = {
                    Severity.BREAKING: "breaking",
                    Severity.REVIEW: "review",
                    Severity.SAFE: "safe",
                    Severity.INFO: "info"
                }.get(diff.severity, "info")
                
                item_id = tree.insert(
                    "",
                    "end",
                    values=(
                        file_path,
                        diff.element_name,
                        diff.interface_type.value,
                        diff.change_type.value,
                        diff.severity.value,
                        diff.diff_summary
                    ),
                    tags=(severity_tag,)
                )
                all_items.append((item_id, file_path, diff))
        
        # Filter function
        def apply_filter(*args):
            filter_text = filter_var.get().lower()
            severity_filter = severity_var.get()
            
            for item_id, file_path, diff in all_items:
                show = True
                
                if filter_text and filter_text not in file_path.lower() and filter_text not in diff.element_name.lower():
                    show = False
                
                if severity_filter != "All":
                    if severity_filter.lower() != diff.severity.value:
                        show = False
                
                if show:
                    tree.reattach(item_id, "", "end")
                else:
                    tree.detach(item_id)
        
        filter_var.trace_add("write", apply_filter)
        severity_combo.bind("<<ComboboxSelected>>", apply_filter)
        
        # Bottom buttons
        btn_frame = tk.Frame(result_win, bg="white")
        btn_frame.pack(fill="x", pady=10)
        
        def export_to_csv():
            """Export interface diff to CSV"""
            csv_path = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                initialfile="interface_differences.csv",
                title="Save Interface Diff Report"
            )
            
            if csv_path:
                try:
                    import csv
                    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        writer.writerow(["File", "Interface", "Type", "Change", "Severity", "Details"])
                        
                        for file_path, file_diff in sorted(baseline_diff.file_diffs.items()):
                            for diff in file_diff.diffs:
                                writer.writerow([
                                    file_path,
                                    diff.element_name,
                                    diff.interface_type.value,
                                    diff.change_type.value,
                                    diff.severity.value,
                                    diff.diff_summary
                                ])
                    
                    messagebox.showinfo("Exported", f"Interface diff exported to:\n{csv_path}")
                except Exception as e:
                    messagebox.showerror("Export Failed", f"Error exporting to CSV:\n\n{str(e)}")
        
        tk.Button(
            btn_frame,
            text="💾 Export to CSV",
            command=export_to_csv,
            bg="#1976D2",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            width=15
        ).pack(side="left", padx=10)
        
        tk.Button(
            btn_frame,
            text="Close",
            command=result_win.destroy,
            bg="#666666",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            width=15
        ).pack(side="right", padx=10)
    
    def open_master_report(self):
        """Open the Beyond Compare-style master snapshot comparison report."""
        master_path = self.report_paths.get('master_report', '') if isinstance(self.report_paths, dict) else ''
        if master_path and os.path.isfile(master_path):
            webbrowser.open('file:///' + master_path.replace('\\', '/'))
        else:
            # Fallback: look for Master_Comparison_Report.html in output_dir
            output_dir = self.report_paths.get('output_dir', '') if isinstance(self.report_paths, dict) else ''
            fallback = os.path.join(output_dir, 'Master_Comparison_Report.html')
            if output_dir and os.path.isfile(fallback):
                webbrowser.open('file:///' + fallback.replace('\\', '/'))
            else:
                messagebox.showinfo(
                    "Not Available",
                    "The Beyond Compare master report was not generated for this comparison.\n\n"
                    "It is only produced for Online→Online snapshot comparisons."
                )

    def open_reports_folder(self):
        """Open the reports folder in file explorer"""
        output_dir = self.report_paths['output_dir']
        if os.path.exists(output_dir):
            if os.name == 'nt':  # Windows
                os.startfile(output_dir)
            elif os.name == 'posix':
                os.system(f'open "{output_dir}"' if os.uname().sysname == 'Darwin' 
                         else f'xdg-open "{output_dir}"')
        else:
            messagebox.showerror("Error", f"Folder not found: {output_dir}")
    
    def open_excel_report(self):
        """Open Excel report"""
        excel_path = self.report_paths['excel']
        if os.path.exists(excel_path):
            if os.name == 'nt':
                os.startfile(excel_path)
            else:
                webbrowser.open(f'file://{os.path.abspath(excel_path)}')
        else:
            messagebox.showerror("Error", f"Excel file not found: {excel_path}")
    
    def open_csv_report(self):
        """Open CSV report"""
        csv_path = self.report_paths['csv']
        if os.path.exists(csv_path):
            if os.name == 'nt':
                os.startfile(csv_path)
            else:
                webbrowser.open(f'file://{os.path.abspath(csv_path)}')
        else:
            messagebox.showerror("Error", f"CSV file not found: {csv_path}")
    
    def open_interface_analysis_tool(self):
        """Open the enhanced interface analysis tool GUI."""
        try:
            # Check if paths are local directories or snapshot URLs
            folder1_is_local = os.path.isdir(str(self.folder1_actual)) if self.folder1_actual else False
            folder2_is_local = os.path.isdir(str(self.folder2_actual)) if self.folder2_actual else False
            
            # If both are local directories, run interface analysis directly
            if folder1_is_local and folder2_is_local:
                from .interface_diff_viewer_enhanced import show_interface_diff_viewer
                
                # Show the enhanced interface diff viewer with paths
                viewer = show_interface_diff_viewer(
                    self.dialog,
                    baseline_path=self.folder1_actual,
                    target_path=self.folder2_actual
                )
                return
            
            # For snapshots (non-local paths), trigger file extraction and then analyze
            if self._is_online_snapshot_result():
                # This is snapshot comparison mode
                messagebox.showinfo(
                    "Interface Analysis - Snapshot Mode",
                    "Interface analysis will extract the selected online components to temporary local folders, then run the same analyzer used for offline comparisons.\n\n"
                    "Only selected components and C/C++ source/header files are pulled."
                )
                
                # Extract and analyze snapshot files
                self._extract_and_analyze_snapshots()
                return
            
            messagebox.showwarning(
                "Interface Analysis",
                "Interface analysis needs either two local folders or an online-online result with selected component metadata."
            )
            
        except ImportError as e:
            messagebox.showerror(
                "Import Error",
                f"Could not import interface analysis tool:\n\n{str(e)}"
            )
        except Exception as e:
            messagebox.showerror(
                "Error",
                f"Error opening interface analysis tool:\n\n{str(e)}"
            )
    
    def _is_online_snapshot_result(self):
        """Return True when this result viewer came from online-online snapshot comparison."""
        return self.online_context.get('mode') == 'online_online'
    
    def _extract_and_analyze_snapshots(self):
        """Extract selected RTC snapshot component files and run interface analysis."""
        try:
            from src.config import settings
            
            username = self.online_context.get('username', '')
            password = self.online_context.get('password', '')
            server_url = self.online_context.get('server_url', '')
            scm_path = getattr(settings, 'LSCM_PATH', '')
            
            if not username or not password:
                messagebox.showerror(
                    "RTC Credentials Required",
                    "Online interface analysis needs the current RTC login session. Please run the online-online comparison again and log in."
                )
                return
            
            if not scm_path or not os.path.exists(scm_path):
                messagebox.showerror(
                    "RTC SCM CLI Not Found",
                    f"Cannot extract online snapshot files because RTC SCM CLI was not found:\n\n{scm_path}\n\n"
                    "Update LSCM_PATH in src/config/settings.py."
                )
                return
            
            snap1_components = self.online_context.get('snapshot1_components', [])
            snap2_components = self.online_context.get('snapshot2_components', [])
            selected_components = self.online_context.get('selected_components', [])
            
            snap1_by_name = {c.get('name'): c for c in snap1_components if c.get('name')}
            snap2_by_name = {c.get('name'): c for c in snap2_components if c.get('name')}
            if not selected_components:
                selected_components = sorted(set(snap1_by_name) & set(snap2_by_name))
            
            if not selected_components:
                messagebox.showwarning(
                    "No Components",
                    "No selected online components are available for interface analysis."
                )
                return
            
            temp_dir = tempfile.mkdtemp(prefix="rtc_snapshot_analysis_")
            baseline_temp = os.path.join(temp_dir, "snapshot1_files")
            target_temp = os.path.join(temp_dir, "snapshot2_files")
            os.makedirs(baseline_temp, exist_ok=True)
            os.makedirs(target_temp, exist_ok=True)
            
            progress_window = tk.Toplevel(self.dialog)
            progress_window.title("Extracting Online Components")
            progress_window.geometry("560x170")
            progress_window.transient(self.dialog)
            progress_window.grab_set()
            
            progress_label = tk.Label(
                progress_window,
                text="Extracting selected RTC components for interface analysis...",
                font=("Segoe UI", 10, "bold")
            )
            progress_label.pack(pady=(18, 8))
            
            progress_bar = ttk.Progressbar(
                progress_window,
                length=500,
                mode='determinate',
                maximum=max(1, len(selected_components) * 2)
            )
            progress_bar.pack(pady=8)
            
            status_label = tk.Label(progress_window, text="", font=("Segoe UI", 9), fg="blue", wraplength=520)
            status_label.pack(pady=5)
            progress_window.update()
            
            extracted_total = 0
            completed_units = 0
            
            try:
                for component_name in selected_components:
                    safe_name = self._safe_path_part(component_name)
                    component1 = snap1_by_name.get(component_name)
                    component2 = snap2_by_name.get(component_name)
                    
                    if component1:
                        status_label.config(text=f"Snapshot 1: extracting {component_name}...")
                        progress_window.update()
                        extracted_total += self._extract_component_baseline_files(
                            component1,
                            os.path.join(baseline_temp, safe_name),
                            username,
                            password,
                            server_url,
                            scm_path
                        )
                    completed_units += 1
                    progress_bar['value'] = completed_units
                    progress_window.update()
                    
                    if component2:
                        status_label.config(text=f"Snapshot 2: extracting {component_name}...")
                        progress_window.update()
                        extracted_total += self._extract_component_baseline_files(
                            component2,
                            os.path.join(target_temp, safe_name),
                            username,
                            password,
                            server_url,
                            scm_path
                        )
                    completed_units += 1
                    progress_bar['value'] = completed_units
                    progress_window.update()
                
                progress_window.destroy()
                
                if extracted_total == 0:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    messagebox.showwarning(
                        "No Interface Files Extracted",
                        "RTC extraction completed, but no C/C++ interface source files were pulled from the selected components.\n\n"
                        "Check that the selected components contain .h/.hpp/.c/.cpp files and that SCM CLI can access the baselines."
                    )
                    return
                
                logger.info(f"Running interface analysis on {extracted_total} extracted online files")
                from .interface_diff_viewer_enhanced import show_interface_diff_viewer
                
                show_interface_diff_viewer(
                    self.dialog,
                    baseline_path=baseline_temp,
                    target_path=target_temp
                )
                
                def cleanup_on_exit(path=temp_dir):
                    try:
                        if os.path.exists(path):
                            shutil.rmtree(path)
                    except Exception as cleanup_err:
                        logger.warning(f"Failed to cleanup snapshot extraction folder {path}: {cleanup_err}")
                
                import atexit
                atexit.register(cleanup_on_exit)
                
            except Exception:
                progress_window.destroy()
                shutil.rmtree(temp_dir, ignore_errors=True)
                raise
        
        except Exception as e:
            logger.error(f"Error extracting and analyzing online snapshots: {e}", exc_info=True)
            messagebox.showerror(
                "Snapshot Analysis Error",
                f"Error during online snapshot extraction:\n\n{str(e)[:500]}"
            )
    
    def _extract_component_baseline_files(self, component, output_dir, username, password, server_url, scm_path):
        """Extract supported C/C++ files from one RTC baseline into output_dir."""
        component_name = component.get('name', 'Unknown')
        baseline_uuid = component.get('baseline_uuid') or component.get('uuid')
        if not baseline_uuid:
            logger.warning(f"Skipping {component_name}: no baseline UUID")
            return 0
        
        os.makedirs(output_dir, exist_ok=True)
        files = self._list_baseline_files(baseline_uuid, username, password, server_url, scm_path)
        supported_exts = {'.h', '.hpp', '.c', '.cpp', '.cc', '.cxx', '.hxx'}
        interface_files = [
            path for path in files
            if os.path.splitext(path)[1].lower() in supported_exts
        ]
        
        if not interface_files:
            logger.info(f"{component_name}: no supported C/C++ files found in baseline {baseline_uuid[:12]}")
            return 0
        
        max_workers = min(6, max(1, os.cpu_count() or 4))
        extracted = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(
                    self._get_baseline_file,
                    baseline_uuid,
                    file_path,
                    output_dir,
                    username,
                    password,
                    server_url,
                    scm_path,
                    component_name
                )
                for file_path in interface_files
            ]
            
            for future in as_completed(futures):
                try:
                    if future.result():
                        extracted += 1
                except Exception as e:
                    logger.debug(f"{component_name}: file extraction failed: {e}")
        
        logger.info(f"{component_name}: extracted {extracted}/{len(interface_files)} interface files")
        return extracted
    
    def _list_baseline_files(self, baseline_uuid, username, password, server_url, scm_path):
        """List files in an RTC baseline using scm list files JSON output."""
        cmd = [
            scm_path,
            'list', 'files',
            '-b', baseline_uuid,
            '-r', server_url,
            '-u', username,
            '-P', password,
            '-D', 'all',
            '-j'
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=90,
            env=self._scm_env(),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        
        if not result.stdout.strip():
            logger.warning(f"SCM list files returned no output for baseline {baseline_uuid[:12]}: {result.stderr[:300]}")
            return []
        
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            logger.warning(f"SCM list files returned non-JSON output for baseline {baseline_uuid[:12]}")
            return []
        
        baseline_data = data.get('baseline', {}) if isinstance(data, dict) else {}
        remote_files = baseline_data.get('remote-files', [])
        paths = []
        for item in remote_files:
            if not isinstance(item, dict):
                continue
            path = item.get('path', '').strip()
            if not path or path.endswith('/'):
                continue
            paths.append(path.strip('/'))
        
        logger.info(f"Baseline {baseline_uuid[:12]}: listed {len(paths)} files")
        return sorted(set(paths))
    
    def _get_baseline_file(self, baseline_uuid, file_path, output_dir, username, password, server_url, scm_path, component_name):
        """Fetch one file from an RTC baseline using scm get file."""
        clean_path = file_path.strip('/').replace('\\', '/')
        relative_parts = [self._safe_path_part(part) for part in clean_path.split('/') if part]
        if not relative_parts:
            return False
        
        output_file = os.path.join(output_dir, *relative_parts)
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        command_variants = [
            [
                scm_path, 'get', 'file', baseline_uuid, '-b',
                '-f', clean_path, '-r', server_url, '-u', username, '-P', password,
                '-o', output_file, '-C', component_name
            ],
            [
                scm_path, 'get', 'file', baseline_uuid, '-c', component_name, '-b',
                '-f', clean_path, '-r', server_url, '-u', username, '-P', password,
                '-o', output_file
            ],
            [
                scm_path, 'get', 'file', baseline_uuid, '-b',
                '-f', clean_path, '-r', server_url, '-u', username, '-P', password,
                '-o', output_file
            ],
        ]
        
        for cmd in command_variants:
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    env=self._scm_env(),
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                if result.returncode == 0 and os.path.exists(output_file):
                    return True
                logger.debug(
                    f"SCM get file failed for {component_name}/{clean_path}: "
                    f"rc={result.returncode}, stderr={result.stderr[:200]}"
                )
            except subprocess.TimeoutExpired:
                logger.warning(f"Timeout extracting {component_name}/{clean_path}")
        
        return False
    
    def _safe_path_part(self, value):
        """Sanitize a component or path segment for local extraction."""
        value = str(value or "unknown").strip()
        value = value.replace(':', '_').replace('*', '_').replace('?', '_')
        value = value.replace('"', '_').replace('<', '_').replace('>', '_')
        value = value.replace('|', '_').replace('/', '_').replace('\\', '_')
        return value or "unknown"
    
    def _scm_env(self):
        """Return environment for SCM CLI without proxy variables that can break RTC CLI calls."""
        env = os.environ.copy()
        for proxy_var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'NO_PROXY', 'no_proxy']:
            env.pop(proxy_var, None)
        return env
    
    def show(self):
        """Show the dialog and wait for it to close"""
        self.dialog.wait_window()


def show_results_dialog(parent, results, folder1_display, folder2_display,
                        folder1_actual, folder2_actual, files1, files2, report_paths):
    """
    Show the enhanced comparison results dialog.
    
    Args:
        parent: Parent window
        results: List of comparison results
        folder1_display: Display name for folder 1
        folder2_display: Display name for folder 2
        folder1_actual: Actual path to folder 1
        folder2_actual: Actual path to folder 2
        files1: Dict of files in folder 1
        files2: Dict of files in folder 2
        report_paths: Dict with report paths
    """
    dialog = ComparisonResultsDialog(
        parent, results, folder1_display, folder2_display,
        folder1_actual, folder2_actual, files1, files2, report_paths
    )
    dialog.show()
