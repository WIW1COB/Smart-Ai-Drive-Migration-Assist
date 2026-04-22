# -*- mode: python ; coding: utf-8 -*-

"""
PyInstaller spec file for Migration Analysis Tool
AGGRESSIVE size optimization (target: <24MB)
SCM tools NOT bundled - users must have LSCM/RTC SCM CLI installed
"""

import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect necessary data files
datas = []

# Add src directory
datas += [('src', 'src')]

# SCM TOOLS NOT BUNDLED to meet 24MB size limit
# Users must have RTC SCM CLI (lscm/scm.exe) installed separately
print("=" * 60)
print("BUILDING LIGHTWEIGHT VERSION (<24MB)")
print("SCM tools NOT bundled - users must install LSCM separately")
print("=" * 60)

# Aggressive exclusions to reduce size
excludes = [
    # Scientific/Data libraries
    'matplotlib',
    'scipy',
    'numpy',
    'pandas',
    'IPython',
    'jupyter',
    'notebook',
    
    # Alternative GUI frameworks
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
    'unittest',
    'test',
    
    # Development tools
    'setuptools',
    'pip',
    'wheel',
    'distutils',
    
    # Network (if not strictly needed)
    'asyncio',
    'multiprocessing',
    
    # Crypto (reduce if possible)
    'OpenSSL',
    
    # Other large modules
    'xml.etree',
    'email',
    'http.server',
    'xmlrpc',
    'pydoc',
    'doctest',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
        'openpyxl',
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        'requests',
        'openai',
        'dotenv',
        'keyring',
        'cryptography',
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
    name='MigrationAnalysisTool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,  # Strip debug symbols - CRITICAL for size reduction
    upx=True,  # Enable UPX compression - CRITICAL for size reduction
    upx_exclude=[
        # Exclude problematic DLLs from UPX (can cause issues)
        'vcruntime*.dll',
        'msvcp*.dll',
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
