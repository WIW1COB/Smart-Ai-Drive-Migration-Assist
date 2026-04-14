"""Main window for the Migration Analysis Tool GUI"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import threading
import json
import logging

from src.utils.comparison_engine import compare_folders, cleanup_temp_dirs
from src.gui.results_viewer import show_results_dialog
from src.rtc.connection import RTCConnection, get_rtc_connection
from src.config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MigrationAnalysisGUI:
    """Main GUI window for Migration Analysis Tool"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Migration Analysis Report Generator")
        self.root.geometry("780x540")
        self.root.config(bg="#EAF3FB")
        
        # RTC Connection variables
        self.rtc_username = tk.StringVar()
        self.rtc_password = tk.StringVar()
        self.rtc_server_url = tk.StringVar(value=settings.RTC_SERVER_URL)
        self.rtc_connection = None
        
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the main UI components"""
        # Header
        self.create_header()
        
        # Comparison Mode Selection
        self.create_mode_selection()
        
        # Input frames (all 3 modes)
        self.create_folder_input_frame()       # Offline → Offline
        self.create_snapshot_input_frame()     # Online → Online
        self.create_hybrid_input_frame()       # Online → Offline
        
        # RTC Integration Section
        self.create_rtc_section()
        
        # Action buttons
        self.create_action_buttons()
        
        # Progress section
        self.create_progress_section()
        
        # Initially show offline_offline mode
        self.toggle_input_mode()
    
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
        
        self.comparison_mode = tk.StringVar(value="offline_offline")
        
        # Mode 1: Offline → Offline (Folders/ZIPs)
        tk.Radiobutton(
            mode_frame,
            text="📁 Offline → Offline",
            variable=self.comparison_mode,
            value="offline_offline",
            bg="#EAF3FB",
            font=("Segoe UI", 10),
            command=self.toggle_input_mode
        ).pack(side="left", padx=10)
        
        # Mode 2: Online → Online (RTC URLs)
        tk.Radiobutton(
            mode_frame,
            text="🌐 Online → Online",
            variable=self.comparison_mode,
            value="online_online",
            bg="#EAF3FB",
            font=("Segoe UI", 10),
            command=self.toggle_input_mode
        ).pack(side="left", padx=10)
        
        # Mode 3: Online → Offline (RTC URL + Folder)
        tk.Radiobutton(
            mode_frame,
            text="🔄 Online → Offline",
            variable=self.comparison_mode,
            value="online_offline",
            bg="#EAF3FB",
            font=("Segoe UI", 10),
            command=self.toggle_input_mode
        ).pack(side="left", padx=10)
    
    def create_folder_input_frame(self):
        """Create offline → offline input section (Folders/ZIPs)"""
        self.folder_input_frame = tk.Frame(self.root, bg="#EAF3FB")
        self.folder_input_frame.pack(fill="x")
        
        # Info label
        tk.Label(
            self.folder_input_frame,
            text="📁 Offline → Offline: Compare local folders or ZIP files",
            bg="#EAF3FB",
            font=("Segoe UI", 9, "italic"),
            fg="#666666"
        ).pack(pady=(5, 10))
        
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
        """Create online → online input section (RTC URLs)"""
        self.snapshot_input_frame = tk.Frame(self.root, bg="#EAF3FB")
        
        # Info label
        tk.Label(
            self.snapshot_input_frame,
            text="🌐 Online → Online: Compare RTC snapshots/workspaces via URLs",
            bg="#EAF3FB",
            font=("Segoe UI", 9, "italic"),
            fg="#666666"
        ).pack(pady=(5, 10))
        
        tk.Label(
            self.snapshot_input_frame,
            text="Platform Snapshot/Workspace URL or UUID:",
            bg="#EAF3FB",
            font=("Segoe UI", 11)
        ).pack(pady=(5, 5))
        
        self.snapshot1_entry = tk.Entry(self.snapshot_input_frame, width=85)
        self.snapshot1_entry.pack()
        
        tk.Label(
            self.snapshot_input_frame,
            text="📝 From RTC web: Copy snapshot URL (with id=_xxxxx) or just the UUID like _ojreQAAbEfG1br8X33nQcA",
            bg="#EAF3FB",
            font=("Segoe UI", 8),
            fg="gray"
        ).pack()
        
        tk.Label(
            self.snapshot_input_frame,
            text="Project Snapshot/Workspace URL or UUID:",
            bg="#EAF3FB",
            font=("Segoe UI", 11)
        ).pack(pady=(10, 5))
        
        self.snapshot2_entry = tk.Entry(self.snapshot_input_frame, width=85)
        self.snapshot2_entry.pack()
        
        tk.Label(
            self.snapshot_input_frame,
            text="📝 From RTC web: Copy snapshot URL (with id=_xxxxx) or just the UUID like _i3S_vwAaEfG3rPS3zZLwKA",
            bg="#EAF3FB",
            font=("Segoe UI", 8),
            fg="gray"
        ).pack()
    
    def create_hybrid_input_frame(self):
        """Create online → offline input section (RTC URL + Local Folder)"""
        self.hybrid_input_frame = tk.Frame(self.root, bg="#EAF3FB")
        
        # Info label
        tk.Label(
            self.hybrid_input_frame,
            text="🔄 Online → Offline: Compare RTC snapshot with local folder",
            bg="#EAF3FB",
            font=("Segoe UI", 9, "italic"),
            fg="#666666"
        ).pack(pady=(5, 10))
        
        tk.Label(
            self.hybrid_input_frame,
            text="Platform Snapshot/Workspace URL or UUID (Online):",
            bg="#EAF3FB",
            font=("Segoe UI", 11)
        ).pack(pady=(5, 5))
        
        self.hybrid_url_entry = tk.Entry(self.hybrid_input_frame, width=85)
        self.hybrid_url_entry.pack()
        
        tk.Label(
            self.hybrid_input_frame,
            text="📝 From RTC web: Copy snapshot URL or UUID",
            bg="#EAF3FB",
            font=("Segoe UI", 8),
            fg="gray"
        ).pack()
        
        tk.Label(
            self.hybrid_input_frame,
            text="Project Folder or ZIP (Offline):",
            bg="#EAF3FB",
            font=("Segoe UI", 11)
        ).pack(pady=(10, 5))
        
        self.hybrid_folder_entry = tk.Entry(self.hybrid_input_frame, width=85)
        self.hybrid_folder_entry.pack()
        
        tk.Button(
            self.hybrid_input_frame,
            text="Browse",
            bg="#007B3E",
            fg="white",
            command=lambda: self.browse_folder(self.hybrid_folder_entry)
        ).pack(pady=5)
    
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
        
        self.compare_btn = tk.Button(
            button_frame,
            text="Start Comparison",
            bg="#003366",
            fg="white",
            font=("Segoe UI", 12, "bold"),
            width=20,
            height=2,
            command=self.start_comparison
        )
        self.compare_btn.pack()
    
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
        """Toggle between different input modes"""
        mode = self.comparison_mode.get()
        
        # Hide all frames first
        self.folder_input_frame.pack_forget()
        self.snapshot_input_frame.pack_forget()
        self.hybrid_input_frame.pack_forget()
        
        # Show the appropriate frame
        if mode == "offline_offline":
            self.folder_input_frame.pack(fill="x", before=self.rtc_frame)
        elif mode == "online_online":
            self.snapshot_input_frame.pack(fill="x", before=self.rtc_frame)
        elif mode == "online_offline":
            self.hybrid_input_frame.pack(fill="x", before=self.rtc_frame)
    
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
        mode = self.comparison_mode.get()
        
        if mode == "offline_offline":
            # Offline → Offline: Folders/ZIPs
            folder1 = self.folder1_entry.get().strip()
            folder2 = self.folder2_entry.get().strip()
            
            # Validate inputs
            if not folder1 or not folder2:
                messagebox.showerror(
                    "Missing Input",
                    "Please select both folders to compare."
                )
                return
            
            # Check if paths exist
            if not (os.path.exists(folder1) and os.path.exists(folder2)):
                messagebox.showerror(
                    "Invalid Path",
                    "One or both folder paths do not exist."
                )
                return
            
            # Show progress and start comparison in background thread
            self.run_folder_comparison(folder1, folder2)
        
        elif mode == "online_online":
            # Online → Online: RTC Snapshots/URLs
            url1 = self.snapshot1_entry.get().strip()
            url2 = self.snapshot2_entry.get().strip()
            
            if not url1 or not url2:
                messagebox.showerror(
                    "Missing Input",
                    "Please enter both RTC snapshot URLs or UUIDs."
                )
                return
            
            # Check if different
            rtc_temp = RTCConnection(self.rtc_server_url.get(), "", "")
            uuid1 = rtc_temp.extract_snapshot_uuid(url1)
            uuid2 = rtc_temp.extract_snapshot_uuid(url2)
            
            if uuid1 == uuid2:
                messagebox.showerror(
                    "Invalid Input",
                    "⚠️ Both snapshot URLs point to the SAME snapshot!\n\n"
                    "Please select two different snapshots for comparison."
                )
                return
            
            # Request credentials if not already provided
            if not self.rtc_username.get() or not self.rtc_password.get():
                self.show_credential_dialog()
            else:
                # Start comparison with existing credentials
                self.start_snapshot_comparison(url1, url2)
        
        elif mode == "online_offline":
            # Online → Offline: RTC URL + Local Folder
            url = self.hybrid_url_entry.get().strip()
            folder = self.hybrid_folder_entry.get().strip()
            
            if not url or not folder:
                messagebox.showerror(
                    "Missing Input",
                    "Please enter RTC URL and select a local folder."
                )
                return
            
            if not os.path.exists(folder):
                messagebox.showerror(
                    "Invalid Path",
                    "The local folder path does not exist."
                )
                return
            
            messagebox.showinfo(
                "Feature Coming Soon",
                "🔄 Online → Offline Mode\n\n"
                "Comparing RTC snapshot with local folder will be implemented soon."
            )
    
    def show_credential_dialog(self):
        """Show dialog to input RTC credentials"""
        dialog = tk.Toplevel(self.root)
        dialog.title("RTC Login")
        dialog.geometry("450x300")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)
        
        # Center the dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        # Header
        header = tk.Frame(dialog, bg='#003366', height=60)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        tk.Label(
            header,
            text="🔐 RTC Login",
            font=('Segoe UI', 14, 'bold'),
            bg='#003366',
            fg='white'
        ).pack(pady=15)
        
        # Main frame
        main_frame = tk.Frame(dialog, bg='white')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)
        
        tk.Label(
            main_frame,
            text="Enter RTC credentials:",
            font=('Segoe UI', 10),
            bg='white'
        ).pack(anchor=tk.W, pady=(0, 10))
        
        # Username
        tk.Label(main_frame, text="Username:", font=('Segoe UI', 10), bg='white').pack(anchor=tk.W)
        username_entry = ttk.Entry(main_frame, textvariable=self.rtc_username, width=40)
        username_entry.pack(fill=tk.X, pady=(0, 10))
        
        # Password
        tk.Label(main_frame, text="Password:", font=('Segoe UI', 10), bg='white').pack(anchor=tk.W)
        password_entry = ttk.Entry(main_frame, textvariable=self.rtc_password, show='●', width=40)
        password_entry.pack(fill=tk.X, pady=(0, 15))
        
        def on_ok():
            username = self.rtc_username.get().strip()
            password = self.rtc_password.get().strip()
            
            if not username or not password:
                messagebox.showerror('Error', 'Please enter both username and password.')
                return
            
            dialog.destroy()
            
            # Get snapshot URLs
            url1 = self.snapshot1_entry.get().strip()
            url2 = self.snapshot2_entry.get().strip()
            
            # Start comparison
            self.start_snapshot_comparison(url1, url2)
        
        def on_cancel():
            dialog.destroy()
        
        # Buttons
        button_frame = tk.Frame(main_frame, bg='white')
        button_frame.pack(pady=(10, 0))
        
        tk.Button(
            button_frame,
            text="✓ Login",
            command=on_ok,
            font=('Segoe UI', 10, 'bold'),
            bg='#007B3E',
            fg='white',
            padx=20,
            pady=8
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            button_frame,
            text="✕ Cancel",
            command=on_cancel,
            font=('Segoe UI', 10, 'bold'),
            bg='#666666',
            fg='white',
            padx=20,
            pady=8
        ).pack(side=tk.LEFT, padx=5)
        
        username_entry.focus()
        dialog.bind('<Return>', lambda e: on_ok())
        dialog.bind('<Escape>', lambda e: on_cancel())
    
    def start_snapshot_comparison(self, url1, url2):
        """Start RTC snapshot comparison in background thread"""
        # Disable button during processing
        self.compare_btn.config(state='disabled')
        self.progress_bar['value'] = 0
        self.progress_label.config(text="🌐 Connecting to RTC server...")
        self.root.update()
        
        # Run in background thread
        thread = threading.Thread(
            target=self._snapshot_comparison_thread,
            args=(url1, url2),
            daemon=True
        )
        thread.start()
    
    def _snapshot_comparison_thread(self, url1, url2):
        """
        Background thread for snapshot comparison with comprehensive error handling
        
        Steps:
        1. Validate inputs
        2. Test RTC connection
        3. Fetch snapshot 1 components
        4. Fetch snapshot 2 components
        5. Compare snapshots (component-level)
        6. Optionally fetch file-level details
        7. Display results
        """
        try:
            logger.info("=" * 80)
            logger.info("SNAPSHOT COMPARISON STARTED")
            logger.info("=" * 80)
            
            # Get credentials
            username = self.rtc_username.get()
            password = self.rtc_password.get()
            server_url = self.rtc_server_url.get()
            
            # Validate credentials
            self.root.after(0, lambda: self._update_progress(5, "Validating credentials..."))
            if not username or not password:
                error_msg = "Username and password are required"
                logger.error(f"Validation failed: {error_msg}")
                self.root.after(0, lambda: messagebox.showerror('Validation Error', error_msg))
                self.root.after(0, lambda: self.compare_btn.config(state='normal'))
                self.root.after(0, lambda: self._update_progress(0, "Ready"))
                return
            
            logger.info(f"Server: {server_url}")
            logger.info(f"Username: {username}")
            
            # Test connection (with retries)
            self.root.after(0, lambda: self._update_progress(8, "🔗 Testing RTC connection (with retries)..."))
            rtc_conn = None
            error_msg = None
            
            for attempt in range(1, 4):  # 3 attempts
                logger.info(f"Connection attempt {attempt}/3...")
                rtc_conn, error_msg = get_rtc_connection(username, password, server_url)
                
                if rtc_conn:
                    logger.info("✓ RTC connection successful")
                    break
                
                if attempt < 3:
                    logger.warning(f"Attempt {attempt} failed: {error_msg}, retrying...")
                    import time
                    time.sleep(2)  # Wait 2 seconds before retry
            
            if not rtc_conn:
                detailed_error = self._format_connection_error(error_msg)
                logger.error(f"Connection failed after 3 attempts: {error_msg}")
                self.root.after(0, lambda: messagebox.showerror('Connection Error', detailed_error))
                self.root.after(0, lambda: self.compare_btn.config(state='normal'))
                self.root.after(0, lambda: self._update_progress(0, "Ready"))
                return
            
            # Extract and validate UUIDs
            self.root.after(0, lambda: self._update_progress(10, "Validating snapshot URLs..."))
            logger.info("Extracting snapshot UUIDs...")
            
            uuid1 = rtc_conn.extract_snapshot_uuid(url1)
            uuid2 = rtc_conn.extract_snapshot_uuid(url2)
            
            logger.info(f"Snapshot 1 UUID: {uuid1}")
            logger.info(f"Snapshot 2 UUID: {uuid2}")
            
            # Validate UUIDs
            if not uuid1 or not uuid2:
                error_msg = "Could not extract snapshot UUIDs. Please verify the URLs/UUIDs are correct."
                logger.error(error_msg)
                self.root.after(0, lambda: messagebox.showerror('Invalid Input', error_msg))
                self.root.after(0, lambda: self.compare_btn.config(state='normal'))
                self.root.after(0, lambda: self._update_progress(0, "Ready"))
                return
            
            if uuid1 == uuid2:
                error_msg = "⚠️ Both snapshot UUIDs are identical!\n\nPlease select two different snapshots."
                logger.error(f"UUID validation error: {error_msg}")
                self.root.after(0, lambda: messagebox.showerror('Duplicate Snapshot', error_msg))
                self.root.after(0, lambda: self.compare_btn.config(state='normal'))
                self.root.after(0, lambda: self._update_progress(0, "Ready"))
                return
            
            # Fetch snapshot 1 components
            self.root.after(0, lambda: self._update_progress(20, "⬇️ Fetching Snapshot 1 components..."))
            logger.info("Fetching components from Snapshot 1...")
            
            snap1_components = rtc_conn.fetch_snapshot_components(uuid1, 'Snapshot 1')
            
            if not snap1_components:
                error_msg = "❌ No components found in Snapshot 1\n\nPossible reasons:\n" \
                           "• Invalid snapshot UUID\n" \
                           "• Snapshot does not exist\n" \
                           "• Permission denied\n" \
                           "• Network connectivity issue"
                logger.error("Failed to fetch components from Snapshot 1")
                self.root.after(0, lambda: messagebox.showerror('Snapshot 1 Error', error_msg))
                self.root.after(0, lambda: self.compare_btn.config(state='normal'))
                self.root.after(0, lambda: self._update_progress(0, "Ready"))
                return
            
            logger.info(f"✓ Snapshot 1: Found {len(snap1_components)} components")
            
            # Fetch snapshot 2 components
            self.root.after(
                0,
                lambda: self._update_progress(50,f"⬇️ Fetching Snapshot 2 components ({len(snap1_components)} in Snapshot 1)...")
            )
            logger.info("Fetching components from Snapshot 2...")
            
            snap2_components = rtc_conn.fetch_snapshot_components(uuid2, 'Snapshot 2')
            
            if not snap2_components:
                error_msg = "❌ No components found in Snapshot 2\n\nPossible reasons:\n" \
                           "• Invalid snapshot UUID\n" \
                           "• Snapshot does not exist\n" \
                           "• Permission denied\n" \
                           "• Network connectivity issue"
                logger.error("Failed to fetch components from Snapshot 2")
                self.root.after(0, lambda: messagebox.showerror('Snapshot 2 Error', error_msg))
                self.root.after(0, lambda: self.compare_btn.config(state='normal'))
                self.root.after(0, lambda: self._update_progress(0, "Ready"))
                return
            
            logger.info(f"✓ Snapshot 2: Found {len(snap2_components)} components")
            
            # ===== COMPONENT SELECTION (Online Mode Specific) =====
            # Show component selection dialog to user
            self.root.after(0, lambda: self._update_progress(60, "📋 Opening component selection dialog..."))
            logger.info("Showing component selection dialog for online mode...")
            
            from src.gui.dialogs import show_component_selection_dialog
            
            selection_result = show_component_selection_dialog(snap1_components, snap2_components)
            
            if selection_result['canceled']:
                logger.info("⚠️ User canceled component selection")
                self.root.after(0, lambda: messagebox.showinfo('Cancelled', 'Component selection cancelled. Comparison aborted.'))
                self.root.after(0, lambda: self.compare_btn.config(state='normal'))
                self.root.after(0, lambda: self._update_progress(0, "Ready"))
                return
            
            selected_comp_names = set(selection_result['selected'])
            logger.info(f"✓ User selected {len(selected_comp_names)}/{len(selection_result['common'])} common components")
            
            # Filter components to only selected ones
            if selected_comp_names:
                snap1_filtered = [c for c in snap1_components if c.get('name', str(c)) in selected_comp_names]
                snap2_filtered = [c for c in snap2_components if c.get('name', str(c)) in selected_comp_names]
                logger.info(f"Filtered: {len(snap1_filtered)} from Snapshot 1, {len(snap2_filtered)} from Snapshot 2")
                logger.info(f"Excluded: {len(selection_result['only_in_snap1'])} only in Snap1, {len(selection_result['only_in_snap2'])} only in Snap2")
            else:
                logger.warning("No components selected - using all components")
                snap1_filtered = snap1_components
                snap2_filtered = snap2_components
            
            # Compare snapshots (only selected components)
            self.root.after(0, lambda: self._update_progress(70, f"🔍 Comparing {len(snap1_filtered)} selected components..."))
            logger.info(f"Comparing {len(snap1_filtered)} vs {len(snap2_filtered)} selected components...")
            
            comparison_results = rtc_conn.compare_snapshots(snap1_filtered, snap2_filtered)
            
            # Calculate statistics
            modified = sum(1 for r in comparison_results if r['status'] == 'Modified')
            added = sum(1 for r in comparison_results if 'Added' in r['status'])
            removed = sum(1 for r in comparison_results if 'Removed' in r['status'])
            unchanged = sum(1 for r in comparison_results if r['status'] == 'Unchanged')
            
            logger.info(f"Comparison results:")
            logger.info(f"  Modified: {modified}")
            logger.info(f"  Added: {added}")
            logger.info(f"  Removed: {removed}")
            logger.info(f"  Unchanged: {unchanged}")
            logger.info(f"  Total: {len(comparison_results)}")
            
            # Prepare results for viewer
            self.root.after(0, lambda: self._update_progress(85, "📊 Preparing results viewer..."))
            
            # Transform snapshot results into results_viewer format
            viewer_results = self._transform_snapshot_results_for_viewer(comparison_results)
            
            # Store comparison metadata for viewer
            comparison_metadata = {
                'snap1_url': url1,
                'snap2_url': url2,
                'snap1_components': snap1_components,
                'snap2_components': snap2_components,
                'comparison_results': comparison_results
            }
            
            # Display results using enhanced viewer
            self.root.after(0, lambda: self._display_snapshot_results_with_viewer(
                viewer_results, comparison_metadata
            ))
            
            self.root.after(0, lambda: self._update_progress(
                100,
                f"✅ Comparison complete: {len(comparison_results)} components" \
                f" ({modified} modified, {added} added, {removed} removed)"
            ))
            
            logger.info("=" * 80)
            logger.info("SNAPSHOT COMPARISON COMPLETED SUCCESSFULLY")
            logger.info("=" * 80)
            
            self.root.after(2000, lambda: self.compare_btn.config(state='normal'))
            
        except Exception as e:
            logger.error(f"Snapshot comparison error: {e}", exc_info=True)
            error_msg = f"Snapshot comparison failed:\n\n{type(e).__name__}:\n{str(e)[:200]}"
            self.root.after(0, lambda: messagebox.showerror('Error', error_msg))
            self.root.after(0, lambda: self.compare_btn.config(state='normal'))
            self.root.after(0, lambda: self._update_progress(0, "Ready"))
    
    def _format_connection_error(self, error_msg):
        """Format connection error message with troubleshooting tips"""
        if not error_msg:
            return "Unknown connection error"
        
        tips = ""
        if "resolve host" in error_msg.lower():
            tips = "\n\nTroubleshooting:\n" \
                   "• Check network connection\n" \
                   "• Verify RTC server URL is reachable\n" \
                   "• May need VPN (if off-site)"
        elif "authentication" in error_msg.lower() or "401" in error_msg:
            tips = "\n\nTroubleshooting:\n" \
                   "• Verify username and password\n" \
                   "• Check credentials are correct\n" \
                   "• Account may need RTC permissions"
        elif "timeout" in error_msg.lower():
            tips = "\n\nTroubleshooting:\n" \
                   "• Server may be slow or offline\n" \
                   "• Try again in a moment\n" \
                   "• Check network connectivity"
        elif "ssl" in error_msg.lower():
            tips = "\n\nTroubleshooting:\n" \
                   "• SSL certificate issue (if self-signed)\n" \
                   "• May need certificate bypass\n" \
                   "• Contact IT support if persistent"
        
        return f"Cannot connect to RTC:\n{error_msg}{tips}"

    
    def _update_progress(self, value, message):
        """Update progress bar and label"""
        self.progress_bar['value'] = value
        self.progress_label.config(text=message)
        self.root.update_idletasks()
    
    def _transform_snapshot_results_for_viewer(self, comparison_results):
        """
        Transform snapshot comparison results into results_viewer format
        
        Match offline results format:
        [comp_name, metric1, metric2, line_status, status, html_link, purpose, changeset]
        
        For snapshots:
        - index[0] = component name
        - index[1] = snapshot1_uuid length (as numeric reference)
        - index[2] = snapshot2_uuid length (as numeric reference)
        - index[3] = line_status (baseline + UUID info)
        - index[4] = status (Modified|Different|Identical|Only in Snapshot 1|Only in Snapshot 2)
        - index[5] = html_link (N/A for snapshot components)
        - index[6] = purpose
        - index[7] = changeset_info
        """
        viewer_results = []
        
        for result in comparison_results:
            comp_name = result['name']
            status = result['status']
            snap1 = result.get('snapshot1', {})
            snap2 = result.get('snapshot2', {})
            
            # Extract baseline UUIDs
            baseline1_uuid = snap1.get('baseline_uuid', 'N/A') if snap1 else 'N/A'
            baseline2_uuid = snap2.get('baseline_uuid', 'N/A') if snap2 else 'N/A'
            
            # Create numeric metrics (UUID string length for reference)
            metric1 = len(baseline1_uuid) if baseline1_uuid != 'N/A' else 0
            metric2 = len(baseline2_uuid) if baseline2_uuid != 'N/A' else 0
            
            # Create line status with baseline info
            line_status = f"Baseline: {baseline1_uuid[:8]}... → {baseline2_uuid[:8]}..."
            
            # Map status to results_viewer format
            if status == 'Unchanged':
                status_type = 'Identical'
            elif status == 'Modified':
                status_type = 'Different'
            elif status == 'Added in Snapshot 2':
                status_type = 'Only in Snapshot 2'
            elif status == 'Removed in Snapshot 2':
                status_type = 'Only in Snapshot 1'
            else:
                status_type = status
            
            # Create result list matching offline format
            result_list = [
                comp_name,                              # index[0]: component name
                metric1,                                # index[1]: metric1 (baseline1 uuid length)
                metric2,                                # index[2]: metric2 (baseline2 uuid length)
                line_status,                            # index[3]: line_status
                status_type,                            # index[4]: status
                "N/A",                                  # index[5]: html_link (N/A for components)
                f"Component comparison",                # index[6]: purpose
                ""                                      # index[7]: changeset_info (empty for snapshots)
            ]
            
            viewer_results.append(result_list)
        
        logger.info(f"Transformed {len(viewer_results)} results for viewer (format: 8-element list)")
        return viewer_results
    
    def _display_snapshot_results_with_viewer(self, viewer_results, comparison_metadata):
        """
        Display snapshot comparison results using enhanced results_viewer
        
        Args:
            viewer_results: List of results in viewer format (8-element lists)
            comparison_metadata: Dict with snapshot URLs and component data
        """
        try:
            # Extract metadata
            snap1_url = comparison_metadata['snap1_url']
            snap2_url = comparison_metadata['snap2_url']
            snap1_components = comparison_metadata['snap1_components']
            snap2_components = comparison_metadata['snap2_components']
            
            # Create display names for snapshots
            snap1_name = f"Snapshot 1: {snap1_url[:16]}..."
            snap2_name = f"Snapshot 2: {snap2_url[:16]}..."
            
            # Create component name mappings (like file dictionaries for offline mode)
            files1 = {}  # {component_name: component_uuid}
            files2 = {}  # {component_name: component_uuid}
            
            for comp in snap1_components:
                comp_name = comp.get('name', 'Unknown')
                files1[comp_name] = comp.get('uuid', '')
            
            for comp in snap2_components:
                comp_name = comp.get('name', 'Unknown')
                files2[comp_name] = comp.get('uuid', '')
            
            # Create report paths (metadata only, snapshots don't have files)
            report_paths = {
                'csv': 'snapshot_comparison.csv',
                'output_dir': 'Snapshot Comparison Results',
                'excel': 'snapshot_comparison.xlsx'
            }
            
            # Log transformation details
            logger.info(f"Displaying {len(viewer_results)} snapshots results in viewer")
            if viewer_results:
                logger.info(f"Sample result: {viewer_results[0]} (type: {type(viewer_results[0])})")
                logger.info(f"Result length: {len(viewer_results[0]) if viewer_results else 'N/A'}")
            
            logger.info(f"Files1 count: {len(files1)}, Files2 count: {len(files2)}")
            logger.info(f"snap1_name: {snap1_name}, snap2_name: {snap2_name}")
            
            # Show results using enhanced viewer
            show_results_dialog(
                self.root,
                viewer_results,
                snap1_name,
                snap2_name,
                snap1_url,
                snap2_url,
                files1,
                files2,
                report_paths
            )
            
            logger.info("✓ Snapshot comparison results displayed in enhanced viewer")
            
        except Exception as e:
            logger.error(f"Error displaying snapshot results in viewer: {e}", exc_info=True)
            # Fallback to simple display
            messagebox.showerror(
                "Error",
                f"Error displaying results in enhanced viewer:\n\n{str(e)[:200]}"
            )
    
    def _display_snapshot_results(self, comparison_results):
        """Display snapshot comparison results"""
        # Create popup window for results
        result_window = tk.Toplevel(self.root)
        result_window.title("📊 Snapshot Comparison Results")
        result_window.geometry("900x600")
        
        # Header
        header = tk.Frame(result_window, bg='#003366')
        header.pack(fill=tk.X)
        tk.Label(
            header,
            text="📊 Snapshot Comparison Results",
            font=('Segoe UI', 12, 'bold'),
            bg='#003366',
            fg='white'
        ).pack(pady=10)
        
        # Statistics
        modified = sum(1 for r in comparison_results if r['status'] == 'Modified')
        added = sum(1 for r in comparison_results if 'Added' in r['status'])
        removed = sum(1 for r in comparison_results if 'Removed' in r['status'])
        unchanged = sum(1 for r in comparison_results if r['status'] == 'Unchanged')
        
        stats_frame = tk.Frame(result_window, bg='#EAF3FB')
        stats_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(stats_frame, text=f"✏️ Modified: {modified}", bg='#EAF3FB', fg='#f39c12').pack(side=tk.LEFT, padx=10)
        tk.Label(stats_frame, text=f"➕ Added: {added}", bg='#EAF3FB', fg='#27ae60').pack(side=tk.LEFT, padx=10)
        tk.Label(stats_frame, text=f"➖ Removed: {removed}", bg='#EAF3FB', fg='#e74c3c').pack(side=tk.LEFT, padx=10)
        tk.Label(stats_frame, text=f"✓ Unchanged: {unchanged}", bg='#EAF3FB', fg='#95a5a6').pack(side=tk.LEFT, padx=10)
        
        # Tree view
        tree_frame = tk.Frame(result_window)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        tree = ttk.Treeview(tree_frame, columns=('status', 'snapshot1', 'snapshot2'), show='tree headings', height=20)
        tree.pack(fill=tk.BOTH, expand=True)
        
        # Configure columns
        tree.column('#0', width=400, heading='Component Name')
        tree.column('status', width=150, heading='Status')
        tree.column('snapshot1', width=150, heading='Snapshot 1')
        tree.column('snapshot2', width=150, heading='Snapshot 2')
        
        # Configure tags for colors
        tree.tag_configure('modified', foreground='#f39c12')
        tree.tag_configure('added', foreground='#27ae60')
        tree.tag_configure('removed', foreground='#e74c3c')
        tree.tag_configure('unchanged', foreground='#95a5a6')
        
        # Populate tree
        for result in sorted(comparison_results, key=lambda r: (r['status'], r['name'])):
            comp_name = result['name']
            status = result['status']
            snap1 = result.get('snapshot1', {})
            snap2 = result.get('snapshot2', {})
            snap1_uuid = snap1.get('uuid', 'N/A')[:8] if snap1 else 'N/A'
            snap2_uuid = snap2.get('uuid', 'N/A')[:8] if snap2 else 'N/A'
            
            tag = status.lower().replace(' ', '_')
            tree.insert('', 'end', text=comp_name, values=(status, snap1_uuid, snap2_uuid), tags=(tag,))
        
        # Close button
        button_frame = tk.Frame(result_window, bg='#EAF3FB')
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Button(
            button_frame,
            text="Close",
            bg='#003366',
            fg='white',
            command=result_window.destroy
        ).pack()

    
    def run_folder_comparison(self, folder1, folder2):
        """Run folder comparison in background thread"""
        # Reset progress
        self.progress_bar['value'] = 0
        self.progress_label.config(text="Starting comparison...")
        self.root.update()
        
        # Disable compare button during processing
        self.compare_btn.config(state='disabled')
        
        # Progress callback
        def update_progress(current, total, message):
            percentage = int((current / total) * 100) if total > 0 else 0
            self.progress_bar['value'] = percentage
            self.progress_label.config(text=message)
            self.root.update_idletasks()
        
        # RTC info (if enabled)
        rtc_info = None
        if self.rtc_enabled_var.get():
            rtc_info = {
                'enabled': True,
                'username': None,  # TODO: Add credential dialog
                'password': None,
                'repository_path': folder2,
                'workspace_name': None,
                'stream_name': None
            }
        
        # Run comparison in background thread
        def comparison_thread():
            try:
                result = compare_folders(
                    folder1,
                    folder2,
                    progress_callback=update_progress,
                    custom_mappings=None,  # TODO: Add file mapping dialog
                    rtc_info=rtc_info
                )
                
                # Update UI on completion (must run in main thread)
                self.root.after(0, lambda: self.on_comparison_complete(result))
                
            except Exception as e:
                error_msg = f"Comparison failed: {str(e)}"
                self.root.after(0, lambda: self.on_comparison_error(error_msg))
        
        thread = threading.Thread(target=comparison_thread, daemon=True)
        thread.start()
    
    def on_comparison_complete(self, result):
        """Handle comparison completion"""
        self.compare_btn.config(state='normal')
        
        if result.get('success'):
            # Hide progress widgets temporarily
            self.progress_bar['value'] = 100
            self.progress_label.config(
                text=f"✅ Comparison complete! Showing results..."
            )
            self.root.update()
            
            # Show interactive results dialog
            try:
                show_results_dialog(
                    self.root,
                    result['results'],
                    result['folder1_display'],
                    result['folder2_display'],
                    result['folder1'],
                    result['folder2'],
                    result['files1'],
                    result['files2'],
                    result['report_paths']
                )
            except Exception as e:
                messagebox.showerror("Error", f"Error showing results: {str(e)}")
            
            # Clean up temp directories from ZIP extraction
            if result.get('temp_dirs'):
                cleanup_temp_dirs(result['temp_dirs'])
            
            # Show final success message
            output_dir = result['report_paths']['output_dir']
            total_files = len(result['results'])
            
            self.progress_label.config(
                text=f"✅ Done! {total_files} files compared. Reports saved to:\n{output_dir}"
            )
        else:
            error = result.get('error', 'Unknown error')
            messagebox.showerror("Comparison Failed", f"Error: {error}")
            self.progress_label.config(text=f"❌ Failed: {error}")
    
    def on_comparison_error(self, error_msg):
        """Handle comparison error"""
        self.compare_btn.config(state='normal')
        self.progress_label.config(text=f"❌ Error occurred")
        messagebox.showerror("Error", error_msg)
    
    def run(self):
        """Run the GUI application"""
        self.root.mainloop()


def launch_gui():
    """Launch the Migration Analysis Tool GUI"""
    app = MigrationAnalysisGUI()
    app.run()
