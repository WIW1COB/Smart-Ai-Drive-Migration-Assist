# Migration Analysis Tool - Distribution Package

## 📦 Available Versions

### 1. **MigrationAnalysisTool.exe** (23.7 MB) - Lightweight
- ✅ All GUI features
- ✅ Folder/ZIP comparison  
- ✅ Excel & HTML reports
- ✅ AI-powered features
- ⚠️ Requires users to have RTC SCM CLI installed for snapshot features

**Use when:** Users already have RTC SCM installed on their systems

---

### 2. **MigrationAnalysisTool_Full.exe** (101 MB) - Complete
- ✅ All features from lightweight version
- ✅ **Bundled RTC SCM tools** - No installation required!
- ✅ True portable solution
- ✅ RTC snapshot comparison works out-of-the-box

**Use when:** Users don't have RTC SCM or you want zero-installation deployment

---

## 🚀 Distribution Instructions

### Quick Start
1. Choose the appropriate version (lightweight or full)
2. Copy the .exe to target location
3. Users can run directly - no installation needed!

### For IT/Deployment Teams
Both executables are standalone - no dependencies required:
- No Python installation needed
- No DLL dependencies
- No registry modifications
- Can run from USB drive, network share, or local disk

---

## 📊 Feature Comparison

| Feature | Lightweight (23.7 MB) | Full (101 MB) |
|---------|----------------------|---------------|
| GUI Interface | ✅ | ✅ |
| Folder/ZIP Comparison | ✅ | ✅ |
| Excel Reports | ✅ | ✅ |
| HTML Diff Reports | ✅ | ✅ |
| AI Smart Merge | ✅ | ✅ |
| Interface Analysis | ✅ | ✅ |
| RTC Integration | ⚠️ Requires SCM | ✅ Built-in |
| Snapshot Comparison | ⚠️ Requires SCM | ✅ Built-in |
| Changeset Tracking | ⚠️ Requires SCM | ✅ Built-in |
| Zero Installation | ✅ | ✅ |
| Portable | ✅ | ✅ |

---

## 🔧 Technical Details

### Lightweight Version
- **Bundled:** Python runtime, GUI libraries, analysis engine
- **External:** RTC SCM CLI (must be installed separately)
- **SCM Detection:** Auto-detects from:
  - `C:\Program Files\BOSCH\STEPS\ALM\SCM`
  - `C:\Program Files\IBM\RTC-SCM-CLI`
  - Other standard locations

### Full Version  
- **Bundled:** Everything + RTC SCM CLI (~89 MB)
- **External:** Nothing - completely self-contained
- **SCM Location:** Embedded in executable's `_internal\SCM` folder

---

## 💻 System Requirements

- **OS:** Windows 10/11 (64-bit)
- **RAM:** 2 GB minimum, 4 GB recommended
- **Disk:** 500 MB free space (for temporary files and reports)
- **Network:** Internet connection for AI features (optional)

---

## 🎯 Recommended Usage

### Development Teams
Use **Lightweight version** if:
- Team already has RTC SCM CLI installed
- Want smaller file size for distribution
- Have standardized development environment

Use **Full version** if:
- Mixed environment (some users don't have RTC)
- Want maximum portability
- Deploying to multiple sites/locations
- Users are non-technical

### End Users
- **Full version is recommended** for hassle-free experience
- No prerequisites or installations needed
- Works immediately after download

---

## 📝 Version Information

**Build Date:** May 18, 2026  
**Python Version:** 3.14.4  
**PyInstaller:** 6.20.0  
**SCM Version:** Bosch STEPS ALM SCM

---

## 🛠️ Rebuilding

To rebuild with updated code:

**Lightweight:**
```powershell
.\build_exe.ps1
```

**Full (with SCM):**
```powershell
.\build_exe_full.ps1
```

**Prerequisites for building:**
- Python 3.8+
- PyInstaller
- For full version: RTC SCM at `C:\Program Files\BOSCH\STEPS\ALM\SCM`

---

## 📞 Support

For issues or questions:
- Check logs: `rtc_comparison.log` (created in tool directory)
- Review: `BUILD_INSTRUCTIONS.md` for build details
- Review: `HOW_TO_ADD_SCM_TOOLS.md` for SCM configuration

---

## ✅ Quality Assurance

Both executables tested for:
- ✓ GUI startup and responsiveness
- ✓ File comparison (folders, ZIPs)
- ✓ Report generation (Excel, HTML)
- ✓ RTC connectivity (Full version)
- ✓ Memory usage (<500 MB typical)
- ✓ Startup time (<5 seconds)

---

**Ready for distribution! 🚀**
