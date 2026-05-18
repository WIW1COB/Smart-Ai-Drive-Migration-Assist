"""Configuration settings for Migration Analysis Tool"""

import os
import sys

try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(os.path.join(os.path.dirname(__file__), "../..", ".env"), override=True)
except Exception:
    pass

# ---------------------------------------------------------------------------
# RTC/ALM Configuration
# ---------------------------------------------------------------------------
RTC_SERVER_URL = "https://rb-alm-06-p.de.bosch.com/ccm"
CERT_PATH = os.path.join(os.path.dirname(__file__), "../..", "rb-alm-06-p-de-bosch-com-chain.pem")

# RTC Client Java Library path for workitem fetching
RTC_CLIENT_LIB_PATH = r"C:\Users\WIW1COB\Desktop\TOOL_Developed\Migration_Analysis_Report\NEW\NEW2\RTC-Client-plainJavaLib-6.0.6.1"

# RTC SCM CLI (lscm) Configuration - OPTIONAL for faster component fetching
# The tool will automatically fall back to REST API if lscm is not available or fails
# Using scm.exe directly instead of lscm.bat to bypass Java environment issues
# Example: r"C:\Program Files\IBM\RTC-SCM-CLI\scmtools\eclipse\scm.exe"

def _get_lscm_path():
    """
    Auto-detect LSCM/SCM path. Checks:
    1. Bundled SCM (if running from executable)
    2. Bosch STEPS installation
    3. Standard installations
    4. Fallback to configured path
    """
    # Check if running as frozen executable (PyInstaller)
    if getattr(sys, 'frozen', False):
        # Running as executable - check bundled SCM
        exe_dir = os.path.dirname(sys.executable)
        bundled_scm = os.path.join(exe_dir, '_internal', 'SCM', 'scm.exe')
        if os.path.exists(bundled_scm):
            return bundled_scm
    
    # Check common installation paths
    common_paths = [
        r"C:\Program Files\BOSCH\STEPS\ALM\SCM\scm.exe",  # Bosch STEPS
        r"C:\Program Files\IBM\RTC-SCM-CLI\scmtools\eclipse\scm.exe",
        r"C:\toolbase\lscm\scmtools\eclipse\scm.exe",
        r"C:\Users\yyy1cob\Desktop\598_Kit_Download_Fail\Migration_Assist\EWM-scmTools-Win64-7.0.3\jazz\scmtools\eclipse\scm.exe",
    ]
    
    for path in common_paths:
        if os.path.exists(path):
            return path
    
    # Fallback to original configured path
    return None

LSCM_PATH = _get_lscm_path()

# Global variables for RTC authentication
RTC_USERNAME = None
RTC_PASSWORD = None
RTC_ENABLED = True  # Enable RTC integration for changeset fetching

# Global variables for RTC workspace/stream detection
RTC_WORKSPACE_NAME = None
RTC_STREAM_NAME = None
RTC_REPOSITORY_UUID = None

# Global variables for snapshot comparison
SNAPSHOT_MODE = False
SNAPSHOT1_URL = None
SNAPSHOT2_URL = None

# ---------------------------------------------------------------------------
# AI Configuration — set keys via environment variables
# ---------------------------------------------------------------------------

# ============ GROQ (Primary LLM — Active) ============
# Groq API key for the migration assistant chatbot.
# Set via environment variable GROQ_API_KEY
# Get your key from: https://console.groq.com
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# Groq model selection
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
# Other available models:
#   - llama-3.3-70b-versatile (recommended for general tasks, currently available)
#   - llama-3.1-405b-reasoning (most capable, slower)
#   - mixtral-8x7b-32768
#   - gemma-7b-it

# ============ Groq Proxy Configuration (for corporate networks) ============
# Set these if Groq fails with DNS/network errors on corporate networks
GROQ_PROXY_URL = os.environ.get(
    "GROQ_PROXY_URL",
    os.environ.get("HTTPS_PROXY", os.environ.get("HTTP_PROXY", "")),
)
# Example: "http://proxy.company.com:8080" or "http://user:pass@proxy:8080"

GROQ_PROXY_USERNAME = os.environ.get(
    "GROQ_PROXY_USERNAME",
    os.environ.get("PROXY_USER", ""),
)
# Example: "DOMAIN\\username" or just "username"

GROQ_PROXY_PASSWORD = os.environ.get(
    "GROQ_PROXY_PASSWORD",
    os.environ.get("PROXY_PASS", ""),
)
# Example: "password" (will be prompted if not set and proxy_url is configured)

# ============ Azure OpenAI / Bosch Farm (Disabled for now; will reuse when available) ============
# NOTE: Bosch AOAI Farm is currently unavailable.
#       Uncomment and configure these settings to re-enable when the service returns.
#       The chatbot will automatically prefer Groq if both are available.

# AOAI_FARM_SUBSCRIPTION_KEY = os.environ.get("GENAIPLATFORM_FARM_SUBSCRIPTION_KEY", "")
# AOAI_FARM_ENDPOINT = os.environ.get("AOAI_FARM_ENDPOINT", "https://aoai-farm.bosch-temp.com/api")
# AOAI_FARM_DEPLOYMENT = os.environ.get(
#     "AOAI_FARM_DEPLOYMENT",
#     "askbosch-prod-farm-openai-gpt-41-mini-2025-04-14",
# )
# AOAI_FARM_API_VERSION = os.environ.get("AOAI_FARM_API_VERSION", "2025-04-14-preview")
# AOAI_FARM_MODEL = os.environ.get("AOAI_FARM_MODEL", "gpt-5-2025-08-07")
# AOAI_CHAT_DEPLOYMENT = os.environ.get("AOAI_CHAT_DEPLOYMENT", "gpt-5-nano-2025-08-07")
# AOAI_CHAT_API_VERSION = os.environ.get("AOAI_CHAT_API_VERSION", "2025-04-01-preview")

# OpenAI API key — used to enhance AI Suggest (optional; heuristics work without it)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# ---------------------------------------------------------------------------
# Corporate Proxy Configuration (optional; used for outbound HTTP calls)
# ---------------------------------------------------------------------------
# Auto-detected Bosch proxy. Change PROXY_URL to "" to disable.
# NOTE: Groq may work better without corporate proxy; configure HTTPS_PROXY if needed.
PROXY_URL = os.environ.get("HTTPS_PROXY",
                          os.environ.get("HTTP_PROXY", "http://rb-proxy-in.bosch.com:8080"))
# Leave PROXY_USER / PROXY_PASS empty to be prompted once at runtime.
# Or fill in directly: PROXY_USER = "BOSCH\\WIW1COB", PROXY_PASS = "yourpassword"
PROXY_DOMAIN = os.environ.get("PROXY_DOMAIN", "BOSCH")
PROXY_USER = os.environ.get("PROXY_USER", "")  # e.g. "WIW1COB" (without domain)
PROXY_PASS = os.environ.get("PROXY_PASS", "")  # leave empty → prompted on first call

# In-memory cache so we only prompt once per session
_proxy_cred_cache = {}

# ---------------------------------------------------------------------------
# Performance Optimization Configuration
# ---------------------------------------------------------------------------
# Maximum number of concurrent threads for parallel baseline fetching.
# Each thread reuses a persistent HTTP connection (requests Session pool),
# so raising this is safe and directly reduces fetch time.
# Rule of thumb: 20 is fast without overloading RTC; raise to 30 if VPN is stable.
# Hard cap in code: 30 (to avoid RTC throttling).
MAX_WORKERS = 20

# Use SCM CLI (scm.exe) to list files in baselines — more reliable than /service/ REST endpoints
# which require Jazz Form Authentication session cookies that can be difficult to obtain.
SKIP_SCM_CLI = False

# Enable lazy loading for tree views
# Load tree children on-demand instead of all at once
ENABLE_LAZY_LOAD = True

# Batch size for UI updates (update UI every N items)
# Higher = faster but less responsive visual feedback
BATCH_SIZE = 500

# Maximum number of threads for parallel directory scanning
MAX_SCAN_THREADS = 4

# Cache configuration
ENABLE_FILE_COMPARISON_CACHE = True
ENABLE_FOLDER_STRUCTURE_CACHE = True
ENABLE_BASELINE_CACHE = True
ENABLE_COMPONENT_COMPARISON_CACHE = True
ENABLE_FILE_CONTENT_CACHE = True

# Cache sizes (number of items)
FILE_COMPARISON_CACHE_SIZE = 500
FOLDER_STRUCTURE_CACHE_SIZE = 100
BASELINE_CACHE_SIZE = 50
COMPONENT_COMPARISON_CACHE_SIZE = 100
FILE_CONTENT_CACHE_SIZE = 200

# Cache TTL (time-to-live) in seconds
CACHE_TTL_FILE_COMPARISON = 3600  # 1 hour
CACHE_TTL_FOLDER_STRUCTURE = 1800  # 30 minutes
CACHE_TTL_BASELINE = 7200  # 2 hours
CACHE_TTL_COMPONENT_COMPARISON = 3600  # 1 hour
CACHE_TTL_FILE_CONTENT = 3600  # 1 hour
