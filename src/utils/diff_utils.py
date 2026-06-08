"""Diff generation utilities for Migration Analysis Tool"""

import os
import difflib
import html as _html
from .file_utils import read_file_as_text
from .xml_utils import normalize_xml

# Files larger than this combined line count use a fast unified-diff fallback
# instead of the O(n²) HtmlDiff / ndiff algorithms.
MAX_DIFF_LINES = 5000


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

    output_path = os.path.join(output_dir, f"{file_name.replace(os.sep,'_')}_diff.html")

    # For large files skip the O(n²) HtmlDiff and emit a lightweight unified-diff page.
    if len(text1) + len(text2) > MAX_DIFF_LINES:
        udiff = list(difflib.unified_diff(text1, text2, fromfile=file1, tofile=file2, n=3))
        rows = []
        for line in udiff:
            esc = _html.escape(line.rstrip('\n'))
            if line.startswith('+') and not line.startswith('+++'):
                rows.append(f'<tr style="background:#e6ffed"><td><pre>{esc}</pre></td></tr>')
            elif line.startswith('-') and not line.startswith('---'):
                rows.append(f'<tr style="background:#ffeef0"><td><pre>{esc}</pre></td></tr>')
            elif line.startswith('@'):
                rows.append(f'<tr style="background:#f1f8ff;color:#005cc5"><td><pre>{esc}</pre></td></tr>')
            else:
                rows.append(f'<tr><td><pre>{esc}</pre></td></tr>')
        page = (
            '<!DOCTYPE html><html><head><meta charset="utf-8">'
            f'<title>Diff: {_html.escape(file_name)}</title>'
            '<style>body{font-family:monospace;font-size:12px}'
            'table{border-collapse:collapse;width:100%}'
            'td{padding:1px 4px;vertical-align:top}pre{margin:0}</style>'
            '</head><body>'
            f'<h3>Unified Diff &mdash; {_html.escape(file_name)}</h3>'
            f'<p>File&nbsp;1:&nbsp;{len(text1)}&nbsp;lines&nbsp;&nbsp;'
            f'File&nbsp;2:&nbsp;{len(text2)}&nbsp;lines'
            f'&nbsp;&nbsp;<em>(large file &mdash; side-by-side view skipped)</em></p>'
            f'<table>{chr(10).join(rows)}</table>'
            '</body></html>'
        )
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(page)
        return output_path, text1, text2

    differ = difflib.HtmlDiff(wrapcolumn=120)
    html_diff = differ.make_file(
        text1, text2,
        fromdesc=f"{file1} (Migration Analysis)",
        todesc=f"{file2} (Migration Analysis)"
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_diff)
    return output_path, text1, text2


def generate_purpose_of_change(text1, text2):
    """Generate summary of changes between two files"""
    # For large files avoid O(n²) ndiff and return a fast line-count summary instead.
    if len(text1) + len(text2) > MAX_DIFF_LINES:
        set1 = set(text1)
        set2 = set(text2)
        added_count = len(set2 - set1)
        removed_count = len(set1 - set2)
        return (f"Large file ({len(text1)} → {len(text2)} lines): "
                f"~{added_count} unique lines added, ~{removed_count} unique lines removed")
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
    STATUS_ICON  = {'added': '+', 'modified': '±', 'removed': '-', 'unchanged': '○'}

    def badge(label, count, color, bg):
        return (f'<span style="display:inline-block;padding:2px 10px;border-radius:12px;'
                f'background:{bg};color:{color};font-weight:600;font-size:13px;margin:0 4px;">'
                f'{label}: {count}</span>')

    # â”€â”€ Build changeset section â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

    # â”€â”€ Binary content detection â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

    # â”€â”€ Build inline diff HTML for a pair of text contents â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
                    'âš ï¸ <strong>Binary file</strong> — line-by-line diff is not available '
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

            # For pure add (snap1 empty) or pure remove (snap2 empty),
            # show a simpler full-content view rather than a confusing diff against empty
            if not lines1:
                body = ''.join(
                    f'<tr><td class="diff_add" colspan="4" style="padding:1px 6px;">'                    f'<code>{line.rstrip()}</code></td></tr>'
                    for line in lines2
                )
                return (
                    f'<table class="diff" style="width:100%">'                    f'<tr><th colspan="4" style="padding:4px 6px;text-align:left;">'                    f'&#43; New file — {html_mod.escape(to_label)}</th></tr>'
                    f'{body}</table>'
                )
            if not lines2:
                body = ''.join(
                    f'<tr><td class="diff_sub" colspan="4" style="padding:1px 6px;">'                    f'<code>{line.rstrip()}</code></td></tr>'
                    for line in lines1
                )
                return (
                    f'<table class="diff" style="width:100%">'                    f'<tr><th colspan="4" style="padding:4px 6px;text-align:left;">'                    f'&#8722; Deleted file — {html_mod.escape(from_label)}</th></tr>'
                    f'{body}</table>'
                )

            differ = difflib.HtmlDiff(wrapcolumn=100, linejunk=None, charjunk=None)
            table_html = differ.make_table(
                lines1, lines2,
                fromdesc=from_label,
                todesc=to_label,
                context=False
            )
            return table_html
        except Exception as _ex:
            return f'<p style="color:#cf222e;">Could not generate diff: {_ex}</p>'

    # â”€â”€ Folder-tree builder with per-file inline diff toggles â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
                    extra_badge = '<span class="file-badge file-badge-bin">âŠ˜ binary</span>'
                else:
                    extra_badge = '<span class="file-badge file-badge-nc">no content</span>'

            parts_html.append(
                f'<div class="rtc-file" data-status="{fstatus}" style="background:{bg_row};">'
                f'<span class="file-icon" style="color:{color};">{icon}</span>'
                f'<span class="file-name" style="color:{color if fstatus != "unchanged" else "#57606a"};">'
                f'{esc_name}</span>'
                f'<span class="file-status" style="color:{color};">{fstatus.capitalize()}</span>'
                f'{extra_badge}{diff_toggle}'
                f'</div>'
            )

        return ''.join(parts_html)

    # â”€â”€ Build the file tree / file table â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

    # â”€â”€ CSS (tree styles + difflib when diffs are present) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
    .rtc-file[data-status="unchanged"] { display:none; }
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
                     color:#fff; font-size:11px; padding:5px 12px; font-family:monospace; }
    .filter-bar { margin:10px 0 6px; display:flex; align-items:center; flex-wrap:wrap; gap:6px; }
    .filter-btn { cursor:pointer; padding:3px 13px; border-radius:20px; border:1px solid #d0d7de;
                  font-size:12px; font-weight:600; background:#f6f8fa; color:#57606a;
                  opacity:0.4; transition:opacity 0.15s; }
    .filter-btn.active { opacity:1; }
    .filter-btn-all { background:#e8eaf6; color:#3730a3; border-color:#a5b4fc; opacity:1; }
    .filter-btn-modified  { background:#fff8c5; color:#9a6700; border-color:#d4a72c; }
    .filter-btn-added     { background:#dafbe1; color:#1a7f37; border-color:#82cfac; }
    .filter-btn-removed   { background:#ffebe9; color:#cf222e; border-color:#ffaba8; }
    .filter-btn-unchanged { background:#f6f8fa; color:#57606a; border-color:#d0d7de; }''' + ('''
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

    # Mapping note — shown when this component was compared via a cross-name user mapping
    _mapped_snap2_name = cd.get('mapped_snap2_name', '')
    _mapping_note_html = ''
    if _mapped_snap2_name:
        _mapping_note_html = (
            f'<tr style="background:#f3e8ff;">'
            f'<td style="padding:8px 12px;color:#6e40c9;font-weight:600;">âš  Mapped Component</td>'
            f'<td style="padding:8px 12px;font-size:12px;color:#6e40c9;">'
            f'This report compares <strong>{html_mod.escape(component_name)}</strong> (Snapshot&nbsp;1)'
            f' against <strong>{html_mod.escape(_mapped_snap2_name)}</strong> (Snapshot&nbsp;2)'
            f' — matched by user-defined component mapping.</td></tr>'
        )

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
        {_mapping_note_html}
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
      <div class="filter-bar">
        <span style="font-size:12px;color:#57606a;font-weight:600;margin-right:2px;">Filter:</span>
        <button class="filter-btn filter-btn-modified active" id="btn-modified"
                onclick="toggleFilter('modified')">&#177; Modified ({modified})</button>
        <button class="filter-btn filter-btn-added active" id="btn-added"
                onclick="toggleFilter('added')">&#43; Added ({added})</button>
        <button class="filter-btn filter-btn-removed active" id="btn-removed"
                onclick="toggleFilter('removed')">&#8722; Removed ({removed})</button>
        <button class="filter-btn filter-btn-unchanged" id="btn-unchanged"
                onclick="toggleFilter('unchanged')">&#9675; Unchanged ({unchanged})</button>
        <button class="filter-btn filter-btn-all" onclick="showAll()">&#9654; Show All</button>
      </div>
      {file_table}
    </div>

    {inline_diff_card}

  </div>
  <script>
  (function() {{
    var visible = {{modified: true, added: true, removed: true, unchanged: false}};

    function applyFilters() {{
      // Hide all folders first, then show only those containing visible files
      document.querySelectorAll('.rtc-folder').forEach(function(f) {{
        f.style.display = 'none';
      }});

      document.querySelectorAll('.rtc-file').forEach(function(el) {{
        var s = el.getAttribute('data-status');
        var show = visible[s] !== false;
        el.style.display = show ? 'flex' : 'none';
        if (show) {{
          // Walk up and make parent folders visible
          var p = el.parentElement;
          while (p) {{
            if (p.classList && p.classList.contains('rtc-folder')) {{
              p.style.display = '';
            }}
            p = p.parentElement;
          }}
        }}
      }});

      ['modified', 'added', 'removed', 'unchanged'].forEach(function(s) {{
        var btn = document.getElementById('btn-' + s);
        if (btn) {{
          if (visible[s]) {{ btn.classList.add('active'); }}
          else {{ btn.classList.remove('active'); }}
        }}
      }});
    }}

    window.toggleFilter = function(status) {{
      visible[status] = !visible[status];
      applyFilters();
    }};

    window.showAll = function() {{
      Object.keys(visible).forEach(function(k) {{ visible[k] = true; }});
      applyFilters();
    }};

    document.addEventListener('DOMContentLoaded', applyFilters);
  }})();
  </script>
</body>
</html>'''

    try:
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        return out_path
    except Exception:
        return None


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Beyond Compare-style master report
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def generate_beyond_compare_master_report(
    comparison_results,
    output_dir,
    snap1_label='Snapshot 1',
    snap2_label='Snapshot 2',
    file_contents_by_component=None,
    changeset_by_component=None,
    server_url=None,
):
    """
    Generate a Beyond Compare-style master HTML report.

    Navigation:
      Left sidebar  → only Different/Added/Removed components
      Click component → see its folders with change counts
      Click folder    → see files inside that folder with status
      Click file      → synchronised side-by-side line diff

    At the bottom of every component view the changeset / baseline section
    is always visible.
    """
    import html as _h
    import json as _json
    import re as _re
    from datetime import datetime

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, "Master_Comparison_Report.html")

    fc_map_all = file_contents_by_component or {}
    cs_map_all  = changeset_by_component    or {}

    total     = len(comparison_results)
    n_diff    = sum(1 for r in comparison_results if r.get('status') == 'Different')
    n_ident   = sum(1 for r in comparison_results if r.get('status') == 'Identical')
    n_added   = sum(1 for r in comparison_results if 'Added'   in r.get('status', ''))
    n_removed = sum(1 for r in comparison_results if 'Removed' in r.get('status', ''))

    STATUS_COLOR = {
        'Different':            '#d29922',
        'Identical':            '#8b949e',
        'Added in Snapshot 2':  '#3fb950',
        'Removed in Snapshot 2':'#f85149',
    }
    FILE_STATUS_COLOR = {'modified':'#d29922','added':'#3fb950','removed':'#f85149','unchanged':'#8b949e'}
    FILE_STATUS_ICON  = {'modified':'±','added':'+','removed':'−','unchanged':'○'}

    MAX_DIFF_ROWS  = 1200   # per file
    MAX_CHARS      = 120_000

    # â”€â”€ Binary detector â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _is_bin(text):
        if not text:
            return False
        if text.count('\ufffd') / max(len(text), 1) > 0.02:
            return True
        if '\x00' in text:
            return True
        sample = text[:2000]
        p = sum(c.isprintable() or c in '\t\n\r' for c in sample)
        return len(sample) > 0 and p / len(sample) < 0.70

    # â”€â”€ Side-by-side diff builder (Python-side, stored as JSON) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _sidebyside_rows(s1, s2):
        """Return list of row-dicts for the synchronised side-by-side view."""
        if _is_bin(s1) or _is_bin(s2):
            return None, True   # binary flag

        l1 = (s1 or '').splitlines()
        l2 = (s2 or '').splitlines()

        truncated = False
        if len(l1) + len(l2) > MAX_DIFF_ROWS * 2:
            l1 = l1[:MAX_DIFF_ROWS]
            l2 = l2[:MAX_DIFF_ROWS]
            truncated = True

        rows = []
        lno1 = lno2 = 1
        sm = difflib.SequenceMatcher(None, l1, l2, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == 'equal':
                for a, b in zip(range(i1, i2), range(j1, j2)):
                    rows.append({'t': 'e', 'l': l1[a], 'r': l2[b], 'n1': lno1, 'n2': lno2})
                    lno1 += 1; lno2 += 1
            elif tag == 'replace':
                ll = list(range(i1, i2))
                rl = list(range(j1, j2))
                for k in range(max(len(ll), len(rl))):
                    lv = l1[ll[k]] if k < len(ll) else None
                    rv = l2[rl[k]] if k < len(rl) else None
                    rows.append({
                        't': 'c',
                        'l': lv if lv is not None else '',
                        'r': rv if rv is not None else '',
                        'n1': lno1 if lv is not None else 0,
                        'n2': lno2 if rv is not None else 0,
                    })
                    if lv is not None: lno1 += 1
                    if rv is not None: lno2 += 1
            elif tag == 'delete':
                for a in range(i1, i2):
                    rows.append({'t': 'd', 'l': l1[a], 'r': '', 'n1': lno1, 'n2': 0})
                    lno1 += 1
            elif tag == 'insert':
                for b in range(j1, j2):
                    rows.append({'t': 'i', 'l': '', 'r': l2[b], 'n1': 0, 'n2': lno2})
                    lno2 += 1

        return rows, truncated

    # â”€â”€ Build component data dict (to be JSON-serialised into the page) â”€â”€â”€
    components_json = []   # only changed components
    diff_data_json  = {}   # {ci_str: {file_path: [rows]}}

    for ci, comp in enumerate(comparison_results):
        status = comp.get('status', '')
        if status not in ('Different', 'Added in Snapshot 2', 'Removed in Snapshot 2'):
            continue

        cname  = comp.get('name', f'Component {ci}')
        b1uuid = comp.get('baseline1_uuid', comp.get('snapshot1', {}).get('baseline_uuid', ''))
        b2uuid = comp.get('baseline2_uuid', comp.get('snapshot2', {}).get('baseline_uuid', ''))

        fc      = comp.get('file_comparison') or {}
        details = fc.get('details', {})

        # Organise files into folders
        folders = {}   # {folder_path: [{name, path, status}]}
        for fpath, fstatus in sorted(details.items()):
            parts      = fpath.replace('\\', '/').split('/')
            fname      = parts[-1]
            folder_key = '/'.join(parts[:-1]) if len(parts) > 1 else ''
            folders.setdefault(folder_key, []).append({
                'name': fname, 'path': fpath, 'status': fstatus
            })

        # Changeset / baseline info
        csdata = cs_map_all.get(cname) or {}
        b1info = csdata.get('baseline1') or {}
        b2info = csdata.get('baseline2') or {}
        csl    = csdata.get('changesets') or []

        def _cs_name(info, uuid):
            return str(info.get('name') or uuid[:30] or '')

        cs_items = []
        for cs in csl[:80]:
            cs_uuid  = str(cs.get('uuid', ''))
            wi_raw   = str(cs.get('comment', ''))
            wi_m     = _re.findall(
                r'(?:Work\s*Item|Task|WI|Defect|Bug|Story)\s*[:#]?\s*(\d{3,7})|#(\d{3,7})',
                wi_raw, _re.IGNORECASE)
            wi_nums  = list(dict.fromkeys(n for pair in wi_m for n in pair if n))
            cs_items.append({
                'uuid':    cs_uuid,
                'author':  str(cs.get('author', '')),
                'comment': str(cs.get('comment', ''))[:500],
                'ts':      str(cs.get('timestamp', '')),
                'wi':      wi_nums[:5],
                'href': (f'{server_url}/resource/itemOid/com.ibm.team.scm.ChangeSet/{cs_uuid}'
                         if server_url and cs_uuid else ''),
            })

        def _wi_hrefs(wi_nums):
            if not wi_nums:
                return []
            return [{'n': wn, 'href': (
                f'{server_url}/resource/itemName/com.ibm.team.workitem.WorkItem/{wn}'
                if server_url else '')} for wn in wi_nums]

        components_json.append({
            'ci':     ci,
            'name':   cname,
            'status': status,
            'b1uuid': b1uuid,
            'b2uuid': b2uuid,
            'b1name': _cs_name(b1info, b1uuid),
            'b2name': _cs_name(b2info, b2uuid),
            'stats': {
                'modified':  fc.get('modified',  0),
                'added':     fc.get('added',     0),
                'removed':   fc.get('removed',   0),
                'unchanged': fc.get('unchanged', 0),
            },
            'folders': {k: v for k, v in folders.items()},
            'has_files': bool(details),
            'baseline1': {
                'name':      b1info.get('name', ''),
                'comment':   b1info.get('comment', ''),
                'author':    str(b1info.get('author', '')),
                'timestamp': str(b1info.get('timestamp', '')),
                'href': (f'{server_url}/resource/itemOid/com.ibm.team.scm.Baseline/{b1uuid}'
                         if server_url and b1uuid else ''),
            },
            'baseline2': {
                'name':      b2info.get('name', ''),
                'comment':   b2info.get('comment', ''),
                'author':    str(b2info.get('author', '')),
                'timestamp': str(b2info.get('timestamp', '')),
                'href': (f'{server_url}/resource/itemOid/com.ibm.team.scm.Baseline/{b2uuid}'
                         if server_url and b2uuid else ''),
            },
            'changesets': cs_items,
        })

        # Pre-compute side-by-side diffs for available file content
        file_diffs = {}
        file_contents = fc_map_all.get(cname, {})
        for fpath, fstatus in details.items():
            if fstatus not in ('modified', 'added', 'removed'):
                continue
            pair = file_contents.get(fpath) or {}
            s1   = pair.get('snap1')
            s2   = pair.get('snap2')
            if s1 is None and s2 is None:
                continue
            # Cap size
            if len(s1 or '') > MAX_CHARS or len(s2 or '') > MAX_CHARS:
                file_diffs[fpath] = {'bin': True, 'reason': 'too_large'}
                continue
            rows, trunc = _sidebyside_rows(s1, s2)
            if rows is None:
                file_diffs[fpath] = {'bin': True, 'reason': 'binary'}
            else:
                file_diffs[fpath] = {'rows': rows, 'trunc': trunc}

        diff_data_json[str(ci)] = file_diffs

    # â”€â”€ Serialise to JS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Use separators=(',',':') for compact output
    comp_js      = _json.dumps(components_json,            separators=(',', ':'), ensure_ascii=False)
    diff_data_js = _json.dumps(diff_data_json,             separators=(',', ':'), ensure_ascii=False)
    surl_js      = _json.dumps(server_url or '',           separators=(',', ':'), ensure_ascii=False)
    s1l_js       = _json.dumps(snap1_label,                separators=(',', ':'), ensure_ascii=False)
    s2l_js       = _json.dumps(snap2_label,                separators=(',', ':'), ensure_ascii=False)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # â”€â”€ CSS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    css = """
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;font-family:"Segoe UI",Arial,sans-serif;font-size:13px;
  background:#0d1117;color:#e6edf3;overflow:hidden}
#app{display:flex;flex-direction:column;height:100vh}
/* â”€â”€ Header â”€â”€ */
#hdr{flex-shrink:0;background:#161b22;border-bottom:1px solid #30363d;padding:8px 18px}
#hdr h1{font-size:15px;font-weight:700;color:#e6edf3;margin:0}
.hdr-sub{font-size:11px;color:#8b949e;margin-top:2px}
.hdr-stats{display:flex;gap:8px;margin-top:5px;flex-wrap:wrap}
/* â”€â”€ Body â”€â”€ */
#body{display:flex;flex:1;overflow:hidden}
/* â”€â”€ Sidebar â”€â”€ */
#sb{width:260px;flex-shrink:0;background:#161b22;border-right:1px solid #30363d;
  display:flex;flex-direction:column;overflow:hidden}
#sb-hd{padding:6px 12px;font-size:10px;font-weight:700;color:#8b949e;
  text-transform:uppercase;letter-spacing:.06em;flex-shrink:0}
#sb-srch{padding:4px 10px;flex-shrink:0}
#sb-srch input{width:100%;padding:4px 8px;border-radius:5px;border:1px solid #30363d;
  background:#0d1117;color:#e6edf3;font-size:11px;outline:none}
#sb-srch input:focus{border-color:#388bfd}
#sb-list{flex:1;overflow-y:auto}
.si{display:flex;align-items:center;padding:5px 10px;cursor:pointer;gap:6px;
  user-select:none;transition:background .1s;border-left:3px solid transparent}
.si:hover{background:#21262d}
.si.active{background:#1f6feb22;border-left-color:#388bfd}
.si-ico{width:14px;text-align:center;flex-shrink:0;font-size:13px}
.si-nm{flex:1;font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.si-cnt{font-size:10px;background:#30363d;color:#cba6f7;padding:0 5px;border-radius:8px}
.si-sep{padding:4px 12px;font-size:10px;color:#484f58;font-style:italic;margin-top:4px}
/* â”€â”€ Main pane â”€â”€ */
#main{flex:1;display:flex;flex-direction:column;overflow:hidden}
.view{display:none;flex-direction:column;height:100%;overflow:hidden}
.view.active{display:flex}
/* â”€â”€ Breadcrumb â”€â”€ */
#bc{flex-shrink:0;background:#161b22;border-bottom:1px solid #30363d;
  padding:6px 14px;display:flex;align-items:center;gap:5px;flex-wrap:wrap}
.bc-seg{font-size:11px;color:#8b949e;cursor:pointer;white-space:nowrap}
.bc-seg:hover{color:#58a6ff;text-decoration:underline}
.bc-sep{color:#484f58;font-size:11px}
.bc-cur{font-size:11px;color:#e6edf3;font-weight:600;white-space:nowrap}
/* â”€â”€ Component stats bar â”€â”€ */
#comp-hdr{flex-shrink:0;padding:8px 14px;background:#0d1117;border-bottom:1px solid #30363d;
  display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.comp-title{font-size:13px;font-weight:700}
.badge{font-size:11px;padding:1px 7px;border-radius:10px;font-weight:700}
/* â”€â”€ Generic scrollable content area â”€â”€ */
#content{flex:1;overflow-y:auto;padding:10px 14px}
/* â”€â”€ Folder list â”€â”€ */
.fl-grid{display:grid;gap:8px}
.fl-item{background:#161b22;border:1px solid #30363d;border-radius:6px;
  padding:10px 14px;cursor:pointer;display:flex;align-items:center;gap:10px;
  transition:background .1s}
.fl-item:hover{background:#21262d;border-color:#58a6ff}
.fl-icon{font-size:20px;flex-shrink:0}
.fl-info{flex:1;overflow:hidden}
.fl-name{font-size:12px;font-weight:700;color:#79c0ff;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis}
.fl-counts{display:flex;gap:6px;margin-top:3px;flex-wrap:wrap}
.fc-m{font-size:10px;color:#d29922}
.fc-a{font-size:10px;color:#3fb950}
.fc-r{font-size:10px;color:#f85149}
.fc-u{font-size:10px;color:#8b949e}
/* â”€â”€ File list â”€â”€ */
.file-item{display:flex;align-items:center;padding:6px 10px;border-bottom:1px solid #21262d;
  cursor:pointer;gap:8px;transition:background .1s;border-radius:4px;margin-bottom:2px}
.file-item:hover{background:#21262d}
.file-item.active{background:#1f6feb22;border:1px solid #388bfd}
.fi-ico{font-size:13px;flex-shrink:0;width:16px;text-align:center}
.fi-name{flex:1;font-family:monospace;font-size:12px;word-break:break-all}
.fi-badge{font-size:10px;font-weight:700;padding:1px 7px;border-radius:10px;
  background:rgba(255,255,255,.08)}
/* â”€â”€ Side-by-side diff â”€â”€ */
#diff-hdr{flex-shrink:0;padding:7px 14px;background:#161b22;
  border-bottom:1px solid #30363d;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.diff-fname{font-family:monospace;font-size:13px;font-weight:700;flex:1}
.diff-status{font-size:11px;padding:2px 8px;border-radius:8px;font-weight:700}
.diff-snaplbl{font-size:11px;color:#8b949e}
#diff-table-wrap{flex:1;overflow:auto;background:#0d1117}
.diff-hdr-row{display:grid;grid-template-columns:46px 1fr 46px 1fr;
  background:#161b22;border-bottom:1px solid #30363d;position:sticky;top:0;z-index:10}
.diff-hdr-cell{padding:4px 8px;font-size:11px;font-weight:700;color:#e6edf3;
  border-right:1px solid #30363d}
.diff-row{display:grid;grid-template-columns:46px 1fr 46px 1fr;min-height:18px}
.diff-row:hover{filter:brightness(1.1)}
.dl-lno{padding:0 6px;text-align:right;font-size:11px;font-family:monospace;
  color:#484f58;border-right:1px solid #21262d;user-select:none;min-height:18px;
  display:flex;align-items:center;justify-content:flex-end;flex-shrink:0}
.dl-code{padding:0 8px;font-family:Consolas,"Courier New",monospace;font-size:12px;
  white-space:pre-wrap;word-break:break-all;min-height:18px;border-right:1px solid #21262d;
  line-height:18px}
.dr-eq  .dl-code,.dr-eq  .dl-lno{background:#0d1117;color:#8b949e}
.dr-chg .dl-code,.dr-chg .dl-lno{background:#2d1800;color:#e6edf3}
.dr-del .dl-code            {background:#2d0000;color:#ffa8a8}
.dr-del .dl-lno             {background:#2d0000;color:#f85149}
.dr-ins .dl-code            {background:#0e2d1a;color:#a8ffb0}
.dr-ins .dl-lno             {background:#0e2d1a;color:#3fb950}
.dr-ept .dl-code,.dr-ept .dl-lno{background:#161b22}
#diff-msg{padding:14px;text-align:center;color:#8b949e;font-size:12px;
  display:none;align-items:center;justify-content:center}
/* â”€â”€ Changeset section â”€â”€ */
#cs-section{flex-shrink:0;background:#161b22;border-top:2px solid #30363d;
  max-height:28vh;overflow-y:auto}
#cs-toggle{padding:7px 14px;cursor:pointer;display:flex;align-items:center;gap:6px;
  background:#161b22;border-bottom:1px solid #30363d;user-select:none;font-size:12px;
  font-weight:700;color:#cba6f7}
#cs-toggle:hover{background:#21262d}
#cs-body{padding:10px 14px}
.bl-row{display:grid;grid-template-columns:140px 1fr;font-size:12px;
  border-bottom:1px solid #21262d;padding:5px 0}
.bl-lbl{color:#8b949e;font-weight:700}
.bl-val a{color:#58a6ff;text-decoration:none}
.bl-val a:hover{text-decoration:underline}
.cs-tbl{width:100%;border-collapse:collapse;font-size:11px;margin-top:8px}
.cs-tbl th{background:#21262d;padding:4px 8px;text-align:left;color:#8b949e;
  font-weight:700;position:sticky;top:0}
.cs-tbl td{padding:3px 8px;border-bottom:1px solid #21262d;vertical-align:top}
.cs-tbl tr:nth-child(even) td{background:#1c2128}
.cs-link{color:#58a6ff;font-family:monospace;font-size:11px;text-decoration:none}
.cs-link:hover{text-decoration:underline}
.wi-link{color:#58a6ff;font-weight:700;font-size:11px;text-decoration:none}
.wi-link:hover{text-decoration:underline}
/* â”€â”€ Scrollbar â”€â”€ */
::-webkit-scrollbar{width:6px;height:6px}
::-webkit-scrollbar-track{background:#0d1117}
::-webkit-scrollbar-thumb{background:#30363d;border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:#484f58}
/* â”€â”€ Welcome â”€â”€ */
#welcome{align-items:center;justify-content:center;text-align:center;gap:12px;
  color:#8b949e}
#welcome h2{font-size:16px;color:#e6edf3}
#welcome .wbadges{display:flex;gap:8px;flex-wrap:wrap;justify-content:center;margin-top:10px}
"""

    # â”€â”€ JS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    js = r"""
const COMPS      = __COMP_JS__;
const DIFFS      = __DIFF_JS__;
const SERVER_URL = __SURL_JS__;
const S1L        = __S1L_JS__;
const S2L        = __S2L_JS__;

// Build lookup: ci → comp data
const BY_CI = {};
COMPS.forEach(c => { BY_CI[c.ci] = c; });

// State
let selCI     = null;   // selected component index
let selFolder = null;   // selected folder key  ('') = root
let selFile   = null;   // selected file path

// â”€â”€ HTML escape â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function esc(s){
  return String(s||'')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// â”€â”€ Sidebar â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function buildSidebar(){
  const list = document.getElementById('sb-list');
  let html = '';
  const diff = COMPS.filter(c=>c.status==='Different');
  const added = COMPS.filter(c=>c.status.includes('Added'));
  const removed = COMPS.filter(c=>c.status.includes('Removed'));

  if(diff.length){
    html += `<div class="si-sep">± Different (${diff.length})</div>`;
    diff.forEach(c=>{
      const n = c.stats.modified+c.stats.added+c.stats.removed;
      html += `<div class="si" id="si_${c.ci}" onclick="selectComp(${c.ci})">
        <span class="si-ico" style="color:#d29922">±</span>
        <span class="si-nm" title="${esc(c.name)}">${esc(c.name.length>36?c.name.slice(0,36)+'…':c.name)}</span>
        ${n?`<span class="si-cnt">${n}</span>`:''}
      </div>`;
    });
  }
  if(added.length){
    html += `<div class="si-sep">+ Added (${added.length})</div>`;
    added.forEach(c=>{
      html += `<div class="si" id="si_${c.ci}" onclick="selectComp(${c.ci})">
        <span class="si-ico" style="color:#3fb950">+</span>
        <span class="si-nm" title="${esc(c.name)}">${esc(c.name.length>36?c.name.slice(0,36)+'…':c.name)}</span>
      </div>`;
    });
  }
  if(removed.length){
    html += `<div class="si-sep">− Removed (${removed.length})</div>`;
    removed.forEach(c=>{
      html += `<div class="si" id="si_${c.ci}" onclick="selectComp(${c.ci})">
        <span class="si-ico" style="color:#f85149">−</span>
        <span class="si-nm" title="${esc(c.name)}">${esc(c.name.length>36?c.name.slice(0,36)+'…':c.name)}</span>
      </div>`;
    });
  }
  list.innerHTML = html || '<div class="si-sep">No changed components</div>';
}

// â”€â”€ Breadcrumb â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function setBreadcrumb(parts){
  // parts: [{label, onclick}]  last one = current (no onclick)
  const bc = document.getElementById('bc');
  let html = '';
  parts.forEach((p,i)=>{
    if(i>0) html += '<span class="bc-sep">â€º</span>';
    if(i===parts.length-1){
      html += `<span class="bc-cur">${esc(p.label)}</span>`;
    } else {
      html += `<span class="bc-seg" onclick="${p.onclick}">${esc(p.label)}</span>`;
    }
  });
  bc.innerHTML = html;
}

// â”€â”€ Comp header â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function setCompHdr(c){
  const h = document.getElementById('comp-hdr');
  if(!c){h.style.display='none';return;}
  h.style.display='flex';
  const sc = {Different:'#d29922','Added in Snapshot 2':'#3fb950','Removed in Snapshot 2':'#f85149'}[c.status]||'#8b949e';
  let badges='';
  if(c.stats.modified) badges+=`<span class="badge" style="background:#332200;color:#d29922">± ${c.stats.modified} Modified</span>`;
  if(c.stats.added)    badges+=`<span class="badge" style="background:#122117;color:#3fb950">+ ${c.stats.added} Added</span>`;
  if(c.stats.removed)  badges+=`<span class="badge" style="background:#2d0000;color:#f85149">− ${c.stats.removed} Removed</span>`;
  if(c.stats.unchanged)badges+=`<span class="badge" style="background:#1c2128;color:#8b949e">○ ${c.stats.unchanged} Unchanged</span>`;
  h.innerHTML = `<span class="comp-title" style="color:${sc}">${esc(c.name)}</span>${badges}`;
}

// â”€â”€ Show views â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function showView(id){
  document.querySelectorAll('.view').forEach(v=>v.classList.remove('active'));
  const v = document.getElementById(id);
  if(v) v.classList.add('active');
}

// â”€â”€ Select component → show folder list â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function selectComp(ci){
  selCI     = ci;
  selFolder = null;
  selFile   = null;

  document.querySelectorAll('.si').forEach(s=>s.classList.remove('active'));
  const si = document.getElementById('si_'+ci);
  if(si){si.classList.add('active');si.scrollIntoView({block:'nearest'});}

  const c = BY_CI[ci];
  if(!c) return;

  setCompHdr(c);
  setBreadcrumb([{label: c.name}]);
  setChangesets(c);

  // Build folder list
  const content = document.getElementById('content');
  const folders  = c.folders;   // {folder_key: [{name,path,status}]}

  if(!c.has_files){
    content.innerHTML = `<div style="padding:20px;color:#8b949e;font-size:12px;">
      ℹ No file-level detail returned by the RTC API for this component.<br>
      The component is marked <strong>Different</strong> because the baseline UUIDs differ.
    </div>`;
    showView('view-folders');
    return;
  }

  // Count changes per folder
  const sortedFolders = Object.entries(folders).sort((a,b)=>{
    // Root first, then alphabetical
    if(a[0]===''&&b[0]!=='') return -1;
    if(b[0]===''&&a[0]!=='') return 1;
    return a[0].localeCompare(b[0]);
  });

  let html = '<div class="fl-grid">';
  sortedFolders.forEach(([fkey, files])=>{
    const nm = files.filter(f=>f.status==='modified').length;
    const na = files.filter(f=>f.status==='added').length;
    const nr = files.filter(f=>f.status==='removed').length;
    const nu = files.filter(f=>f.status==='unchanged').length;
    const nchg = nm+na+nr;
    const label = fkey==='' ? '/ (root)' : fkey;
    let counts = '';
    if(nm) counts+=`<span class="fc-m">± ${nm} modified</span>`;
    if(na) counts+=`<span class="fc-a">+ ${na} added</span>`;
    if(nr) counts+=`<span class="fc-r">− ${nr} removed</span>`;
    if(nu) counts+=`<span class="fc-u">○ ${nu} unchanged</span>`;
    const fkEsc = esc(fkey).replace(/'/g,"\\'");
    html += `<div class="fl-item" onclick="selectFolder(${ci},'${fkEsc}')">
      <span class="fl-icon">📁</span>
      <div class="fl-info">
        <div class="fl-name">${esc(label)}</div>
        <div class="fl-counts">${counts||'<span class="fc-u">○ no changes</span>'}</div>
      </div>
      ${nchg?`<span class="badge" style="background:#30363d;color:#cba6f7">${nchg}</span>`:''}
    </div>`;
  });
  html += '</div>';
  content.innerHTML = html;
  showView('view-folders');
}

// â”€â”€ Select folder → show file list â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function selectFolder(ci, fkey){
  selCI     = ci;
  selFolder = fkey;
  selFile   = null;

  const c = BY_CI[ci];
  if(!c) return;

  setCompHdr(c);
  setBreadcrumb([
    {label: c.name, onclick:`selectComp(${ci})`},
    {label: fkey===''?'/ (root)':fkey},
  ]);
  setChangesets(c);

  const files = (c.folders[fkey]||[]).slice().sort((a,b)=>{
    // Changed files first
    const ord={modified:0,added:1,removed:2,unchanged:3};
    return (ord[a.status]??9)-(ord[b.status]??9)||a.name.localeCompare(b.name);
  });

  let html = '';
  files.forEach(f=>{
    const col = {modified:'#d29922',added:'#3fb950',removed:'#f85149',unchanged:'#8b949e'}[f.status]||'#8b949e';
    const ico = {modified:'±',added:'+',removed:'−',unchanged:'○'}[f.status]||'○';
    const bg  = {modified:'#332200',added:'#122117',removed:'#2d0000'}[f.status]||'';
    const fpE = esc(f.path).replace(/'/g,"\\'");
    const clickable = f.status!=='unchanged';
    html += `<div class="file-item" onclick="${clickable?`selectFile(${ci},'${fpE}','${esc(f.status)}')`:''}"
      style="${clickable?'cursor:pointer':'cursor:default;opacity:.6'}">
      <span class="fi-ico" style="color:${col}">${ico}</span>
      <span class="fi-name" style="color:${col}">${esc(f.name)}</span>
      <span class="fi-badge" style="background:${bg};color:${col}">${f.status}</span>
    </div>`;
  });

  document.getElementById('content').innerHTML = html||'<div style="padding:14px;color:#8b949e">No files</div>';
  showView('view-folders');
}

// â”€â”€ Select file → show side-by-side diff â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function selectFile(ci, fpath, fstatus){
  selCI   = ci;
  selFile = fpath;

  const c = BY_CI[ci];
  if(!c) return;

  // Determine folder key from fpath
  const parts = fpath.replace(/\\/g,'/').split('/');
  const fname = parts[parts.length-1];
  const fkey  = parts.slice(0,-1).join('/');

  setCompHdr(c);
  setBreadcrumb([
    {label: c.name,                     onclick:`selectComp(${ci})`},
    {label: fkey===''?'/ (root)':fkey,  onclick:`selectFolder(${ci},'${esc(fkey).replace(/'/g,"\\'")}')` },
    {label: fname},
  ]);
  setChangesets(c);

  // Diff header
  const col = {modified:'#d29922',added:'#3fb950',removed:'#f85149'}[fstatus]||'#8b949e';
  const bg  = {modified:'#332200',added:'#122117',removed:'#2d0000'}[fstatus]||'#1c2128';
  document.getElementById('diff-hdr').innerHTML = `
    <span class="diff-fname">${esc(fpath)}</span>
    <span class="diff-status" style="background:${bg};color:${col}">${fstatus}</span>
    <span class="diff-snaplbl">← ${esc(S1L)}</span>
    <span class="diff-snaplbl">${esc(S2L)} →</span>
  `;

  // Look up diff data
  const ciData  = DIFFS[String(ci)] || {};
  const fd      = ciData[fpath];
  const wrap    = document.getElementById('diff-table-wrap');
  const msg     = document.getElementById('diff-msg');

  if(!fd){
    msg.textContent = 'No file content available — could not be fetched from the server.';
    msg.style.display='flex'; wrap.innerHTML=''; showView('view-diff'); return;
  }
  if(fd.bin){
    const reason = fd.reason==='too_large'
      ? 'File is too large for inline diff. Open the per-component HTML report.'
      : 'Binary file — line-by-line diff is not available for binary files.';
    msg.textContent = reason;
    msg.style.display='flex'; wrap.innerHTML=''; showView('view-diff'); return;
  }

  msg.style.display='none';
  const rows    = fd.rows;
  const trunc   = fd.trunc;

  // Build side-by-side table
  let thead = `<div class="diff-hdr-row">
    <div class="diff-hdr-cell">#</div>
    <div class="diff-hdr-cell">← ${esc(S1L)}</div>
    <div class="diff-hdr-cell">#</div>
    <div class="diff-hdr-cell">${esc(S2L)} →</div>
  </div>`;

  let tbody = '';
  rows.forEach(function(row){
    let cls='';
    if(row.t==='e') cls='dr-eq';
    else if(row.t==='c'){
      // If one side is empty it's actually insert/delete
      if(!row.l && row.n1===0) cls='dr-ins';
      else if(!row.r && row.n2===0) cls='dr-del';
      else cls='dr-chg';
    }
    else if(row.t==='d') cls='dr-del';
    else if(row.t==='i') cls='dr-ins';

    const ln1 = row.n1>0 ? row.n1 : '';
    const ln2 = row.n2>0 ? row.n2 : '';

    // Left side might be empty (insert row), right side empty (delete row)
    const leftCls  = (row.t==='i' || (row.t==='c'&&row.n1===0)) ? 'dr-ept' : cls;
    const rightCls = (row.t==='d' || (row.t==='c'&&row.n2===0)) ? 'dr-ept' : cls;

    tbody += `<div class="diff-row ${cls}">
      <div class="dl-lno ${leftCls}">${ln1}</div>
      <div class="dl-code ${leftCls}">${esc(row.l)}</div>
      <div class="dl-lno ${rightCls}">${ln2}</div>
      <div class="dl-code ${rightCls}">${esc(row.r)}</div>
    </div>`;
  });

  if(trunc){
    tbody += `<div style="padding:8px 14px;background:#1d2d3e;color:#79c0ff;font-size:11px;">
      âš  Diff truncated — file is large. Open the per-component HTML report for the full diff.
    </div>`;
  }

  wrap.innerHTML = thead + tbody;
  showView('view-diff');
}

// â”€â”€ Changeset section â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
let csOpen = true;
function setChangesets(c){
  const body = document.getElementById('cs-body');
  if(!c){body.innerHTML='';return;}

  // Baselines
  function blrow(label, info, uuid, href){
    const nm = esc(info.name||uuid.slice(0,30));
    const link = href
      ? `<a href="${esc(href)}" target="_blank" class="cs-link">${nm}</a>`
      : `<code class="cs-link">${nm}</code>`;
    const sub = info.author
      ? `<br><small style="color:#8b949e">${esc(info.author)} · ${esc(info.timestamp)}</small>` : '';
    const com = info.comment
      ? `<br><span style="color:#8b949e;font-size:11px">${esc(info.comment.slice(0,200))}</span>` : '';
    return `<div class="bl-row"><div class="bl-lbl">${esc(label)}</div>
      <div class="bl-val">${link}${sub}${com}</div></div>`;
  }
  let html = blrow(S1L, c.baseline1, c.b1uuid, c.baseline1.href);
  html    += blrow(S2L, c.baseline2, c.b2uuid, c.baseline2.href);

  // Changesets
  if(c.changesets && c.changesets.length){
    html += `<table class="cs-tbl"><thead><tr>
      <th>Changeset</th><th>Author</th><th>Comment</th>
      <th>Work Items</th><th>Timestamp</th>
    </tr></thead><tbody>`;
    c.changesets.forEach(cs=>{
      const csLink = cs.href
        ? `<a href="${esc(cs.href)}" target="_blank" class="cs-link">${esc(cs.uuid.slice(0,24))}</a>`
        : `<code class="cs-link">${esc(cs.uuid.slice(0,24))}</code>`;
      const wiCells = cs.wi && cs.wi.length
        ? cs.wi.map(w=>{
            const wi = (typeof w==='object') ? w : {n:w,href:''};
            return wi.href
              ? `<a href="${esc(wi.href)}" target="_blank" class="wi-link">#${esc(wi.n)}</a>`
              : `<span class="wi-link">#${esc(wi.n)}</span>`;
          }).join(' ')
        : '—';
      html += `<tr><td>${csLink}</td><td>${esc(cs.author)}</td>
        <td style="white-space:pre-wrap;font-size:11px">${esc(cs.comment)}</td>
        <td>${wiCells}</td><td style="white-space:nowrap">${esc(cs.ts)}</td></tr>`;
    });
    html += '</tbody></table>';
  }

  body.innerHTML = html;
  document.getElementById('cs-section').style.display = '';
}

function toggleCS(){
  csOpen = !csOpen;
  document.getElementById('cs-body').style.display = csOpen ? '' : 'none';
  document.getElementById('cs-toggle').querySelector('.cs-arr').textContent = csOpen ? '▾' : '▸';
}

// â”€â”€ Sidebar search â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
document.getElementById('sb-srch').querySelector('input').addEventListener('input',function(){
  const q = this.value.toLowerCase();
  document.querySelectorAll('.si').forEach(s=>{
    const nm = s.querySelector('.si-nm');
    s.style.display = (nm&&nm.textContent.toLowerCase().includes(q)) ? '' : 'none';
  });
  document.querySelectorAll('.si-sep').forEach(s=>s.style.display='');
});

// â”€â”€ Boot â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
buildSidebar();
// Auto-select first Different component
const first = COMPS.find(c=>c.status==='Different') || COMPS[0];
if(first){
  selectComp(first.ci);
} else {
  document.getElementById('comp-hdr').style.display='none';
  showView('welcome');
}
"""
    # Replace placeholders with actual JSON
    js = (js
          .replace('__COMP_JS__',  comp_js)
          .replace('__DIFF_JS__',  diff_data_js)
          .replace('__SURL_JS__',  surl_js)
          .replace('__S1L_JS__',   s1l_js)
          .replace('__S2L_JS__',   s2l_js))

    s1e = _h.escape(snap1_label)
    s2e = _h.escape(snap2_label)

    hidden_only_ident = n_ident + sum(
        1 for r in comparison_results
        if r.get('status') not in ('Different', 'Added in Snapshot 2', 'Removed in Snapshot 2')
    )

    html_out = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>Beyond Compare: {s1e} → {s2e}</title>
  <style>{css}</style>
</head>
<body>
<div id="app">

  <!-- Header -->
  <div id="hdr">
    <h1>🔍 Beyond Compare — Master Snapshot Report</h1>
    <div class="hdr-sub">{s1e} &nbsp;→&nbsp; {s2e} &nbsp;·&nbsp; {now_str}</div>
    <div class="hdr-stats">
      <span class="badge" style="background:#332200;color:#d29922">± {n_diff} Different</span>
      <span class="badge" style="background:#122117;color:#3fb950">+ {n_added} Added</span>
      <span class="badge" style="background:#2d0000;color:#f85149">− {n_removed} Removed</span>
      <span class="badge" style="background:#1c2128;color:#8b949e">○ {n_ident} Identical (hidden)</span>
      <span class="badge" style="background:#1c2128;color:#e6edf3">Total: {total}</span>
    </div>
  </div>

  <!-- Body -->
  <div id="body">

    <!-- Sidebar: only changed components -->
    <div id="sb">
      <div id="sb-hd">Changed Components ({n_diff + n_added + n_removed})</div>
      <div id="sb-srch"><input type="text" placeholder="Filter…"></div>
      <div id="sb-list"></div>
    </div>

    <!-- Main -->
    <div id="main">

      <!-- Breadcrumb -->
      <div id="bc"><span class="bc-cur">Select a component</span></div>

      <!-- Component stats bar -->
      <div id="comp-hdr" style="display:none"></div>

      <!-- VIEW: folder / file list -->
      <div id="view-folders" class="view active">
        <div id="content" style="flex:1;overflow-y:auto;padding:10px 14px"></div>
      </div>

      <!-- VIEW: side-by-side diff -->
      <div id="view-diff" class="view" style="display:none;">
        <div id="diff-hdr"></div>
        <div id="diff-msg" style="display:none;padding:14px;color:#8b949e;font-size:12px;
          align-items:center;justify-content:center"></div>
        <div id="diff-table-wrap" style="flex:1;overflow:auto;background:#0d1117"></div>
      </div>

      <!-- VIEW: welcome -->
      <div id="welcome" class="view" style="display:none;flex-direction:column">
        <div style="font-size:48px">🔍</div>
        <h2>Select a component</h2>
        <p>Choose a changed component from the left sidebar.</p>
        <div class="wbadges">
          <span class="badge" style="background:#332200;color:#d29922">± {n_diff} Different</span>
          <span class="badge" style="background:#122117;color:#3fb950">+ {n_added} Added</span>
          <span class="badge" style="background:#2d0000;color:#f85149">− {n_removed} Removed</span>
        </div>
      </div>

      <!-- Changeset section (always at bottom) -->
      <div id="cs-section" style="display:none">
        <div id="cs-toggle" onclick="toggleCS()">
          <span class="cs-arr">▾</span>
          🔗 Baselines &amp; Changesets
        </div>
        <div id="cs-body"></div>
      </div>

    </div><!-- /main -->
  </div><!-- /body -->
</div><!-- /app -->
<script>{js}</script>
</body>
</html>"""

    try:
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(html_out)
        return out_path
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Online → Offline per-component HTML diff report
# ---------------------------------------------------------------------------

def generate_hybrid_component_html(
    component_name,
    compare_results,
    temp_online_dir,
    local_folder_dir,
    output_dir,
    snap1_label='Online (RTC Snapshot)',
    snap2_label='Local Folder',
):
    """
    Generate a self-contained HTML diff report for a single Online → Offline
    component comparison, showing line-by-line diffs for every changed file.

    The visual style mirrors ``generate_snapshot_component_html``:
      - Summary card (component name, folder paths, change counts)
      - File tree with ± / + / − / ○ indicators
      - Inline side-by-side diff for each modified/added/removed file
      - Filter buttons to show/hide file statuses

    Args:
        component_name   : RTC component name (e.g. "rb.as.ms.fiatgen.cswpr")
        compare_results  : ``result['results']`` from ``compare_folders`` –
                           each row is [rel_path, lines1, lines2, line_status,
                                        status, html_link, purpose, changeset_info]
        temp_online_dir  : path to temp folder containing downloaded online files
        local_folder_dir : path to the local folder
        output_dir       : directory where the HTML file will be written
        snap1_label      : display label for the online (left) side
        snap2_label      : display label for the local (right) side

    Returns:
        Absolute path to the generated HTML file, or None on failure.
    """
    import html as _h
    import difflib
    from datetime import datetime

    os.makedirs(output_dir, exist_ok=True)

    safe_name = component_name.replace('.', '_').replace(os.sep, '_').replace('/', '_')
    out_path  = os.path.join(output_dir, f"{safe_name}_diff.html")

    # ── Build file_comparison dict from compare_folders rows ───────────────
    details   = {}   # {rel_path: 'modified'|'added'|'removed'|'unchanged'}
    n_mod = n_add = n_rem = n_unch = 0

    for row in (compare_results or []):
        if len(row) < 5:
            continue
        rel_path = row[0].replace('\\', '/')
        status   = row[4]
        if status == 'Identical' or status == 'Comments update only':
            details[rel_path] = 'unchanged'
            n_unch += 1
        elif status == 'Different':
            details[rel_path] = 'modified'
            n_mod += 1
        elif 'Only in Platform' in status:   # online side only
            details[rel_path] = 'removed'
            n_rem += 1
        elif 'Only in Project' in status:    # local side only
            details[rel_path] = 'added'
            n_add += 1

    # ── Read file contents for inline diffs ────────────────────────────────
    _BINARY_EXTS = {
        '.xls', '.xlsx', '.zip', '.exe', '.dll', '.so', '.a', '.o',
        '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.pdf', '.doc', '.docx',
        '.ppt', '.pptx', '.bin', '.lib', '.obj', '.jar', '.class', '.pyc',
    }

    def _read(folder, rel):
        ext = os.path.splitext(rel.lower())[1]
        if ext in _BINARY_EXTS:
            return None
        abs_path = os.path.join(folder, rel.replace('/', os.sep))
        if not os.path.isfile(abs_path):
            return None
        try:
            with open(abs_path, 'r', encoding='utf-8', errors='replace') as fh:
                return fh.read()
        except Exception:
            return None

    def _is_binary(text):
        if not text:
            return False
        if text.count('\ufffd') / max(len(text), 1) > 0.02:
            return True
        if '\x00' in text:
            return True
        sample = text[:2000]
        if sample and sum(c.isprintable() or c in '\t\n\r' for c in sample) / len(sample) < 0.70:
            return True
        return False

    file_contents = {}   # {rel_path: {'snap1': str|None, 'snap2': str|None}}
    for rel_path, fstatus in details.items():
        if fstatus == 'unchanged':
            continue
        c1 = _read(temp_online_dir, rel_path)
        c2 = _read(local_folder_dir, rel_path)
        if c1 is not None or c2 is not None:
            file_contents[rel_path] = {'snap1': c1, 'snap2': c2}

    # ── Flags ──────────────────────────────────────────────────────────────
    STATUS_COLOR = {'added': '#1a7f37', 'modified': '#9a6700',
                    'removed': '#cf222e', 'unchanged': '#57606a'}
    STATUS_BG    = {'added': '#dafbe1', 'modified': '#fff8c5',
                    'removed': '#ffebe9', 'unchanged': '#f6f8fa'}
    STATUS_ICON  = {'added': '+', 'modified': '±', 'removed': '-', 'unchanged': '○'}

    def badge(label, count, color, bg):
        return (
            f'<span style="display:inline-block;padding:2px 10px;border-radius:12px;'
            f'background:{bg};color:{color};font-weight:600;font-size:13px;margin:0 4px;">'
            f'{label}: {count}</span>'
        )

    # ── Inline diff builder ────────────────────────────────────────────────
    _diff_present = [False]

    def _make_inline_diff(snap1_text, snap2_text, fpath, fstatus):
        try:
            if _is_binary(snap1_text) or _is_binary(snap2_text):
                return (
                    '<div style="padding:12px 16px;background:#fff8c5;border-radius:4px;'
                    'color:#9a6700;font-size:13px;">'
                    '⚠ <strong>Binary file</strong> — line-by-line diff not available.</div>'
                )
            lines1 = (snap1_text or '').splitlines(keepends=True)
            lines2 = (snap2_text or '').splitlines(keepends=True)
            if not lines1 and not lines2:
                return '<p style="color:#57606a;padding:8px;">Empty file on both sides.</p>'
            from_lbl = f'{os.path.basename(fpath)} ← {snap1_label}'
            to_lbl   = f'{os.path.basename(fpath)} → {snap2_label}'
            if not lines1:
                body = ''.join(
                    f'<tr><td class="diff_add" colspan="4" style="padding:1px 6px;">'
                    f'<code>{_h.escape(ln.rstrip())}</code></td></tr>'
                    for ln in lines2
                )
                return (f'<table class="diff" style="width:100%">'
                        f'<tr><th colspan="4" style="padding:4px 6px;text-align:left;">'
                        f'+ New file — {_h.escape(to_lbl)}</th></tr>{body}</table>')
            if not lines2:
                body = ''.join(
                    f'<tr><td class="diff_sub" colspan="4" style="padding:1px 6px;">'
                    f'<code>{_h.escape(ln.rstrip())}</code></td></tr>'
                    for ln in lines1
                )
                return (f'<table class="diff" style="width:100%">'
                        f'<tr><th colspan="4" style="padding:4px 6px;text-align:left;">'
                        f'− Deleted file — {_h.escape(from_lbl)}</th></tr>{body}</table>')
            differ = difflib.HtmlDiff(wrapcolumn=100)
            return differ.make_table(lines1, lines2,
                                     fromdesc=from_lbl, todesc=to_lbl,
                                     context=False)
        except Exception as ex:
            return f'<p style="color:#cf222e;">Could not generate diff: {_h.escape(str(ex))}</p>'

    # ── File tree builder ──────────────────────────────────────────────────
    def _build_tree(pairs):
        tree = {}
        for fpath, fstatus in pairs:
            parts = fpath.replace('\\', '/').split('/')
            node  = tree
            for part in parts[:-1]:
                node = node.setdefault(part, {'__children__': {}})['__children__']
            node[parts[-1]] = fstatus
        return tree

    def _count_changes(node):
        c = 0
        for v in node.values():
            if isinstance(v, dict):
                c += _count_changes(v.get('__children__', {}))
            elif v in ('modified', 'added', 'removed'):
                c += 1
        return c

    def _render_tree(node, prefix=''):
        html_parts = []
        folders = sorted((k, v) for k, v in node.items() if isinstance(v, dict))
        files   = sorted((k, v) for k, v in node.items() if isinstance(v, str))

        for fname, fnode in folders:
            fpath    = f'{prefix}{fname}/'
            children = fnode.get('__children__', {})
            n        = _count_changes(children)
            n_badge  = (
                f' <span style="background:#cf222e;color:#fff;font-size:10px;'
                f'padding:1px 7px;border-radius:10px;font-weight:600;">'
                f'{n} change{"s" if n != 1 else ""}</span>'
            ) if n else ''
            html_parts.append(
                f'<details class="rtc-folder" open>'
                f'<summary class="rtc-folder-sum">'
                f'<span style="color:#0550ae;font-weight:600;">📁 {_h.escape(fname)}</span>'
                f'{n_badge}</summary>'
                f'<div class="rtc-folder-body">{_render_tree(children, fpath)}</div>'
                f'</details>'
            )

        for fname, fstatus in files:
            full_path = f'{prefix}{fname}'
            color  = STATUS_COLOR.get(fstatus, '#57606a')
            bg_row = STATUS_BG.get(fstatus, 'transparent') if fstatus != 'unchanged' else 'transparent'
            icon   = STATUS_ICON.get(fstatus, '○')

            pair       = file_contents.get(full_path, {})
            c1         = pair.get('snap1')
            c2         = pair.get('snap2')
            is_bin     = _is_binary(c1) or _is_binary(c2)
            has_diff   = (fstatus in ('modified', 'added', 'removed')
                          and not is_bin
                          and (c1 is not None or c2 is not None))

            extra = diff_toggle = ''
            if fstatus in ('modified', 'added', 'removed'):
                if has_diff:
                    _diff_present[0] = True
                    tbl = _make_inline_diff(c1, c2, full_path, fstatus)
                    diff_toggle = (
                        f'<details class="file-diff-details">'
                        f'<summary class="view-diff-btn" style="background:{color};">'
                        f'▶ View Diff</summary>'
                        f'<div class="diff-panel">'
                        f'<div class="diff-snap-bar">'
                        f'<span>← {_h.escape(snap1_label)}</span>'
                        f'<span>{_h.escape(snap2_label)} →</span>'
                        f'</div>{tbl}</div></details>'
                    )
                elif is_bin:
                    extra = '<span class="file-badge file-badge-bin">⊘ binary</span>'
                else:
                    extra = '<span class="file-badge file-badge-nc">no content</span>'

            html_parts.append(
                f'<div class="rtc-file" data-status="{fstatus}" style="background:{bg_row};">'
                f'<span class="file-icon" style="color:{color};">{icon}</span>'
                f'<span class="file-name" style="color:{color if fstatus != "unchanged" else "#57606a"};">'
                f'{_h.escape(fname)}</span>'
                f'<span class="file-status" style="color:{color};">{fstatus.capitalize()}</span>'
                f'{extra}{diff_toggle}'
                f'</div>'
            )
        return ''.join(html_parts)

    # ── Build tree HTML ────────────────────────────────────────────────────
    sorted_details = sorted(details.items(),
                            key=lambda x: (x[1] == 'unchanged', x[1] != 'modified', x[0]))
    tree_html = _render_tree(_build_tree(sorted_details))

    # ── CSS ────────────────────────────────────────────────────────────────
    diff_css = ('''
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
        padding-right:8px; user-select:none; }'''
    ) if _diff_present[0] else ''

    html_doc = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Diff: {_h.escape(component_name)}</title>
  <style>
    body {{ font-family:"Segoe UI",Arial,sans-serif; margin:0; padding:0;
            background:#f6f8fa; color:#24292f; }}
    .header {{ background:#003366; color:#fff; padding:20px 32px; }}
    .header h1 {{ margin:0 0 4px; font-size:20px; }}
    .header .sub {{ font-size:13px; opacity:.75; }}
    .content {{ padding:28px 32px; max-width:1400px; margin:auto; }}
    .card {{ background:#fff; border:1px solid #d0d7de; border-radius:8px;
             padding:20px 24px; margin-bottom:20px; }}
    table.main-table {{ border-collapse:collapse; width:100%; }}
    table.main-table td {{ border-bottom:1px solid #d0d7de; }}
    h3 {{ color:#0d1117; font-size:15px; border-bottom:1px solid #d0d7de;
          padding-bottom:6px; margin-top:0; }}
    .rtc-tree {{ border:1px solid #d0d7de; border-radius:6px; overflow:hidden;
                 background:#fff; margin-top:10px; }}
    .rtc-folder {{ border-bottom:1px solid #eaecef; }}
    .rtc-folder-sum {{ cursor:pointer; padding:6px 10px; background:#f6f8fa;
                       display:block; list-style:none; font-size:13px; }}
    .rtc-folder-sum::-webkit-details-marker {{ display:none; }}
    .rtc-folder-sum:hover {{ background:#eaf3fb; }}
    .rtc-folder-body {{ padding-left:18px; border-left:2px solid #d0d7de; margin-left:10px; }}
    .rtc-file {{ display:flex; align-items:flex-start; flex-wrap:wrap;
                 padding:4px 10px; border-bottom:1px solid #f0f0f0;
                 font-family:"Segoe UI",Arial,sans-serif; }}
    .rtc-file:last-child {{ border-bottom:none; }}
    .rtc-file[data-status="unchanged"] {{ display:none; }}
    .file-icon {{ font-size:14px; margin-right:6px; flex-shrink:0; padding-top:1px; }}
    .file-name {{ font-family:Consolas,"Courier New",monospace; font-size:12px;
                  flex:1; word-break:break-all; min-width:100px; }}
    .file-status {{ font-size:11px; font-weight:600; margin-left:8px; white-space:nowrap; }}
    .file-badge {{ font-size:10px; margin-left:6px; padding:1px 7px; border-radius:10px; }}
    .file-badge-bin {{ background:#fff8c5; color:#9a6700; }}
    .file-badge-nc  {{ background:#f6f8fa; color:#aaa; }}
    .file-diff-details {{ width:100%; margin-top:5px; flex-basis:100%; }}
    .view-diff-btn {{ cursor:pointer; display:inline-block; padding:2px 10px;
                      border-radius:4px; color:#fff; font-size:11px; font-weight:600;
                      margin-left:8px; user-select:none; list-style:none; }}
    .view-diff-btn::-webkit-details-marker {{ display:none; }}
    .diff-panel {{ margin-top:4px; overflow-x:auto; border:1px solid #d0d7de; border-radius:4px; }}
    .diff-snap-bar {{ display:flex; justify-content:space-between; background:#003366;
                      color:#fff; font-size:11px; padding:5px 12px; font-family:monospace; }}
    .filter-bar {{ margin:10px 0 6px; display:flex; align-items:center; flex-wrap:wrap; gap:6px; }}
    .filter-btn {{ cursor:pointer; padding:3px 13px; border-radius:20px;
                   border:1px solid #d0d7de; font-size:12px; font-weight:600;
                   background:#f6f8fa; color:#57606a; opacity:0.4; transition:opacity 0.15s; }}
    .filter-btn.active {{ opacity:1; }}
    .filter-btn-all      {{ background:#e8eaf6; color:#3730a3; border-color:#a5b4fc; opacity:1; }}
    .filter-btn-modified {{ background:#fff8c5; color:#9a6700; border-color:#d4a72c; }}
    .filter-btn-added    {{ background:#dafbe1; color:#1a7f37; border-color:#82cfac; }}
    .filter-btn-removed  {{ background:#ffebe9; color:#cf222e; border-color:#ffaba8; }}
    .filter-btn-unchanged{{ background:#f6f8fa; color:#57606a; border-color:#d0d7de; }}
    {diff_css}
  </style>
</head>
<body>
  <div class="header">
    <h1>🔍 Online → Offline Component Diff</h1>
    <div class="sub">{_h.escape(component_name)}</div>
    <div class="sub">Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>
  </div>
  <div class="content">
    <div class="card">
      <h3>Comparison Summary</h3>
      <table class="main-table" style="font-size:13px;">
        <tr>
          <td style="padding:8px 12px;width:160px;color:#57606a;font-weight:600;">Component</td>
          <td style="padding:8px 12px;font-family:monospace;">{_h.escape(component_name)}</td>
        </tr>
        <tr style="background:#f6f8fa;">
          <td style="padding:8px 12px;color:#57606a;font-weight:600;">Online (RTC)</td>
          <td style="padding:8px 12px;">{_h.escape(snap1_label)}</td>
        </tr>
        <tr>
          <td style="padding:8px 12px;color:#57606a;font-weight:600;">Local Folder</td>
          <td style="padding:8px 12px;font-family:monospace;font-size:12px;">{_h.escape(local_folder_dir)}</td>
        </tr>
      </table>
    </div>

    <div class="card">
      <h3>File Changes</h3>
      <div style="margin-bottom:10px;">
        {badge("Modified",  n_mod,  STATUS_COLOR["modified"],  STATUS_BG["modified"])}
        {badge("Added",     n_add,  STATUS_COLOR["added"],     STATUS_BG["added"])}
        {badge("Removed",   n_rem,  STATUS_COLOR["removed"],   STATUS_BG["removed"])}
        {badge("Unchanged", n_unch, STATUS_COLOR["unchanged"], STATUS_BG["unchanged"])}
      </div>
      <div class="filter-bar">
        <span style="font-size:12px;color:#57606a;font-weight:600;margin-right:2px;">Filter:</span>
        <button class="filter-btn filter-btn-modified active" id="btn-modified"
                onclick="toggleFilter('modified')">± Modified ({n_mod})</button>
        <button class="filter-btn filter-btn-added active" id="btn-added"
                onclick="toggleFilter('added')">+ Added ({n_add})</button>
        <button class="filter-btn filter-btn-removed active" id="btn-removed"
                onclick="toggleFilter('removed')">− Removed ({n_rem})</button>
        <button class="filter-btn filter-btn-unchanged" id="btn-unchanged"
                onclick="toggleFilter('unchanged')">○ Unchanged ({n_unch})</button>
        <button class="filter-btn filter-btn-all" onclick="showAll()">▶ Show All</button>
      </div>
      <div class="rtc-tree">{tree_html}</div>
    </div>
  </div>

  <script>
  (function() {{
    var visible = {{modified:true, added:true, removed:true, unchanged:false}};
    function applyFilters() {{
      document.querySelectorAll('.rtc-folder').forEach(function(f){{f.style.display='none';}});
      document.querySelectorAll('.rtc-file').forEach(function(el) {{
        var s = el.getAttribute('data-status');
        var show = visible[s] !== false;
        el.style.display = show ? 'flex' : 'none';
        if (show) {{
          var p = el.parentElement;
          while (p) {{
            if (p.classList && p.classList.contains('rtc-folder')) p.style.display = '';
            p = p.parentElement;
          }}
        }}
      }});
      ['modified','added','removed','unchanged'].forEach(function(s) {{
        var b = document.getElementById('btn-'+s);
        if (b) {{ if (visible[s]) b.classList.add('active'); else b.classList.remove('active'); }}
      }});
    }}
    window.toggleFilter = function(s) {{ visible[s]=!visible[s]; applyFilters(); }};
    window.showAll = function() {{
      Object.keys(visible).forEach(function(k){{visible[k]=true;}}); applyFilters();
    }};
    document.addEventListener('DOMContentLoaded', applyFilters);
  }})();
  </script>
</body>
</html>'''

    try:
        with open(out_path, 'w', encoding='utf-8') as fh:
            fh.write(html_doc)
        return out_path
    except Exception:
        return None
