"""Main window for the Migration Analysis Tool GUI"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import threading
import json
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.utils.comparison_engine import compare_folders, cleanup_temp_dirs
from src.utils.credential_manager import CredentialManager
from src.gui.results_viewer import show_results_dialog
from src.rtc.connection import RTCConnection, get_rtc_connection
from src.config import settings

# Configure logging — write INFO+ to both console and a rotating log file
_log_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "rtc_comparison.log")
_file_handler = logging.FileHandler(_log_file, mode='w', encoding='utf-8')
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
_console_handler = logging.StreamHandler()
_console_handler.setLevel(logging.INFO)
_console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))

_root_logger = logging.getLogger()
_root_logger.setLevel(logging.DEBUG)
# Clear any existing handlers set by basicConfig before adding ours
_root_logger.handlers.clear()
_root_logger.addHandler(_file_handler)
_root_logger.addHandler(_console_handler)

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
        self.keep_signed_in_var = tk.BooleanVar(value=False)
        self.cached_credentials_loaded = False
        self.save_credentials_on_success = False
        
        self.setup_ui()
        self._load_cached_credentials()
    
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
        title_frame.grid_columnconfigure(0, weight=1)
        title_frame.grid_columnconfigure(1, weight=2)
        title_frame.grid_columnconfigure(2, weight=1)
        
        title_label = tk.Label(
            title_frame,
            text="Migration Analysis Report Generator",
            font=("Segoe UI", 18, "bold"),
            bg="#003366",
            fg="white"
        )
        title_label.grid(row=0, column=1, padx=10, pady=10)
        
        auth_frame = tk.Frame(title_frame, bg="#003366")
        auth_frame.grid(row=0, column=2, sticky="e", padx=10, pady=8)
        
        self.auth_status_label = tk.Label(
            auth_frame,
            text="RTC: signed out",
            font=("Segoe UI", 8),
            bg="#003366",
            fg="#DDEBFF"
        )
        self.auth_status_label.pack(side=tk.LEFT, padx=(0, 8))
        
        self.logout_btn = tk.Button(
            auth_frame,
            text="Logout",
            command=self.on_logout,
            font=("Segoe UI", 9, "bold"),
            bg="#666666",
            fg="white",
            padx=10,
            pady=4,
            state="disabled"
        )
        self.logout_btn.pack(side=tk.LEFT)
    
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
        
        # Main comparison button
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
        self.compare_btn.pack(side="left", padx=10)
        
        # Platform Dependency Analysis button
        self.platform_dep_btn = tk.Button(
            button_frame,
            text="🔍 Platform Dependency\n     Analysis",
            bg="#0066CC",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            width=18,
            height=2,
            command=self.open_platform_dependency_analysis
        )
        self.platform_dep_btn.pack(side="left", padx=10)
    
    def open_platform_dependency_analysis(self):
        """Open Platform Dependency Analysis tool for single folder analysis"""
        from src.gui.platform_dependency_viewer import PlatformDependencyViewer
        PlatformDependencyViewer(self.root)
    
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
        dialog.geometry("480x360")
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
        password_entry.pack(fill=tk.X, pady=(0, 10))
        
        keep_signed_in_check = tk.Checkbutton(
            main_frame,
            text="Keep me signed in",
            variable=self.keep_signed_in_var,
            font=('Segoe UI', 10),
            bg='white',
            activebackground='white'
        )
        keep_signed_in_check.pack(anchor=tk.W, pady=(0, 6))
        
        cache_note = "Credentials are stored in Windows Credential Manager or encrypted local storage."
        tk.Label(
            main_frame,
            text=cache_note,
            font=('Segoe UI', 8),
            bg='white',
            fg='#666666',
            wraplength=420,
            justify=tk.LEFT
        ).pack(anchor=tk.W, pady=(0, 8))
        
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
        
        tk.Button(
            button_frame,
            text="Clear Cache",
            command=lambda: self.on_logout(show_message=True),
            font=('Segoe UI', 10, 'bold'),
            bg='#B00020',
            fg='white',
            padx=20,
            pady=8
        ).pack(side=tk.LEFT, padx=5)
        
        if self.rtc_username.get():
            password_entry.focus()
        else:
            username_entry.focus()
        dialog.bind('<Return>', lambda e: on_ok())
        dialog.bind('<Escape>', lambda e: on_cancel())
    
    def _load_cached_credentials(self):
        """Load cached RTC credentials for online-online comparisons."""
        server_url = self.rtc_server_url.get()
        cached_credentials = CredentialManager.load_credentials(server_url)
        
        if cached_credentials:
            username, password = cached_credentials
            self.rtc_username.set(username)
            self.rtc_password.set(password)
            self.keep_signed_in_var.set(True)
            self.cached_credentials_loaded = True
            logger.info("Cached RTC credentials loaded for online-online mode")
        else:
            self.cached_credentials_loaded = False
        
        self._refresh_auth_status()
    
    def _refresh_auth_status(self):
        """Refresh the main window RTC auth display."""
        if not hasattr(self, 'auth_status_label') or not hasattr(self, 'logout_btn'):
            return
        
        if self.rtc_username.get() and self.rtc_password.get():
            username = self.rtc_username.get()
            label_text = f"RTC: {username}"
            self.auth_status_label.config(text=label_text)
            self.logout_btn.config(state="normal", bg="#B00020")
        else:
            self.auth_status_label.config(text="RTC: signed out")
            self.logout_btn.config(state="disabled", bg="#666666")
    
    def _update_cached_credentials_after_login(self, username, password, server_url):
        """Persist or clear RTC credentials based on the login checkbox."""
        # CRITICAL FIX: Always check current checkbox value at time of credential save
        # This ensures credentials are saved even if start_snapshot_comparison wasn't called yet
        should_save = self.keep_signed_in_var.get()
        
        if should_save:
            saved = CredentialManager.save_credentials(username, password, server_url)
            if saved:
                self.cached_credentials_loaded = True
                logger.info("✓ RTC credentials cached after successful login")
            else:
                self.cached_credentials_loaded = False
                logger.warning("✗ Failed to save credentials securely")
                self.root.after(
                    0,
                    lambda: messagebox.showwarning(
                        "Credential Cache Warning",
                        "Login succeeded, but credentials could not be saved securely.\n\n" +
                        "Possible causes:\n" +
                        "• keyring library not installed (pip install keyring)\n" +
                        "• cryptography library not installed (pip install cryptography)\n" +
                        "• File permission issues\n\n" +
                        "You will need to re-enter credentials on next login."
                    )
                )
        else:
            # User unchecked "Keep me signed in" - clear any existing cached credentials
            CredentialManager.clear_credentials(server_url)
            self.cached_credentials_loaded = False
            logger.info("Credentials not saved (Keep me signed in unchecked)")
        
        self.root.after(0, self._refresh_auth_status)
    
    def on_logout(self, show_message=True):
        """Clear online RTC login state and cached credentials."""
        server_url = self.rtc_server_url.get()
        CredentialManager.clear_credentials(server_url)
        self.rtc_username.set("")
        self.rtc_password.set("")
        self.keep_signed_in_var.set(False)
        self.cached_credentials_loaded = False
        self.rtc_connection = None
        self._refresh_auth_status()
        
        if show_message:
            messagebox.showinfo(
                "Logged Out",
                "RTC credentials have been cleared from this session and local secure storage."
            )
    
    def start_snapshot_comparison(self, url1, url2):
        """Start RTC snapshot comparison in background thread"""
        # Disable button during processing
        self.save_credentials_on_success = self.keep_signed_in_var.get()
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
            
            self._update_cached_credentials_after_login(username, password, server_url)
            
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
            
            # Fetch snapshots sequentially: Snapshot 1 first, then Snapshot 2.
            # Fetching in parallel caused Snapshot 1 to time out because Snapshot 2
            # immediately spawns 20 workers for its 422 baseline detail requests,
            # saturating the server before Snapshot 1's initial request completes.
            self.root.after(0, lambda: self._update_progress(20, "⬇️ Fetching Snapshot 1 components..."))
            logger.info("Fetching Snapshot 1 and Snapshot 2 components sequentially...")

            fetched_components = {}
            snapshot_fetches = {
                "Snapshot 1": uuid1,
                "Snapshot 2": uuid2
            }

            # Progress tracking for both snapshots
            import threading
            progress_lock = threading.Lock()
            snapshot_progress = {
                "Snapshot 1": {"current": 0, "total": 0, "message": "Starting..."},
                "Snapshot 2": {"current": 0, "total": 0, "message": "Starting..."}
            }
            
            def create_progress_callback(snap_name):
                """Create a progress callback for a specific snapshot"""
                def callback(current, total, message):
                    with progress_lock:
                        snapshot_progress[snap_name] = {
                            "current": current,
                            "total": total,
                            "message": message
                        }
                        # Calculate overall progress
                        snap1_prog = snapshot_progress["Snapshot 1"]
                        snap2_prog = snapshot_progress["Snapshot 2"]
                        
                        # Calculate percentage for each snapshot
                        snap1_pct = (snap1_prog["current"] / snap1_prog["total"] * 100) if snap1_prog["total"] > 0 else 0
                        snap2_pct = (snap2_prog["current"] / snap2_prog["total"] * 100) if snap2_prog["total"] > 0 else 0
                        
                        # Overall progress (20-50 range for fetching)
                        overall_pct = 20 + ((snap1_pct + snap2_pct) / 2) * 0.3  # 30% of progress bar for fetching
                        
                        # Create combined status message
                        status_msg = f"⬇️ Snap1: {snap1_prog['current']}/{snap1_prog['total']} | Snap2: {snap2_prog['current']}/{snap2_prog['total']}"
                        
                        # Update GUI from main thread
                        self.root.after(0, lambda p=overall_pct, m=status_msg: self._update_progress(p, m))
                return callback

            with ThreadPoolExecutor(max_workers=2) as executor:
                future_to_name = {
                    executor.submit(
                        rtc_conn.fetch_snapshot_components,
                        snapshot_uuid,
                        snapshot_name=snapshot_name,
                        progress_callback=create_progress_callback(snapshot_name)
                    ): snapshot_name
                    for snapshot_name, snapshot_uuid in snapshot_fetches.items()
                }

                for future in as_completed(future_to_name):
                    snapshot_name = future_to_name[future]
                    try:
                        result = future.result()
                        # Handle dict return format with name and components
                        if isinstance(result, dict):
                            components = result.get('components', [])
                            snap_name = result.get('name')
                        else:
                            # Fallback for old format
                            components = result if isinstance(result, list) else []
                            snap_name = None
                    except Exception as fetch_err:
                        logger.error(f"{snapshot_name}: fetch failed: {fetch_err}", exc_info=True)
                        components = []
                        snap_name = None

                    fetched_components[snapshot_name] = {
                        'components': components,
                        'name': snap_name
                    }
                    completed = len(fetched_components)
                    progress = 20 + (completed * 15)
                    self.root.after(
                        0,
                        lambda name=snapshot_name, count=len(components), value=progress:
                            self._update_progress(value, f"✓ {name}: fetched {count} components")
                    )

            snap1_components = fetched_components.get("Snapshot 1", {}).get('components', [])
            snap2_components = fetched_components.get("Snapshot 2", {}).get('components', [])
            snap1_actual_name = fetched_components.get("Snapshot 1", {}).get('name')
            snap2_actual_name = fetched_components.get("Snapshot 2", {}).get('name')

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
            
            # ===== COMPONENT SELECTION (Online Mode Specific) =====
            # Show component selection dialog to user (from main thread!)
            self.root.after(0, lambda: self._update_progress(60, "📋 Opening component selection dialog..."))
            logger.info("Showing component selection dialog for online mode...")
            
            from src.gui.dialogs import show_component_selection_dialog
            import threading
            
            # Use a threading event to coordinate dialog display
            dialog_event = threading.Event()
            selection_result = {'canceled': True, 'selected': []}
            
            def show_dialog_in_main_thread():
                nonlocal selection_result
                try:
                    selection_result = show_component_selection_dialog(snap1_components, snap2_components)
                    logger.info(f"Component selection result: {len(selection_result.get('selected', []))} components selected")
                except Exception as e:
                    logger.error(f"Error showing component selection dialog: {e}", exc_info=True)
                    selection_result = {'canceled': True, 'selected': []}
                finally:
                    dialog_event.set()  # Signal that dialog is done
            
            # Schedule dialog from main thread to ensure proper display
            self.root.after(0, show_dialog_in_main_thread)
            
            # Wait for dialog to complete (with timeout)
            if not dialog_event.wait(timeout=300):  # 5 minute timeout
                logger.warning("Component selection dialog timed out")
                self.root.after(0, lambda: messagebox.showwarning('Timeout', 'Component selection timed out.'))
                self.root.after(0, lambda: self.compare_btn.config(state='normal'))
                self.root.after(0, lambda: self._update_progress(0, "Ready"))
                return
            
            if selection_result['canceled']:
                logger.info("⚠️ User canceled component selection")
                self.root.after(0, lambda: messagebox.showinfo('Cancelled', 'Component selection cancelled. Comparison aborted.'))
                self.root.after(0, lambda: self.compare_btn.config(state='normal'))
                self.root.after(0, lambda: self._update_progress(0, "Ready"))
                return
            
            selected_comp_names = set(selection_result['selected'])
            component_mappings  = selection_result.get('component_mappings', {})  # {snap1_name: snap2_name}
            logger.info(f"✓ User selected {len(selected_comp_names)}/{len(selection_result['common'])} common components")
            if component_mappings:
                logger.info(f"✓ User mapped {len(component_mappings)} cross-snapshot component pair(s):")
                for s1n, s2n in component_mappings.items():
                    logger.info(f"    {s1n}  ↔  {s2n}")
            
            # Filter components to only selected ones
            if not selected_comp_names and not component_mappings:
                logger.info("No components selected. Comparison aborted.")
                self.root.after(0, lambda: messagebox.showwarning(
                    'No Components Selected',
                    'Please select at least one common component to compare or map at least one pair.'
                ))
                self.root.after(0, lambda: self.compare_btn.config(state='normal'))
                self.root.after(0, lambda: self._update_progress(0, "Ready"))
                return

            snap1_filtered = [c for c in snap1_components if c.get('name', str(c)) in selected_comp_names]
            snap2_filtered = [c for c in snap2_components if c.get('name', str(c)) in selected_comp_names]

            # ── Inject mapped pairs ────────────────────────────────────────
            # For each (snap1_name → snap2_name) user mapping, add the snap1 component
            # as-is, and add a renamed copy of the snap2 component so that
            # compare_snapshots pairs them by name naturally.
            if component_mappings:
                snap1_by_name = {c.get('name', str(c)): c for c in snap1_components}
                snap2_by_name = {c.get('name', str(c)): c for c in snap2_components}
                for s1_name, s2_name in component_mappings.items():
                    s1_comp = snap1_by_name.get(s1_name)
                    s2_comp = snap2_by_name.get(s2_name)
                    if s1_comp and s2_comp:
                        snap1_filtered.append(s1_comp)
                        # Rename the snap2 component so compare_snapshots pairs it with s1_name
                        renamed_s2 = dict(s2_comp)
                        renamed_s2['name'] = s1_name
                        renamed_s2['_original_name'] = s2_name   # preserved for reference
                        snap2_filtered.append(renamed_s2)
                        logger.info(f"  Injected mapped pair: {s1_name!r} (Snap1) ↔ {s2_name!r} (Snap2)")
                    else:
                        logger.warning(f"  Skipping mapped pair {s1_name!r}/{s2_name!r}: component not found")

            logger.info(f"Filtered: {len(snap1_filtered)} from Snapshot 1, {len(snap2_filtered)} from Snapshot 2")
            logger.info(f"Excluded: {len(selection_result['only_in_snap1'])} only in Snap1, "
                        f"{len(selection_result['only_in_snap2'])} only in Snap2, "
                        f"{len(component_mappings)} cross-mapped pair(s)")
            
            # Compare snapshots (only selected components) with progress tracking
            self.root.after(0, lambda: self._update_progress(70, f"🔍 Comparing {len(snap1_filtered)} selected components..."))
            logger.info(f"Comparing {len(snap1_filtered)} vs {len(snap2_filtered)} selected components (PARALLEL MODE)...")
            
            # Create progress callback for component comparison
            def comparison_progress_callback(current, total, message):
                # Calculate progress percentage (70-90% range for comparison phase)
                progress_pct = 70 + int((current / total) * 20)
                self.root.after(0, lambda p=progress_pct, m=message: self._update_progress(p, m))
            
            comparison_results = rtc_conn.compare_snapshots(
                snap1_filtered, 
                snap2_filtered, 
                progress_callback=comparison_progress_callback
            )
            
            # Calculate statistics
            different = sum(1 for r in comparison_results if r['status'] == 'Different')
            identical = sum(1 for r in comparison_results if r['status'] == 'Identical')
            added     = sum(1 for r in comparison_results if 'Added'   in r['status'])
            removed   = sum(1 for r in comparison_results if 'Removed' in r['status'])

            logger.info(f"Comparison results:")
            logger.info(f"  Different: {different}")
            logger.info(f"  Identical: {identical}")
            logger.info(f"  Added:     {added}")
            logger.info(f"  Removed:   {removed}")
            logger.info(f"  Total:     {len(comparison_results)}")
            
            # ── Fetch file content for inline HTML diffs ─────────────────────────
            # Strategy (per file):
            #   1. scm get file <baseline_uuid> -b -f <full_repo_path> -o <out>
            #      — mirrors results_viewer._get_baseline_file which is proven to work.
            #      Uses full_path from fi['path'] (e.g. 'src/foo.c'), NOT the
            #      filename-only key used in 'details' (e.g. 'foo.c').
            #   2. scm get file <item_id> <state_id> <out>
            #      — if item-id/state-id are populated in the folder structure.
            self.root.after(0, lambda: self._update_progress(88, "📥 Fetching modified file content for diffs..."))
            logger.info("Fetching file content for modified files...")

            from src.rtc.connection import RTCConnection as _RTCConn

            _BINARY_EXTS = {
                '.xls', '.xlsx', '.zip', '.exe', '.dll', '.so', '.a', '.o',
                '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.pdf', '.doc', '.docx',
                '.ppt', '.pptx', '.bin', '.lib', '.obj', '.jar', '.class', '.pyc',
            }
            MAX_FILES_PER_COMP   = 200
            MAX_TOTAL_FETCH_JOBS = 1000
            TOTAL_BUDGET_SECS    = 900

            # Each task: (cname, fpath_key, full_path, item_id, state_id, baseline_uuid, snap_key)
            #   fpath_key   — key in details dict (just filename in flat SCM structure)
            #   full_path   — fi['path'] = full repo path (e.g. 'src/comp/foo.c')
            #   item_id     — from fi['uuid'] if populated
            #   state_id    — from fi['state-id'] if populated
            #   baseline_uuid — comp's baseline_uuid (for -b -f form)
            fetch_tasks = []
            for comp in comparison_results:
                if comp.get('status') != 'Different':
                    continue
                if len(fetch_tasks) >= MAX_TOTAL_FETCH_JOBS:
                    break

                cname  = comp.get('name', '')
                b1uuid = comp.get('baseline1_uuid', '')
                b2uuid = comp.get('baseline2_uuid', '')
                fcmp   = comp.get('file_comparison') or {}
                details = fcmp.get('details', {})

                struct1 = comp.get('folder_structure1') or {}
                struct2 = comp.get('folder_structure2') or {}
                files1_map = _RTCConn._get_all_files_from_structure(struct1)
                files2_map = _RTCConn._get_all_files_from_structure(struct2)

                comp_jobs = 0
                for fpath_key, fstatus in sorted(details.items()):
                    if fstatus not in ('modified', 'added', 'removed'):
                        continue
                    if os.path.splitext(fpath_key.lower())[1] in _BINARY_EXTS:
                        continue
                    if comp_jobs >= MAX_FILES_PER_COMP:
                        break
                    if len(fetch_tasks) >= MAX_TOTAL_FETCH_JOBS:
                        break

                    if fstatus in ('modified', 'removed') and b1uuid:
                        fi1 = files1_map.get(fpath_key, {})
                        full_path1 = fi1.get('path', fpath_key)   # full repo path
                        iid1 = fi1.get('uuid', '')
                        sid1 = fi1.get('state-id', '')
                        fetch_tasks.append((cname, fpath_key, full_path1, iid1, sid1, b1uuid, 'snap1'))

                    if fstatus in ('modified', 'added') and b2uuid:
                        fi2 = files2_map.get(fpath_key, {})
                        full_path2 = fi2.get('path', fpath_key)
                        iid2 = fi2.get('uuid', '')
                        sid2 = fi2.get('state-id', '')
                        fetch_tasks.append((cname, fpath_key, full_path2, iid2, sid2, b2uuid, 'snap2'))

                    comp_jobs += 1

            logger.info(f"Prepared {len(fetch_tasks)} file-content fetch tasks")
            if fetch_tasks:
                sample = fetch_tasks[0]
                logger.info(
                    f"Sample task: cname={sample[0]!r} key={sample[1]!r} "
                    f"full_path={sample[2]!r} item_id={sample[3]!r} "
                    f"state_id={sample[4]!r} baseline={sample[5]!r} snap={sample[6]!r}"
                )
            else:
                for comp in comparison_results:
                    if comp.get('status') == 'Different':
                        struct1 = comp.get('folder_structure1') or {}
                        fi_map = _RTCConn._get_all_files_from_structure(struct1)
                        if fi_map:
                            k = next(iter(fi_map))
                            logger.info(
                                f"Zero tasks — sample fi from {comp.get('name')!r}/{k!r}: {fi_map[k]}"
                            )
                        else:
                            logger.info(f"Zero tasks — folder_structure1 empty for {comp.get('name')!r}")
                        break

            file_contents_by_component = {}

            if fetch_tasks:
                def _fetch_one(task):
                    cname, fpath_key, full_path, item_id, state_id, baseline_uuid, snap_key = task
                    # Strategy 1: baseline UUID + full repo path (proven form)
                    content = rtc_conn.fetch_file_content_from_baseline(
                        baseline_uuid, full_path, cname)
                    # Strategy 2: item-id + state-id (if available and strategy 1 failed)
                    if content is None and item_id and state_id:
                        content = rtc_conn.fetch_file_content_by_item_state(
                            item_id, state_id, fpath_key)
                    return (cname, fpath_key, snap_key, content)

                import time as _time
                deadline = _time.time() + TOTAL_BUDGET_SECS

                with ThreadPoolExecutor(max_workers=10) as fetch_ex:
                    futures = {fetch_ex.submit(_fetch_one, t): t for t in fetch_tasks}
                    for fut in as_completed(futures):
                        if _time.time() > deadline:
                            logger.warning("File content fetch budget exceeded — stopping early")
                            break
                        try:
                            cname, fpath_key, snap_key, content = fut.result(timeout=90)
                            if content is not None:
                                file_contents_by_component.setdefault(
                                    cname, {}).setdefault(fpath_key, {})[snap_key] = content
                        except Exception as _fe:
                            logger.debug(f"Content fetch error: {_fe}")

                fetched_files = sum(len(v) for v in file_contents_by_component.values())
                logger.info(
                    f"✓ File content fetched for {fetched_files} files "
                    f"in {len(file_contents_by_component)} components"
                )

            # ── Fetch baseline info (name, comment, author, timestamp) ──────────
            # Used for the Changeset section in per-component HTML reports.
            self.root.after(0, lambda: self._update_progress(89, "📋 Fetching baseline/changeset metadata..."))
            logger.info("Fetching baseline metadata and changeset info for Different components...")

            baseline_info_cache = {}  # {baseline_uuid: {name, comment, author, timestamp}}
            changeset_by_component = {}  # {comp_name: {'baseline1': info, 'baseline2': info, 'changesets': []}}

            def _fetch_baseline_meta(bid):
                if bid in baseline_info_cache:
                    return baseline_info_cache[bid]
                info = rtc_conn.fetch_baseline_info(bid)
                baseline_info_cache[bid] = info
                return info

            for comp in comparison_results:
                if comp.get('status') != 'Different':
                    continue
                cname  = comp.get('name', '')
                b1uuid = comp.get('baseline1_uuid', '')
                b2uuid = comp.get('baseline2_uuid', '')

                b1info = _fetch_baseline_meta(b1uuid) if b1uuid and b1uuid != 'N/A' else {}
                b2info = _fetch_baseline_meta(b2uuid) if b2uuid and b2uuid != 'N/A' else {}

                # Fetch changeset list from baseline2 (the newer one) via SCM CLI
                changesets = rtc_conn.fetch_baseline_changesets_scm(b2uuid, cname) if b2uuid and b2uuid != 'N/A' else []

                changeset_by_component[cname] = {
                    'baseline1': b1info,
                    'baseline2': b2info,
                    'changesets': changesets,
                }
                # If this component was compared via a cross-name mapping, record
                # the original Snapshot 2 component name for display in the report.
                if cname in component_mappings:
                    changeset_by_component[cname]['mapped_snap2_name'] = component_mappings[cname]

            logger.info(
                f"✓ Baseline metadata fetched for {len(changeset_by_component)} components"
            )

            # Prepare results for viewer
            self.root.after(0, lambda: self._update_progress(90, "📊 Preparing results viewer..."))
            
            # Enable changeset fetching for modified components
            # IMPORTANT: Changeset fetching requires LSCM/SCM CLI to be installed and configured
            # Set to True to fetch changeset information (adds comprehensive change tracking to reports)
            # Set to False for faster comparisons without changeset details
            enable_changesets = True  # ENABLED: Fetch changeset information for modified files
            
            # Transform snapshot results into results_viewer format (with changeset fetching)
            if enable_changesets:
                logger.info("Changeset fetching ENABLED - fetching changesets for modified files...")
                self.root.after(0, lambda: self._update_progress(87, "🔍 Fetching changesets..."))
            else:
                logger.info("Changeset fetching DISABLED for faster performance")
            viewer_results = self._transform_snapshot_results_for_viewer(
                comparison_results,
                rtc_conn=rtc_conn,
                enable_changesets=enable_changesets
            )
            
            # Create timestamped output directory for this comparison run
            from datetime import datetime as _dt
            timestamp = _dt.now().strftime("%Y%m%d_%H%M%S")
            base_results_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "Snapshot_Comparison_Results"
            )
            output_dir = os.path.join(base_results_dir, f"selected_components_{timestamp}")
            os.makedirs(output_dir, exist_ok=True)
            logger.info(f"Created output directory: {output_dir}")

            # Store comparison metadata for viewer
            comparison_metadata = {
                'snap1_url': url1,
                'snap2_url': url2,
                'snap1_name': snap1_actual_name,  # Actual snapshot name from API
                'snap2_name': snap2_actual_name,  # Actual snapshot name from API
                'snap1_components': snap1_filtered,
                'snap2_components': snap2_filtered,
                'selected_components': sorted(selected_comp_names),
                'total_common_components': len(selection_result['common']),
                'comparison_results': comparison_results,
                'file_contents_by_component': file_contents_by_component,
                'changeset_by_component': changeset_by_component,
                'rtc_server_url': server_url,
                'output_dir': output_dir,
            }
            
            # Display results using enhanced viewer
            self.root.after(0, lambda: self._display_snapshot_results_with_viewer(
                viewer_results, comparison_metadata
            ))
            
            self.root.after(0, lambda: self._update_progress(
                100,
                f"✅ Comparison complete: {len(comparison_results)} components analyzed "
                f"({different} different, {identical} identical, {added} added, {removed} removed)"
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
    
    def _generate_file_diffs_for_comparison(self, comparison_results, rtc_conn, output_dir):
        """
        Generate HTML diffs for modified files in component comparisons (OPTIMIZED)
        
        Args:
            comparison_results: List of component comparison results
            rtc_conn: RTCConnection instance
            output_dir: Directory to save diff HTML files
        """
        try:
            import tempfile
            from concurrent.futures import ThreadPoolExecutor, as_completed
            
            total_diffs = 0
            total_files_to_diff = 0
            max_diffs_per_component = 50  # Process up to 50 files per component
            max_file_size_kb = 500  # Skip files larger than 500KB for diff (still compare)
            max_workers = 10  # Parallel diff generation
            
            # Create diffs subdirectory
            diffs_dir = os.path.join(output_dir, "file_diffs")
            os.makedirs(diffs_dir, exist_ok=True)
            logger.info(f"Created diffs directory: {diffs_dir}")
            
            # Count modified components
            modified_components = [r for r in comparison_results if r.get('file_comparison')]
            logger.info(f"Found {len(modified_components)} components with file comparison data")
            
            if not modified_components:
                logger.warning("No components have file comparison data - cannot generate diffs")
                return
            
            # Collect all file diff tasks
            all_tasks = []
            component_task_mapping = {}
            
            for comp_result in comparison_results:
                comp_name = comp_result.get('name', 'Unknown')
                file_comparison = comp_result.get('file_comparison')
                
                if not file_comparison:
                    continue
                
                modified_files = file_comparison.get('modified', [])
                if not modified_files:
                    continue
                
                logger.info(f"{comp_name}: Found {len(modified_files)} modified files")
                total_files_to_diff += len(modified_files)
                
                # Limit files to diff
                files_to_diff = modified_files[:max_diffs_per_component]
                if len(modified_files) > max_diffs_per_component:
                    logger.warning(f"{comp_name}: Limiting to {max_diffs_per_component} of {len(modified_files)} modified files")
                
                comp_result['file_diffs'] = []
                component_task_mapping[comp_name] = comp_result
                
                baseline1_uuid = comp_result.get('baseline1_uuid')
                baseline2_uuid = comp_result.get('baseline2_uuid')
                
                if not baseline1_uuid or not baseline2_uuid:
                    logger.warning(f"{comp_name}: Missing baseline UUIDs")
                    continue
                
                # Create tasks for parallel processing
                for file_path in files_to_diff:
                    all_tasks.append({
                        'comp_name': comp_name,
                        'file_path': file_path,
                        'baseline1_uuid': baseline1_uuid,
                        'baseline2_uuid': baseline2_uuid,
                        'comp_result': comp_result
                    })
            
            if not all_tasks:
                logger.warning("No files to generate diffs for")
                return
            
            logger.info(f"Starting parallel diff generation for {len(all_tasks)} files (workers={max_workers})...")
            
            def generate_single_diff(task):
                """Generate diff for a single file (runs in thread pool)"""
                comp_name = task['comp_name']
                file_path = task['file_path']
                baseline1_uuid = task['baseline1_uuid']
                baseline2_uuid = task['baseline2_uuid']
                
                try:
                    # Download both versions
                    content1 = rtc_conn.fetch_file_content_from_baseline(baseline1_uuid, file_path, comp_name)
                    if content1 is None:
                        return {'success': False, 'reason': 'download1_failed'}
                    
                    content2 = rtc_conn.fetch_file_content_from_baseline(baseline2_uuid, file_path, comp_name)
                    if content2 is None:
                        return {'success': False, 'reason': 'download2_failed'}
                    
                    # Check file size (skip very large files for HTML diff)
                    size1_kb = len(content1) / 1024
                    size2_kb = len(content2) / 1024
                    max_size = max(size1_kb, size2_kb)
                    
                    if max_size > max_file_size_kb:
                        logger.info(f"{comp_name}: Skipping HTML diff for {file_path} (size: {max_size:.1f}KB > {max_file_size_kb}KB)")
                        return {'success': False, 'reason': 'too_large', 'size': max_size}
                    
                    # Generate diff in memory (no temp files)
                    import difflib
                    lines1 = content1.splitlines(keepends=True)
                    lines2 = content2.splitlines(keepends=True)
                    
                    differ = difflib.HtmlDiff(wrapcolumn=120)
                    html_diff = differ.make_file(
                        lines1, lines2,
                        fromdesc=f"Baseline 1: {file_path}",
                        todesc=f"Baseline 2: {file_path}"
                    )
                    
                    # Count differences for summary
                    added_count = html_diff.count('class="diff_add"')
                    deleted_count = html_diff.count('class="diff_sub"')
                    changed_count = html_diff.count('class="diff_chg"')
                    total_diffs = added_count + deleted_count + changed_count
                    
                    # Add navigation summary at top of HTML
                    summary_html = f'''
<div style="background-color: #e8f4f8; border: 2px solid #1976d2; padding: 20px; margin: 20px; border-radius: 8px; font-family: Arial, sans-serif;">
    <h2 style="margin-top: 0; color: #1976d2;">📊 File Comparison Summary</h2>
    <p><strong>File:</strong> {file_path}</p>
    <p><strong>Component:</strong> {comp_name}</p>
    <table style="margin-top: 15px; border-collapse: collapse;">
        <tr>
            <td style="padding: 8px; background-color: palegreen; border: 1px solid #ccc;"><strong>Added Lines:</strong></td>
            <td style="padding: 8px; border: 1px solid #ccc;">{added_count}</td>
        </tr>
        <tr>
            <td style="padding: 8px; background-color: #ffaaaa; border: 1px solid #ccc;"><strong>Deleted Lines:</strong></td>
            <td style="padding: 8px; border: 1px solid #ccc;">{deleted_count}</td>
        </tr>
        <tr>
            <td style="padding: 8px; background-color: #ffff77; border: 1px solid #ccc;"><strong>Changed Lines:</strong></td>
            <td style="padding: 8px; border: 1px solid #ccc;">{changed_count}</td>
        </tr>
        <tr style="font-weight: bold; background-color: #f0f0f0;">
            <td style="padding: 8px; border: 1px solid #ccc;"><strong>Total Differences:</strong></td>
            <td style="padding: 8px; border: 1px solid #ccc;">{total_diffs}</td>
        </tr>
    </table>
    <p style="margin-top: 15px; font-size: 14px; color: #666;">
        💡 <strong>Tip:</strong> Click the "f" or "t" links in the first column to jump to the next difference.
        Differences are highlighted in <span style="background-color: palegreen; padding: 2px 4px;">green</span> (added),
        <span style="background-color: #ffaaaa; padding: 2px 4px;">red</span> (deleted), or
        <span style="background-color: #ffff77; padding: 2px 4px;">yellow</span> (changed).
    </p>
    {f'<p style="margin-top: 10px; padding: 10px; background-color: #fff3cd; border-left: 4px solid #ffc107;"><strong>⚠️ Warning:</strong> Files are identical - no differences found. The metadata may have changed but content is the same.</p>' if total_diffs == 0 else ''}
</div>
'''
                    
                    # Insert summary after <body> tag
                    html_diff = html_diff.replace('<body>', '<body>' + summary_html, 1)
                    
                    # Write to output
                    safe_filename = file_path.replace('/', '_').replace('\\', '_').replace(':', '_')
                    diff_path = os.path.join(diffs_dir, f"{safe_filename}_diff.html")
                    
                    with open(diff_path, 'w', encoding='utf-8') as f:
                        f.write(html_diff)
                    
                    logger.debug(f"{comp_name}: ✓ Generated diff for {file_path} ({total_diffs} differences)")
                    
                    return {
                        'success': True,
                        'comp_name': comp_name,
                        'file_path': file_path,
                        'diff_path': diff_path,
                        'size': max_size,
                        'diff_count': total_diffs
                    }
                    
                except Exception as e:
                    logger.warning(f"{comp_name}: ✗ Error generating diff for {file_path}: {e}", exc_info=True)
                    return {'success': False, 'comp_name': comp_name, 'file_path': file_path, 'reason': str(e)[:100]}
            
            # Process diffs in parallel
            completed_count = 0
            success_count = 0
            failed_count = 0
            failed_details = []  # Track failures for debugging
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_task = {executor.submit(generate_single_diff, task): task for task in all_tasks}
                
                for future in as_completed(future_to_task):
                    completed_count += 1
                    result = future.result()
                    
                    # Update progress every 5 files
                    if completed_count % 5 == 0 or completed_count == len(all_tasks):
                        progress_pct = 75 + (completed_count / len(all_tasks)) * 10  # 75-85% range
                        self.root.after(
                            0,
                            lambda p=progress_pct, c=completed_count, t=len(all_tasks):
                                self._update_progress(p, f"📄 Generating diffs: {c}/{t} files")
                        )
                    
                    if result['success']:
                        success_count += 1
                        comp_name = result['comp_name']
                        comp_result = component_task_mapping[comp_name]
                        
                        relative_diff_path = os.path.relpath(result['diff_path'], output_dir)
                        comp_result['file_diffs'].append({
                            'file_path': result['file_path'],
                            'diff_html': relative_diff_path.replace('\\', '/'),
                            'diff_html_abs': result['diff_path']
                        })
                    else:
                        failed_count += 1
                        # Track failure details for logging
                        comp_name = result.get('comp_name', 'Unknown')
                        file_path = result.get('file_path', 'Unknown')
                        reason = result.get('reason', 'Unknown')
                        failed_details.append(f"{comp_name}: {file_path} ({reason})")
            
            logger.info("=" * 80)
            logger.info(f"✓ FILE DIFF GENERATION COMPLETE (PARALLEL):")
            logger.info(f"  Total files processed: {len(all_tasks)}")
            logger.info(f"  Successfully generated diffs: {success_count}")
            logger.info(f"  Failed: {failed_count}")
            logger.info(f"  Diffs saved to: {diffs_dir}")
            
            if failed_count > 0 and failed_details:
                logger.warning(f"Failed diffs (showing first 10):")
                for detail in failed_details[:10]:
                    logger.warning(f"  - {detail}")
                if len(failed_details) > 10:
                    logger.warning(f"  ... and {len(failed_details) - 10} more")
            
            logger.info("=" * 80)
            
        except Exception as e:
            logger.error(f"Error generating file diffs: {e}", exc_info=True)

    def _transform_snapshot_results_for_viewer(self, comparison_results, rtc_conn=None, enable_changesets=False):
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
        
        Args:
            comparison_results: Results from compare_snapshots
            rtc_conn: RTCConnection object (optional, for changeset fetching)
            enable_changesets: Whether to fetch changeset information (default: False for performance)
        """
        viewer_results = []
        changeset_stats = {'total_modified': 0, 'changesets_found': 0, 'changesets_failed': 0}
        
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
            # _compare_one_component already uses 'Identical' and 'Different' directly.
            if status == 'Added in Snapshot 2':
                status_type = 'Only in Snapshot 2'
            elif status == 'Removed in Snapshot 2':
                status_type = 'Only in Snapshot 1'
            else:
                status_type = status  # 'Identical' or 'Different' passed through unchanged
            
            # Generate purpose/description based on status
            if status == 'Different':
                # Show file change details in purpose
                file_comparison = result.get('file_comparison', {})
                if file_comparison:
                    # file_comparison values are ints (counts) from compare_folder_structures
                    added_count = file_comparison.get('added', 0)
                    modified_count = file_comparison.get('modified', 0)
                    removed_count = file_comparison.get('removed', 0)
                    purpose = f"Component baseline changed: {baseline1_uuid[:12]}... → {baseline2_uuid[:12]}... " \
                             f"(+{added_count} added, ~{modified_count} modified, -{removed_count} removed)"
                else:
                    purpose = f"Component baseline changed: {baseline1_uuid[:12]}... → {baseline2_uuid[:12]}..."
            elif status == 'Identical' or status == 'Unchanged':
                purpose = f"Component baseline unchanged: {baseline1_uuid[:12]}..."
            elif status == 'Added in Snapshot 2':
                purpose = f"Component added in snapshot 2: {baseline2_uuid[:12]}..."
            elif status == 'Removed in Snapshot 2':
                purpose = f"Component removed from snapshot 2 (was: {baseline1_uuid[:12]}...)"
            else:
                purpose = "Component comparison"
            
            # Check if file-level diffs were generated
            file_diffs = result.get('file_diffs', [])
            if file_diffs and len(file_diffs) > 0:
                # Use first diff file as the html_link
                html_link = file_diffs[0].get('diff_html', 'N/A')
            else:
                html_link = "Component-level (no file diff)"
            
            # Fetch changeset information if enabled and component was modified
            changeset_info = ""
            if enable_changesets and rtc_conn and status == 'Different':
                changeset_stats['total_modified'] += 1
                try:
                    # Get file comparison data
                    file_comparison = result.get('file_comparison', {})
                    if file_comparison:
                        # Get modified file paths from details dict (values are ints, not lists)
                        modified_files = [
                            fp for fp, ct in file_comparison.get('details', {}).items()
                            if ct == 'modified'
                        ][:5]
                        if modified_files:
                            logger.info(f"📋 {comp_name}: Fetching changesets for {len(modified_files)} modified files...")
                            changeset_map = rtc_conn.fetch_changesets_for_files(
                                modified_files,
                                baseline2_uuid,  # Use baseline2 (newer version)
                                comp_name
                            )
                            
                            if changeset_map:
                                # Summarize changeset info
                                changeset_count = len(changeset_map)
                                first_file = list(changeset_map.keys())[0]
                                first_cs = changeset_map[first_file]
                                changeset_uuid = first_cs.get('uuid', 'N/A')[:10]
                                changeset_info = f"Changeset: {changeset_uuid}... ({changeset_count} file(s))"
                                changeset_stats['changesets_found'] += 1
                                logger.info(f"   ✓ {comp_name}: Found changesets for {changeset_count} files - {changeset_info}")
                            elif not settings.LSCM_PATH:
                                changeset_info = "LSCM not configured - Install RTC SCM CLI for changeset details"
                                changeset_stats['changesets_failed'] += 1
                                logger.warning(f"   ⚠ {comp_name}: LSCM not available")
                            elif changeset_map is not None and len(changeset_map) == 0:
                                changeset_info = "No changesets found (LSCM may not be configured correctly)"
                                changeset_stats['changesets_failed'] += 1
                                logger.warning(f"   ⚠ {comp_name}: No changesets found")
                            else:
                                changeset_info = "Changeset fetch failed"
                                changeset_stats['changesets_failed'] += 1
                        else:
                            logger.debug(f"{comp_name}: No modified files to fetch changesets for")
                            changeset_info = "No modified files"
                    else:
                        logger.debug(f"{comp_name}: No file comparison data available")
                        changeset_info = "No file comparison data"
                except Exception as e:
                    logger.warning(f"{comp_name}: Failed to fetch changesets: {e}", exc_info=True)
                    changeset_info = f"Changeset fetch error: {str(e)[:50]}"
                    changeset_stats['changesets_failed'] += 1
            
            # Create result list matching offline format
            result_list = [
                comp_name,                              # index[0]: component name
                metric1,                                # index[1]: metric1 (baseline1 uuid length)
                metric2,                                # index[2]: metric2 (baseline2 uuid length)
                line_status,                            # index[3]: line_status
                status_type,                            # index[4]: status
                html_link,                              # index[5]: html_link (first file diff or component-level)
                purpose,                                # index[6]: purpose with baseline info
                changeset_info                          # index[7]: changeset_info (fetched if enabled)
            ]
            
            viewer_results.append(result_list)
        
        # Log changeset fetching statistics
        if enable_changesets:
            logger.info("=" * 80)
            logger.info("CHANGESET FETCHING SUMMARY:")
            logger.info(f"  Total modified components: {changeset_stats['total_modified']}")
            logger.info(f"  Components with changesets found: {changeset_stats['changesets_found']}")
            logger.info(f"  Components with no changesets: {changeset_stats['changesets_failed']}")
            if changeset_stats['changesets_found'] > 0:
                success_rate = (changeset_stats['changesets_found'] / changeset_stats['total_modified']) * 100 if changeset_stats['total_modified'] > 0 else 0
                logger.info(f"  Success rate: {success_rate:.1f}%")
            logger.info("=" * 80)
        
        logger.info(f"Transformed {len(viewer_results)} results for viewer (format: 8-element list)")
        return viewer_results
    
    def _export_snapshot_results_to_reports(self, viewer_results, csv_path, excel_path, snap1_name, snap2_name, comparison_results=None):
        """
        Export snapshot comparison results to CSV and Excel files with file-level details
        
        Args:
            viewer_results: List of 8-element result lists from viewer format
            csv_path: Path to save CSV file
            excel_path: Path to save Excel file
            snap1_name: Display name for snapshot 1
            snap2_name: Display name for snapshot 2
            comparison_results: Original comparison results with file diff info
        """
        try:
            import csv
            
            # Calculate summary statistics
            total_components = len(viewer_results)
            modified_count = sum(1 for r in viewer_results if r[4] == 'Different')
            unchanged_count = sum(1 for r in viewer_results if r[4] == 'Identical')
            added_count = sum(1 for r in viewer_results if 'Snapshot 2' in r[4])
            removed_count = sum(1 for r in viewer_results if 'Snapshot 1' in r[4])
            
            # Count file-level changes
            total_files_modified = 0
            total_files_added = 0
            total_files_removed = 0
            total_files_unchanged = 0
            
            if comparison_results:
                for comp in comparison_results:
                    file_comp = comp.get('file_comparison', {})
                    if file_comp:
                        # file_comparison values are ints (counts) from compare_folder_structures
                        total_files_modified += file_comp.get('modified', 0) if isinstance(file_comp.get('modified'), int) else len(file_comp.get('details', {}))
                        total_files_added += file_comp.get('added', 0) if isinstance(file_comp.get('added'), int) else 0
                        total_files_removed += file_comp.get('removed', 0) if isinstance(file_comp.get('removed'), int) else 0
                        total_files_unchanged += file_comp.get('unchanged', 0) if isinstance(file_comp.get('unchanged'), int) else 0
            
            # Write MAIN CSV report (component-level)
            logger.info(f"Exporting snapshot comparison to CSV: {csv_path}")
            with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                
                # Write summary section
                writer.writerow(["SNAPSHOT COMPARISON SUMMARY"])
                writer.writerow(["Snapshot 1", snap1_name])
                writer.writerow(["Snapshot 2", snap2_name])
                writer.writerow(["Date", datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
                writer.writerow([])
                
                writer.writerow(["COMPONENT-LEVEL STATISTICS"])
                writer.writerow(["Total Components", total_components])
                writer.writerow(["Modified Components", modified_count])
                writer.writerow(["Unchanged Components", unchanged_count])
                writer.writerow(["Added Components", added_count])
                writer.writerow(["Removed Components", removed_count])
                writer.writerow([])
                
                if comparison_results:
                    writer.writerow(["FILE-LEVEL STATISTICS"])
                    writer.writerow(["Total Modified Files", total_files_modified])
                    writer.writerow(["Total Added Files", total_files_added])
                    writer.writerow(["Total Removed Files", total_files_removed])
                    writer.writerow(["Total Unchanged Files", total_files_unchanged])
                    writer.writerow([])
                
                # Write component headers
                writer.writerow(["COMPONENT-LEVEL DETAILS"])
                writer.writerow([
                    "Component Name",
                    f"Snapshot 1 Metric ({snap1_name})",
                    f"Snapshot 2 Metric ({snap2_name})",
                    "Baseline Comparison",
                    "Status",
                    "Details",
                    "Type",
                    "Changeset Info"  # Column 8: Changeset information
                ])
                # Write data rows
                for row in viewer_results:
                    try:
                        writer.writerow([str(cell) if cell else '' for cell in row])
                    except Exception as row_err:
                        logger.warning(f"Error writing row: {row_err}")
            
            logger.info(f"✓ CSV report exported: {csv_path}")
            
            # Write FILE-LEVEL CSV report
            if comparison_results:
                file_csv_path = csv_path.replace('.csv', '_FileDetails.csv')
                logger.info(f"Exporting file-level details to CSV: {file_csv_path}")
                
                with open(file_csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow([
                        "Component Name",
                        "File Path",
                        "Change Type",
                        "HTML Diff Link"
                    ])
                    
                    for comp in comparison_results:
                        comp_name = comp.get('name', 'Unknown')
                        file_comp = comp.get('file_comparison', {})
                        file_diffs = comp.get('file_diffs', [])
                        
                        # Create lookup for diff links
                        diff_lookup = {fd['file_path']: fd['diff_html'] for fd in file_diffs}
                        
                        if file_comp:
                            # Use details dict: {file_path: 'modified'|'added'|'removed'|'unchanged'}
                            details = file_comp.get('details', {})
                            for file_path, change_type in sorted(details.items()):
                                if change_type == 'modified':
                                    diff_link = diff_lookup.get(file_path, 'N/A')
                                    writer.writerow([comp_name, file_path, 'Modified', diff_link])
                                elif change_type == 'added':
                                    writer.writerow([comp_name, file_path, 'Added', 'N/A'])
                                elif change_type == 'removed':
                                    writer.writerow([comp_name, file_path, 'Removed', 'N/A'])
                
                logger.info(f"✓ File-level CSV exported: {file_csv_path}")
            
            # Write HTML summary report
            html_path = csv_path.replace('.csv', '.html')
            logger.info(f"Exporting snapshot comparison to HTML: {html_path}")
            try:
                self._generate_snapshot_html_report(viewer_results, html_path, snap1_name, snap2_name, comparison_results)
                logger.info(f"✓ HTML report exported: {html_path}")
            except Exception as html_err:
                logger.error(f"Error generating HTML report: {html_err}")
            
            # Write Excel report with MULTIPLE SHEETS
            logger.info(f"Exporting snapshot comparison to Excel: {excel_path}")
            try:
                from openpyxl import Workbook
                from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
                
                wb = Workbook()
                
                # Remove default sheet
                if 'Sheet' in wb.sheetnames:
                    del wb['Sheet']
                
                # ========== SHEET 1: SUMMARY ==========
                ws_summary = wb.create_sheet("Summary", 0)
                
                # Title
                title_font = Font(bold=True, size=16, color="FFFFFF")
                title_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
                
                ws_summary['A1'] = "SNAPSHOT COMPARISON SUMMARY"
                ws_summary['A1'].font = title_font
                ws_summary['A1'].fill = title_fill
                ws_summary.merge_cells('A1:B1')
                
                # Snapshot info
                ws_summary['A3'] = "Snapshot 1:"
                ws_summary['B3'] = snap1_name
                ws_summary['A4'] = "Snapshot 2:"
                ws_summary['B4'] = snap2_name
                ws_summary['A5'] = "Comparison Date:"
                ws_summary['B5'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                # Component statistics
                ws_summary['A7'] = "COMPONENT-LEVEL STATISTICS"
                ws_summary['A7'].font = Font(bold=True, size=12)
                ws_summary['A8'] = "Total Components"
                ws_summary['B8'] = total_components
                ws_summary['A9'] = "Modified Components"
                ws_summary['B9'] = modified_count
                ws_summary['A10'] = "Unchanged Components"
                ws_summary['B10'] = unchanged_count
                ws_summary['A11'] = "Added Components"
                ws_summary['B11'] = added_count
                ws_summary['A12'] = "Removed Components"
                ws_summary['B12'] = removed_count
                
                # File statistics
                if comparison_results:
                    ws_summary['A14'] = "FILE-LEVEL STATISTICS"
                    ws_summary['A14'].font = Font(bold=True, size=12)
                    ws_summary['A15'] = "Total Modified Files"
                    ws_summary['B15'] = total_files_modified
                    ws_summary['A16'] = "Total Added Files"
                    ws_summary['B16'] = total_files_added
                    ws_summary['A17'] = "Total Removed Files"
                    ws_summary['B17'] = total_files_removed
                    ws_summary['A18'] = "Total Unchanged Files"
                    ws_summary['B18'] = total_files_unchanged
                
                # Column widths
                ws_summary.column_dimensions['A'].width = 30
                ws_summary.column_dimensions['B'].width = 50
                
                # ========== SHEET 2: COMPONENT DETAILS ==========
                ws_components = wb.create_sheet("Component Details", 1)
                
                # Headers
                headers = [
                    "Component Name",
                    f"Snapshot 1 Metric",
                    f"Snapshot 2 Metric",
                    "Baseline Comparison",
                    "Status",
                    "Details",
                    "Type",
                    "Changeset Info"  # Column 8: Changeset information
                ]
                
                header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
                header_font = Font(bold=True, color="FFFFFF")
                
                for col_idx, header in enumerate(headers, 1):
                    cell = ws_components.cell(row=1, column=col_idx, value=header)
                    cell.fill = header_fill
                    cell.font = header_font
                    cell.alignment = Alignment(horizontal='center', vertical='center')
                
                # Data rows
                for row_idx, row in enumerate(viewer_results, 2):
                    for col_idx, cell_value in enumerate(row, 1):
                        cell = ws_components.cell(row=row_idx, column=col_idx, value=str(cell_value) if cell_value else '')
                        cell.alignment = Alignment(horizontal='left', vertical='top', wrap_text=True)
                        
                        # Color code by status
                        if col_idx == 5:  # Status column
                            if cell_value == 'Different':
                                cell.fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
                            elif cell_value == 'Identical':
                                cell.fill = PatternFill(start_color="D4EDDA", end_color="D4EDDA", fill_type="solid")
                
                # Auto-adjust column widths
                for col_idx in range(1, len(headers) + 1):
                    ws_components.column_dimensions[chr(64 + col_idx)].width = 25
                
                # ========== SHEET 3: FILE-LEVEL DETAILS ==========
                if comparison_results:
                    ws_files = wb.create_sheet("File Details", 2)
                    
                    # Headers
                    file_headers = ["Component Name", "File Path", "Change Type", "HTML Diff Link"]
                    for col_idx, header in enumerate(file_headers, 1):
                        cell = ws_files.cell(row=1, column=col_idx, value=header)
                        cell.fill = header_fill
                        cell.font = header_font
                        cell.alignment = Alignment(horizontal='center', vertical='center')
                    
                    # Data rows
                    file_row = 2
                    for comp in comparison_results:
                        comp_name = comp.get('name', 'Unknown')
                        file_comp = comp.get('file_comparison', {})
                        file_diffs = comp.get('file_diffs', [])
                        
                        # Create lookup for diff links
                        diff_lookup = {fd['file_path']: fd['diff_html'] for fd in file_diffs}
                        
                        if file_comp:
                            # Use details dict: {file_path: 'modified'|'added'|'removed'|'unchanged'}
                            details = file_comp.get('details', {})
                            fill_map = {
                                'modified': PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid"),
                                'added':    PatternFill(start_color="D4EDDA", end_color="D4EDDA", fill_type="solid"),
                                'removed':  PatternFill(start_color="F8D7DA", end_color="F8D7DA", fill_type="solid"),
                            }
                            label_map = {'modified': 'Modified', 'added': 'Added', 'removed': 'Removed'}
                            for file_path, change_type in sorted(details.items()):
                                if change_type not in label_map:
                                    continue
                                diff_link = diff_lookup.get(file_path, 'N/A') if change_type == 'modified' else 'N/A'
                                ws_files.cell(row=file_row, column=1, value=comp_name)
                                ws_files.cell(row=file_row, column=2, value=file_path)
                                cell_type = ws_files.cell(row=file_row, column=3, value=label_map[change_type])
                                cell_type.fill = fill_map[change_type]
                                ws_files.cell(row=file_row, column=4, value=diff_link)
                                file_row += 1
                    
                    # Column widths
                    ws_files.column_dimensions['A'].width = 30
                    ws_files.column_dimensions['B'].width = 50
                    ws_files.column_dimensions['C'].width = 15
                    ws_files.column_dimensions['D'].width = 60
                    
                    logger.info(f"Added {file_row - 2} file-level entries to Excel")                
                
                wb.save(excel_path)
                logger.info(f"✓ Excel report exported with {len(wb.sheetnames)} sheets: {excel_path}")
            
            except ImportError:
                logger.warning("openpyxl not installed - skipping Excel export")
            except Exception as excel_err:
                logger.error(f"Error generating Excel report: {excel_err}")
        
        except Exception as e:
            logger.error(f"Error exporting snapshot results: {e}", exc_info=True)
    
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
            snap1_actual_name = comparison_metadata.get('snap1_name')
            snap2_actual_name = comparison_metadata.get('snap2_name')
            snap1_components = comparison_metadata['snap1_components']
            snap2_components = comparison_metadata['snap2_components']
            selected_components = comparison_metadata.get('selected_components', [])
            total_common_components = comparison_metadata.get('total_common_components', len(selected_components))
            output_dir = comparison_metadata.get('output_dir')  # Get output_dir from metadata
            
            # Create display names for snapshots - use actual names if available
            if snap1_actual_name:
                snap1_name = snap1_actual_name
            else:
                snap1_name = f"Snapshot 1: {snap1_url[:50]}..."
            
            if snap2_actual_name:
                snap2_name = snap2_actual_name
            else:
                snap2_name = f"Snapshot 2: {snap2_url[:50]}..."
            
            # Create component name mappings (like file dictionaries for offline mode)
            files1 = {}  # {component_name: component_uuid}
            files2 = {}  # {component_name: component_uuid}
            
            for comp in snap1_components:
                comp_name = comp.get('name', 'Unknown')
                files1[comp_name] = comp.get('uuid', '')
            
            for comp in snap2_components:
                comp_name = comp.get('name', 'Unknown')
                files2[comp_name] = comp.get('uuid', '')
            
            # Use the output directory already created during comparison
            # (output_dir was created earlier in run_snapshot_comparison_analysis)
            
            # Create report paths with absolute paths (consistent with offline mode)
            csv_report = os.path.join(output_dir, "Selected_Snapshot_Comparison.csv")
            excel_report = os.path.join(output_dir, "Selected_Snapshot_Comparison.xlsx")
            html_report = os.path.join(output_dir, "Selected_Snapshot_Comparison.html")
            
            report_paths = {
                'csv': csv_report,
                'output_dir': output_dir,
                'excel': excel_report,
                'html': html_report,
                'online_context': {
                    'mode': 'online_online',
                    'server_url': self.rtc_server_url.get(),
                    'username': self.rtc_username.get(),
                    'password': self.rtc_password.get(),
                    'snapshot1_components': snap1_components,
                    'snapshot2_components': snap2_components,
                    'selected_components': selected_components,
                }
            }
            
            logger.info(f"✓ Created output directory: {output_dir}")

            manifest_path = os.path.join(output_dir, "selected_components.txt")
            with open(manifest_path, 'w', encoding='utf-8') as manifest:
                manifest.write("Selected Online-Online Snapshot Components\n")
                manifest.write(f"Snapshot 1: {snap1_name}\n")
                manifest.write(f"Snapshot 2: {snap2_name}\n")
                manifest.write(f"Selected: {len(selected_components)} of {total_common_components} common components\n\n")
                for component_name in selected_components:
                    manifest.write(f"{component_name}\n")
            logger.info(f"✓ Selected component manifest exported: {manifest_path}")
            
            # Export snapshot comparison results to CSV, Excel, and HTML
            comparison_results = comparison_metadata.get('comparison_results', [])
            self._export_snapshot_results_to_reports(
                viewer_results, 
                csv_report, 
                excel_report,
                snap1_name,
                snap2_name,
                comparison_results  # Pass comparison results for file diff links
            )

            # ── Generate per-component HTML diff reports ─────────────────────
            # For every "Different" component, write a self-contained HTML report
            # and store its absolute path in viewer_results[idx][5] so the
            # results-viewer "View Diff" button can open it.
            try:
                from src.utils.diff_utils import generate_snapshot_component_html
                full_comparison_results = comparison_metadata.get('comparison_results', [])
                html_dir = os.path.join(output_dir, "html_diffs")
                os.makedirs(html_dir, exist_ok=True)

                # Pre-fetched file contents and RTC server URL (from comparison thread)
                file_contents_by_comp = comparison_metadata.get('file_contents_by_component', {})
                rtc_srv_url           = comparison_metadata.get('rtc_server_url', '')

                # Build a quick lookup: component_name → viewer_results index
                name_to_idx = {vr[0]: i for i, vr in enumerate(viewer_results)}

                for comp_result in full_comparison_results:
                    if comp_result.get('status') != 'Different':
                        continue
                    cname  = comp_result['name']
                    b1uuid = comp_result.get('baseline1_uuid', '')
                    b2uuid = comp_result.get('baseline2_uuid', '')
                    fcmp   = comp_result.get('file_comparison')

                    # Per-component changeset metadata passed into HTML generator
                    csdata = comparison_metadata.get('changeset_by_component', {}).get(cname, {})

                    html_path = generate_snapshot_component_html(
                        component_name=cname,
                        baseline1_uuid=b1uuid,
                        baseline2_uuid=b2uuid,
                        file_comparison=fcmp,
                        output_dir=html_dir,
                        snap1_label=snap1_name,
                        snap2_label=snap2_name,
                        file_contents=file_contents_by_comp.get(cname),
                        changeset_data=csdata,
                        server_url=rtc_srv_url,
                    )
                    if html_path and cname in name_to_idx:
                        viewer_results[name_to_idx[cname]][5] = html_path

                logger.info(
                    f"✓ HTML diff reports generated for "
                    f"{sum(1 for vr in viewer_results if vr[5] not in ['N/A', '', None])} "
                    f"Different components in: {html_dir}"
                )
            except Exception as html_err:
                logger.warning(f"HTML diff generation failed (non-fatal): {html_err}")
            
            # Log transformation details
            logger.info(f"Displaying {len(viewer_results)} snapshots results in viewer")
            if viewer_results:
                logger.info(f"Sample result: {viewer_results[0]} (type: {type(viewer_results[0])})")
                logger.info(f"Result length: {len(viewer_results[0]) if viewer_results else 'N/A'}")
            
            logger.info(f"Files1 count: {len(files1)}, Files2 count: {len(files2)}")
            logger.info(f"snap1_name: {snap1_name}, snap2_name: {snap2_name}")
            logger.info(f"Selected components exported: {len(selected_components)}/{total_common_components}")
            
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
    
    def _generate_snapshot_html_report(self, viewer_results, html_path, snap1_name, snap2_name, comparison_results=None):
        """Generate HTML summary report for snapshot comparison"""
        try:
            from datetime import datetime
            
            # Count statistics
            modified = sum(1 for r in viewer_results if r[4] == 'Different')
            added = sum(1 for r in viewer_results if 'Only in Snapshot 2' in r[4])
            removed = sum(1 for r in viewer_results if 'Only in Snapshot 1' in r[4])
            unchanged = sum(1 for r in viewer_results if r[4] == 'Identical')
            
            # Create a mapping from component name to comparison result for file diff links
            comp_results_map = {}
            if comparison_results:
                comp_results_map = {r['name']: r for r in comparison_results}
            
            html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Snapshot Comparison Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
        .header {{ background-color: #003366; color: white; padding: 20px; border-radius: 5px; }}
        .header h1 {{ margin: 0; }}
        .header p {{ margin: 5px 0; opacity: 0.9; }}
        .summary {{ background-color: white; padding: 20px; margin: 20px 0; border-radius: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .stats {{ display: flex; gap: 20px; margin: 20px 0; }}
        .stat-box {{ flex: 1; padding: 15px; border-radius: 5px; text-align: center; }}
        .stat-box h3 {{ margin: 0 0 10px 0; font-size: 32px; }}
        .stat-box p {{ margin: 0; color: #666; }}
        .modified {{ background-color: #fff3cd; border-left: 4px solid #ffc107; }}
        .added {{ background-color: #d4edda; border-left: 4px solid #28a745; }}
        .removed {{ background-color: #f8d7da; border-left: 4px solid #dc3545; }}
        .unchanged {{ background-color: #d1ecf1; border-left: 4px solid #17a2b8; }}
        table {{ width: 100%; border-collapse: collapse; background-color: white; border-radius: 5px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        th {{ background-color: #003366; color: white; padding: 12px; text-align: left; font-weight: bold; }}
        td {{ padding: 10px; border-bottom: 1px solid #ddd; }}
        tr:hover {{ background-color: #f8f9fa; }}
        .status-Different {{ color: #ffc107; font-weight: bold; }}
        .status-Identical {{ color: #17a2b8; }}
        .status-added {{ color: #28a745; font-weight: bold; }}
        .status-removed {{ color: #dc3545; font-weight: bold; }}
        .file-diffs {{ margin-top: 10px; padding: 10px; background-color: #f8f9fa; border-radius: 3px; }}
        .file-diffs-header {{ font-weight: bold; margin-bottom: 5px; color: #666; font-size: 12px; }}
        .file-diff-link {{ display: inline-block; margin: 2px 5px; padding: 2px 8px; background-color: #007bff; color: white; text-decoration: none; border-radius: 3px; font-size: 11px; }}
        .file-diff-link:hover {{ background-color: #0056b3; }}
        .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 Snapshot Comparison Report</h1>
        <p><strong>Snapshot 1:</strong> {snap1_name}</p>
        <p><strong>Snapshot 2:</strong> {snap2_name}</p>
        <p><strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
    
    <div class="summary">
        <h2>Summary</h2>
        <div class="stats">
            <div class="stat-box modified">
                <h3>{modified}</h3>
                <p>Modified Components</p>
            </div>
            <div class="stat-box added">
                <h3>{added}</h3>
                <p>Added Components</p>
            </div>
            <div class="stat-box removed">
                <h3>{removed}</h3>
                <p>Removed Components</p>
            </div>
            <div class="stat-box unchanged">
                <h3>{unchanged}</h3>
                <p>Unchanged Components</p>
            </div>
        </div>
    </div>
    
    <table>
        <thead>
            <tr>
                <th>Component Name</th>
                <th>Baseline Comparison</th>
                <th>Status</th>
                <th>Description & File Diffs</th>
            </tr>
        </thead>
        <tbody>
"""
            
            for row in viewer_results:
                comp_name = row[0]
                line_status = row[3]
                status = row[4]
                purpose = row[6]
                
                status_class = status.replace(' ', '-').replace('Snapshot', '')
                
                # Check for file diffs
                file_diffs_html = ""
                if comp_name in comp_results_map:
                    comp_result = comp_results_map[comp_name]
                    file_diffs = comp_result.get('file_diffs', [])
                    if file_diffs:
                        file_diffs_html = '<div class="file-diffs"><div class="file-diffs-header">📄 File-Level Diffs:</div>'
                        for diff_info in file_diffs:
                            file_name = os.path.basename(diff_info['file_path'])
                            diff_link = diff_info['diff_html']
                            file_diffs_html += f'<a href="{diff_link}" class="file-diff-link" target="_blank">{file_name}</a>'
                        file_diffs_html += '</div>'
                
                html_content += f"""            <tr>
                <td><strong>{comp_name}</strong></td>
                <td><code>{line_status}</code></td>
                <td class="status-{status_class}">{status}</td>
                <td>{purpose}{file_diffs_html}</td>
            </tr>
"""
            
            html_content += f"""        </tbody>
    </table>
    
    <div class="footer">
        <p>Migration Analysis Tool - Bosch Engineering</p>
        <p>Online-Online Snapshot Comparison (Component + File Level)</p>
    </div>
</body>
</html>
"""
            
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
                
        except Exception as e:
            logger.error(f"Error generating HTML report: {e}", exc_info=True)
            raise
    
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
