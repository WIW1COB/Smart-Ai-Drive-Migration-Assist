"""Diff generation utilities for Migration Analysis Tool"""

import os
import difflib
from .file_utils import read_file_as_text
from .xml_utils import normalize_xml


def generate_html_diff(file1, file2, file_name, output_dir):
    """Generate HTML diff report for two files"""
    # Check if files are XML
    is_xml = file1.lower().endswith('.xml') and file2.lower().endswith('.xml')
    
    if is_xml:
        text1 = normalize_xml(file1)
        text2 = normalize_xml(file2)
    else:
        text1 = read_file_as_text(file1)
        text2 = read_file_as_text(file2)

    differ = difflib.HtmlDiff(wrapcolumn=120)
    html_diff = differ.make_file(
        text1, text2,
        fromdesc=f"{file1} (Migration Analysis)",
        todesc=f"{file2} (Migration Analysis)"
    )

    output_path = os.path.join(output_dir, f"{file_name.replace(os.sep,'_')}_diff.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_diff)
    return output_path, text1, text2


def generate_purpose_of_change(text1, text2):
    """Generate summary of changes between two files"""
    diff = list(difflib.ndiff(text1, text2))
    comments = []
    for line in diff:
        if line.startswith("+ "):
            line_text = line[2:].strip()
            # Only include printable text, skip binary/control characters
            if line_text and len(line_text) < 200:  # Skip very long lines
                # Check if line is mostly printable
                printable_ratio = sum(c.isprintable() or c in '\t\n\r' for c in line_text) / len(line_text)
                if printable_ratio > 0.7:  # At least 70% printable characters
                    comments.append(f"Added: {line_text}")
        elif line.startswith("- "):
            line_text = line[2:].strip()
            if line_text and len(line_text) < 200:
                printable_ratio = sum(c.isprintable() or c in '\t\n\r' for c in line_text) / len(line_text)
                if printable_ratio > 0.7:
                    comments.append(f"Removed: {line_text}")
    
    if not comments:
        return "No change detected."
    if len(comments) > 10:
        comments = comments[:10]
        comments.append("... (more differences omitted)")
    return " | ".join(comments)
