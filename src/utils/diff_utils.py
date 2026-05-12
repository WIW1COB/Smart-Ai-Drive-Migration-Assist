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
            uuid_str  = html_mod.escape(str(cs.get('uuid', '')))
            author    = html_mod.escape(str(cs.get('author', '—')))
            comment   = html_mod.escape(str(cs.get('comment', '')))
            ts        = html_mod.escape(str(cs.get('timestamp', '')))
            cs_rows += (
                f'<tr style="background:{bg};">'
                f'<td style="padding:5px 10px;font-family:monospace;font-size:11px;color:#57606a;">{uuid_str[:24]}</td>'
                f'<td style="padding:5px 10px;font-size:12px;color:#0d1117;">{author}</td>'
                f'<td style="padding:5px 10px;font-size:12px;white-space:pre-wrap;">{comment}</td>'
                f'<td style="padding:5px 10px;font-size:11px;color:#57606a;white-space:nowrap;">{ts}</td>'
                f'</tr>'
            )
        cs_table_html = f'''
      <h3 style="margin-top:20px;">Changesets in {html_mod.escape(snap2_label)}</h3>
      <table style="width:100%;border-collapse:collapse;font-size:13px;">
        <thead>
          <tr style="background:#24292f;color:#fff;">
            <th style="padding:6px 10px;text-align:left;width:160px;">Changeset UUID</th>
            <th style="padding:6px 10px;text-align:left;width:140px;">Author</th>
            <th style="padding:6px 10px;text-align:left;">Comment</th>
            <th style="padding:6px 10px;text-align:left;width:160px;">Timestamp</th>
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

    # ── Build inline diff HTML for a pair of text contents ────────────────
    def _make_inline_diff(snap1_text, snap2_text, fpath, fstatus):
        """Generate a side-by-side diff table embedded in the HTML report."""
        try:
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

    # ── Build the collapsible file list with optional inline diffs ─────────
    file_rows_html = ''
    inline_diffs_html = ''

    if details:
        sorted_files = sorted(details.items(), key=lambda x: (
            x[1] == 'unchanged',
            x[1] != 'modified',
            x[1] != 'added',
            x[1] != 'removed',
            x[0]
        ))

        diff_css_needed = False

        for fpath, fstatus in sorted_files:
            icon  = STATUS_ICON.get(fstatus, '?')
            color = STATUS_COLOR.get(fstatus, '#000')
            bg    = STATUS_BG.get(fstatus, '#fff')
            esc_path = html_mod.escape(fpath)
            file_id  = html_mod.escape(fpath.replace('/', '_').replace('.', '_').replace(' ', '_'))

            # Check if we have content for this file to generate a diff
            content_pair = fc_map.get(fpath) or {}
            snap1_text   = content_pair.get('snap1')
            snap2_text   = content_pair.get('snap2')
            has_diff     = (fstatus in ('modified', 'added', 'removed')
                            and (snap1_text is not None or snap2_text is not None))

            if has_diff and fstatus != 'unchanged':
                diff_css_needed = True
                diff_anchor = f'diff_{file_id}'
                file_rows_html += (
                    f'<tr style="background:{bg};">'
                    f'<td style="padding:5px 10px;color:{color};font-size:18px;text-align:center;">{icon}</td>'
                    f'<td style="padding:5px 12px;font-family:monospace;font-size:12px;">'
                    f'<a href="#{diff_anchor}" style="color:{color};text-decoration:none;"'
                    f' title="Click to jump to inline diff">{esc_path}</a></td>'
                    f'<td style="padding:5px 10px;color:{color};font-weight:600;font-size:12px;">'
                    f'{fstatus.capitalize()}</td>'
                    f'<td style="padding:5px 6px;">'
                    f'<a href="#{diff_anchor}" style="font-size:11px;color:{color};">▼ View diff</a></td>'
                    f'</tr>'
                )

                # Generate the inline diff section for this file
                diff_table = _make_inline_diff(snap1_text, snap2_text, fpath, fstatus)
                inline_diffs_html += f'''
                <details id="{diff_anchor}" style="margin-bottom:12px;" open>
                  <summary style="cursor:pointer;padding:8px 12px;background:{bg};
                           border:1px solid {color}33;border-radius:6px;
                           font-family:monospace;font-size:13px;color:{color};font-weight:600;">
                    {icon} {esc_path}
                    <span style="font-weight:normal;font-size:11px;margin-left:8px;">
                      ({fstatus.capitalize()}) — line-by-line comparison
                    </span>
                  </summary>
                  <div style="overflow-x:auto;margin-top:6px;border:1px solid #d0d7de;border-radius:4px;">
                    {diff_table}
                  </div>
                </details>'''
            else:
                file_rows_html += (
                    f'<tr style="background:{bg};">'
                    f'<td style="padding:5px 10px;color:{color};font-size:18px;text-align:center;">{icon}</td>'
                    f'<td style="padding:5px 12px;font-family:monospace;font-size:12px;">{esc_path}</td>'
                    f'<td style="padding:5px 10px;color:{color};font-weight:600;font-size:12px;">'
                    f'{fstatus.capitalize()}</td>'
                    f'<td style="padding:5px 6px;color:#aaa;font-size:11px;">'
                    f'{"(binary)" if fstatus != "unchanged" else ""}</td>'
                    f'</tr>'
                )

    # ── File change table ──────────────────────────────────────────────────
    file_table = ''
    if file_rows_html:
        has_diff_col = bool(inline_diffs_html)
        diff_col_header = '<th style="padding:7px 8px;text-align:left;width:80px;">Diff</th>' if has_diff_col else ''
        file_table = f'''
        <h3 style="margin-top:28px;">File-Level Changes</h3>
        <table style="width:100%;border-collapse:collapse;font-size:13px;">
          <thead>
            <tr style="background:#0d1117;color:#fff;">
              <th style="padding:7px 10px;width:36px;"></th>
              <th style="padding:7px 12px;text-align:left;">File Path</th>
              <th style="padding:7px 10px;text-align:left;width:110px;">Status</th>
              {diff_col_header}
            </tr>
          </thead>
          <tbody>{file_rows_html}</tbody>
        </table>'''
    elif has_file_data:
        file_table = '<p style="color:#57606a;margin-top:20px;">File details: counts retrieved but file list not available.</p>'
    else:
        file_table = '''
        <div style="margin-top:24px;padding:16px 20px;background:#fff8c5;border:1px solid #d4a72c;
                    border-radius:6px;color:#9a6700;">
          <strong>ℹ File-level detail not available</strong><br>
          The RTC folder/file listing API did not return file data for this component.<br>
          The component is marked <strong>Different</strong> because the two baselines have
          different UUIDs — baselines are immutable, so a different UUID means different content.
        </div>'''

    # ── Inline diff section ────────────────────────────────────────────────
    inline_diff_card = ''
    if inline_diffs_html:
        diff_count = inline_diffs_html.count('<details ')
        inline_diff_card = f'''
    <div class="card">
      <h3>📄 Line-by-Line File Comparisons ({diff_count} file{"s" if diff_count != 1 else ""})</h3>
      <p style="color:#57606a;font-size:12px;margin:0 0 14px;">
        Left panel = <strong>{html_mod.escape(snap1_label)}</strong> &nbsp;|&nbsp;
        Right panel = <strong>{html_mod.escape(snap2_label)}</strong>.
        Added lines are highlighted in green, removed in red, changed in yellow.
        Click a file header to collapse/expand.
      </p>
      {inline_diffs_html}
    </div>'''
    elif details and any(s in ('modified', 'added', 'removed') for s in details.values()):
        # There are changed files but no content was fetched (SCM CLI not available or binary)
        changed_count = sum(1 for s in details.values() if s in ('modified', 'added', 'removed'))
        inline_diff_card = f'''
    <div class="card" style="border-color:#d4a72c;">
      <h3>📄 Line-by-Line Diff</h3>
      <div style="padding:14px 16px;background:#fff8c5;border-radius:6px;color:#9a6700;">
        <strong>ℹ {changed_count} changed file{"s" if changed_count != 1 else ""} detected</strong> —
        inline content diff requires the EWM SCM CLI (<code>scm.exe</code>) to be configured
        and reachable.<br>
        <small>Set <code>LSCM_PATH</code> and <code>SKIP_SCM_CLI = False</code> in
        <code>src/config/settings.py</code> to enable inline diffs.</small>
      </div>
    </div>'''

    # ── difflib CSS (needed when inline diffs are present) ─────────────────
    difflib_css = ''
    if inline_diffs_html:
        difflib_css = '''
    /* difflib side-by-side diff table styles */
    .diff_header { background-color:#F8B862; }
    td.diff_header { text-align:right; }
    .diff_next { background-color:#c0c0c0; }
    .diff_add { background-color:#aaffaa; }
    .diff_chg { background-color:#ffff77; }
    .diff_sub { background-color:#ffaaaa; }
    table.diff { font-family: Consolas, "Courier New", monospace; font-size:12px;
                 border-collapse:collapse; width:100%; }
    table.diff td { padding:2px 6px; white-space:pre-wrap; word-break:break-all; }
    table.diff th { padding:4px 6px; background:#24292f; color:#fff; font-weight:600; }
    table.diff td:first-child, table.diff td:nth-child(3) {
        color:#57606a; font-size:11px; min-width:36px; text-align:right;
        padding-right:8px; user-select:none; }
    details > summary { list-style:none; }
    details > summary::-webkit-details-marker { display:none; }'''

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
          <td style="padding:8px 12px;"><span class="uuid">{html_mod.escape(baseline1_uuid)}</span></td></tr>
        <tr style="background:#f6f8fa;">
          <td style="padding:8px 12px;color:#57606a;font-weight:600;">{html_mod.escape(snap2_label)}</td>
          <td style="padding:8px 12px;"><span class="uuid">{html_mod.escape(baseline2_uuid)}</span></td></tr>
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
