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
logging.basicConfig(level=logging.INFO)
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
                logger.info("Γ£ô RTC connection successful")
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
    
    def _make_session(self):
        """
        Create a requests Session with connection pooling and retry logic.
        Pool size matches MAX_WORKERS so every thread reuses a persistent
        TCP connection instead of opening a new one per request.
        Returns None if requests library is unavailable (falls back to curl).
        """
        if not _requests_available:
            return None
        try:
            session = _requests.Session()  # type: ignore[possibly-undefined]
            session.verify = False          # self-signed Bosch cert
            session.auth = (self.username, self.password)
            session.headers.update({
                'Accept': 'application/json',
                'Connection': 'keep-alive',
                'OSLC-Core-Version': '2.0',
            })
            max_pool = max(1, min(getattr(settings, 'MAX_WORKERS', 20), 30))
            adapter = _HTTPAdapter(  # type: ignore[possibly-undefined]
                pool_connections=max_pool,
                pool_maxsize=max_pool * 2,
                max_retries=_Retry(  # type: ignore[possibly-undefined]
                    total=3, backoff_factor=0.3,
                    status_forcelist=[429, 500, 502, 503, 504]
                )
            )
            session.mount('https://', adapter)
            session.mount('http://', adapter)
            return session
        except Exception as e:
            logger.warning(f"Could not create requests session: {e}; will use curl fallback")
            return None

    def _scm_login(self):
        """
        Authenticate once to the EWM server using 'scm login' and cache the
        session in a temporary config directory.  All subsequent scm CLI calls
        pass --config <dir> so they reuse cached credentials instead of doing
        a full JVM + LDAP round-trip for every component.

        Returns the config directory path, or None if login failed / CLI absent.
        Thread-safe: only one login is ever performed per process.
        """
        global _scm_config_dir, _scm_logged_in

        with _scm_config_lock:
            if _scm_logged_in and _scm_config_dir:
                return _scm_config_dir   # already logged in

            skip     = getattr(settings, 'SKIP_SCM_CLI', True)
            scm_path = getattr(settings, 'LSCM_PATH', '')
            if skip or not scm_path or not os.path.exists(scm_path):
                return None

            config_dir = tempfile.mkdtemp(prefix='scm_cfg_')
            cmd = [
                scm_path,
                '--non-interactive',
                '--config', config_dir,
                'login',
                '-r', self.server_url,
                '-u', self.username,
                '-P', self.password,
            ]
            env = os.environ.copy()
            for pv in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy',
                       'NO_PROXY', 'no_proxy'):
                env.pop(pv, None)

            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=60, env=env,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                )
                logger.info(
                    f"[SCM Login] rc={result.returncode} "
                    f"stdout={result.stdout.strip()[:200]!r} "
                    f"stderr={result.stderr.strip()[:200]!r}"
                )
                _scm_config_dir = config_dir
                if result.returncode == 0:
                    _scm_logged_in = True
                    logger.info(f"[SCM Login] \u2713 Logged in; config cached at {config_dir}")
                else:
                    logger.warning("[SCM Login] Login failed \u2014 will retry auth per-call")
                return config_dir
            except subprocess.TimeoutExpired:
                logger.warning("[SCM Login] Timed out after 60s")
                return None
            except Exception as e:
                logger.warning(f"[SCM Login] Error: {e}")
                return None

    def fetch_file_content_by_item_state(self, item_id, state_id, file_path=''):
        """
        Fetch the text content of a specific file version using its item-id and state-id.

        These IDs come directly from 'scm list files -j' output, which is already
        used during comparison.  This is the most direct and reliable way to get
        file content ΓÇö no baseline UUID or filepath needed.

        CLI syntax (from 'scm help get file'):
            scm get file <item_id> <state_id> <path-on-disk>
                         -r <repo> -u <user> -P <pass>

        Falls back to REST /resource/itemOid/com.ibm.team.scm.Content endpoint
        if the CLI is unavailable.

        Returns file text (str) or None if binary / unavailable.
        """
        BINARY_EXTS = {
            '.xls', '.xlsx', '.zip', '.exe', '.dll', '.so', '.a', '.o',
            '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.pdf', '.doc', '.docx',
            '.ppt', '.pptx', '.bin', '.lib', '.obj', '.jar', '.class', '.pyc',
        }
        if file_path:
            ext = os.path.splitext(file_path.lower())[1]
            if ext in BINARY_EXTS:
                return None
        else:
            ext = '.tmp'

        if not item_id or not state_id:
            return None

        # Normalise UUIDs ΓÇö EWM may or may not include the leading '_'
        iid = item_id  if item_id.startswith('_')  else '_' + item_id
        sid = state_id if state_id.startswith('_') else '_' + state_id

        skip     = getattr(settings, 'SKIP_SCM_CLI', True)
        scm_path = getattr(settings, 'LSCM_PATH', '')
        scm_ok   = not skip and bool(scm_path) and os.path.exists(scm_path)

        # ΓöÇΓöÇ SCM CLI: scm get file <item_id> <state_id> <output> ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
        if scm_ok:
            tmp_path = None
            try:
                import tempfile
                ext_suffix = os.path.splitext(file_path.lower())[1] if file_path else '.tmp'
                fd, tmp_path = tempfile.mkstemp(suffix=ext_suffix or '.tmp')
                os.close(fd)

                env = os.environ.copy()
                for pv in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy',
                           'NO_PROXY', 'no_proxy'):
                    env.pop(pv, None)

                # positional form: item_id  state_id  path-on-disk
                cmd = [
                    scm_path, '--non-interactive',
                    'get', 'file',
                    iid, sid, tmp_path,
                    '-r', self.server_url,
                    '-u', self.username,
                    '-P', self.password,
                ]
                logger.info(f"[scm get file] item={iid[:16]} state={sid[:16]} path={file_path!r}")
                with _scm_semaphore:
                    result = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=60, env=env,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                    )
                logger.info(
                    f"[scm get file] rc={result.returncode} "
                    f"size={os.path.getsize(tmp_path) if os.path.exists(tmp_path) else 0} "
                    f"stderr={result.stderr[:200]!r}"
                )
                if result.returncode == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                    with open(tmp_path, 'r', encoding='utf-8', errors='replace') as f:
                        return f.read()

            except subprocess.TimeoutExpired:
                logger.warning(f"[scm get file] Timeout for {file_path!r}")
            except Exception as e:
                logger.warning(f"[scm get file] Error: {e}")
            finally:
                if tmp_path:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass

        # ΓöÇΓöÇ REST fallback: /resource/itemOid/com.ibm.team.scm.Content/{sid} ΓöÇ
        # The state-id maps to the FileContent OID.  Requesting it with a
        # non-JSON Accept header returns the raw file bytes on EWM 7.
        try:
            MAX_BYTES = 3 * 1024 * 1024
            url = f'{self.server_url}/resource/itemOid/com.ibm.team.scm.FileContent/{sid}'
            session = self._make_session()
            if session:
                r = session.get(url, timeout=30, stream=True,
                                headers={'Accept': 'application/octet-stream'})
                if r.status_code == 200:
                    raw = b''
                    for chunk in r.iter_content(8192):
                        raw += chunk
                        if len(raw) > MAX_BYTES:
                            return None
                    if raw:
                        return raw.decode('utf-8', errors='replace')
        except Exception as e:
            logger.debug(f"[REST FileContent] {sid[:12]}: {e}")

        return None

    def fetch_file_content_from_baseline(self, baseline_uuid, file_path, component_name=''):
        """
        Fetch file text using: scm get file <baseline_uuid> -b -f <full_repo_path> <output>

        The full_repo_path must be the path relative to the component root as
        returned by 'scm list files' (e.g. 'src/foo.c', not just 'foo.c').
        This mirrors results_viewer._get_baseline_file which is the proven working form.
        """
        BINARY_EXTS = {
            '.xls', '.xlsx', '.zip', '.exe', '.dll', '.so', '.a', '.o',
            '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.pdf', '.doc', '.docx',
            '.ppt', '.pptx', '.bin', '.lib', '.obj', '.jar', '.class', '.pyc',
        }
        ext = os.path.splitext(file_path.lower())[1]
        if ext in BINARY_EXTS:
            return None

        skip     = getattr(settings, 'SKIP_SCM_CLI', True)
        scm_path = getattr(settings, 'LSCM_PATH', '')
        scm_ok   = not skip and bool(scm_path) and os.path.exists(scm_path)

        buuid      = baseline_uuid if baseline_uuid.startswith('_') else '_' + baseline_uuid
        clean_path = file_path.strip('/').replace('\\', '/')

        if not scm_ok:
            logger.debug(f"[scm get file -b] SCM CLI not available for {clean_path!r}")
            return None

        tmp_path = None
        try:
            import tempfile
            fd, tmp_path = tempfile.mkstemp(suffix=ext or '.tmp')
            os.close(fd)

            env = os.environ.copy()
            for pv in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy',
                       'NO_PROXY', 'no_proxy'):
                env.pop(pv, None)

            # Syntax: scm get file <baseline_uuid> -b -f <filepath> -o <output>
            # where -o = overwrite flag (bool), <output> = positional path-on-disk
            # Matches results_viewer._get_baseline_file exactly.
            # -c (component) is required by EWM scm get file -b
            cmd = [
                scm_path, 'get', 'file', buuid, '-b',
                '-f', clean_path,
                '-r', self.server_url, '-u', self.username, '-P', self.password,
                '-o', tmp_path,
            ]
            if component_name:
                cmd += ['-c', component_name]  # lowercase -c is required

            logger.info(
                f"[scm get file -b] baseline={buuid[:16]!r} path={clean_path!r} "
                f"comp={component_name!r}"
            )
            with _scm_semaphore:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=60, env=env,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                )
            size = os.path.getsize(tmp_path) if os.path.exists(tmp_path) else 0
            logger.info(
                f"[scm get file -b] rc={result.returncode} size={size} "
                f"stderr={result.stderr[:300]!r}"
            )
            if result.returncode == 0 and size > 0:
                with open(tmp_path, 'r', encoding='utf-8', errors='replace') as f:
                    return f.read()

        except subprocess.TimeoutExpired:
            logger.warning(f"[scm get file -b] Timeout for {clean_path!r}")
        except Exception as e:
            logger.warning(f"[scm get file -b] Error: {e}")
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

        return None

    def fetch_file_content_by_content_id(self, content_id, file_path=''):
        """
        Fetch text content of a file from RTC via the Content item REST API.

        Uses the content-id (already fetched as part of scm list files / folder
        structure fetch) so no additional CLI calls are required.

        Endpoint: GET /resource/itemOid/com.ibm.team.scm.Content/{content_id}

        Returns: file text as str, or None on binary / error.
        """
        BINARY_EXTS = {
            '.xls', '.xlsx', '.zip', '.exe', '.dll', '.so', '.a', '.o',
            '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.pdf', '.doc', '.docx',
            '.ppt', '.pptx', '.bin', '.lib', '.obj', '.jar', '.class', '.pyc',
        }
        if file_path:
            ext = os.path.splitext(file_path.lower())[1]
            if ext in BINARY_EXTS:
                return None

        if not content_id:
            return None
        if not content_id.startswith('_'):
            content_id = '_' + content_id

        MAX_BYTES = 3 * 1024 * 1024  # 3 MB ΓÇö anything larger is likely binary
        url = f'{self.server_url}/resource/itemOid/com.ibm.team.scm.Content/{content_id}'

        env = os.environ.copy()
        for pv in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy',
                   'NO_PROXY', 'no_proxy'):
            env.pop(pv, None)

        try:
            if _requests_available:
                session = self._make_session()
                if session:
                    r = session.get(url, timeout=30, stream=True)
                    if r.status_code != 200:
                        logger.debug(f"content fetch HTTP {r.status_code} for {content_id[:12]}")
                        return None
                    raw = b''
                    for chunk in r.iter_content(8192):
                        raw += chunk
                        if len(raw) > MAX_BYTES:
                            return None  # too large / binary
                    try:
                        return raw.decode('utf-8', errors='replace')
                    except Exception:
                        return None

            # curl fallback
            result = subprocess.run(
                ['curl.exe', '-k', '-L', '--noproxy', '*',
                 '-u', f'{self.username}:{self.password}',
                 '-X', 'GET', url,
                 '--max-filesize', str(MAX_BYTES)],
                capture_output=True, timeout=30, env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            )
            if result.returncode == 0 and result.stdout:
                raw = result.stdout
                if len(raw) > MAX_BYTES:
                    return None
                text = raw.decode('utf-8', errors='replace')
                # If the server returned a JSON error body, discard it
                stripped = text.strip()
                if (stripped.startswith('{') or stripped.startswith('[')) and len(text) < 8000:
                    try:
                        parsed = json.loads(text)
                        if isinstance(parsed, dict) and (
                            'error' in parsed or 'Reason' in parsed or 'errorCode' in parsed
                        ):
                            return None
                    except Exception:
                        pass
                return text
            return None

        except Exception as e:
            logger.debug(f"fetch_file_content_by_content_id error ({content_id[:12]}): {e}")
            return None

    def fetch_baseline_info(self, baseline_uuid):
        """
        Fetch baseline metadata (name, comment, author, created-date) via REST API.
        Returns a dict or {} on failure.
        """
        if not baseline_uuid or baseline_uuid == 'N/A':
            return {}
        if not baseline_uuid.startswith('_'):
            baseline_uuid = '_' + baseline_uuid

        url = f'{self.server_url}/resource/itemOid/com.ibm.team.scm.Baseline/{baseline_uuid}'
        try:
            session = self._make_session()
            data    = self._get_json(session, url, timeout=15)
            if not data:
                return {}

            info = {
                'name':      data.get('name', data.get('dc:title', '')),
                'comment':   data.get('comment', data.get('dc:description', '')),
                'author':    '',
                'timestamp': data.get('modified', data.get('dc:modified', '')),
            }
            creator = data.get('creator', data.get('rtc_cm:com.ibm.team.process.contributor', {}))
            if isinstance(creator, dict):
                info['author'] = creator.get('name',
                                 creator.get('dc:title',
                                 creator.get('userId', '')))
            # Changeset reference (the most recent changeset baked into this baseline)
            for key in ('lastChangeset', 'changeSet', 'rtc_scm:changeSet'):
                cs = data.get(key)
                if isinstance(cs, dict):
                    href = cs.get('@id', cs.get('href', cs.get('url', '')))
                    if href:
                        info['changeset_url'] = href
                    break
            return info
        except Exception as e:
            logger.debug(f"fetch_baseline_info error for {baseline_uuid[:12]}: {e}")
            return {}

    def fetch_baseline_changesets_scm(self, baseline_uuid, component_name=''):
        """
        Fetch changeset list for a baseline using SCM CLI.
        Returns list of changeset dicts with keys: uuid, author, comment, timestamp.
        Falls back to [] on any failure.
        """
        skip     = getattr(settings, 'SKIP_SCM_CLI', True)
        scm_path = getattr(settings, 'LSCM_PATH', '')
        if skip or not scm_path or not os.path.exists(scm_path):
            return []

        buuid      = baseline_uuid if baseline_uuid.startswith('_') else '_' + baseline_uuid
        config_dir = _scm_config_dir

        cmd = [scm_path, '--non-interactive']
        if config_dir:
            cmd += ['--config', config_dir]
        cmd += [
            'list', 'changesets',
            '-b', buuid,
            '-r', self.server_url,
            '-u', self.username,
            '-P', self.password,
            '-j',
        ]
        if component_name:
            cmd += ['-C', component_name]

        env = os.environ.copy()
        for pv in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy',
                   'NO_PROXY', 'no_proxy'):
            env.pop(pv, None)

        try:
            with _scm_semaphore:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=60, env=env,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                )
            if result.returncode != 0 or not result.stdout.strip():
                logger.debug(f"list changesets returned rc={result.returncode}: {result.stderr[:200]}")
                return []
            data = json.loads(result.stdout)
            changesets = []
            raw_list = (data.get('changesets') or data.get('changes') or
                        data.get('workItems') or [])
            if not raw_list and isinstance(data, list):
                raw_list = data
            for item in raw_list:
                if not isinstance(item, dict):
                    continue
                cs = {
                    'uuid':      item.get('uuid', item.get('itemId', '')),
                    'author':    item.get('author', item.get('modifier', '')),
                    'comment':   item.get('comment', item.get('description', '')),
                    'timestamp': item.get('modified', item.get('created', '')),
                }
                changesets.append(cs)
            return changesets[:30]  # cap at 30
        except Exception as e:
            logger.debug(f"fetch_baseline_changesets_scm error: {e}")
            return []

    def _fetch_scm_file_list(self, baseline_uuid):
        """
        Use the EWM/RTC SCM CLI (scm.exe) to list all files in a component baseline.

        Command:
            scm --non-interactive --config <dir> list files -b -D all -j
                -r <server> -u <user> -P <pass> <baseline_uuid>

        A module-level semaphore limits concurrency to 3 simultaneous scm.exe
        processes so the server is not overwhelmed by parallel JVM+auth sessions.

        Returns {'files': [...], 'folders': {}} or None on failure.
        """
        skip     = getattr(settings, 'SKIP_SCM_CLI', True)
        scm_path = getattr(settings, 'LSCM_PATH', '')
        if skip or not scm_path or not os.path.exists(scm_path):
            return None

        try:
            buuid      = baseline_uuid if baseline_uuid.startswith('_') else '_' + baseline_uuid
            config_dir = self._scm_login()   # no-op if already done

            cmd = [scm_path, '--non-interactive']
            if config_dir:
                cmd += ['--config', config_dir]
            cmd += [
                'list', 'files',
                '-b',          # flag: selector is a baseline
                '-D', 'all',   # infinite depth
                '-j',          # JSON output
                '-r', self.server_url,
                '-u', self.username,
                '-P', self.password,
                buuid,         # positional <selector> ΓÇö MUST be last
            ]

            env = os.environ.copy()
            for pv in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy',
                       'NO_PROXY', 'no_proxy'):
                env.pop(pv, None)

            with _scm_semaphore:   # max 3 concurrent scm.exe processes
                logger.info(f"[SCM CLI] Running list files for baseline {buuid[:16]}...")
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=300, env=env,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                )

            logger.info(
                f"[SCM CLI] list files: rc={result.returncode} "
                f"stdout_len={len(result.stdout.strip())} "
                f"stderr={result.stderr.strip()[:300]!r}"
            )

            raw = result.stdout.strip()
            if not raw:
                logger.warning("[SCM CLI] empty stdout \u2014 CLI unavailable or auth failed")
                return None

            try:
                data = json.loads(raw)
            except Exception:
                logger.warning(f"[SCM CLI] non-JSON stdout: {raw[:300]!r}")
                return None

            if isinstance(data, dict):
                logger.info(f"[SCM CLI] JSON top-level keys: {list(data.keys())}")
            else:
                logger.info(f"[SCM CLI] JSON root type: {type(data).__name__}")

            # Try multiple JSON structures that different EWM versions return
            raw_files = []
            if isinstance(data, dict) and 'baseline' in data:
                raw_files = data['baseline'].get('remote-files', [])
            if not raw_files and isinstance(data, dict) and 'workspaces' in data:
                for ws in data.get('workspaces', []):
                    for comp in ws.get('components', []):
                        raw_files.extend(comp.get('files', []))
            if not raw_files and isinstance(data, list):
                raw_files = data
            if not raw_files and isinstance(data, dict) and 'files' in data:
                raw_files = data['files']

            logger.info(
                f"[SCM CLI] raw_files count={len(raw_files)}  "
                f"sample={str(raw_files[:1])[:200]}"
            )

            files = []
            for item in raw_files:
                if not isinstance(item, dict):
                    continue
                path = (item.get('path') or item.get('remotePath') or
                        item.get('name') or '').strip().lstrip('/')
                if not path or path.endswith('/'):
                    continue
                name = path.rsplit('/', 1)[-1]
                files.append({
                    'name'      : name,
                    'path'      : path,
                    'uuid'      : item.get('item-id', item.get('itemId', '')),
                    'state-id'  : item.get('state-id', item.get('stateId', '')),
                    'content-id': item.get('content-id', item.get('contentId', '')),
                })

            logger.info(f"[SCM CLI] \u2713 {len(files)} files for baseline {buuid[:16]}")
            return {'files': files, 'folders': {}}

        except subprocess.TimeoutExpired:
            logger.warning("[SCM CLI] Timed out (300s) \u2014 baseline may be very large")
            return None
        except Exception as e:
            logger.warning(f"[SCM CLI] Error: {e}")
            return None

    def _make_jazz_session(self):
        """
        Create a requests Session authenticated via Jazz Form Authentication (JFA).

        RTC's /service/ endpoints (filesystem, SCM) require Jazz session cookies,
        not just HTTP Basic Auth.  JFA flow:
          1. GET /authenticated/identity  ΓÇô triggers the auth challenge
          2. POST /j_security_check       ΓÇô submit credentials, receive session cookie
          3. Subsequent requests send the cookie automatically

        Falls back to a plain Basic-Auth session if JFA fails.
        Returns None if requests library is unavailable.
        """
        if not _requests_available:
            return None
        try:
            import urllib3
            urllib3.disable_warnings()

            session = _requests.Session()  # type: ignore[possibly-undefined]
            session.verify = False
            max_pool = max(1, min(getattr(settings, 'MAX_WORKERS', 20), 30))
            adapter = _HTTPAdapter(  # type: ignore[possibly-undefined]
                pool_connections=max_pool,
                pool_maxsize=max_pool * 2,
                max_retries=_Retry(  # type: ignore[possibly-undefined]
                    total=2, backoff_factor=0.3,
                    status_forcelist=[429, 500, 502, 503, 504]
                )
            )
            session.mount('https://', adapter)
            session.mount('http://', adapter)

            # Step 1: touch the authenticated endpoint to let RTC set JAZZ_CSRF tokens
            identity_url = f'{self.server_url}/authenticated/identity'
            try:
                resp = session.get(identity_url, timeout=15,
                                   headers={'Accept': 'application/json'})
                logger.info(f"[JFA] identity probe: HTTP {resp.status_code}")
            except Exception as e:
                logger.warning(f"[JFA] identity probe failed: {e}")

            # Step 2: POST credentials to j_security_check
            jsc_url = f'{self.server_url}/j_security_check'
            jsc_payload = {'j_username': self.username, 'j_password': self.password}
            try:
                resp = session.post(
                    jsc_url,
                    data=jsc_payload,
                    headers={'Content-Type': 'application/x-www-form-urlencoded'},
                    timeout=30,
                    allow_redirects=True,
                )
                logger.info(
                    f"[JFA] j_security_check: HTTP {resp.status_code} "
                    f"url={resp.url[:60]} cookies={list(session.cookies.keys())}"
                )
                if resp.status_code in (200, 302):
                    logger.info("[JFA] \u2713 Jazz Form Authentication succeeded")
                    # Also keep Basic Auth as a fallback for resource/itemOid endpoints
                    session.auth = (self.username, self.password)
                    return session
            except Exception as e:
                logger.warning(f"[JFA] j_security_check POST failed: {e}")

            # Fallback: plain Basic Auth session
            logger.warning("[JFA] Falling back to Basic Auth session")
            session.auth = (self.username, self.password)
            return session
        except Exception as e:
            logger.warning(f"Could not create Jazz session: {e}")
            return None

    def _get_json(self, session, url, timeout=20):
        """GET a URL and return parsed JSON, or None on any error."""
        try:
            if session is not None and _requests_available:
                r = session.get(url, timeout=timeout)
                if r.status_code == 200 and r.text.strip():
                    return r.json()
                return None
            # Fallback to curl when requests is unavailable
            result = subprocess.run(
                ['curl.exe', '-k', '-L', '--noproxy', '*',
                 '-u', f'{self.username}:{self.password}',
                 '-X', 'GET', url,
                 '-H', 'Accept: application/json',
                 '-H', 'OSLC-Core-Version: 2.0'],
                capture_output=True, text=True, timeout=timeout,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            )
            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout)
            return None
        except Exception:
            return None

    def fetch_snapshot_components(self, snapshot_url, username=None, password=None, snapshot_name='Snapshot', progress_callback=None):
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
                        curl_command, capture_output=True, text=True, timeout=45,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                    )
                    request_elapsed = time.time() - request_start
                    logger.info(f'{snapshot_name}: Response time: {request_elapsed:.2f}s')
                except subprocess.TimeoutExpired:
                    logger.warning(f'{snapshot_name}: Request timed out (45s) for {candidate_url} ΓÇö retrying once')
                    try:
                        candidate_result = subprocess.run(
                            curl_command, capture_output=True, text=True, timeout=60,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                        )
                    except subprocess.TimeoutExpired:
                        logger.warning(f'{snapshot_name}: Retry also timed out (60s) ΓÇö skipping URL')
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
                logger.info(f'{snapshot_name}: Γ£ô Got valid response from: {candidate_url}')
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

                # ΓöÇΓöÇ Worker count ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
                # Use MAX_WORKERS from settings (default 20), capped at 30 to
                # avoid hammering RTC. Previously was hard-capped at 12.
                requested_workers = getattr(settings, 'MAX_WORKERS', 20)
                try:
                    requested_workers = int(requested_workers)
                except Exception:
                    requested_workers = 20
                max_workers = max(1, min(requested_workers, 30))

                logger.info(
                    f'{snapshot_name}: Fetching component details for {total_baselines} baselines '
                    f'(workers={max_workers})...'
                )

                # ΓöÇΓöÇ Shared HTTP session & caches ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
                # One session ΓåÆ connection pool ΓåÆ no TCP handshake per request.
                # Previously each request spawned a fresh curl.exe process.
                session = self._make_session()
                component_name_cache: dict = {}
                cache_lock = threading.Lock()

                def get_component_name(comp_item_id: str) -> str | None:
                    """Return cached component name, fetching only on first miss."""
                    with cache_lock:
                        if comp_item_id in component_name_cache:
                            return component_name_cache[comp_item_id]

                    comp_url = (f'{server_url}/resource/itemOid/'
                                f'com.ibm.team.scm.Component/{comp_item_id}')
                    data = self._get_json(session, comp_url, timeout=20)
                    if data:
                        name = (data.get('name') or data.get('dcterms:title')
                                or data.get('dc:title') or data.get('title'))
                        if name:
                            with cache_lock:
                                component_name_cache[comp_item_id] = name
                            return name
                    return None

                def fetch_baseline_component(baseline_ref):
                    """
                    Fetch component info for a single baseline.

                    Speed improvement: The baseline JSON already contains the
                    component itemId inline under the 'component' key.
                    We extract it directly instead of making a second HTTP call
                    to resolve the component ID ΓÇö the only extra call needed is
                    the component-name lookup (which is heavily cached).
                    """
                    if not isinstance(baseline_ref, dict):
                        return None

                    item_id   = baseline_ref.get('itemId', '')
                    state_id  = baseline_ref.get('stateId', '')
                    if not item_id:
                        return None

                    # ΓöÇΓöÇ Fast path: component ID embedded in baseline_ref ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
                    # Some RTC versions embed the component reference directly
                    # inside the baseline list entry, avoiding a round-trip.
                    inline_comp = (baseline_ref.get('component')
                                   or baseline_ref.get('com.ibm.team.scm.Component'))
                    if isinstance(inline_comp, dict) and inline_comp.get('itemId'):
                        comp_item_id = inline_comp['itemId']
                        comp_name = get_component_name(comp_item_id)
                        if comp_name:
                            return {
                                'name': comp_name,
                                'uuid': comp_item_id,
                                'baseline_uuid': item_id,
                                'state_id': state_id,
                            }

                    # ΓöÇΓöÇ Slow path: fetch baseline details first ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
                    baseline_url = (f'{server_url}/resource/itemOid/'
                                    f'com.ibm.team.scm.Baseline/{item_id}')
                    data = self._get_json(session, baseline_url, timeout=25)
                    if not data:
                        logger.debug(f'{snapshot_name}: No data for baseline {item_id[:8]}')
                        return None

                    comp_ref = (data.get('component')
                                or data.get('com.ibm.team.scm.Component'))
                    if not isinstance(comp_ref, dict) or not comp_ref.get('itemId'):
                        logger.debug(f'{snapshot_name}: No component ref in baseline {item_id[:8]}')
                        return None

                    comp_item_id = comp_ref['itemId']
                    comp_name = get_component_name(comp_item_id)
                    if not comp_name:
                        logger.debug(f'{snapshot_name}: Could not resolve name for {comp_item_id[:8]}')
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
                processed = 0

                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    pending = {executor.submit(fetch_baseline_component, b) for b in baseline_list}

                    while pending:
                        done, pending = wait(pending, timeout=5)

                        for future in done:
                            processed += 1
                            try:
                                component = future.result()
                                if component:
                                    components.append(component)
                            except Exception as e:
                                logger.debug(f'{snapshot_name}: Baseline processing error: {e}')

                        if progress_callback:
                            try:
                                progress_callback(processed, total_baselines, f'{len(components)} components found')
                            except Exception:
                                pass

                        now = _time.time()
                        if (processed % 20 == 0 and processed > 0) or processed == total_baselines:
                            elapsed = now - start_time
                            rate = processed / elapsed if elapsed > 0 else 0
                            logger.info(
                                f'{snapshot_name}: Progress: {processed}/{total_baselines} baselines '
                                f'({len(components)} components found) ΓÇö '
                                f'{elapsed:.1f}s  ({rate:.1f} baselines/s)'
                            )
                            last_heartbeat = now
                        elif now - last_heartbeat >= 10:
                            elapsed = now - start_time
                            logger.info(
                                f'{snapshot_name}: Still working... {processed}/{total_baselines} processed, '
                                f'{len(pending)} pending, {len(components)} components found - {elapsed:.1f}s'
                            )
                            last_heartbeat = now

                logger.info(f'{snapshot_name}: Γ£ô Successfully extracted {len(components)} components')

            if len(components) == 0:
                logger.warning(f'{snapshot_name}: No components could be extracted from {len(baseline_list) if baseline_list else 0} baselines')

            return components

        except Exception as e:
            logger.error(f'{snapshot_name}: Error fetching components: {e}')
            import traceback
            logger.debug(traceback.format_exc())
            return []
    
    def _compare_one_component(self, name, comp1, comp2):
        """
        Compare a single pair of snapshot components.

        Decision logic:
          1. Same baseline UUID  ΓåÆ Identical immediately (no fetch needed; baselines
             are immutable, so identical UUID guarantees identical content).
          2. Different baseline UUIDs ΓåÆ attempt file-level fetch+compare for detail.
             The UUID difference is the *ground truth* for status:
               ΓÇó Fetch succeeded and returned files ΓåÆ use file comparison result:
                   - differences found  ΓåÆ 'Different'
                   - no differences     ΓåÆ 'Identical'
               ΓÇó Fetch returned 0 files (API unavailable / empty component) ΓåÆ
                   fall back to UUID signal ΓåÆ 'Different'
               ΓÇó Fetch raised an exception ΓåÆ 'Different' (safe default)

        Returns: entry dict with 'name', 'status', and comparison data.
        """
        entry = {'name': name, 'snapshot1': comp1, 'snapshot2': comp2}

        if comp1 and comp2:
            baseline1 = comp1.get('baseline_uuid', '') or comp1.get('uuid', '')
            baseline2 = comp2.get('baseline_uuid', '') or comp2.get('uuid', '')

            entry['baseline1_uuid'] = baseline1
            entry['baseline2_uuid'] = baseline2

            logger.info(f"\n--- Component: {name} ---")
            logger.info(f"  Baseline 1: {baseline1}")
            logger.info(f"  Baseline 2: {baseline2}")
            logger.info(f"  Same baseline UUID: {baseline1 == baseline2}")

            # ΓöÇΓöÇ Rule 1: Same UUID ΓåÆ Identical, no fetch ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
            if baseline1 == baseline2 and baseline1:
                logger.info(f"  ΓåÆ '{name}': Identical (same baseline UUID ΓÇô no fetch needed)")
                entry['status'] = 'Identical'
                return entry

            # ΓöÇΓöÇ Rule 2: Different UUIDs ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
            # Ground truth: UUIDs differ ΓåÆ Different.
            # Attempt file-level fetch to enrich with detail AND to allow
            # override to 'Identical' only when the fetch actually returned
            # files (proving the content is genuinely unchanged).
            entry['status'] = 'Different'   # set from UUID ΓÇô overridden below only if safe
            logger.info(
                f"  ΓåÆ '{name}': baseline UUIDs differ ΓÇô fetching folder structures in parallel..."
            )
            try:
                with ThreadPoolExecutor(max_workers=2) as _ex:
                    _f1 = _ex.submit(self.fetch_baseline_folder_structure, baseline1, name)
                    _f2 = _ex.submit(self.fetch_baseline_folder_structure, baseline2, name)
                    folder1, folder2 = _f1.result(), _f2.result()

                total_f1 = len(self._get_all_files_from_structure(folder1))
                total_f2 = len(self._get_all_files_from_structure(folder2))
                logger.info(f"  Folder 1: {total_f1} files  |  Folder 2: {total_f2} files")

                if total_f1 == 0 and total_f2 == 0:
                    # Folder fetch returned nothing ΓÇô API issue; keep UUID-based status
                    logger.warning(
                        f"  Folder fetch returned 0 files for both baselines of '{name}'. "
                        f"Keeping UUID-based status: Different"
                    )
                else:
                    file_cmp = self.compare_folder_structures(folder1, folder2)
                    entry['folder_structure1'] = folder1
                    entry['folder_structure2'] = folder2
                    entry['file_comparison']   = file_cmp
                    logger.info(
                        f"  File comparison: {file_cmp.get('modified', 0)} modified, "
                        f"{file_cmp.get('added', 0)} added, "
                        f"{file_cmp.get('removed', 0)} removed, "
                        f"{file_cmp.get('unchanged', 0)} unchanged"
                    )
                    has_changes = (
                        file_cmp.get('added',    0) > 0
                        or file_cmp.get('modified', 0) > 0
                        or file_cmp.get('removed',  0) > 0
                    )
                    entry['status'] = 'Different' if has_changes else 'Identical'
                    logger.info(f"  ΓåÆ '{name}': {entry['status']} (file-level result)")

            except Exception as e:
                logger.warning(f"  File-level fetch failed for '{name}': {e} ΓÇô keeping Different")

        elif comp1:
            entry['status'] = 'Removed in Snapshot 2'
            entry['baseline1_uuid'] = comp1.get('baseline_uuid', '') or comp1.get('uuid', '')
            entry['baseline2_uuid'] = 'N/A'
        else:
            entry['status'] = 'Added in Snapshot 2'
            entry['baseline1_uuid'] = 'N/A'
            entry['baseline2_uuid'] = comp2.get('baseline_uuid', '') or comp2.get('uuid', '')

        if 'status' not in entry:
            logger.error(f"ERROR: Component '{name}' has no status! Defaulting to 'Different'")
            entry['status'] = 'Different'

        return entry

    def compare_snapshots(self, snap1_components, snap2_components, progress_callback=None):
        """
        Compare two sets of snapshot components with file-level analysis.
        Always performs file-level comparison to detect version differences.

        Components are compared in parallel using up to MAX_WORKERS threads.
        Within each component the two baseline folder structures are also
        fetched concurrently, giving a compounding speed-up.

        Args:
            snap1_components: List of components from snapshot 1
            snap2_components: List of components from snapshot 2
            progress_callback: Optional callback(current, total, message) for progress updates

        Returns: List of comparison result dicts
        """
        try:
            snap1_dict = {c['name']: c for c in snap1_components if c.get('name')}
            snap2_dict = {c['name']: c for c in snap2_components if c.get('name')}
            all_names = set(snap1_dict) | set(snap2_dict)
            total_components = len(all_names)

            logger.info(f"=== SNAPSHOT COMPARISON START ===")
            logger.info(f"Snapshot 1: {len(snap1_components)} components")
            logger.info(f"Snapshot 2: {len(snap2_components)} components")
            logger.info(f"Common components: {len(snap1_dict.keys() & snap2_dict.keys())}")
            logger.info(f"Only in Snapshot 1: {len(snap1_dict.keys() - snap2_dict.keys())}")
            logger.info(f"Only in Snapshot 2: {len(snap2_dict.keys() - snap1_dict.keys())}")
            logger.info(f"Total components to compare: {total_components}")

            # Pre-login to EWM SCM CLI once before parallel workers start.
            # This caches credentials in a temp config dir so all worker threads
            # can reuse the session instead of each authenticating from scratch.
            self._scm_login()

            # ΓöÇΓöÇ Parallel component comparison ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
            max_cmp_workers = max(1, min(getattr(settings, 'MAX_WORKERS', 20), 30))
            logger.info(
                f"Starting parallel comparison of {total_components} components "
                f"with {max_cmp_workers} workers..."
            )

            results = []
            completed_count = 0
            count_lock = threading.Lock()
            sorted_names = sorted(all_names)

            with ThreadPoolExecutor(max_workers=max_cmp_workers) as executor:
                future_to_name = {
                    executor.submit(
                        self._compare_one_component,
                        name,
                        snap1_dict.get(name),
                        snap2_dict.get(name),
                    ): name
                    for name in sorted_names
                }

                for future in as_completed(future_to_name):
                    name = future_to_name[future]
                    with count_lock:
                        completed_count += 1
                        current = completed_count
                    try:
                        entry = future.result()
                        results.append(entry)
                    except Exception as e:
                        logger.error(f"Component comparison failed for '{name}': {e}")
                        results.append({
                            'name': name,
                            'status': 'Modified',
                            'snapshot1': snap1_dict.get(name),
                            'snapshot2': snap2_dict.get(name),
                        })

                    if progress_callback:
                        try:
                            progress_callback(
                                current, total_components,
                                f"≡ƒöì Comparing component {current}/{total_components}: {name}"
                            )
                        except Exception as e:
                            logger.debug(f"Progress callback error: {e}")

            # Restore deterministic ordering
            results.sort(key=lambda r: r['name'])

            logger.info(f"\n=== SNAPSHOT COMPARISON COMPLETE ===")
            logger.info(f"Total components analyzed: {len(results)}")
            
            # Summary statistics
            different  = sum(1 for r in results if r['status'] == 'Different')
            identical  = sum(1 for r in results if r['status'] == 'Identical')
            added      = sum(1 for r in results if 'Added'   in r['status'])
            removed    = sum(1 for r in results if 'Removed' in r['status'])

            logger.info(f"  Different: {different}")
            logger.info(f"  Identical: {identical}")
            logger.info(f"  Added: {added}")
            logger.info(f"  Removed: {removed}")
            
            return results
            
        except Exception as e:
            logger.error(f"Error in compare_snapshots: {e}")
            return []


    def fetch_baseline_folder_structure(self, baseline_uuid, component_name='Unknown'):
        """
        Fetch folder/file structure from a baseline.

        Strategy (fast-path first):
          1. SCM CLI (scm list files -b ... -j) ΓÇö no REST /service/ auth needed.
             Returns immediately when the CLI is available; skips all REST steps.
          2. REST API fallback: Baseline ΓåÆ Component ΓåÆ Root Folder ΓåÆ BFS.
             NOTE: The IVersionableRestService BFS endpoint is disabled on the
             Bosch RTC server (HTTP 400 CRJAZ1168E), so this path returns empty.

        Returns: {'folders': {...}, 'files': [{name, path, uuid, content-id, state-id}]}
        """
        try:
            if not baseline_uuid:
                logger.warning(f"No baseline UUID provided for {component_name}")
                return {'folders': {}, 'files': []}

            if not baseline_uuid.startswith('_'):
                baseline_uuid = '_' + baseline_uuid

            # ΓöÇΓöÇ Fast path: SCM CLI ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
            # Try the CLI before any REST calls.  When it works, we return
            # immediately and skip Step 1, Step 2, JFA, and the BFS entirely.
            scm_structure = self._fetch_scm_file_list(baseline_uuid)
            if scm_structure is not None and scm_structure.get('files'):
                logger.info(
                    f"\u2713 SCM CLI: {len(scm_structure['files'])} files "
                    f"for {component_name} ({baseline_uuid[:12]})"
                )
                return scm_structure

            # ΓöÇΓöÇ REST fallback (Steps 1 & 2) ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
            # Only reached when the SCM CLI is unavailable or returns 0 files.
            logger.info(f"Fetching baseline structure for {component_name}: {baseline_uuid[:12]}...")
            baseline_uri = f'{self.server_url}/resource/itemOid/com.ibm.team.scm.Baseline/{baseline_uuid}'

            # Step 1: baseline metadata ΓåÆ component ID
            baseline_curl = [
                'curl.exe', '-k', '-L', '--noproxy', '*',
                '-u', f'{self.username}:{self.password}',
                '-X', 'GET', baseline_uri,
                '-H', 'Accept: application/json',
                '-H', 'OSLC-Core-Version: 2.0',
            ]
            result = subprocess.run(
                baseline_curl, capture_output=True, text=True, timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            )
            if result.returncode != 0 or not result.stdout.strip():
                logger.warning(f"Failed to fetch baseline metadata for {component_name}")
                return {'folders': {}, 'files': []}
            baseline_data = json.loads(result.stdout)
            logger.info(f"[Step1] Baseline JSON keys for {component_name}: {list(baseline_data.keys())}")
            component_ref = baseline_data.get('component') or baseline_data.get('com.ibm.team.scm.Component', {})
            component_id = component_ref.get('itemId', '')
            if not component_id:
                logger.warning(f"No component ID in baseline {baseline_uuid[:12]}")
                return {'folders': {}, 'files': []}

            # Step 2: component metadata ΓåÆ root folder ID
            comp_url = f'{self.server_url}/resource/itemOid/com.ibm.team.scm.Component/{component_id}'
            comp_curl = [
                'curl.exe', '-k', '-L', '--noproxy', '*',
                '-u', f'{self.username}:{self.password}',
                '-X', 'GET', comp_url,
                '-H', 'Accept: application/json',
                '-H', 'OSLC-Core-Version: 2.0',
                '-H', f'OSLC-Configuration-Context: {baseline_uri}',
            ]
            result = subprocess.run(
                comp_curl, capture_output=True, text=True, timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            )
            if result.returncode != 0 or not result.stdout.strip():
                logger.warning(f"Failed to fetch component metadata for {component_name}")
                return {'folders': {}, 'files': []}
            comp_data = json.loads(result.stdout)
            logger.info(f"[Step2] Component JSON keys for {component_name}: {list(comp_data.keys())}")
            root_folder = comp_data.get('rootFolder', {})
            root_folder_id = root_folder.get('itemId', '')
            root_folder_state_id = root_folder.get('stateId', root_folder.get('state-id', ''))
            logger.info(
                f"[Step2] rootFolder itemId={root_folder_id[:16] if root_folder_id else 'N/A'} "
                f"stateId={root_folder_state_id[:16] if root_folder_state_id else 'N/A'}"
            )
            if not root_folder_id:
                logger.warning(f"No root folder in component {component_name}")
                return {'folders': {}, 'files': []}

            # Step 3: BFS via /service/ endpoint.
            # NOTE: Disabled on Bosch RTC (returns HTTP 400 CRJAZ1168E).
            # Return empty so the caller keeps the UUID-based 'Different' status.
            logger.warning(
                f"[{component_name}] SCM CLI returned 0 files and REST BFS is disabled "
                f"on this server \u2014 no file-level data available"
            )
            return {'folders': {}, 'files': []}

        except Exception as e:
            logger.error(f"Error fetching baseline structure for {component_name}: {e}")
            import traceback; logger.debug(traceback.format_exc())
            return {'folders': {}, 'files': []}
    
    def _get_folder_children(self, folder_id, baseline_uuid, current_path='',
                              baseline_uri='', jazz_session=None):
        """
        Fetch the *direct* children of a single RTC folder.

        Strategy order (first success wins):
          0. Jazz-session GET with oslc_config.context  (uses proper JFA cookies)
          1. Jazz-session GET with configuration param
          2. Jazz-session GET without any config context
          3. curl GET with oslc_config.context header+param  (fallback)
          4. curl GET with configuration header+param
          5. curl GET with no config context

        The full JSON response body is logged at INFO level so the RTC response
        format can be diagnosed from the application logs.
        """
        from urllib.parse import quote as _url_quote

        if not folder_id.startswith('_'):
            folder_id = '_' + folder_id
        if baseline_uuid and not baseline_uuid.startswith('_'):
            baseline_uuid = '_' + baseline_uuid

        if not baseline_uri and baseline_uuid:
            baseline_uri = (
                f'{self.server_url}/resource/itemOid/com.ibm.team.scm.Baseline/{baseline_uuid}'
            )

        base_url = (
            f'{self.server_url}/service/com.ibm.team.filesystem.service.rest'
            f'.IVersionableRestService/folder/{folder_id}/children'
        )
        encoded_uri = _url_quote(baseline_uri, safe='') if baseline_uri else ''

        # ΓöÇΓöÇ Session-based strategies (use JFA cookies) ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
        if jazz_session is not None and _requests_available:
            session_candidates = []
            if baseline_uri:
                session_candidates.append((
                    f'{base_url}?oslc_config.context={encoded_uri}',
                    {
                        'Accept': 'application/json',
                        'OSLC-Core-Version': '2.0',
                        'OSLC-Configuration-Context': baseline_uri,
                    },
                    'session+oslc_config',
                ))
                session_candidates.append((
                    f'{base_url}?configuration={baseline_uuid}',
                    {
                        'Accept': 'application/json',
                        'OSLC-Core-Version': '2.0',
                        'Configuration-Context': baseline_uuid,
                    },
                    'session+configuration',
                ))
            session_candidates.append((
                base_url,
                {'Accept': 'application/json', 'OSLC-Core-Version': '2.0'},
                'session+no-context',
            ))

            for url, headers, strategy in session_candidates:
                try:
                    resp = jazz_session.get(url, headers=headers, timeout=30, verify=False)
                    raw = resp.text.strip() if resp.text else ''
                    logger.info(
                        f"[FolderFetch] ({strategy}) folder={folder_id[:12]} "
                        f"HTTP={resp.status_code} len={len(raw)} "
                        f"body_preview={raw[:600]!r}"
                    )
                    if resp.status_code != 200 or not raw:
                        continue
                    if raw.lower().startswith('<'):   # HTML redirect / login page
                        logger.warning(f"[FolderFetch] ({strategy}) got HTML response ΓÇô likely auth redirect")
                        continue
                    try:
                        data = resp.json()
                    except Exception as je:
                        logger.warning(f"[FolderFetch] ({strategy}) JSON parse error: {je}")
                        continue
                    if not isinstance(data, dict):
                        logger.warning(f"[FolderFetch] ({strategy}) non-dict JSON: {type(data)}")
                        continue

                    logger.info(f"[FolderFetch] ({strategy}) JSON top-level keys: {list(data.keys())}")

                    children = (
                        data.get('children')
                        or data.get('versionables')
                        or data.get('pathEntries')
                        or data.get('items')
                        or data.get('versionable')
                        or data.get('entries')
                        or []
                    )
                    if not children:
                        logger.info(f"[FolderFetch] ({strategy}) 0 children ΓÇô trying next strategy")
                        continue

                    logger.info(f"[FolderFetch] \u2713 {len(children)} children via strategy='{strategy}'")
                    return self._parse_folder_children(children, current_path)

                except Exception as e:
                    logger.warning(f"[FolderFetch] ({strategy}) error: {e}")
                    continue

        # ΓöÇΓöÇ curl fallback strategies ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
        curl_candidates = []
        if baseline_uri:
            curl_candidates.append((
                f'{base_url}?oslc_config.context={encoded_uri}',
                ['Accept: application/json', 'OSLC-Core-Version: 2.0',
                 f'OSLC-Configuration-Context: {baseline_uri}'],
                'curl+oslc_config',
            ))
            curl_candidates.append((
                f'{base_url}?configuration={baseline_uuid}',
                ['Accept: application/json', 'OSLC-Core-Version: 2.0',
                 f'Configuration-Context: {baseline_uuid}'],
                'curl+configuration',
            ))
        curl_candidates.append((
            base_url,
            ['Accept: application/json', 'OSLC-Core-Version: 2.0'],
            'curl+no-context',
        ))

        for folder_url, headers, strategy in curl_candidates:
            curl_cmd = [
                'curl.exe', '-k', '-L', '--noproxy', '*',
                '-u', f'{self.username}:{self.password}',
                '-X', 'GET', folder_url,
            ]
            for h in headers:
                curl_cmd.extend(['-H', h])
            try:
                result = subprocess.run(
                    curl_cmd, capture_output=True, text=True, timeout=30,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                )
            except Exception as e:
                logger.warning(f"[FolderFetch] ({strategy}) curl error: {e}")
                continue

            raw = result.stdout.strip()
            logger.info(
                f"[FolderFetch] ({strategy}) curl code={result.returncode} "
                f"len={len(raw)} body_preview={raw[:600]!r}"
            )
            if result.returncode != 0 or not raw:
                continue
            if raw.lower().startswith('<'):
                logger.warning(f"[FolderFetch] ({strategy}) got HTML ΓÇô auth redirect?")
                continue
            try:
                data = json.loads(raw)
            except Exception as je:
                logger.warning(f"[FolderFetch] ({strategy}) JSON error: {je}")
                continue
            if not isinstance(data, dict):
                continue

            logger.info(f"[FolderFetch] ({strategy}) JSON keys: {list(data.keys())}")

            children = (
                data.get('children')
                or data.get('versionables')
                or data.get('pathEntries')
                or data.get('items')
                or data.get('versionable')
                or data.get('entries')
                or []
            )
            if not children:
                logger.info(f"[FolderFetch] ({strategy}) 0 children ΓÇô trying next")
                continue

            logger.info(f"[FolderFetch] \u2713 {len(children)} children via strategy='{strategy}'")
            return self._parse_folder_children(children, current_path)

        logger.warning(f"[FolderFetch] ALL strategies returned 0 for folder {folder_id[:12]}")
        return [], []

    def _parse_folder_children(self, children, current_path):
        """Parse a list of RTC folder child entries into (files, subfolders)."""
        files, subfolders = [], []
        for child in children:
            if not isinstance(child, dict):
                continue
            child_name = child.get('name', '')
            child_type = child.get('type', '') or child.get('itemType', '')
            child_id   = child.get('itemId', child.get('uuid', ''))
            if not child_name:
                continue

            child_path = f"{current_path}/{child_name}" if current_path else child_name

            if 'folder' in child_type.lower() or child_type == 'com.ibm.team.filesystem.Folder':
                subfolders.append((child_name, child_id, child_path))
            else:
                file_info = {
                    'name'      : child_name,
                    'path'      : child_path,
                    'uuid'      : child_id,
                    'content-id': child.get('contentId', child.get('content-id', '')),
                    'state-id'  : child.get('stateId',   child.get('state-id',   '')),
                }
                files.append(file_info)
        return files, subfolders

    def _fetch_folder_bfs(self, root_folder_id, baseline_uuid,
                          baseline_uri='', root_folder_state_id='',
                          jazz_session=None, max_depth=10):
        """
        Fetch a complete RTC folder tree using BFS + ThreadPoolExecutor.

        Each BFS level is submitted as a batch of parallel tasks.  Workers
        never wait for tasks that belong to later BFS levels, so there is no
        risk of thread-pool deadlock.

        Returns: dict {'folders': {name: {...}}, 'files': [{...}]}
        """
        result = {'folders': {}, 'files': []}

        # Queue items: (folder_id, target_struct_dict, current_path, depth)
        work_queue = [(root_folder_id, result, '', 0)]

        # Use a fraction of MAX_WORKERS ΓÇö this pool is nested inside the
        # per-component pool, so keep it modest to avoid overloading RTC.
        folder_workers = max(1, min(4, getattr(settings, 'MAX_WORKERS', 20) // 4))

        bfs_level = 0
        with ThreadPoolExecutor(max_workers=folder_workers) as ex:
            while work_queue:
                # Snapshot the current level and reset the queue for the next level
                batch = work_queue[:]
                work_queue = []
                logger.info(
                    f"[BFS] level={bfs_level} submitting {len(batch)} folder request(s) "
                    f"(workers={folder_workers})"
                )

                future_map = {
                    ex.submit(self._get_folder_children, fid, baseline_uuid, path,
                              baseline_uri, jazz_session): (struct, depth)
                    for fid, struct, path, depth in batch
                    if depth <= max_depth
                }

                level_files = 0
                level_folders = 0
                for future in as_completed(future_map):
                    struct, depth = future_map[future]
                    try:
                        files, subfolders = future.result()
                        struct['files'].extend(files)
                        level_files += len(files)
                        level_folders += len(subfolders)
                        for child_name, child_id, child_path in subfolders:
                            sub = {'folders': {}, 'files': []}
                            struct['folders'][child_name] = sub
                            work_queue.append((child_id, sub, child_path, depth + 1))
                    except Exception as e:
                        logger.warning(f"[BFS] folder fetch error at level {bfs_level}: {e}")

                logger.info(
                    f"[BFS] level={bfs_level} done: {level_files} files, "
                    f"{level_folders} sub-folders ΓåÆ {len(work_queue)} folders queued next"
                )
                bfs_level += 1

        return result

    def _fetch_folder_recursively(self, folder_id, baseline_uuid, depth=0, max_depth=10, current_path=''):
        """Recursively fetch folder contents via RTC REST API with baseline context."""
        if depth > max_depth:
            return {'folders': {}, 'files': []}
        try:
            # Ensure folder_id has '_' prefix for REST API
            if not folder_id.startswith('_'):
                folder_id = '_' + folder_id
            
            # Ensure baseline_uuid has '_' prefix for configuration context
            if baseline_uuid and not baseline_uuid.startswith('_'):
                baseline_uuid = '_' + baseline_uuid
            
            # CRITICAL: Add baseline configuration context to get baseline-specific file versions
            # Without this, the API returns current/latest file states instead of baseline-scoped versions
            folder_url = f'{self.server_url}/service/com.ibm.team.filesystem.service.rest.IVersionableRestService/folder/{folder_id}/children'
            
            # RTC configuration context can be passed via header or URL parameter
            # Try both approaches for maximum compatibility
            headers = [
                'Accept: application/json',
                'OSLC-Core-Version: 2.0'
            ]
            
            if baseline_uuid:
                # Add as URL parameter
                folder_url += f'?configuration={baseline_uuid}'
                # Also add as OSLC Configuration-Context header for RTC 6.x+
                headers.append(f'Configuration-Context: {baseline_uuid}')
            
            curl_cmd = [
                'curl.exe', '-k', '-L', '--noproxy', '*',
                '-u', f'{self.username}:{self.password}',
                '-X', 'GET', folder_url
            ]
            
            # Add headers to curl command
            for header in headers:
                curl_cmd.extend(['-H', header])
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
                    file_info = {
                        'name': child_name,
                        'path': file_path,
                        'uuid': child_id,
                        'content-id': child.get('contentId', child.get('content-id', '')),
                        'state-id'  : child.get('stateId', child.get('state-id', ''))
                    }
                    structure['files'].append(file_info)
                    # Debug logging to see what identifiers we're getting
                    logger.debug(f"  File: {file_path} | state-id: {file_info.get('state-id', 'N/A')[:12]}... | content-id: {file_info.get('content-id', 'N/A')[:12]}...")
                else:
                    # Unknown type ΓÇö treat conservatively as file
                    file_path = f"{current_path}/{child_name}" if current_path else child_name
                    file_info = {
                        'name': child_name,
                        'path': file_path,
                        'uuid': child_id,
                        'content-id': child.get('contentId', child.get('content-id', '')),
                        'state-id'  : child.get('stateId', child.get('state-id', ''))
                    }
                    structure['files'].append(file_info)
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
                    # File exists in both ΓÇö compare content identifiers
                    content1 = f1.get('content-id', '')
                    content2 = f2.get('content-id', '')
                    state1   = f1.get('state-id', '')
                    state2   = f2.get('state-id', '')
                    uuid1    = f1.get('uuid', '')
                    uuid2    = f2.get('uuid', '')
                    
                    # Determine modification using priority: state-id > content-id > uuid
                    is_modified = False
                    has_identifiers = False
                    comparison_method = 'none'
                    
                    if state1 and state2:
                        has_identifiers = True
                        comparison_method = 'state-id'
                        if state1 != state2:
                            is_modified = True
                            logger.debug(f"  File '{path}': MODIFIED (state-id: {state1[:12]}... != {state2[:12]}...)")
                    elif content1 and content2:
                        has_identifiers = True
                        comparison_method = 'content-id'
                        if content1 != content2:
                            is_modified = True
                            logger.debug(f"  File '{path}': MODIFIED (content-id: {content1[:12]}... != {content2[:12]}...)")
                    elif uuid1 and uuid2:
                        has_identifiers = True
                        comparison_method = 'uuid'
                        if uuid1 != uuid2:
                            is_modified = True
                            logger.debug(f"  File '{path}': MODIFIED (uuid: {uuid1[:12]}... != {uuid2[:12]}...)")
                    
                    if not has_identifiers:
                        # Cannot verify equality ΓÇö assume modified to avoid false negatives
                        is_modified = True
                        logger.debug(f"  File '{path}': MODIFIED (no identifiers available - assuming changed)")
                    
                    if is_modified:
                        details[path] = 'modified'
                        modified += 1
                    else:
                        details[path] = 'unchanged'
                        unchanged += 1
                        logger.debug(f"  File '{path}': unchanged ({comparison_method} match)")
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
