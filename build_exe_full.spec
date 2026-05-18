# -*- mode: python ; coding: utf-8 -*-

"""
PyInstaller spec file for Migration Analysis Tool - FULL VERSION
INCLUDES SCM TOOLS BUNDLED (~150-180 MB)
Users don't need LSCM installed separately
"""

import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect necessary data files
datas = []

# Add src directory
datas += [('src', 'src')]

# ============================================================
# BUNDLE SCM TOOLS (Full Version)
# ============================================================
# Check multiple possible locations for SCM tools
scm_paths = [
    r'C:\Program Files\BOSCH\STEPS\ALM\SCM',  # Found on this system!
    r'C:\Users\yyy1cob\Desktop\598_Kit_Download_Fail\Migration_Assist\EWM-scmTools-Win64-7.0.3\jazz\scmtools\eclipse',
    r'C:\Program Files\IBM\RTC-SCM-CLI\scmtools\eclipse',
    r'C:\toolbase\lscm\scmtools\eclipse',
]

scm_source_dir = None
for path in scm_paths:
    if os.path.exists(path):
        scm_source_dir = path
        break

if scm_source_dir and os.path.exists(scm_source_dir):
    print("=" * 70)
    print("BUILDING FULL VERSION WITH BUNDLED SCM TOOLS")
    print(f"SCM Source: {scm_source_dir}")
    print("Expected Size: ~110-130 MB (with 89MB SCM)")
    print("=" * 70)
    datas += [(scm_source_dir, 'SCM')]
    scm_bundled = True
else:
    print("=" * 70)
    print("SCM tools not found - Building FULL VERSION structure")
    print("You can add SCM tools manually later")
    print("Checked paths:")
    for path in scm_paths:
        print(f"  - {path}")
    print("Expected Size: ~24 MB (without SCM)")
    print("=" * 70)
    scm_bundled = False

# Reduced exclusions (keep more functionality for full version)
excludes = [
    # Scientific/Data libraries (not needed)
    'matplotlib',
    'scipy',
    'numpy',
    'pandas',
    'IPython',
    'jupyter',
    'notebook',
    
    # Alternative GUI frameworks (not needed)
    'PyQt5',
    'PyQt6',
    'PySide2',
    'PySide6',
    'wx',
    
    # Web/Testing frameworks
    'tornado',
    'flask',
    'django',
    'sphinx',
    'pytest',
    
    # Development tools
    'setuptools',
    'pip',
    'wheel',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
        'openpyxl',
        'openpyxl.styles',
        'openpyxl.utils',
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        'requests',
        'openai',
        'dotenv',
        'keyring',
        'cryptography',
        'requests_ntlm',
        'dateutil',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='MigrationAnalysisTool_Full',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,  # Don't strip for full version (better compatibility)
    upx=True,  # Enable UPX compression to reduce size somewhat
    upx_exclude=[
        'vcruntime*.dll',
        'msvcp*.dll',
        'python*.dll',
    ],
    runtime_tmpdir=None,
    console=False,  # No console window for GUI
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon path if available
    onefile=True,  # Single file executable
)
