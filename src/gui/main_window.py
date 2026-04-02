"""Main window for the Migration Analysis Tool GUI"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os


class MigrationAnalysisGUI:
    """Main GUI window for Migration Analysis Tool"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Migration Analysis Report Generator")
        self.root.geometry("780x540")
        self.root.config(bg="#EAF3FB")
        
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the main UI components"""
        # Header
        self.create_header()
        
        # Comparison Mode Selection
        self.create_mode_selection()
        
        # Input frames
        self.create_folder_input_frame()
        self.create_snapshot_input_frame()
        
        # RTC Integration Section
        self.create_rtc_section()
        
        # Action buttons
        self.create_action_buttons()
        
        # Progress section
        self.create_progress_section()
    
    def create_header(self):
        """Create the Bosch-style header"""
        header_frame = tk.Frame(self.root, bg="#EAF3FB")
        header_frame.pack(fill="x")
        
        top_strip = tk.Label(header_frame, bg="#E60000", height=1)
        top_strip.pack(fill="x")
        
        title_frame = tk.Frame(header_frame, bg="#003366")
        title_frame.pack(fill="x")
        
        title_label = tk.Label(
            title_frame,
            text="Migration Analysis Report Generator",
            font=("Segoe UI", 18, "bold"),
            bg="#003366",
            fg="white"
        )
        title_label.pack(padx=10, pady=10)
    
    def create_mode_selection(self):
        """Create comparison mode selection"""
        mode_frame = tk.Frame(self.root, bg="#EAF3FB")
        mode_frame.pack(pady=(20, 10))
        
        tk.Label(
            mode_frame,
            text="Comparison Mode:",
            bg="#EAF3FB",
            font=("Segoe UI", 11, "bold")
        ).pack(side="left", padx=5)
        
        self.comparison_mode = tk.StringVar(value="folder")
        
        tk.Radiobutton(
            mode_frame,
            text="Folder/ZIP Comparison",
            variable=self.comparison_mode,
            value="folder",
            bg="#EAF3FB",
            font=("Segoe UI", 10),
            command=self.toggle_input_mode
        ).pack(side="left", padx=10)
        
        tk.Radiobutton(
            mode_frame,
            text="RTC Snapshot Comparison",
            variable=self.comparison_mode,
            value="snapshot",
            bg="#EAF3FB",
            font=("Segoe UI", 10),
            command=self.toggle_input_mode
        ).pack(side="left", padx=10)
    
    def create_folder_input_frame(self):
        """Create folder input section"""
        self.folder_input_frame = tk.Frame(self.root, bg="#EAF3FB")
        self.folder_input_frame.pack(fill="x")
        
        tk.Label(
            self.folder_input_frame,
            text="Select Platform Folder (or ZIP file):",
            bg="#EAF3FB",
            font=("Segoe UI", 11)
        ).pack(pady=(5, 5))
        
        self.folder1_entry = tk.Entry(self.folder_input_frame, width=85)
        self.folder1_entry.pack()
        
        tk.Button(
            self.folder_input_frame,
            text="Browse",
            bg="#007B3E",
            fg="white",
            command=lambda: self.browse_folder(self.folder1_entry)
        ).pack(pady=5)
        
        tk.Label(
            self.folder_input_frame,
            text="Select Project Folder (or ZIP file):",
            bg="#EAF3FB",
            font=("Segoe UI", 11)
        ).pack(pady=(10, 5))
        
        self.folder2_entry = tk.Entry(self.folder_input_frame, width=85)
        self.folder2_entry.pack()
        
        tk.Button(
            self.folder_input_frame,
            text="Browse",
            bg="#007B3E",
            fg="white",
            command=lambda: self.browse_folder(self.folder2_entry)
        ).pack(pady=5)
    
    def create_snapshot_input_frame(self):
        """Create snapshot input section"""
        self.snapshot_input_frame = tk.Frame(self.root, bg="#EAF3FB")
        
        tk.Label(
            self.snapshot_input_frame,
            text="Platform Snapshot URL/ID:",
            bg="#EAF3FB",
            font=("Segoe UI", 11)
        ).pack(pady=(5, 5))
        
        self.snapshot1_entry = tk.Entry(self.snapshot_input_frame, width=85)
        self.snapshot1_entry.pack()
        
        tk.Label(
            self.snapshot_input_frame,
            text="From RTC web: Copy snapshot URL (with id=_xxxxx) or just the UUID",
            bg="#EAF3FB",
            font=("Segoe UI", 8),
            fg="gray"
        ).pack()
        
        tk.Label(
            self.snapshot_input_frame,
            text="Project Snapshot URL/ID:",
            bg="#EAF3FB",
            font=("Segoe UI", 11)
        ).pack(pady=(10, 5))
        
        self.snapshot2_entry = tk.Entry(self.snapshot_input_frame, width=85)
        self.snapshot2_entry.pack()
        
        tk.Label(
            self.snapshot_input_frame,
            text="From RTC web: Copy snapshot URL (with id=_xxxxx) or just the UUID",
            bg="#EAF3FB",
            font=("Segoe UI", 8),
            fg="gray"
        ).pack()
    
    def create_rtc_section(self):
        """Create RTC integration section"""
        self.rtc_frame = tk.Frame(self.root, bg="#EAF3FB")
        self.rtc_frame.pack(pady=10)
        
        self.rtc_enabled_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            self.rtc_frame,
            text="Enable RTC/ALM WorkItem Integration",
            variable=self.rtc_enabled_var,
            bg="#EAF3FB",
            font=("Segoe UI", 10)
        ).grid(row=0, column=0, sticky="w", padx=5)
    
    def create_action_buttons(self):
        """Create action buttons"""
        button_frame = tk.Frame(self.root, bg="#EAF3FB")
        button_frame.pack(pady=20)
        
        tk.Button(
            button_frame,
            text="Start Comparison",
            bg="#003366",
            fg="white",
            font=("Segoe UI", 12, "bold"),
            width=20,
            height=2,
            command=self.start_comparison
        ).pack()
    
    def create_progress_section(self):
        """Create progress display section"""
        self.progress_frame = tk.Frame(self.root, bg="#EAF3FB")
        self.progress_frame.pack(fill="both", expand=True, pady=10)
        
        self.progress_label = tk.Label(
            self.progress_frame,
            text="Ready to start comparison...",
            bg="#EAF3FB",
            font=("Segoe UI", 10)
        )
        self.progress_label.pack(pady=5)
        
        self.progress_bar = ttk.Progressbar(
            self.progress_frame,
            length=600,
            mode='determinate'
        )
        self.progress_bar.pack(pady=5)
    
    def toggle_input_mode(self):
        """Toggle between folder and snapshot input modes"""
        if self.comparison_mode.get() == "folder":
            self.snapshot_input_frame.pack_forget()
            self.folder_input_frame.pack(fill="x", before=self.rtc_frame)
        else:
            self.folder_input_frame.pack_forget()
            self.snapshot_input_frame.pack(fill="x", before=self.rtc_frame)
    
    def browse_folder(self, entry_field):
        """Browse for folder or ZIP file"""
        choice = messagebox.askyesnocancel(
            "Select Input Type",
            "Do you want to select a FOLDER?\n\nYes = Select Folder\nNo = Select ZIP File\nCancel = Abort"
        )
        
        if choice is None:  # Cancel
            return
        elif choice:  # Yes - Select Folder
            folder_selected = filedialog.askdirectory()
            if folder_selected:
                entry_field.delete(0, tk.END)
                entry_field.insert(0, folder_selected)
        else:  # No - Select ZIP File
            zip_selected = filedialog.askopenfilename(
                title="Select ZIP File",
                filetypes=[("ZIP files", "*.zip"), ("All files", "*.*")]
            )
            if zip_selected:
                entry_field.delete(0, tk.END)
                entry_field.insert(0, zip_selected)
    
    def start_comparison(self):
        """Start the comparison process"""
        # TODO: Implement the actual comparison logic
        # This should call the appropriate comparison functions from the core modules
        messagebox.showinfo(
            "Not Implemented",
            "Comparison logic needs to be implemented.\nRefer to test.py for the complete implementation."
        )
    
    def run(self):
        """Run the GUI application"""
        self.root.mainloop()


def launch_gui():
    """Launch the Migration Analysis Tool GUI"""
    app = MigrationAnalysisGUI()
    app.run()
