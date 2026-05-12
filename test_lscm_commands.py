"""
Diagnostic Script to Test LSCM Commands for File Comparison
This will help identify why file diffs are not being generated
"""

import subprocess
import os
import json

# Configuration
LSCM_PATH = r"C:\toolbase\lscm\7.0.3\jazz\scmtools\eclipse\scm.exe"
RTC_SERVER = "https://rb-alm-06-p.de.bosch.com/ccm"

# Test credentials (will be entered interactively)
username = input("Enter RTC username: ")
password = input("Enter RTC password: ")

# Test baseline UUIDs (from one of the modified components)
# You can get these from the CSV file for any "Different" component
baseline1_uuid = input("Enter Baseline 1 UUID (from snapshot 1): ")
baseline2_uuid = input("Enter Baseline 2 UUID (from snapshot 2): ")

print("\n" + "=" * 80)
print("TESTING LSCM COMMANDS")
print("=" * 80)

# Test 1: Check if lscm exists
print("\n1. Checking if lscm.exe exists...")
if os.path.exists(LSCM_PATH):
    print(f"   ✓ Found: {LSCM_PATH}")
else:
    print(f"   ✗ NOT FOUND: {LSCM_PATH}")
    print("   Please update LSCM_PATH in this script")
    exit(1)

# Test 2: List files from baseline 1
print("\n2. Testing: lscm list files from Baseline 1...")
cmd = [
    LSCM_PATH,
    'list', 'files',
    '-b', baseline1_uuid,
    '-r', RTC_SERVER,
    '-u', username,
    '-P', password,
    '-D', 'all',
    '-j'
]

print(f"   Command: lscm list files -b {baseline1_uuid[:12]}... -r {RTC_SERVER} -u {username} -P **** -D all -j")

try:
    # Remove proxy
    env = os.environ.copy()
    for pv in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'NO_PROXY', 'no_proxy']:
        env.pop(pv, None)
    
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
        env=env
    )
    
    print(f"   Exit code: {result.returncode}")
    
    if result.returncode != 0:
        print(f"   ✗ Command failed!")
        print(f"   Stderr: {result.stderr[:500]}")
    
    if not result.stdout or not result.stdout.strip():
        print(f"   ✗ No output!")
        print(f"   Stderr: {result.stderr[:500]}")
    else:
        print(f"   ✓ Got output ({len(result.stdout)} bytes)")
        
        # Try to parse JSON
        try:
            data = json.loads(result.stdout)
            baseline_data = data.get('baseline', {})
            remote_files = baseline_data.get('remote-files', [])
            
            files = [f for f in remote_files if f.get('path', '').strip('/') and not f.get('path', '').endswith('/')]
            
            print(f"   ✓ Parsed JSON successfully")
            print(f"   ✓ Found {len(files)} files in baseline")
            
            if files:
                print(f"\n   Sample files (first 5):")
                for f in files[:5]:
                    path = f.get('path', '').strip('/')
                    content_id = f.get('content-id', 'N/A')
                    print(f"      - {path} (content-id: {content_id[:12]}...)")
            
        except json.JSONDecodeError as e:
            print(f"   ✗ Failed to parse JSON: {e}")
            print(f"   Output (first 500 chars): {result.stdout[:500]}")

except subprocess.TimeoutExpired:
    print(f"   ✗ Command timed out after 120 seconds")
except Exception as e:
    print(f"   ✗ Error: {e}")

# Test 3: List files from baseline 2
print("\n3. Testing: lscm list files from Baseline 2...")
cmd[4] = baseline2_uuid

try:
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
        env=env
    )
    
    print(f"   Exit code: {result.returncode}")
    
    if result.stdout and result.stdout.strip():
        try:
            data = json.loads(result.stdout)
            baseline_data = data.get('baseline', {})
            remote_files = baseline_data.get('remote-files', [])
            files = [f for f in remote_files if f.get('path', '').strip('/') and not f.get('path', '').endswith('/')]
            print(f"   ✓ Found {len(files)} files in baseline 2")
        except:
            print(f"   ✗ Failed to parse JSON")
    else:
        print(f"   ✗ No output from baseline 2")

except Exception as e:
    print(f"   ✗ Error: {e}")

# Test 4: Try to download a file
if 'files' in locals() and files:
    print("\n4. Testing: lscm get file (download)...")
    test_file = files[0].get('path', '').strip('/')
    
    if not test_file.startswith('/'):
        test_file = '/' + test_file
    
    print(f"   Downloading test file: {test_file}")
    
    import tempfile
    with tempfile.TemporaryDirectory() as temp_dir:
        output_file = os.path.join(temp_dir, os.path.basename(test_file))
        
        cmd = [
            LSCM_PATH,
            'get', 'file',
            baseline1_uuid,
            '-b',
            '-f', test_file,
            '-r', RTC_SERVER,
            '-u', username,
            '-P', password,
            '-o',
            output_file
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=90,
                env=env
            )
            
            print(f"   Exit code: {result.returncode}")
            
            if result.returncode == 0 and os.path.exists(output_file):
                file_size = os.path.getsize(output_file)
                print(f"   ✓ File downloaded successfully ({file_size} bytes)")
            else:
                print(f"   ✗ File download failed")
                print(f"   Stderr: {result.stderr[:500]}")
                print(f"   Stdout: {result.stdout[:500]}")
        
        except subprocess.TimeoutExpired:
            print(f"   ✗ Download timed out")
        except Exception as e:
            print(f"   ✗ Error: {e}")

print("\n" + "=" * 80)
print("DIAGNOSTIC COMPLETE")
print("=" * 80)
print("\nIf you see failures above, that explains why file diffs aren't being generated.")
print("Common issues:")
print("  - Incorrect lscm path")
print("  - Network/VPN not connected")
print("  - Invalid credentials")
print("  - Baseline UUIDs are incorrect")
print("  - Firewall blocking lscm")
