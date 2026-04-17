"""RTC/ALM Connection Module - Comprehensive REST API Integration"""

import os
import subprocess
import json
import re
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from src.config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
            
            for candidate_url in api_url_candidates:
                logger.info(f'{snapshot_name}: Trying API URL: {candidate_url}')
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
                    logger.warning(f'{snapshot_name}: Request timed out for {candidate_url}')
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
            except json.JSONDecodeError as e:
                logger.error(f'{snapshot_name}: Failed to parse JSON: {e}')
                logger.error(f'{snapshot_name}: Response: {result.stdout[:500]}')
                return []

            # Check for authentication errors in JSON response
            if isinstance(data, dict):
                if 'error_code' in data or 'error_message' in data:
                    error_code = data.get('error_code', 'unknown')
                    error_msg = data.get('error_message', 'Unknown error')
                    logger.error(f'{snapshot_name}: API ERROR: {error_code} - {error_msg}')
                    return []

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
                max_workers = getattr(settings, "MAX_WORKERS", 10)
                logger.info(f'{snapshot_name}: Fetching component details for {total_baselines} baselines (workers={max_workers})...')

                # Shared cache for component names
                component_name_cache = {}
                cache_lock = threading.Lock()

                def get_component_name(comp_item_id):
                    """Fetch component name with caching"""
                    with cache_lock:
                        cached = component_name_cache.get(comp_item_id)
                    if cached:
                        return cached

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
                    """Fetch component info for a single baseline"""
                    if not isinstance(baseline_ref, dict):
                        return None

                    item_id = baseline_ref.get("itemId", "")
                    state_id = baseline_ref.get("stateId", "")
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
                                    "name": comp_name,
                                    "uuid": comp_item_id,
                                    "baseline_uuid": item_id,
                                    "state_id": state_id,
                                }

                            logger.debug(f'{snapshot_name}: Skipping baseline {item_id[:8]} - no component reference')
                            return None

                    except Exception as e:
                        logger.debug(f'{snapshot_name}: Failed to fetch baseline {item_id[:12]}...: {e}')

                    return None

                start_time = time.time()
                processed = 0

                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = [executor.submit(fetch_baseline_component, b) for b in baseline_list]

                    for future in as_completed(futures):
                        processed += 1
                        try:
                            component = future.result()
                            if component:
                                components.append(component)
                        except Exception as e:
                            logger.debug(f'{snapshot_name}: Baseline processing error: {e}')

                        if processed % 20 == 0 or processed == total_baselines:
                            elapsed = time.time() - start_time
                            logger.info(
                                f'{snapshot_name}: Progress: {processed}/{total_baselines} baselines processed '
                                f'({len(components)} components found) - {elapsed:.1f}s'
                            )

                logger.info(f'{snapshot_name}: ✓ Successfully extracted {len(components)} components')

            if len(components) == 0:
                logger.warning(f'{snapshot_name}: No components could be extracted from {len(baseline_list) if baseline_list else 0} baselines')

            return components

        except Exception as e:
            logger.error(f'{snapshot_name}: Error fetching components: {e}')
            import traceback
            logger.debug(traceback.format_exc())
            return []
    
    def compare_snapshots(self, snap1_components, snap2_components):
        """
        Compare two sets of snapshot components
        
        Returns: List of comparison results
        """
        try:
            # Create lookup dictionaries
            snap1_dict = {comp['name']: comp for comp in snap1_components if comp.get('name')}
            snap2_dict = {comp['name']: comp for comp in snap2_components if comp.get('name')}
            
            # Find all unique component names
            all_names = set(snap1_dict.keys()) | set(snap2_dict.keys())
            
            results = []
            
            for name in sorted(all_names):
                comp1 = snap1_dict.get(name)
                comp2 = snap2_dict.get(name)
                
                comparison = {
                    'name': name,
                    'snapshot1': comp1,
                    'snapshot2': comp2,
                }
                
                if comp1 and comp2:
                    # Component exists in both
                    uuid1 = comp1.get('uuid') or comp1.get('baseline_uuid')
                    uuid2 = comp2.get('uuid') or comp2.get('baseline_uuid')
                    
                    if uuid1 == uuid2:
                        comparison['status'] = 'Unchanged'
                    else:
                        comparison['status'] = 'Modified'
                
                elif comp1:
                    # Only in snapshot 1
                    comparison['status'] = 'Removed in Snapshot 2'
                
                else:
                    # Only in snapshot 2
                    comparison['status'] = 'Added in Snapshot 2'
                
                results.append(comparison)
            
            logger.info(f"Comparison complete: {len(results)} components analyzed")
            return results
            
        except Exception as e:
            logger.error(f"Error comparing snapshots: {e}")
            return []


    def fetch_baseline_folder_structure(self, baseline_uuid, component_name='Unknown'):
        """
        Fetch folder/file structure from a baseline via RTC REST API
        
        Args:
            baseline_uuid: Baseline UUID
            component_name: Component name for logging
            
        Returns: dict with folder structure {'folders': {...}, 'files': [...]}
        """
        try:
            if not baseline_uuid:
                logger.warning(f"No baseline UUID provided for {component_name}")
                return {'folders': {}, 'files': []}
            
            # Add _ prefix if missing
            if not baseline_uuid.startswith('_'):
                baseline_uuid = '_' + baseline_uuid
            
            logger.info(f"Fetching baseline structure for {component_name}: {baseline_uuid[:12]}...")
            
            # Build API URL for baseline
            api_url = f'{self.server_url}/resource/itemOid/com.ibm.team.scm.Baseline/{baseline_uuid}'
            
            try:
                cmd = [
                    'curl.exe',
                    '-k',
                    '-L',
                    '--noproxy', '*',
                    '-u', f'{self.username}:{self.password}',
                    api_url,
                    '-H', 'Accept: application/json',
                    '-H', 'OSLC-Core-Version: 2.0'
                ]
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                
                if result.returncode != 0:
                    logger.warning(f"Failed to fetch baseline structure for {component_name}")
                    return {'folders': {}, 'files': []}
                
                if not result.stdout.strip():
                    logger.warning(f"Empty response for baseline {baseline_uuid[:12]}...")
                    return {'folders': {}, 'files': []}
                
                # Parse response
                try:
                    data = json.loads(result.stdout)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse baseline response for {component_name}")
                    return {'folders': {}, 'files': []}
                
                # Extract folder structure from response
                folders = {}
                files = []
                
                # Handle different response formats
                if isinstance(data, dict):
                    # Look for file list or folder structure
                    file_list = data.get('files', []) or data.get('components', [])
                    if isinstance(file_list, list):
                        for file_item in file_list:
                            if isinstance(file_item, dict):
                                files.append({
                                    'name': file_item.get('name', 'Unknown'),
                                    'path': file_item.get('path', ''),
                                    'uuid': file_item.get('uuid', '')
                                })
                
                return {'folders': folders, 'files': files}
                
            except subprocess.TimeoutExpired:
                logger.warning(f"Timeout fetching baseline for {component_name}")
                return {'folders': {}, 'files': []}
                
        except Exception as e:
            logger.error(f"Error fetching baseline structure for {component_name}: {e}")
            return {'folders': {}, 'files': []}
    
    def compare_folder_structures(self, folder1, folder2):
        """
        Compare two folder structures from baselines
        
        Returns: dict with comparison results
        {
            'added': N,
            'modified': N,
            'removed': N,
            'unchanged': N,
            'details': {file_path: status}
        }
        """
        try:
            files1 = set((f['path'], f['uuid']) for f in folder1.get('files', []))
            files2 = set((f['path'], f['uuid']) for f in folder2.get('files', []))
            
            paths1 = {f[0]: f[1] for f in files1}
            paths2 = {f[0]: f[1] for f in files2}
            
            all_paths = set(paths1.keys()) | set(paths2.keys())
            
            added = 0
            modified = 0
            removed = 0
            unchanged = 0
            details = {}
            
            for path in sorted(all_paths):
                uuid1 = paths1.get(path)
                uuid2 = paths2.get(path)
                
                if uuid1 and uuid2:
                    if uuid1 == uuid2:
                        details[path] = 'unchanged'
                        unchanged += 1
                    else:
                        details[path] = 'modified'
                        modified += 1
                elif uuid2:
                    details[path] = 'added'
                    added += 1
                else:
                    details[path] = 'removed'
                    removed += 1
            
            return {
                'added': added,
                'modified': modified,
                'removed': removed,
                'unchanged': unchanged,
                'details': details
            }
            
        except Exception as e:
            logger.error(f"Error comparing folder structures: {e}")
            return {
                'added': 0,
                'modified': 0,
                'removed': 0,
                'unchanged': 0,
                'details': {}
            }


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
