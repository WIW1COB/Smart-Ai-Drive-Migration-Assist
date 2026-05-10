#!/usr/bin/env python3
"""Test Groq API connectivity and functionality"""

import os
import sys
from urllib.parse import quote, urlsplit, urlunsplit

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"), override=True)
except Exception:
    pass


def _first_env(*names: str) -> str:
    """Return the first non-empty environment variable from names."""
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _with_proxy_credentials(proxy_url: str) -> str:
    """Add Bosch proxy credentials from .env when the proxy URL has no auth."""
    if not proxy_url:
        return ""

    parsed = urlsplit(proxy_url if "://" in proxy_url else f"http://{proxy_url}")
    if "@" in parsed.netloc:
        return urlunsplit(parsed)

    user = _first_env("GROQ_PROXY_USERNAME", "PROXY_USER")
    password = _first_env("GROQ_PROXY_PASSWORD", "PROXY_PASS")
    domain = _first_env("PROXY_DOMAIN")
    if not user:
        return urlunsplit(parsed)

    if domain and "\\" not in user and "/" not in user:
        user = f"{domain}\\{user}"

    auth = quote(user, safe="") if password == "" else f"{quote(user, safe='')}:{quote(password, safe='')}"
    return urlunsplit((parsed.scheme, f"{auth}@{parsed.netloc}", parsed.path, parsed.query, parsed.fragment))


def _groq_proxy_url() -> str:
    """Prefer explicit Groq proxy, then standard HTTPS/HTTP proxy env vars."""
    return _with_proxy_credentials(
        _first_env("GROQ_PROXY_URL", "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy")
    )


def _httpx_client(httpx):
    proxy_url = _groq_proxy_url()
    if proxy_url:
        print("   Using proxy from .env/env: configured")
        return httpx.Client(
            proxy=proxy_url,
            trust_env=False,
            verify=False,
            timeout=60.0,
        )

    print("   No proxy configured; using direct connection")
    return httpx.Client(trust_env=True, timeout=60.0)


def _fail_if_bosch_proxy_missing() -> None:
    if _groq_proxy_url():
        return

    print(
        "   ❌ No proxy loaded. On the Bosch network this will fail after "
        "\"Sending test message to Groq...\" with a socket/connection error."
    )
    print("   Fix .env by uncommenting at least:")
    print("      HTTPS_PROXY=http://rb-proxy-in.bosch.com:8080")
    print("      HTTP_PROXY=http://rb-proxy-in.bosch.com:8080")
    print("   If your proxy requires auth, also uncomment PROXY_DOMAIN, PROXY_USER, and PROXY_PASS.")
    sys.exit(1)

print("=" * 70)
print("GROQ API TEST")
print("=" * 70)

# Check if GROQ_API_KEY is set
groq_key = os.environ.get("GROQ_API_KEY", "")
print(f"\n1. GROQ_API_KEY env var: {'✅ SET' if groq_key else '❌ NOT SET'}")
if groq_key:
    print(f"   Key preview: {groq_key[:20]}...{groq_key[-5:]}")

proxy_preview = _first_env("GROQ_PROXY_URL", "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy")
print(f"   Proxy env var: {'✅ SET' if proxy_preview else '❌ NOT SET'}")
if proxy_preview:
    print(f"   Proxy source: {'GROQ_PROXY_URL' if _first_env('GROQ_PROXY_URL') else 'HTTPS_PROXY/HTTP_PROXY'}")
else:
    print("   Proxy source: none loaded from .env")

# Check if groq package is installed
print("\n2. Checking groq package...")
try:
    import groq
    print(f"   ✅ groq package installed (version: {groq.__version__ if hasattr(groq, '__version__') else 'unknown'})")
except ImportError as e:
    print(f"   ❌ groq package NOT installed: {e}")
    print("      Install with: pip install groq")
    sys.exit(1)

# Test Groq API call
print("\n3. Testing Groq API call...")
try:
    from groq import Groq
    import httpx

    _fail_if_bosch_proxy_missing()

    with _httpx_client(httpx) as http_client:
        client = Groq(api_key=groq_key, http_client=http_client)

        print("   Sending test message to Groq...")
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "user",
                    "content": "Explain in 2-3 sentences: what is enterprise code migration and why is it important for automotive software at Bosch?"
                }
            ],
            temperature=0.7,
            max_tokens=200,
        )
        
        reply = response.choices[0].message.content
        print(f"   ✅ Groq API working!\n")
        print(f"   Response:\n   {reply}\n")

except Exception as e:
    print(f"   ❌ Groq API call failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test our GroqChatEngine wrapper
print("\n4. Testing GroqChatEngine wrapper...")
try:
    from src.chatbot.chatbot import GroqChatEngine
    
    groq_model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    groq_proxy = _first_env("GROQ_PROXY_URL", "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy")
    groq_proxy_user = _first_env("GROQ_PROXY_USERNAME", "PROXY_USER")
    groq_proxy_pass = _first_env("GROQ_PROXY_PASSWORD", "PROXY_PASS")
    groq_proxy_domain = _first_env("PROXY_DOMAIN")
    if groq_proxy_domain and groq_proxy_user and "\\" not in groq_proxy_user and "/" not in groq_proxy_user:
        groq_proxy_user = f"{groq_proxy_domain}\\{groq_proxy_user}"
    print(f"   Using model: {groq_model}")
    engine = GroqChatEngine(
        api_key=groq_key,
        model=groq_model,
        proxy_url=groq_proxy or None,
        proxy_user=groq_proxy_user or None,
        proxy_password=groq_proxy_pass or None,
    )
    
    print("   Calling engine.complete()...")
    reply = engine.complete([
        {"role": "user", "content": "In 2-3 sentences: explain enterprise code migration and why it's important for Bosch."}
    ])
    
    print(f"   ✅ GroqChatEngine working!\n")
    print(f"   Response:\n   {reply}\n")
    
except Exception as e:
    print(f"   ❌ GroqChatEngine failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 70)
print("✅ ALL TESTS PASSED - Groq is working correctly!")
print("=" * 70)
