"""
Interface Diff Analysis Viewer GUI
Displays interface differences between two baselines with detailed analysis
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import logging
from pathlib import Path

from ..utils.interface_diff import (
    InterfaceDiffEngine, Severity, ChangeType, InterfaceType,
    BaselineDiff, FileDiff
)

logger = logging.getLogger(__name__)


class InterfaceDiffViewer:
    """GUI for analyzing interface differences between two baselines."""
    
    def __init__(self, parent=None):
        """Initialize the interface diff viewer."""
        self.window = tk.Toplevel(parent) if parent else tk.Tk()
        self.window.title("Interface Difference Analysis Tool")
        self.window.geometry("1200x700")
        
        self.baseline_path = tk.StringVar()
        self.target_path = tk.StringVar()
        self.diff_result = None
        self.is_analyzing = False
        
        self._create_ui()
    
    def _create_ui(self):
        """Create the user interface."""
        # Input Section
        self._create_input_section()
        
        # Results Section
        self._create_results_section()
        
        # Status Bar
        self._create_status_bar()
    
    def _create_input_section(self):
        """Create baseline and target selection section."""
        input_frame = ttk.LabelFrame(self.window, text="Select Baselines to Compare", padding=10)
        input_frame.pack(fill="x", padx=10, pady=10)
        
        # Baseline folder
        ttk.Label(input_frame, text="Baseline (Stream 1):").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(input_frame, textvariable=self.baseline_path, width=50).grid(row=0, column=1, padx=5)
        ttk.Button(input_frame, text="Browse", command=self._browse_baseline).grid(row=0, column=2, padx=2)
        
        # Target folder
        ttk.Label(input_frame, text="Target (Stream 2):").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(input_frame, textvariable=self.target_path, width=50).grid(row=1, column=1, padx=5)
        ttk.Button(input_frame, text="Browse", command=self._browse_target).grid(row=1, column=2, padx=2)
        
        # Compare button
        ttk.Button(input_frame, text="🔍 Analyze Interfaces", command=self._start_analysis).grid(
            row=2, column=0, columnspan=3, pady=10, sticky="ew"
        )
    
    def _create_results_section(self):
        """Create results display section."""
        results_frame = ttk.LabelFrame(self.window, text="Analysis Results", padding=10)
        results_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Summary section
        summary_frame = ttk.Frame(results_frame)
        summary_frame.pack(fill="x", pady=5)
        
        self.summary_label = ttk.Label(summary_frame, text="No analysis run yet", foreground="gray")
        self.summary_label.pack(fill="x")
        
        # Notebook for tabbed results
        self.notebook = ttk.Notebook(results_frame)
        self.notebook.pack(fill="both", expand=True, pady=5)
        
        # Summary tab
        self.summary_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.summary_tab, text="📊 Summary")
        self._create_summary_tab()
        
        # Changes by severity tab
        self.severity_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.severity_tab, text="⚠️ By Severity")
        self._create_severity_tab()
        
        # Changes by functional area tab
        self.area_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.area_tab, text="🏭 By Area")
        self._create_area_tab()
        
        # File details tab
        self.files_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.files_tab, text="📁 File Details")
        self._create_files_tab()
    
    def _create_summary_tab(self):
        """Create summary tab content."""
        self.summary_text = tk.Text(self.summary_tab, height=20, width=100, wrap=tk.WORD)
        scrollbar = ttk.Scrollbar(self.summary_tab, orient="vertical", command=self.summary_text.yview)
        self.summary_text.config(yscrollcommand=scrollbar.set)
        
        self.summary_text.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        scrollbar.pack(side="right", fill="y")
    
    def _create_severity_tab(self):
        """Create severity categorization tab."""
        self.severity_text = tk.Text(self.severity_tab, height=20, width=100, wrap=tk.WORD)
        scrollbar = ttk.Scrollbar(self.severity_tab, orient="vertical", command=self.severity_text.yview)
        self.severity_text.config(yscrollcommand=scrollbar.set)
        
        self.severity_text.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        scrollbar.pack(side="right", fill="y")
    
    def _create_area_tab(self):
        """Create functional area tab."""
        self.area_text = tk.Text(self.area_tab, height=20, width=100, wrap=tk.WORD)
        scrollbar = ttk.Scrollbar(self.area_tab, orient="vertical", command=self.area_text.yview)
        self.area_text.config(yscrollcommand=scrollbar.set)
        
        self.area_text.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        scrollbar.pack(side="right", fill="y")
    
    def _create_files_tab(self):
        """Create file details tab."""
        # Tree view for file details
        columns = ("File", "Status", "Changes", "🔴", "🟡", "🟢")
        self.files_tree = ttk.Treeview(self.files_tab, columns=columns, show="tree headings", height=20)
        
        for col in columns:
            self.files_tree.column(col, width=150)
            self.files_tree.heading(col, text=col)
        
        scrollbar = ttk.Scrollbar(self.files_tab, orient="vertical", command=self.files_tree.yview)
        self.files_tree.config(yscrollcommand=scrollbar.set)
        
        self.files_tree.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        scrollbar.pack(side="right", fill="y")
    
    def _create_status_bar(self):
        """Create status bar."""
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(self.window, textvariable=self.status_var, relief="sunken")
        status_bar.pack(fill="x", side="bottom")
    
    def _browse_baseline(self):
        """Browse for baseline folder."""
        folder = filedialog.askdirectory(title="Select Baseline (Stream 1) Folder")
        if folder:
            self.baseline_path.set(folder)
    
    def _browse_target(self):
        """Browse for target folder."""
        folder = filedialog.askdirectory(title="Select Target (Stream 2) Folder")
        if folder:
            self.target_path.set(folder)
    
    def _start_analysis(self):
        """Start the interface analysis."""
        if not self.baseline_path.get() or not self.target_path.get():
            messagebox.showwarning("Missing Input", "Please select both baseline and target folders")
            return
        
        # Start analysis in background thread
        thread = threading.Thread(target=self._analyze_interfaces, daemon=True)
        thread.start()
    
    def _analyze_interfaces(self):
        """Analyze interfaces between two baselines."""
        try:
            self.is_analyzing = True
            self.status_var.set("🔄 Analyzing interfaces...")
            self.window.update()
            
            engine = InterfaceDiffEngine(ignore_patterns=['*_test.c', '*_mock.c', 'test_*.c'])
            self.diff_result = engine.compare_baselines(
                self.baseline_path.get(),
                self.target_path.get()
            )
            
            self.status_var.set("✅ Analysis complete")
            self._display_results()
            
        except Exception as e:
            messagebox.showerror("Analysis Error", f"Error during analysis:\n{e}")
            logger.exception("Interface analysis error")
            self.status_var.set("❌ Analysis failed")
        finally:
            self.is_analyzing = False
    
    def _display_results(self):
        """Display analysis results in the UI."""
        if not self.diff_result:
            return
        
        # Clear previous results
        self.summary_text.delete(1.0, tk.END)
        self.severity_text.delete(1.0, tk.END)
        self.area_text.delete(1.0, tk.END)
        for item in self.files_tree.get_children():
            self.files_tree.delete(item)
        
        # Display summary
        self._display_summary()
        
        # Display severity breakdown
        self._display_severity()
        
        # Display functional areas
        self._display_areas()
        
        # Display file details
        self._display_files()
        
        # Update summary label
        total = (self.diff_result.breaking_changes + 
                self.diff_result.review_needed + 
                self.diff_result.safe_changes)
        self.summary_label.config(
            text=f"📊 Total Changes: {total} | 🔴 Breaking: {self.diff_result.breaking_changes} | "
                 f"🟡 Review: {self.diff_result.review_needed} | 🟢 Safe: {self.diff_result.safe_changes}",
            foreground="black"
        )
    
    def _display_summary(self):
        """Display summary statistics."""
        text_widget = self.summary_text
        
        text_widget.insert(tk.END, "=== INTERFACE COMPARISON SUMMARY ===\n\n", "header")
        
        text_widget.insert(tk.END, f"Baseline: {self.diff_result.baseline_path}\n")
        text_widget.insert(tk.END, f"Target:   {self.diff_result.target_path}\n\n")
        
        text_widget.insert(tk.END, "FILE STATISTICS:\n")
        text_widget.insert(tk.END, f"  Total Files:    {self.diff_result.total_files}\n")
        text_widget.insert(tk.END, f"  Added:          {self.diff_result.files_added}\n")
        text_widget.insert(tk.END, f"  Removed:        {self.diff_result.files_removed}\n")
        text_widget.insert(tk.END, f"  Modified:       {self.diff_result.files_modified}\n")
        text_widget.insert(tk.END, f"  Unchanged:      {self.diff_result.files_unchanged}\n\n")
        
        text_widget.insert(tk.END, "INTERFACE CHANGES:\n")
        text_widget.insert(tk.END, f"  Total:          {self.diff_result.total_interfaces}\n")
        text_widget.insert(tk.END, f"  Added:          {self.diff_result.interfaces_added}\n")
        text_widget.insert(tk.END, f"  Removed:        {self.diff_result.interfaces_removed}\n")
        text_widget.insert(tk.END, f"  Modified:       {self.diff_result.interfaces_modified}\n\n")
        
        text_widget.insert(tk.END, "IMPACT ASSESSMENT:\n")
        text_widget.insert(tk.END, f"  🔴 Breaking Changes: {self.diff_result.breaking_changes}\n")
        text_widget.insert(tk.END, f"  🟡 Needs Review:     {self.diff_result.review_needed}\n")
        text_widget.insert(tk.END, f"  🟢 Safe Changes:     {self.diff_result.safe_changes}\n")
    
    def _display_severity(self):
        """Display changes categorized by severity."""
        text_widget = self.severity_text
        
        severities = {
            Severity.BREAKING: "🔴 BREAKING CHANGES (Will cause compilation errors)",
            Severity.REVIEW: "🟡 REQUIRES REVIEW (May impact functionality)",
            Severity.SAFE: "🟢 SAFE CHANGES (Can be auto-merged)",
            Severity.INFO: "ℹ️ INFORMATIONAL (Non-functional changes)"
        }
        
        collected_by_severity = {}
        for file_diff in self.diff_result.file_diffs.values():
            for diff in file_diff.diffs:
                if diff.severity not in collected_by_severity:
                    collected_by_severity[diff.severity] = []
                collected_by_severity[diff.severity].append(diff)
        
        for severity in [Severity.BREAKING, Severity.REVIEW, Severity.SAFE, Severity.INFO]:
            diffs = collected_by_severity.get(severity, [])
            text_widget.insert(tk.END, f"\n{severities[severity]}\n")
            text_widget.insert(tk.END, "=" * 80 + "\n")
            
            if diffs:
                for diff in diffs:
                    text_widget.insert(tk.END, 
                        f"  {diff.element_name:<40} [{diff.interface_type.value}] {diff.file_path}\n")
                    text_widget.insert(tk.END, f"    {diff.diff_summary}\n")
            else:
                text_widget.insert(tk.END, "  (none)\n")
    
    def _display_areas(self):
        """Display changes grouped by functional area."""
        text_widget = self.area_text
        
        text_widget.insert(tk.END, "=== CHANGES BY FUNCTIONAL AREA ===\n\n")
        
        for area, diffs in sorted(self.diff_result.by_functional_area.items()):
            breaking = sum(1 for d in diffs if d.severity == Severity.BREAKING)
            review = sum(1 for d in diffs if d.severity == Severity.REVIEW)
            safe = sum(1 for d in diffs if d.severity == Severity.SAFE)
            
            text_widget.insert(tk.END, f"{area}\n")
            text_widget.insert(tk.END, f"  Total: {len(diffs)} | 🔴 {breaking} | 🟡 {review} | 🟢 {safe}\n")
            
            for diff in sorted(diffs, key=lambda d: (d.severity.value, d.element_name)):
                icon = {"breaking": "🔴", "review": "🟡", "safe": "🟢", "info": "ℹ️"}.get(diff.severity.value, "?")
                text_widget.insert(tk.END, f"  {icon} {diff.element_name} ({diff.change_type.value})\n")
            
            text_widget.insert(tk.END, "\n")
    
    def _display_files(self):
        """Display file-level changes."""
        for rel_path, file_diff in sorted(self.diff_result.file_diffs.items()):
            status_icon = {"added": "➕", "removed": "➖", "modified": "✏️", "unchanged": "✓"}.get(
                file_diff.file_status, "?"
            )
            
            self.files_tree.insert("", "end", values=(
                rel_path,
                status_icon + " " + file_diff.file_status,
                len(file_diff.diffs),
                file_diff.breaking_count,
                file_diff.review_count,
                file_diff.safe_count
            ))


def show_interface_diff_viewer(parent=None, baseline_path=None, target_path=None):
    """Show the interface diff viewer window."""
    viewer = InterfaceDiffViewer(parent)
    
    if baseline_path:
        viewer.baseline_path.set(baseline_path)
    if target_path:
        viewer.target_path.set(target_path)
    
    return viewer
