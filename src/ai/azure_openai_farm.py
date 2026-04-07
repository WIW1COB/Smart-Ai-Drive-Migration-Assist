"""Azure OpenAI (Farm) integration for AI Smart Merge.

Uses Bosch AOAI Farm endpoint via the OpenAI Python SDK's `AzureOpenAI` client.
"""

from __future__ import annotations

import os
from typing import Dict, List, Tuple, Optional

from src.config import settings


_DEP_SCAN_EXTS = {
    ".c", ".h", ".cpp", ".hpp", ".cc", ".cxx", ".hxx",
    ".cs", ".py", ".java",
    ".xml", ".arxml", ".cfg", ".mk", ".mak",
    ".json", ".yaml", ".yml", ".properties",
}


def _read_file_safe(path: str, max_chars: int = 8000) -> str:
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


def _scan_related_files(fname: str, target_files_dict: Dict[str, str], max_files: int = 8):
    """Find files in the TARGET folder that reference fname (include/import heuristics)."""
    base = os.path.basename(fname)
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


def _get_aoai_client(subscription_key: Optional[str] = None):
    """Create AzureOpenAI client using settings/env."""
    api_key = (subscription_key or settings.AOAI_FARM_SUBSCRIPTION_KEY or "").strip()
    if not api_key or api_key.lower() == "none":
        raise ValueError(
            "Azure OpenAI subscription key not configured.\n\n"
            "Set environment variable: GENAIPLATFORM_FARM_SUBSCRIPTION_KEY"
        )

    try:
        from openai import AzureOpenAI  # type: ignore
    except Exception as e:
        raise ImportError(
            "openai package not available. Ensure requirements are installed (openai>=1.0.0)."
        ) from e

    return AzureOpenAI(
        api_key=api_key,
        azure_endpoint=settings.AOAI_FARM_ENDPOINT,
        azure_deployment=settings.AOAI_FARM_DEPLOYMENT,
        api_version=settings.AOAI_FARM_API_VERSION,
    )


def _chat_completion(system_prompt: str, user_prompt: str, subscription_key: Optional[str] = None) -> str:
    """Call AOAI chat completion and return message content."""
    client = _get_aoai_client(subscription_key=subscription_key)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # In Azure OpenAI, many setups expect deployment name in `model`.
    # Your provided snippet passes a base model name; we try both for robustness.
    model_candidates = []
    if getattr(settings, "AOAI_FARM_MODEL", ""):
        model_candidates.append(settings.AOAI_FARM_MODEL)
    model_candidates.append(settings.AOAI_FARM_DEPLOYMENT)

    last_exc: Optional[Exception] = None
    for model in model_candidates:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.2,
                max_tokens=8192,
                timeout=120,
            )
            content = resp.choices[0].message.content
            return (content or "").strip()
        except Exception as e:
            last_exc = e
            continue

    raise ValueError(f"Azure OpenAI chat completion failed: {last_exc}")


def ai_merge_with_azure_openai(
    path1: str,
    path2: str,
    status: str,
    rel_path: str,
    files1: Dict[str, str],
    files2: Dict[str, str],
    folder1_root: str,
    folder2_root: str,
    subscription_key: Optional[str] = None,
) -> Tuple[str, str, List[str]]:
    """AI Smart Merge using Azure OpenAI (Farm).

    Returns: (merged_content, dependency_report, warnings)
    """

    fname = os.path.basename(path1 or path2 or rel_path)
    ext = os.path.splitext(fname)[1].lower()
    lang = {
        ".c": "C", ".h": "C", ".cpp": "C++", ".hpp": "C++",
        ".cs": "C#", ".py": "Python", ".java": "Java",
        ".xml": "XML", ".arxml": "ARXML", ".cfg": "Config",
        ".mk": "Makefile", ".mak": "Makefile",
        ".json": "JSON", ".yaml": "YAML", ".yml": "YAML",
        ".properties": "Properties",
    }.get(ext, "text")

    content1 = _read_file_safe(path1)
    content2 = _read_file_safe(path2)

    # Dependency scan on the TARGET side (heuristic, file-level)
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

    system_prompt = (
        "You are an expert software engineer specialising in code migration and merging. "
        "Your task is to produce a SINGLE merged file that:\n"
        "1. Combines both versions without losing any logic.\n"
        "2. Resolves all conflicts intelligently.\n"
        "3. Does NOT break any of the dependent files shown (preserve signatures, types, macros).\n"
        "4. Keeps all copyright headers, version comments, and important annotations.\n"
        "5. Preserves the original language syntax and style.\n\n"
        "OUTPUT FORMAT - return EXACTLY two sections separated by ===DEPENDENCY_REPORT===\n"
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

    raw = _chat_completion(system_prompt, user_prompt, subscription_key=subscription_key)

    sep = "===DEPENDENCY_REPORT==="
    if sep in raw:
        merged_content, dependency_report = raw.split(sep, 1)
        merged_content = merged_content.strip()
        dependency_report = dependency_report.strip()
    else:
        merged_content = raw.strip()
        dependency_report = "(Model did not return a separate dependency report)"

    # Strip markdown fences if any
    if merged_content.startswith("```"):
        merged_content = merged_content.split("\n", 1)[-1]
        if merged_content.endswith("```"):
            merged_content = merged_content[:-3].rstrip()

    warnings = [
        line.strip("- •\t ")
        for line in dependency_report.splitlines()
        if any(w in line.lower() for w in ("warn", "break", "conflict", "caution", "risk", "alert"))
    ]

    return merged_content, dependency_report, warnings
