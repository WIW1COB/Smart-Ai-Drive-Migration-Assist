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


def generate_snapshot_component_html(component_name, baseline1_uuid, baseline2_uuid,
                                     file_comparison, output_dir, snap1_label='Snapshot 1',
                                     snap2_label='Snapshot 2', file_contents=None,
                                     changeset_data=None, server_url=None):
    """
    Generate a self-contained HTML diff report for a single online-online snapshot
    component that shows as 'Different'.

    Args:
        component_name  : RTC component name
        baseline1_uuid  : Baseline UUID from snapshot 1
        baseline2_uuid  : Baseline UUID from snapshot 2
        file_comparison : dict with keys added/modified/removed/unchanged/details
                          (may be None if folder API returned no data)
        output_dir      : absolute path where the HTML file will be written
        snap1_label     : display label for snapshot 1
        snap2_label     : display label for snapshot 2
        file_contents   : optional dict {file_path: {'snap1': str, 'snap2': str}}
                          with pre-fetched text content for inline diff generation
        changeset_data  : optional dict with changeset/baseline info
        server_url      : optional RTC server URL for building hyperlinks

    Returns:
        Absolute path to the generated HTML file, or None on failure.
    """
    import html as html_mod
    import difflib
    from datetime import datetime

    os.makedirs(output_dir, exist_ok=True)

    safe_name = component_name.replace(os.sep, '_').replace('/', '_').replace('\\', '_')
    out_path = os.path.join(output_dir, f"{safe_name}_diff.html")

    fc = file_comparison or {}
    added     = fc.get('added',     0)
    modified  = fc.get('modified',  0)
    removed   = fc.get('removed',   0)
    unchanged = fc.get('unchanged', 0)
    details   = fc.get('details',   {})   # {file_path: 'added'|'modified'|'removed'|'unchanged'}
    has_file_data = bool(details) or (added + modified + removed + unchanged) > 0
    fc_map = file_contents or {}          # {file_path: {'snap1': str|None, 'snap2': str|None}}

    STATUS_COLOR = {'added': '#1a7f37', 'modified': '#9a6700', 'removed': '#cf222e', 'unchanged': '#57606a'}
    STATUS_BG    = {'added': '#dafbe1', 'modified': '#fff8c5', 'removed': '#ffebe9', 'unchanged': '#f6f8fa'}
    STATUS_ICON  = {'added': '＋', 'modified': '±', 'removed': '－', 'unchanged': '○'}

    def badge(label, count, color, bg):
        return (f'<span style="display:inline-block;padding:2px 10px;border-radius:12px;'
                f'background:{bg};color:{color};font-weight:600;font-size:13px;margin:0 4px;">'
                f'{label}: {count}</span>')

    # ── Build changeset section ────────────────────────────────────────────
    # changeset_data dict may contain:
    #   baseline1: {name, comment, author, timestamp, changeset_url}
    #   baseline2: {name, comment, author, timestamp, changeset_url}
    #   changesets: [{uuid, author, comment, timestamp}, ...]
    cd = changeset_data or {}
    b1info = cd.get('baseline1') or {}
    b2info = cd.get('baseline2') or {}
    cs_list = cd.get('changesets') or []

    def _make_baseline_link(uuid, label):
        if server_url and uuid and uuid != 'N/A':
            href = f'{server_url}/resource/itemOid/com.ibm.team.scm.Baseline/{uuid}'
            return (f'<a href="{html_mod.escape(href)}" target="_blank" '
                    f'style="font-family:monospace;font-size:12px;color:#0969da;">'
                    f'{html_mod.escape(uuid)}</a>')
        return f'<span style="font-family:monospace;font-size:12px;">{html_mod.escape(uuid)}</span>'

    def _info_rows(info_dict, uuid, snap_label):
        """Build HTML table rows for one baseline's metadata."""
        rows = ''
        rows += (
            f'<tr><td style="padding:6px 12px;width:180px;color:#57606a;font-weight:600;vertical-align:top;">'
            f'{html_mod.escape(snap_label)}<br><small style="font-weight:normal;">Baseline UUID</small></td>'
            f'<td style="padding:6px 12px;">{_make_baseline_link(uuid, snap_label)}</td></tr>'
        )
        if info_dict.get('name'):
            rows += (
                f'<tr style="background:#f6f8fa;">'
                f'<td style="padding:6px 12px;color:#57606a;font-weight:600;">Baseline Name</td>'
                f'<td style="padding:6px 12px;">{html_mod.escape(info_dict["name"])}</td></tr>'
            )
        if info_dict.get('comment'):
            rows += (
                f'<tr><td style="padding:6px 12px;color:#57606a;font-weight:600;">Comment</td>'
                f'<td style="padding:6px 12px;white-space:pre-wrap;">'
                f'{html_mod.escape(info_dict["comment"])}</td></tr>'
            )
        if info_dict.get('author'):
            rows += (
                f'<tr style="background:#f6f8fa;">'
                f'<td style="padding:6px 12px;color:#57606a;font-weight:600;">Author</td>'
                f'<td style="padding:6px 12px;">{html_mod.escape(str(info_dict["author"]))}</td></tr>'
            )
        if info_dict.get('timestamp'):
            rows += (
                f'<tr><td style="padding:6px 12px;color:#57606a;font-weight:600;">Timestamp</td>'
                f'<td style="padding:6px 12px;font-family:monospace;font-size:12px;">'
                f'{html_mod.escape(str(info_dict["timestamp"]))}</td></tr>'
            )
        return rows

    # Changeset list rows
    cs_table_html = ''
    if cs_list:
        cs_rows = ''
        for i, cs in enumerate(cs_list):
            bg = '#f6f8fa' if i % 2 else '#fff'
            cs_uuid   = str(cs.get('uuid', ''))
            author    = html_mod.escape(str(cs.get('author', '—')))
            comment   = html_mod.escape(str(cs.get('comment', '')))
            ts        = html_mod.escape(str(cs.get('timestamp', '')))

            # Build clickable changeset link
            if server_url and cs_uuid:
                cs_href = f'{server_url}/resource/itemOid/com.ibm.team.scm.ChangeSet/{cs_uuid}'
                cs_cell = (f'<a href="{html_mod.escape(cs_href)}" target="_blank" '
                           f'style="font-family:monospace;font-size:11px;color:#0969da;" '
                           f'title="Open changeset in EWM">{html_mod.escape(cs_uuid[:24])}</a>')
            else:
                cs_cell = f'<span style="font-family:monospace;font-size:11px;color:#57606a;">{html_mod.escape(cs_uuid[:24])}</span>'

            # Extract work-item/task numbers from comment (e.g. #12345, WI 12345, Task: 12345)
            import re as _re
            wi_matches = _re.findall(
                r'(?:Work\s*Item|Task|WI|Defect|Bug|Story)\s*[:#]?\s*(\d{3,7})'
                r'|#(\d{3,7})',
                str(cs.get('comment', '')), _re.IGNORECASE
            )
            wi_numbers = list(dict.fromkeys(
                n for pair in wi_matches for n in pair if n
            ))
            task_cell = ''
            if wi_numbers and server_url:
                links = []
                for wn in wi_numbers[:5]:
                    wi_href = f'{server_url}/resource/itemName/com.ibm.team.workitem.WorkItem/{wn}'
                    links.append(
                        f'<a href="{html_mod.escape(wi_href)}" target="_blank" '
                        f'style="color:#0969da;font-weight:600;font-size:12px;" '
                        f'title="Open work item {wn}">#{wn}</a>'
                    )
                task_cell = ' &nbsp;'.join(links)
            elif wi_numbers:
                task_cell = ' '.join(f'<span style="font-weight:600;">#{n}</span>' for n in wi_numbers[:5])
            else:
                task_cell = '<span style="color:#aaa;font-size:11px;">—</span>'

            cs_rows += (
                f'<tr style="background:{bg};">'
                f'<td style="padding:5px 10px;">{cs_cell}</td>'
                f'<td style="padding:5px 10px;font-size:12px;color:#0d1117;">{author}</td>'
                f'<td style="padding:5px 10px;font-size:12px;white-space:pre-wrap;">{comment}</td>'
                f'<td style="padding:5px 10px;">{task_cell}</td>'
                f'<td style="padding:5px 10px;font-size:11px;color:#57606a;white-space:nowrap;">{ts}</td>'
                f'</tr>'
            )
        cs_table_html = f'''
      <h3 style="margin-top:20px;">Changesets in {html_mod.escape(snap2_label)}</h3>
      <table style="width:100%;border-collapse:collapse;font-size:13px;">
        <thead>
          <tr style="background:#24292f;color:#fff;">
            <th style="padding:6px 10px;text-align:left;width:140px;">Changeset</th>
            <th style="padding:6px 10px;text-align:left;width:140px;">Author</th>
            <th style="padding:6px 10px;text-align:left;">Comment</th>
            <th style="padding:6px 10px;text-align:left;width:100px;">Task(s)</th>
            <th style="padding:6px 10px;text-align:left;width:150px;">Timestamp</th>
          </tr>
        </thead>
        <tbody>{cs_rows}</tbody>
      </table>'''

    changeset_section = f'''
    <div class="card">
      <h3>🔗 Changeset / Baseline Comparison</h3>
      <table class="main-table" style="width:100%;border-collapse:collapse;font-size:13px;">
        {_info_rows(b1info, baseline1_uuid, snap1_label)}
        <tr><td colspan="2" style="padding:2px;background:#d0d7de;"></td></tr>
        {_info_rows(b2info, baseline2_uuid, snap2_label)}
        <tr style="background:#fff3cd;">
          <td style="padding:6px 12px;color:#57606a;font-weight:600;">Change Direction</td>
          <td style="padding:6px 12px;color:#6e40c9;font-weight:700;">
            {html_mod.escape(snap1_label)} ➜ {html_mod.escape(snap2_label)}
          </td>
        </tr>
      </table>
      {cs_table_html}
    </div>'''

    # ── Binary content detection ───────────────────────────────────────────
    _BINARY_SIGNATURES = (b'PK', b'\x7fELF', b'\x89PNG', b'%PDF',
                          b'\xff\xd8', b'GIF8', b'BM', b'\xd0\xcf')

    def _is_binary_content(text):
        """Return True if the text string appears to be decoded binary data."""
        if not text:
            return False
        # High ratio of unicode replacement chars (\ufffd) → binary decoded as utf-8
        replacement_ratio = text.count('\ufffd') / max(len(text), 1)
        if replacement_ratio > 0.02:   # >2 % replacement chars → binary
            return True
        # Null bytes are a strong indicator of binary
        if '\x00' in text:
            return True
        # Low printable ratio
        sample = text[:2000]
        printable = sum(c.isprintable() or c in '\t\n\r' for c in sample)
        if len(sample) > 0 and (printable / len(sample)) < 0.70:
            return True
        # Known binary file signatures at start of content
        raw_start = text[:8].encode('utf-8', errors='replace')
        if any(raw_start.startswith(sig) for sig in _BINARY_SIGNATURES):
            return True
        return False

    # ── Build inline diff HTML for a pair of text contents ────────────────
    def _make_inline_diff(snap1_text, snap2_text, fpath, fstatus):
        """Generate a side-by-side diff table embedded in the HTML report."""
        try:
            # Detect binary content before attempting text diff
            s1_binary = _is_binary_content(snap1_text)
            s2_binary = _is_binary_content(snap2_text)
            if s1_binary or s2_binary:
                return (
                    '<div style="padding:12px 16px;background:#fff8c5;border-radius:4px;'
                    'color:#9a6700;font-size:13px;">'
                    '⚠️ <strong>Binary file</strong> — line-by-line diff is not available '
                    'for binary/non-text files. The file has changed (different baseline UUIDs) '
                    'but its content cannot be displayed as text.'
                    '</div>'
                )

            lines1 = (snap1_text or '').splitlines(keepends=True)
            lines2 = (snap2_text or '').splitlines(keepends=True)

            if not lines1 and not lines2:
                return '<p style="color:#57606a;padding:8px;">Empty file in both snapshots.</p>'

            from_label = f'{os.path.basename(fpath)} ← {snap1_label}'
            to_label   = f'{os.path.basename(fpath)} → {snap2_label}'

            differ = difflib.HtmlDiff(wrapcolumn=100, linejunk=None, charjunk=None)
            table_html = differ.make_table(
                lines1, lines2,
                fromdesc=from_label,
                todesc=to_label,
                context=True,
                numlines=3
            )
            return table_html
        except Exception as _ex:
            return f'<p style="color:#cf222e;">Could not generate diff: {_ex}</p>'

    # ── Folder-tree builder with per-file inline diff toggles ────────────
    def _build_path_tree(pairs):
        """Build a nested dict: folders have __children__, files have string status."""
        tree = {}
        for fpath, fstatus in pairs:
            parts = fpath.replace('\\', '/').split('/')
            node = tree
            for part in parts[:-1]:
                if part not in node:
                    node[part] = {'__children__': {}}
                node = node[part]['__children__']
            node[parts[-1]] = fstatus
        return tree

    def _count_changes_in_node(node):
        count = 0
        for v in node.values():
            if isinstance(v, dict):
                count += _count_changes_in_node(v.get('__children__', {}))
            elif v in ('modified', 'added', 'removed'):
                count += 1
        return count

    _diff_active = [False]  # mutable flag: True once any text diff is generated

    def _render_tree_html(node, path_prefix=''):
        parts_html = []
        folders = sorted((k, v) for k, v in node.items() if isinstance(v, dict))
        files   = sorted((k, v) for k, v in node.items() if isinstance(v, str))

        for fname, folder_node in folders:
            folder_path = f'{path_prefix}{fname}/'
            children    = folder_node.get('__children__', {})
            n_changes   = _count_changes_in_node(children)
            badge_html  = (
                f' <span style="background:#cf222e;color:#fff;font-size:10px;'
                f'padding:1px 7px;border-radius:10px;vertical-align:middle;'
                f'font-weight:600;">{n_changes} change{"s" if n_changes != 1 else ""}</span>'
            ) if n_changes else ''
            child_html  = _render_tree_html(children, folder_path)
            parts_html.append(
                f'<details class="rtc-folder" open>'
                f'<summary class="rtc-folder-sum">'
                f'<span style="color:#0550ae;font-weight:600;">📁 {html_mod.escape(fname)}</span>'
                f'{badge_html}</summary>'
                f'<div class="rtc-folder-body">{child_html}</div>'
                f'</details>'
            )

        for fname, fstatus in files:
            full_path = f'{path_prefix}{fname}'
            color     = STATUS_COLOR.get(fstatus, '#57606a')
            bg_row    = STATUS_BG.get(fstatus, 'transparent') if fstatus != 'unchanged' else 'transparent'
            icon      = STATUS_ICON.get(fstatus, '○')
            esc_name  = html_mod.escape(fname)

            content_pair = fc_map.get(full_path) or {}
            snap1_text   = content_pair.get('snap1')
            snap2_text   = content_pair.get('snap2')
            is_binary    = _is_binary_content(snap1_text) or _is_binary_content(snap2_text)
            has_diff     = (fstatus in ('modified', 'added', 'removed')
                            and not is_binary
                            and (snap1_text is not None or snap2_text is not None))

            extra_badge = ''
            diff_toggle = ''
            if fstatus in ('modified', 'added', 'removed'):
                if has_diff:
                    _diff_active[0] = True
                    diff_table = _make_inline_diff(snap1_text, snap2_text, full_path, fstatus)
                    s1_display = html_mod.escape(b1info.get('name') or snap1_label)
                    s2_display = html_mod.escape(b2info.get('name') or snap2_label)
                    diff_toggle = (
                        f'<details class="file-diff-details">'
                        f'<summary class="view-diff-btn" style="background:{color};">'
                        f'▶ View Diff</summary>'
                        f'<div class="diff-panel">'
                        f'<div class="diff-snap-bar">'
                        f'<span>&#8592; {s1_display}</span>'
                        f'<span>{s2_display} &#8594;</span>'
                        f'</div>{diff_table}</div></details>'
                    )
                elif is_binary:
                    extra_badge = '<span class="file-badge file-badge-bin">⊘ binary</span>'
                else:
                    extra_badge = '<span class="file-badge file-badge-nc">no content</span>'

            parts_html.append(
                f'<div class="rtc-file" style="background:{bg_row};">'
                f'<span class="file-icon" style="color:{color};">{icon}</span>'
                f'<span class="file-name" style="color:{color if fstatus != "unchanged" else "#57606a"};">'
                f'{esc_name}</span>'
                f'<span class="file-status" style="color:{color};">{fstatus.capitalize()}</span>'
                f'{extra_badge}{diff_toggle}'
                f'</div>'
            )

        return ''.join(parts_html)

    # ── Build the file tree / file table ──────────────────────────────────
    file_table = ''
    if details:
        sorted_all = sorted(details.items(), key=lambda x: (
            x[1] == 'unchanged', x[1] != 'modified', x[0]
        ))
        tree     = _build_path_tree(sorted_all)
        rendered = _render_tree_html(tree)
        file_table = (
            '<h3 style="margin-top:28px;">File-Level Changes</h3>'
            '<div class="rtc-tree">' + rendered + '</div>'
        )
    elif has_file_data:
        file_table = '<p style="color:#57606a;margin-top:20px;">File counts available but path details not returned.</p>'
    else:
        file_table = '''
        <div style="margin-top:24px;padding:16px 20px;background:#fff8c5;border:1px solid #d4a72c;
                    border-radius:6px;color:#9a6700;">
          <strong>ℹ File-level detail not available</strong><br>
          The RTC folder/file listing API did not return file data for this component.<br>
          The component is marked <strong>Different</strong> because the two baselines have
          different UUIDs — baselines are immutable, so a different UUID means different content.
        </div>'''

    # Diffs are now embedded per-file inside the tree; no separate diff card needed
    inline_diff_card = ''

    # ── CSS (tree styles + difflib when diffs are present) ────────────────
    difflib_css = '''
    .rtc-tree { border:1px solid #d0d7de; border-radius:6px; overflow:hidden; background:#fff; margin-top:10px; }
    .rtc-folder { border-bottom:1px solid #eaecef; }
    .rtc-folder-sum { cursor:pointer; padding:6px 10px; background:#f6f8fa;
                      display:block; list-style:none; font-size:13px; }
    .rtc-folder-sum::-webkit-details-marker { display:none; }
    .rtc-folder-sum:hover { background:#eaf3fb; }
    .rtc-folder-body { padding-left:18px; border-left:2px solid #d0d7de; margin-left:10px; }
    .rtc-file { display:flex; align-items:flex-start; flex-wrap:wrap;
                padding:4px 10px 4px 10px; border-bottom:1px solid #f0f0f0;
                font-family:"Segoe UI",Arial,sans-serif; }
    .rtc-file:last-child { border-bottom:none; }
    .file-icon { font-size:14px; margin-right:6px; flex-shrink:0; padding-top:1px; }
    .file-name { font-family:Consolas,"Courier New",monospace; font-size:12px;
                 flex:1; word-break:break-all; min-width:100px; }
    .file-status { font-size:11px; font-weight:600; margin-left:8px; white-space:nowrap; }
    .file-badge { font-size:10px; margin-left:6px; padding:1px 7px; border-radius:10px; }
    .file-badge-bin { background:#fff8c5; color:#9a6700; }
    .file-badge-nc  { background:#f6f8fa; color:#aaa; }
    .file-diff-details { width:100%; margin-top:5px; flex-basis:100%; }
    .view-diff-btn { cursor:pointer; display:inline-block; padding:2px 10px;
                     border-radius:4px; color:#fff; font-size:11px; font-weight:600;
                     margin-left:8px; user-select:none; list-style:none; }
    .view-diff-btn::-webkit-details-marker { display:none; }
    .diff-panel { margin-top:4px; overflow-x:auto; border:1px solid #d0d7de; border-radius:4px; }
    .diff-snap-bar { display:flex; justify-content:space-between; background:#003366;
                     color:#fff; font-size:11px; padding:5px 12px; font-family:monospace; }''' + ('''
    .diff_header { background-color:#F8B862; }
    td.diff_header { text-align:right; }
    .diff_next { background-color:#c0c0c0; }
    .diff_add { background-color:#aaffaa; }
    .diff_chg { background-color:#ffff77; }
    .diff_sub { background-color:#ffaaaa; }
    table.diff { font-family:Consolas,"Courier New",monospace; font-size:12px;
                 border-collapse:collapse; width:100%; }
    table.diff td { padding:2px 6px; white-space:pre-wrap; word-break:break-all; }
    table.diff th { padding:4px 6px; background:#24292f; color:#fff; font-weight:600; }
    table.diff td:first-child, table.diff td:nth-child(3) {
        color:#57606a; font-size:11px; min-width:36px; text-align:right;
        padding-right:8px; user-select:none; }''' if _diff_active[0] else '')

    html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Diff: {html_mod.escape(component_name)}</title>
  <style>
    body {{ font-family: "Segoe UI", Arial, sans-serif; margin: 0; padding: 0; background: #f6f8fa; color: #24292f; }}
    .header {{ background: #003366; color: #fff; padding: 20px 32px; }}
    .header h1 {{ margin: 0 0 4px; font-size: 20px; }}
    .header .sub {{ font-size: 13px; opacity: .75; }}
    .badge-row {{ padding: 4px 0 0; }}
    .content {{ padding: 28px 32px; max-width: 1400px; margin: auto; }}
    .card {{ background: #fff; border: 1px solid #d0d7de; border-radius: 8px; padding: 20px 24px; margin-bottom: 20px; }}
    table.main-table {{ border: 1px solid #d0d7de; }}
    table.main-table th, table.main-table td {{ border-bottom: 1px solid #d0d7de; }}
    h3 {{ color: #0d1117; font-size: 15px; border-bottom: 1px solid #d0d7de; padding-bottom: 6px; margin-top:0; }}
    .uuid {{ font-family: monospace; font-size: 12px; background: #f6f8fa; padding: 2px 6px;
             border-radius: 4px; border: 1px solid #d0d7de; }}
    .status-diff {{ color: #cf222e; font-weight: 700; font-size: 15px; }}
    {difflib_css}
  </style>
</head>
<body>
  <div class="header">
    <h1>🔍 Component Diff Report</h1>
    <div class="sub">{html_mod.escape(component_name)}</div>
    <div class="sub">Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>
  </div>
  <div class="content">
    <div class="card">
      <h3>Comparison Summary</h3>
      <table class="main-table" style="width:100%;border-collapse:collapse;font-size:13px;">
        <tr><td style="padding:8px 12px;width:160px;color:#57606a;font-weight:600;">Status</td>
            <td style="padding:8px 12px;" class="status-diff">● Different</td></tr>
        <tr style="background:#f6f8fa;">
          <td style="padding:8px 12px;color:#57606a;font-weight:600;">Component</td>
          <td style="padding:8px 12px;font-family:monospace;">{html_mod.escape(component_name)}</td></tr>
        <tr>
          <td style="padding:8px 12px;color:#57606a;font-weight:600;">{html_mod.escape(snap1_label)}</td>
          <td style="padding:8px 12px;">
            <strong style="font-size:13px;">{html_mod.escape(b1info.get('name') or baseline1_uuid)}</strong>
            <br><span class="uuid" style="font-size:11px;color:#57606a;">{html_mod.escape(baseline1_uuid)}</span>
          </td></tr>
        <tr style="background:#f6f8fa;">
          <td style="padding:8px 12px;color:#57606a;font-weight:600;">{html_mod.escape(snap2_label)}</td>
          <td style="padding:8px 12px;">
            <strong style="font-size:13px;">{html_mod.escape(b2info.get('name') or baseline2_uuid)}</strong>
            <br><span class="uuid" style="font-size:11px;color:#57606a;">{html_mod.escape(baseline2_uuid)}</span>
          </td></tr>
      </table>
    </div>

    {changeset_section}

    <div class="card">
      <h3>File Change Counts</h3>
      <div class="badge-row">
        {badge("Modified",  modified,  STATUS_COLOR["modified"],  STATUS_BG["modified"])}
        {badge("Added",     added,     STATUS_COLOR["added"],     STATUS_BG["added"])}
        {badge("Removed",   removed,   STATUS_COLOR["removed"],   STATUS_BG["removed"])}
        {badge("Unchanged", unchanged, STATUS_COLOR["unchanged"], STATUS_BG["unchanged"])}
      </div>
      {file_table}
    </div>

    {inline_diff_card}

  </div>
</body>
</html>'''

    try:
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        return out_path
    except Exception:
        return None
