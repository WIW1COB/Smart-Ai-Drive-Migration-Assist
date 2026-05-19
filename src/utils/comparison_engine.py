"""
Comparison Engine - Core folder/file comparison logic
Extracted from test.py and refactored for modular architecture
"""
 
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import csv
 
from .file_utils import (
    count_file_lines, read_file_as_text, prepare_folder_path,
    sanitize_for_excel, remove_comments, is_only_comment_change
)
from .diff_utils import generate_html_diff, generate_purpose_of_change
from .excel_utils import write_excel_report
from src.config import settings
 
 
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
            return f"Identical ({lines1} lines)"
        else:
            # Check if only comments changed
            if text1_lines and text2_lines and is_only_comment_change(text1_lines, text2_lines):
                return f"Only comments changed ({lines1} lines)"
            return f"Modified ({lines1} lines)"
    elif lines2 > lines1:
        diff = lines2 - lines1
        # Check if only comments changed despite line count difference
        if text1_lines and text2_lines and is_only_comment_change(text1_lines, text2_lines):
            return f"Only comments changed ({lines1} → {lines2} lines, +{diff})"
        else:
            return f"Modified ({lines1} → {lines2} lines, +{diff} lines added)"
    else:  # lines2 < lines1
        diff = lines1 - lines2
        # Check if only comments changed despite line count difference
        if text1_lines and text2_lines and is_only_comment_change(text1_lines, text2_lines):
            return f"Only comments changed ({lines1} → {lines2} lines, -{diff})"
        else:
            return f"Modified ({lines1} → {lines2} lines, -{diff} lines removed)"
 
 
def process_file_comparison(args):
    """
    Process a single file comparison - designed for parallel execution
   
    Args:
        args: Tuple of (rel_path, path1, path2, output_dir, is_custom_mapping, rtc_info)
       
    Returns:
        List containing comparison result: [File Path, Lines1, Lines2, Line Status, Status, HTML Link, Purpose, Changeset]
    """
    rel_path, path1, path2, output_dir, is_custom_mapping, rtc_info = args
   
    try:
        # Determine file existence and status
        exists1 = path1 and os.path.isfile(path1)
        exists2 = path2 and os.path.isfile(path2)
       
        if not exists1 and not exists2:
            return [rel_path, 0, 0, "File not found", "Error", "", "", ""]
       
        # Count lines
        lines1 = count_file_lines(path1) if exists1 else 0
        lines2 = count_file_lines(path2) if exists2 else 0
       
        # Determine status
        if exists1 and exists2:
            # Both files exist - compare them
            text1 = read_file_as_text(path1)
            text2 = read_file_as_text(path2)
           
            files_identical = (text1 == text2)
           
            if files_identical:
                status = "Identical"
            else:
                # Check if only comments changed
                if is_only_comment_change(text1, text2):
                    status = "Comments update only"
                else:
                    status = "Different"
           
            line_status = get_line_comparison_status(lines1, lines2, files_identical, text1, text2)
           
            # Generate HTML diff for non-identical files
            if not files_identical:
                try:
                    html_path, _, _ = generate_html_diff(path1, path2, rel_path, output_dir)
                    html_link = html_path  # Store full path for hyperlink
                except Exception as e:
                    html_link = f"Error: {str(e)}"
               
                # Generate purpose of change
                try:
                    purpose = generate_purpose_of_change(text1, text2)
                except Exception as e:
                    purpose = f"Error: {str(e)}"
            else:
                html_link = "N/A (Identical)"
                purpose = "No changes"
       
        elif exists1 and not exists2:
            # Only in folder 1
            status = "Only in Platform"
            line_status = f"{lines1} lines (only in platform)"
            html_link = "N/A"
            purpose = "File removed in project or not migrated"
       
        elif not exists1 and exists2:
            # Only in folder 2
            status = "Only in Project"
            line_status = f"{lines2} lines (only in project)"
            html_link = "N/A"
            purpose = "New file added in project"
       
        # RTC Integration - fetch changesets if enabled
        changeset_info = ""
        if rtc_info and rtc_info.get('enabled') and exists2:
            try:
                from src.rtc.changeset import get_workitems_for_file
               
                changeset_data = get_workitems_for_file(
                    path2,
                    rtc_info.get('repository_path'),
                    rtc_info.get('username'),
                    rtc_info.get('password'),
                    rtc_info.get('workspace_name'),
                    rtc_info.get('stream_name')
                )
               
                if changeset_data:
                    changeset_url = changeset_data.get('changeset_url', '')
                    workitems = changeset_data.get('workitem_ids', [])
                    changeset_info = f"Changeset: {changeset_url} | WorkItems: {', '.join(workitems)}"
            except Exception as e:
                changeset_info = f"RTC Error: {str(e)}"
       
        # Return result row
        return [
            rel_path,
            lines1,
            lines2,
            line_status,
            status,
            html_link,
            purpose,
            changeset_info
        ]
   
    except Exception as e:
        print(f"Error comparing {rel_path}: {e}")
        return [
            rel_path,
            0,
            0,
            f"Error: {str(e)}",
            "Error",
            "",
            "",
            ""
        ]
 
 
def compare_folders(folder1, folder2, progress_callback=None, custom_mappings=None, rtc_info=None, output_dir=None, report_name=None):
    """
    Compare two folders and generate comparison reports.
   
    Args:
        folder1 (str): Path to first folder (Platform/Baseline)
        folder2 (str): Path to second folder (Project/Target)
        progress_callback (callable, optional): Callback(current, total, message) for progress updates
        custom_mappings (dict, optional): Custom file mappings {file1_rel_path: file2_rel_path}
        rtc_info (dict, optional): RTC integration info with keys: enabled, username, password, etc.
        output_dir (str, optional): Directory to write CSV/Excel/HTML reports. Defaults to Migration_Analysis_Reports/.
        report_name (str, optional): Base filename (without extension) for CSV/Excel reports.
                                     Defaults to 'Migration_Analysis_Report'.
       
    Returns:
        dict: Result dictionary with keys:
            - 'success': bool
            - 'results': list of comparison results
            - 'report_paths': dict with 'csv' and 'excel' paths
            - 'files1': dict of files in folder1
            - 'files2': dict of files in folder2
            - 'output_dir': path to output directory
    """
    # Create output directory
    if not output_dir:
        output_dir = os.path.join(os.getcwd(), "Migration_Analysis_Reports")
    os.makedirs(output_dir, exist_ok=True)

    base_name = report_name if report_name else "Migration_Analysis_Report"
    csv_report_path = os.path.join(output_dir, f"{base_name}.csv")
    excel_report_path = os.path.join(output_dir, f"{base_name}.xlsx")
   
    # Handle ZIP folder inputs - extract if needed
    temp_dirs_to_cleanup = []
    original_folder1 = folder1
    original_folder2 = folder2
   
    if progress_callback:
        progress_callback(0, 100, "Preparing folders (extracting if ZIP)...")
   
    folder1_actual, is_temp1, orig1 = prepare_folder_path(folder1)
    folder2_actual, is_temp2, orig2 = prepare_folder_path(folder2)
   
    if is_temp1:
        temp_dirs_to_cleanup.append(folder1_actual)
   
    if is_temp2:
        temp_dirs_to_cleanup.append(folder2_actual)
   
    if not folder1_actual or not folder2_actual:
        return {
            'success': False,
            'error': 'Invalid folder paths',
            'temp_dirs': temp_dirs_to_cleanup
        }
   
    # Use actual folders for comparison
    folder1 = folder1_actual
    folder2 = folder2_actual
   
    # Collect all files from both folders
    files1 = {}
    files2 = {}
   
    for dp, _, fnames in os.walk(folder1):
        for f in fnames:
            rel_path = os.path.relpath(os.path.join(dp, f), folder1)
            files1[rel_path] = os.path.join(dp, f)
   
    for dp, _, fnames in os.walk(folder2):
        for f in fnames:
            rel_path = os.path.relpath(os.path.join(dp, f), folder2)
            files2[rel_path] = os.path.join(dp, f)
   
    all_files = sorted(set(files1.keys()) | set(files2.keys()))
   
    # Track which files have been processed via custom mappings
    processed_files = set()
   
    # Prepare comparison tasks
    comparison_tasks = []
   
    # Add custom mappings first
    if custom_mappings:
        for file1_rel, file2_rel in custom_mappings.items():
            path1 = files1.get(file1_rel)
            path2 = files2.get(file2_rel)
            comparison_tasks.append((file2_rel, path1, path2, output_dir, True, rtc_info))
            processed_files.add(file1_rel)
            processed_files.add(file2_rel)
   
    # Add regular file comparisons
    for rel_path in all_files:
        if rel_path not in processed_files:
            path1 = files1.get(rel_path)
            path2 = files2.get(rel_path)
            comparison_tasks.append((rel_path, path1, path2, output_dir, False, rtc_info))
   
    total_files = len(comparison_tasks)
    completed = 0
    results = []
   
    # Use ThreadPoolExecutor for parallel processing
    # File comparison is I/O-bound, so use MAX_WORKERS directly (no cpu_count cap).
    max_workers = max(1, getattr(settings, 'MAX_WORKERS', 8))
   
    if progress_callback:
        progress_callback(0, total_files, f"Starting parallel comparison with {max_workers} workers...")
   
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all comparison tasks
        future_to_task = {
            executor.submit(process_file_comparison, task): task
            for task in comparison_tasks
        }
       
        # Collect results as they complete
        for future in as_completed(future_to_task):
            try:
                result = future.result()
                results.append(result)
                completed += 1
               
                # Update progress
                if progress_callback:
                    percentage = int((completed / total_files) * 100)
                    progress_callback(
                        completed,
                        total_files,
                        f"Processing ({completed}/{total_files}): {result[0]}"
                    )
            except Exception as e:
                print(f"Error processing file: {e}")
                completed += 1
   
    # Sort results by file path
    results.sort(key=lambda x: x[0])
   
    # Use original folder names in reports
    folder1_display = original_folder1
    folder2_display = original_folder2
   
    # Generate CSV report
    if progress_callback:
        progress_callback(total_files, total_files, "Generating CSV report...")
   
    try:
        with open(csv_report_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            # Write headers
            writer.writerow([
                "File Path",
                f"Lines in Platform ({folder1_display})",
                f"Lines in Project ({folder2_display})",
                "Line Comparison Status",
                "Status",
                "HTML Diff Report",
                "Purpose of Change",
                "ChangeSet & WorkItem from RTC"
            ])
            # Write data
            for row in results:
                writer.writerow([sanitize_for_excel(str(cell)) for cell in row])
    except Exception as e:
        print(f"Error writing CSV: {e}")
   
    # Generate Excel report
    if progress_callback:
        progress_callback(total_files, total_files, "Generating Excel report...")
   
    try:
        write_excel_report(results, excel_report_path, folder1_display, folder2_display)
    except Exception as e:
        print(f"Error writing Excel: {e}")
   
    if progress_callback:
        progress_callback(total_files, total_files, "✅ Comparison complete!")
   
    return {
        'success': True,
        'results': results,
        'report_paths': {
            'csv': csv_report_path,
            'excel': excel_report_path,
            'output_dir': output_dir
        },
        'files1': files1,
        'files2': files2,
        'folder1': folder1,
        'folder2': folder2,
        'folder1_display': folder1_display,
        'folder2_display': folder2_display,
        'temp_dirs': temp_dirs_to_cleanup
    }
 
 
def cleanup_temp_dirs(temp_dirs):
    """Clean up temporary directories created during ZIP extraction"""
    import shutil
    for temp_dir in temp_dirs:
        try:
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                print(f"Cleaned up temp directory: {temp_dir}")
        except Exception as e:
            print(f"Error cleaning up {temp_dir}: {e}")