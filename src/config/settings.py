"""Configuration settings for Migration Analysis Tool"""

import os

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
LSCM_PATH = r"C:\toolbase\lscm\7.0.3\jazz\scmtools\eclipse\scm.exe"  # BOSCH STEPS ALM SCM installation

# Global variables for RTC authentication
RTC_USERNAME = None
RTC_PASSWORD = None
RTC_ENABLED = False

# Global variables for RTC workspace/stream detection
RTC_WORKSPACE_NAME = None
RTC_STREAM_NAME = None
RTC_REPOSITORY_UUID = None

# Global variables for snapshot comparison
SNAPSHOT_MODE = False
SNAPSHOT1_URL = None
SNAPSHOT2_URL = None

# ---------------------------------------------------------------------------
# AI Configuration — set your API keys here (tool-level, no UI entry needed)
# ---------------------------------------------------------------------------
# Google Gemini Flash — FREE AI model used for AI Smart Merge
# Get a FREE key (no credit card) at: https://aistudio.google.com/app/apikey
# Sign in with any Google account → "Create API key" → paste below
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyD2TwpunJMKwCRsDh97-IqYsTWd__1W-UY")

# OpenAI GPT-4o-mini — used to enhance AI Suggest (optional; heuristics work without it)
# Get your key at: https://platform.openai.com/api-keys
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# ---------------------------------------------------------------------------
# Corporate Proxy Configuration (for Gemini API calls)
# ---------------------------------------------------------------------------
# Auto-detected Bosch proxy. Change PROXY_URL to "" to disable.
PROXY_URL = os.environ.get("HTTPS_PROXY",
                          os.environ.get("HTTP_PROXY", "http://rb-proxy-in.bosch.com:8080"))
# Leave PROXY_USER / PROXY_PASS empty to be prompted once at runtime.
# Or fill in directly: PROXY_USER = "BOSCH\\WIW1COB", PROXY_PASS = "yourpassword"
PROXY_DOMAIN = os.environ.get("PROXY_DOMAIN", "BOSCH")
PROXY_USER = os.environ.get("PROXY_USER", "")  # e.g. "WIW1COB" (without domain)
PROXY_PASS = os.environ.get("PROXY_PASS", "")  # leave empty → prompted on first call

# In-memory cache so we only prompt once per session
_proxy_cred_cache = {}
