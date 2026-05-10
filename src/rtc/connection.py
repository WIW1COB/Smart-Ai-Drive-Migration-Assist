"""RTC/ALM Connection Module - Comprehensive REST API Integration"""

import os
import subprocess
import json
import re
import logging
import threading
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError, wait
from src.config import settings

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
    
    def fetch_snapshot_components(self, snapshot_url, username=None, password=None, snapshot_name='Snapshot', progress_callback=None):
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
                        curl_command, capture_output=True, text=True, timeout=10,  # Reduced from 15s
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
                
                # Notify GUI of total count
                if progress_callback:
                    try:
                        progress_callback(0, total_baselines, f"{snapshot_name}: Found {total_baselines} baselines, fetching components...")
                    except Exception:
                        pass
                
                requested_workers = getattr(settings, "MAX_WORKERS", 10)
                try:
                    requested_workers = int(requested_workers)
                except Exception:
                    requested_workers = 10

                # Use configured MAX_WORKERS for optimal performance
                # Modern RTC servers can handle 50+ parallel connections
                max_workers = max(1, requested_workers)
                logger.info(
                    f'{snapshot_name}: Fetching component details for {total_baselines} baselines '
                    f'(workers={max_workers})...'
                )

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
                        api_timeout = getattr(settings, 'RTC_API_TIMEOUT', 15)
                        comp_result = subprocess.run(
                            curl_comp,
                            capture_output=True,
                            text=True,
                            timeout=api_timeout,
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
                        api_timeout = getattr(settings, 'RTC_API_TIMEOUT', 15)
                        baseline_result = subprocess.run(
                            curl_baseline,
                            capture_output=True,
                            text=True,
                            timeout=api_timeout,
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
                last_heartbeat = start_time
                last_gui_update = start_time
                processed = 0

                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    pending = {executor.submit(fetch_baseline_component, b) for b in baseline_list}

                    # Heartbeat loop: logs progress even when the server is slow and no futures
                    # have completed yet (so it doesn't look stuck).
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

                        now = time.time()
                        if (processed % 20 == 0 and processed > 0) or processed == total_baselines:
                            elapsed = now - start_time
                            rate = processed / elapsed if elapsed > 0 else 0
                            remaining = (total_baselines - processed) / rate if rate > 0 else 0
                            logger.info(
                                f'{snapshot_name}: Progress: {processed}/{total_baselines} baselines processed '
                                f'({len(components)} components found) - {elapsed:.1f}s ({rate:.1f}/s, ~{remaining:.0f}s remaining)'
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
            return {'name': None, 'components': []}
    
    def fetch_file_content_from_baseline(self, baseline_uuid, file_path, component_name=None):
        """
        Fetch file content from RTC baseline using SCM CLI
        
        Args:
            baseline_uuid: Baseline UUID  
            file_path: File path within the component (without leading slash)
            component_name: Optional component name
            
        Returns: File content as string, or None if error
        """
        try:
            if not settings.LSCM_PATH or not os.path.exists(settings.LSCM_PATH):
                logger.warning('LSCM/SCM CLI not found, cannot download file content')
                return None
            
            # Clean up the file path - ensure it starts with /
            clean_path = file_path.strip()
            if not clean_path.startswith('/'):
                clean_path = '/' + clean_path
            
            logger.debug(f'{component_name}: Downloading file: {clean_path} from baseline {baseline_uuid[:12]}...')
            
            # Use temporary directory for file download
            with tempfile.TemporaryDirectory() as temp_dir:
                # Get the filename from the path
                filename = os.path.basename(clean_path)
                if not filename:
                    logger.error(f'{component_name}: Invalid file path: {clean_path}')
                    return None
                
                output_file = os.path.join(temp_dir, filename)
                
                # Build scm get file command
                # Correct syntax from help: scm get file [options] <item> [state] [path-on-disk]
                # When using -b -f, <item> is the baseline UUID, path-on-disk is the output location
                cmd = [
                    settings.LSCM_PATH,
                    'get', 'file',
                    '-b',                     # Get from baseline
                    '-f', clean_path,         # File path within baseline
                    '-r', self.server_url,    # Repository URL
                    '-u', self.username,      # Username
                    '-P', self.password,      # Password
                    '-o',                     # Overwrite if exists
                    baseline_uuid,            # Baseline UUID (positional arg)
                    output_file               # Output file location (positional arg)
                ]
                
                # Add component if provided (use lowercase -c, not -C)
                if component_name:
                    # Insert component option after -b but before -f
                    cmd.insert(4, '-c')
                    cmd.insert(5, component_name)
                
                logger.debug(f'{component_name}: Running lscm get file for {clean_path}')
                
                # Remove proxy settings
                env = os.environ.copy()
                for proxy_var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy',
                                 'NO_PROXY', 'no_proxy']:
                    env.pop(proxy_var, None)
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=45,  # Reduced from 90s - fail faster on stuck file downloads
                    env=env,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                
                if result.returncode == 0 and os.path.exists(output_file):
                    with open(output_file, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    logger.debug(f'{component_name}: ✓ Downloaded {clean_path}: {len(content)} bytes')
                    return content
                else:
                    stderr_preview = result.stderr[:200] if result.stderr else 'No error output'
                    logger.warning(f'{component_name}: ✗ Failed to download {clean_path}')
                    logger.warning(f'{component_name}: Return code: {result.returncode}')
                    logger.warning(f'{component_name}: Stderr: {stderr_preview}')
                    logger.warning(f'{component_name}: File exists: {os.path.exists(output_file)}')
                    return None
        
        except subprocess.TimeoutExpired:
            logger.error(f'{component_name}: ✗ Timeout downloading {file_path} (45s)')
            return None
        except Exception as e:
            logger.error(f'{component_name}: ✗ Error downloading {file_path}: {e}', exc_info=True)
            return None
    
    def fetch_baseline_file_list(self, baseline_uuid, component_name='Unknown'):
        """
        Fetch list of files from a baseline using lscm CLI
        
        Args:
            baseline_uuid: Baseline UUID
            component_name: Component name for logging
            
        Returns: dict {file_path: file_metadata_dict}
        """
        try:
            if not settings.LSCM_PATH or not os.path.exists(settings.LSCM_PATH):
                logger.warning(f'{component_name}: LSCM not available, cannot list files')
                return {}
            
            logger.info(f'{component_name}: Fetching file list from baseline {baseline_uuid[:12]}...')
            
            # Use lscm list files command with JSON output
            cmd = [
                settings.LSCM_PATH,
                'list', 'files',
                '-b', baseline_uuid,  # Baseline UUID
                '-r', self.server_url,
                '-u', self.username,
                '-P', self.password,
                '-D', 'all',  # Recursive listing with infinite depth
                '-j'  # JSON output
            ]
            
            logger.debug(f'{component_name}: Running lscm command: {" ".join([c if i != cmd.index(self.password) else "****" for i, c in enumerate(cmd)])}')
            
            # Remove proxy settings
            env = os.environ.copy()
            for proxy_var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy',
                             'NO_PROXY', 'no_proxy']:
                env.pop(proxy_var, None)
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,  # OPTIMIZED: Reduced from 60s to 30s for faster failure detection
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            # SCM CLI may return exit code 1 even with valid output
            if not result.stdout or not result.stdout.strip():
                logger.warning(f'{component_name}: No output from list files')
                logger.warning(f'{component_name}: Exit code: {result.returncode}')
                logger.warning(f'{component_name}: Stderr: {result.stderr[:500]}')
                return {}
            
            # Log first 500 chars of output for debugging
            logger.debug(f'{component_name}: lscm output (first 500 chars): {result.stdout[:500]}')
            
            # Parse JSON output
            try:
                data = json.loads(result.stdout)
                baseline_data = data.get('baseline', {})
                remote_files = baseline_data.get('remote-files', [])
                
                if not remote_files:
                    logger.warning(f'{component_name}: No remote-files in JSON output')
                    return {}
                
                # Build file dictionary with metadata
                files = {}
                for item in remote_files:
                    path = item.get('path', '').strip('/')
                    
                    if not path or path.endswith('/'):
                        # Skip folders
                        continue
                    
                    # Store file with metadata for comparison
                    files[path] = {
                        'uuid': item.get('uuid', item.get('item-id', '')),
                        'content-id': item.get('content-id', ''),
                        'state-id': item.get('state-id', ''),
                        'path': path
                    }
                
                logger.info(f'{component_name}: Found {len(files)} files in baseline')
                return files
                
            except json.JSONDecodeError as e:
                logger.error(f'{component_name}: Failed to parse JSON: {e}')
                logger.debug(f'Output: {result.stdout[:500]}')
                return {}
            
        except subprocess.TimeoutExpired:
            logger.error(f'{component_name}: Timeout fetching file list')
            return {}
        except Exception as e:
            logger.error(f'{component_name}: Error fetching file list: {e}')
            return {}
    
    def compare_file_lists(self, files1, files2):
        """
        Compare two file lists to identify added/modified/removed files
        
        Args:
            files1: dict of files from baseline 1 {path: metadata}
            files2: dict of files from baseline 2 {path: metadata}
            
        Returns: dict with added, modified, removed, unchanged lists
        """
        paths1 = set(files1.keys())
        paths2 = set(files2.keys())
        
        added = sorted(paths2 - paths1)
        removed = sorted(paths1 - paths2)
        common = sorted(paths1 & paths2)
        
        # For common files, compare content-id or state-id to determine if modified
        modified = []
        unchanged = []
        no_metadata_files = []
        
        for path in common:
            file1 = files1[path]
            file2 = files2[path]
            
            # Compare using content-id (most reliable - file content hash)
            content1 = file1.get('content-id', '')
            content2 = file2.get('content-id', '')
            
            if content1 and content2:
                if content1 != content2:
                    modified.append(path)
                else:
                    unchanged.append(path)
            else:
                # Fallback to state-id comparison
                state1 = file1.get('state-id', '')
                state2 = file2.get('state-id', '')
                
                if state1 and state2:
                    if state1 != state2:
                        modified.append(path)
                    else:
                        unchanged.append(path)
                else:
                    # CRITICAL FIX: No metadata to compare - treat as UNCHANGED
                    # Rationale: If we can't prove it changed, assume it didn't
                    # This prevents false positives from missing metadata
                    unchanged.append(path)
                    no_metadata_files.append(path)
        
        # Log warning if files had no metadata for comparison
        if no_metadata_files:
            logger.warning(f"⚠ {len(no_metadata_files)} file(s) lacked content-id/state-id metadata, treated as unchanged")
            if len(no_metadata_files) <= 5:
                for path in no_metadata_files:
                    logger.debug(f"  - No metadata: {path}")
        
        logger.debug(f"File comparison: {len(added)} added, {len(modified)} modified, "
                    f"{len(removed)} removed, {len(unchanged)} unchanged")
        
        return {
            'added': added,
            'modified': modified,
            'removed': removed,
            'unchanged': unchanged,
            'details': {
                **{path: 'added' for path in added},
                **{path: 'modified' for path in modified},
                **{path: 'removed' for path in removed},
                **{path: 'unchanged' for path in unchanged}
            }
        }
    
    def compare_snapshots(self, snap1_components, snap2_components, progress_callback=None):
        """
        Compare two sets of snapshot components with file-level analysis.
        When both components exist but baseline UUIDs differ, fetches folder
        structures and performs file-level comparison.
        
        OPTIMIZED: Uses parallel processing for baseline file list fetching
        
        Args:
            snap1_components: List of components from snapshot 1
            snap2_components: List of components from snapshot 2
            progress_callback: Optional callback(current, total, message) for progress updates
        
        Returns: List of comparison results
        """
        try:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            
            logger.info("=" * 80)
            logger.info("STARTING SNAPSHOT COMPONENT COMPARISON (OPTIMIZED)")
            logger.info(f"Snapshot 1: {len(snap1_components)} components")
            logger.info(f"Snapshot 2: {len(snap2_components)} components")
            
            # Show sample component data for debugging
            if snap1_components:
                sample = snap1_components[0]
                logger.info(f"Sample component structure: name={sample.get('name', 'N/A')}, "
                           f"uuid={sample.get('uuid', 'N/A')[:12] if sample.get('uuid') else 'N/A'}..., "
                           f"baseline_uuid={sample.get('baseline_uuid', 'N/A')[:12] if sample.get('baseline_uuid') else 'N/A'}...")
            logger.info("=" * 80)
            
            # Create lookup dictionaries
            snap1_dict = {comp['name']: comp for comp in snap1_components if comp.get('name')}
            snap2_dict = {comp['name']: comp for comp in snap2_components if comp.get('name')}
            
            # Find all unique component names
            all_names = sorted(set(snap1_dict.keys()) | set(snap2_dict.keys()))
            
            # Phase 1: Quick comparison - identify modified components
            logger.info("Phase 1: Identifying modified components...")
            components_needing_file_comparison = []
            results = []
            
            for idx, name in enumerate(all_names):
                if progress_callback:
                    progress_callback(idx, len(all_names), f"Analyzing {name}...")
                
                comp1 = snap1_dict.get(name)
                comp2 = snap2_dict.get(name)
                
                entry = {'name': name, 'snapshot1': comp1, 'snapshot2': comp2}
                
                if comp1 and comp2:
                    # Component exists in both
                    uuid1 = comp1.get('baseline_uuid') or comp1.get('uuid')
                    uuid2 = comp2.get('baseline_uuid') or comp2.get('uuid')
                    
                    # Log the UUIDs being compared for debugging
                    logger.debug(f'{name}: Comparing baseline_uuid1={uuid1[:20]}... vs baseline_uuid2={uuid2[:20]}...')
                    
                    if uuid1 == uuid2:
                        comparison['status'] = 'Unchanged'
                        logger.info(f'{name}: Unchanged - baseline UUIDs match')
                    else:
                        # Baselines differ - queue for file-level comparison
                        # Note: Baseline UUIDs can differ even with identical content if:
                        # - Baseline was recreated
                        # - Metadata/permissions changed
                        # - Component configuration changed
                        comparison['status'] = 'Modified'
                        comparison['baseline1_uuid'] = uuid1
                        comparison['baseline2_uuid'] = uuid2
                        components_needing_file_comparison.append((name, uuid1, uuid2, comparison))
                        logger.info(f'{name}: Baseline UUIDs differ ({uuid1[:8]}...≠{uuid2[:8]}...) - queued for file-level comparison')
                
                elif comp1:
                    comparison['status'] = 'Removed in Snapshot 2'
                else:
                    comparison['status'] = 'Added in Snapshot 2'
                
                results.append(comparison)
            
            # Phase 2: Parallel file list fetching for modified components
            if components_needing_file_comparison:
                logger.info(f"Phase 2: Fetching file lists for {len(components_needing_file_comparison)} modified components (PARALLEL)...")
                
                # Build list of baseline UUIDs to fetch (deduplicate)
                baselines_to_fetch = set()
                for name, uuid1, uuid2, _ in components_needing_file_comparison:
                    if uuid1:
                        baselines_to_fetch.add((uuid1, name, 1))
                    if uuid2:
                        baselines_to_fetch.add((uuid2, name, 2))
                
                logger.info(f"Fetching {len(baselines_to_fetch)} unique baselines in parallel...")
                
                # Parallel fetch with ThreadPoolExecutor
                baseline_cache = {}
                max_workers = min(8, len(baselines_to_fetch))  # Cap at 8 parallel workers
                
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_to_baseline = {
                        executor.submit(self.fetch_baseline_file_list, uuid, f"{name}_snap{snap_num}"): (uuid, name, snap_num)
                        for uuid, name, snap_num in baselines_to_fetch
                    }
                    
                    completed = 0
                    for future in as_completed(future_to_baseline):
                        uuid, name, snap_num = future_to_baseline[future]
                        completed += 1
                        
                        if progress_callback:
                            progress_callback(completed, len(baselines_to_fetch), 
                                            f"Fetching files for {name} ({completed}/{len(baselines_to_fetch)})...")
                        
                        try:
                            files = future.result()
                            baseline_cache[uuid] = files
                            logger.info(f'{name} (snap{snap_num}): ✓ Fetched {len(files)} files')
                        except Exception as e:
                            logger.error(f'{name} (snap{snap_num}): ✗ Failed to fetch: {e}')
                            baseline_cache[uuid] = {}
                
                # Phase 3: Compare file lists using cached results
                logger.info("Phase 3: Comparing file lists...")
                for idx, (name, uuid1, uuid2, comparison) in enumerate(components_needing_file_comparison):
                    if progress_callback:
                        progress_callback(idx, len(components_needing_file_comparison), f"Comparing files in {name}...")
                    
                    try:
                        files1 = baseline_cache.get(uuid1, {})
                        files2 = baseline_cache.get(uuid2, {})
                        
                        # Always perform file comparison - even for empty components
                        # Empty file lists (both {}) should result in 'Unchanged' status
                        file_comparison = self.compare_file_lists(files1, files2)
                        comparison['file_comparison'] = file_comparison
                        comparison['files_added'] = file_comparison['added']
                        comparison['files_modified'] = file_comparison['modified']
                        comparison['files_removed'] = file_comparison['removed']
                        comparison['files_unchanged'] = file_comparison['unchanged']
                        
                        # CRITICAL FIX: Update status to 'Unchanged' if NO actual file changes
                        # This now correctly handles components with no files (empty baselines)
                        if (len(file_comparison['added']) == 0 and 
                            len(file_comparison['modified']) == 0 and 
                            len(file_comparison['removed']) == 0):
                            comparison['status'] = 'Unchanged'
                            if not files1 and not files2:
                                logger.info(f'{name}: ✓ Both baselines are empty (no files) - Status: Unchanged')
                            else:
                                logger.info(f'{name}: ✓ Baseline UUIDs differ but NO file changes - Status: Unchanged')
                        else:
                            # Log which files are causing the Modified status
                            change_summary = []
                            if file_comparison['added']:
                                change_summary.append(f"{len(file_comparison['added'])} added")
                                if len(file_comparison['added']) <= 3:
                                    for f in file_comparison['added'][:3]:
                                        logger.debug(f"  + Added: {f}")
                            if file_comparison['modified']:
                                change_summary.append(f"{len(file_comparison['modified'])} modified")
                                if len(file_comparison['modified']) <= 3:
                                    for f in file_comparison['modified'][:3]:
                                        logger.debug(f"  ~ Modified: {f}")
                            if file_comparison['removed']:
                                change_summary.append(f"{len(file_comparison['removed'])} removed")
                                if len(file_comparison['removed']) <= 3:
                                    for f in file_comparison['removed'][:3]:
                                        logger.debug(f"  - Removed: {f}")
                            
                            logger.info(f'{name}: ✓ {", ".join(change_summary)} - Status: Modified')
                    
                    except Exception as file_err:
                        logger.error(f'{name}: Error comparing files: {file_err}', exc_info=True)
                        comparison['file_comparison'] = None
            
            # Update results with file comparisons
            result_dict = {r['name']: r for r in results}
            for name, _, _, comparison in components_needing_file_comparison:
                if name in result_dict:
                    # Log status before and after update for debugging
                    old_status = result_dict[name].get('status', 'Unknown')
                    result_dict[name].update(comparison)
                    new_status = result_dict[name].get('status', 'Unknown')
                    
                    if old_status != new_status:
                        logger.info(f"{name}: Status updated from '{old_status}' → '{new_status}'")
            
            # Log summary
            logger.info("=" * 80)
            logger.info("COMPARISON SUMMARY:")
            logger.info(f"  Total components: {len(results)}")
            modified = sum(1 for r in results if r['status'] == 'Modified')
            unchanged = sum(1 for r in results if r['status'] == 'Unchanged')
            added = sum(1 for r in results if 'Added' in r['status'])
            removed = sum(1 for r in results if 'Removed' in r['status'])
            logger.info(f"  Modified: {modified}")
            logger.info(f"  Unchanged: {unchanged}")
            logger.info(f"  Added: {added}")
            logger.info(f"  Removed: {removed}")
            
            # Detailed status verification for debugging
            status_breakdown = {}
            for r in results:
                status = r.get('status', 'Unknown')
                status_breakdown[status] = status_breakdown.get(status, 0) + 1
            
            if len(status_breakdown) > 0:
                logger.info("  Status breakdown:")
                for status, count in sorted(status_breakdown.items()):
                    logger.info(f"    - '{status}': {count}")
            
            logger.info("=" * 80)
            
            # Return ALL components with their correct status
            # Status is already set correctly: 'Modified', 'Unchanged', 'Added', 'Removed'
            return results
            
        except Exception as e:
            logger.error(f"Error in compare_snapshots: {e}")
            return []

    
    def fetch_changesets_for_files(self, modified_files, baseline_uuid, component_name='Unknown'):
        """
        Fetch changeset information for a list of modified files in a baseline.
        
        REQUIREMENTS: This feature requires RTC SCM CLI (lscm/scm.exe) to be installed.
        If not available, returns empty results with a warning.
        
        Args:
            modified_files: List of file paths (from baseline file list)
            baseline_uuid: Baseline UUID for context
            component_name: Component name for logging
            
        Returns: Dictionary mapping file_path -> changeset_data
        """
        try:
            if not modified_files:
                logger.debug(f"{component_name}: No modified files to fetch changesets for")
                return {}
            
            logger.info(f"{component_name}: Attempting to fetch changesets for {len(modified_files)} modified files...")
            
            changeset_map = {}
            
            # Check LSCM availability
            lscm_path = settings.LSCM_PATH
            if not lscm_path:
                logger.warning(f"{component_name}: LSCM_PATH not configured - changeset fetching unavailable")
                logger.warning(f"Install RTC SCM CLI and configure settings.LSCM_PATH to enable changeset fetching")
                return {}
            
            if not os.path.exists(lscm_path):
                logger.warning(f"{component_name}: LSCM not found at {lscm_path} - changeset fetching unavailable")
                logger.warning(f"Please install RTC SCM CLI (scm.exe/lscm) to enable changeset details")
                return {}
            
            logger.info(f"{component_name}: Using LSCM at {lscm_path}")
            
            # Ensure baseline UUID has underscore prefix
            if baseline_uuid and not baseline_uuid.startswith('_'):
                baseline_uuid = '_' + baseline_uuid
            
            logger.info(f"{component_name}: Baseline UUID: {baseline_uuid[:20]}...")
            
            # Fetch changesets for up to 10 files (to avoid excessive delay)
            files_to_check = modified_files[:10]
            logger.info(f"{component_name}: Fetching changesets for {len(files_to_check)} files (limited from {len(modified_files)} total)")
            
            for idx, file_path in enumerate(files_to_check, 1):
                try:
                    logger.debug(f"  [{idx}/{len(files_to_check)}] Fetching changeset for: {file_path}")
                    
                    # SCM history command for repository file
                    cmd = [
                        lscm_path,
                        'history',
                        file_path,
                        '-r', self.server_url,
                        '-u', self.username,
                        '-P', self.password,
                        '-m', '1',  # Only most recent changeset
                        '-j'  # JSON output (if supported)
                    ]
                    
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=15,  # Reduced timeout for faster failure
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                    )
                    
                    if result.returncode == 0 and result.stdout:
                        # Parse changeset from output
                        changeset_data = self._parse_changeset_from_scm_output(result.stdout)
                        if changeset_data:
                            changeset_map[file_path] = changeset_data
                            logger.info(f"  ✓ [{idx}/{len(files_to_check)}] {file_path}: Found changeset {changeset_data.get('uuid', 'N/A')[:12]}...")
                        else:
                            logger.debug(f"  ⚠ [{idx}/{len(files_to_check)}] {file_path}: Could not parse changeset from output")
                    else:
                        stderr_preview = result.stderr[:100] if result.stderr else 'No error output'
                        logger.debug(f"  ✗ [{idx}/{len(files_to_check)}] {file_path}: Command failed. Stderr: {stderr_preview}")
                    
                except subprocess.TimeoutExpired:
                    logger.warning(f"  ⏱ [{idx}/{len(files_to_check)}] {file_path}: Timeout (15s) fetching changeset")
                    continue
                except Exception as e:
                    logger.debug(f"  ✗ [{idx}/{len(files_to_check)}] {file_path}: Failed: {e}")
                    continue
            
            if changeset_map:
                logger.info(f"{component_name}: ✓ Successfully fetched changesets for {len(changeset_map)}/{len(files_to_check)} files")
            else:
                logger.warning(f"{component_name}: ⚠ No changesets found for any files (LSCM may not be properly configured)")
            
            return changeset_map
            
        except Exception as e:
            logger.error(f"{component_name}: Error fetching changesets: {e}", exc_info=True)
            return {}
    
    
    def _parse_changeset_from_scm_output(self, scm_output):
        """Parse changeset information from SCM history output"""
        try:
            # Try JSON parsing first
            try:
                data = json.loads(scm_output)
                changesets = data.get('changesets', [])
                if changesets:
                    cs = changesets[0]
                    uuid = cs.get('uuid', '')
                    logger.debug(f"  Parsed JSON changeset: {uuid}")
                    return {
                        'uuid': uuid,
                        'comment': cs.get('comment', ''),
                        'author': cs.get('author', {}).get('name', ''),
                        'url': f"{self.server_url}/resource/itemName/com.ibm.team.scm.ChangeSet/{uuid}"
                    }
            except json.JSONDecodeError:
                logger.debug("  JSON parsing failed, trying text parsing...")
            
            # Fallback to text parsing
            lines = scm_output.split('\n')
            for line in lines:
                # Match: (1234) ---$ "Comment"
                cs_match = re.match(r'\((\d+)\)\s+---\$?\s*"?([^"]*)"?', line.strip())
                if cs_match:
                    cs_number = cs_match.group(1)
                    comment = cs_match.group(2).strip()
                    logger.debug(f"  Parsed text changeset: {cs_number}")
                    return {
                        'uuid': cs_number,
                        'comment': comment,
                        'author': '',
                        'url': f"{self.server_url}/resource/itemName/com.ibm.team.scm.ChangeSet/{cs_number}"
                    }
            
            # If no match found, log the output for debugging
            logger.debug(f"  Could not parse changeset. Output preview: {scm_output[:300]}")
            return None
            
        except Exception as e:
            logger.debug(f"Failed to parse changeset output: {e}")
            return None


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
                
                api_timeout = getattr(settings, 'RTC_API_TIMEOUT', 15)
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=api_timeout,
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
