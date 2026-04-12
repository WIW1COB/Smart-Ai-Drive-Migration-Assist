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
    
    def fetch_snapshot_components(self, snapshot_url, snapshot_name='Snapshot'):
        """
        Fetch all components from a snapshot via REST API
        
        Args:
            snapshot_url: Snapshot UUID or URL
            snapshot_name: Display name for logging
            
        Returns: List of components [{name, uuid, baseline_uuid}, ...]
        """
        try:
            # Extract UUID
            snapshot_id = self.extract_snapshot_uuid(snapshot_url)
            if not snapshot_id:
                logger.error(f"{snapshot_name}: Invalid snapshot URL format")
                return []
            
            logger.info(f"{snapshot_name}: Extracted ID: {snapshot_id}")
            
            # Build API URLs to try (multiple formats)
            api_urls = [
                f'{self.server_url}/resource/itemOid/com.ibm.team.scm.BaselineSet/{snapshot_id}',
                f'{self.server_url}/resource/itemName/com.ibm.team.scm.BaselineSet/{snapshot_id}',
            ]
            
            result = None
            
            for api_url in api_urls:
                logger.info(f"{snapshot_name}: Trying: {api_url}")
                
                try:
                    cmd = [
                        'curl.exe',
                        '-k',
                        '-L',
                        '--noproxy', '*',
                        '-u', f'{self.username}:{self.password}',
                        '-X', 'GET',
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
                    
                    if result.returncode == 0 and result.stdout.strip():
                        logger.info(f"{snapshot_name}: ✓ Got response from {api_url}")
                        break
                    
                except subprocess.TimeoutExpired:
                    logger.warning(f"{snapshot_name}: Request timeout for {api_url}")
                    continue
            
            if not result or result.returncode != 0:
                logger.error(f"{snapshot_name}: Failed to fetch - all URLs failed")
                return []
            
            if not result.stdout.strip():
                logger.error(f"{snapshot_name}: Empty response")
                return []
            
            # Parse JSON response
            try:
                data = json.loads(result.stdout)
            except json.JSONDecodeError as e:
                logger.error(f"{snapshot_name}: Failed to parse response: {e}")
                logger.error(f"Response: {result.stdout[:500]}")
                return []
            
            # Extract components from response
            components = []
            
            # Handle various response structures
            if isinstance(data, dict):
                # Check for error in response
                if data.get('errorCode') and int(data.get('errorCode', 0)) >= 400:
                    logger.error(f"{snapshot_name}: API error: {data.get('errorMessage')}")
                    return []
                
                # Look for component lists in various formats
                items = data.get('oslc:results', []) or data.get('results', []) or []
                
                if isinstance(items, list):
                    for item in items:
                        comp = {
                            'name': item.get('dcterms:title') or item.get('name') or item.get('dc:title'),
                            'uuid': item.get('rdf:about', '').split('/')[-1],
                            'baseline_uuid': item.get('baseline_id') or item.get('uuid'),
                        }
                        if comp['name']:
                            components.append(comp)
                
                # Handle RDF format
                elif 'rdf:RDF' in data:
                    rdf_items = data.get('rdf:RDF', {}).get('rdf:Description', [])
                    if not isinstance(rdf_items, list):
                        rdf_items = [rdf_items]
                    
                    for item in rdf_items:
                        if isinstance(item, dict) and item.get('dcterms:title'):
                            comp = {
                                'name': item.get('dcterms:title'),
                                'uuid': item.get('rdf:about', '').split('/')[-1],
                                'baseline_uuid': item.get('baseline_id'),
                            }
                            components.append(comp)
            
            logger.info(f"{snapshot_name}: Found {len(components)} components")
            return components
            
        except Exception as e:
            logger.error(f"{snapshot_name}: Error fetching components: {e}")
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
