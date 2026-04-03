"""
Results viewer dialog - Interactive comparison results display
Simplified version extracted from test.py for modular architecture
"""

import tkinter as tk
from tkinter import ttk, messagebox
import os
import webbrowser


class ComparisonResultsDialog:
    """
    Interactive results viewer dialog showing comparison results.
    Displays files with color-coded status and allows viewing HTML diffs.
    """
    
    def __init__(self, parent, results, folder1_display, folder2_display, 
                 folder1_actual, folder2_actual, files1, files2, report_paths):
        """
        Initialize the results dialog.
        
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
        
        # Create dialog
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Comparison Results - Interactive Viewer")
        self.dialog.geometry("1400x800")
        self.dialog.configure(bg="#f0f4f7")
        self.dialog.grab_set()  # Modal
        
        self.create_ui()
        self.populate_results()
    
    def create_ui(self):
        """Create the UI components"""
        # Header
        header = tk.Frame(self.dialog, bg="#003366", height=60)
        header.pack(fill="x")
        header.pack_propagate(False)
        
        tk.Label(
            header,
            text="📊 Comparison Results - Interactive Viewer",
            font=("Segoe UI", 14, "bold"),
            bg="#003366",
            fg="white"
        ).pack(pady=15)
        
        # Statistics bar
        self.create_stats_bar()
        
        # Main content area
        content_frame = tk.Frame(self.dialog, bg="white")
        content_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Info labels
        info_frame = tk.Frame(content_frame, bg="white")
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
        filter_frame = tk.Frame(content_frame, bg="white")
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
            width=30
        ).pack(side="left", padx=5)
        
        tk.Label(
            filter_frame,
            text="Status:",
            font=("Segoe UI", 9),
            bg="white"
        ).pack(side="left", padx=(20, 5))
        
        self.status_filter = tk.StringVar(value="All")
        status_options = ["All", "Different", "Identical", "Only in Platform", 
                         "Only in Project", "Comments update only", "Error"]
        
        status_combo = ttk.Combobox(
            filter_frame,
            textvariable=self.status_filter,
            values=status_options,
            state="readonly",
            width=25,
            font=("Segoe UI", 9)
        )
        status_combo.pack(side="left", padx=5)
        status_combo.bind("<<ComboboxSelected>>", self.on_filter_change)
        
        # Tree view
        tree_frame = tk.Frame(content_frame, bg="white")
        tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Scrollbars
        vsb = tk.Scrollbar(tree_frame, orient="vertical")
        hsb = tk.Scrollbar(tree_frame, orient="horizontal")
        
        # Create treeview
        columns = ("File Path", "Status", "Lines F1", "Lines F2", "Line Status")
        self.tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set
        )
        
        vsb.config(command=self.tree.yview)
        hsb.config(command=self.tree.xview)
        
        # Configure columns
        self.tree.heading("File Path", text="File Path")
        self.tree.heading("Status", text="Status")
        self.tree.heading("Lines F1", text="Lines F1")
        self.tree.heading("Lines F2", text="Lines F2")
        self.tree.heading("Line Status", text="Line Status")
        
        self.tree.column("File Path", width=500, anchor="w")
        self.tree.column("Status", width=180, anchor="center")
        self.tree.column("Lines F1", width=80, anchor="center")
        self.tree.column("Lines F2", width=80, anchor="center")
        self.tree.column("Line Status", width=300, anchor="w")
        
        # Pack treeview
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        
        # Configure tags for colors
        self.tree.tag_configure("identical", background="#C8E6C9", foreground="#1B5E20")
        self.tree.tag_configure("different", background="#FFF9C4", foreground="#827717")
        self.tree.tag_configure("only1", background="#BBDEFB", foreground="#0D47A1")
        self.tree.tag_configure("only2", background="#FFE0B2", foreground="#BF360C")
        self.tree.tag_configure("comments", background="#E8F5E9", foreground="#2E7D32")
        self.tree.tag_configure("error", background="#FFCDD2", foreground="#B71C1C")
        
        # Bind double-click to view HTML diff
        self.tree.bind("<Double-Button-1>", self.on_tree_double_click)
        
        # Bottom button frame
        button_frame = tk.Frame(self.dialog, bg="#f0f4f7")
        button_frame.pack(fill="x", padx=10, pady=10)
        
        # Action buttons
        tk.Button(
            button_frame,
            text="📁 Open Reports Folder",
            command=self.open_reports_folder,
            bg="#1976D2",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            padx=15,
            pady=8
        ).pack(side="left", padx=5)
        
        tk.Button(
            button_frame,
            text="📊 Open Excel Report",
            command=self.open_excel_report,
            bg="#27ae60",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            padx=15,
            pady=8
        ).pack(side="left", padx=5)
        
        tk.Button(
            button_frame,
            text="📄 Open CSV Report",
            command=self.open_csv_report,
            bg="#f39c12",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            padx=15,
            pady=8
        ).pack(side="left", padx=5)
        
        tk.Button(
            button_frame,
            text="✕ Close",
            command=self.dialog.destroy,
            bg="#c62828",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            padx=20,
            pady=8
        ).pack(side="right", padx=5)
    
    def create_stats_bar(self):
        """Create statistics bar"""
        # Calculate statistics
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
    
    def populate_results(self):
        """Populate the tree with results"""
        self.all_items = []  # Store all items for filtering
        
        for result in self.results:
            file_path = result[0]
            lines1 = result[1]
            lines2 = result[2]
            line_status = result[3]
            status = result[4]
            
            # Determine tag for coloring
            if status == "Identical":
                tag = "identical"
            elif status == "Different":
                tag = "different"
            elif status == "Only in Platform":
                tag = "only1"
            elif status == "Only in Project":
                tag = "only2"
            elif status == "Comments update only":
                tag = "comments"
            elif status == "Error":
                tag = "error"
            else:
                tag = "different"
            
            item_id = self.tree.insert(
                "",
                "end",
                values=(file_path, status, lines1, lines2, line_status),
                tags=(tag,)
            )
            
            # Store item data for filtering
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
        
        # Clear tree
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Re-populate with filtered items
        for item_data in self.all_items:
            file_path = item_data['file_path']
            status = item_data['status']
            result = item_data['result']
            
            # Apply filters
            if filter_text and filter_text not in file_path.lower():
                continue
            
            if status_filter != "All" and status != status_filter:
                continue
            
            # Determine tag
            if status == "Identical":
                tag = "identical"
            elif status == "Different":
                tag = "different"
            elif status == "Only in Platform":
                tag = "only1"
            elif status == "Only in Project":
                tag = "only2"
            elif status == "Comments update only":
                tag = "comments"
            elif status == "Error":
                tag = "error"
            else:
                tag = "different"
            
            self.tree.insert(
                "",
                "end",
                values=(result[0], result[4], result[1], result[2], result[3]),
                tags=(tag,)
            )
    
    def on_tree_double_click(self, event):
        """Handle double-click on tree item"""
        selection = self.tree.selection()
        if not selection:
            return
        
        item = selection[0]
        values = self.tree.item(item, 'values')
        
        if not values:
            return
        
        file_path = values[0]
        status = values[1]
        html_link = None
        
        # Find the HTML diff link
        for result in self.results:
            if result[0] == file_path:
                html_link = result[5]  # HTML diff report column
                break
        
        if html_link and html_link not in ["N/A", "N/A (Identical)", ""]:
            # Open HTML diff in browser
            html_full_path = os.path.join(self.report_paths['output_dir'], html_link)
            if os.path.exists(html_full_path):
                webbrowser.open(f'file://{os.path.abspath(html_full_path)}')
            else:
                messagebox.showwarning(
                    "File Not Found",
                    f"HTML diff file not found:\n{html_full_path}"
                )
        else:
            messagebox.showinfo(
                "No Diff Available",
                f"No HTML diff available for this file.\n\n"
                f"Status: {status}\n"
                f"File: {file_path}"
            )
    
    def open_reports_folder(self):
        """Open the reports folder in file explorer"""
        output_dir = self.report_paths['output_dir']
        if os.path.exists(output_dir):
            if os.name == 'nt':  # Windows
                os.startfile(output_dir)
            elif os.name == 'posix':  # macOS/Linux
                os.system(f'open "{output_dir}"' if os.uname().sysname == 'Darwin' 
                         else f'xdg-open "{output_dir}"')
        else:
            messagebox.showerror("Error", f"Folder not found: {output_dir}")
    
    def open_excel_report(self):
        """Open Excel report"""
        excel_path = self.report_paths['excel']
        if os.path.exists(excel_path):
            if os.name == 'nt':  # Windows
                os.startfile(excel_path)
            else:
                webbrowser.open(f'file://{os.path.abspath(excel_path)}')
        else:
            messagebox.showerror("Error", f"Excel file not found: {excel_path}")
    
    def open_csv_report(self):
        """Open CSV report"""
        csv_path = self.report_paths['csv']
        if os.path.exists(csv_path):
            if os.name == 'nt':  # Windows
                os.startfile(csv_path)
            else:
                webbrowser.open(f'file://{os.path.abspath(csv_path)}')
        else:
            messagebox.showerror("Error", f"CSV file not found: {csv_path}")
    
    def show(self):
        """Show the dialog and wait for it to close"""
        self.dialog.wait_window()


def show_results_dialog(parent, results, folder1_display, folder2_display,
                        folder1_actual, folder2_actual, files1, files2, report_paths):
    """
    Show the comparison results dialog.
    
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
