"""
Interface Diff Analysis Viewer GUI - Enterprise Edition with Dependency & Impact Analysis
Comprehensive interface difference analysis with detailed drill-down, filtering, and export
Integrates: interface-parser.py, interface-diff.py, dependency-graph.py, enterprise-engine.py
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import threading
import logging
import csv
import webbrowser
import sys
import os
from pathlib import Path
from datetime import datetime

# Add parent directory to path if needed
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

from ..utils.interface_diff import (
    InterfaceDiffEngine, Severity, ChangeType, InterfaceType,
    BaselineDiff, FileDiff, InterfaceDiff
)

# Import dependency graph and impact analysis
try:
    # Try relative import
    if __name__ != '__main__':
        from ..dependency_graph import DependencyGraphBuilder, DependencyGraph, ImpactAnalyzer
    else:
        from dependency_graph import DependencyGraphBuilder, DependencyGraph, ImpactAnalyzer
    DEPENDENCY_AVAILABLE = True
except ImportError as e:
    DEPENDENCY_AVAILABLE = False
    logger.warning(f"Dependency graph module not available - impact analysis will be disabled: {e}")


class InterfaceDiffViewer:
    """Enterprise-grade GUI for analyzing interface differences between two baselines."""
    
    def __init__(self, parent=None):
        """Initialize the comprehensive interface diff viewer."""
        self.window = tk.Toplevel(parent) if parent else tk.Tk()
        self.window.title("🔬 Interface Difference Analysis Tool - Enterprise Edition")
        self.window.geometry("1600x900")
        self.window.configure(bg="#F0F0F0")
        
        self.baseline_path = tk.StringVar()
        self.target_path = tk.StringVar()
        self.diff_result = None
        self.is_analyzing = False
        
        # Dependency graph and impact analysis
        self.dependency_graph_baseline = None
        self.dependency_graph_target = None
        self.impact_analyzer_baseline = None
        self.impact_analyzer_target = None
        self.enable_dependency_analysis = tk.BooleanVar(value=DEPENDENCY_AVAILABLE)
        
        # Filter states
        self.filter_severity = tk.StringVar(value="All")
        self.filter_type = tk.StringVar(value="All")
        self.filter_change = tk.StringVar(value="All")
        self.filter_area = tk.StringVar(value="All")
        self.search_text = tk.StringVar()
        
        # All diffs for filtering
        self.all_diffs = []  # List of (diff, file_path) tuples
        
        # Selected diff for detail view
        self.selected_diff = None
        
        # Configure styles first (before creating UI that uses them)
        self._configure_styles()
        
        # Then create UI
        self._create_ui()
    
    def _configure_styles(self):
        """Configure custom styles for the UI."""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Configure Treeview colors
        style.configure("Treeview", rowheight=25)
        style.configure("Diff.Treeview", rowheight=28, font=("Consolas", 9))
        
        # Tag colors for severity
        self.severity_colors = {
            Severity.BREAKING: "#FFE5E5",
            Severity.REVIEW: "#FFF3CD",
            Severity.SAFE: "#D4EDDA",
            Severity.INFO: "#D1ECF1"
        }
        
        self.severity_icons = {
            Severity.BREAKING: "🔴",
            Severity.REVIEW: "🟡",
            Severity.SAFE: "🟢",
            Severity.INFO: "ℹ️"
        }
        
        self.change_icons = {
            ChangeType.ADDED: "➕",
            ChangeType.REMOVED: "➖",
            ChangeType.MODIFIED: "✏️",
            ChangeType.UNCHANGED: "✓"
        }
    
    def _create_ui(self):
        """Create the comprehensive user interface."""
        # Header
        self._create_header()
        
        # Input Section
        self._create_input_section()
        
        # Main content area (with splitter)
        self._create_main_content()
        
        # Status Bar
        self._create_status_bar()
    
    def _create_header(self):
        """Create header with branding."""
        header = tk.Frame(self.window, bg="#1565C0", height=60)
        header.pack(fill="x")
        header.pack_propagate(False)
        
        tk.Label(
            header,
            text="🔬 Interface Difference Analysis Tool",
            font=("Segoe UI", 16, "bold"),
            bg="#1565C0",
            fg="white"
        ).pack(side="left", padx=20, pady=15)
        
        tk.Label(
            header,
            text="Enterprise Edition - Detailed Interface Comparison with Full Parser Support",
            font=("Segoe UI", 9),
            bg="#1565C0",
            fg="#E3F2FD"
        ).pack(side="left", pady=15)
    
    def _create_input_section(self):
        """Create baseline and target selection section with analysis controls."""
        input_frame = tk.Frame(self.window, bg="#E3F2FD", relief="raised", bd=1)
        input_frame.pack(fill="x", padx=0, pady=0)
        
        # Row 1: Baseline
        row1 = tk.Frame(input_frame, bg="#E3F2FD")
        row1.pack(fill="x", padx=10, pady=5)
        
        tk.Label(
            row1, text="📦 Baseline (Stream 1):", bg="#E3F2FD",
            font=("Segoe UI", 9, "bold"), width=18, anchor="w"
        ).pack(side="left", padx=5)
        
        tk.Entry(
            row1, textvariable=self.baseline_path, width=70,
            font=("Segoe UI", 9)
        ).pack(side="left", padx=5, fill="x", expand=True)
        
        tk.Button(
            row1, text="Browse", command=self._browse_baseline,
            bg="#1976D2", fg="white", font=("Segoe UI", 8), padx=12, pady=2
        ).pack(side="left", padx=2)
        
        # Row 2: Target
        row2 = tk.Frame(input_frame, bg="#E3F2FD")
        row2.pack(fill="x", padx=10, pady=5)
        
        tk.Label(
            row2, text="📦 Target (Stream 2):", bg="#E3F2FD",
            font=("Segoe UI", 9, "bold"), width=18, anchor="w"
        ).pack(side="left", padx=5)
        
        tk.Entry(
            row2, textvariable=self.target_path, width=70,
            font=("Segoe UI", 9)
        ).pack(side="left", padx=5, fill="x", expand=True)
        
        tk.Button(
            row2, text="Browse", command=self._browse_target,
            bg="#1976D2", fg="white", font=("Segoe UI", 8), padx=12, pady=2
        ).pack(side="left", padx=2)
        
        # Row 3: Action buttons
        row3 = tk.Frame(input_frame, bg="#E3F2FD")
        row3.pack(fill="x", padx=10, pady=8)
        
        tk.Button(
            row3, text="🔍 Analyze Interfaces", command=self._start_analysis,
            bg="#27ae60", fg="white", font=("Segoe UI", 10, "bold"),
            padx=20, pady=6
        ).pack(side="left", padx=5)
        
        tk.Button(
            row3, text="📊 Export to CSV", command=self._export_to_csv,
            bg="#3498db", fg="white", font=("Segoe UI", 9), padx=15, pady=6
        ).pack(side="left", padx=5)
        
        tk.Button(
            row3, text="📄 Export HTML Report", command=self._export_to_html,
            bg="#9b59b6", fg="white", font=("Segoe UI", 9), padx=15, pady=6
        ).pack(side="left", padx=5)
        
        tk.Button(
            row3, text="🔄 Clear Results", command=self._clear_results,
            bg="#95a5a6", fg="white", font=("Segoe UI", 9), padx=15, pady=6
        ).pack(side="left", padx=5)
        
        # Dependency analysis checkbox
        if DEPENDENCY_AVAILABLE:
            dep_check = tk.Checkbutton(
                row3, text="🔗 Include Dependency & Impact Analysis",
                variable=self.enable_dependency_analysis,
                bg="#E3F2FD", font=("Segoe UI", 9),
                activebackground="#E3F2FD"
            )
            dep_check.pack(side="left", padx=15)
        else:
            tk.Label(
                row3, text="⚠️ Dependency analysis unavailable",
                bg="#E3F2FD", fg="#e74c3c", font=("Segoe UI", 8, "italic")
            ).pack(side="left", padx=15)
    
    def _create_main_content(self):
        """Create main content area with filters, tree, and detail panel."""
        # Container
        container = tk.Frame(self.window, bg="white")
        container.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Summary bar (hidden until analysis complete)
        self.summary_bar = tk.Frame(container, bg="#E8F5E9", height=40, relief="groove", bd=1)
        self.summary_bar.pack(fill="x", pady=(0, 5))
        self.summary_bar.pack_propagate(False)
        self.summary_label = tk.Label(
            self.summary_bar, text="No analysis performed yet - Select baseline and target folders, then click 'Analyze Interfaces'", 
            bg="#E8F5E9", fg="#555", font=("Segoe UI", 9)
        )
        self.summary_label.pack(pady=10)
        
        # Main paned window (left: tree + filters, right: detail panel)
        main_paned = tk.PanedWindow(container, orient="horizontal", 
                                    bg="#bdc3c7", sashwidth=6, sashrelief="raised")
        main_paned.pack(fill="both", expand=True)
        
        # LEFT PANE: Filters + Tree
        left_pane = tk.Frame(main_paned, bg="white")
        main_paned.add(left_pane, minsize=900)
        
        # Filters panel
        self._create_filters_panel(left_pane)
        
        # Tree view with results
        self._create_tree_view(left_pane)
        
        # RIGHT PANE: Detail panel
        right_pane = tk.Frame(main_paned, bg="white")
        main_paned.add(right_pane, minsize=500)
        
        self._create_detail_panel(right_pane)
    
    def _create_filters_panel(self, parent):
        """Create comprehensive filters panel."""
        filter_frame = tk.LabelFrame(
            parent, text="🔍 Filters & Search", 
            bg="#F5F5F5", font=("Segoe UI", 9, "bold"),
            relief="groove", bd=2
        )
        filter_frame.pack(fill="x", padx=5, pady=5)
        
        # Row 1: Severity and Type filters
        row1 = tk.Frame(filter_frame, bg="#F5F5F5")
        row1.pack(fill="x", padx=10, pady=5)
        
        tk.Label(row1, text="Severity:", bg="#F5F5F5", font=("Segoe UI", 8, "bold")).pack(side="left", padx=5)
        severity_combo = ttk.Combobox(
            row1, textvariable=self.filter_severity, 
            values=["All", "Breaking", "Review", "Safe", "Info"],
            width=12, state="readonly", font=("Segoe UI", 8)
        )
        severity_combo.pack(side="left", padx=5)
        severity_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_filters())
        
        tk.Label(row1, text="Type:", bg="#F5F5F5", font=("Segoe UI", 8, "bold")).pack(side="left", padx=10)
        type_combo = ttk.Combobox(
            row1, textvariable=self.filter_type,
            values=["All", "function", "struct", "enum", "macro", "typedef", "extern_var"],
            width=12, state="readonly", font=("Segoe UI", 8)
        )
        type_combo.pack(side="left", padx=5)
        type_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_filters())
        
        tk.Label(row1, text="Change:", bg="#F5F5F5", font=("Segoe UI", 8, "bold")).pack(side="left", padx=10)
        change_combo = ttk.Combobox(
            row1, textvariable=self.filter_change,
            values=["All", "added", "removed", "modified"],
            width=12, state="readonly", font=("Segoe UI", 8)
        )
        change_combo.pack(side="left", padx=5)
        change_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_filters())
        
        # Row 2: Functional area and search
        row2 = tk.Frame(filter_frame, bg="#F5F5F5")
        row2.pack(fill="x", padx=10, pady=5)
        
        tk.Label(row2, text="Area:", bg="#F5F5F5", font=("Segoe UI", 8, "bold")).pack(side="left", padx=5)
        self.area_combo = ttk.Combobox(
            row2, textvariable=self.filter_area,
            values=["All"],  # Will be populated after analysis
            width=15, state="readonly", font=("Segoe UI", 8)
        )
        self.area_combo.pack(side="left", padx=5)
        self.area_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_filters())
        
        tk.Label(row2, text="Search:", bg="#F5F5F5", font=("Segoe UI", 8, "bold")).pack(side="left", padx=10)
        search_entry = tk.Entry(row2, textvariable=self.search_text, width=30, font=("Segoe UI", 9))
        search_entry.pack(side="left", padx=5)
        search_entry.bind("<KeyRelease>", lambda e: self._apply_filters())
        
        tk.Button(
            row2, text="Clear All", command=self._clear_filters,
            bg="#e74c3c", fg="white", font=("Segoe UI", 8), padx=10, pady=2
        ).pack(side="left", padx=10)
        
        # Results count
        self.filter_count_label = tk.Label(
            row2, text="", bg="#F5F5F5", fg="#27ae60", font=("Segoe UI", 8, "bold")
        )
        self.filter_count_label.pack(side="right", padx=5)
    
    def _create_tree_view(self, parent):
        """Create comprehensive tree view for interface diffs."""
        tree_frame = tk.Frame(parent, bg="white")
        tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Columns: Icon | File | Interface | Type | Change | Severity | Summary
        columns = ("icon", "file", "interface", "type", "change", "severity", "summary")
        self.tree = ttk.Treeview(
            tree_frame, columns=columns, show="tree headings",
            height=20, style="Diff.Treeview"
        )
        
        # Column configuration
        self.tree.column("#0", width=0, stretch=False)
        self.tree.column("icon", width=40, anchor="center")
        self.tree.column("file", width=250, anchor="w")
        self.tree.column("interface", width=200, anchor="w")
        self.tree.column("type", width=80, anchor="center")
        self.tree.column("change", width=80, anchor="center")
        self.tree.column("severity", width=80, anchor="center")
        self.tree.column("summary", width=450, anchor="w")
        
        # Headings
        self.tree.heading("icon", text="")
        self.tree.heading("file", text="📁 File Path")
        self.tree.heading("interface", text="🔧 Interface Name")
        self.tree.heading("type", text="Type")
        self.tree.heading("change", text="Change")
        self.tree.heading("severity", text="Severity")
        self.tree.heading("summary", text="Summary")
        
        # Scrollbars
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        # Pack
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        
        # Bind selection
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        
        # Configure tags for severity colors
        for severity, color in self.severity_colors.items():
            self.tree.tag_configure(severity.value, background=color)
    
    def _create_detail_panel(self, parent):
        """Create detail panel to show full diff information."""
        detail_frame = tk.LabelFrame(
            parent, text="📋 Interface Details & Comparison", 
            bg="white", font=("Segoe UI", 10, "bold"),
            relief="groove", bd=2
        )
        detail_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Tabs for different detail views
        self.detail_notebook = ttk.Notebook(detail_frame)
        self.detail_notebook.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Tab 1: Change Summary
        summary_frame = tk.Frame(self.detail_notebook, bg="white")
        self.detail_notebook.add(summary_frame, text="📝 Summary")
        
        self.detail_summary = scrolledtext.ScrolledText(
            summary_frame, wrap=tk.WORD, width=60, height=15,
            font=("Consolas", 9), bg="#FAFAFA"
        )
        self.detail_summary.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Tab 2: Baseline (Before)
        baseline_frame = tk.Frame(self.detail_notebook, bg="white")
        self.detail_notebook.add(baseline_frame, text="📦 Baseline (Before)")
        
        self.detail_baseline = scrolledtext.ScrolledText(
            baseline_frame, wrap=tk.WORD, width=60, height=15,
            font=("Consolas", 9), bg="#FFF5F5"
        )
        self.detail_baseline.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Tab 3: Target (After)
        target_frame = tk.Frame(self.detail_notebook, bg="white")
        self.detail_notebook.add(target_frame, text="🎯 Target (After)")
        
        self.detail_target = scrolledtext.ScrolledText(
            target_frame, wrap=tk.WORD, width=60, height=15,
            font=("Consolas", 9), bg="#F5FFF5"
        )
        self.detail_target.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Tab 4: Impact Analysis
        impact_frame = tk.Frame(self.detail_notebook, bg="white")
        self.detail_notebook.add(impact_frame, text="⚠️ Impact Analysis")
        
        self.detail_impact = scrolledtext.ScrolledText(
            impact_frame, wrap=tk.WORD, width=60, height=15,
            font=("Segoe UI", 9), bg="#FFF9E6"
        )
        self.detail_impact.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Tab 5: Dependency Graph (if enabled)
        if DEPENDENCY_AVAILABLE:
            dependency_frame = tk.Frame(self.detail_notebook, bg="white")
            self.detail_notebook.add(dependency_frame, text="🔗 Dependencies")
            
            self.detail_dependencies = scrolledtext.ScrolledText(
                dependency_frame, wrap=tk.WORD, width=60, height=15,
                font=("Consolas", 9), bg="#F0F8FF"
            )
            self.detail_dependencies.pack(fill="both", expand=True, padx=5, pady=5)
        else:
            self.detail_dependencies = None
        
        # Initial message
        self.detail_summary.insert("1.0", "Select an interface change from the tree to view detailed comparison...\n\n" +
                                           "This panel will show:\n" +
                                           "• Full function signatures with parameters\n" +
                                           "• Struct fields with types and arrays\n" +
                                           "• Enum values\n" +
                                           "• Macro definitions\n" +
                                           "• Line numbers in source files\n" +
                                           "• Impact analysis and recommendations\n" +
                                           "• Dependency graph showing affected files")
        self.detail_summary.config(state="disabled")
    
    def _create_status_bar(self):
        """Create status bar."""
        status_frame = tk.Frame(self.window, relief="sunken", bd=1, bg="#34495e")
        status_frame.pack(fill="x", side="bottom")
        
        self.status_var = tk.StringVar(value="Ready - Select folders and click Analyze")
        tk.Label(
            status_frame, textvariable=self.status_var,
            bg="#34495e", fg="white", font=("Segoe UI", 9),
            anchor="w", padx=10
        ).pack(fill="x", pady=3)
    
    # =======================
    # Event Handlers
    # =======================
    
    def _browse_baseline(self):
        """Browse for baseline folder."""
        folder = filedialog.askdirectory(title="Select Baseline (Stream 1) Folder")
        if folder:
            self.baseline_path.set(folder)
            self.status_var.set(f"Baseline selected: {folder}")
    
    def _browse_target(self):
        """Browse for target folder."""
        folder = filedialog.askdirectory(title="Select Target (Stream 2) Folder")
        if folder:
            self.target_path.set(folder)
            self.status_var.set(f"Target selected: {folder}")
    
    def _start_analysis(self):
        """Start the interface analysis."""
        if not self.baseline_path.get() or not self.target_path.get():
            messagebox.showwarning("Missing Input", "Please select both baseline and target folders")
            return
        
        # Start analysis in background thread
        thread = threading.Thread(target=self._analyze_interfaces, daemon=True)
        thread.start()
    
    def _analyze_interfaces(self):
        """Analyze interfaces between two baselines with optional dependency analysis."""
        try:
            self.is_analyzing = True
            self.status_var.set("🔄 Phase 1/3: Parsing baseline interfaces...")
            self.window.update()
            
            engine = InterfaceDiffEngine(ignore_patterns=['*_test.c', '*_mock.c', 'test_*.c'])
            
            self.status_var.set("🔄 Phase 2/3: Parsing target interfaces...")
            self.window.update()
            
            self.status_var.set("🔄 Phase 2/3: Comparing interfaces...")
            self.window.update()
            
            self.diff_result = engine.compare_baselines(
                self.baseline_path.get(),
                self.target_path.get()
            )
            
            # Build dependency graphs if enabled
            if self.enable_dependency_analysis.get() and DEPENDENCY_AVAILABLE:
                self.status_var.set("🔄 Phase 3/3: Building dependency graphs...")
                self.window.update()
                
                try:
                    builder = DependencyGraphBuilder()
                    
                    # Build baseline dependency graph
                    self.status_var.set("🔄 Building baseline dependency graph...")
                    self.window.update()
                    self.dependency_graph_baseline = builder.build_graph(self.baseline_path.get())
                    self.impact_analyzer_baseline = ImpactAnalyzer(self.dependency_graph_baseline)
                    
                    # Build target dependency graph
                    self.status_var.set("🔄 Building target dependency graph...")
                    self.window.update()
                    self.dependency_graph_target = builder.build_graph(self.target_path.get())
                    self.impact_analyzer_target = ImpactAnalyzer(self.dependency_graph_target)
                    
                    self.status_var.set("✅ Analysis complete with dependency graphs")
                except Exception as e:
                    logger.exception("Dependency graph building failed")
                    messagebox.showwarning("Dependency Analysis Warning", 
                                          f"Dependency graph building failed:\n{str(e)}\n\nContinuing with interface analysis only.")
                    self.dependency_graph_baseline = None
                    self.dependency_graph_target = None
            else:
                self.status_var.set("✅ Interface analysis complete")
            
            self.window.update()
            
            # Must display results in main thread
            self.window.after(100, self._display_results)
            
        except Exception as e:
            messagebox.showerror("Analysis Error", f"Error during analysis:\n\n{str(e)}")
            logger.exception("Interface analysis error")
            self.status_var.set("❌ Analysis failed")
        finally:
            self.is_analyzing = False
    
    def _display_results(self):
        """Display analysis results in the comprehensive UI."""
        if not self.diff_result:
            return
        
        # Clear previous results
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        self.all_diffs = []
        
        # Collect all diffs
        for file_path, file_diff in sorted(self.diff_result.file_diffs.items()):
            for diff in file_diff.diffs:
                self.all_diffs.append((diff, file_path))
        
        # Populate functional area filter
        areas = ["All"] + sorted(list(self.diff_result.by_functional_area.keys()))
        self.area_combo.config(values=areas)
        
        # Populate tree
        self._populate_tree(self.all_diffs)
        
        # Update summary bar
        total = len(self.all_diffs)
        breaking = self.diff_result.breaking_changes
        review = self.diff_result.review_needed
        safe = self.diff_result.safe_changes
        
        self.summary_label.config(
            text=f"📊 Analysis Complete: {total} interfaces changed | " +
                 f"🔴 {breaking} Breaking | 🟡 {review} Review Needed | 🟢 {safe} Safe | " +
                 f"📁 {self.diff_result.files_modified} files modified",
            fg="#2c3e50", font=("Segoe UI", 9, "bold")
        )
        
        self.status_var.set(f"✅ Found {total} interface changes across {len(self.diff_result.file_diffs)} files")
        
        # Show stats in a message
        stats_msg = (
            f"Analysis Complete!\n\n"
            f"Files: {self.diff_result.total_files} total\n"
            f"  • Added: {self.diff_result.files_added}\n"
            f"  • Removed: {self.diff_result.files_removed}\n"
            f"  • Modified: {self.diff_result.files_modified}\n\n"
            f"Interface Changes: {total}\n"
            f"  • Added: {self.diff_result.interfaces_added}\n"
            f"  • Removed: {self.diff_result.interfaces_removed}\n"
            f"  • Modified: {self.diff_result.interfaces_modified}\n\n"
            f"Impact:\n"
            f"  🔴 Breaking: {breaking}\n"
            f"  🟡 Review: {review}\n"
            f"  🟢 Safe: {safe}"
        )
        messagebox.showinfo("Analysis Complete", stats_msg)
    
    def _populate_tree(self, diffs):
        """Populate tree with diff results."""
        for diff, file_path in diffs:
            severity_icon = self.severity_icons.get(diff.severity, "")
            change_icon = self.change_icons.get(diff.change_type, "")
            
            icon = f"{severity_icon}{change_icon}"
            
            # Truncate summary if too long
            summary = diff.diff_summary[:100] + "..." if len(diff.diff_summary) > 100 else diff.diff_summary
            
            item_id = self.tree.insert(
                "", "end",
                values=(
                    icon,
                    file_path,
                    diff.element_name,
                    diff.interface_type.value,
                    diff.change_type.value,
                    diff.severity.value,
                    summary
                ),
                tags=(diff.severity.value,)
            )
            
            # Store diff object in item
            self.tree.set(item_id, "#0", str(id(diff)))  # Hidden column stores diff ID
    
    def _on_tree_select(self, event):
        """Handle tree selection to show details."""
        selection = self.tree.selection()
        if not selection:
            return
        
        item_id = selection[0]
        diff_id = self.tree.set(item_id, "#0")
        
        # Find the diff object
        selected_diff = None
        for diff, file_path in self.all_diffs:
            if str(id(diff)) == diff_id:
                selected_diff = (diff, file_path)
                break
        
        if selected_diff:
            self.selected_diff = selected_diff
            self._display_diff_details(selected_diff[0], selected_diff[1])
    
    def _display_diff_details(self, diff: InterfaceDiff, file_path: str):
        """Display comprehensive details for the selected diff."""
        # Clear all detail panels
        for widget in [self.detail_summary, self.detail_baseline, self.detail_target, self.detail_impact]:
            widget.config(state="normal")
            widget.delete("1.0", tk.END)
        
        # === TAB 1: Summary ===
        self.detail_summary.insert("end", f"═══ INTERFACE CHANGE SUMMARY ═══\n\n", "header")
        self.detail_summary.insert("end", f"File: {file_path}\n")
        self.detail_summary.insert("end", f"Interface: {diff.element_name}\n")
        self.detail_summary.insert("end", f"Type: {diff.interface_type.value}\n")
        self.detail_summary.insert("end", f"Change: {diff.change_type.value}\n")
        self.detail_summary.insert("end", f"Severity: {diff.severity.value} {self.severity_icons.get(diff.severity, '')}\n")
        self.detail_summary.insert("end", f"Functional Area: {diff.functional_area}\n\n")
        
        self.detail_summary.insert("end", f"Summary:\n")
        self.detail_summary.insert("end", f"{diff.diff_summary}\n\n")
        
        if diff.diff_details:
            self.detail_summary.insert("end", f"Detailed Changes:\n")
            for detail in diff.diff_details:
                self.detail_summary.insert("end", f"  • {detail}\n")
            self.detail_summary.insert("end", "\n")
        
        # Line numbers
        if diff.line_baseline:
            self.detail_summary.insert("end", f"Baseline Line: {diff.line_baseline}\n")
        if diff.line_target:
            self.detail_summary.insert("end", f"Target Line: {diff.line_target}\n")
        
        # === TAB 2: Baseline (Before) ===
        if diff.baseline_element:
            elem = diff.baseline_element
            self._format_interface_element(self.detail_baseline, elem, "BASELINE (BEFORE)")
        else:
            self.detail_baseline.insert("end", "Not present in baseline (newly added)")
        
        # === TAB 3: Target (After) ===
        if diff.target_element:
            elem = diff.target_element
            self._format_interface_element(self.detail_target, elem, "TARGET (AFTER)")
        else:
            self.detail_target.insert("end", "Not present in target (removed)")
        
        # === TAB 4: Impact Analysis ===
        self.detail_impact.insert("end", f"═══ IMPACT ANALYSIS ═══\n\n", "header")
        self.detail_impact.insert("end", f"Severity: {diff.severity.value.upper()} {self.severity_icons.get(diff.severity, '')}\n\n")
        
        if diff.severity == Severity.BREAKING:
            self.detail_impact.insert("end", "⚠️ BREAKING CHANGE\n\n")
            self.detail_impact.insert("end", "This change will cause compilation errors in any code that uses this interface.\n\n")
            self.detail_impact.insert("end", "Required Actions:\n")
            self.detail_impact.insert("end", "1. Identify all call sites that use this interface\n")
            self.detail_impact.insert("end", "2. Update call sites to match the new signature\n")
            self.detail_impact.insert("end", "3. Update unit tests\n")
            self.detail_impact.insert("end", "4. Verify functionality after changes\n\n")
        elif diff.severity == Severity.REVIEW:
            self.detail_impact.insert("end", "⚠️ REQUIRES REVIEW\n\n")
            self.detail_impact.insert("end", "This change may impact functionality and requires careful review.\n\n")
            self.detail_impact.insert("end", "Recommended Actions:\n")
            self.detail_impact.insert("end", "1. Review the change details carefully\n")
            self.detail_impact.insert("end", "2. Check if the change affects runtime behavior\n")
            self.detail_impact.insert("end", "3. Update documentation if needed\n")
            self.detail_impact.insert("end", "4. Consider testing implications\n\n")
        elif diff.severity == Severity.SAFE:
            self.detail_impact.insert("end", "✅ SAFE CHANGE\n\n")
            self.detail_impact.insert("end", "This change is safe and can typically be auto-merged.\n\n")
        
        if diff.impact_description:
            self.detail_impact.insert("end", f"Impact Description:\n{diff.impact_description}\n\n")
        
        # Add dependency analysis if available
        if self.dependency_graph_target and self.impact_analyzer_target:
            self.detail_impact.insert("end", "\n═══ DEPENDENCY IMPACT ═══\n\n")
            impact = self.impact_analyzer_target.analyze_impact(file_path)
            
            self.detail_impact.insert("end", f"📊 Files Affected by Changes to {os.path.basename(file_path)}:\n\n")
            self.detail_impact.insert("end", f"Direct Dependents: {len(impact.direct_dependents)}\n")
            self.detail_impact.insert("end", f"Total Impact: {len(impact.all_dependents)} files\n\n")
            
            if impact.direct_dependents:
                self.detail_impact.insert("end", "Direct Dependents (first 10):\n")
                for dep in impact.direct_dependents[:10]:
                    self.detail_impact.insert("end", f"  • {dep}\n")
                if len(impact.direct_dependents) > 10:
                    self.detail_impact.insert("end", f"  ... and {len(impact.direct_dependents) - 10} more\n")
        
        # === TAB 5: Dependency Graph (if available) ===
        if self.detail_dependencies and self.dependency_graph_target:
            self.detail_dependencies.insert("end", f"═══ DEPENDENCY ANALYSIS FOR {file_path} ═══\n\n")
            
            impact = self.impact_analyzer_target.analyze_impact(file_path)
            node = self.dependency_graph_target.get_node(file_path)
            
            if node:
                self.detail_dependencies.insert("end", f"File Type: {'Header' if node.is_header else 'Source'}\n\n")
                
                # Show what this file includes
                self.detail_dependencies.insert("end", f"📥 This file includes ({len(node.resolved_includes)}):\n")
                if node.resolved_includes:
                    for inc in sorted(node.resolved_includes):
                        self.detail_dependencies.insert("end", f"  • {inc}\n")
                else:
                    self.detail_dependencies.insert("end", "  (no dependencies)\n")
                
                self.detail_dependencies.insert("end", f"\n📤 This file is included by ({len(node.included_by)}):\n")
                if node.included_by:
                    for inc_by in sorted(node.included_by):
                        self.detail_dependencies.insert("end", f"  • {inc_by}\n")
                else:
                    self.detail_dependencies.insert("end", "  (no reverse dependencies)\n")
                
                # Impact radius
                self.detail_dependencies.insert("end", f"\n🎯 IMPACT RADIUS\n")
                self.detail_dependencies.insert("end", f"Total files that depend on this file: {len(impact.all_dependents)}\n")
                self.detail_dependencies.insert("end", f"  • Headers affected: {impact.headers_affected}\n")
                self.detail_dependencies.insert("end", f"  • Sources affected: {impact.sources_affected}\n\n")
                
                if impact.functional_areas:
                    self.detail_dependencies.insert("end", f"Functional Areas Affected:\n")
                    for area, count in sorted(impact.functional_areas.items(), key=lambda x: x[1], reverse=True):
                        self.detail_dependencies.insert("end", f"  • {area}: {count} files\n")
                
                if len(impact.all_dependents) > 0:
                    self.detail_dependencies.insert("end", f"\n⚠️ All Affected Files:\n")
                    for dep in sorted(impact.all_dependents)[:50]:  # Limit to 50
                        self.detail_dependencies.insert("end", f"  • {dep}\n")
                    if len(impact.all_dependents) > 50:
                        self.detail_dependencies.insert("end", f"  ... and {len(impact.all_dependents) - 50} more\n")
            else:
                self.detail_dependencies.insert("end", "File not found in dependency graph\n")
        
        # Make read-only
        widgets_to_readonly = [self.detail_summary, self.detail_baseline, self.detail_target, self.detail_impact]
        if self.detail_dependencies:
            widgets_to_readonly.append(self.detail_dependencies)
        for widget in widgets_to_readonly:
            widget.config(state="disabled")
    
    def _format_interface_element(self, text_widget, elem, title):
        """Format an interface element for display."""
        text_widget.insert("end", f"═══ {title} ═══\n\n", "header")
        text_widget.insert("end", f"Line {elem.line_number}: {elem.signature}\n\n")
        
        if elem.type == InterfaceType.FUNCTION:
            text_widget.insert("end", f"Return Type: {elem.return_type}\n")
            if elem.is_static:
                text_widget.insert("end", "Static: Yes\n")
            if elem.is_inline:
                text_widget.insert("end", "Inline: Yes\n")
            text_widget.insert("end", f"Declaration: {'Yes' if elem.is_declaration else 'Definition'}\n\n")
            
            if elem.parameters:
                text_widget.insert("end", "Parameters:\n")
                for i, param in enumerate(elem.parameters, 1):
                    text_widget.insert("end", f"  {i}. {param.type} {param.name}")
                    if param.default_value:
                        text_widget.insert("end", f" = {param.default_value}")
                    text_widget.insert("end", "\n")
            else:
                text_widget.insert("end", "Parameters: (none)\n")
        
        elif elem.type == InterfaceType.STRUCT:
            text_widget.insert("end", f"Type: {'Union' if elem.is_union else 'Struct'}\n\n")
            if elem.fields:
                text_widget.insert("end", "Fields:\n")
                for field in elem.fields:
                    text_widget.insert("end", f"  {field.type} {field.name}")
                    if field.array_size:
                        text_widget.insert("end", f"[{field.array_size}]")
                    if field.bit_field:
                        text_widget.insert("end", f" : {field.bit_field}")
                    text_widget.insert("end", "\n")
            else:
                text_widget.insert("end", "Fields: (empty)\n")
        
        elif elem.type == InterfaceType.ENUM:
            if elem.values:
                text_widget.insert("end", "Values:\n")
                for val in elem.values:
                    text_widget.insert("end", f"  {val.name}")
                    if val.value:
                        text_widget.insert("end", f" = {val.value}")
                    text_widget.insert("end", "\n")
            else:
                text_widget.insert("end", "Values: (empty)\n")
        
        elif elem.type == InterfaceType.MACRO:
            if elem.macro_params:
                text_widget.insert("end", f"Parameters: {', '.join(elem.macro_params)}\n")
            text_widget.insert("end", f"Value: {elem.macro_value}\n")
        
        elif elem.type == InterfaceType.TYPEDEF:
            text_widget.insert("end", f"Target: {elem.typedef_target}\n")
        
        text_widget.insert("end", f"\nRaw Source:\n")
        text_widget.insert("end", f"{elem.raw_text}\n")
    
    # =======================
    # Filtering
    # =======================
    
    def _apply_filters(self):
        """Apply all active filters."""
        if not self.all_diffs:
            return
        
        filtered = self.all_diffs
        
        # Filter by severity
        if self.filter_severity.get() != "All":
            sev_map = {"Breaking": Severity.BREAKING, "Review": Severity.REVIEW, 
                      "Safe": Severity.SAFE, "Info": Severity.INFO}
            target_sev = sev_map.get(self.filter_severity.get())
            if target_sev:
                filtered = [(d, f) for d, f in filtered if d.severity == target_sev]
        
        # Filter by type
        if self.filter_type.get() != "All":
            filtered = [(d, f) for d, f in filtered if d.interface_type.value == self.filter_type.get()]
        
        # Filter by change
        if self.filter_change.get() != "All":
            filtered = [(d, f) for d, f in filtered if d.change_type.value == self.filter_change.get()]
        
        # Filter by area
        if self.filter_area.get() != "All":
            filtered = [(d, f) for d, f in filtered if d.functional_area == self.filter_area.get()]
        
        # Filter by search text
        search = self.search_text.get().lower()
        if search:
            filtered = [(d, f) for d, f in filtered if 
                       search in d.element_name.lower() or 
                       search in f.lower() or
                       search in d.diff_summary.lower()]
        
        # Update tree
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._populate_tree(filtered)
        
        # Update count
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
        self.diff_result = None
        self.summary_label.config(text="No analysis performed yet", fg="#555", font=("Segoe UI", 9))
        self.status_var.set("Ready - Results cleared")
        
        # Clear detail panels
        for widget in [self.detail_summary, self.detail_baseline, self.detail_target, self.detail_impact]:
            widget.config(state="normal")
            widget.delete("1.0", tk.END)
            widget.config(state="disabled")
    
    # =======================
    # Export Functions
    # =======================
    
    def _export_to_csv(self):
        """Export results to CSV."""
        if not self.diff_result:
            messagebox.showwarning("No Data", "No analysis results to export")
            return
        
        csv_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=f"interface_diff_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            title="Export Interface Diff to CSV"
        )
        
        if not csv_path:
            return
        
        try:
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "File", "Interface", "Type", "Change", "Severity", "Functional Area",
                    "Line (Baseline)", "Line (Target)", "Summary", "Details"
                ])
                
                for diff, file_path in self.all_diffs:
                    writer.writerow([
                        file_path,
                        diff.element_name,
                        diff.interface_type.value,
                        diff.change_type.value,
                        diff.severity.value,
                        diff.functional_area,
                        diff.line_baseline or "",
                        diff.line_target or "",
                        diff.diff_summary,
                        "; ".join(diff.diff_details) if diff.diff_details else ""
                    ])
            
            messagebox.showinfo("Exported", f"Interface diff exported to:\n{csv_path}")
            self.status_var.set(f"✅ Exported to CSV: {csv_path}")
            
        except Exception as e:
            messagebox.showerror("Export Failed", f"Error exporting to CSV:\n\n{str(e)}")
    
    def _export_to_html(self):
        """Export results to HTML report."""
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
            html_content = self._generate_html_report()
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            messagebox.showinfo("Exported", f"HTML report exported to:\n{html_path}")
            self.status_var.set(f"✅ Exported to HTML: {html_path}")
            
            # Ask to open
            if messagebox.askyesno("Open Report", "Would you like to open the report in your browser?"):
                webbrowser.open(f'file://{html_path}')
            
        except Exception as e:
            messagebox.showerror("Export Failed", f"Error exporting to HTML:\n\n{str(e)}")
    
    def _generate_html_report(self):
        """Generate HTML report content."""
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Interface Difference Analysis Report</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .header {{ background: #1565C0; color: white; padding: 20px; border-radius: 5px; }}
        .summary {{ background: white; padding: 20px; margin: 20px 0; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
        .section {{ background: white; padding: 20px; margin: 20px 0; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
        table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
        th {{ background: #34495e; color: white; padding: 12px; text-align: left; }}
        td {{ padding: 10px; border-bottom: 1px solid #ddd; }}
        tr:hover {{ background: #f5f5f5; }}
        .breaking {{ background: #FFE5E5; }}
        .review {{ background: #FFF3CD; }}
        .safe {{ background: #D4EDDA; }}
        .info {{ background: #D1ECF1; }}
        .stats {{ display: flex; justify-content: space-around; margin: 20px 0; }}
        .stat-box {{ background: white; padding: 20px; border-radius: 5px; text-align: center; flex: 1; margin: 0 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
        .stat-number {{ font-size: 36px; font-weight: bold; }}
        .stat-label {{ color: #666; margin-top: 10px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🔬 Interface Difference Analysis Report</h1>
        <p>Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
    
    <div class="summary">
        <h2>Summary</h2>
        <p><strong>Baseline:</strong> {self.diff_result.baseline_path}</p>
        <p><strong>Target:</strong> {self.diff_result.target_path}</p>
    </div>
    
    <div class="stats">
        <div class="stat-box">
            <div class="stat-number">{self.diff_result.total_interfaces}</div>
            <div class="stat-label">Total Changes</div>
        </div>
        <div class="stat-box" style="color: #c0392b;">
            <div class="stat-number">🔴 {self.diff_result.breaking_changes}</div>
            <div class="stat-label">Breaking</div>
        </div>
        <div class="stat-box" style="color: #f39c12;">
            <div class="stat-number">🟡 {self.diff_result.review_needed}</div>
            <div class="stat-label">Review Needed</div>
        </div>
        <div class="stat-box" style="color: #27ae60;">
            <div class="stat-number">🟢 {self.diff_result.safe_changes}</div>
            <div class="stat-label">Safe</div>
        </div>
    </div>
    
    <div class="section">
        <h2>All Interface Changes</h2>
        <table>
            <thead>
                <tr>
                    <th>File</th>
                    <th>Interface</th>
                    <th>Type</th>
                    <th>Change</th>
                    <th>Severity</th>
                    <th>Summary</th>
                </tr>
            </thead>
            <tbody>
"""
        
        for diff, file_path in sorted(self.all_diffs, key=lambda x: (x[0].severity.value, x[1], x[0].element_name)):
            severity_class = diff.severity.value
            html += f"""
                <tr class="{severity_class}">
                    <td>{file_path}</td>
                    <td><code>{diff.element_name}</code></td>
                    <td>{diff.interface_type.value}</td>
                    <td>{diff.change_type.value}</td>
                    <td>{diff.severity.value}</td>
                    <td>{diff.diff_summary}</td>
                </tr>
"""
        
        html += """
            </tbody>
        </table>
    </div>
</body>
</html>
"""
        return html


def show_interface_diff_viewer(parent=None, baseline_path=None, target_path=None):
    """Show the comprehensive interface diff viewer window."""
    viewer = InterfaceDiffViewer(parent)
    
    if baseline_path:
        viewer.baseline_path.set(baseline_path)
    if target_path:
        viewer.target_path.set(target_path)
    
    return viewer
