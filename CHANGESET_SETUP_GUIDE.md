# Changeset Support - Setup Guide

## Overview
The Migration Analysis Tool now includes **changeset fetching** to show which changesets modified files in snapshot comparisons. This information appears in Excel and HTML reports.

## Requirements
To enable changeset details, you need:
1. **RTC SCM CLI (scm.exe or lscm)** installed on your system
2. **Configured LSCM_PATH** in the tool settings

## Installation Steps

### Step 1: Install RTC SCM CLI
Download and install the RTC SCM command-line client:
- **Official Download**: IBM RTC SCM CLI Tools
- **Version**: 7.0.3 or newer recommended
- **Typical Install Location**: 
  - `C:\Program Files\IBM\RTC-SCM-CLI\scmtools\eclipse\scm.exe`
  - `C:\toolbase\lscm\scmtools\eclipse\scm.exe`

### Step 2: Configure LSCM_PATH
The tool will automatically try to locate SCM at common paths:

**Automatic Detection Paths** (in order):
1. Bundled SCM (if running as .exe)
2. `C:\Users\yyy1cob\Desktop\598_Kit_Download_Fail\Migration_Assist\EWM-scmTools-Win64-7.0.3\jazz\scmtools\eclipse\scm.exe`
3. `C:\Program Files\IBM\RTC-SCM-CLI\scmtools\eclipse\scm.exe`
4. `C:\toolbase\lscm\scmtools\eclipse\scm.exe`

**Manual Configuration**:
If your SCM is installed elsewhere, edit `src/config/settings.py`:

```python
# Option 1: Set directly (bypasses auto-detection)
LSCM_PATH = r"C:\Your\Custom\Path\to\scm.exe"

# Option 2: Add to common paths list in _get_bundled_scm_path()
common_paths = [
    r"C:\Your\Custom\Path\to\scm.exe",
    # ... existing paths
]
```

### Step 3: Verify Configuration
Run a snapshot comparison. Check the logs for:

**Success Messages**:
```
Component_Name: Using LSCM at C:\path\to\scm.exe
✓ Component_Name: Found changeset 1234... (3 file(s))
```

**failure Messages**:
```
⚠ Component_Name: LSCM not available
"LSCM not configured - Install RTC SCM CLI for changeset details"
```

## What Gets Displayed

### Excel Report (Column 8: "Changeset Info")
- **Success**: `Changeset: 1234567890... (3 file(s))`
- **Not Available**: `LSCM not configured - Install RTC SCM CLI for changeset details`
- **No Changes**: `No modified files`

### HTML Reports
- Changeset information appears in the comparison details section
- Links to changesets (if available)

## Troubleshooting

### Issue: "LSCM not configured"
**Solution**: Install RTC SCM CLI and verify path

```powershell
# Check if SCM is accessible
& "C:\path\to\scm.exe" version
```

### Issue: "Changeset fetch failed"
**Possible Causes**:
1. SCM CLI not authenticated
2. Network/proxy issues
3. Incorrect server URL

**Solution**:
- Ensure you can run SCM commands manually
- Check RTC credentials
- Verify server connectivity

### Issue: Slow Performance
**Note**: Changeset fetching adds ~5-10 seconds per modified component

**Options**:
1. **Disable changeset fetching** for faster comparisons:
   - Edit `src/gui/main_window.py`
   - Change `enable_changesets = True` to `False` (line ~1021)
   - Rebuild executable

2. **Keep enabled** for comprehensive reports with changeset tracking

## Testing

### Test Snapshots (Provided by User)
```
Snapshot 1: _Ja2njykXEfGJH-eL1f3gyw
Snapshot 2: _7KJ8kzo3EfG7-rrSiLtzNg
```

Use these snapshots to verify changeset fetching works:
1. Enter snapshots in the tool
2. Select components to compare
3. Check Excel report (Column 8) for changeset details
4. Review logs for success/failure messages

## FAQ

**Q: Do I need LSCM for the tool to work?**
A: No. The tool works without LSCM, but changeset details won't be available in reports.

**Q: Can I use this with the .exe version?**
A: Yes. Install RTC SCM CLI separately and it will be auto-detected if in standard locations.

**Q: How many changesets are fetched per component?**
A: Up to 10 file changesets per component (configurable in code).

**Q: Does this slow down comparisons?**
A: Yes, adds ~5-10 seconds per modified component. You can disable it in settings for faster performance.

## Support
For issues or questions:
- Check application logs (`MigrationAssist_*.log`)
- Review console output during comparison
- Verify LSCM installation and configuration
