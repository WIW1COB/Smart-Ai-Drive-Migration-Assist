"""
Platform Dependency Viewer
Analyzes dependencies within a single source folder (platform/project).

Shows #include relationships, dependency chains, and impact analysis.
"""

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
from typing import Dict, Set, List, Optional

# Import dependency graph module
try:
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from dependency_graph import DependencyGraphBuilder, DependencyGraph, DependencyNode
    DEPENDENCY_GRAPH_AVAILABLE = True
except ImportError:
    DEPENDENCY_GRAPH_AVAILABLE = False
    DependencyGraphBuilder = None
    DependencyGraph = None
    DependencyNode = None


class PlatformDependencyViewer:
    """
    Single-folder dependency analysis tool.
    
    Analyzes #include relationships within a single source folder to understand:
    - Which files include which other files
    - Which files are most critical (highest impact if changed)
    - Dependency chains between files
    - Circular dependencies
    """
    
    def __init__(self, parent):
        self.parent = parent
        self.graph: Optional[DependencyGraph] = None
        self.folder_path: str = ""
        self.all_files: Dict[str, str] = {}  # rel_path -> abs_path
        
        # Build the window
        self.window = tk.Toplevel(parent)
        self.window.title("Platform Dependency Analysis")
        self.window.geometry("1100x750")
        self.window.minsize(900, 600)
        self.window.configure(bg="#EAF3FB")
        
        self._build_ui()
        
    def _build_ui(self):
        """Build the user interface"""
        # Header
        header = tk.Frame(self.window, bg="#003366", height=60)
        header.pack(fill="x")
        header.pack_propagate(False)
        
        tk.Label(
            header,
            text="🔍 Platform Dependency Analysis",
            font=("Segoe UI", 16, "bold"),
            bg="#003366",
            fg="white"
        ).pack(side="left", padx=20, pady=15)
        
        tk.Label(
            header,
            text="Analyze #include dependencies within a single folder",
            font=("Segoe UI", 10),
            bg="#003366",
            fg="#B8D8FF"
        ).pack(side="left", padx=10, pady=15)
        
        # Folder selection frame
        folder_frame = tk.Frame(self.window, bg="#EAF3FB")
        folder_frame.pack(fill="x", padx=20, pady=15)
        
        tk.Label(
            folder_frame,
            text="Source Folder:",
            font=("Segoe UI", 11, "bold"),
            bg="#EAF3FB"
        ).pack(side="left", padx=(0, 10))
        
        self.folder_entry = tk.Entry(folder_frame, font=("Segoe UI", 10), width=60)
        self.folder_entry.pack(side="left", padx=5)
        
        tk.Button(
            folder_frame,
            text="Browse...",
            command=self._browse_folder,
            bg="#0066CC",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            padx=15
        ).pack(side="left", padx=5)
        
        self.analyze_btn = tk.Button(
            folder_frame,
            text="▶ Analyze Dependencies",
            command=self._start_analysis,
            bg="#007B3E",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            padx=20
        )
        self.analyze_btn.pack(side="left", padx=15)
        
        # Progress bar
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            self.window,
            variable=self.progress_var,
            maximum=100,
            length=400
        )
        self.progress_bar.pack(pady=5)
        
        self.status_label = tk.Label(
            self.window,
            text="Select a folder and click 'Analyze Dependencies'",
            font=("Segoe UI", 9),
            bg="#EAF3FB",
            fg="#666666"
        )
        self.status_label.pack()
        
        # Main content area with paned window
        paned = ttk.PanedWindow(self.window, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Left panel - File tree
        left_frame = tk.Frame(paned, bg="#FFFFFF")
        paned.add(left_frame, weight=1)
        
        # Search box for files
        search_frame = tk.Frame(left_frame, bg="#FFFFFF")
        search_frame.pack(fill="x", padx=5, pady=5)
        
        tk.Label(
            search_frame,
            text="🔎",
            font=("Segoe UI", 10),
            bg="#FFFFFF"
        ).pack(side="left")
        
        self.search_var = tk.StringVar()
        self.search_var.trace("w", self._on_search_change)
        self.search_entry = tk.Entry(
            search_frame,
            textvariable=self.search_var,
            font=("Segoe UI", 10),
            width=30
        )
        self.search_entry.pack(side="left", padx=5, fill="x", expand=True)
        
        # Filter options
        filter_frame = tk.Frame(left_frame, bg="#FFFFFF")
        filter_frame.pack(fill="x", padx=5)
        
        self.filter_var = tk.StringVar(value="all")
        tk.Radiobutton(
            filter_frame, text="All", variable=self.filter_var, value="all",
            bg="#FFFFFF", command=self._apply_filter
        ).pack(side="left")
        tk.Radiobutton(
            filter_frame, text="Headers (.h)", variable=self.filter_var, value="headers",
            bg="#FFFFFF", command=self._apply_filter
        ).pack(side="left")
        tk.Radiobutton(
            filter_frame, text="Sources (.c)", variable=self.filter_var, value="sources",
            bg="#FFFFFF", command=self._apply_filter
        ).pack(side="left")
        tk.Radiobutton(
            filter_frame, text="High Impact", variable=self.filter_var, value="high_impact",
            bg="#FFFFFF", command=self._apply_filter
        ).pack(side="left")
        
        # Tree view for files
        tree_frame = tk.Frame(left_frame, bg="#FFFFFF")
        tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        columns = ("file", "type", "includes", "included_by", "impact")
        self.file_tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            selectmode="browse"
        )
        
        self.file_tree.heading("file", text="File", command=lambda: self._sort_tree("file"))
        self.file_tree.heading("type", text="Type", command=lambda: self._sort_tree("type"))
        self.file_tree.heading("includes", text="Includes", command=lambda: self._sort_tree("includes"))
        self.file_tree.heading("included_by", text="Included By", command=lambda: self._sort_tree("included_by"))
        self.file_tree.heading("impact", text="Impact", command=lambda: self._sort_tree("impact"))
        
        self.file_tree.column("file", width=250, minwidth=150)
        self.file_tree.column("type", width=70, minwidth=50)
        self.file_tree.column("includes", width=80, minwidth=50)
        self.file_tree.column("included_by", width=90, minwidth=50)
        self.file_tree.column("impact", width=70, minwidth=50)
        
        # Scrollbars
        tree_scroll_y = ttk.Scrollbar(tree_frame, orient="vertical", command=self.file_tree.yview)
        tree_scroll_x = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.file_tree.xview)
        self.file_tree.configure(yscrollcommand=tree_scroll_y.set, xscrollcommand=tree_scroll_x.set)
        
        tree_scroll_y.pack(side="right", fill="y")
        tree_scroll_x.pack(side="bottom", fill="x")
        self.file_tree.pack(fill="both", expand=True)
        
        self.file_tree.bind("<<TreeviewSelect>>", self._on_file_select)
        
        # Right panel - Details
        right_frame = tk.Frame(paned, bg="#FFFFFF")
        paned.add(right_frame, weight=1)
        
        # Selected file info
        self.detail_label = tk.Label(
            right_frame,
            text="Select a file to view dependencies",
            font=("Segoe UI", 12, "bold"),
            bg="#FFFFFF",
            anchor="w"
        )
        self.detail_label.pack(fill="x", padx=10, pady=(10, 5))
        
        # Notebook for different views
        self.detail_notebook = ttk.Notebook(right_frame)
        self.detail_notebook.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Tab 1: Files this file includes
        includes_frame = tk.Frame(self.detail_notebook, bg="#FFFFFF")
        self.detail_notebook.add(includes_frame, text="📤 Includes (Dependencies)")
        
        self.includes_text = scrolledtext.ScrolledText(
            includes_frame,
            font=("Consolas", 10),
            bg="#F8F9FA",
            wrap="none",
            height=15
        )
        self.includes_text.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Tab 2: Files that include this file
        included_by_frame = tk.Frame(self.detail_notebook, bg="#FFFFFF")
        self.detail_notebook.add(included_by_frame, text="📥 Included By (Dependents)")
        
        self.included_by_text = scrolledtext.ScrolledText(
            included_by_frame,
            font=("Consolas", 10),
            bg="#F8F9FA",
            wrap="none",
            height=15
        )
        self.included_by_text.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Tab 3: Full dependency chain
        chain_frame = tk.Frame(self.detail_notebook, bg="#FFFFFF")
        self.detail_notebook.add(chain_frame, text="🔗 Dependency Chain")
        
        self.chain_text = scrolledtext.ScrolledText(
            chain_frame,
            font=("Consolas", 10),
            bg="#F8F9FA",
            wrap="none",
            height=15
        )
        self.chain_text.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Tab 4: Summary / Statistics
        stats_frame = tk.Frame(self.detail_notebook, bg="#FFFFFF")
        self.detail_notebook.add(stats_frame, text="📊 Statistics")
        
        self.stats_text = scrolledtext.ScrolledText(
            stats_frame,
            font=("Consolas", 10),
            bg="#F8F9FA",
            wrap="none",
            height=15
        )
        self.stats_text.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Bottom action bar
        action_bar = tk.Frame(self.window, bg="#EAF3FB")
        action_bar.pack(fill="x", padx=10, pady=10)
        
        tk.Button(
            action_bar,
            text="📋 Copy Report",
            command=self._copy_report,
            bg="#666666",
            fg="white",
            font=("Segoe UI", 9)
        ).pack(side="left", padx=5)
        
        tk.Button(
            action_bar,
            text="💾 Export to CSV",
            command=self._export_csv,
            bg="#666666",
            fg="white",
            font=("Segoe UI", 9)
        ).pack(side="left", padx=5)
        
        tk.Button(
            action_bar,
            text="⚠️ Find Circular Dependencies",
            command=self._find_circular_deps,
            bg="#CC6600",
            fg="white",
            font=("Segoe UI", 9, "bold")
        ).pack(side="left", padx=5)
        
        tk.Button(
            action_bar,
            text="🔥 Show High Impact Files",
            command=self._show_high_impact,
            bg="#CC0000",
            fg="white",
            font=("Segoe UI", 9, "bold")
        ).pack(side="left", padx=5)
        
        # Sort state
        self._sort_column = "impact"
        self._sort_reverse = True
        
    def _browse_folder(self):
        """Browse for folder"""
        folder = filedialog.askdirectory(title="Select Source Folder to Analyze")
        if folder:
            self.folder_entry.delete(0, tk.END)
            self.folder_entry.insert(0, folder)
    
    def _start_analysis(self):
        """Start dependency analysis in background thread"""
        folder = self.folder_entry.get().strip()
        if not folder:
            messagebox.showerror("Error", "Please select a folder to analyze.")
            return
        
        if not os.path.isdir(folder):
            messagebox.showerror("Error", f"Folder does not exist:\n{folder}")
            return
        
        if not DEPENDENCY_GRAPH_AVAILABLE:
            messagebox.showerror(
                "Error",
                "Dependency graph module not available.\n"
                "Make sure dependency_graph.py is in the src folder."
            )
            return
        
        self.folder_path = folder
        self.analyze_btn.config(state="disabled")
        self.status_label.config(text="Analyzing dependencies...")
        self.progress_var.set(10)
        
        # Clear existing data
        for item in self.file_tree.get_children():
            self.file_tree.delete(item)
        
        # Run analysis in background
        thread = threading.Thread(target=self._run_analysis, daemon=True)
        thread.start()
    
    def _run_analysis(self):
        """Run dependency analysis (background thread)"""
        try:
            self.window.after(0, lambda: self.progress_var.set(20))
            self.window.after(0, lambda: self.status_label.config(text="Building dependency graph..."))
            
            # Build the graph
            builder = DependencyGraphBuilder()
            self.graph = builder.build_graph(self.folder_path)
            
            self.window.after(0, lambda: self.progress_var.set(60))
            self.window.after(0, lambda: self.status_label.config(text="Processing results..."))
            
            # Calculate statistics
            stats = self._calculate_stats()
            
            self.window.after(0, lambda: self.progress_var.set(80))
            
            # Update UI on main thread
            self.window.after(0, lambda: self._populate_tree())
            self.window.after(0, lambda: self._show_stats(stats))
            self.window.after(0, lambda: self.progress_var.set(100))
            self.window.after(0, lambda: self.status_label.config(
                text=f"✅ Analysis complete: {len(self.graph.nodes)} files analyzed"
            ))
            
        except Exception as e:
            self.window.after(0, lambda: messagebox.showerror("Error", f"Analysis failed:\n{e}"))
            self.window.after(0, lambda: self.status_label.config(text=f"❌ Error: {e}"))
        finally:
            self.window.after(0, lambda: self.analyze_btn.config(state="normal"))
            self.window.after(0, lambda: self.progress_var.set(0))
    
    def _calculate_stats(self) -> dict:
        """Calculate statistics about the dependency graph"""
        if not self.graph:
            return {}
        
        stats = {
            "total_files": len(self.graph.nodes),
            "headers": 0,
            "sources": 0,
            "orphan_headers": 0,  # Headers not included by anyone
            "orphan_sources": 0,  # Sources that don't include anything
            "max_includes": 0,
            "max_included_by": 0,
            "max_impact": 0,
            "most_included_file": "",
            "most_including_file": "",
            "highest_impact_file": "",
            "avg_includes": 0,
            "avg_included_by": 0,
        }
        
        total_includes = 0
        total_included_by = 0
        
        for rel_path, node in self.graph.nodes.items():
            if node.is_header:
                stats["headers"] += 1
                if len(node.included_by) == 0:
                    stats["orphan_headers"] += 1
            elif node.is_source:
                stats["sources"] += 1
                if len(node.resolved_includes) == 0:
                    stats["orphan_sources"] += 1
            
            num_includes = len(node.resolved_includes)
            num_included_by = len(node.included_by)
            impact = self.graph.get_impact_radius(rel_path)
            
            total_includes += num_includes
            total_included_by += num_included_by
            
            if num_includes > stats["max_includes"]:
                stats["max_includes"] = num_includes
                stats["most_including_file"] = rel_path
            
            if num_included_by > stats["max_included_by"]:
                stats["max_included_by"] = num_included_by
                stats["most_included_file"] = rel_path
            
            if impact > stats["max_impact"]:
                stats["max_impact"] = impact
                stats["highest_impact_file"] = rel_path
        
        if stats["total_files"] > 0:
            stats["avg_includes"] = total_includes / stats["total_files"]
            stats["avg_included_by"] = total_included_by / stats["total_files"]
        
        return stats
    
    def _populate_tree(self):
        """Populate the file tree with analysis results"""
        if not self.graph:
            return
        
        # Collect data
        items = []
        for rel_path, node in self.graph.nodes.items():
            file_type = "Header" if node.is_header else "Source" if node.is_source else "Other"
            num_includes = len(node.resolved_includes)
            num_included_by = len(node.included_by)
            impact = self.graph.get_impact_radius(rel_path)
            
            items.append({
                "file": rel_path,
                "type": file_type,
                "includes": num_includes,
                "included_by": num_included_by,
                "impact": impact,
            })
        
        # Sort by impact (descending) by default
        items.sort(key=lambda x: x["impact"], reverse=True)
        
        # Insert into tree
        for item in items:
            # Color code based on impact
            tags = ()
            if item["impact"] >= 10:
                tags = ("high_impact",)
            elif item["impact"] >= 5:
                tags = ("medium_impact",)
            
            self.file_tree.insert(
                "",
                "end",
                values=(
                    item["file"],
                    item["type"],
                    item["includes"],
                    item["included_by"],
                    item["impact"]
                ),
                tags=tags
            )
        
        # Configure tags for coloring
        self.file_tree.tag_configure("high_impact", background="#FFE0E0")
        self.file_tree.tag_configure("medium_impact", background="#FFF0E0")
    
    def _show_stats(self, stats: dict):
        """Display statistics"""
        self.stats_text.delete("1.0", "end")
        
        text = f"""
╔══════════════════════════════════════════════════════════════╗
║           PLATFORM DEPENDENCY ANALYSIS REPORT                ║
╚══════════════════════════════════════════════════════════════╝

📁 Folder: {self.folder_path}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 FILE STATISTICS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Total Files Analyzed:     {stats.get('total_files', 0)}
  Header Files (.h):        {stats.get('headers', 0)}
  Source Files (.c/.cpp):   {stats.get('sources', 0)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔗 DEPENDENCY STATISTICS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Average includes per file:     {stats.get('avg_includes', 0):.1f}
  Average dependents per file:   {stats.get('avg_included_by', 0):.1f}
  
  Most including file:
    {stats.get('most_including_file', 'N/A')}
    ({stats.get('max_includes', 0)} includes)
  
  Most included file:
    {stats.get('most_included_file', 'N/A')}
    ({stats.get('max_included_by', 0)} dependents)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ RISK ANALYSIS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Highest impact file:
    {stats.get('highest_impact_file', 'N/A')}
    (Changes affect {stats.get('max_impact', 0)} files)
  
  Orphan headers (never included):  {stats.get('orphan_headers', 0)}
  Isolated sources (no includes):   {stats.get('orphan_sources', 0)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 RECOMMENDATIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        # Add recommendations based on stats
        if stats.get('orphan_headers', 0) > 0:
            text += f"  • Review {stats['orphan_headers']} orphan headers - may be unused\n"
        
        if stats.get('max_impact', 0) > 20:
            text += f"  • High-impact file detected - consider interface stability\n"
        
        if stats.get('max_includes', 0) > 15:
            text += f"  • Some files have many includes - consider modularization\n"
        
        self.stats_text.insert("1.0", text)
    
    def _on_file_select(self, event):
        """Handle file selection"""
        selection = self.file_tree.selection()
        if not selection:
            return
        
        item = selection[0]
        values = self.file_tree.item(item, "values")
        if not values:
            return
        
        rel_path = values[0]
        self._show_file_details(rel_path)
    
    def _show_file_details(self, rel_path: str):
        """Show detailed dependency info for a file"""
        if not self.graph:
            return
        
        node = self.graph.get_node(rel_path)
        if not node:
            return
        
        # Update header
        self.detail_label.config(text=f"📄 {rel_path}")
        
        # Tab 1: Files this file includes
        self.includes_text.delete("1.0", "end")
        if node.resolved_includes:
            text = f"Files included by {os.path.basename(rel_path)}:\n"
            text += "=" * 50 + "\n\n"
            for inc in sorted(node.resolved_includes):
                impact = self.graph.get_impact_radius(inc)
                text += f"  → {inc}  (impact: {impact})\n"
            text += f"\nTotal: {len(node.resolved_includes)} files"
        else:
            text = "This file does not include any other files."
        self.includes_text.insert("1.0", text)
        
        # Tab 2: Files that include this file
        self.included_by_text.delete("1.0", "end")
        if node.included_by:
            text = f"Files that include {os.path.basename(rel_path)}:\n"
            text += "=" * 50 + "\n\n"
            for dep in sorted(node.included_by):
                text += f"  ← {dep}\n"
            text += f"\nTotal: {len(node.included_by)} files"
        else:
            text = "No files include this file (leaf node or orphan header)."
        self.included_by_text.insert("1.0", text)
        
        # Tab 3: Dependency chain
        self.chain_text.delete("1.0", "end")
        
        # Get transitive dependencies and dependents
        all_deps = self.graph.get_dependencies(rel_path, recursive=True)
        all_dependents = self.graph.get_dependents(rel_path, recursive=True)
        
        text = f"Dependency Chain for {os.path.basename(rel_path)}:\n"
        text += "=" * 50 + "\n\n"
        
        text += "📤 UPSTREAM DEPENDENCIES (what this file needs):\n"
        text += "-" * 40 + "\n"
        if all_deps:
            for dep in sorted(all_deps):
                text += f"  ↑ {dep}\n"
            text += f"\nTotal upstream: {len(all_deps)} files\n"
        else:
            text += "  (none)\n"
        
        text += "\n📥 DOWNSTREAM DEPENDENTS (what needs this file):\n"
        text += "-" * 40 + "\n"
        if all_dependents:
            for dep in sorted(all_dependents):
                text += f"  ↓ {dep}\n"
            text += f"\nTotal downstream: {len(all_dependents)} files\n"
        else:
            text += "  (none)\n"
        
        impact = self.graph.get_impact_radius(rel_path)
        text += f"\n⚠️ IMPACT RADIUS: {impact} files affected if this file changes"
        
        self.chain_text.insert("1.0", text)
    
    def _on_search_change(self, *args):
        """Handle search text change"""
        self._apply_filter()
    
    def _apply_filter(self):
        """Apply search and filter"""
        if not self.graph:
            return
        
        search_text = self.search_var.get().lower()
        filter_type = self.filter_var.get()
        
        # Clear tree
        for item in self.file_tree.get_children():
            self.file_tree.delete(item)
        
        # Filter and add items
        for rel_path, node in self.graph.nodes.items():
            # Search filter
            if search_text and search_text not in rel_path.lower():
                continue
            
            # Type filter
            if filter_type == "headers" and not node.is_header:
                continue
            if filter_type == "sources" and not node.is_source:
                continue
            
            impact = self.graph.get_impact_radius(rel_path)
            
            if filter_type == "high_impact" and impact < 5:
                continue
            
            file_type = "Header" if node.is_header else "Source" if node.is_source else "Other"
            num_includes = len(node.resolved_includes)
            num_included_by = len(node.included_by)
            
            tags = ()
            if impact >= 10:
                tags = ("high_impact",)
            elif impact >= 5:
                tags = ("medium_impact",)
            
            self.file_tree.insert(
                "",
                "end",
                values=(rel_path, file_type, num_includes, num_included_by, impact),
                tags=tags
            )
    
    def _sort_tree(self, column):
        """Sort tree by column"""
        if self._sort_column == column:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = column
            self._sort_reverse = column in ("includes", "included_by", "impact")
        
        # Get all items
        items = [(self.file_tree.set(item, column), item) for item in self.file_tree.get_children()]
        
        # Sort
        try:
            items.sort(key=lambda x: int(x[0]), reverse=self._sort_reverse)
        except ValueError:
            items.sort(key=lambda x: x[0].lower(), reverse=self._sort_reverse)
        
        # Rearrange
        for index, (_, item) in enumerate(items):
            self.file_tree.move(item, "", index)
    
    def _find_circular_deps(self):
        """Find and display circular dependencies"""
        if not self.graph:
            messagebox.showinfo("Info", "Please analyze a folder first.")
            return
        
        cycles = self.graph.find_circular_dependencies()
        
        if not cycles:
            messagebox.showinfo(
                "No Circular Dependencies",
                "✅ No circular dependencies found in this codebase."
            )
            return
        
        # Show in a popup
        popup = tk.Toplevel(self.window)
        popup.title("⚠️ Circular Dependencies Found")
        popup.geometry("600x400")
        
        tk.Label(
            popup,
            text=f"Found {len(cycles)} circular dependency chain(s):",
            font=("Segoe UI", 12, "bold"),
            fg="#CC0000"
        ).pack(pady=10)
        
        text = scrolledtext.ScrolledText(popup, font=("Consolas", 10), wrap="word")
        text.pack(fill="both", expand=True, padx=10, pady=10)
        
        for i, cycle in enumerate(cycles, 1):
            text.insert("end", f"\n🔄 Cycle {i}:\n")
            text.insert("end", "  " + " → ".join(cycle) + "\n")
        
        text.config(state="disabled")
    
    def _show_high_impact(self):
        """Show high impact files popup"""
        if not self.graph:
            messagebox.showinfo("Info", "Please analyze a folder first.")
            return
        
        # Get top 20 high impact files
        impact_list = []
        for rel_path in self.graph.nodes:
            impact = self.graph.get_impact_radius(rel_path)
            if impact > 0:
                impact_list.append((rel_path, impact))
        
        impact_list.sort(key=lambda x: x[1], reverse=True)
        top_20 = impact_list[:20]
        
        if not top_20:
            messagebox.showinfo("Info", "No high-impact files found.")
            return
        
        # Show in popup
        popup = tk.Toplevel(self.window)
        popup.title("🔥 High Impact Files")
        popup.geometry("700x500")
        
        tk.Label(
            popup,
            text="Files with Highest Impact (changes affect most files):",
            font=("Segoe UI", 12, "bold"),
            fg="#CC0000"
        ).pack(pady=10)
        
        text = scrolledtext.ScrolledText(popup, font=("Consolas", 10), wrap="none")
        text.pack(fill="both", expand=True, padx=10, pady=10)
        
        text.insert("end", f"{'Rank':<6} {'Impact':<10} {'File'}\n")
        text.insert("end", "=" * 70 + "\n")
        
        for i, (path, impact) in enumerate(top_20, 1):
            text.insert("end", f"{i:<6} {impact:<10} {path}\n")
        
        text.config(state="disabled")
    
    def _copy_report(self):
        """Copy statistics report to clipboard"""
        report = self.stats_text.get("1.0", "end")
        self.window.clipboard_clear()
        self.window.clipboard_append(report)
        messagebox.showinfo("Copied", "Report copied to clipboard!")
    
    def _export_csv(self):
        """Export analysis to CSV"""
        if not self.graph:
            messagebox.showinfo("Info", "Please analyze a folder first.")
            return
        
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Export Dependency Analysis"
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("File,Type,Includes,Included By,Impact\n")
                for rel_path, node in self.graph.nodes.items():
                    file_type = "Header" if node.is_header else "Source" if node.is_source else "Other"
                    num_includes = len(node.resolved_includes)
                    num_included_by = len(node.included_by)
                    impact = self.graph.get_impact_radius(rel_path)
                    f.write(f'"{rel_path}",{file_type},{num_includes},{num_included_by},{impact}\n')
            
            messagebox.showinfo("Exported", f"Analysis exported to:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Export failed:\n{e}")
