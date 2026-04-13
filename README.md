# Migration Analysis Report Generator

A comprehensive tool for analyzing code migration differences between platforms, with RTC/ALM integration and AI-powered suggestions.

## 🌟 Features
WIW1COB

- **Folder/ZIP Comparison**: Compare entire directories or ZIP archives
- **RTC Snapshot Comparison**: Compare snapshots from IBM Rational Team Concert
- **File Mapping**: Manual and automatic file mapping for accurate comparisons
- **HTML Diff Reports**: Generate detailed HTML difference reports
- **Excel Reports**: Create comprehensive Excel reports with statistics
- **RTC Integration**: Fetch changesets and work items from RTC/ALM
- **AI Smart Merge**: Use Google Gemini AI for intelligent merge suggestions
- **Comment Detection**: Identify when only comments have changed
- **Parallel Processing**: Fast comparison using multi-threading

## 📁 Project Structure

```
WP-8152/
├── src/
│   ├── config/          # Configuration settings
│   │   ├── __init__.py
│   │   └── settings.py  # RTC, AI, and proxy configurations
│   ├── utils/           # Utility modules
│   │   ├── __init__.py
│   │   ├── file_utils.py    # File operations
│   │   ├── excel_utils.py   # Excel report generation
│   │   ├── xml_utils.py     # XML handling
│   │   └── diff_utils.py    # Diff generation
│   ├── rtc/             # RTC/ALM integration
│   │   ├── __init__.py
│   │   ├── snapshot.py      # Snapshot operations
│   │   ├── workspace.py     # Workspace detection
│   │   └── changeset.py     # Changeset and work item operations
│   ├── ai/              # AI integration
│   │   ├── __init__.py
│   │   ├── gemini.py        # Google Gemini integration
│   │   └── openai_integration.py  # OpenAI GPT integration
│   └── gui/             # GUI components
│       ├── __init__.py
│       ├── main_window.py   # Main application window
│       ├── dialogs.py       # Dialog windows
│       └── components.py    # Reusable GUI components
├── main.py              # Application entry point
├── test.py              # Original monolithic implementation (reference)
├── requirements.txt     # Python dependencies
├── .gitignore          # Git ignore rules
└── README.md           # This file
```

## 🚀 Getting Started

### Prerequisites

- Python 3.8 or higher
- Windows OS (for full RTC integration)
- Optional: IBM RTC SCM CLI for enhanced snapshot comparison
- Optional: Java Runtime for RTC work item fetching

### Installation

1. Clone the repository:

```bash
cd WP-8152
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Configure settings:
   - Edit `src/config/settings.py` to set:
     - RTC server URL and paths
     - API keys for AI features (optional)
     - Proxy settings if behind corporate proxy

### Running the Application

```bash
python main.py
```

## 🔧 Configuration

### RTC/ALM Integration

Edit `src/config/settings.py`:

```python
RTC_SERVER_URL = "https://your-rtc-server.com/ccm"
CERT_PATH = "path/to/certificate.pem"
LSCM_PATH = r"C:\path\to\scm.exe"  # Optional
RTC_CLIENT_LIB_PATH = r"C:\path\to\RTC-Client-plainJavaLib"  # Optional
```

### AI Integration

Set up API keys:

```python
# Google Gemini (Free tier available)
GEMINI_API_KEY = "your-gemini-api-key"

# OpenAI GPT (Optional)
OPENAI_API_KEY = "your-openai-api-key"
```

Get your free Gemini API key: https://aistudio.google.com/app/apikey

### Proxy Configuration

For corporate networks:

```python
PROXY_URL = "http://proxy.company.com:8080"
PROXY_DOMAIN = "DOMAIN"
PROXY_USER = "username"  # Leave empty to be prompted
PROXY_PASS = "password"  # Leave empty to be prompted
```

## 📖 Usage

### Folder Comparison

1. Launch the application
2. Select "Folder/ZIP Comparison" mode
3. Browse and select platform folder/ZIP
4. Browse and select project folder/ZIP
5. Click "Start Comparison"
6. Review results in the interactive dialog
7. Export results to Excel/CSV

### Snapshot Comparison

1. Launch the application
2. Select "RTC Snapshot Comparison" mode
3. Paste snapshot URLs or UUIDs from RTC
4. Enable RTC integration if needed
5. Click "Start Comparison"
6. Select components to compare
7. Review changeset and file differences

## 📊 Output

The tool generates:

- **Excel Report**: Detailed comparison with statistics and color coding
- **CSV Report**: Raw data for further processing
- **HTML Diff Reports**: Side-by-side file comparisons
- **Interactive GUI**: Browse and analyze results

## 🎨 Color Coding

- 🟢 Green: Identical files (no changes)
- 🔵 Blue: Files only in platform
- 🟡 Yellow: Comment changes only
- 🔴 Red: Files with code differences
- 🟠 Orange: Files only in project

## 🔨 Development

### Project Evolution

This project was restructured from a monolithic `test.py` file into a modular architecture:

- **Original**: Single 5,500+ line file
- **Restructured**: Organized into logical modules
- **Benefits**: Better maintainability, testability, and extensibility

### Adding New Features

1. Identify the appropriate module (utils, rtc, ai, gui)
2. Add your implementation
3. Update imports in module's `__init__.py`
4. Test thoroughly

### TODO: Complete Implementation

The current structure provides a framework. To complete:

1. Migrate full logic from `test.py` to respective modules:
   - RTC snapshot/workspace/changeset functions
   - Complete Excel report generation
   - AI integration implementation
   - Full GUI dialog implementations

2. Test all features thoroughly
3. Add unit tests
4. Update documentation

## 🐛 Troubleshooting

### Common Issues

**RTC Connection Failed:**

- Verify RTC server URL and credentials
- Check certificate path
- Ensure network connectivity

**ZIP Extraction Error:**

- Verify ZIP file is not corrupted
- Check disk space for temp extraction

**Excel Export Failed:**

- Close any open Excel files with same name
- Check write permissions in output directory

**AI Features Not Working:**

- Verify API keys are set correctly
- Check proxy configuration
- Ensure internet connectivity

## 📝 License

Internal Bosch tool - Refer to company policies for usage rights.

## 👥 Contributors

Bosch Engineering Team

## 🔗 Related Tools

- IBM Rational Team Concert (RTC)
- Google Gemini AI
- OpenAI GPT

## 📞 Support

For issues or questions, contact the development team or refer to internal documentation.

---

**Note**: This tool is designed for internal use within Bosch for migration analysis projects. The `test.py` file contains the original complete implementation and serves as a reference during the modularization process.
Workpacket for developing Migration Assist application
