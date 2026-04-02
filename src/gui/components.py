"""Reusable GUI components for the Migration Analysis Tool"""

import tkinter as tk
from tkinter import ttk


def create_styled_button(parent, text, command, bg_color="#003366", fg_color="white", width=20):
    """
    Create a styled button with consistent appearance.
    
    Args:
        parent: Parent widget
        text: Button text
        command: Command to execute on click
        bg_color: Background color
        fg_color: Foreground (text) color
        width: Button width
    
    Returns:
        tk.Button: Configured button widget
    """
    return tk.Button(
        parent,
        text=text,
        command=command,
        bg=bg_color,
        fg=fg_color,
        font=("Segoe UI", 10, "bold"),
        width=width,
        cursor="hand2"
    )


def create_label_entry_pair(parent, label_text, entry_width=50):
    """
    Create a label-entry pair with consistent styling.
    
    Args:
        parent: Parent widget
        label_text: Text for the label
        entry_width: Width of the entry field
    
    Returns:
        tuple: (label_widget, entry_widget)
    """
    label = tk.Label(
        parent,
        text=label_text,
        bg="#EAF3FB",
        font=("Segoe UI", 10)
    )
    
    entry = tk.Entry(parent, width=entry_width)
    
    return label, entry


def create_progress_section(parent):
    """
    Create a progress section with label and progress bar.
    
    Args:
        parent: Parent widget
    
    Returns:
        tuple: (progress_label, progress_bar)
    """
    frame = tk.Frame(parent, bg="#EAF3FB")
    frame.pack(fill="both", expand=True, pady=10)
    
    label = tk.Label(
        frame,
        text="Ready...",
        bg="#EAF3FB",
        font=("Segoe UI", 10)
    )
    label.pack(pady=5)
    
    progress_bar = ttk.Progressbar(
        frame,
        length=600,
        mode='determinate'
    )
    progress_bar.pack(pady=5)
    
    return label, progress_bar


def create_scrollable_frame(parent, bg_color="white"):
    """
    Create a scrollable frame using canvas and scrollbar.
    
    Args:
        parent: Parent widget
        bg_color: Background color
    
    Returns:
        tuple: (canvas, scrollbar, scrollable_frame)
    """
    canvas = tk.Canvas(parent, bg=bg_color, highlightthickness=0)
    scrollbar = tk.Scrollbar(parent, orient="vertical", command=canvas.yview)
    scrollable_frame = tk.Frame(canvas, bg=bg_color)
    
    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )
    
    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    
    return canvas, scrollbar, scrollable_frame
