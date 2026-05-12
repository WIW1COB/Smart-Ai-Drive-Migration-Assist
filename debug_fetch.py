"""
debug_fetch.py  —  Standalone diagnostic for SCM file fetching.

Run from the project root:
    py debug_fetch.py

It will prompt for credentials, then test every step of the fetch pipeline
for the two known snapshots, printing exactly what each SCM command returns.
"""

import sys, os, subprocess, json, tempfile, getpass, re
sys.path.insert(0, os.path.dirname(__file__))

SCM = r"C:\Users\yyy1cob\Desktop\598_Kit_Download_Fail\Migration_Assist\EWM-scmTools-Win64-7.0.3\jazz\scmtools\eclipse\scm.exe"
REPO = "https://rb-alm-06-p.de.bosch.com/ccm"

SNAP1_UUID = "_BE1tdgcqEfGW-rzudwgDAg"   # Snapshot 1
SNAP2_UUID = "_Q6DB1ELHEfGFbcYEjnrD-Q"   # Snapshot 2

# ─────────────────────────────────────────────────────────────────────────────
print("=" * 70)
print("  SCM File Fetch Diagnostic")
print("=" * 70)

USER = input("RTC Username: ").strip()
PASS = getpass.getpass("RTC Password: ")

ENV = os.environ.copy()
for pv in ('HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','NO_PROXY','no_proxy'):
    ENV.pop(pv, None)

def run(cmd, timeout=60):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                       env=ENV, creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    return r.returncode, r.stdout.strip(), r.stderr.strip()

def section(title):
    print(f"\n{'─'*70}\n  {title}\n{'─'*70}")

# ═══════════════════════════════════════════════════════════════════════════
# STEP 1 — Login
# ═══════════════════════════════════════════════════════════════════════════
section("STEP 1: SCM login")
config_dir = tempfile.mkdtemp(prefix="scm_dbg_")
rc, out, err = run([SCM, "--non-interactive", "--config", config_dir,
                    "login", "-r", REPO, "-u", USER, "-P", PASS])
print(f"rc={rc}  stdout={out[:300]!r}  stderr={err[:300]!r}")
if rc != 0:
    print("❌ Login failed — check credentials / network. Aborting.")
    sys.exit(1)
print("✅ Login OK")

# ═══════════════════════════════════════════════════════════════════════════
# STEP 2 — List components in each snapshot
# ═══════════════════════════════════════════════════════════════════════════
section("STEP 2: List components in Snapshot 1 (scm list components -s)")
rc, out, err = run([SCM, "--non-interactive", "--config", config_dir,
                    "list", "components", "-s", SNAP1_UUID,
                    "-r", REPO, "-u", USER, "-P", PASS, "-j"])
print(f"rc={rc}  stderr={err[:300]!r}")
try:
    snap1_data = json.loads(out) if out else {}
    print(f"Top-level keys: {list(snap1_data.keys()) if isinstance(snap1_data,dict) else type(snap1_data).__name__}")
    print(f"stdout[:500]: {out[:500]!r}")
except Exception as e:
    print(f"JSON parse error: {e}")
    print(f"stdout[:500]: {out[:500]!r}")
    snap1_data = {}

# ═══════════════════════════════════════════════════════════════════════════
# STEP 3 — Find a baseline UUID to test with
# ═══════════════════════════════════════════════════════════════════════════
section("STEP 3: Extract a baseline UUID from snapshot 1")

# Try to pull baseline from snapshot components via REST
import urllib.request, urllib.error, base64

auth = base64.b64encode(f"{USER}:{PASS}".encode()).decode()
headers = {
    "Accept": "application/json",
    "Authorization": f"Basic {auth}",
    "OSLC-Core-Version": "2.0",
}

def rest_get(url):
    try:
        req = urllib.request.Request(url, headers=headers)
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, context=ctx, timeout=20) as r:
            return json.loads(r.read().decode('utf-8', errors='replace'))
    except Exception as e:
        print(f"  REST error: {e}")
        return None

snap_url = f"{REPO}/resource/itemOid/com.ibm.team.scm.Snapshot/{SNAP1_UUID}"
snap_json = rest_get(snap_url)
if snap_json:
    print(f"Snapshot REST keys: {list(snap_json.keys())}")
    baselines = snap_json.get('baselines', snap_json.get('baseline', []))
    print(f"baselines type: {type(baselines).__name__}  sample: {str(baselines)[:400]}")

# ═══════════════════════════════════════════════════════════════════════════
# STEP 4 — scm list files on a known component baseline
# ═══════════════════════════════════════════════════════════════════════════
section("STEP 4: scm list files -b <baseline_uuid> -j")

# Try with snapshot UUID first (some EWM builds support -s for list files)
print("\n-- Attempt A: list files -s <snapshot_uuid> (snapshot selector) --")
rc, out, err = run([SCM, "--non-interactive", "--config", config_dir,
                    "list", "files", "-s", SNAP1_UUID,
                    "-D", "all", "-j",
                    "-r", REPO, "-u", USER, "-P", PASS], timeout=120)
print(f"rc={rc}  len_stdout={len(out)}  stderr={err[:200]!r}")
if out:
    try:
        d = json.loads(out)
        print(f"Top-level keys: {list(d.keys()) if isinstance(d,dict) else 'list/other'}")
        print(f"stdout[:600]: {out[:600]!r}")
    except:
        print(f"stdout[:600]: {out[:600]!r}")

# Get the comparison results to find a real baseline UUID
print("\n-- Attempt B: read baseline_uuid from app comparison_results --")
# Try to read from any existing html diff (grab uuid from filename or file content)
html_dir_base = os.path.join(os.path.dirname(__file__), "Snapshot_Comparison_Results")
baseline_uuid_found = None
comp_name_found = None

for root, dirs, files in os.walk(html_dir_base):
    for fn in files:
        if fn.endswith('_diff.html'):
            fpath = os.path.join(root, fn)
            with open(fpath, encoding='utf-8', errors='replace') as fh:
                content = fh.read()
            # Look for a UUID pattern in the HTML
            m = re.search(r'[_]([A-Za-z0-9\-]{20,40})["\']', content)
            if m:
                candidate = '_' + m.group(1)
                if len(candidate) > 10:
                    baseline_uuid_found = candidate
                    break
    if baseline_uuid_found:
        break

if baseline_uuid_found:
    print(f"Found candidate baseline UUID from HTML: {baseline_uuid_found}")
    print(f"\n-- Attempt C: scm list files -b <baseline_uuid> -j --")
    rc, out, err = run([SCM, "--non-interactive", "--config", config_dir,
                        "list", "files", "-b",
                        "-D", "all", "-j",
                        "-r", REPO, "-u", USER, "-P", PASS,
                        baseline_uuid_found], timeout=180)
    print(f"rc={rc}  len_stdout={len(out)}  stderr={err[:300]!r}")
    if out:
        try:
            d = json.loads(out)
            print(f"Top-level keys: {list(d.keys()) if isinstance(d,dict) else 'list/other'}")
            # Show a sample file entry
            if isinstance(d, dict):
                if 'baseline' in d:
                    rf = d['baseline'].get('remote-files', [])
                    if rf:
                        print(f"\nSample remote-file entry ({len(rf)} total):")
                        print(json.dumps(rf[0], indent=2))
                for k, v in d.items():
                    if isinstance(v, list) and v:
                        print(f"\nField '{k}' has {len(v)} items, sample:")
                        print(json.dumps(v[0] if isinstance(v[0], dict) else v[:3], indent=2))
                        break
        except Exception as e:
            print(f"JSON error: {e}")
            print(f"stdout[:800]: {out[:800]!r}")
else:
    print("Could not find baseline UUID from HTML files — please provide one manually.")

# ═══════════════════════════════════════════════════════════════════════════
# STEP 5 — Test scm get file with item-id and state-id
# ═══════════════════════════════════════════════════════════════════════════
section("STEP 5: Test scm get file <item_id> <state_id> <output>")
print("(Requires a valid item-id and state-id from Step 4)")
item_id_test = input("Enter item-id (or press Enter to skip): ").strip()
state_id_test = input("Enter state-id (or press Enter to skip): ").strip()

if item_id_test and state_id_test:
    iid = item_id_test if item_id_test.startswith('_') else '_' + item_id_test
    sid = state_id_test if state_id_test.startswith('_') else '_' + state_id_test
    fd, tmp = tempfile.mkstemp(suffix='.txt')
    os.close(fd)
    print(f"\nRunning: scm get file {iid} {sid} {tmp}")
    rc, out, err = run([SCM, "--non-interactive", "--config", config_dir,
                        "get", "file", iid, sid, tmp,
                        "-r", REPO, "-u", USER, "-P", PASS])
    size = os.path.getsize(tmp) if os.path.exists(tmp) else 0
    print(f"rc={rc}  file_size={size}  stderr={err[:300]!r}")
    if size > 0:
        with open(tmp, 'r', encoding='utf-8', errors='replace') as f:
            preview = f.read(500)
        print(f"Content preview:\n{preview}")
        print("✅ scm get file by item/state WORKS!")
    else:
        print("❌ scm get file returned nothing")
    os.unlink(tmp)

    # Also test -b baseline form for comparison
    if baseline_uuid_found:
        print(f"\n-- Also test: scm get file <baseline> -b -f <filepath> --")
        fpath_test = input("Enter file path (or press Enter to skip): ").strip()
        if fpath_test:
            fd, tmp2 = tempfile.mkstemp(suffix='.txt')
            os.close(fd)
            rc2, out2, err2 = run([SCM, "--non-interactive", "--config", config_dir,
                                    "get", "file", baseline_uuid_found, "-b",
                                    "-f", fpath_test,
                                    "-r", REPO, "-u", USER, "-P", PASS,
                                    "-o", tmp2])
            size2 = os.path.getsize(tmp2) if os.path.exists(tmp2) else 0
            print(f"rc={rc2}  file_size={size2}  stderr={err2[:300]!r}")
            if size2 > 0:
                print("✅ scm get file -b WORKS!")
            os.unlink(tmp2)

# ═══════════════════════════════════════════════════════════════════════════
# STEP 6 — Check path matching between details and file_map
# ═══════════════════════════════════════════════════════════════════════════
section("STEP 6: Summary of findings")
print("""
Things to verify from the output above:
1. Step 1: Did login succeed?
2. Step 4: Did 'scm list files -b <uuid> -j' return JSON with a 'baseline' key?
   → Look at 'Top-level keys' and 'Sample remote-file entry'
   → Does the sample file entry have 'item-id' and 'state-id' fields?
3. Step 5: Did 'scm get file <item_id> <state_id>' work?
   → If yes → the new fetch_file_content_by_item_state will work
   → If no  → check if item-id/state-id from step 4 are actually populated

Share the full output of this script so the issue can be diagnosed precisely.
""")
