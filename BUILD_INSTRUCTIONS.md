# Building Standalone Executable

## Overview
This guide explains how to build a standalone `.exe` file that **includes the RTC SCM CLI (scm.exe)** bundled within it. Users won't need to have LSCM installed on their PC.

## Prerequisites

1. **Python 3.8+** installed
2. **PyInstaller** (will be auto-installed by build script)
3. **SCM Tools** available at:
   ```
   C:\Users\yyy1cob\Desktop\598_Kit_Download_Fail\Migration_Assist\EWM-scmTools-Win64-7.0.3\jazz\scmtools\eclipse
   ```

## Build Steps

### Option 1: Using PowerShell Script (Recommended)

```powershell
cd WP-8152
.\build_exe.ps1
```

### Option 2: Manual Build

```powershell
cd WP-8152
pip install pyinstaller
pyinstaller --clean build_exe.spec
```

## What Gets Bundled

The executable includes:
- ✅ All Python dependencies (tkinter, openpyxl, requests, etc.)
- ✅ Complete RTC SCM CLI (~133 MB)
  - scm.exe
  - All plugins
  - Configuration files
- ✅ Application source code
- ✅ GUI assets

## Output

After build completes:
- **Executable**: `dist\MigrationAnalysisTool.exe`
- **Expected Size**: ~150-180 MB (includes SCM tools)
- **No installation required** - just distribute the .exe file

## How It Works

### Development Mode
When running from source (`python main.py`):
- Uses SCM from: `C:\Users\yyy1cob\Desktop\...\scmtools\eclipse\scm.exe`

### Compiled Executable Mode  
When running the built `.exe`:
- Uses bundled SCM from: `{exe_directory}\_internal\scmtools\scm.exe`
- Automatically detected via `sys.frozen` check in `settings.py`

## Distribution

To distribute to users:
1. Build the executable using steps above
2. Copy `dist\MigrationAnalysisTool.exe` to target location
3. Users can run directly - **no LSCM installation needed**!

## Customization

### To change SCM source path:
Edit `build_exe.spec` line 22:
```python
scm_source_dir = r'C:\path\to\your\scmtools\eclipse'
```

### To exclude SCM bundling:
Comment out lines 23-27 in `build_exe.spec`:
```python
# if os.path.exists(scm_source_dir):
#     datas += [(scm_source_dir, 'scmtools')]
```

## Troubleshooting

### Build fails with "SCM tools not found"
- Verify SCM path in `build_exe.spec`
- Ensure scm.exe exists at specified location

### Executable crashes on startup
- Run with console mode to see errors:
  - Edit `build_exe.spec`: Change `console=False` to `console=True`
  - Rebuild

### SCM commands fail in exe
- Check bundled path: Extract exe to temp folder and verify `scmtools\scm.exe` exists
- Verify SCM version compatibility (tested with 7.0.3)

## File Size Optimization

Current bundling includes full SCM installation (133 MB). If size is critical:

1. **Compress with UPX** (already enabled in spec):
   - Reduces exe size by ~30-40%

2. **7-Zip SFX** (optional):
   - Further compress the final exe
   - Users extract on first run

3. **Minimal SCM** (advanced):
   - Identify minimal plugin set needed
   - Exclude unnecessary plugins from bundling
   - *Warning: May break SCM functionality*

## Version Info

- Build Tool: PyInstaller 6.x
- SCM Version: 7.0.3 (EWM-scmTools-Win64)
- Python: 3.14
- Target OS: Windows x64
