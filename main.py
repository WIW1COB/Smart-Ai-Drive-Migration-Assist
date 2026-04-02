"""
Migration Analysis Report Generator

Main entry point for the application.
"""

import sys
import os

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
