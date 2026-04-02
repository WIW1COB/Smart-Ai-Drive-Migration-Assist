"""File utility functions for Migration Analysis Tool"""

import os
import re
import zipfile
import tempfile
import shutil


def sanitize_for_excel(text):
    """Remove illegal characters that Excel cannot handle"""
    if not text:
        return text
    # Remove control characters (0x00-0x1F except tab, newline, carriage return)
    # and other problematic characters
    illegal_chars = re.compile(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F-\x9F]')
    cleaned = illegal_chars.sub('', str(text))
    # Limit length to prevent Excel cell overflow
    if len(cleaned) > 32767:  # Excel cell character limit
        cleaned = cleaned[:32760] + "...[truncated]"
    return cleaned


def count_file_lines(file_path):
    """Count the number of lines in a file."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return sum(1 for _ in f)
    except Exception:
        try:
            with open(file_path, 'rb') as f:
                return sum(1 for _ in f)
        except:
            return 0


def read_file_as_text(file_path):
    """Read file content safely"""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.readlines()
    except Exception:
        with open(file_path, 'rb') as f:
            content = f.read().decode('latin-1', errors='ignore')
            return content.splitlines(keepends=True)


def extract_zip_to_temp(zip_path):
    """Extract ZIP file to temporary directory and return path"""
    try:
        temp_dir = tempfile.mkdtemp(prefix="migration_zip_")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        return temp_dir
    except Exception as e:
        print(f"Error extracting ZIP {zip_path}: {e}")
        return None


def prepare_folder_path(path):
    """Check if path is a ZIP file and extract it, otherwise return as-is
    Returns: (actual_path, is_temp_dir, original_path)
    """
    if not path:
        return None, False, None
    
    # Check if path is a ZIP file
    if os.path.isfile(path) and path.lower().endswith('.zip'):
        temp_dir = extract_zip_to_temp(path)
        if temp_dir:
            return temp_dir, True, path
        else:
            return None, False, path
    
    # Regular directory
    if os.path.isdir(path):
        return path, False, path
    
    return None, False, path


def remove_comments(text):
    """
    Remove C/C++ style comments (/* */ and //) from text.
    Returns text with comments removed.
    """
    # Remove multi-line comments /* ... */
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    # Remove single-line comments //
    text = re.sub(r'//.*?$', '', text, flags=re.MULTILINE)
    return text


def is_only_comment_change(text1_lines, text2_lines):
    """
    Check if the difference between two files is only in comments.
    Returns True if only comments changed, False otherwise.
    """
    # Join lines and remove comments from both
    text1 = ''.join(text1_lines)
    text2 = ''.join(text2_lines)
    
    text1_no_comments = remove_comments(text1)
    text2_no_comments = remove_comments(text2)
    
    # Normalize whitespace for comparison
    text1_normalized = ' '.join(text1_no_comments.split())
    text2_normalized = ' '.join(text2_no_comments.split())
    
    # If code without comments is the same, only comments changed
    return text1_normalized == text2_normalized


def get_line_comparison_status(lines1, lines2, files_identical, text1_lines=None, text2_lines=None):
    """
    Determine the status based on line counts and file content.
    Returns a descriptive status string.
    """
    if lines1 == 0 and lines2 == 0:
        return "Both files empty"
    elif lines1 == 0:
        return f"{lines2} lines added in project"
    elif lines2 == 0:
        return f"{lines1} lines removed in project"
    elif lines1 == lines2:
        if files_identical:
            return "No change (same lines, same content)"
        else:
            # Check if only comments changed
            if text1_lines and text2_lines and is_only_comment_change(text1_lines, text2_lines):
                return "Comments update only"
            else:
                return "Same line count, but modifications occurred"
    elif lines2 > lines1:
        diff = lines2 - lines1
        # Check if only comments changed despite line count difference
        if text1_lines and text2_lines and is_only_comment_change(text1_lines, text2_lines):
            return f"Comments update only ({diff} line(s) added in project)"
        else:
            return f"{diff} line(s) added in project"
    else:  # lines2 < lines1
        diff = lines1 - lines2
        # Check if only comments changed despite line count difference
        if text1_lines and text2_lines and is_only_comment_change(text1_lines, text2_lines):
            return f"Comments update only ({diff} line(s) removed in project)"
        else:
            return f"{diff} line(s) removed in project"
