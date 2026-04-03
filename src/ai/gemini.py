"""Google Gemini AI integration for AI Smart Merge"""

import os
import json as _json
import urllib.parse
import getpass
from src.config import settings


_GEMINI_MODEL   = "gemini-2.0-flash"
_GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
_DEP_SCAN_EXTS  = {".c", ".h", ".cpp", ".hpp", ".cs", ".py", ".java",
                   ".xml", ".arxml", ".cfg", ".mk", ".mak",
                   ".json", ".yaml", ".yml", ".properties"}

# Proxy credential cache (in-memory)
_proxy_cred_cache = {}


def _gemini_call(api_key, system_prompt, user_prompt, max_tokens=8192):
    """Send a message to Google Gemini Flash and return the text response.
    Automatically routes through the corporate Bosch NTLM proxy.
    Password is requested once via a popup and cached for the session.
    Includes retry logic for rate limiting (429 errors).
    """
    import time
    import requests as _req
    
    url = f"{_GEMINI_API_URL}?key={urllib.parse.quote(api_key.strip())}"
    headers  = {"content-type": "application/json"}
    payload  = _json.dumps({
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents":           [{"parts": [{"text": user_prompt}]}],
        "generationConfig":   {"maxOutputTokens": max_tokens, "temperature": 0.3},
    })

    def _build_session(user, password):
        """Return a requests.Session configured with NTLM proxy auth."""
        sess = _req.Session()
        if settings.PROXY_URL and settings.PROXY_URL.strip():
            _pu = settings.PROXY_URL.strip().rstrip("/")
            sess.proxies = {"http": _pu, "https": _pu}
            if user and password:
                try:
                    from requests_ntlm import HttpNtlmAuth
                    domain_user = f"{settings.PROXY_DOMAIN}\\{user}" if "\\" not in user else user
                    sess.auth = HttpNtlmAuth(domain_user, password)
                except ImportError:
                    pass  # no NTLM library — try basic proxy URL embedding
        return sess

    def _get_credentials():
        """Return (user, password) from cache, constants, or a one-time Tkinter dialog."""
        if _proxy_cred_cache:
            return _proxy_cred_cache.get("user", ""), _proxy_cred_cache.get("pass", "")

        _u = settings.PROXY_USER.strip() if hasattr(settings, 'PROXY_USER') and settings.PROXY_USER else getpass.getuser()
        _p = settings.PROXY_PASS.strip() if hasattr(settings, 'PROXY_PASS') and settings.PROXY_PASS else ""

        if not _p and settings.PROXY_URL:
            # Show a one-time password popup
            try:
                import tkinter as _tk
                import tkinter.simpledialog as _sd
                _root_hidden = _tk.Tk()
                _root_hidden.withdraw()
                _p = _sd.askstring(
                    "Proxy Authentication",
                    f"Enter your Bosch Windows password for:\n"
                    f"  Proxy : {settings.PROXY_URL}\n"
                    f"  User  : {settings.PROXY_DOMAIN}\\{_u}\n",
                    show="*", parent=_root_hidden
                ) or ""
                _root_hidden.destroy()
            except:
                pass

        _proxy_cred_cache["user"] = _u
        _proxy_cred_cache["pass"] = _p
        return _u, _p

    user, password = _get_credentials()
    sess = _build_session(user, password)

    # Retry logic with exponential backoff for rate limiting
    max_retries = 3
    base_delay = 2  # seconds
    
    for attempt in range(max_retries):
        try:
            resp = sess.post(url, data=payload.encode(), headers=headers, timeout=90, verify=True)
            resp.raise_for_status()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
            
        except _req.exceptions.HTTPError as e:
            if e.response.status_code == 429:  # Rate limit error
                if attempt < max_retries - 1:  # Not the last attempt
                    wait_time = base_delay * (2 ** attempt)  # Exponential backoff: 2s, 4s, 8s
                    print(f"⚠️ Rate limit hit. Waiting {wait_time}s before retry {attempt + 2}/{max_retries}...")
                    time.sleep(wait_time)
                    continue
                else:
                    # Last attempt failed
                    raise ValueError(
                        "Gemini API Rate Limit Exceeded\n\n"
                        "The free tier of Gemini API has limits:\n"
                        "• 15 requests per minute\n"
                        "• 1 million tokens per minute\n"
                        "• 1,500 requests per day\n\n"
                        "Please wait a minute and try again, or:\n"
                        "1. Check your quota at: https://aistudio.google.com/app/apikey\n"
                        "2. Consider upgrading to paid tier for higher limits\n"
                        "3. Use the request less frequently"
                    ) from e
            else:
                # Other HTTP errors
                raise ValueError(f"Gemini API Error ({e.response.status_code}): {str(e)}") from e
                
        except _req.exceptions.RequestException as e:
            raise ValueError(f"Network error calling Gemini API: {str(e)}") from e
    
    # Should not reach here, but just in case
    raise ValueError("Failed to call Gemini API after all retries")


def _read_file_safe(path, max_chars=8000):
    """Read a file as text, truncating if very large."""
    if not path or not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read(max_chars)
        if os.path.getsize(path) > max_chars:
            content += f"\n... [truncated - file is {os.path.getsize(path)} bytes total]"
        return content
    except Exception:
        return ""


def _scan_related_files(fname, target_files_dict, max_files=8):
    """
    Find files in the TARGET folder that reference fname.
    Returns list of (rel_path, abs_path, lineno, match_line) tuples.
    """
    base        = os.path.basename(fname)
    base_no_ext = os.path.splitext(base)[0]
    patterns = [
        f'include "{base}"',
        f"include '{base}'",
        f"include <{base}>",
        f'import "{base_no_ext}"',
        f"import '{base_no_ext}'",
        f"from {base_no_ext} import",
    ]
    found = []
    for rel, abs_path in sorted(target_files_dict.items()):
        if os.path.splitext(rel)[1].lower() not in _DEP_SCAN_EXTS:
            continue
        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as fh:
                for lineno, line in enumerate(fh, 1):
                    ll = line.lower()
                    if any(p.lower() in ll for p in patterns):
                        found.append((rel, abs_path, lineno, line.strip()))
                        break
        except Exception:
            pass
        if len(found) >= max_files:
            break
    return found


def ai_merge_with_gemini(path1, path2, status, rel_path, files1, files2, 
                         folder1_root, folder2_root, api_key):
    """
    Use Google Gemini Flash to intelligently merge two file versions.
    Returns (merged_content, dependency_report, warnings) tuple.
    
    Args:
        path1: Path to file in folder 1
        path2: Path to file in folder 2
        status: Comparison status
        rel_path: Relative path of the file
        files1: Dict of all files in folder 1
        files2: Dict of all files in folder 2
        folder1_root: Root path of folder 1
        folder2_root: Root path of folder 2
        api_key: Gemini API key
        
    Returns:
        tuple: (merged_content, dependency_report, warnings)
    """
    if not api_key or not api_key.strip():
        raise ValueError("Gemini API key is required for AI Merge.")

    fname = os.path.basename(path1 or path2 or rel_path)
    ext   = os.path.splitext(fname)[1].lower()
    lang  = {
        ".c": "C", ".h": "C", ".cpp": "C++", ".hpp": "C++",
        ".cs": "C#", ".py": "Python", ".java": "Java",
        ".xml": "XML", ".arxml": "ARXML", ".cfg": "Config",
        ".mk": "Makefile", ".mak": "Makefile",
        ".json": "JSON", ".yaml": "YAML", ".yml": "YAML",
        ".properties": "Properties",
    }.get(ext, "text")

    content1 = _read_file_safe(path1)
    content2 = _read_file_safe(path2)

    # Dependency scan on the TARGET side
    if status == "Only in Platform":
        related = _scan_related_files(fname, files2)
        target_label = "Project (target)"
        source_label = "Platform (baseline)"
    elif status == "Only in Project":
        related = _scan_related_files(fname, files1)
        target_label = "Platform (baseline)"
        source_label = "Project (target)"
    else:
        related = _scan_related_files(fname, files2)
        target_label = "Folder 2 (target)"
        source_label = "Folder 1 (baseline)"

    dep_snippets = []
    for rel, abs_path, lineno, match_line in related:
        snippet = _read_file_safe(abs_path, max_chars=1200)
        dep_snippets.append(
            f"--- Dependent: {rel} (reference at line {lineno}: {match_line}) ---\n{snippet}\n"
        )
    dep_context = "\n".join(dep_snippets) if dep_snippets else "(no direct dependencies found in target folder)"

    # Build Gemini prompt
    system_prompt = (
        "You are an expert software engineer specialising in code migration and merging. "
        "Your task is to produce a SINGLE merged file that:\n"
        "1. Combines both versions without losing any logic.\n"
        "2. Resolves all conflicts intelligently.\n"
        "3. Does NOT break any of the dependent files shown (preserve signatures, types, macros).\n"
        "4. Keeps all copyright headers, version comments, and important annotations.\n"
        "5. Preserves the original language syntax and style.\n"
        "\nOUTPUT FORMAT - return EXACTLY two sections separated by ===DEPENDENCY_REPORT===\n"
        "Section 1: Complete merged file (raw file only, no markdown fences, no explanation).\n"
        "Section 2: Bullet-point dependency impact report (max 15 bullets) covering:\n"
        "  - Which dependent files were checked\n"
        "  - Whether the merge could break any of them\n"
        "  - Warnings and recommended follow-up actions\n"
    )

    if status in ("Only in Platform", "Only in Project"):
        src_content = content1 if status == "Only in Platform" else content2
        user_prompt = (
            f"File: {fname} ({lang})\nStatus: {status}\n"
            f"This file exists ONLY in {source_label} and must be integrated into {target_label}.\n\n"
            f"=== FILE CONTENT from {source_label} ===\n{src_content}\n\n"
            f"=== DEPENDENT FILES already in {target_label} ===\n{dep_context}\n\n"
            "Instructions:\n"
            "- Adapt the file if needed to integrate cleanly into the target context.\n"
            "- Adjust include paths / namespaces ONLY if required by the dependent files.\n"
            "- Keep ALL logic intact. Do not simplify or remove code.\n"
            "- Produce the adapted file content then the dependency report.\n"
        )
    else:
        user_prompt = (
            f"File: {fname} ({lang})\nStatus: {status}\n\n"
            f"=== VERSION 1 - {source_label} ({len(content1.splitlines())} lines) ===\n{content1}\n\n"
            f"=== VERSION 2 - {target_label} ({len(content2.splitlines())} lines) ===\n{content2}\n\n"
            f"=== DEPENDENT FILES in target folder ===\n{dep_context}\n\n"
            "Instructions:\n"
            "- Produce a single merged file combining both versions.\n"
            "- Resolve conflicts by taking the most complete/correct implementation.\n"
            "- Do NOT add conflict markers (<<<<, ====, >>>>) in the output.\n"
            "- Preserve all unique code from both versions.\n"
            "- Ensure the merged file is syntactically correct.\n"
            "- Produce merged content then the dependency report.\n"
        )

    raw = _gemini_call(api_key, system_prompt, user_prompt, max_tokens=8192)

    # Parse response
    sep = "===DEPENDENCY_REPORT==="
    if sep in raw:
        parts = raw.split(sep, 1)
        merged_content    = parts[0].strip()
        dependency_report = parts[1].strip()
    else:
        merged_content    = raw.strip()
        dependency_report = "(Gemini did not return a separate dependency report)"

    # Strip markdown code fences if Gemini added them
    for fence in (f"```{lang.lower()}", f"```{ext.lstrip('.')}", "```"):
        if merged_content.startswith(fence):
            merged_content = merged_content[len(fence):].lstrip()
            if merged_content.endswith("```"):
                merged_content = merged_content[:-3].rstrip()
            break

    warnings = [
        line.strip("- •\t ")
        for line in dependency_report.splitlines()
        if any(w in line.lower() for w in ("warn", "break", "conflict", "caution", "risk", "alert"))
    ]

    return merged_content, dependency_report, warnings
