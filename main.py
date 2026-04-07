"""
Migration Analysis Report Generator

Main entry point for the application.
"""

import sys
import os

# Load environment variables from .env when running from terminal
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except Exception:
    # .env loading is optional; app can still run with OS-level env vars
    pass

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.gui.main_window import launch_gui


def main():
    """Main entry point for the Migration Analysis Tool"""
    print("=" * 60)
    print("Migration Analysis Report Generator")
    print("Bosch Engineering - Migration Analysis Tool")
    print("=" * 60)
    print()
    
    # Launch the GUI
    launch_gui()


if __name__ == "__main__":
    main()
