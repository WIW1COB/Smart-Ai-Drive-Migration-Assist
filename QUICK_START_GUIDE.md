# Migration Analysis Tool - Quick Start Guide

## 🚀 Getting Started in 60 Seconds

### Step 1: Choose Your Version
- **MigrationAnalysisTool_Full.exe (101 MB)** ← **Recommended!**
  - No installation needed
  - Works immediately
  
- **MigrationAnalysisTool.exe (23 MB)**
  - Requires RTC SCM CLI installed

### Step 2: Run the Tool
Simply double-click the `.exe` file - no installation required!

### Step 3: Select Comparison Mode
Choose from the main window:
- **📁 Offline → Offline**: Compare local folders or ZIP files
- **☁️ Online → Online**: Compare RTC snapshots
- **🔄 Online → Offline**: Compare RTC snapshot with local folder

### Step 4: Start Analysis
1. Select your source and target
2. Click "Run Comparison"
3. View results in Excel/HTML reports

---

## 📊 Common Use Cases

### Compare Two Folders
1. Select "Offline → Offline" mode
2. Browse Source A and Source B folders
3. Click "Run Comparison"
4. Excel report opens automatically

### Compare RTC Snapshots
1. Select "Online → Online" mode
2. Login with RTC credentials
3. Enter snapshot URLs
4. Click "Fetch & Compare"
5. View results with changeset information

### Analyze Interface Changes
1. Go to "Advanced" → "Interface Analysis"
2. Select workspace path
3. Choose analysis type (Single/Compare)
4. Generate interface compatibility report

---

## 🔧 Features Overview

### Core Features
- ✅ **Multi-Mode Comparison** - Folders, ZIPs, RTC snapshots
- ✅ **10x Faster** - Parallel processing engine
- ✅ **Smart Reports** - Excel statistics + HTML diffs
- ✅ **RTC Integration** - Changeset tracking, work items
- ✅ **AI Assistant** - Ask questions about changes
- ✅ **Interface Analysis** - Header file compatibility

### AI Features (Optional)
Set API keys in `.env` file for:
- **Smart Merge Suggestions** - AI-powered conflict resolution
- **Comparison Assistant** - Natural language Q&A about changes

---

## ⚙️ Configuration (Optional)

### For AI Features
Create/edit `.env` file next to the executable:

```ini
# Groq API (Free tier available)
GROQ_API_KEY=your_key_here
GROQ_MODEL=llama-3.3-70b-versatile

# Corporate Proxy (if needed)
HTTPS_PROXY=http://proxy.company.com:8080
PROXY_USER=your_username
PROXY_PASS=your_password
```

Get free Groq API key: https://console.groq.com

### For RTC Integration
The tool auto-configures RTC settings. Just enter credentials when prompted!

---

## 💡 Tips & Tricks

### Faster Comparisons
- Use "Quick Compare" for large folders (skips file content analysis)
- Enable "Skip Binary Files" in advanced options
- Close other applications during large comparisons

### Better Reports
- Enable "Group by Component" for RTC comparisons
- Use "Show Comments Only" filter to find documentation changes
- Export results to share with team

### RTC Troubleshooting
- **Connection fails?** Check proxy settings in preferences
- **Snapshots not loading?** Verify RTC URL and credentials
- **SCM errors?** Full version has SCM bundled - use that!

---

## 📝 Report Outputs

After comparison, you'll get:

### 1. Excel Report (.xlsx)
- Summary statistics
- File-by-file comparison
- Component breakdowns
- Color-coded changes

### 2. HTML Diff Reports
- Side-by-side code comparison
- Syntax highlighting
- Line-by-line changes
- Clickable navigation

### 3. AI Chat (Optional)
- Ask questions about changes
- Get impact analysis
- Dependency insights

---

## 🆘 Quick Troubleshooting

### Tool Won't Start
- ✓ Check antivirus isn't blocking
- ✓ Run as administrator if needed
- ✓ Ensure Windows Defender allows execution

### RTC Features Don't Work
- ✓ Use **Full version** (has SCM bundled)
- ✓ Check RTC server is accessible
- ✓ Verify credentials are correct

### Comparison is Slow
- ✓200+ files can take 1-2 minutes (still 10x faster!)
- ✓ Use Quick Compare mode
- ✓ Check disk space for temp files

### Reports Don't Open
- ✓ Excel must be installed for .xlsx reports
- ✓ HTML reports open in default browser
- ✓ Check file permissions in output folder

---

## 📞 Need Help?

### Documentation Files
- **DISTRIBUTION_README.md** - Complete feature guide
- **BUILD_INSTRUCTIONS.md** - How to rebuild/customize
- **Presentation.pptx** - Visual overview of features

### Log Files
Check `rtc_comparison.log` in tool directory for detailed error messages

---

## ✅ Minimum Requirements

- **OS:** Windows 10/11 (64-bit)
- **RAM:** 2 GB minimum
- **Disk:** 500 MB free space
- **Network:** Optional (for RTC/AI features)

---

**Ready to go! Just double-click the .exe and start comparing!** 🚀
