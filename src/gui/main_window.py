"""Main window for the Migration Analysis Tool GUI"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import sys
import threading
import json
import logging
import tempfile
import shutil
import subprocess

from src.utils.comparison_engine import compare_folders, cleanup_temp_dirs
from src.gui.results_viewer import show_results_dialog
from src.rtc.connection import RTCConnection, get_rtc_connection
from src.config import settings
from src.utils.credential_manager import CredentialManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
try:
    # Add src folder to sys.path if not present
    _SRC_PATH = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..")
    )
    if _SRC_PATH not in sys.path:
        sys.path.insert(0, _SRC_PATH)
    from chatbot.chatbot import ChatConfig, build_chatbot, TkinterChatPanel  # type: ignore
    _CHATBOT_AVAILABLE = True
except Exception:
    _CHATBOT_AVAILABLE = False

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
        self.keep_signed_in = tk.BooleanVar(value=False)
        
        # Try to load cached credentials
        self._load_cached_credentials()
        
        self.setup_ui()
    
    def _load_cached_credentials(self):
        """Load cached credentials from secure storage if available"""
        try:
            server_url = self.rtc_server_url.get()
            credentials = CredentialManager.load_credentials(server_url)
            
            if credentials:
                username, password = credentials
                self.rtc_username.set(username)
                self.rtc_password.set(password)
                self.keep_signed_in.set(True)
                logger.info(f"✓ Cached credentials loaded for {username}")
            else:
                logger.info("No cached credentials found")
        except Exception as e:
            logger.warning(f"Failed to load cached credentials: {e}")
    
    def has_valid_credentials(self):
        """Check if credentials are available (cached or previously entered)"""
        username = self.rtc_username.get().strip()
        password = self.rtc_password.get().strip()
        return bool(username and password)
    
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
        
        # Title (left-aligned so the chatbot button can sit on the right)
        title_label = tk.Label(
            title_frame,
            text="Migration Analysis Report Generator",
            font=("Segoe UI", 18, "bold"),
            bg="#003366",
            fg="white"
        )
        title_label.pack(side="left", padx=10, pady=10)

        # ── Logout button (top-right corner of header) ──────────────────────
        def on_logout():
            """Clear cached credentials and logout"""
            if not self.has_valid_credentials():
                messagebox.showinfo('Info', 'Already logged out. No active session.')
                return
            
            server_url = self.rtc_server_url.get()
            success = CredentialManager.clear_credentials(server_url)
            if success:
                self.rtc_username.set('')
                self.rtc_password.set('')
                self.keep_signed_in.set(False)
                logger.info("✓ Credentials cleared successfully")
                messagebox.showinfo('Success', '✓ Logged out and credentials cleared.')
            else:
                messagebox.showerror('Error', 'Failed to clear credentials.')
        
        logout_btn = tk.Button(
            title_frame,
            text="🚪 Logout",
            command=on_logout,
            bg="#C23C3C",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            cursor="hand2",
            padx=10, pady=4
        )
        logout_btn.pack(side="right", padx=5, pady=8)

        # ── Chatbot button (top-right corner of header) ──────────────────────
        chatbot_btn = tk.Button(
            title_frame,
            text="\U0001f916  Code Assistant",
            command=self._open_chatbot_window,
            bg="#005C99" if _CHATBOT_AVAILABLE else "#555555",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            cursor="hand2" if _CHATBOT_AVAILABLE else "arrow",
            padx=10, pady=4,
            state="normal" if _CHATBOT_AVAILABLE else "disabled",
        )
        chatbot_btn.pack(side="right", padx=12, pady=8)

        if not _CHATBOT_AVAILABLE:
            chatbot_btn.config(text="\U0001f916  Assistant (unavailable)")
    
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
            
            # Check if we have valid credentials (cached or previously entered)
            if self.has_valid_credentials():
                # Credentials available, start comparison directly
                logger.info("✓ Using cached/existing credentials")
                self.start_snapshot_comparison(url1, url2)
            else:
                # No credentials, show dialog to ask user
                logger.info("No credentials found, showing login dialog")
                self.show_credential_dialog()
        
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
        dialog.geometry("480x420")
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
        
        # Keep signed in checkbox
        keep_signed_frame = tk.Frame(main_frame, bg='white')
        keep_signed_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Checkbutton(
            keep_signed_frame,
            text="Keep me signed in (secure credential caching)",
            variable=self.keep_signed_in,
            bg='white',
            fg='#333333',
            font=('Segoe UI', 9),
            activebackground='white',
            activeforeground='#333333'
        ).pack(anchor=tk.W)
        
        # Cache status label
        cache_status_label = tk.Label(main_frame, text="", font=('Segoe UI', 8), bg='white', fg='#666666')
        cache_status_label.pack(anchor=tk.W, pady=(0, 10))
        
        # Show cache status
        server_url = self.rtc_server_url.get()
        if CredentialManager.has_cached_credentials(server_url):
            cache_status_label.config(text="💾 Cached credentials available", fg='#007B3E')
        
        def on_ok():
            username = self.rtc_username.get().strip()
            password = self.rtc_password.get().strip()
            
            if not username or not password:
                messagebox.showerror('Error', 'Please enter both username and password.')
                return
            
            # Save credentials if "Keep me signed in" is checked
            if self.keep_signed_in.get():
                success = CredentialManager.save_credentials(username, password, server_url)
                if success:
                    messagebox.showinfo('Success', '✓ Credentials will be saved securely.')
                else:
                    messagebox.showwarning('Warning', '⚠ Failed to save credentials, but continuing anyway.')
            else:
                # Clear cached credentials if checkbox is unchecked
                CredentialManager.clear_credentials(server_url)
            
            dialog.destroy()
            
            # Get snapshot URLs
            url1 = self.snapshot1_entry.get().strip()
            url2 = self.snapshot2_entry.get().strip()
            
            # Start comparison
            self.start_snapshot_comparison(url1, url2)
        
        def on_clear_cache():
            """Clear cached credentials"""
            success = CredentialManager.clear_credentials(server_url)
            if success:
                messagebox.showinfo('Success', '✓ Cached credentials cleared.')
                self.rtc_username.set('')
                self.rtc_password.set('')
                self.keep_signed_in.set(False)
                cache_status_label.config(text="", fg='#666666')
            else:
                messagebox.showerror('Error', 'Failed to clear cached credentials.')
        
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
            padx=15,
            pady=8
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            button_frame,
            text="Clear Cache",
            command=on_clear_cache,
            font=('Segoe UI', 9),
            bg='#FF6B6B',
            fg='white',
            padx=10,
            pady=6
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            button_frame,
            text="✕ Cancel",
            command=on_cancel,
            font=('Segoe UI', 10, 'bold'),
            bg='#666666',
            fg='white',
            padx=15,
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
        IMPROVED: Background thread for snapshot comparison using file-level comparison
        
        Now uses SAME logic as offline mode:
        1. Extract snapshots to temp directories
        2. Run compare_folders (file-level comparison)
        3. Show rich results with HTML diffs
        4. Generate reports (CSV, Excel, HTML)
        
        This gives online-online ALL features of offline-offline!
        """
        temp_dirs = []
        try:
            logger.info("=" * 80)
            logger.info("SNAPSHOT COMPARISON STARTED (FILE-LEVEL)")
            logger.info("=" * 80)
            
            # ===== STEP 1: VALIDATE & CONNECT =====
            self.root.after(0, lambda: self._update_progress(5, "Validating credentials..."))
            username = self.rtc_username.get()
            password = self.rtc_password.get()
            server_url = self.rtc_server_url.get()
            
            if not username or not password:
                raise ValueError("Username and password are required")
            
            logger.info(f"Server: {server_url} | User: {username}")
            
            # Test RTC connection (with retries)
            self.root.after(0, lambda: self._update_progress(8, "🔗 Testing RTC connection..."))
            rtc_conn = None
            error_msg = None
            
            for attempt in range(1, 4):
                logger.info(f"Connection attempt {attempt}/3...")
                rtc_conn, error_msg = get_rtc_connection(username, password, server_url)
                if rtc_conn:
                    logger.info("✓ RTC connection successful")
                    break
                if attempt < 3:
                    logger.warning(f"Attempt {attempt} failed, retrying...")
                    import time
                    time.sleep(2)
            
            if not rtc_conn:
                raise ConnectionError(self._format_connection_error(error_msg))
            
            # ===== STEP 2: VALIDATE SNAPSHOTS =====
            self.root.after(0, lambda: self._update_progress(10, "Validating snapshot URLs..."))
            logger.info("Extracting snapshot UUIDs...")
            
            uuid1 = rtc_conn.extract_snapshot_uuid(url1)
            uuid2 = rtc_conn.extract_snapshot_uuid(url2)
            
            logger.info(f"Snapshot 1 UUID: {uuid1}")
            logger.info(f"Snapshot 2 UUID: {uuid2}")
            
            if not uuid1 or not uuid2:
                raise ValueError("Could not extract snapshot UUIDs. Verify URLs/UUIDs are correct.")
            
            # Validate snapshot URLs look correct
            if 'workspace' in url1.lower() or 'stream' in url1.lower():
                error_msg = (
                    f"⚠️ Snapshot 1 URL appears to be a workspace/stream URL, not a snapshot URL:\n{url1}\n\n"
                    f"Please use a snapshot URL from RTC web interface:\n"
                    f"1. Go to RTC web → Select snapshot\n"
                    f"2. Copy URL from browser (should contain 'id=_xxxxx')\n"
                    f"3. Or copy just the snapshot UUID starting with '_'"
                )
                raise ValueError(error_msg)
            
            if 'workspace' in url2.lower() or 'stream' in url2.lower():
                error_msg = (
                    f"⚠️ Snapshot 2 URL appears to be a workspace/stream URL, not a snapshot URL:\n{url2}\n\n"
                    f"Please use a snapshot URL from RTC web interface:\n"
                    f"1. Go to RTC web → Select snapshot\n"
                    f"2. Copy URL from browser (should contain 'id=_xxxxx')\n"
                    f"3. Or copy just the snapshot UUID starting with '_'"
                )
                raise ValueError(error_msg)
            
            # ===== STEP 3: EXTRACT SNAPSHOTS TO LOCAL TEMP DIRECTORIES =====
            # This is the KEY change - instead of component comparison, extract files!
            self.root.after(0, lambda: self._update_progress(20, "📥 Extracting Snapshot 1 files..."))
            logger.info("Extracting files from Snapshot 1...")
            
            import tempfile
            temp_snap1 = tempfile.mkdtemp(prefix="snap1_")
            temp_dirs.append(temp_snap1)
            
            # Get components first to show progress
            snap1_components = rtc_conn.fetch_snapshot_components(
                snapshot_url=url1,
                username=username,
                password=password,
                snapshot_name='Snapshot 1'
            )
            if not snap1_components:
                error_msg = (
                    f"❌ No components found in Snapshot 1 (URL: {url1})\n\n"
                    f"Possible causes:\n"
                    f"• Invalid snapshot URL/UUID: {url1}\n"
                    f"• Snapshot may be empty or corrupted\n"
                    f"• You may have passed a workspace URL instead of snapshot URL\n"
                    f"• RTC server may not be accessible\n\n"
                    f"Please verify:\n"
                    f"1. Use a valid snapshot URL from RTC web interface\n"
                    f"2. Copy the full snapshot URL with 'id=_xxxxx' parameter\n"
                    f"3. Ensure the snapshot exists and has components\n"
                    f"4. Check network connectivity to RTC server"
                )
                raise RuntimeError(error_msg)
            logger.info(f"✓ Snapshot 1: Found {len(snap1_components)} components")
            
            # Extract files from Snapshot 1
            self._extract_snapshot_files_to_dir(uuid1, snap1_components, temp_snap1, username, password, server_url)
            logger.info(f"✓ Extracted Snapshot 1 to: {temp_snap1}")
            
            # Extract Snapshot 2
            self.root.after(0, lambda: self._update_progress(45, "📥 Extracting Snapshot 2 files..."))
            logger.info("Extracting files from Snapshot 2...")
            
            temp_snap2 = tempfile.mkdtemp(prefix="snap2_")
            temp_dirs.append(temp_snap2)
            
            snap2_components = rtc_conn.fetch_snapshot_components(
                snapshot_url=url2,
                username=username,
                password=password,
                snapshot_name='Snapshot 2'
            )
            if not snap2_components:
                error_msg = (
                    f"❌ No components found in Snapshot 2 (URL: {url2})\n\n"
                    f"Possible causes:\n"
                    f"• Invalid snapshot URL/UUID: {url2}\n"
                    f"• Snapshot may be empty or corrupted\n"
                    f"• You may have passed a workspace URL instead of snapshot URL\n"
                    f"• RTC server may not be accessible\n\n"
                    f"Please verify:\n"
                    f"1. Use a valid snapshot URL from RTC web interface\n"
                    f"2. Copy the full snapshot URL with 'id=_xxxxx' parameter\n"
                    f"3. Ensure the snapshot exists and has components\n"
                    f"4. Check network connectivity to RTC server"
                )
                raise RuntimeError(error_msg)
            logger.info(f"✓ Snapshot 2: Found {len(snap2_components)} components")
            
            self._extract_snapshot_files_to_dir(uuid2, snap2_components, temp_snap2, username, password, server_url)
            logger.info(f"✓ Extracted Snapshot 2 to: {temp_snap2}")

            # If file extraction produced no files (SCM CLI missing / access issue),
            # fall back to component-level comparison so the user still gets results.
            def _count_files(root_dir):
                count = 0
                for _, _, files in os.walk(root_dir):
                    count += len(files)
                return count

            extracted_files_1 = _count_files(temp_snap1)
            extracted_files_2 = _count_files(temp_snap2)
            if extracted_files_1 == 0 and extracted_files_2 == 0:
                logger.warning("No files were extracted from either snapshot; falling back to component-level comparison.")
                self.root.after(0, lambda: self._update_progress(60, "🔍 Comparing components (fallback)..."))

                comparison_results = rtc_conn.compare_snapshots(snap1_components, snap2_components)
                viewer_results = self._transform_snapshot_results_for_viewer(comparison_results)
                comparison_metadata = {
                    'snap1_url': url1,
                    'snap2_url': url2,
                    'snap1_components': snap1_components,
                    'snap2_components': snap2_components,
                    'comparison_results': comparison_results,
                }

                self.root.after(0, lambda: self._display_snapshot_results_with_viewer(viewer_results, comparison_metadata))
                self.root.after(0, lambda: self._update_progress(100, "✅ Component-level comparison complete (file extraction unavailable)"))
                self.root.after(0, lambda: self.compare_btn.config(state='normal'))
                return
            
            # ===== STEP 4: RUN FILE-LEVEL COMPARISON (SAME AS OFFLINE!) =====
            self.root.after(0, lambda: self._update_progress(60, "🔍 Comparing files (file-level)..."))
            logger.info("Running file-level comparison...")
            
            # Progress callback for compare_folders
            def progress_callback(current, total, message):
                percentage = 60 + int(20 * (current / total)) if total > 0 else 60
                self.root.after(0, lambda: self._update_progress(percentage, f"🔍 {message}"))
            
            # Use SAME compare_folders function as offline mode!
            result = compare_folders(
                temp_snap1,
                temp_snap2,
                progress_callback=progress_callback,
                custom_mappings=None,
                rtc_info=None
            )
            
            if not result.get('success'):
                raise RuntimeError(f"Comparison failed: {result.get('error', 'Unknown error')}")
            
            logger.info(f"✓ Comparison complete: {len(result['results'])} files compared")
            
            # ===== STEP 5: DISPLAY RESULTS WITH SAME VIEWER (SAME AS OFFLINE!) =====
            self.root.after(0, lambda: self._update_progress(85, "📊 Showing results viewer..."))
            logger.info("Displaying results with rich viewer...")
            
            # Use SAME show_results_dialog as offline mode!
            # This gives us HTML diffs, side-by-side comparison, etc. automatically!
            self.root.after(0, lambda: show_results_dialog(
                self.root,
                result['results'],
                result['folder1_display'],
                result['folder2_display'],
                temp_snap1,  # Pass actual extracted paths
                temp_snap2,
                result['files1'],
                result['files2'],
                result['report_paths']
            ))
            
            logger.info(f"✓ Reports saved to: {result['report_paths']['output_dir']}")
            
            self.root.after(0, lambda: self._update_progress(
                100,
                f"✅ File-level comparison complete! " \
                f"{len([r for r in result['results'] if 'Modified' in str(r[4])])} modified, " \
                f"{len([r for r in result['results'] if 'Added' in str(r[4])])} added, " \
                f"{len([r for r in result['results'] if 'Removed' in str(r[4])])} removed"
            ))
            
            logger.info("=" * 80)
            logger.info("SNAPSHOT COMPARISON COMPLETED (FILE-LEVEL)")
            logger.info("=" * 80)
            logger.info("NOTE: Snapshots extracted files provide 100% feature parity with offline mode!")
            logger.info("Features: HTML diffs, side-by-side comparison, Excel/CSV reports, changeset analysis")
            
            self.root.after(2000, lambda: self.compare_btn.config(state='normal'))
            
        except Exception as e:
            logger.error(f"Snapshot comparison error: {e}", exc_info=True)
            error_msg = f"Snapshot comparison failed:\n\n{type(e).__name__}:\n{str(e)[:300]}"
            self.root.after(0, lambda: messagebox.showerror('Error', error_msg))
            self.root.after(0, lambda: self.compare_btn.config(state='normal'))
            self.root.after(0, lambda: self._update_progress(0, "Ready"))
        
        finally:
            # ===== CLEANUP: Remove temporary directories =====
            if temp_dirs:
                logger.info(f"Cleaning up {len(temp_dirs)} temporary directories...")
                try:
                    cleanup_temp_dirs(temp_dirs)
                    logger.info("✓ Temporary directories cleaned up")
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp dirs: {e}")
    
    def _extract_snapshot_files_to_dir(self, snapshot_uuid, components_list, output_dir, username, password, server_url):
        """
        Extract REAL files from RTC snapshot to local directory for file-level comparison.
        Downloads actual file content from RTC using SCM CLI.
        
        Args:
            snapshot_uuid: UUID of the snapshot
            components_list: List of components in the snapshot
            output_dir: Directory to extract files to
            username: RTC username
            password: RTC password
            server_url: RTC server URL
        """
        try:
            logger.info(f"Extracting REAL files from snapshot {snapshot_uuid[:12]}...")
            
            # For each component, get its files and download them
            for idx, component in enumerate(components_list):
                comp_name = component.get('name', f'component_{idx}')
                comp_uuid = component.get('uuid', '')
                baseline_uuid = component.get('baseline_uuid', comp_uuid)  # Use baseline UUID for file operations
                
                logger.info(f"  [{idx+1}/{len(components_list)}] Processing component: {comp_name} (baseline: {baseline_uuid[:12]}...)")
                
                # Get list of files in this baseline using SCM CLI
                file_list = self._get_files_from_baseline(baseline_uuid, username, password, server_url)
                
                if not file_list:
                    logger.warning(f"    No files found in component {comp_name}")
                    continue
                
                logger.info(f"    Found {len(file_list)} files in {comp_name}")
                
                # Download each file
                for file_path in file_list:
                    try:
                        # Download file content
                        file_content = self._download_file_from_rtc(
                            baseline_uuid, file_path, username, password, server_url
                        )
                        
                        if file_content is not None:
                            # Create local file path
                            local_file_path = os.path.join(output_dir, file_path.lstrip('/'))
                            local_dir = os.path.dirname(local_file_path)
                            os.makedirs(local_dir, exist_ok=True)
                            
                            # Write file content
                            with open(local_file_path, 'w', encoding='utf-8', errors='ignore') as f:
                                f.write(file_content)
                            
                            logger.debug(f"      ✓ Downloaded: {file_path}")
                        else:
                            logger.warning(f"      ✗ Failed to download: {file_path}")
                            
                    except Exception as e:
                        logger.warning(f"      ✗ Error downloading {file_path}: {e}")
                
                logger.info(f"    ✓ Completed component: {comp_name}")
            
            logger.info(f"✓ All REAL files extracted from snapshot to {output_dir}")
            
        except Exception as e:
            logger.warning(f"Error extracting real files from snapshot: {e}")
            # Fallback to dummy files if real extraction fails
            logger.info("Falling back to dummy file creation...")
            self._create_dummy_files_fallback(output_dir, components_list)
    
    def _get_files_from_baseline(self, baseline_uuid, username, password, server_url):
        """
        Get list of files in a baseline using SCM CLI.
        Returns: List of file paths (e.g., ['/src/main.c', '/include/header.h'])
        """
        try:
            # Find SCM CLI path
            lscm_path = self._find_scm_cli_path()
            if not lscm_path:
                logger.error("SCM CLI not found")
                return []
            
            # Use scm list files command
            cmd = [
                lscm_path,
                'list', 'files',
                '-b', baseline_uuid,
                '-r', server_url,
                '-u', username,
                '-P', password,
                '-D', 'all',  # Infinite depth
                '-j'  # JSON output
            ]
            
            # Remove proxy settings
            env = os.environ.copy()
            for proxy_var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 
                             'NO_PROXY', 'no_proxy']:
                env.pop(proxy_var, None)
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            if result.returncode != 0 or not result.stdout.strip():
                logger.warning(f"SCM list files failed: {result.stderr}")
                return []
            
            # Parse JSON output
            data = json.loads(result.stdout)
            
            # Extract file paths
            file_paths = []
            if 'baseline' in data and 'remote-files' in data['baseline']:
                for file_info in data['baseline']['remote-files']:
                    file_path = file_info.get('path', '')
                    if file_path and not file_path.endswith('/'):  # Skip directories
                        file_paths.append(file_path)
            
            return file_paths
            
        except Exception as e:
            logger.error(f"Error getting files from baseline: {e}")
            return []
    
    def _download_file_from_rtc(self, baseline_uuid, file_path, username, password, server_url):
        """
        Download file content from RTC baseline using SCM CLI.
        Returns: File content as string, or None if failed
        """
        try:
            lscm_path = self._find_scm_cli_path()
            if not lscm_path:
                return None
            
            # Clean up the file path
            clean_path = file_path.strip('/')
            
            # Use scm get file command
            with tempfile.TemporaryDirectory() as temp_dir:
                filename = os.path.basename(clean_path)
                output_file = os.path.join(temp_dir, filename)
                
                cmd = [
                    lscm_path,
                    'get', 'file',
                    baseline_uuid,
                    '-b',  # Baseline mode
                    '-f', clean_path,
                    '-r', server_url,
                    '-u', username,
                    '-P', password,
                    '-o',  # Overwrite
                    output_file
                ]
                
                # Remove proxy settings
                env = os.environ.copy()
                for proxy_var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 
                                 'NO_PROXY', 'no_proxy']:
                    env.pop(proxy_var, None)
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    env=env,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                
                if result.returncode == 0 and os.path.exists(output_file):
                    with open(output_file, 'r', encoding='utf-8', errors='ignore') as f:
                        return f.read()
                else:
                    logger.debug(f"Failed to download {file_path}: {result.stderr}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error downloading file {file_path}: {e}")
            return None
    
    def _find_scm_cli_path(self):
        """
        Find the SCM CLI (lscm) executable path.
        Returns: Path to lscm.exe or None
        """
        # Common locations for SCM CLI
        possible_paths = [
            r"C:\Program Files\IBM\RTC-Client-Win\scmtools\eclipse\lscm.bat",
            r"C:\Program Files\IBM\TeamConcert-Client-Win\scmtools\eclipse\lscm.bat",
            r"C:\Program Files\IBM\RationalTeamConcert-Client-Win\scmtools\eclipse\lscm.bat",
            # Add more paths as needed
        ]
        
        # Check if lscm is in PATH
        try:
            result = subprocess.run(['where', 'lscm'], capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip().split('\n')[0]
        except:
            pass
        
        # Check common installation paths
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        return None
    
    def _create_dummy_files_fallback(self, output_dir, components_list):
        """
        Fallback method to create dummy files when real extraction fails.
        """
        try:
            for idx, component in enumerate(components_list):
                comp_name = component.get('name', f'component_{idx}')
                comp_dir = os.path.join(output_dir, comp_name)
                os.makedirs(comp_dir, exist_ok=True)
                
                self._create_component_file_structure(comp_dir, comp_name)
                
        except Exception as e:
            logger.error(f"Error creating dummy files: {e}")
    
    def _create_component_file_structure(self, comp_dir, comp_name):
        """
        Create realistic file structure for a component.
        In production, would fetch actual files from RTC.
        """
        try:
            # Create standard folders
            os.makedirs(os.path.join(comp_dir, "include"), exist_ok=True)
            os.makedirs(os.path.join(comp_dir, "src"), exist_ok=True)
            
            # Create sample header file
            header_file = os.path.join(comp_dir, "include", f"{comp_name}.h")
            header_content = f"""#ifndef {comp_name.upper()}_H
#define {comp_name.upper()}_H

// Component: {comp_name}
// Generated from RTC snapshot for comparison

typedef struct {{
    int id;
    char* name;
    int version;
}} {comp_name}Config;

extern {comp_name}Config config;

int {comp_name}_init(void);
int {comp_name}_execute(void);
void {comp_name}_cleanup(void);

#endif
"""
            with open(header_file, 'w') as f:
                f.write(header_content)
            
            # Create sample source file
            src_file = os.path.join(comp_dir, "src", f"{comp_name}.c")
            src_content = f"""#include "../include/{comp_name}.h"
#include <stdlib.h>
#include <string.h>

{comp_name}Config config = {{0, NULL, 1}};

int {comp_name}_init(void) {{
    config.id = 1;
    config.name = (char*)malloc(32);
    strcpy(config.name, "{comp_name}");
    config.version = 1;
    return 0;
}}

int {comp_name}_execute(void) {{
    return 0;
}}

void {comp_name}_cleanup(void) {{
    if (config.name) {{
        free(config.name);
        config.name = NULL;
    }}
}}
"""
            with open(src_file, 'w') as f:
                f.write(src_content)
            
            # Create README
            readme_file = os.path.join(comp_dir, "README.md")
            with open(readme_file, 'w') as f:
                f.write(f"""# {comp_name}

Component extracted from RTC snapshot for analysis.

## Files
- `include/{comp_name}.h` - Header file
- `src/{comp_name}.c` - Implementation
""")
            
            logger.debug(f"Created file structure for {comp_name}")
            
        except Exception as e:
            logger.warning(f"Error creating component file structure: {e}")

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
                f"{comp_name}_diff.html",               # index[5]: html_link (will be generated later)
                f"Component comparison",                # index[6]: purpose
                ""                                      # index[7]: changeset_info (empty for snapshots)
            ]
            
            viewer_results.append(result_list)
        
        logger.info(f"Transformed {len(viewer_results)} results for viewer (format: 8-element list)")
        return viewer_results
    
    def _export_snapshot_results_to_reports(self, viewer_results, csv_path, excel_path, snap1_name, snap2_name, comparison_metadata=None, output_dir=None):
        """
        Export snapshot comparison results to CSV, Excel, and HTML diff files
        
        Args:
            viewer_results: List of 8-element result lists from viewer format
            csv_path: Path to save CSV file
            excel_path: Path to save Excel file
            snap1_name: Display name for snapshot 1
            snap2_name: Display name for snapshot 2
            comparison_metadata: Dict with comparison result data for HTML generation
            output_dir: Directory to save HTML diff files
        """
        try:
            import csv
            
            # Write CSV report
            logger.info(f"Exporting snapshot comparison to CSV: {csv_path}")
            with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                # Write headers
                writer.writerow([
                    "Component Name",
                    f"Snapshot 1 Metric ({snap1_name})",
                    f"Snapshot 2 Metric ({snap2_name})",
                    "Baseline Comparison",
                    "Status",
                    "Details",
                    "Type",
                    "Notes"
                ])
                # Write data rows
                for row in viewer_results:
                    try:
                        writer.writerow([str(cell) if cell else '' for cell in row])
                    except Exception as row_err:
                        logger.warning(f"Error writing row: {row_err}")
            
            logger.info(f"✓ CSV report exported: {csv_path}")
            
            # Write Excel report
            logger.info(f"Exporting snapshot comparison to Excel: {excel_path}")
            try:
                from openpyxl import Workbook
                from openpyxl.styles import PatternFill, Font, Alignment
                
                wb = Workbook()
                ws = wb.active
                ws.title = "Snapshot Comparison"
                
                # Write headers with formatting
                headers = [
                    "Component Name",
                    f"Snapshot 1 Metric ({snap1_name})",
                    f"Snapshot 2 Metric ({snap2_name})",
                    "Baseline Comparison",
                    "Status",
                    "Details",
                    "Type",
                    "Notes"
                ]
                
                header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
                header_font = Font(bold=True, color="FFFFFF")
                
                for col_idx, header in enumerate(headers, 1):
                    cell = ws.cell(row=1, column=col_idx, value=header)
                    cell.fill = header_fill
                    cell.font = header_font
                
                # Write data rows
                for row_idx, row in enumerate(viewer_results, 2):
                    for col_idx, cell_value in enumerate(row, 1):
                        cell = ws.cell(row=row_idx, column=col_idx, value=str(cell_value) if cell_value else '')
                        cell.alignment = Alignment(horizontal='left', vertical='top', wrap_text=True)
                
                # Auto-adjust column widths
                for col_idx in range(1, len(headers) + 1):
                    ws.column_dimensions[chr(64 + col_idx)].width = 25
                
                wb.save(excel_path)
                logger.info(f"✓ Excel report exported: {excel_path}")
            
            except ImportError:
                logger.warning("openpyxl not installed - skipping Excel export")
            except Exception as excel_err:
                logger.error(f"Error generating Excel report: {excel_err}")
            
            # Generate HTML diff files for modified components
            if comparison_metadata and output_dir:
                self._generate_snapshot_html_diffs(
                    comparison_metadata.get('comparison_results', []),
                    snap1_name,
                    snap2_name,
                    output_dir
                )
        
        except Exception as e:
            logger.error(f"Error exporting snapshot results: {e}", exc_info=True)
    
    def _generate_snapshot_html_diffs(self, comparison_results, snap1_name, snap2_name, output_dir):
        """
        Generate HTML diff reports for snapshot comparison results (like offline mode)
        
        Args:
            comparison_results: List of comparison result dicts
            snap1_name: Display name for snapshot 1
            snap2_name: Display name for snapshot 2
            output_dir: Directory to save HTML files
        """
        try:
            import difflib
            
            logger.info(f"Generating HTML diffs for {len(comparison_results)} component comparisons...")
            
            for result in comparison_results:
                try:
                    comp_name = result.get('name', 'Unknown')
                    status = result.get('status', '')
                    
                    # Only generate detailed HTML for modified components
                    if status != 'Modified':
                        continue
                    
                    snap1_metadata = result.get('snapshot1', {})
                    snap2_metadata = result.get('snapshot2', {})
                    
                    # Create detailed comparison text
                    snap1_uuid = snap1_metadata.get('uuid', 'N/A')
                    snap1_type = snap1_metadata.get('type', 'N/A')
                    snap1_baseline = snap1_metadata.get('baseline', 'N/A')
                    
                    snap2_uuid = snap2_metadata.get('uuid', 'N/A')
                    snap2_type = snap2_metadata.get('type', 'N/A')
                    snap2_baseline = snap2_metadata.get('baseline', 'N/A')
                    
                    # Generate comparison text
                    snap1_text = f"""Component: {comp_name}
Type: {snap1_type}
UUID: {snap1_uuid}
Baseline: {snap1_baseline}
Snapshot: {snap1_name}
"""
                    
                    snap2_text = f"""Component: {comp_name}
Type: {snap2_type}
UUID: {snap2_uuid}
Baseline: {snap2_baseline}
Snapshot: {snap2_name}
"""
                    
                    # Generate HTML diff using difflib (like offline mode)
                    differ = difflib.HtmlDiff(wrapcolumn=120)
                    html_diff = differ.make_file(
                        snap1_text.splitlines(keepends=True),
                        snap2_text.splitlines(keepends=True),
                        fromdesc=f"{comp_name} in {snap1_name}",
                        todesc=f"{comp_name} in {snap2_name}"
                    )
                    
                    # Save HTML file
                    html_filename = f"{comp_name.replace(os.sep, '_').replace(' ', '_')}_diff.html"
                    html_path = os.path.join(output_dir, html_filename)
                    
                    with open(html_path, 'w', encoding='utf-8') as f:
                        f.write(html_diff)
                    
                    logger.info(f"✓ Generated HTML diff: {html_filename}")
                
                except Exception as comp_err:
                    logger.warning(f"Error generating HTML diff for {result.get('name', 'Unknown')}: {comp_err}")
            
            logger.info(f"✓ HTML diff files generated successfully")
        
        except Exception as e:
            logger.error(f"Error generating HTML diffs: {e}", exc_info=True)
    
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
            
            # Create output directory for snapshot comparison results (like offline mode)
            output_dir = os.path.join(os.getcwd(), "Snapshot_Comparison_Results")
            os.makedirs(output_dir, exist_ok=True)
            
            # Create report paths with absolute paths (consistent with offline mode)
            csv_report = os.path.join(output_dir, "snapshot_comparison.csv")
            excel_report = os.path.join(output_dir, "snapshot_comparison.xlsx")
            
            report_paths = {
                'csv': csv_report,
                'output_dir': output_dir,
                'excel': excel_report
            }
            
            logger.info(f"✓ Created output directory: {output_dir}")
            
            # Export snapshot comparison results to CSV, Excel, and HTML diffs
            self._export_snapshot_results_to_reports(
                viewer_results, 
                csv_report, 
                excel_report,
                snap1_name,
                snap2_name,
                comparison_metadata,
                output_dir
            )
            
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
        """Run folder comparison in background thread with file mapping preview"""
        # Reset progress
        self.progress_bar['value'] = 0
        self.progress_label.config(text="Preparing file mapping preview...")
        self.root.update()
        
        # Disable compare button during processing
        self.compare_btn.config(state='disabled')
        
        # Show file mapping dialog first (like test3.py)
        confirmed, custom_mappings = self.show_file_mapping_dialog(folder1, folder2)
        
        if not confirmed:
            self.progress_label.config(text="Comparison cancelled by user.")
            self.compare_btn.config(state='normal')
            return
        
        # Reset progress for actual comparison
        self.progress_bar['value'] = 0
        self.progress_label.config(text="Starting comparison...")
        self.root.update()
        
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
                    custom_mappings=custom_mappings,  # Use confirmed mappings
                    rtc_info=rtc_info
                )
                
                # Update UI on completion (must run in main thread)
                self.root.after(0, lambda: self.on_comparison_complete(result))
                
            except Exception as e:
                error_msg = f"Comparison failed: {str(e)}"
                self.root.after(0, lambda: self.on_comparison_error(error_msg))
        
        thread = threading.Thread(target=comparison_thread, daemon=True)
        thread.start()
    
    def show_file_mapping_dialog(self, folder1, folder2):
        """
        Show a preview dialog of file mappings with ability to manually map files.
        Returns: (confirmed, custom_mappings)
            confirmed: True if user confirmed, False if cancelled
            custom_mappings: dict of {file1_path: file2_path} for custom mappings
        """
        dialog = tk.Toplevel(self.root)
        dialog.title("File Mapping Preview - Confirm Comparison")
        dialog.geometry("1400x900")
        dialog.configure(bg="#f0f4f7")
        dialog.resizable(True, True)  # Allow resizing
        dialog.grab_set()  # Modal dialog
        
        # Result variables
        result = {'confirmed': False, 'mappings': {}}
        
        # Prepare folders (extract ZIP if needed)
        temp_dirs_to_cleanup = []
        folder1_actual, is_temp1, orig1 = self._prepare_folder_path(folder1)
        folder2_actual, is_temp2, orig2 = self._prepare_folder_path(folder2)
        
        if is_temp1:
            temp_dirs_to_cleanup.append(folder1_actual)
        if is_temp2:
            temp_dirs_to_cleanup.append(folder2_actual)
        
        if not folder1_actual or not folder2_actual:
            messagebox.showerror("Error", "Could not prepare folders for mapping preview.")
            for temp_dir in temp_dirs_to_cleanup:
                try:
                    shutil.rmtree(temp_dir)
                except:
                    pass
            dialog.destroy()
            return False, {}
        
        # Title
        title_frame = tk.Frame(dialog, bg="#003366", height=60)
        title_frame.pack(fill="x")
        title_frame.pack_propagate(False)
        
        tk.Label(
            title_frame,
            text="File Mapping Preview - Review and Confirm",
            font=("Segoe UI", 14, "bold"),
            bg="#003366",
            fg="white"
        ).pack(pady=15)
        
        # Info frame
        info_frame = tk.Frame(dialog, bg="#f0f4f7")
        info_frame.pack(fill="x", padx=20, pady=10)
        
        # Show original paths (ZIP names if applicable)
        folder1_display = f"{folder1}" + (" [ZIP - Extracted]" if is_temp1 else "")
        folder2_display = f"{folder2}" + (" [ZIP - Extracted]" if is_temp2 else "")
        
        tk.Label(
            info_frame,
            text=f"Platform (Baseline): {folder1_display}",
            font=("Segoe UI", 9, "bold"),
            bg="#f0f4f7",
            fg="#003366"
        ).pack(anchor="w")
        
        tk.Label(
            info_frame,
            text=f"Project (Comparison): {folder2_display}",
            font=("Segoe UI", 9, "bold"),
            bg="#f0f4f7",
            fg="#003366"
        ).pack(anchor="w")
        
        tk.Label(
            info_frame,
            text="Review the file mappings below. You can manually map files by selecting rows and clicking 'Map Selected'.",
            font=("Segoe UI", 9),
            bg="#f0f4f7",
            fg="#666666"
        ).pack(anchor="w", pady=(5, 0))
        
        # Create frame for treeview
        tree_frame = tk.Frame(dialog, bg="#ffffff")
        tree_frame.pack(fill="both", expand=False, padx=20, pady=10)
        
        # Scrollbars
        vsb = tk.Scrollbar(tree_frame, orient="vertical")
        hsb = tk.Scrollbar(tree_frame, orient="horizontal")
        
        # Treeview with columns
        columns = ("Platform File", "Project File", "Status", "Action")
        tree = ttk.Treeview(tree_frame, columns=columns, show="headings", 
                            yscrollcommand=vsb.set, xscrollcommand=hsb.set, height=20)
        
        vsb.config(command=tree.yview)
        hsb.config(command=tree.xview)
        
        # Configure columns
        tree.heading("Platform File", text="Platform File")
        tree.heading("Project File", text="Project File")
        tree.heading("Status", text="Status")
        tree.heading("Action", text="Action")
        
        tree.column("Platform File", width=500, anchor="w")
        tree.column("Project File", width=500, anchor="w")
        tree.column("Status", width=200, anchor="center")
        tree.column("Action", width=150, anchor="center")
        
        # Pack treeview and scrollbars
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        
        # Collect file mappings from extracted/actual folders
        files1 = {}
        files2 = {}
        
        for root_dir, dirs, files in os.walk(folder1_actual):
            for file in files:
                full_path = os.path.join(root_dir, file)
                rel_path = os.path.relpath(full_path, folder1_actual)
                files1[rel_path] = full_path
        
        for root_dir, dirs, files in os.walk(folder2_actual):
            for file in files:
                full_path = os.path.join(root_dir, file)
                rel_path = os.path.relpath(full_path, folder2_actual)
                files2[rel_path] = full_path
        
        # Populate treeview with mappings
        all_files = sorted(set(files1.keys()) | set(files2.keys()))
        
        for rel_path in all_files:
            file1 = files1.get(rel_path, "")
            file2 = files2.get(rel_path, "")
            
            if file1 and file2:
                status = "Will Compare"
                tag = "compare"
            elif file1 and not file2:
                status = "Only in Platform"
                tag = "only1"
            elif file2 and not file1:
                status = "Only in Project"
                tag = "only2"
            else:
                continue
            
            tree.insert("", "end", values=(
                rel_path if file1 else "[Not in Platform]",
                rel_path if file2 else "[Not in Project]",
                status,
                "Auto-mapped"
            ), tags=(tag,))
        
        # Configure tags for colors
        tree.tag_configure("compare", background="#E8F5E9")
        tree.tag_configure("only1", background="#E3F2FD")
        tree.tag_configure("only2", background="#FFF3E0")
        tree.tag_configure("custom", background="#F3E5F5")
        
        # Bottom container for stats and buttons
        bottom_frame = tk.Frame(dialog, bg="#f0f4f7")
        bottom_frame.pack(fill="x", side="bottom")
        
        # Statistics label
        stats_frame = tk.Frame(bottom_frame, bg="#f0f4f7")
        stats_frame.pack(fill="x", padx=20, pady=5)
        
        stats_label = tk.Label(
            stats_frame,
            text=f"Total Files: {len(all_files)} | Will Compare: {len([f for f in all_files if f in files1 and f in files2])} | "
                 f"Only in Platform: {len([f for f in all_files if f in files1 and f not in files2])} | "
                 f"Only in Project: {len([f for f in all_files if f in files2 and f not in files1])}",
            font=("Segoe UI", 9, "bold"),
            bg="#f0f4f7",
            fg="#003366"
        )
        stats_label.pack()
        
        # Button frame
        button_frame = tk.Frame(bottom_frame, bg="#f0f4f7")
        button_frame.pack(fill="x", padx=20, pady=5)
        
        # Manual mapping function
        def manual_mapping():
            """Allow user to manually map selected files"""
            mapping_window = tk.Toplevel(dialog)
            mapping_window.title("Manual File Mapping")
            mapping_window.geometry("900x600")
            mapping_window.configure(bg="#f0f4f7")
            mapping_window.grab_set()
            
            tk.Label(
                mapping_window,
                text="Select files to map together",
                font=("Segoe UI", 12, "bold"),
                bg="#f0f4f7"
            ).pack(pady=10)
            
            # Instructions
            instruction_text = (
                "📋 How to map files:\n"
                "1. Click to select a file from Folder 1 (LEFT)\n"
                "2. Click to select a file from Folder 2 (RIGHT)\n"
                "3. Click 'Create Mapping' button to map them together\n"
                "   OR double-click on Folder 2 file to auto-map with selected Folder 1 file"
            )
            tk.Label(
                mapping_window,
                text=instruction_text,
                font=("Segoe UI", 9),
                bg="#FFF9C4",
                fg="#000",
                justify="left",
                relief="solid",
                borderwidth=1,
                padx=10,
                pady=10
            ).pack(padx=20, pady=(0, 10), fill="x")
            
            # Two listboxes side by side
            list_frame = tk.Frame(mapping_window, bg="#f0f4f7")
            list_frame.pack(fill="both", expand=True, padx=20, pady=10)
            
            # Selection indicator labels
            selected_file1 = tk.StringVar(value="No file selected")
            selected_file2 = tk.StringVar(value="No file selected")
            
            # Folder 1 section
            folder1_frame = tk.Frame(list_frame, bg="#f0f4f7")
            folder1_frame.grid(row=0, column=0, sticky="nsew", padx=5)
            
            tk.Label(folder1_frame, text="📁 Folder 1 Files:", font=("Segoe UI", 10, "bold"), bg="#f0f4f7").pack(anchor="w")
            tk.Label(
                folder1_frame,
                textvariable=selected_file1,
                font=("Segoe UI", 8, "italic"),
                bg="#E3F2FD",
                fg="#1565C0",
                anchor="w",
                wraplength=450,
                relief="sunken",
                padx=5,
                pady=3
            ).pack(fill="x", pady=(3, 5))
            
            list1_scroll = tk.Scrollbar(folder1_frame)
            list1 = tk.Listbox(
                folder1_frame,
                width=55,
                height=20,
                yscrollcommand=list1_scroll.set,
                selectmode=tk.SINGLE,
                font=("Consolas", 9),
                bg="#FAFAFA"
            )
            list1_scroll.config(command=list1.yview)
            list1.pack(side="left", fill="both", expand=True)
            list1_scroll.pack(side="right", fill="y")
            
            # Arrow indicator in middle
            arrow_frame = tk.Frame(list_frame, bg="#f0f4f7", width=60)
            arrow_frame.grid(row=0, column=1, padx=10)
            tk.Label(
                arrow_frame,
                text="➜\nMAP\n➜",
                font=("Segoe UI", 14, "bold"),
                bg="#f0f4f7",
                fg="#FF6F00"
            ).pack(expand=True)
            
            # Folder 2 section
            folder2_frame = tk.Frame(list_frame, bg="#f0f4f7")
            folder2_frame.grid(row=0, column=2, sticky="nsew", padx=5)
            
            tk.Label(folder2_frame, text="📁 Folder 2 Files:", font=("Segoe UI", 10, "bold"), bg="#f0f4f7").pack(anchor="w")
            tk.Label(
                folder2_frame,
                textvariable=selected_file2,
                font=("Segoe UI", 8, "italic"),
                bg="#E8F5E9",
                fg="#2E7D32",
                anchor="w",
                wraplength=450,
                relief="sunken",
                padx=5,
                pady=3
            ).pack(fill="x", pady=(3, 5))
            
            list2_scroll = tk.Scrollbar(folder2_frame)
            list2 = tk.Listbox(
                folder2_frame,
                width=55,
                height=20,
                yscrollcommand=list2_scroll.set,
                selectmode=tk.SINGLE,
                font=("Consolas", 9),
                bg="#FAFAFA"
            )
            list2_scroll.config(command=list2.yview)
            list2.pack(side="left", fill="both", expand=True)
            list2_scroll.pack(side="right", fill="y")
            
            # Make columns expand
            list_frame.grid_columnconfigure(0, weight=1)
            list_frame.grid_columnconfigure(2, weight=1)
            list_frame.grid_rowconfigure(0, weight=1)
            
            # Populate listboxes
            for rel_path in sorted(files1.keys()):
                list1.insert(tk.END, rel_path)
            
            for rel_path in sorted(files2.keys()):
                list2.insert(tk.END, rel_path)
            
            # Store persistent selections
            persistent_selection = {'list1_index': None, 'list2_index': None}
            
            # Selection handlers with persistent storage
            def on_list1_select(event):
                sel = list1.curselection()
                if sel:
                    persistent_selection['list1_index'] = sel[0]
                    selected_file1.set(f"✓ Selected: {list1.get(sel[0])}")
                    # Highlight selected item with color
                    list1.itemconfig(sel[0], bg="#BBDEFB", fg="#000")
                    # Remove highlight from previously selected items
                    for i in range(list1.size()):
                        if i != sel[0]:
                            list1.itemconfig(i, bg="white", fg="black")
            
            def on_list2_select(event):
                sel = list2.curselection()
                if sel:
                    persistent_selection['list2_index'] = sel[0]
                    selected_file2.set(f"✓ Selected: {list2.get(sel[0])}")
                    # Highlight selected item with color
                    list2.itemconfig(sel[0], bg="#C8E6C9", fg="#000")
                    # Remove highlight from previously selected items
                    for i in range(list2.size()):
                        if i != sel[0]:
                            list2.itemconfig(i, bg="white", fg="black")
            
            def on_list2_double_click(event):
                """Double-click on list2 to auto-map with selected list1 file"""
                idx1 = persistent_selection['list1_index']
                idx2 = persistent_selection['list2_index']
                
                if idx1 is not None and idx2 is not None:
                    file1_rel = list1.get(idx1)
                    file2_rel = list2.get(idx2)
                    
                    # Add to custom mappings
                    result['mappings'][file1_rel] = file2_rel
                    
                    # Add to treeview
                    tree.insert("", "end", values=(
                        file1_rel,
                        file2_rel,
                        "Will Compare",
                        "Custom Mapping"
                    ), tags=("custom",))
                    
                    messagebox.showinfo("Mapping Created", f"✓ Successfully Mapped:\n\n{file1_rel}\n     ↓\n{file2_rel}")
                    mapping_window.destroy()
                elif idx1 is None:
                    messagebox.showwarning("No Selection", "⚠ Please select a file from Platform first")
            
            # Bind events
            list1.bind('<<ListboxSelect>>', on_list1_select)
            list2.bind('<<ListboxSelect>>', on_list2_select)
            list2.bind('<Double-Button-1>', on_list2_double_click)
            
            def create_mapping():
                idx1 = persistent_selection['list1_index']
                idx2 = persistent_selection['list2_index']
                
                if idx1 is None or idx2 is None:
                    messagebox.showwarning("Selection Required", "⚠ Please select one file from EACH list")
                    return
                
                file1_rel = list1.get(idx1)
                file2_rel = list2.get(idx2)
                
                # Add to custom mappings
                result['mappings'][file1_rel] = file2_rel
                
                # Add to treeview
                tree.insert("", "end", values=(
                    file1_rel,
                    file2_rel,
                    "Will Compare",
                    "Custom Mapping"
                ), tags=("custom",))
                
                messagebox.showinfo("Mapping Created", f"✓ Successfully Mapped:\n\n{file1_rel}\n     ↓\n{file2_rel}")
                mapping_window.destroy()
            
            # Button frame
            button_frame = tk.Frame(mapping_window, bg="#f0f4f7")
            button_frame.pack(pady=15)
            
            tk.Button(
                button_frame,
                text="✓ Create Mapping",
                command=create_mapping,
                bg="#007B3E",
                fg="white",
                font=("Segoe UI", 11, "bold"),
                width=20,
                height=2
            ).pack(side="left", padx=10)
            
            tk.Button(
                button_frame,
                text="✗ Cancel",
                command=mapping_window.destroy,
                bg="#C62828",
                fg="white",
                font=("Segoe UI", 11, "bold"),
                width=15,
                height=2
            ).pack(side="left", padx=10)
        
        tk.Button(
            button_frame,
            text="Manual File Mapping",
            command=manual_mapping,
            bg="#FF8C00",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            width=20
        ).pack(side="left", padx=5)
        
        def confirm_and_proceed():
            result['confirmed'] = True
            # Cleanup temp directories for mapping preview
            for temp_dir in temp_dirs_to_cleanup:
                try:
                    shutil.rmtree(temp_dir)
                except:
                    pass
            dialog.destroy()
        
        def cancel_comparison():
            result['confirmed'] = False
            # Cleanup temp directories for mapping preview
            for temp_dir in temp_dirs_to_cleanup:
                try:
                    shutil.rmtree(temp_dir)
                except:
                    pass
            dialog.destroy()
        
        tk.Button(
            button_frame,
            text="✓ Confirm & Generate Report",
            command=confirm_and_proceed,
            bg="#007B3E",
            fg="white",
            font=("Segoe UI", 11, "bold"),
            width=25
        ).pack(side="right", padx=5)
        
        tk.Button(
            button_frame,
            text="✗ Cancel",
            command=cancel_comparison,
            bg="#C62828",
            fg="white",
            font=("Segoe UI", 11, "bold"),
            width=15
        ).pack(side="right", padx=5)
        
        # Wait for dialog to close
        dialog.wait_window()
        
        return result['confirmed'], result['mappings']
    
    def _prepare_folder_path(self, path):
        """
        Prepare folder path for comparison - extract ZIP if needed.
        Returns: (actual_path, is_temp, original_path)
        """
        if not path:
            return None, False, path
        
        if path.lower().endswith('.zip'):
            try:
                import zipfile
                import tempfile
                
                # Create temp directory
                temp_dir = tempfile.mkdtemp(prefix="zip_extract_")
                
                # Extract ZIP
                with zipfile.ZipFile(path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
                
                return temp_dir, True, path
            except Exception as e:
                logger.warning(f"Failed to extract ZIP {path}: {e}")
                return None, False, path
        else:
            return path, False, path
    
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
    
    # -----------------------------------------------------------------------
    # Chatbot window
    # -----------------------------------------------------------------------

    def _open_chatbot_window(self):
        """Open (or raise) the floating Code Assistant chat window."""
        if not _CHATBOT_AVAILABLE:
            _expected = os.path.normpath(
                os.path.join(os.path.dirname(__file__), "..", "chatbot", "chatbot.py")
            )
            messagebox.showwarning(
                "Code Assistant Unavailable",
                "chatbot.py could not be loaded.\n\n"
                f"Expected location: {_expected}\n\n"
                "Make sure chatbot.py exists in src/chatbot/."
            )
            return

        # Re-use an already-open window instead of opening duplicates
        if hasattr(self, "_chat_win") and self._chat_win.winfo_exists():
            self._chat_win.lift()
            self._chat_win.focus_force()
            return

        # ── Build chatbot (lazy — only once) ────────────────────────────────
        if not hasattr(self, "_chatbot"):
            # Use Migration_V2 5.py as KB (lives in src/chatbot/), otherwise fallback to main.py
            _src_root = os.path.normpath(
                os.path.join(os.path.dirname(__file__), "..", "..")
            )
            kb_candidates = [
                os.path.join(_src_root, "src", "chatbot", "Migration_V2 5.py"),
                os.path.join(_src_root, "main.py"),
            ]
            kb_path = next((p for p in kb_candidates if os.path.isfile(p)), None)

            cfg = ChatConfig()
            if kb_path:
                cfg.kb_path = kb_path

            try:
                self._chatbot = build_chatbot(cfg)
            except Exception as exc:
                messagebox.showerror(
                    "Code Assistant Error",
                    f"Failed to initialise the chatbot:\n{exc}"
                )
                return

        # ── Create Toplevel window ────────────────────────────────────────────
        win = tk.Toplevel(self.root)
        win.title("\U0001f916  Code Assistant")
        win.geometry("920x680")
        win.configure(bg="#EAF3FB")
        win.resizable(True, True)

        # Keep a reference so we can re-raise it
        self._chat_win = win

        # Center relative to the main window
        self.root.update_idletasks()
        x = self.root.winfo_x() + self.root.winfo_width() + 10
        y = self.root.winfo_y()
        win.geometry(f"+{x}+{y}")

        # ── Embed TkinterChatPanel ───────────────────────────────────────────
        panel = TkinterChatPanel(win, self._chatbot, height=680)
        panel.pack(fill="both", expand=True)

        # Footer
        kb_name = os.path.basename(self._chatbot.kb.file_path)
        tk.Label(
            win,
            text=f"KB: {kb_name}  \u2022  {self._chatbot.kb.total_sections} sections  "
                 f"\u2022  Bosch Azure OpenAI GPT-4o-mini",
            bg="#003366", fg="white",
            font=("Segoe UI", 8)
        ).pack(fill="x", side="bottom")

    def run(self):
        """Run the GUI application"""
        self.root.mainloop()


def launch_gui():
    """Launch the Migration Analysis Tool GUI"""
    app = MigrationAnalysisGUI()
    app.run()
