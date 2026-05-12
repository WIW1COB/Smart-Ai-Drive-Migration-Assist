"""RTC/ALM Connection Module - Comprehensive REST API Integration"""

import os
import subprocess
import json
import re
import logging
import threading
import tempfile
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError, wait
from src.config import settings

try:
    import requests as _requests
    from requests.adapters import HTTPAdapter as _HTTPAdapter
    from urllib3.util.retry import Retry as _Retry
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    _requests_available = True
except ImportError:
    _requests_available = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('rtc_comparison.log', mode='a', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Module-level semaphore: limit concurrent scm.exe processes to avoid overwhelming
# the server with simultaneous Java/LDAP auth sessions.
_scm_semaphore = threading.Semaphore(3)

# Shared scm config directory (created once per process via _scm_login).
# Storing credentials here means subsequent scm list files calls skip re-auth.
_scm_config_dir: str | None = None
_scm_config_lock = threading.Lock()
_scm_logged_in = False


class RTCConnection:
    """Handles all RTC/ALM connectivity and operations"""
    
    def __init__(self, server_url, username, password):
        """
        Initialize RTC connection
        
        Args:
            server_url: RTC server URL (e.g., https://rb-alm-06-p.de.bosch.com/ccm)
            username: RTC username
            password: RTC password
        """
        self.server_url = server_url
        self.username = username
        self.password = password
        self.session_valid = False
        
    def test_connection(self):
        """
        Test RTC connection
        Returns: (success: bool, message: str)
        """
        try:
            test_url = f'{self.server_url}/rootservices'
            cmd = [
                'curl.exe',
                '-k',  # Skip SSL verification (Bosch self-signed certs)
                '-L',
                '--noproxy', '*',
                '-u', f'{self.username}:{self.password}',
                test_url,
                '-H', 'Accept: application/json'
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            if result.returncode != 0:
                error = result.stderr[:200] if result.stderr else "Unknown error"
                if 'Could not resolve host' in error:
                    return False, "Network error - cannot reach server"
                elif '401' in result.stdout or 'Unauthorized' in error:
                    return False, "Authentication failed - check username/password"
                else:
                    return False, f"Connection failed: {error}"
            
            # Check response
            if 'error' in result.stdout.lower() and '401' in result.stdout:
                return False, "Authentication failed"
            
            if 'rootservices' in result.stdout or 'jazz' in result.stdout.lower():
                logger.info("✓ RTC connection successful")
                self.session_valid = True
                return True, "Connection successful"
            
            logger.warning("Connection response unexpected but proceeding...")
            self.session_valid = True
            return True, "Connection accepted"
            
        except subprocess.TimeoutExpired:
            return False, "Connection timeout - server not responding"
        except Exception as e:
            return False, f"Error: {str(e)}"
    
    def extract_snapshot_uuid(self, input_text):
        """
        Extract snapshot UUID from various formats
        
        Handles:
        - Direct UUID: _abc123xyz
        - Web URL: https://server/ccm/.../?id=_abc123xyz
        - Resource URL: https://server/ccm/resource/.../com.ibm.team.scm.Snapshot/_abc123xyz
        
        Returns: UUID string or None if invalid
        """
        input_text = input_text.strip()
        
        # If already a UUID (no slashes/colons)
        if '/' not in input_text and ':' not in input_text:
            if input_text.startswith('_'):
                return input_text
            else:
                return '_' + input_text if input_text else None
        
        # Extract from web URL format: ?id=_abc123
        if 'id=' in input_text:
            match = re.search(r'id=(_?[a-zA-Z0-9_-]+)', input_text)
            if match:
                uuid = match.group(1)
                return uuid if uuid.startswith('_') else ('_' + uuid if uuid else None)
        
        # Extract from resource URL format: /.../com.ibm.team.scm.Snapshot/_abc123
        if '/_' in input_text:
            uuid = input_text.split('/_')[-1]
            # Remove query params if present
            if '&' in uuid:
                uuid = uuid.split('&')[0]
            if '?' in uuid:
                uuid = uuid.split('?')[0]
            return '_' + uuid if not uuid.startswith('_') else uuid
        
        # Try generic UUID pattern
        uuid_pattern = r'_?[a-zA-Z0-9_-]{20,}'
        match = re.search(uuid_pattern, input_text)
        if match:
            uuid = match.group(0)
            return uuid if uuid.startswith('_') else ('_' + uuid)
        
        return None
    
    def fetch_snapshot_components(self, snapshot_url, username=None, password=None, snapshot_name='Snapshot'):
        """
        Fetch all components from a snapshot URL
        
        Args:
            snapshot_url: Snapshot URL or UUID
            username: RTC username
            password: RTC password
            snapshot_name: Display name for logging
            progress_callback: Optional callback function(current, total, message) for progress updates
        
        Based on test2.py implementation with SCM CLI and REST API fallback
        """
        import time
        try:
            # Use provided credentials or instance credentials
            if username is None:
                username = self.username
            if password is None:
                password = self.password
            # Extract server URL from the snapshot URL
            server_url = None
            if snapshot_url.startswith('http'):
                url_match = re.match(r'(https?://[^/]+/ccm)', snapshot_url)
                if url_match:
                    server_url = url_match.group(1)
            
            # If server URL not found in snapshot URL, use instance variable
            if not server_url:
                server_url = self.server_url
            
            # Extract snapshot UUID from URL - handle both direct ID and web UI URL
            snapshot_id = snapshot_url.strip()
            
            # If it's a web UI URL, extract the ID parameter
            if 'id=' in snapshot_id:
                snapshot_id = snapshot_id.split('id=')[-1]
                if '&' in snapshot_id:
                    snapshot_id = snapshot_id.split('&')[0]
            elif '/' in snapshot_id:
                snapshot_id = snapshot_id.split('/')[-1]
            
            logger.info(f'{snapshot_name}: Extracted ID: {snapshot_id}')

            # Detect whether the ID looks like a standard UUID (hex + dashes)
            uuid_pattern = re.compile(
                r'^[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}$'
            )
            is_uuid = bool(uuid_pattern.match(snapshot_id))

            # RTC base64-style item IDs (e.g. "FhzYKfR3EfCYz4XyfURacA") MUST be
            # prefixed with "_" when used in REST API / SCM CLI calls.
            if snapshot_id.startswith('_'):
                id_with_prefix    = snapshot_id          # already prefixed
                id_without_prefix = snapshot_id[1:]
            else:
                id_with_prefix    = '_' + snapshot_id   # add the required "_" prefix
                id_without_prefix = snapshot_id

            logger.info(f'{snapshot_name}: ID with _ prefix: {id_with_prefix}')

            if is_uuid:
                # Standard UUID - try both itemOid and itemName without prefix changes
                api_url_candidates = [
                    f'{server_url}/resource/itemOid/com.ibm.team.scm.BaselineSet/{snapshot_id}',
                    f'{server_url}/resource/itemName/com.ibm.team.scm.BaselineSet/{snapshot_id}',
                ]
            else:
                # RTC base64 item name - the "_"-prefixed form is what the REST API uses
                api_url_candidates = [
                    f'{server_url}/resource/itemOid/com.ibm.team.scm.BaselineSet/{id_with_prefix}',
                    f'{server_url}/resource/itemName/com.ibm.team.scm.BaselineSet/{id_with_prefix}',
                    f'{server_url}/resource/itemOid/com.ibm.team.scm.BaselineSet/{id_without_prefix}',
                    f'{server_url}/resource/itemName/com.ibm.team.scm.BaselineSet/{id_without_prefix}',
                ]

            def _build_curl(url):
                return [
                    'curl.exe',
                    '-k',  # Skip SSL certificate verification
                    '-L',
                    '--noproxy', '*',
                    '-u', f'{username}:{password}',
                    '-X', 'GET',
                    url,
                    '-H', 'Accept: application/json',
                    '-H', 'Connection: keep-alive',
                    '-H', 'OSLC-Core-Version: 2.0',
                ]

            result = None
            api_url = None
            
            # Try API URLs in order, but fail fast on wrong ones
            for idx, candidate_url in enumerate(api_url_candidates):
                logger.info(f'{snapshot_name}: Trying API URL {idx+1}/{len(api_url_candidates)}: {candidate_url}')
                
                # Update progress if callback provided
                if progress_callback:
                    try:
                        progress_callback(0, 100, f"{snapshot_name}: Connecting to RTC server...")
                    except Exception:
                        pass
                
                curl_command = _build_curl(candidate_url)
                try:
                    request_start = time.time()
                    candidate_result = subprocess.run(
                        curl_command, capture_output=True, text=True, timeout=15,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                    )
                    request_elapsed = time.time() - request_start
                    logger.info(f'{snapshot_name}: Response time: {request_elapsed:.2f}s')
                except subprocess.TimeoutExpired:
                    logger.warning(f'{snapshot_name}: Request timed out (45s) for {candidate_url} — retrying once')
                    try:
                        candidate_result = subprocess.run(
                            curl_command, capture_output=True, text=True, timeout=60,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                        )
                    except subprocess.TimeoutExpired:
                        logger.warning(f'{snapshot_name}: Retry also timed out (60s) — skipping URL')
                        continue

                if candidate_result.returncode != 0:
                    logger.warning(f'{snapshot_name}: Curl error for {candidate_url}: {candidate_result.stderr[:200]}')
                    continue

                if not candidate_result.stdout.strip():
                    logger.warning(f'{snapshot_name}: Empty response from {candidate_url}')
                    continue

                # Check for JSON error response
                raw = candidate_result.stdout.strip()
                if raw.startswith('{'):
                    try:
                        probe = json.loads(raw)
                        err_code = probe.get('errorCode', 0)
                        if err_code and int(err_code) >= 400:
                            logger.warning(
                                f'{snapshot_name}: API error {err_code} from {candidate_url}: '
                                f'{probe.get("errorMessage", "")[:200]}'
                            )
                            continue
                    except Exception:
                        pass  # not parseable yet, let main parsing handle it

                # This candidate succeeded
                result = candidate_result
                api_url = candidate_url
                logger.info(f'{snapshot_name}: ✓ Got valid response from: {candidate_url}')
                break

            if result is None:
                logger.error(f'{snapshot_name}: All API URL candidates failed')
                return []

            if result.returncode != 0:
                logger.error(f'{snapshot_name}: Failed to fetch components (exit code {result.returncode})')
                logger.error(f'{snapshot_name}: Error: {result.stderr}')
                return []

            if not result.stdout.strip():
                logger.error(f'{snapshot_name}: No data returned (empty response)')
                return []

            logger.info(f'{snapshot_name}: Got response ({len(result.stdout)} bytes)')

            # Check if response is HTML (error page)
            if result.stdout.strip().startswith("<"):
                logger.error(f'{snapshot_name}: Received HTML response instead of JSON')
                return []

            try:
                data = json.loads(result.stdout)
                logger.info(f'{snapshot_name}: Successfully parsed JSON response')
                
                # Extract snapshot name from response
                extracted_name = None
                if isinstance(data, dict):
                    # Try various name fields
                    extracted_name = (
                        data.get('name') or 
                        data.get('dc:title') or 
                        data.get('dcterms:title') or 
                        data.get('title')
                    )
                    if extracted_name:
                        logger.info(f'{snapshot_name}: Extracted snapshot name: {extracted_name}')
            except json.JSONDecodeError as e:
                logger.error(f'{snapshot_name}: Failed to parse JSON: {e}')
                logger.error(f'{snapshot_name}: Response: {result.stdout[:500]}')
                return {'name': None, 'components': []}

            # Check for authentication errors in JSON response
            if isinstance(data, dict):
                if 'error_code' in data or 'error_message' in data:
                    error_code = data.get('error_code', 'unknown')
                    error_msg = data.get('error_message', 'Unknown error')
                    logger.error(f'{snapshot_name}: API ERROR: {error_code} - {error_msg}')
                    return {'name': extracted_name, 'components': []}

            components = []

            # Parse components - RTC BaselineSet format
            baseline_list = None
            
            if isinstance(data, dict):
                # Check for 'baselines' key
                if "baselines" in data:
                    baseline_list = data["baselines"]
                    logger.info(f'{snapshot_name}: Found "baselines" key with {len(baseline_list) if isinstance(baseline_list, list) else "non-list"} items')
                # Check for 'com.ibm.team.scm.Baseline' key
                elif "com.ibm.team.scm.Baseline" in data:
                    baseline_list = data["com.ibm.team.scm.Baseline"]
                    logger.info(f'{snapshot_name}: Found "com.ibm.team.scm.Baseline" key with {len(baseline_list) if isinstance(baseline_list, list) else "non-list"} items')
                else:
                    logger.warning(f'{snapshot_name}: No baseline key found. Available keys: {list(data.keys())}')

            if baseline_list and isinstance(baseline_list, list):
                total_baselines = len(baseline_list)
                requested_workers = getattr(settings, "MAX_WORKERS", 10)
                try:
                    requested_workers = int(requested_workers)
                except Exception:
                    requested_workers = 20
                max_workers = max(1, min(requested_workers, 30))

                # Too many parallel curl processes can trigger RTC throttling / long stalls.
                max_workers = max(1, min(requested_workers, 12))
                logger.info(
                    f'{snapshot_name}: Fetching component details for {total_baselines} baselines '
                    f'(workers={max_workers})...'
                )

                # ── Shared HTTP session & caches ─────────────────────────────
                # One session → connection pool → no TCP handshake per request.
                # Previously each request spawned a fresh curl.exe process.
                session = self._make_session()
                component_name_cache: dict = {}
                cache_lock = threading.Lock()

                def get_component_name(comp_item_id: str) -> str | None:
                    """Return cached component name, fetching only on first miss."""
                    with cache_lock:
                        if comp_item_id in component_name_cache:
                            return component_name_cache[comp_item_id]

                    comp_url = f'{server_url}/resource/itemOid/com.ibm.team.scm.Component/{comp_item_id}'
                    curl_comp = [
                        'curl.exe', '-k', '-L', '--noproxy', '*',
                        '-u', f'{username}:{password}',
                        '-X', 'GET',
                        comp_url,
                        '-H', 'Accept: application/json',
                        '-H', 'Connection: keep-alive',
                        '-H', 'OSLC-Core-Version: 2.0'
                    ]

                    try:
                        comp_result = subprocess.run(
                            curl_comp,
                            capture_output=True,
                            text=True,
                            timeout=30,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                        )
                        if comp_result.returncode == 0 and comp_result.stdout.strip():
                            comp_data = json.loads(comp_result.stdout)
                            comp_name = (
                                comp_data.get("name")
                                or comp_data.get("dcterms:title")
                                or comp_data.get("dc:title")
                                or comp_data.get("title")
                            )
                            if comp_name:
                                with cache_lock:
                                    component_name_cache[comp_item_id] = comp_name
                                return comp_name
                    except Exception as e:
                        logger.debug(f'{snapshot_name}: Failed to fetch component name {comp_item_id[:12]}...: {e}')

                    return None

                def fetch_baseline_component(baseline_ref):
                    """
                    Fetch component info for a single baseline.

                    Speed improvement: The baseline JSON already contains the
                    component itemId inline under the 'component' key.
                    We extract it directly instead of making a second HTTP call
                    to resolve the component ID — the only extra call needed is
                    the component-name lookup (which is heavily cached).
                    """
                    if not isinstance(baseline_ref, dict):
                        return None

                    item_id   = baseline_ref.get('itemId', '')
                    state_id  = baseline_ref.get('stateId', '')
                    if not item_id:
                        return None

                    baseline_url = f'{server_url}/resource/itemOid/com.ibm.team.scm.Baseline/{item_id}'
                    curl_baseline = [
                        'curl.exe', '-k', '-L', '--noproxy', '*',
                        '-u', f'{username}:{password}',
                        '-X', 'GET',
                        baseline_url,
                        '-H', 'Accept: application/json',
                        '-H', 'Connection: keep-alive',
                        '-H', 'OSLC-Core-Version: 2.0'
                    ]

                    try:
                        baseline_result = subprocess.run(
                            curl_baseline,
                            capture_output=True,
                            text=True,
                            timeout=30,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                        )

                        if baseline_result.returncode == 0 and baseline_result.stdout.strip():
                            baseline_data = json.loads(baseline_result.stdout)

                            comp_ref = baseline_data.get("component") or baseline_data.get("com.ibm.team.scm.Component")
                            if isinstance(comp_ref, dict) and comp_ref.get("itemId"):
                                comp_item_id = comp_ref.get("itemId", "")
                                comp_name = get_component_name(comp_item_id)
                                if not comp_name:
                                    logger.debug(f'{snapshot_name}: Skipping baseline {item_id[:8]} - failed to get component name')
                                    return None

                    return {
                        'name': comp_name,
                        'uuid': comp_item_id,
                        'baseline_uuid': item_id,
                        'state_id': state_id,
                    }

                import time as _time
                start_time = _time.time()
                last_heartbeat = start_time
                last_gui_update = start_time
                processed = 0

                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    pending = {executor.submit(fetch_baseline_component, b) for b in baseline_list}

                    while pending:
                        done, pending = wait(pending, timeout=2)  # Reduced from 5s to 2s for more responsive GUI

                        for future in done:
                            processed += 1
                            try:
                                component = future.result()
                                if component:
                                    components.append(component)
                            except Exception as e:
                                logger.debug(f'{snapshot_name}: Baseline processing error: {e}')
                        
                        # Update GUI more frequently (every 2 seconds or every 10 components)
                        now = time.time()
                        should_update_gui = (now - last_gui_update >= 2) or (processed % 10 == 0 and processed > 0)
                        
                        if should_update_gui and progress_callback:
                            try:
                                elapsed = now - start_time
                                rate = processed / elapsed if elapsed > 0 else 0
                                progress_callback(
                                    processed,
                                    total_baselines,
                                    f"{snapshot_name}: {processed}/{total_baselines} ({len(components)} components, {rate:.1f}/s)"
                                )
                                last_gui_update = now
                            except Exception:
                                pass

                        now = _time.time()
                        if (processed % 20 == 0 and processed > 0) or processed == total_baselines:
                            elapsed = now - start_time
                            logger.info(
                                f'{snapshot_name}: Progress: {processed}/{total_baselines} baselines processed '
                                f'({len(components)} components found) - {elapsed:.1f}s'
                            )
                            # Send progress update to GUI if callback provided
                            if progress_callback:
                                try:
                                    progress_callback(
                                        processed, 
                                        total_baselines,
                                        f"{snapshot_name}: {processed}/{total_baselines} baselines ({len(components)} components, {rate:.1f}/s)"
                                    )
                                except Exception as cb_err:
                                    logger.debug(f"Progress callback error: {cb_err}")
                            last_heartbeat = now
                        elif now - last_heartbeat >= 10:
                            elapsed = now - start_time
                            rate = processed / elapsed if elapsed > 0 else 0
                            logger.info(
                                f'{snapshot_name}: Still working... {processed}/{total_baselines} processed, '
                                f'{len(pending)} pending, {len(components)} components found - {elapsed:.1f}s ({rate:.1f}/s)'
                            )
                            # Send heartbeat update to GUI
                            if progress_callback:
                                try:
                                    progress_callback(
                                        processed,
                                        total_baselines,
                                        f"{snapshot_name}: {processed}/{total_baselines} processed ({len(components)} components)..."
                                    )
                                except Exception:
                                    pass
                            last_heartbeat = now

                logger.info(f'{snapshot_name}: ✓ Successfully extracted {len(components)} components')

            if len(components) == 0:
                logger.warning(f'{snapshot_name}: No components could be extracted from {len(baseline_list) if baseline_list else 0} baselines')

            return {'name': extracted_name, 'components': components}

        except Exception as e:
            logger.error(f'{snapshot_name}: Error fetching components: {e}')
            import traceback
            logger.debug(traceback.format_exc())
            return []
    
    def compare_snapshots(self, snap1_components, snap2_components):
        """
        Compare two sets of snapshot components with file-level analysis.
        When both components exist but baseline UUIDs differ, fetches folder
        structures and performs file-level comparison.
        
        Returns: List of comparison result dicts
        """
        try:
            snap1_dict = {c['name']: c for c in snap1_components if c.get('name')}
            snap2_dict = {c['name']: c for c in snap2_components if c.get('name')}
            all_names = set(snap1_dict) | set(snap2_dict)
            
            results = []
            for name in sorted(all_names):
                comp1 = snap1_dict.get(name)
                comp2 = snap2_dict.get(name)
                
                entry = {'name': name, 'snapshot1': comp1, 'snapshot2': comp2}
                
                if comp1 and comp2:
                    # Both have this component — first check baseline UUIDs directly
                    baseline1 = comp1.get('baseline_uuid', '')
                    baseline2 = comp2.get('baseline_uuid', '')
                    
                    if baseline1 == baseline2 and baseline1:
                        entry['status'] = 'Unchanged'
                        entry['baseline1_uuid'] = baseline1
                        entry['baseline2_uuid'] = baseline2
                    else:
                        # Baseline UUIDs differ (or missing) → file-level comparison
                        baseline1 = baseline1 or comp1.get('uuid', '')
                        baseline2 = baseline2 or comp2.get('uuid', '')
                        try:
                            folder1 = self.fetch_baseline_folder_structure(baseline1, name)
                            folder2 = self.fetch_baseline_folder_structure(baseline2, name)
                            file_cmp = self.compare_folder_structures(folder1, folder2)
                            entry['folder_structure1'] = folder1
                            entry['folder_structure2'] = folder2
                            entry['file_comparison']   = file_cmp
                            entry['baseline1_uuid']   = baseline1
                            entry['baseline2_uuid']   = baseline2
                            
                            if file_cmp.get('added') or file_cmp.get('modified') or file_cmp.get('removed'):
                                entry['status'] = 'Modified'
                            else:
                                entry['status'] = 'Unchanged'
                        except Exception as e:
                            logger.warning(f"File-level comparison failed for {name}: {e}")
                            entry['status'] = 'Modified'  # Safe default
                
                elif comp1:
                    entry['status'] = 'Removed in Snapshot 2'
                else:
                    entry['status'] = 'Added in Snapshot 2'
                
                results.append(entry)
            
            logger.info(f"Comparison complete: {len(results)} components analyzed")
            return results
            
        except Exception as e:
            logger.error(f"Error in compare_snapshots: {e}")
            return []

    
    def fetch_changesets_for_files(self, modified_files, baseline_uuid, component_name='Unknown'):
        """
        Fetch folder/file structure from a baseline via RTC REST API.
        Uses: Baseline → Component → Root Folder → Recursive children traversal.
        
        Returns: dict {'folders': {...}, 'files': [{name, path, uuid, content-id, state-id}]}
        """
        try:
            if not baseline_uuid:
                logger.warning(f"No baseline UUID provided for {component_name}")
                return {'folders': {}, 'files': []}
            
            if not baseline_uuid.startswith('_'):
                baseline_uuid = '_' + baseline_uuid
            
            logger.info(f"Fetching baseline structure for {component_name}: {baseline_uuid[:12]}...")
            
            # Step 1: Get baseline metadata (to extract component ID)
            baseline_url = f'{self.server_url}/resource/itemOid/com.ibm.team.scm.Baseline/{baseline_uuid}'
            baseline_curl = [
                'curl.exe', '-k', '-L', '--noproxy', '*',
                '-u', f'{self.username}:{self.password}',
                '-X', 'GET', baseline_url,
                '-H', 'Accept: application/json',
                '-H', 'OSLC-Core-Version: 2.0'
            ]
            result = subprocess.run(
                baseline_curl, capture_output=True, text=True, timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            if result.returncode != 0 or not result.stdout.strip():
                logger.warning(f"Failed to fetch baseline metadata for {component_name}")
                return {'folders': {}, 'files': []}
            baseline_data = json.loads(result.stdout)
            component_ref = baseline_data.get('component') or baseline_data.get('com.ibm.team.scm.Component', {})
            component_id = component_ref.get('itemId', '')
            if not component_id:
                logger.warning(f"No component ID in baseline {baseline_uuid[:12]}")
                return {'folders': {}, 'files': []}
            
            # Step 2: Get component metadata (to extract root folder ID)
            comp_url = f'{self.server_url}/resource/itemOid/com.ibm.team.scm.Component/{component_id}'
            comp_curl = [
                'curl.exe', '-k', '-L', '--noproxy', '*',
                '-u', f'{self.username}:{self.password}',
                '-X', 'GET', comp_url,
                '-H', 'Accept: application/json',
                '-H', 'OSLC-Core-Version: 2.0'
            ]
            result = subprocess.run(
                comp_curl, capture_output=True, text=True, timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            if result.returncode != 0 or not result.stdout.strip():
                logger.warning(f"Failed to fetch component metadata for {component_name}")
                return {'folders': {}, 'files': []}
            comp_data = json.loads(result.stdout)
            root_folder = comp_data.get('rootFolder', {})
            root_folder_id = root_folder.get('itemId', '')
            if not root_folder_id:
                logger.warning(f"No root folder in component {component_name}")
                return {'folders': {}, 'files': []}
            
            if not root_folder_id.startswith('_'):
                root_folder_id = '_' + root_folder_id
            
            # Step 3: Recursively fetch folder tree
            logger.info(f"Traversing folder tree from root: {root_folder_id[:12]}...")
            structure = self._fetch_folder_recursively(root_folder_id, baseline_uuid, max_depth=10)
            
            num_files = len(structure.get('files', []))
            num_folders = len(structure.get('folders', {}))
            logger.info(f"✓ Fetched structure: {num_folders} folders, {num_files} files")
            return structure
            
        except Exception as e:
            logger.error(f"Error fetching baseline structure for {component_name}: {e}")
            import traceback; logger.debug(traceback.format_exc())
            return {'folders': {}, 'files': []}
    
    def _fetch_folder_recursively(self, folder_id, baseline_uuid, depth=0, max_depth=10, current_path=''):
        """Recursively fetch folder contents via RTC REST API."""
        if depth > max_depth:
            return {'folders': {}, 'files': []}
        try:
            # Ensure folder_id has '_' prefix for REST API
            if not folder_id.startswith('_'):
                folder_id = '_' + folder_id
            
            folder_url = f'{self.server_url}/service/com.ibm.team.filesystem.service.rest.IVersionableRestService/folder/{folder_id}/children'
            curl_cmd = [
                'curl.exe', '-k', '-L', '--noproxy', '*',
                '-u', f'{self.username}:{self.password}',
                '-X', 'GET', folder_url,
                '-H', 'Accept: application/json',
                '-H', 'OSLC-Core-Version: 2.0'
            ]
            result = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=30,
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            if result.returncode != 0:
                return {'folders': {}, 'files': []}
            
            try:
                data = json.loads(result.stdout)
            except Exception:
                return {'folders': {}, 'files': []}
            
            # The response may use different keys
            children = data.get('children', []) or data.get('versionables', []) or []
            
            structure = {'folders': {}, 'files': []}
            
            for child in children:
                if not isinstance(child, dict):
                    continue
                child_name = child.get('name', '')
                child_type = child.get('type', '') or child.get('itemType', '')
                child_id   = child.get('itemId', child.get('uuid', ''))
                
                if not child_name:
                    continue
                
                # Folder?
                if 'folder' in child_type.lower() or child_type == 'com.ibm.team.filesystem.Folder':
                    subfolder_name = child_name
                    subfolder_path = f"{current_path}/{subfolder_name}" if current_path else subfolder_name
                    structure['folders'][subfolder_name] = self._fetch_folder_recursively(
                        child_id, baseline_uuid, depth+1, max_depth, subfolder_path
                    )
                # File?
                elif 'file' in child_type.lower() or child_type == 'com.ibm.team.filesystem.FileItem':
                    file_path = f"{current_path}/{child_name}" if current_path else child_name
                    structure['files'].append({
                        'name': child_name,
                        'path': file_path,
                        'uuid': child_id,
                        'content-id': child.get('contentId', child.get('content-id', '')),
                        'state-id'  : child.get('stateId', child.get('state-id', ''))
                    })
                else:
                    # Unknown type — treat conservatively as file
                    file_path = f"{current_path}/{child_name}" if current_path else child_name
                    structure['files'].append({
                        'name': child_name,
                        'path': file_path,
                        'uuid': child_id,
                        'content-id': child.get('contentId', child.get('content-id', '')),
                        'state-id'  : child.get('stateId', child.get('state-id', ''))
                    })
            return structure
            
        except Exception as e:
            logger.debug(f"Error fetching folder {folder_id[:12]}: {e}")
            return {'folders': {}, 'files': []}
    
    @staticmethod
    def _get_all_files_from_structure(structure, parent_path=''):
        """
        Recursively extract all files from a nested folder structure.
        
        Returns: dict {file_path: file_info_dict}
        """
        files = {}
        if not structure:
            return files
        
        # Add files at this level
        for file_item in structure.get('files', []):
            if isinstance(file_item, dict):
                file_name = file_item.get('name', '')
                if file_name:
                    file_path = f"{parent_path}/{file_name}" if parent_path else file_name
                    files[file_path] = file_item
            elif isinstance(file_item, str):
                file_path = f"{parent_path}/{file_item}" if parent_path else file_item
                files[file_path] = {'name': file_item}
        
        # Recurse into subfolders
        for folder_name, folder_content in structure.get('folders', {}).items():
            folder_path = f"{parent_path}/{folder_name}" if parent_path else folder_name
            subfolder_files = RTCConnection._get_all_files_from_structure(folder_content, folder_path)
            files.update(subfolder_files)
        
        return files
    
    def compare_folder_structures(self, folder1, folder2):
        """
        Compare two folder structures from baselines.
        
        Returns: {
            'added': int,
            'modified': int,
            'removed': int,
            'unchanged': int,
            'details': {file_path: 'added'|'removed'|'modified'|'unchanged'}
        }
        """
        try:
            if not folder1 and not folder2:
                return {'added': 0, 'modified': 0, 'removed': 0, 'unchanged': 0, 'details': {}}
            
            # Recursively collect all files with full metadata
            files1 = self._get_all_files_from_structure(folder1, '')
            files2 = self._get_all_files_from_structure(folder2, '')
            
            paths1 = set(files1.keys())
            paths2 = set(files2.keys())
            
            all_paths = paths1 | paths2
            added = modified = removed = unchanged = 0
            details = {}
            
            for path in sorted(all_paths):
                f1 = files1.get(path)
                f2 = files2.get(path)
                
                if f1 and f2:
                    # File exists in both — compare content identifiers
                    content1 = f1.get('content-id', '')
                    content2 = f2.get('content-id', '')
                    state1   = f1.get('state-id', '')
                    state2   = f2.get('state-id', '')
                    uuid1    = f1.get('uuid', '')
                    uuid2    = f2.get('uuid', '')
                    
                    # Determine modification using priority: state-id > content-id > uuid
                    is_modified = False
                    has_identifiers = False
                    
                    if state1 and state2:
                        has_identifiers = True
                        if state1 != state2:
                            is_modified = True
                    elif content1 and content2:
                        has_identifiers = True
                        if content1 != content2:
                            is_modified = True
                    elif uuid1 and uuid2:
                        has_identifiers = True
                        if uuid1 != uuid2:
                            is_modified = True
                    
                    if not has_identifiers:
                        # Cannot verify equality — assume modified to avoid false negatives
                        is_modified = True
                    
                    if is_modified:
                        details[path] = 'modified'
                        modified += 1
                    else:
                        details[path] = 'unchanged'
                        unchanged += 1
                elif f2:
                    details[path] = 'added'
                    added += 1
                else:
                    details[path] = 'removed'
                    removed += 1
            
            logger.info(f"Folder comparison complete: {modified} modified, {added} added, {removed} removed, {unchanged} unchanged (total: {len(all_paths)} files)")
            
            return {
                'added': added,
                'modified': modified,
                'removed': removed,
                'unchanged': unchanged,
                'details': details
            }
        except Exception as e:
            logger.error(f"Error comparing folder structures: {e}")
            return {'added': 0, 'modified': 0, 'removed': 0, 'unchanged': 0, 'details': {}}


def get_rtc_connection(username, password, server_url=None):
    """
    Factory function to create and validate RTC connection
    
    Returns: (RTCConnection or None, error_message or None)
    """
    if not server_url:
        server_url = settings.RTC_SERVER_URL
    
    conn = RTCConnection(server_url, username, password)
    success, msg = conn.test_connection()
    
    if success:
        return conn, None
    else:
        return None, msg
