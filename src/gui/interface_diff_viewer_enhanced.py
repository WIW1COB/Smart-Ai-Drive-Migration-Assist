"""
Interface Diff Analysis Viewer GUI - Enterprise Edition (Enhanced & Refactored)
Developer-friendly interactive analysis tool with hierarchical navigation and dynamic panels
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import threading
import logging
import csv
import html
import webbrowser
import sys
import os
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Optional

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

from ..utils.interface_diff import (
    InterfaceDiffEngine, Severity, ChangeType, InterfaceType,
    BaselineDiff, FileDiff, InterfaceDiff
)

# Import dependency analysis
try:
    if __name__ != '__main__':
        from ..dependency_graph import DependencyGraphBuilder, DependencyGraph, ImpactAnalyzer
    else:
        from dependency_graph import DependencyGraphBuilder, DependencyGraph, ImpactAnalyzer
    DEPENDENCY_AVAILABLE = True
except ImportError as e:
    DEPENDENCY_AVAILABLE = False
    logger.warning(f"Dependency analysis unavailable: {e}")


class ToolTip:
    """Create a tooltip for a given widget."""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        widget.bind("<Enter>", self.show_tooltip)
        widget.bind("<Leave>", self.hide_tooltip)
    
    def show_tooltip(self, event=None):
        if self.tooltip_window or not self.text:
            return
        x, y, _, _ = self.widget.bbox("insert") if hasattr(self.widget, 'bbox') else (0, 0, 0, 0)
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 20
        
        self.tooltip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        
        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                        background="#FFFFDD", relief=tk.SOLID, borderwidth=1,
                        font=("Segoe UI", 8))
        label.pack(ipadx=5, ipady=3)
    
    def hide_tooltip(self, event=None):
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None


class LoadingIndicator:
    """Animated loading indicator."""
    def __init__(self, parent, message="Loading..."):
        self.parent = parent
        self.is_showing = False
        self.frame = None
        self.message = message
        self.animation_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.current_char = 0
        
    def show(self, message=None):
        if self.is_showing:
            return
        
        if message:
            self.message = message
            
        self.is_showing = True
        self.frame = tk.Frame(self.parent, bg="white", relief="raised", bd=2)
        self.frame.place(relx=0.5, rely=0.5, anchor="center")
        
        self.label = tk.Label(
            self.frame, text=f"{self.animation_chars[0]} {self.message}",
            font=("Segoe UI", 12), bg="white", fg="#1565C0", padx=30, pady=20
        )
        self.label.pack()
        
        self._animate()
    
    def _animate(self):
        if not self.is_showing:
            return
        self.current_char = (self.current_char + 1) % len(self.animation_chars)
        self.label.config(text=f"{self.animation_chars[self.current_char]} {self.message}")
        self.parent.after(100, self._animate)
    
    def hide(self):
        self.is_showing = False
        if self.frame:
            self.frame.destroy()
            self.frame = None


class QuickActionsPanel:
    """Quick actions panel for selected interface."""
    def __init__(self, parent, viewer):
        self.viewer = viewer
        self.frame = tk.LabelFrame(
            parent, text="⚡ Quick Actions", 
            bg="white", font=("Segoe UI", 9, "bold"),
            relief="groove", bd=1
        )
        self.frame.pack(fill="x", padx=5, pady=(0, 5))
        
        button_frame = tk.Frame(self.frame, bg="white")
        button_frame.pack(fill="x", padx=5, pady=5)
        
        # Open baseline file
        self.baseline_btn = tk.Button(
            button_frame, text="📂 Open Baseline File",
            command=self._open_baseline_file,
            bg="#3498db", fg="white", font=("Segoe UI", 8),
            padx=10, pady=4, state="disabled"
        )
        self.baseline_btn.pack(side="left", padx=3)
        ToolTip(self.baseline_btn, "Open the baseline file in default editor")
        
        # Open target file
        self.target_btn = tk.Button(
            button_frame, text="📂 Open Target File",
            command=self._open_target_file,
            bg="#3498db", fg="white", font=("Segoe UI", 8),
            padx=10, pady=4, state="disabled"
        )
        self.target_btn.pack(side="left", padx=3)
        ToolTip(self.target_btn, "Open the target file in default editor")
        
        # Copy recommendation
        self.copy_btn = tk.Button(
            button_frame, text="📋 Copy Summary",
            command=self._copy_summary,
            bg="#9b59b6", fg="white", font=("Segoe UI", 8),
            padx=10, pady=4, state="disabled"
        )
        self.copy_btn.pack(side="left", padx=3)
        ToolTip(self.copy_btn, "Copy change summary to clipboard")
        
        # View in folder
        self.folder_btn = tk.Button(
            button_frame, text="📁 Show in Folder",
            command=self._show_in_folder,
            bg="#27ae60", fg="white", font=("Segoe UI", 8),
            padx=10, pady=4, state="disabled"
        )
        self.folder_btn.pack(side="left", padx=3)
        ToolTip(self.folder_btn, "Show file in file explorer")
        
    def enable_actions(self, diff, file_path):
        """Enable quick actions for selected interface."""
        self.current_diff = diff
        self.current_file_path = file_path
        
        # Enable all buttons
        for btn in [self.baseline_btn, self.target_btn, self.copy_btn, self.folder_btn]:
            btn.config(state="normal")
    
    def disable_actions(self):
        """Disable all quick actions."""
        for btn in [self.baseline_btn, self.target_btn, self.copy_btn, self.folder_btn]:
            btn.config(state="disabled")
    
    def _open_baseline_file(self):
        if hasattr(self, 'current_diff') and self.current_diff.baseline_element:
            file_path = self.current_diff.baseline_element.file_path
            if os.path.exists(file_path):
                os.startfile(file_path) if os.name == 'nt' else os.system(f'open "{file_path}"')
    
    def _open_target_file(self):
        if hasattr(self, 'current_diff') and self.current_diff.target_element:
            file_path = self.current_diff.target_element.file_path
            if os.path.exists(file_path):
                os.startfile(file_path) if os.name == 'nt' else os.system(f'open "{file_path}"')
    
    def _copy_summary(self):
        if hasattr(self, 'current_diff'):
            summary = f"{self.current_diff.element_name}: {self.current_diff.diff_summary}\n"
            summary += f"Severity: {self.current_diff.severity.value}\n"
            summary += f"Change: {self.current_diff.change_type.value}"
            
            self.viewer.window.clipboard_clear()
            self.viewer.window.clipboard_append(summary)
            messagebox.showinfo("Copied", "Summary copied to clipboard!")
    
    def _show_in_folder(self):
        if hasattr(self, 'current_file_path'):
            folder = os.path.dirname(os.path.join(
                self.viewer.diff_result.target_path if self.viewer.diff_result else "",
                self.current_file_path
            ))
            if os.path.exists(folder):
                os.startfile(folder) if os.name == 'nt' else os.system(f'open "{folder}"')


class EnhancedInterfaceDiffViewer:
    """Enhanced enterprise-grade interface analysis tool with improved UX."""
    
    def __init__(self, parent=None):
        """Initialize the enhanced viewer."""
        self.window = tk.Toplevel(parent) if parent else tk.Tk()
        self.window.title("🔬 Interface Analysis Tool - Enterprise Edition")
        self.window.geometry("1700x950")
        self.window.configure(bg="#ECEFF1")
        
        # State variables
        self.baseline_root = tk.StringVar()
        self.target_root = tk.StringVar()
        self.diff_scope_baseline_path = tk.StringVar()
        self.diff_scope_target_path = tk.StringVar()
        self.diff_result = None
        self.is_analyzing = False

        # Scope settings
        self.diff_scope_mode = tk.StringVar(value="whole_workspace")  # "whole_workspace" or "subfolder_only"
        self.enable_full_dependency = tk.BooleanVar(value=True)

        # Dependency analysis
        self.dependency_graph_baseline = None
        self.dependency_graph_target = None
        self.impact_analyzer_target = None
        self.enable_dependency_analysis = tk.BooleanVar(value=DEPENDENCY_AVAILABLE)
        
        # Filter states
        self.filter_severity = tk.StringVar(value="All")
        self.filter_type = tk.StringVar(value="All")
        self.filter_change = tk.StringVar(value="All")
        self.filter_area = tk.StringVar(value="All")
        self.search_text = tk.StringVar()
        
        # Data storage
        self.all_diffs = []  # List of (diff, file_path)
        self.file_groups = defaultdict(list)  # Group diffs by file
        self.selected_diff = None
        
        # Tree item to diff mapping for easy retrieval
        self.tree_item_to_diff = {}  # Maps tree item ID to (diff, file_path)

        # Interface-level reference (call-site) analysis
        # Cache: (root_path, interface_name, interface_type) -> list[(rel_path, line_no, line_text)]
        self._interface_ref_cache = {}
        self._interface_ref_inflight = set()
        
        # Loading indicator
        self.loading = LoadingIndicator(self.window)
        
        # Configure styles and create UI
        self._configure_styles()
        self._create_ui()
    
    def _configure_styles(self):
        """Configure UI styles and themes."""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Tree view styling
        style.configure("Hierarchical.Treeview",
                       rowheight=26,
                       font=("Segoe UI", 9),
                       background="white",
                       fieldbackground="white")
        style.configure("Hierarchical.Treeview.Heading",
                       font=("Segoe UI", 9, "bold"),
                       background="#37474F",
                       foreground="white")
        style.map("Hierarchical.Treeview.Heading",
                 background=[('active', '#455A64')])
        
        # Severity colors
        self.severity_colors = {
            Severity.BREAKING: "#FFCDD2",
            Severity.REVIEW: "#FFF9C4",
            Severity.SAFE: "#C8E6C9",
            Severity.INFO: "#B3E5FC"
        }
        
        self.severity_icons = {
            Severity.BREAKING: "🔴",
            Severity.REVIEW: "🟡",
            Severity.SAFE: "🟢",
            Severity.INFO: "ℹ️"
        }
        
        self.type_icons = {
            InterfaceType.FUNCTION: "⚙️",
            InterfaceType.STRUCT: "📦",
            InterfaceType.ENUM: "🔢",
            InterfaceType.MACRO: "#️⃣",
            InterfaceType.TYPEDEF: "📝",
            InterfaceType.EXTERN_VAR: "🌐"
        }
        
        self.change_icons = {
            ChangeType.ADDED: "➕",
            ChangeType.REMOVED: "➖",
            ChangeType.MODIFIED: "✏️"
        }
    
    def _create_ui(self):
        """Create the main UI layout."""
        # Modern header
        self._create_modern_header()
        
        # Input section with improved hierarchy
        self._create_improved_input_section()
        
        # Main analysis area
        self._create_main_analysis_area()
        
        # Enhanced status bar
        self._create_enhanced_status_bar()
    
    def _create_modern_header(self):
        """Create modern gradient header."""
        header = tk.Frame(self.window, bg="#0D47A1", height=55)
        header.pack(fill="x")
        header.pack_propagate(False)
        
        # Title
        title_frame = tk.Frame(header, bg="#0D47A1")
        title_frame.pack(fill="both", expand=True, padx=20)
        
        tk.Label(
            title_frame,
            text="🔬 Interface Difference Analysis",
            font=("Segoe UI", 16, "bold"),
            bg="#0D47A1",
            fg="white"
        ).pack(side="left", pady=10)
        
        tk.Label(
            title_frame,
            text="Enterprise Developer Tool",
            font=("Segoe UI", 9),
            bg="#0D47A1",
            fg="#90CAF9"
        ).pack(side="left", padx=15, pady=10)
        
        # Stats placeholder (will be populated after analysis)
        self.stats_frame = tk.Frame(title_frame, bg="#0D47A1")
        self.stats_frame.pack(side="right", pady=10)
    
    def _create_improved_input_section(self):
        """Create improved input section with better visual hierarchy."""
        input_container = tk.Frame(self.window, bg="#F5F5F5", relief="flat", bd=0)
        input_container.pack(fill="x", padx=0, pady=0)
        
        # Path selection (compact)
        path_frame = tk.Frame(input_container, bg="#F5F5F5")
        path_frame.pack(fill="x", padx=15, pady=5)
        
        # Baseline
        baseline_row = tk.Frame(path_frame, bg="#F5F5F5")
        baseline_row.pack(fill="x", pady=2)
        
        tk.Label(
            baseline_row, text="Baseline:", bg="#F5F5F5",
            font=("Segoe UI", 9, "bold"), width=10, anchor="e"
        ).pack(side="left", padx=5)
        
        baseline_entry = tk.Entry(
            baseline_row, textvariable=self.baseline_root,
            font=("Segoe UI", 9), relief="solid", bd=1
        )
        baseline_entry.pack(side="left", fill="x", expand=True, padx=5)
        
        baseline_btn = tk.Button(
            baseline_row, text="📁", command=self._browse_baseline,
            bg="#1976D2", fg="white", font=("Segoe UI", 9),
            width=3, relief="flat", cursor="hand2"
        )
        baseline_btn.pack(side="left", padx=2)
        ToolTip(baseline_btn, "Select baseline folder (Stream 1)")
        
        # Target
        target_row = tk.Frame(path_frame, bg="#F5F5F5")
        target_row.pack(fill="x", pady=2)
        
        tk.Label(
            target_row, text="Target:", bg="#F5F5F5",
            font=("Segoe UI", 9, "bold"), width=10, anchor="e"
        ).pack(side="left", padx=5)
        
        target_entry = tk.Entry(
            target_row, textvariable=self.target_root,
            font=("Segoe UI", 9), relief="solid", bd=1
        )
        target_entry.pack(side="left", fill="x", expand=True, padx=5)
        
        target_btn = tk.Button(
            target_row, text="📁", command=self._browse_target,
            bg="#1976D2", fg="white", font=("Segoe UI", 9),
            width=3, relief="flat", cursor="hand2"
        )
        target_btn.pack(side="left", padx=2)
        ToolTip(target_btn, "Select target folder (Stream 2)")

        # Interface Diff Scope section
        scope_frame = tk.LabelFrame(input_container, text="🔍 Interface Diff Scope",
                                   bg="#F5F5F5", fg="#1976D2",
                                   font=("Segoe UI", 9, "bold"),
                                   relief="groove", bd=1)
        scope_frame.pack(fill="x", padx=15, pady=5)

        scope_inner = tk.Frame(scope_frame, bg="#F5F5F5")
        scope_inner.pack(fill="x", padx=10, pady=8)

        # Scope mode selection
        scope_mode_frame = tk.Frame(scope_inner, bg="#F5F5F5")
        scope_mode_frame.pack(fill="x", pady=2)

        tk.Label(scope_mode_frame, text="Diff Scope:", bg="#F5F5F5", font=("Segoe UI", 8, "bold")).pack(side="left", padx=5)

        whole_workspace_rb = tk.Radiobutton(
            scope_mode_frame, text="Whole workspace",
            variable=self.diff_scope_mode, value="whole_workspace",
            bg="#F5F5F5", font=("Segoe UI", 8),
            command=self._update_scope_paths
        )
        whole_workspace_rb.pack(side="left", padx=10)

        subfolder_rb = tk.Radiobutton(
            scope_mode_frame, text="Subfolder/module only:",
            variable=self.diff_scope_mode, value="subfolder_only",
            bg="#F5F5F5", font=("Segoe UI", 8),
            command=self._update_scope_paths
        )
        subfolder_rb.pack(side="left", padx=10)

        # Subfolder picker (initially disabled)
        self.subfolder_frame = tk.Frame(scope_inner, bg="#F5F5F5")
        self.subfolder_frame.pack(fill="x", pady=2)

        tk.Label(self.subfolder_frame, text="Subfolder:", bg="#F5F5F5", font=("Segoe UI", 8, "bold"), width=10, anchor="e").pack(side="left", padx=5)

        self.subfolder_path = tk.StringVar()
        subfolder_entry = tk.Entry(
            self.subfolder_frame, textvariable=self.subfolder_path,
            font=("Segoe UI", 9), relief="solid", bd=1, state="disabled"
        )
        subfolder_entry.pack(side="left", fill="x", expand=True, padx=5)

        subfolder_btn = tk.Button(
            self.subfolder_frame, text="📁", command=self._browse_subfolder,
            bg="#1976D2", fg="white", font=("Segoe UI", 9),
            width=3, relief="flat", cursor="hand2", state="disabled"
        )
        subfolder_btn.pack(side="left", padx=2)
        ToolTip(subfolder_btn, "Select subfolder for diff scope")

        # Dependency analysis option
        dep_frame = tk.Frame(scope_inner, bg="#F5F5F5")
        dep_frame.pack(fill="x", pady=5)

        self.full_dep_check = tk.Checkbutton(
            dep_frame, text="Dependency & Impact: always analyze full workspace",
            variable=self.enable_full_dependency,
            bg="#F5F5F5", font=("Segoe UI", 8),
            activebackground="#F5F5F5"
        )
        self.full_dep_check.pack(side="left", padx=5)

        # Action bar with clear hierarchy
        action_frame = tk.Frame(input_container, bg="#FFFFFF", relief="raised", bd=1)
        action_frame.pack(fill="x", padx=15, pady=5)
        
        # Primary action (PROMINENT)
        primary_frame = tk.Frame(action_frame, bg="#FFFFFF")
        primary_frame.pack(side="left", padx=10, pady=4)
        
        self.analyze_btn = tk.Button(
            primary_frame, text="🔍  ANALYZE INTERFACES",
            command=self._start_analysis,
            bg="#2E7D32", fg="white",
            font=("Segoe UI", 9, "bold"),
            padx=20, pady=6,
            relief="flat", cursor="hand2"
        )
        self.analyze_btn.pack()
        ToolTip(self.analyze_btn, "Start comprehensive interface analysis with dependency tracking")
        
        # Dependency checkbox
        if DEPENDENCY_AVAILABLE:
            dep_check = tk.Checkbutton(
                primary_frame, text="Include dependency & impact analysis",
                variable=self.enable_dependency_analysis,
                bg="#FFFFFF", font=("Segoe UI", 8),
                activebackground="#FFFFFF"
            )
            dep_check.pack(pady=2)
        
        # Secondary actions (less prominent)
        secondary_frame = tk.Frame(action_frame, bg="#FFFFFF")
        secondary_frame.pack(side="left", padx=20, pady=4)
        
        tk.Label(
            secondary_frame, text="Export:",
            bg="#FFFFFF", fg="#666", font=("Segoe UI", 8)
        ).pack(side="left", padx=5)
        
        export_csv_btn = tk.Button(
            secondary_frame, text="📊 CSV",
            command=self._export_to_csv,
            bg="#E0E0E0", fg="#333",
            font=("Segoe UI", 8),
            padx=12, pady=5,
            relief="flat", cursor="hand2"
        )
        export_csv_btn.pack(side="left", padx=2)
        ToolTip(export_csv_btn, "Export results to CSV file")
        
        export_html_btn = tk.Button(
            secondary_frame, text="📄 HTML",
            command=self._export_to_html,
            bg="#E0E0E0", fg="#333",
            font=("Segoe UI", 8),
            padx=12, pady=5,
            relief="flat", cursor="hand2"
        )
        export_html_btn.pack(side="left", padx=2)
        ToolTip(export_html_btn, "Generate HTML report")
        
        clear_btn = tk.Button(
            secondary_frame, text="🔄 Clear",
            command=self._clear_results,
            bg="#E0E0E0", fg="#333",
            font=("Segoe UI", 8),
            padx=12, pady=5,
            relief="flat", cursor="hand2"
        )
        clear_btn.pack(side="left", padx=2)
        ToolTip(clear_btn, "Clear all results")
    
    def _create_main_analysis_area(self):
        """Create main analysis area with hierarchical tree and dynamic panel."""
        container = tk.Frame(self.window, bg="#ECEFF1")
        container.pack(fill="both", expand=True, padx=5, pady=2)
        
        # Summary bar
        self._create_summary_bar(container)
        
        # Main paned window
        paned = tk.PanedWindow(
            container, orient=tk.HORIZONTAL,
            sashwidth=8, sashrelief="raised",
            bg="#B0BEC5"
        )
        paned.pack(fill="both", expand=True, pady=2)
        
        # LEFT: Hierarchical tree with filters
        left_panel = self._create_left_panel(paned)
        paned.add(left_panel, minsize=750)
        
        # RIGHT: Dynamic detail panel
        right_panel = self._create_right_panel(paned)
        paned.add(right_panel, minsize=600)
    
    def _create_summary_bar(self, parent):
        """Create dynamic summary bar."""
        self.summary_frame = tk.Frame(parent, bg="white", relief="raised", bd=1)
        self.summary_frame.pack(fill="x", pady=(0, 3))
        
        inner = tk.Frame(self.summary_frame, bg="white")
        inner.pack(fill="x", padx=15, pady=5)
        
        self.summary_label = tk.Label(
            inner,
            text="💡 Select folders above and click 'ANALYZE INTERFACES' to begin",
            bg="white", fg="#666",
            font=("Segoe UI", 9, "italic")
        )
        self.summary_label.pack(side="left")
        
        # Stats boxes (hidden initially)
        self.stats_boxes = tk.Frame(inner, bg="white")
        self.stats_boxes.pack(side="right")
    
    def _create_left_panel(self, parent):
        """Create left panel with filters and hierarchical tree."""
        left_panel = tk.Frame(parent, bg="white", relief="flat")
        
        # Structured filter section
        filter_section = tk.LabelFrame(
            left_panel, text="🔍 Filters & Search",
            bg="white", fg="#1976D2",
            font=("Segoe UI", 9, "bold"),
            relief="groove", bd=1
        )
        filter_section.pack(fill="x", padx=5, pady=5)
        
        # Filter grid
        filter_grid = tk.Frame(filter_section, bg="white")
        filter_grid.pack(fill="x", padx=10, pady=8)
        
        # Row 1: Main filters
        row1 = tk.Frame(filter_grid, bg="white")
        row1.pack(fill="x", pady=2)
        
        self._create_filter_combo(row1, "Severity:", self.filter_severity,
                                  ["All", "Breaking", "Review", "Safe", "Info"],
                                  "Filter by change severity level")
        
        self._create_filter_combo(row1, "Type:", self.filter_type,
                                  ["All", "function", "struct", "enum", "macro", "typedef", "extern_var"],
                                  "Filter by interface type")
        
        self._create_filter_combo(row1, "Change:", self.filter_change,
                                  ["All", "added", "removed", "modified"],
                                  "Filter by change type")
        
        # Row 2: Search
        row2 = tk.Frame(filter_grid, bg="white")
        row2.pack(fill="x", pady=5)
        
        tk.Label(row2, text="Search:", bg="white", font=("Segoe UI", 8, "bold")).pack(side="left", padx=5)
        
        search_entry = tk.Entry(row2, textvariable=self.search_text, font=("Segoe UI", 9), relief="solid", bd=1)
        search_entry.pack(side="left", fill="x", expand=True, padx=5)
        search_entry.bind("<KeyRelease>", lambda e: self._apply_filters())
        ToolTip(search_entry, "Search by interface name or file path")
        
        clear_search_btn = tk.Button(
            row2, text="✖", command=self._clear_filters,
            bg="#ef5350", fg="white", font=("Segoe UI", 8),
            width=2, relief="flat", cursor="hand2"
        )
        clear_search_btn.pack(side="left", padx=2)
        ToolTip(clear_search_btn, "Clear all filters")
        
        # Results count
        self.filter_count_label = tk.Label(
            filter_grid, text="", bg="white", fg="#2E7D32",
            font=("Segoe UI", 8, "bold")
        )
        self.filter_count_label.pack(pady=3)
        
        # Hierarchical tree view
        tree_frame = tk.Frame(left_panel, bg="white")
        tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Tree with scrollbars
        self.tree = ttk.Treeview(
            tree_frame,
            columns=("severity", "type", "change", "summary"),
            show="tree headings",
            style="Hierarchical.Treeview",
            selectmode="browse"
        )
        
        # Column configuration
        self.tree.column("#0", width=300, minwidth=200)  # File/Interface
        self.tree.column("severity", width=80, anchor="center")
        self.tree.column("type", width=80, anchor="center")
        self.tree.column("change", width=80, anchor="center")
        self.tree.column("summary", width=400)
        
        # Headings
        self.tree.heading("#0", text="📁 File / Interface", anchor="w")
        self.tree.heading("severity", text="Severity")
        self.tree.heading("type", text="Type")
        self.tree.heading("change", text="Change")
        self.tree.heading("summary", text="Summary")
        
        # Scrollbars
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        # Grid layout
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        
        # Bind selection
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        
        # Configure tags
        for severity, color in self.severity_colors.items():
            self.tree.tag_configure(severity.value, background=color)
        
        return left_panel
    
    def _create_filter_combo(self, parent, label_text, variable, values, tooltip):
        """Create a filter combobox with label."""
        tk.Label(parent, text=label_text, bg="white", font=("Segoe UI", 8, "bold")).pack(side="left", padx=5)
        
        combo = ttk.Combobox(
            parent, textvariable=variable,
            values=values, width=12,
            state="readonly", font=("Segoe UI", 8)
        )
        combo.pack(side="left", padx=5)
        combo.bind("<<ComboboxSelected>>", lambda e: self._apply_filters())
        ToolTip(combo, tooltip)
    
    def _create_right_panel(self, parent):
        """Create right panel with dynamic detail view."""
        right_panel = tk.Frame(parent, bg="white", relief="flat")
        
        # Quick actions panel
        self.quick_actions = QuickActionsPanel(right_panel, self)
        
        # Tabbed detail view
        self.detail_notebook = ttk.Notebook(right_panel)
        self.detail_notebook.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Tab 1: Summary
        self.tab_summary = self._create_detail_tab("📝 Summary", "#FAFAFA")
        
        # Tab 2: Baseline
        self.tab_baseline = self._create_detail_tab("📦 Baseline (Before)", "#FFF5F5")
        
        # Tab 3: Target
        self.tab_target = self._create_detail_tab("🎯 Target (After)", "#F5FFF5")
        
        # Tab 4: Impact
        self.tab_impact = self._create_detail_tab("⚠️ Impact Analysis", "#FFF9E6")
        
        # Tab 5: Dependencies
        if DEPENDENCY_AVAILABLE:
            self.tab_dependencies = self._create_detail_tab("🔗 Dependencies", "#F0F8FF")
        else:
            self.tab_dependencies = None
        
        # Initial message
        self._show_initial_message()
        
        return right_panel
    
    def _create_detail_tab(self, title, bg_color):
        """Create a detail tab with scrolled text."""
        frame = tk.Frame(self.detail_notebook, bg="white")
        self.detail_notebook.add(frame, text=title)
        
        text_widget = scrolledtext.ScrolledText(
            frame, wrap=tk.WORD, width=60, height=20,
            font=("Consolas", 9), bg=bg_color,
            relief="flat", padx=10, pady=10
        )
        text_widget.pack(fill="both", expand=True, padx=5, pady=5)
        
        return text_widget
    
    def _show_initial_message(self):
        """Show initial message in detail panel."""
        msg = """
Welcome to the Interface Analysis Tool!

Select an interface from the tree on the left to view:
• Detailed change summary
• Before/After comparison
• Impact analysis
• Dependency graph
• Quick actions

Features:
✓ Hierarchical navigation grouped by file
✓ Color-coded severity indicators
✓ Real-time filtering and search
✓ Dependency impact analysis
✓ Export to CSV/HTML
"""
        self.tab_summary.insert("1.0", msg)
        self.tab_summary.config(state="disabled")
    
    def _create_enhanced_status_bar(self):
        """Create enhanced status bar with icons."""
        status_frame = tk.Frame(self.window, bg="#37474F", relief="flat", bd=0)
        status_frame.pack(fill="x", side="bottom")
        
        content = tk.Frame(status_frame, bg="#37474F")
        content.pack(fill="x", padx=10, pady=4)
        
        # Status icon and text
        self.status_icon = tk.Label(
            content, text="●", bg="#37474F", fg="#66BB6A",
            font=("Segoe UI", 10)
        )
        self.status_icon.pack(side="left", padx=5)
        
        self.status_var = tk.StringVar(value="Ready")
        self.status_label = tk.Label(
            content, textvariable=self.status_var,
            bg="#37474F", fg="white",
            font=("Segoe UI", 9), anchor="w"
        )
        self.status_label.pack(side="left", fill="x", expand=True)
        
        # Progress indicator (hidden initially)
        self.progress_var = tk.IntVar(value=0)
        self.progress_bar = ttk.Progressbar(
            content, variable=self.progress_var,
            maximum=100, length=200, mode='determinate'
        )
        # Don't pack initially

    def _show_progress_bar(self):
        """Show progress bar in the status bar."""
        try:
            if not self.progress_bar.winfo_ismapped():
                self.progress_bar.pack(side="right", padx=10)
        except Exception:
            # If widget isn't fully initialized yet, ignore
            pass

    def _hide_progress_bar(self):
        """Hide progress bar in the status bar."""
        try:
            if self.progress_bar.winfo_ismapped():
                self.progress_bar.pack_forget()
        except Exception:
            pass

    def _set_progress(self, percent: int, status: Optional[str] = None):
        """Update progress bar and optional status text (UI thread only)."""
        self.progress_var.set(max(0, min(100, int(percent))))
        if status:
            self.status_var.set(status)
    
    # ==========================================
    # Event Handlers and Business Logic
    # ==========================================
    
    def _browse_baseline(self):
        folder = filedialog.askdirectory(title="Select Baseline Folder (Stream 1)")
        if folder:
            self.baseline_root.set(folder)
            self.diff_scope_baseline_path.set(folder)  # Initially same as root
            self.status_var.set(f"Baseline: {os.path.basename(folder)}")

    def _browse_target(self):
        folder = filedialog.askdirectory(title="Select Target Folder (Stream 2)")
        if folder:
            self.target_root.set(folder)
            self._update_scope_paths()  # Update scope paths based on current mode
            self.status_var.set(f"Target: {os.path.basename(folder)}")

    def _update_scope_paths(self):
        """Update diff scope paths based on selected mode."""
        baseline_root = self.baseline_root.get()
        target_root = self.target_root.get()

        if self.diff_scope_mode.get() == "whole_workspace":
            # Scope is same as roots
            self.diff_scope_baseline_path.set(baseline_root)
            self.diff_scope_target_path.set(target_root)
            # Disable subfolder controls
            self.subfolder_path.set("")
            self._enable_subfolder_controls(False)
        else:  # subfolder_only
            # Use subfolder path if set, otherwise root
            subfolder = self.subfolder_path.get()
            if subfolder and os.path.exists(subfolder):
                # Calculate relative path from root
                try:
                    rel_path = os.path.relpath(subfolder, target_root)
                    if not rel_path.startswith('..'):
                        self.diff_scope_target_path.set(subfolder)
                    else:
                        self.diff_scope_target_path.set(target_root)
                except:
                    self.diff_scope_target_path.set(target_root)
            else:
                self.diff_scope_target_path.set(target_root)

            # For baseline, try to mirror the subfolder if it exists
            if subfolder and target_root:
                try:
                    rel_path = os.path.relpath(subfolder, target_root)
                    if not rel_path.startswith('..'):
                        baseline_subfolder = os.path.join(baseline_root, rel_path)
                        if os.path.exists(baseline_subfolder):
                            self.diff_scope_baseline_path.set(baseline_subfolder)
                        else:
                            self.diff_scope_baseline_path.set(baseline_root)
                    else:
                        self.diff_scope_baseline_path.set(baseline_root)
                except:
                    self.diff_scope_baseline_path.set(baseline_root)
            else:
                self.diff_scope_baseline_path.set(baseline_root)

            # Enable subfolder controls
            self._enable_subfolder_controls(True)

    def _enable_subfolder_controls(self, enable):
        """Enable or disable subfolder selection controls."""
        state = "normal" if enable else "disabled"
        try:
            # Enable/disable the entry and button
            for child in self.subfolder_frame.winfo_children():
                if isinstance(child, tk.Entry) or isinstance(child, tk.Button):
                    child.config(state=state)
        except:
            pass

    def _browse_subfolder(self):
        """Browse for subfolder within target root."""
        target_root = self.target_root.get()
        if not target_root:
            messagebox.showwarning("No Target", "Please select target folder first")
            return

        initial_dir = target_root
        folder = filedialog.askdirectory(title="Select Subfolder for Diff Scope",
                                        initialdir=initial_dir)
        if folder:
            # Validate it's within target root
            try:
                rel_path = os.path.relpath(folder, target_root)
                if rel_path.startswith('..'):
                    messagebox.showwarning("Invalid Subfolder",
                                          "Selected folder must be within the target root folder")
                    return
            except:
                messagebox.showwarning("Invalid Subfolder",
                                      "Selected folder must be within the target root folder")
                return

            self.subfolder_path.set(folder)
            self._update_scope_paths()
    
    def _start_analysis(self):
        """Start interface analysis with loading indicator."""
        if not self.baseline_root.get() or not self.target_root.get():
            messagebox.showwarning("Missing Input",
                                  "Please select both baseline and target folders")
            return
        
        # Disable analyze button
        self.analyze_btn.config(state="disabled", text="⏳ ANALYZING...")

        # Show progress bar
        self._show_progress_bar()
        self._set_progress(0, "🔄 Starting analysis...")
        self.status_icon.config(fg="#FFC107")
        
        # Start analysis in background
        thread = threading.Thread(target=self._analyze_interfaces, daemon=True)
        thread.start()
    
    def _analyze_interfaces(self):
        """Perform interface analysis."""
        try:
            self.is_analyzing = True
            
            # Phase 1: Interface diff
            self.window.after(0, lambda: self._set_progress(10, "🔄 Phase 1/3: Parsing & comparing interfaces..."))
            
            engine = InterfaceDiffEngine(ignore_patterns=['*_test.c', '*_mock.c'])

            self.diff_result = engine.compare_baselines(
                self.baseline_root.get(),
                self.target_root.get(),
                self.diff_scope_baseline_path.get(),
                self.diff_scope_target_path.get()
            )

            self.window.after(0, lambda: self._set_progress(70, "🔄 Phase 2/3: Preparing results..."))
            
            # Phase 2: Build dependency graphs (if enabled and full workspace analysis enabled)
            if self.enable_dependency_analysis.get() and self.enable_full_dependency.get() and DEPENDENCY_AVAILABLE:
                self.window.after(0, lambda: self._set_progress(80, "🔄 Phase 3/3: Building dependency graph..."))

                try:
                    builder = DependencyGraphBuilder()
                    self.dependency_graph_target = builder.build_graph(self.target_root.get())
                    self.impact_analyzer_target = ImpactAnalyzer(self.dependency_graph_target)
                except Exception as e:
                    logger.exception("Dependency analysis failed")

            self.window.after(0, lambda: self._set_progress(95, "🔄 Rendering results..."))
            
            # Display results
            self.window.after(0, self._display_results)
            self.window.after(0, lambda: self._set_progress(100, "✅ Analysis complete"))
            self.window.after(0, lambda: self.status_icon.config(fg="#66BB6A"))
            # Hide progress bar shortly after completion
            self.window.after(800, self._hide_progress_bar)
            
        except Exception as e:
            self.window.after(0, lambda: messagebox.showerror("Analysis Error", f"Error:\n\n{str(e)}"))
            self.window.after(0, lambda: self.status_var.set(f"❌ Analysis failed: {str(e)}"))
            self.window.after(0, lambda: self.status_icon.config(fg="#EF5350"))
            self.window.after(0, lambda: self._set_progress(0))
            self.window.after(0, self._hide_progress_bar)
            logger.exception("Analysis failed")
        finally:
            self.is_analyzing = False
            self.window.after(0, lambda: self.analyze_btn.config(state="normal", text="🔍  ANALYZE INTERFACES"))
    
    def _display_results(self):
        """Display results in hierarchical tree."""
        # Clear tree
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        self.all_diffs = []
        self.file_groups = defaultdict(list)
        
        # Group diffs by file
        for file_path, file_diff in sorted(self.diff_result.file_diffs.items()):
            for diff in file_diff.diffs:
                self.all_diffs.append((diff, file_path))
                self.file_groups[file_path].append(diff)
        
        # Build hierarchical tree
        self._build_hierarchical_tree(self.file_groups)
        
        # Update summary
        self._update_summary_stats()

        # No popup on completion (keep it inline)
        total = len(self.all_diffs)
        self.status_var.set(
            f"✅ Analysis complete: {total} changes | 🔴 {self.diff_result.breaking_changes} | 🟡 {self.diff_result.review_needed} | 🟢 {self.diff_result.safe_changes}"
        )
    
    def _build_hierarchical_tree(self, file_groups):
        """Build hierarchical tree grouped by file."""
        # Clear the mapping
        self.tree_item_to_diff = {}
        
        for file_path, diffs in sorted(file_groups.items()):
            # Calculate file-level stats
            breaking = sum(1 for d in diffs if d.severity == Severity.BREAKING)
            review = sum(1 for d in diffs if d.severity == Severity.REVIEW)
            safe = sum(1 for d in diffs if d.severity == Severity.SAFE)
            
            # Determine file severity (highest severity wins)
            if breaking > 0:
                file_severity = Severity.BREAKING
                severity_str = f"🔴 {breaking}"
            elif review > 0:
                file_severity = Severity.REVIEW
                severity_str = f"🟡 {review}"
            else:
                file_severity = Severity.SAFE
                severity_str = f"🟢 {safe}"
            
            # Insert file node
            file_node = self.tree.insert(
                "", "end",
                text=f"📁 {file_path}",
                values=(severity_str, f"{len(diffs)} changes", "", f"{breaking}🔴 {review}🟡 {safe}🟢"),
                tags=(file_severity.value,),
                open=False  # Collapsed by default
            )
            
            # Insert interface children
            for diff in sorted(diffs, key=lambda d: (d.severity.value, d.element_name)):
                icon = self.type_icons.get(diff.interface_type, "")
                change_icon = self.change_icons.get(diff.change_type, "")
                severity_icon = self.severity_icons.get(diff.severity, "")
                
                summary = diff.diff_summary[:80] + "..." if len(diff.diff_summary) > 80 else diff.diff_summary
                
                # Insert item and store mapping
                item_id = self.tree.insert(
                    file_node, "end",
                    text=f"  {icon} {diff.element_name}",
                    values=(
                        f"{severity_icon}",
                        diff.interface_type.value,
                        f"{change_icon} {diff.change_type.value}",
                        summary
                    ),
                    tags=(diff.severity.value,)
                )
                
                # Map tree item to diff for easy retrieval
                self.tree_item_to_diff[item_id] = (diff, file_path)
    
    def _update_summary_stats(self):
        """Update summary bar with statistics."""
        total = len(self.all_diffs)
        breaking = self.diff_result.breaking_changes
        review = self.diff_result.review_needed
        safe = self.diff_result.safe_changes

        # Build scope info
        scope_info = self._get_scope_display_info()

        # Update main summary
        self.summary_label.config(
            text=f"📊 Analysis Results: {total} interfaces analyzed across {len(self.file_groups)} files | {scope_info}",
            font=("Segoe UI", 9, "bold"),
            fg="#1976D2"
        )
        
        # Clear and rebuild stats boxes
        for widget in self.stats_boxes.winfo_children():
            widget.destroy()
        
        # Add stat boxes
        self._add_stat_box(self.stats_boxes, breaking, "Breaking", "#EF5350")
        self._add_stat_box(self.stats_boxes, review, "Review", "#FFC107")
        self._add_stat_box(self.stats_boxes, safe, "Safe", "#66BB6A")
        
        # Update filter count
        self.filter_count_label.config(text=f"Showing all {total} changes")
    
    def _get_scope_display_info(self):
        """Get display string for current scope settings."""
        if self.diff_scope_mode.get() == "whole_workspace":
            diff_scope = "full workspace"
        else:
            target_root = self.target_root.get()
            diff_scope_path = self.diff_scope_target_path.get()
            if diff_scope_path and diff_scope_path != target_root:
                try:
                    rel_path = os.path.relpath(diff_scope_path, target_root)
                    diff_scope = rel_path.replace('\\', '/')
                except:
                    diff_scope = "subfolder"
            else:
                diff_scope = "full workspace"

        dep_scope = "full workspace" if self.enable_full_dependency.get() else "diff scope only"

        return f"Diff scope: {diff_scope} | Dependency scope: {dep_scope}"

    def _add_stat_box(self, parent, value, label, color):
        """Add a stat box to summary."""
        box = tk.Frame(parent, bg=color, relief="flat", bd=0)
        box.pack(side="left", padx=5)

        tk.Label(
            box, text=str(value),
            bg=color, fg="white",
            font=("Segoe UI", 14, "bold")
        ).pack(padx=10, pady=2)

        tk.Label(
            box, text=label,
            bg=color, fg="white",
            font=("Segoe UI", 7)
        ).pack(padx=10, pady=(0, 4))
    
    def _on_tree_select(self, event):
        """Handle tree selection - improved with direct mapping."""
        selection = self.tree.selection()
        if not selection:
            return
        
        item_id = selection[0]
        
        # Check if this item maps to a diff (interface node, not file node)
        if item_id in self.tree_item_to_diff:
            diff, file_path = self.tree_item_to_diff[item_id]
            self._display_diff_details(diff, file_path)
            self.quick_actions.enable_actions(diff, file_path)
        else:
            # File node selected - could show file-level summary in the future
            # For now, just disable quick actions
            self.quick_actions.disable_actions()
    
    def _display_diff_details(self, diff, file_path):
        """Display comprehensive diff details in right panel."""
        # Clear all tabs
        for tab in [self.tab_summary, self.tab_baseline, self.tab_target, self.tab_impact]:
            tab.config(state="normal")
            tab.delete("1.0", tk.END)
        
        if self.tab_dependencies:
            self.tab_dependencies.config(state="normal")
            self.tab_dependencies.delete("1.0", tk.END)
        
        # TAB 1: Summary
        self._write_summary_tab(self.tab_summary, diff, file_path)
        
        # TAB 2: Baseline
        if diff.baseline_element:
            self._write_element_tab(self.tab_baseline, diff.baseline_element, "BASELINE (BEFORE)")
        else:
            self.tab_baseline.insert("1.0", "Not present in baseline (newly added)")
        
        # TAB 3: Target
        if diff.target_element:
            self._write_element_tab(self.tab_target, diff.target_element, "TARGET (AFTER)")
        else:
            self.tab_target.insert("1.0", "Not present in target (removed)")
        
        # TAB 4: Impact
        self._write_impact_tab(self.tab_impact, diff, file_path)
        
        # TAB 5: Dependencies
        if self.tab_dependencies:
            self._write_dependencies_tab(self.tab_dependencies, diff, file_path)
        
        # Make all read-only
        for tab in [self.tab_summary, self.tab_baseline, self.tab_target, self.tab_impact]:
            tab.config(state="disabled")
        if self.tab_dependencies:
            self.tab_dependencies.config(state="disabled")

    def _add_suggestions(self, widget, diff, file_path, impact):
        """Add deterministic suggestions based on change characteristics."""
        widget.insert("end", "\n═══ SUGGESTED ACTIONS ═══\n\n")

        suggestions = []

        # Severity-based suggestions
        if diff.severity == Severity.BREAKING:
            suggestions.append("🔴 HIGH PRIORITY: This breaking change requires immediate attention")
            suggestions.append("  • Update all call sites before deploying")
            suggestions.append("  • Consider backward compatibility wrapper if possible")

            if diff.interface_type == InterfaceType.FUNCTION:
                suggestions.append("  • Function signature change - update all callers")
            elif diff.interface_type == InterfaceType.STRUCT:
                suggestions.append("  • Struct change - may break memory layout")

        elif diff.severity == Severity.REVIEW:
            suggestions.append("🟡 MEDIUM PRIORITY: Manual review recommended")
            suggestions.append("  • Check for implicit assumptions in calling code")

        else:  # SAFE
            suggestions.append("🟢 LOW PRIORITY: Appears safe to deploy")
            suggestions.append("  • Still verify in test environment")

        # Impact-based suggestions
        if impact and impact.all_dependents:
            blast_radius = len(impact.all_dependents)
            if blast_radius > 10:
                suggestions.append(f"💥 HIGH BLAST RADIUS: {blast_radius} files affected")
                suggestions.append("  • Plan phased rollout")
                suggestions.append("  • Consider feature flags for gradual migration")
            elif blast_radius > 5:
                suggestions.append(f"⚠️ MEDIUM BLAST RADIUS: {blast_radius} files affected")
                suggestions.append("  • Update in logical groups")
            else:
                suggestions.append(f"✅ LOW BLAST RADIUS: {blast_radius} files affected")
                suggestions.append("  • Can be updated incrementally")

            # Suggest top impacted files
            if impact.direct_dependents:
                top_deps = sorted(impact.direct_dependents)[:5]
                suggestions.append(f"  • Start with direct dependents: {', '.join(top_deps)}")

        # Interface type specific suggestions
        if diff.interface_type == InterfaceType.FUNCTION:
            suggestions.append("🔧 FUNCTION CHANGE: Focus on parameter compatibility")
        elif diff.interface_type == InterfaceType.STRUCT:
            suggestions.append("📦 STRUCT CHANGE: Check for padding/size implications")
        elif diff.interface_type == InterfaceType.ENUM:
            suggestions.append("🔢 ENUM CHANGE: Verify switch statements and default cases")

        # Display suggestions
        for suggestion in suggestions:
            widget.insert("end", f"{suggestion}\n")

        widget.insert("end", "\n")

        # Kick off reference search asynchronously (doesn't block UI)
        if self.tab_dependencies:
            self._start_interface_reference_search(diff, file_path)
    
    def _write_summary_tab(self, widget, diff, file_path):
        """Write summary information."""
        widget.insert("end", "═══ INTERFACE CHANGE SUMMARY ═══\n\n", "header")
        widget.insert("end", f"File: {file_path}\n")
        widget.insert("end", f"Interface: {diff.element_name}\n")
        widget.insert("end", f"Type: {diff.interface_type.value}\n")
        widget.insert("end", f"Change: {diff.change_type.value}\n")
        widget.insert("end", f"Severity: {diff.severity.value} {self.severity_icons.get(diff.severity, '')}\n")
        widget.insert("end", f"Functional Area: {diff.functional_area}\n\n")
        widget.insert("end", "Summary:\n")
        widget.insert("end", f"{diff.diff_summary}\n\n")
        
        if diff.diff_details:
            widget.insert("end", "Detailed Changes:\n")
            for detail in diff.diff_details:
                widget.insert("end", f"  • {detail}\n")
    
    def _write_element_tab(self, widget, elem, title):
        """Write interface element details."""
        widget.insert("end", f"═══ {title} ═══\n\n")
        widget.insert("end", f"Line {elem.line_number}: {elem.signature}\n\n")
        
        if elem.type == InterfaceType.FUNCTION:
            widget.insert("end", f"Return Type: {elem.return_type}\n")
            if elem.is_static:
                widget.insert("end", "Static: Yes\n")
            if elem.parameters:
                widget.insert("end", "\nParameters:\n")
                for i, param in enumerate(elem.parameters, 1):
                    widget.insert("end", f"  {i}. {param.type} {param.name}\n")
        elif elem.type == InterfaceType.STRUCT:
            if elem.fields:
                widget.insert("end", "Fields:\n")
                for field in elem.fields:
                    widget.insert("end", f"  {field.type} {field.name}\n")
        elif elem.type == InterfaceType.ENUM:
            if elem.values:
                widget.insert("end", "Values:\n")
                for val in elem.values:
                    widget.insert("end", f"  {val.name}\n")
        
        widget.insert("end", f"\nRaw Source:\n{elem.raw_text}\n")
    
    def _write_impact_tab(self, widget, diff, file_path):
        """Write impact analysis."""
        widget.insert("end", "═══ IMPACT ANALYSIS ═══\n\n")
        widget.insert("end", f"Severity: {diff.severity.value.upper()} {self.severity_icons.get(diff.severity, '')}\n\n")
        
        if diff.severity == Severity.BREAKING:
            widget.insert("end", "⚠️ BREAKING CHANGE\n\n")
            widget.insert("end", "This will cause compilation errors.\n\n")
            widget.insert("end", "Required Actions:\n")
            widget.insert("end", "1. Find all call sites\n")
            widget.insert("end", "2. Update to match new signature\n")
            widget.insert("end", "3. Update tests\n")
            widget.insert("end", "4. Verify functionality\n\n")
        
        # Add dependency impact if available
        if self.impact_analyzer_target:
            impact = self.impact_analyzer_target.analyze_impact(file_path)
            widget.insert("end", "\n═══ DEPENDENCY IMPACT ═══\n\n")
            widget.insert("end", f"Files Affected: {len(impact.all_dependents)}\n")

            # Categorize impact by scope
            if impact.all_dependents:
                in_scope_impact = []
                out_of_scope_impact = []

                target_root = self.target_root.get()
                diff_scope = self.diff_scope_target_path.get()

                for dep in impact.all_dependents:
                    if diff_scope and diff_scope != target_root:
                        dep_abs = os.path.join(target_root, dep)
                        try:
                            rel_to_scope = os.path.relpath(dep_abs, diff_scope)
                            if not rel_to_scope.startswith('..'):
                                in_scope_impact.append(dep)
                            else:
                                out_of_scope_impact.append(dep)
                        except:
                            out_of_scope_impact.append(dep)
                    else:
                        in_scope_impact.append(dep)

                widget.insert("end", f"  • In-scope: {len(in_scope_impact)}\n")
                widget.insert("end", f"  • Out-of-scope: {len(out_of_scope_impact)}\n")
            else:
                widget.insert("end", f"  • Direct: {len(impact.direct_dependents)}\n")

            widget.insert("end", f"  • Headers: {impact.headers_affected}\n")
            widget.insert("end", f"  • Sources: {impact.sources_affected}\n")

        # Add suggestions based on severity and impact
        impact_data = None
        if self.impact_analyzer_target:
            try:
                impact_data = self.impact_analyzer_target.analyze_impact(file_path)
            except:
                pass
        self._add_suggestions(widget, diff, file_path, impact_data)
    
    def _write_dependencies_tab(self, widget, diff, file_path):
        """Write dependency information (file include graph + interface references placeholder)."""
        widget.insert("end", f"═══ DEPENDENCIES FOR {file_path} ═══\n\n")

        if self.dependency_graph_target and self.impact_analyzer_target:
            impact = self.impact_analyzer_target.analyze_impact(file_path)
            node = self.dependency_graph_target.get_node(file_path)

            if node:
                widget.insert("end", f"📥 File Includes ({len(node.resolved_includes)}):\n")
                if node.resolved_includes:
                    for inc in sorted(node.resolved_includes)[:25]:
                        widget.insert("end", f"  • {inc}\n")
                else:
                    widget.insert("end", "  (none)\n")

                widget.insert("end", f"\n📤 Reverse Includes / Dependents ({len(node.included_by)}):\n")
                if node.included_by:
                    # Categorize dependents by scope
                    in_scope = []
                    out_of_scope = []

                    target_root = self.target_root.get()
                    diff_scope = self.diff_scope_target_path.get()

                    for dep in sorted(node.included_by):
                        if diff_scope and diff_scope != target_root:
                            # Check if dependent is within the diff scope
                            dep_abs = os.path.join(target_root, dep)
                            try:
                                rel_to_scope = os.path.relpath(dep_abs, diff_scope)
                                if not rel_to_scope.startswith('..'):
                                    in_scope.append(dep)
                                else:
                                    out_of_scope.append(dep)
                            except:
                                out_of_scope.append(dep)
                        else:
                            # Whole workspace scope, everything is in scope
                            in_scope.append(dep)

                    widget.insert("end", f"    In-scope dependents ({len(in_scope)}):\n")
                    for dep in in_scope[:15]:  # Limit to top 15
                        widget.insert("end", f"      • {dep}\n")
                    if len(in_scope) > 15:
                        widget.insert("end", f"      ... and {len(in_scope) - 15} more\n")

                    widget.insert("end", f"    Out-of-scope dependents ({len(out_of_scope)}):\n")
                    for dep in out_of_scope[:15]:  # Limit to top 15
                        widget.insert("end", f"      • {dep}\n")
                    if len(out_of_scope) > 15:
                        widget.insert("end", f"      ... and {len(out_of_scope) - 15} more\n")
                else:
                    widget.insert("end", "  (none)\n")

                # Categorize impact radius by scope
                if impact.all_dependents:
                    in_scope_impact = []
                    out_of_scope_impact = []

                    target_root = self.target_root.get()
                    diff_scope = self.diff_scope_target_path.get()

                    for dep in impact.all_dependents:
                        if diff_scope and diff_scope != target_root:
                            dep_abs = os.path.join(target_root, dep)
                            try:
                                rel_to_scope = os.path.relpath(dep_abs, diff_scope)
                                if not rel_to_scope.startswith('..'):
                                    in_scope_impact.append(dep)
                                else:
                                    out_of_scope_impact.append(dep)
                            except:
                                out_of_scope_impact.append(dep)
                        else:
                            in_scope_impact.append(dep)

                    widget.insert("end", f"\n🎯 Impact Radius: {len(impact.all_dependents)} file(s) transitively depend on this file\n")
                    widget.insert("end", f"    In-scope impact: {len(in_scope_impact)}\n")
                    widget.insert("end", f"    Out-of-scope impact: {len(out_of_scope_impact)}\n")
                    widget.insert("end", f"    Headers affected:  {impact.headers_affected}\n")
                    widget.insert("end", f"    Sources affected:  {impact.sources_affected}\n")
                else:
                    widget.insert("end", f"\n🎯 Impact Radius: {len(impact.all_dependents)} file(s) transitively depend on this file\n")
            else:
                widget.insert("end", "Dependency graph node not found for this file (path resolution issue).\n")
        else:
            widget.insert("end", "Dependency graph not built (enable it and re-run analysis).\n")

        widget.insert("end", "\n═══ INTERFACE REFERENCES (CALL SITES) ═══\n\n")
        widget.insert(
            "end",
            f"Selected interface: {diff.element_name} ({diff.interface_type.value})\n\n"
        )
        widget.insert(
            "end",
            "Searching references... (this runs in background and will update here)\n"
        )

    def _start_interface_reference_search(self, diff, rel_file_path: str):
        """Start a background search for interface references and update Dependencies tab."""
        if not self.diff_result or not self.tab_dependencies:
            return
        if not self.target_root.get():
            return

        root = self.target_root.get()
        key = (root, diff.element_name, diff.interface_type.value)

        # If cached, update immediately
        if key in self._interface_ref_cache:
            self._update_dependencies_with_references(diff, rel_file_path, self._interface_ref_cache[key])
            return

        # Prevent duplicate inflight searches
        if key in self._interface_ref_inflight:
            return
        self._interface_ref_inflight.add(key)

        def worker():
            try:
                refs = self._find_interface_references(
                    root_path=root,
                    interface_name=diff.element_name,
                    interface_type=diff.interface_type,
                    exclude_rel_path=rel_file_path,
                    exclude_line=(diff.target_element.line_number if diff.target_element else None)
                )
            except Exception:
                logger.exception("Interface reference search failed")
                refs = []

            self._interface_ref_cache[key] = refs
            self._interface_ref_inflight.discard(key)

            # Update UI in main thread
            self.window.after(0, lambda: self._update_dependencies_with_references(diff, rel_file_path, refs))

        threading.Thread(target=worker, daemon=True).start()

    def _find_interface_references(
        self,
        root_path: str,
        interface_name: str,
        interface_type: InterfaceType,
        exclude_rel_path: Optional[str] = None,
        exclude_line: Optional[int] = None,
        max_results: int = 300,
    ):
        """Find call sites/references for a given interface name under root_path.

        Practical static analysis:
        - For functions: looks for `name(` patterns.
        - For other types: looks for word-boundary occurrences.
        """

        exts = {'.h', '.hpp', '.hh', '.hxx', '.c', '.cc', '.cpp', '.cxx'}

        if interface_type == InterfaceType.FUNCTION:
            pattern = re.compile(rf"\b{re.escape(interface_name)}\s*\(")
        else:
            pattern = re.compile(rf"\b{re.escape(interface_name)}\b")

        results = []
        root_path = os.path.abspath(root_path)

        for dirpath, dirnames, filenames in os.walk(root_path):
            dirnames[:] = [d for d in dirnames if not d.startswith('.')]
            for filename in filenames:
                ext = os.path.splitext(filename)[1].lower()
                if ext not in exts:
                    continue

                abs_path = os.path.join(dirpath, filename)
                rel_path = os.path.relpath(abs_path, root_path).replace('\\', '/')

                try:
                    with open(abs_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        lines = content.splitlines()

                        # Preprocess content to remove strings and comments (similar to parser)
                        processed_content = self._preprocess_content_for_search(content)

                        for idx, line in enumerate(lines, start=1):
                            original_line = line
                            processed_line = processed_content.splitlines()[idx-1] if idx-1 < len(processed_content.splitlines()) else ""

                            if not pattern.search(processed_line):
                                continue

                            # Additional heuristics for functions: exclude likely definitions
                            if interface_type == InterfaceType.FUNCTION:
                                # Skip if line looks like a function definition (has return type before name)
                                stripped = original_line.strip()
                                # Check for common return type patterns before function name
                                func_def_pattern = re.compile(rf'\b(?:void|int|char|float|double|bool|uint\d+_t|int\d+_t|struct\s+\w+|enum\s+\w+|const\s+\w+|\w+\s*\*)\s+(?:\w+\s+)*{re.escape(interface_name)}\s*\(')
                                if func_def_pattern.search(stripped):
                                    continue

                                # Skip if it's clearly a declaration/definition in header
                                if abs_path.endswith('.h') or abs_path.endswith('.hpp'):
                                    # Check for patterns like "extern", "static", or ending with ";"
                                    if re.search(r'\b(?:extern|static)\b', stripped) or stripped.rstrip().endswith(';'):
                                        continue

                            # Heuristic: exclude the definition/declaration line in its own file
                            if exclude_rel_path and rel_path == exclude_rel_path.replace('\\', '/'):
                                if exclude_line and abs(idx - exclude_line) <= 2:
                                    continue

                            results.append((rel_path, idx, original_line.strip()))
                            if len(results) >= max_results:
                                return results
                except Exception:
                    continue

        return results

    def _preprocess_content_for_search(self, content: str) -> str:
        """Remove string literals and comments to avoid false regex matches."""
        # Remove string literals
        content = re.sub(r'"(?:[^"\\]|\\.)*"', '""', content)
        # Remove character literals
        content = re.sub(r"'(?:[^'\\]|\\.)*'", "''", content)
        # Remove multi-line comments
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        # Remove single-line comments
        content = re.sub(r'//.*', '', content)
        return content

    def _update_dependencies_with_references(self, diff, rel_file_path: str, refs):
        """Update the Dependencies tab with reference results."""
        if not self.tab_dependencies:
            return

        self.tab_dependencies.config(state="normal")
        self.tab_dependencies.delete("1.0", tk.END)
        self._write_dependencies_tab(self.tab_dependencies, diff, rel_file_path)

        self.tab_dependencies.insert("end", "\n\n")
        if not refs:
            self.tab_dependencies.insert("end", "No references found in target codebase.\n")
            self.tab_dependencies.config(state="disabled")
            return

        # Categorize references by scope
        in_scope_refs = defaultdict(list)
        out_of_scope_refs = defaultdict(list)

        target_root = self.target_root.get()
        diff_scope = self.diff_scope_target_path.get()

        for relp, line_no, text in refs:
            if diff_scope and diff_scope != target_root:
                file_abs = os.path.join(target_root, relp)
                try:
                    rel_to_scope = os.path.relpath(file_abs, diff_scope)
                    if not rel_to_scope.startswith('..'):
                        in_scope_refs[relp].append((line_no, text))
                    else:
                        out_of_scope_refs[relp].append((line_no, text))
                except:
                    out_of_scope_refs[relp].append((line_no, text))
            else:
                in_scope_refs[relp].append((line_no, text))

        total_in_scope = sum(len(v) for v in in_scope_refs.values())
        total_out_scope = sum(len(v) for v in out_of_scope_refs.values())
        total = total_in_scope + total_out_scope

        self.tab_dependencies.insert("end", f"Found {total} reference(s) across {len(in_scope_refs) + len(out_of_scope_refs)} file(s):\n")
        self.tab_dependencies.insert("end", f"  • {total_in_scope} in scope, {total_out_scope} out of scope\n\n")

        # Display in-scope references
        if in_scope_refs:
            self.tab_dependencies.insert("end", f"📄 In-scope files ({len(in_scope_refs)} files, {total_in_scope} refs):\n")
            for relp in sorted(in_scope_refs.keys()):
                self.tab_dependencies.insert("end", f"  📄 {relp} ({len(in_scope_refs[relp])})\n")
                for line_no, text in in_scope_refs[relp][:10]:  # Limit per file
                    self.tab_dependencies.insert("end", f"    L{line_no}: {text}\n")
                if len(in_scope_refs[relp]) > 10:
                    self.tab_dependencies.insert("end", f"    ... and {len(in_scope_refs[relp]) - 10} more\n")
            self.tab_dependencies.insert("end", "\n")

        # Display out-of-scope references
        if out_of_scope_refs:
            self.tab_dependencies.insert("end", f"📄 Out-of-scope files ({len(out_of_scope_refs)} files, {total_out_scope} refs):\n")
            for relp in sorted(out_of_scope_refs.keys()):
                self.tab_dependencies.insert("end", f"  📄 {relp} ({len(out_of_scope_refs[relp])})\n")
                for line_no, text in out_of_scope_refs[relp][:10]:  # Limit per file
                    self.tab_dependencies.insert("end", f"    L{line_no}: {text}\n")
                if len(out_of_scope_refs[relp]) > 10:
                    self.tab_dependencies.insert("end", f"    ... and {len(out_of_scope_refs[relp]) - 10} more\n")
            self.tab_dependencies.insert("end", "\n")

        self.tab_dependencies.config(state="disabled")
    
    def _apply_filters(self):
        """Apply filters to tree view."""
        if not self.all_diffs:
            return

        filtered = self.all_diffs

        # Severity filter
        severity_label = self.filter_severity.get()
        if severity_label != "All":
            sev_map = {
                "Breaking": Severity.BREAKING,
                "Review": Severity.REVIEW,
                "Safe": Severity.SAFE,
                "Info": Severity.INFO,
            }
            target_sev = sev_map.get(severity_label)
            if target_sev:
                filtered = [(d, fp) for d, fp in filtered if d.severity == target_sev]

        # Type filter
        type_label = self.filter_type.get()
        if type_label != "All":
            filtered = [(d, fp) for d, fp in filtered if d.interface_type.value == type_label]

        # Change filter
        change_label = self.filter_change.get()
        if change_label != "All":
            filtered = [(d, fp) for d, fp in filtered if d.change_type.value == change_label]

        # Search filter
        search = (self.search_text.get() or "").strip().lower()
        if search:
            filtered = [
                (d, fp)
                for d, fp in filtered
                if search in d.element_name.lower()
                or search in fp.lower()
                or search in (d.diff_summary or "").lower()
            ]

        # Group filtered diffs by file
        grouped = defaultdict(list)
        for d, fp in filtered:
            grouped[fp].append(d)

        # Rebuild the tree
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._build_hierarchical_tree(grouped)

        self.filter_count_label.config(text=f"Showing {len(filtered)} of {len(self.all_diffs)} changes")
    
    def _clear_filters(self):
        """Clear all filters."""
        self.filter_severity.set("All")
        self.filter_type.set("All")
        self.filter_change.set("All")
        self.filter_area.set("All")
        self.search_text.set("")
        self._apply_filters()
    
    def _clear_results(self):
        """Clear all results."""
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.all_diffs = []
        self.file_groups.clear()
        self.tree_item_to_diff.clear()  # Clear the mapping
        self._interface_ref_cache.clear()
        self._interface_ref_inflight.clear()
        self.diff_result = None
        
        for tab in [self.tab_summary, self.tab_baseline, self.tab_target, self.tab_impact]:
            tab.config(state="normal")
            tab.delete("1.0", tk.END)
            tab.config(state="disabled")
        
        if self.tab_dependencies:
            self.tab_dependencies.config(state="normal")
            self.tab_dependencies.delete("1.0", tk.END)
            self.tab_dependencies.config(state="disabled")
        
        self._show_initial_message()
        self.quick_actions.disable_actions()
        self.summary_label.config(
            text="💡 Select folders above and click 'ANALYZE INTERFACES' to begin",
            fg="#666", font=("Segoe UI", 9, "italic")
        )
        self.status_var.set("Ready")
    
    def _export_to_csv(self):
        """Export to CSV."""
        if not self.diff_result:
            messagebox.showwarning("No Data", "No analysis results to export")
            return
        
        csv_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile=f"interface_diff_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        
        if csv_path:
            try:
                with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(["File", "Interface", "Type", "Change", "Severity", "Summary"])
                    
                    for diff, file_path in self.all_diffs:
                        writer.writerow([
                            file_path, diff.element_name, diff.interface_type.value,
                            diff.change_type.value, diff.severity.value, diff.diff_summary
                        ])
                
                messagebox.showinfo("Exported", f"Exported to:\n{csv_path}")
                self.status_var.set(f"✅ Exported to CSV")
            except Exception as e:
                messagebox.showerror("Export Failed", f"Error:\n{e}")
    
    def _export_to_html(self):
        """Export to HTML."""
        if not self.diff_result:
            messagebox.showwarning("No Data", "No analysis results to export")
            return

        html_path = filedialog.asksaveasfilename(
            defaultextension=".html",
            filetypes=[("HTML files", "*.html"), ("All files", "*.*")],
            initialfile=f"interface_diff_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html",
            title="Export Interface Diff Report"
        )

        if not html_path:
            return

        try:
            report_html = self._generate_html_report()
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(report_html)

            self.status_var.set(f"✅ Exported to HTML")
            messagebox.showinfo("Exported", f"HTML report exported to:\n{html_path}")

            if messagebox.askyesno("Open Report", "Would you like to open the HTML report now?"):
                webbrowser.open(f'file://{os.path.abspath(html_path)}')
        except Exception as e:
            logger.exception("HTML export failed")
            messagebox.showerror("Export Failed", f"Error exporting to HTML:\n\n{str(e)}")

    def _generate_html_report(self):
        """Generate a standalone HTML interface-analysis report."""
        generated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        baseline_path = self._html_escape(getattr(self.diff_result, "baseline_path", self.baseline_root.get()))
        target_path = self._html_escape(getattr(self.diff_result, "target_path", self.target_root.get()))
        scope_info = self._html_escape(self._get_scope_display_info())

        total_changes = len(self.all_diffs)
        files_changed = len(self.file_groups)
        breaking = getattr(self.diff_result, "breaking_changes", 0)
        review = getattr(self.diff_result, "review_needed", 0)
        safe = getattr(self.diff_result, "safe_changes", 0)

        rows = []
        for diff, file_path in sorted(
            self.all_diffs,
            key=lambda item: (
                self._severity_sort_key(item[0].severity),
                item[1].lower(),
                item[0].element_name.lower()
            )
        ):
            severity = self._enum_value(diff.severity)
            change_type = self._enum_value(diff.change_type)
            interface_type = self._enum_value(diff.interface_type)
            details = "<br>".join(self._html_escape(detail) for detail in (diff.diff_details or []))
            if not details:
                details = "<span class=\"muted\">No extra details</span>"

            rows.append(f"""
                <tr class="severity-{self._html_escape(severity)}">
                    <td class="file">{self._html_escape(file_path)}</td>
                    <td><code>{self._html_escape(diff.element_name)}</code></td>
                    <td>{self._html_escape(interface_type)}</td>
                    <td>{self._html_escape(change_type)}</td>
                    <td><span class="pill {self._html_escape(severity)}">{self._html_escape(severity)}</span></td>
                    <td>{self._html_escape(diff.diff_summary)}</td>
                    <td>{details}</td>
                </tr>
""")

        if not rows:
            rows.append("""
                <tr>
                    <td colspan="7" class="empty">No interface changes were found.</td>
                </tr>
""")

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Interface Difference Analysis Report</title>
    <style>
        :root {{
            --ink: #172033;
            --muted: #667085;
            --line: #d9e2ec;
            --surface: #ffffff;
            --page: #f4f7fb;
            --brand: #1557b0;
            --breaking: #c62828;
            --review: #b26a00;
            --safe: #1b7f3a;
            --info: #0b6b88;
        }}
        * {{ box-sizing: border-box; }}
        body {{
            margin: 0;
            background: var(--page);
            color: var(--ink);
            font-family: "Segoe UI", Arial, sans-serif;
            line-height: 1.45;
        }}
        header {{
            background: var(--brand);
            color: white;
            padding: 28px 36px;
        }}
        header h1 {{
            margin: 0 0 8px;
            font-size: 28px;
            font-weight: 700;
        }}
        header p {{
            margin: 0;
            opacity: 0.92;
        }}
        main {{
            max-width: 1500px;
            margin: 0 auto;
            padding: 24px 28px 36px;
        }}
        section {{
            background: var(--surface);
            border: 1px solid var(--line);
            border-radius: 8px;
            margin-bottom: 18px;
            padding: 20px;
        }}
        h2 {{
            margin: 0 0 14px;
            font-size: 18px;
        }}
        .meta-grid {{
            display: grid;
            grid-template-columns: 140px minmax(0, 1fr);
            gap: 8px 16px;
            font-size: 14px;
        }}
        .label {{
            color: var(--muted);
            font-weight: 600;
        }}
        .path {{
            overflow-wrap: anywhere;
            font-family: Consolas, "Courier New", monospace;
        }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 14px;
        }}
        .stat {{
            border: 1px solid var(--line);
            border-left: 5px solid var(--brand);
            border-radius: 7px;
            padding: 14px;
            background: #fbfdff;
        }}
        .stat.breaking {{ border-left-color: var(--breaking); }}
        .stat.review {{ border-left-color: var(--review); }}
        .stat.safe {{ border-left-color: var(--safe); }}
        .stat-number {{
            display: block;
            font-size: 28px;
            font-weight: 800;
        }}
        .stat-label {{
            color: var(--muted);
            font-size: 13px;
        }}
        .table-wrap {{
            overflow-x: auto;
            border: 1px solid var(--line);
            border-radius: 8px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            min-width: 1050px;
            background: white;
        }}
        th {{
            position: sticky;
            top: 0;
            background: #26364d;
            color: white;
            padding: 11px 12px;
            text-align: left;
            font-size: 13px;
        }}
        td {{
            border-top: 1px solid var(--line);
            padding: 10px 12px;
            vertical-align: top;
            font-size: 13px;
        }}
        tr.severity-breaking td {{ background: #fff3f3; }}
        tr.severity-review td {{ background: #fff9eb; }}
        tr.severity-safe td {{ background: #f0fbf3; }}
        tr.severity-info td {{ background: #eefaff; }}
        code {{
            font-family: Consolas, "Courier New", monospace;
            font-size: 12px;
        }}
        .file {{
            min-width: 260px;
            overflow-wrap: anywhere;
            font-family: Consolas, "Courier New", monospace;
        }}
        .pill {{
            display: inline-block;
            min-width: 72px;
            padding: 3px 8px;
            border-radius: 999px;
            color: white;
            text-align: center;
            font-size: 12px;
            font-weight: 700;
        }}
        .pill.breaking {{ background: var(--breaking); }}
        .pill.review {{ background: var(--review); }}
        .pill.safe {{ background: var(--safe); }}
        .pill.info {{ background: var(--info); }}
        .muted, .empty {{
            color: var(--muted);
        }}
        .empty {{
            text-align: center;
            padding: 24px;
        }}
        @media print {{
            body {{ background: white; }}
            header, section {{ box-shadow: none; }}
            th {{ position: static; }}
        }}
    </style>
</head>
<body>
    <header>
        <h1>Interface Difference Analysis Report</h1>
        <p>Generated on {self._html_escape(generated_at)}</p>
    </header>
    <main>
        <section>
            <h2>Analysis Context</h2>
            <div class="meta-grid">
                <div class="label">Baseline</div><div class="path">{baseline_path}</div>
                <div class="label">Target</div><div class="path">{target_path}</div>
                <div class="label">Scope</div><div>{scope_info}</div>
            </div>
        </section>

        <section>
            <h2>Summary</h2>
            <div class="stats">
                <div class="stat"><span class="stat-number">{total_changes}</span><span class="stat-label">Interface Changes</span></div>
                <div class="stat"><span class="stat-number">{files_changed}</span><span class="stat-label">Files With Changes</span></div>
                <div class="stat breaking"><span class="stat-number">{breaking}</span><span class="stat-label">Breaking</span></div>
                <div class="stat review"><span class="stat-number">{review}</span><span class="stat-label">Review Needed</span></div>
                <div class="stat safe"><span class="stat-number">{safe}</span><span class="stat-label">Safe</span></div>
            </div>
        </section>

        <section>
            <h2>Interface Changes</h2>
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>File</th>
                            <th>Interface</th>
                            <th>Type</th>
                            <th>Change</th>
                            <th>Severity</th>
                            <th>Summary</th>
                            <th>Details</th>
                        </tr>
                    </thead>
                    <tbody>
                        {''.join(rows)}
                    </tbody>
                </table>
            </div>
        </section>
    </main>
</body>
</html>
"""

    @staticmethod
    def _html_escape(value):
        """Escape a value for safe HTML output."""
        if value is None:
            return ""
        return html.escape(str(value), quote=True)

    @staticmethod
    def _enum_value(value):
        """Return enum.value when available, otherwise a safe string."""
        return getattr(value, "value", str(value)).lower()

    @staticmethod
    def _severity_sort_key(severity):
        """Sort severities with highest-risk changes first."""
        order = {
            Severity.BREAKING: 0,
            Severity.REVIEW: 1,
            Severity.SAFE: 2,
        }
        return order.get(severity, 99)


def show_interface_diff_viewer(parent=None, baseline_path=None, target_path=None):
    """Show the enhanced interface diff viewer."""
    viewer = EnhancedInterfaceDiffViewer(parent)

    if baseline_path:
        viewer.baseline_root.set(baseline_path)
        viewer.diff_scope_baseline_path.set(baseline_path)
    if target_path:
        viewer.target_root.set(target_path)
        viewer.diff_scope_target_path.set(target_path)

    return viewer


if __name__ == "__main__":
    # Standalone test
    root = tk.Tk()
    root.withdraw()
    viewer = show_interface_diff_viewer()
    viewer.window.mainloop()
