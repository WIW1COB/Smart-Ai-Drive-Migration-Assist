"""Dialog windows for the Migration Analysis Tool"""

import tkinter as tk
from tkinter import messagebox


def show_comparison_results_dialog(results, folder1_name, folder2_name, folder1_path, folder2_path, files1, files2):
    """
    Show interactive results dialog with file listing and details.
    
    Args:
        results: List of comparison results
        folder1_name: Name/path of platform folder
        folder2_name: Name/path of project folder
        folder1_path: Actual path to folder 1
        folder2_path: Actual path to folder 2
        files1: Dict of files in folder 1
        files2: Dict of files in folder 2
    """
    # NOTE: This is a placeholder - Full implementation in test.py lines ~3000-3500
    # Should implement the complete interactive results dialog
    print("show_comparison_results_dialog - TODO: Implement from test.py")
    messagebox.showinfo("Results", f"Comparison complete!\n{len(results)} files processed.")


def show_component_selection_dialog(components1, components2):
    """
    Show dialog to select components for online-online snapshot comparison.
    
    Only shows components that exist in BOTH snapshots (common components).
    Components unique to each snapshot are shown as info only.
    
    Args:
        components1: List of components from snapshot 1 (list of dicts with 'name' key)
        components2: List of components from snapshot 2 (list of dicts with 'name' key)
    
    Returns:
        dict: {
            'canceled': bool (True if user canceled),
            'selected': list of selected component names,
            'only_in_snap1': list of components only in snapshot 1,
            'only_in_snap2': list of components only in snapshot 2,
            'common': list of all common components
        }
    """
    import tkinter.ttk as ttk
    
    # Extract component names
    names1 = set(c.get('name', str(c)) for c in (components1 or []))
    names2 = set(c.get('name', str(c)) for c in (components2 or []))
    
    common_components = sorted(names1 & names2)
    only_in_snap1 = sorted(names1 - names2)
    only_in_snap2 = sorted(names2 - names1)
    
    # Create dialog
    dialog = tk.Toplevel()
    dialog.title("Select Components for Comparison - Online Mode")
    dialog.geometry("1000x700")
    dialog.resizable(True, True)
    
    # Make modal
    dialog.transient()
    dialog.grab_set()
    
    result = {
        'canceled': True,
        'selected': [],
        'only_in_snap1': only_in_snap1,
        'only_in_snap2': only_in_snap2,
        'common': common_components,
    }
    
    # ===== Header =====
    header_frame = tk.Frame(dialog, bg='#34495E', height=70)
    header_frame.pack(fill=tk.X)
    
    title_label = tk.Label(
        header_frame,
        text="📋 Component Selection - Online Snapshot Comparison",
        font=("Arial", 13, "bold"),
        bg='#34495E',
        fg='white'
    )
    title_label.pack(pady=8)
    
    stats_label = tk.Label(
        header_frame,
        text=f"Snapshot 1: {len(names1)} components  |  Snapshot 2: {len(names2)} components  |  Common: {len(common_components)}",
        font=("Arial", 10),
        bg='#34495E',
        fg='#ECF0F1'
    )
    stats_label.pack()
    
    # ===== Notebook Tabs =====
    notebook = ttk.Notebook(dialog)
    notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
    
    # --- Tab 1: Common Components (Selectable) ---
    tab_common = ttk.Frame(notebook)
    notebook.add(tab_common, text=f"🔄 Common Components ({len(common_components)})")
    
    # Info label
    info_label = tk.Label(
        tab_common,
        text="Select which components to compare (exist in both snapshots):",
        font=("Arial", 10),
        bg='white',
        justify=tk.LEFT
    )
    info_label.pack(anchor=tk.W, padx=10, pady=8)
    
    # Scrollable checkboxes for common components
    scrollframe = tk.Frame(tab_common)
    scrollframe.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
    
    scrollbar = ttk.Scrollbar(scrollframe)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    canvas = tk.Canvas(scrollframe, yscrollcommand=scrollbar.set, bg='white', highlightthickness=0)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.config(command=canvas.yview)
    
    inner_frame = tk.Frame(canvas, bg='white')
    canvas_window = canvas.create_window((0, 0), window=inner_frame, anchor=tk.NW)
    
    # Store checkbox variables
    component_vars = {}
    
    for comp_name in common_components:
        var = tk.BooleanVar(value=True)  # Default: all selected
        component_vars[comp_name] = var
        
        cb = tk.Checkbutton(
            inner_frame,
            text=comp_name,
            variable=var,
            font=("Arial", 9),
            bg='white',
            activebackground='#ECF0F1',
            anchor=tk.W
        )
        cb.pack(fill=tk.X, padx=5, pady=2)
    
    # Update canvas scroll region
    def on_frame_configure(event=None):
        canvas.configure(scrollregion=canvas.bbox("all"))
        # Make window width match canvas width
        canvas.itemconfig(canvas_window, width=canvas.winfo_width())
    
    inner_frame.bind("<Configure>", on_frame_configure)
    canvas.bind("<Configure>", lambda e: on_frame_configure())
    
    # Mouse wheel scrolling
    def _on_mousewheel(event):
        canvas.yview_scroll(int(-1*(event.delta/120)), "units")
    canvas.bind_all("<MouseWheel>", _on_mousewheel)
    
    # --- Tab 2: Only in Snapshot 1 ---
    tab_snap1 = ttk.Frame(notebook)
    notebook.add(tab_snap1, text=f"📍 Only in Snapshot 1 ({len(only_in_snap1)})")
    
    label1 = tk.Label(
        tab_snap1,
        text="These components exist ONLY in Snapshot 1 (excluded from comparison):",
        font=("Arial", 10),
        bg='white'
    )
    label1.pack(anchor=tk.W, padx=10, pady=8)
    
    text1 = tk.Text(tab_snap1, height=20, font=("Courier", 9), bg='#FFF3E0', fg='#E65100')
    text1.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
    
    snap1_text = "\n".join([f"  • {c}" for c in only_in_snap1]) if only_in_snap1 else "  (none)"
    text1.insert(tk.END, snap1_text)
    text1.config(state=tk.DISABLED)
    
    # --- Tab 3: Only in Snapshot 2 ---
    tab_snap2 = ttk.Frame(notebook)
    notebook.add(tab_snap2, text=f"📍 Only in Snapshot 2 ({len(only_in_snap2)})")
    
    label2 = tk.Label(
        tab_snap2,
        text="These components exist ONLY in Snapshot 2 (excluded from comparison):",
        font=("Arial", 10),
        bg='white'
    )
    label2.pack(anchor=tk.W, padx=10, pady=8)
    
    text2 = tk.Text(tab_snap2, height=20, font=("Courier", 9), bg='#E3F2FD', fg='#01579B')
    text2.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
    
    snap2_text = "\n".join([f"  • {c}" for c in only_in_snap2]) if only_in_snap2 else "  (none)"
    text2.insert(tk.END, snap2_text)
    text2.config(state=tk.DISABLED)
    
    # ===== Button Frame =====
    button_frame = tk.Frame(dialog, bg='#ECF0F1', height=50)
    button_frame.pack(fill=tk.X, padx=10, pady=10)
    
    # Quick action buttons
    quick_frame = tk.Frame(button_frame, bg='#ECF0F1')
    quick_frame.pack(side=tk.LEFT)
    
    def select_all():
        for var in component_vars.values():
            var.set(True)
    
    def deselect_all():
        for var in component_vars.values():
            var.set(False)
    
    btn_select_all = tk.Button(
        quick_frame,
        text="✓ Select All",
        command=select_all,
        bg='#27AE60',
        fg='white',
        font=("Arial", 10),
        padx=10,
        pady=5
    )
    btn_select_all.pack(side=tk.LEFT, padx=5)
    
    btn_deselect = tk.Button(
        quick_frame,
        text="✗ Deselect All",
        command=deselect_all,
        bg='#E74C3C',
        fg='white',
        font=("Arial", 10),
        padx=10,
        pady=5
    )
    btn_deselect.pack(side=tk.LEFT, padx=5)
    
    # Action buttons
    action_frame = tk.Frame(button_frame, bg='#ECF0F1')
    action_frame.pack(side=tk.RIGHT)
    
    def on_compare():
        result['selected'] = [comp for comp, var in component_vars.items() if var.get()]
        result['canceled'] = False
        dialog.destroy()
    
    def on_cancel():
        result['canceled'] = True
        dialog.destroy()
    
    btn_compare = tk.Button(
        action_frame,
        text="▶ Compare Selected",
        command=on_compare,
        bg='#3498DB',
        fg='white',
        font=("Arial", 11, "bold"),
        padx=20,
        pady=6
    )
    btn_compare.pack(side=tk.LEFT, padx=5)
    
    btn_cancel = tk.Button(
        action_frame,
        text="Cancel",
        command=on_cancel,
        bg='#95A5A6',
        fg='white',
        font=("Arial", 10),
        padx=20,
        pady=6
    )
    btn_cancel.pack(side=tk.LEFT, padx=5)
    
    # Center dialog on screen
    dialog.update_idletasks()
    x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
    y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
    dialog.geometry(f"+{max(0, x)}+{max(0, y)}")
    
    # Wait for dialog to close
    dialog.wait_window()
    
    return result


def show_file_mapping_dialog(files1, files2, existing_mappings=None):
    """
    Show dialog for manual file mapping between two folders.
    
    Args:
        files1: Dict of files from folder 1
        files2: Dict of files from folder 2
        existing_mappings: Dict of existing custom mappings
    
    Returns:
        tuple: (confirmed, mappings_dict)
    """
    # NOTE: This is a placeholder - Full implementation in test.py
    # Should implement the complete file mapping dialog
    print("show_file_mapping_dialog - TODO: Implement from test.py")
    return False, {}
