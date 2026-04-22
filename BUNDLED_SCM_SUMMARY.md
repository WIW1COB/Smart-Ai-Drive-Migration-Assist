# Standalone EXE with Bundled SCM - Summary

## ✅ What Was Done

### 1. Updated PyInstaller Spec (`build_exe.spec`)
- Added SCM tools bundling configuration
- Bundles entire `scmtools/eclipse` directory (133 MB)
- Includes scm.exe + all plugins + configuration

### 2. Updated Settings (`src/config/settings.py`)
- Added `_get_bundled_scm_path()` function
- Auto-detects if running as compiled .exe or in dev mode
- **Dev mode**: Uses installed SCM at original path
- **Exe mode**: Uses bundled SCM from `{exe}\_internal\scmtools\scm.exe`

### 3. Created Build Scripts
- **BUILD.bat** - Windows double-click build
- **build_exe.ps1** - PowerShell build script (existing, updated)
- **BUILD_INSTRUCTIONS.md** - Comprehensive guide

## 🚀 How to Build

### Quick Start (Double-click)
```
1. Navigate to: WP-8152\
2. Double-click: BUILD.bat
3. Wait 5-10 minutes
4. Find exe at: dist\MigrationAnalysisTool.exe
```

### PowerShell
```powershell
cd WP-8152
.\build_exe.ps1
```

### Command Line
```bash
cd WP-8152
pyinstaller --clean build_exe.spec
```

## 📦 What Gets Bundled

| Component | Size | Purpose |
|-----------|------|---------|
| Application Code | ~5 MB | Python source + dependencies |
| Python Runtime | ~15 MB | Embedded Python interpreter |
| SCM Tools | ~133 MB | RTC CLI (scm.exe + plugins) |
| **Total** | **~150-180 MB** | Single .exe file |

## 🎯 Key Features

### ✅ No User Installation Required
- Users **don't need** to install RTC SCM CLI
- Users **don't need** Python
- Just run `MigrationAnalysisTool.exe`

### ✅ Automatic SCM Detection
Development mode:
```python
# Uses: C:\Users\...\scmtools\eclipse\scm.exe
LSCM_PATH = _get_bundled_scm_path()
```

Compiled exe mode:
```python
# Uses: {exe_dir}\_internal\scmtools\scm.exe  
if getattr(sys, 'frozen', False):
    bundle_dir = sys._MEIPASS
    scm_path = os.path.join(bundle_dir, 'scmtools', 'scm.exe')
```

### ✅ Fallback Support
If bundled SCM not found, tries:
1. Bundled location
2. Development path
3. Common installation paths:
   - `C:\Program Files\IBM\RTC-SCM-CLI\...`
   - `C:\toolbase\lscm\...`

## 📊 Expected Build Output

```
========================================
Migration Analysis Tool - EXE Builder
Bundles SCM Tools (~133MB)
========================================

✓ PyInstaller is ready!
✓ Bundling SCM tools from: C:\...\scmtools\eclipse
✓ Build Complete!

Final executable size: 155.23 MB
Location: dist\MigrationAnalysisTool.exe

✓ SCM tools bundled - users don't need LSCM installed!
```

## 🔧 Customization

### Change SCM Source Path
Edit `build_exe.spec` line 20:
```python
scm_source_dir = r'C:\your\custom\path\scmtools\eclipse'
```

### Disable Console Window
In `build_exe.spec` line 90:
```python
console=False,  # No console (current)
# console=True, # Show console for debugging
```

## 📝 Distribution

1. Build the exe: `.\BUILD.bat`
2. Test locally: `dist\MigrationAnalysisTool.exe`
3. Distribute: Copy .exe to target computers
4. Users run: Double-click to launch

**No installation, no dependencies, no configuration!**

## ⚠️ Known Limitations

1. **Size**: ~150-180 MB (includes full SCM installation)
2. **Build Time**: 5-10 minutes (bundles large SCM directory)
3. **Windows Only**: Build spec configured for Windows x64
4. **Antivirus**: Some AV may flag PyInstaller exes (false positive)

## 🐛 Troubleshooting

### Build fails: "SCM tools not found"
**Solution**: Check path in `build_exe.spec` matches your SCM location

### Exe crashes on startup  
**Solution**: Enable console mode, rebuild, check error messages

### SCM commands fail in exe
**Solution**: Verify bundled files exist in `{exe}\_internal\scmtools\`

### File too large to distribute
**Options**:
- Use 7-Zip to compress (reduces ~30%)
- Host on network share instead of email
- Use installer (NSIS/Inno Setup) with compression

## ✅ Testing Checklist

Before distribution, test the exe:
- [ ] Launches without errors
- [ ] RTC connection works
- [ ] Snapshot comparison runs
- [ ] File diffs generate
- [ ] HTML reports open
- [ ] No "LSCM not found" warnings

## 📞 Support

For issues, check:
1. `BUILD_INSTRUCTIONS.md` - Detailed build guide
2. Build logs in `build\` directory
3. Console output (set `console=True` in spec)
