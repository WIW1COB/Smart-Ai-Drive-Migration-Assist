"""RTC Snapshot operations"""

import os
import subprocess
import json
import re
from src.config import settings


def fetch_snapshot_details(snapshot_url_or_id, username, password):
    """
    Fetch snapshot details from RTC using REST API.
    Returns snapshot information including name and UUID.
    Supports formats:
    - Direct UUID: _ojreQAAbEfG1br8X33nQcA
    - Web URL: https://rb-alm-06-p.de.bosch.com/ccm/web/projects/...&id=_i3S_vwAaEfG3rPS3zZLwKA&...
    - Resource URL: https://rb-alm-06-p.de.bosch.com/ccm/resource/itemOid/...
    """
    try:
        # Extract snapshot UUID from URL if needed
        snapshot_id = snapshot_url_or_id.strip()
        
        # Check if it's a web UI URL with id= parameter
        if "id=" in snapshot_id:
            # Extract UUID from id=_xxxxx format
            match = re.search(r'id=(_[a-zA-Z0-9_-]+)', snapshot_id)
            if match:
                snapshot_id = match.group(1)
                print(f"Extracted snapshot ID from web URL: {snapshot_id}")
        # Check if it's a resource URL format
        elif "/_" in snapshot_id:
            snapshot_id = snapshot_id.split("/_")[-1]
            if "?" in snapshot_id:
                snapshot_id = snapshot_id.split("?")[0]
            print(f"Extracted snapshot ID from resource URL: {snapshot_id}")
        # Otherwise assume it's a direct UUID
        else:
            print(f"Using direct snapshot UUID: {snapshot_id}")
        
        print(f"Fetching snapshot details for: {snapshot_id}")
        
        # Build REST API URL - use BaselineSet for snapshots
        api_url = f"{settings.RTC_SERVER_URL}/resource/itemOid/com.ibm.team.scm.BaselineSet/{snapshot_id}"
        
        cert_param = []
        if os.path.exists(settings.CERT_PATH):
            cert_param = ["--cacert", settings.CERT_PATH]
        
        curl_command = [
            "curl",
            "-k",
            "-L",
            "-u", f"{username}:{password}",
            *cert_param,
            "-X", "GET",
            "-H", "Accept: application/json",
            api_url
        ]
        
        print("Fetching snapshot details (timeout: 180s, please wait...)")
        result = subprocess.run(curl_command, capture_output=True, text=True, timeout=180)
        
        if result.returncode != 0:
            print(f"Failed to fetch snapshot: {result.stderr}")
            return None
        
        if not result.stdout.strip():
            print("No data returned from snapshot query")
            return None
        
        snapshot_data = json.loads(result.stdout)
        
        # Extract snapshot name from various possible fields
        snapshot_name = snapshot_data.get('name', 
                        snapshot_data.get('dc:title', 
                        snapshot_data.get('title', 'Unknown')))
        
        print(f"✓ Snapshot fetched: {snapshot_name}")
        print(f"  Snapshot details: name={snapshot_name}, itemId={snapshot_data.get('itemId', 'N/A')}")
        
        return snapshot_data
        
    except Exception as e:
        print(f"Error fetching snapshot details: {e}")
        import traceback
        traceback.print_exc()
        return None


def fetch_snapshot_components(snapshot_url_or_id, username, password, snapshot_details=None):
    """
    Fetch components from a snapshot.
    First tries using lscm CLI for faster results, falls back to REST API.
    Returns list of component dictionaries with name and uuid.
    """
    # Try lscm first
    components = fetch_components_using_lscm(snapshot_url_or_id, username, password)
    
    # Fallback to REST API if lscm fails
    if not components:
        components = fetch_components_using_rest_api(snapshot_url_or_id, username, password, snapshot_details)
    
    return components


def fetch_components_using_lscm(snapshot_url_or_id, username, password):
    """
    Fetch components from a snapshot using lscm (RTC SCM command-line tool).
    Returns list of component dictionaries with name and uuid.
    """
    # NOTE: This is a placeholder - Actual implementation from test.py lines 385-636
    # Should implement the full lscm-based component fetching logic
    print("fetch_components_using_lscm - TODO: Implement from test.py")
    return []


def fetch_components_using_rest_api(snapshot_url_or_id, username, password, snapshot_details=None):
    """
    Fetch components from a snapshot using RTC REST API.
    Returns list of component dictionaries with name and uuid.
    """
    # NOTE: This is a placeholder - Actual implementation from test.py lines 636-997
    # Should implement the full REST API-based component fetching logic
    print("fetch_components_using_rest_api - TODO: Implement from test.py")
    return []
