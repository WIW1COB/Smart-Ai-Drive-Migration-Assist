"""Excel utility functions for Migration Analysis Tool"""

import os
import csv
import datetime
from openpyxl import Workbook, load_workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.styles import numbers

from .file_utils import sanitize_for_excel


def create_overview_sheet(wb, results, folder1, folder2):
    """
    Create an overview sheet with summary statistics and comparison info.
    Contains detailed analysis similar to the original implementation.
    """
    ws = wb.active
    ws.title = "Overview"
    
    # Define styles
    title_font = Font(size=14, bold=True, color="1F4E78")
    subtitle_font = Font(size=11, bold=True, color="003366")
    normal_font = Font(size=10)
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    # Calculate statistics
    total_files = len(results)
    identical_count = sum(1 for r in results if r[4] == "Identical")
    different_count = sum(1 for r in results if r[4] == "Different")
    comments_only_count = sum(1 for r in results if r[4] == "Comments update only")
    only_folder1_count = sum(1 for r in results if r[4] == "Only in Platform")
    only_folder2_count = sum(1 for r in results if r[4] == "Only in Project")
    
    # Add title and basic info
    ws.merge_cells('A1:D1')
    cell = ws['A1']
    cell.value = "Migration Analysis Report - Overview"
    cell.font = title_font
    cell.alignment = Alignment(horizontal='center', vertical='center')
    ws.row_dimensions[1].height = 25
    
    # Comparison Information
    ws.append([])
    ws.append(["Comparison Information:"])
    ws['A3'].font = subtitle_font
    ws.append(["Platform (Baseline):", folder1])
    ws.append(["Project:", folder2])
    ws.append(["Generated:", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
    ws.append([])
    
    # Summary Statistics
    ws.append(["Summary Statistics:"])
    ws.append(["Identical Files:", identical_count])
    ws.append(["Different Files:", different_count])
    ws.append(["Comment Changes Only:", comments_only_count])
    ws.append(["Only in Platform:", only_folder1_count])
    ws.append(["Only in Project:", only_folder2_count])
    ws.append(["Total Files:", total_files])
    
    # Set column widths
    ws.column_dimensions['A'].width = 30
    ws.column_dimensions['B'].width = 40
    
    return ws


def write_excel_report(results, output_path, folder1_name, folder2_name):
    """Write comparison results to Excel file with formatting"""
    wb = Workbook()
    
    # Create overview sheet
    create_overview_sheet(wb, results, folder1_name, folder2_name)
    
    # Create detailed results sheet
    ws_details = wb.create_sheet(title="Detailed Results")
    
    # Header row
    headers = [
        "File Path",
        f"Lines in Platform ({folder1_name})",
        f"Lines in Project ({folder2_name})",
        "Line Comparison Status",
        "Status",
        "HTML Diff Report",
        "Purpose of Change",
        "ChangeSet & WorkItem from RTC History"
    ]
    ws_details.append(headers)
    
    # Style header row
    header_fill = PatternFill(start_color="003366", end_color="003366", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    
    for col_num, header in enumerate(headers, 1):
        cell = ws_details.cell(row=1, column=col_num)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    
    # Data rows with color coding
    for row_idx, row_data in enumerate(results, 2):
        ws_details.append([sanitize_for_excel(str(cell)) for cell in row_data])
        
        # Apply color based on status
        status = row_data[4] if len(row_data) > 4 else ""
        fill_color = None
        
        if status == "Identical":
            fill_color = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
        elif status == "Different":
            fill_color = PatternFill(start_color="FF9999", end_color="FF9999", fill_type="solid")
        elif status == "Comments update only":
            fill_color = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
        elif status == "Only in Platform":
            fill_color = PatternFill(start_color="9BC2E6", end_color="9BC2E6", fill_type="solid")
        elif status == "Only in Project":
            fill_color = PatternFill(start_color="F4B084", end_color="F4B084", fill_type="solid")
        
        if fill_color:
            for col_num in range(1, len(headers) + 1):
                ws_details.cell(row=row_idx, column=col_num).fill = fill_color
    
    # Set column widths
    ws_details.column_dimensions['A'].width = 50
    ws_details.column_dimensions['B'].width = 15
    ws_details.column_dimensions['C'].width = 15
    ws_details.column_dimensions['D'].width = 30
    ws_details.column_dimensions['E'].width = 20
    ws_details.column_dimensions['F'].width = 40
    ws_details.column_dimensions['G'].width = 50
    ws_details.column_dimensions['H'].width = 40
    
    # Save workbook
    wb.save(output_path)
    print(f"Excel report saved: {output_path}")
