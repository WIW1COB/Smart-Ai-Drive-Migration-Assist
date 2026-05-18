# HOW TO ADD SCM TOOLS TO THE EXECUTABLE

## Current Status
✅ **MigrationAnalysisTool_Full.exe created** (~24 MB)  
⚠️ **SCM tools NOT bundled** - needs manual addition

## Two Ways to Get Full Functionality

### Option 1: Users Install RTC SCM CLI (Easiest)
Users who run the .exe simply need to install RTC SCM CLI on their PC:
- Download from IBM/Bosch repository
- Install to standard location
- The tool will auto-detect it

### Option 2: Rebuild with SCM Bundled (Best)

#### Step 1: Get RTC SCM CLI
Download: **EWM-scmTools-Win64-7.0.3** or newer

#### Step 2: Extract to one of these locations:
- `C:\Program Files\IBM\RTC-SCM-CLI\scmtools\eclipse`
- `C:\toolbase\lscm\scmtools\eclipse`

#### Step 3: Verify SCM exists:
```powershell
Test-Path "C:\Program Files\IBM\RTC-SCM-CLI\scmtools\eclipse\scm.exe"
```
Should return: `True`

#### Step 4: Rebuild:
```powershell
cd WP-8152
.\build_exe_full.ps1
```

This will create a ~150-180 MB exe with ALL SCM tools bundled!

## What's the Difference?

### Current Build (24 MB):
- ✅ All GUI features
- ✅ Excel/HTML reports
- ✅ AI features
- ⚠️ RTC features require system-installed SCM

### Full Build with SCM (150-180 MB):
- ✅ Everything above
- ✅ SCM tools bundled inside
- ✅ Users don't need ANY installation
- ✅ Truly portable

## Which Should You Use?

**If users have RTC SCM installed:** Current 24 MB version is perfect!  
**If users don't have RTC:** Rebuild with SCM bundled (follow steps above)

## Testing

Run either version:
```powershell
.\dist\MigrationAnalysisTool_Full.exe
```

Try RTC snapshot comparison to verify SCM functionality works.
