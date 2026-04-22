"""RTC Changeset and WorkItem operations"""

import os
import subprocess
import json
import re
import logging
from src.config import settings

logger = logging.getLogger(__name__)


def fetch_file_changesets_from_scm(file_path, repository_path, username=None, password=None, workspace_name=None, stream_name=None):
    """
    Fetch changesets for a file using SCM command line.
    Returns list of changeset dictionaries with changeset UUID, comment, author, date.
    
    Uses: scm history <file_path> -r <repository_url> -u <username> -P <password> -m 10
    """
    try:
        # Get LSCM path
        lscm_path = settings.LSCM_PATH
        if not lscm_path or not os.path.exists(lscm_path):
            logger.warning(f"LSCM not found at {lscm_path}")
            return []
        
        # Build command to get file history
        # scm history shows changesets that modified the file
        cmd = [
            lscm_path,
            'history',
            file_path,
            '-r', settings.RTC_SERVER_URL,
            '-u', username if username else '',
            '-P', password if password else '',
            '-m', '10',  # Max 10 changesets
            '--json'  # Try JSON output if supported
        ]
        
        # Filter out empty parameters
        cmd = [c for c in cmd if c]
        
        logger.debug(f"Executing SCM history for {file_path}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=repository_path if repository_path and os.path.exists(repository_path) else None
        )
        
        if result.returncode != 0 or not result.stdout:
            logger.warning(f"SCM history failed for {file_path}: {result.stderr[:200]}")
            return []
        
        # Try to parse JSON output
        changesets = []
        try:
            data = json.loads(result.stdout)
            # Extract changeset info from JSON structure
            for cs in data.get('changesets', []):
                changesets.append({
                    'uuid': cs.get('uuid', ''),
                    'url': f"{settings.RTC_SERVER_URL}/resource/itemName/com.ibm.team.scm.ChangeSet/{cs.get('uuid', '')}",
                    'comment': cs.get('comment', ''),
                    'author': cs.get('author', {}).get('name', ''),
                    'date': cs.get('modified-date', '')
                })
        except (json.JSONDecodeError, KeyError):
            # Fallback to text parsing if JSON fails
            logger.debug("JSON parsing failed, trying text parsing")
            changesets = _parse_scm_history_text(result.stdout, settings.RTC_SERVER_URL)
        
        logger.info(f"Found {len(changesets)} changesets for {file_path}")
        return changesets
        
    except subprocess.TimeoutExpired:
        logger.error(f"Timeout fetching changesets for {file_path}")
        return []
    except Exception as e:
        logger.error(f"Error fetching changesets for {file_path}: {e}")
        return []


def _parse_scm_history_text(text_output, server_url):
    """
    Parse text output from scm history command.
    Expected format:
      Change sets:
        (1234) ---$ "Comment here"
        Component: MyComponent
        Modified: Jan 01, 2024 | Author: user@example.com
    """
    changesets = []
    lines = text_output.split('\n')
    
    current_changeset = None
    for line in lines:
        line = line.strip()
        
        # Match changeset line: (1234) ---$ "Comment"
        cs_match = re.match(r'\((\d+)\)\s+---\$?\s*"?([^"]*)"?', line)
        if cs_match:
            if current_changeset:
                changesets.append(current_changeset)
            
            cs_number = cs_match.group(1)
            comment = cs_match.group(2).strip()
            current_changeset = {
                'uuid': cs_number,
                'url': f"{server_url}/resource/itemName/com.ibm.team.scm.ChangeSet/{cs_number}",
                'comment': comment,
                'author': '',
                'date': ''
            }
        
        # Extract author
        elif current_changeset and 'Author:' in line:
            author_match = re.search(r'Author:\s*([^\s]+)', line)
            if author_match:
                current_changeset['author'] = author_match.group(1)
        
        # Extract date
        elif current_changeset and 'Modified:' in line:
            date_match = re.search(r'Modified:\s*([^|]+)', line)
            if date_match:
                current_changeset['date'] = date_match.group(1).strip()
    
    # Add last changeset
    if current_changeset:
        changesets.append(current_changeset)
    
    return changesets


def fetch_file_changesets_from_rest_api(rel_file_path, username=None, password=None):
    """
    Fetch changesets for a file using RTC REST API.
    Returns list of changeset dictionaries.
    
    Note: REST API approach for file history is complex and requires proper workspace context.
    Currently using SCM CLI as primary method.
    """
    logger.debug(f"REST API changeset fetch not fully implemented for {rel_file_path}")
    return []


def fetch_workitems_using_java_client(changeset_uuid, username=None, password=None):
    """
    Fetch workitem IDs using RTC Java Client Library.
    Returns a list of workitem IDs.
    
    Note: Requires RTC Java Client setup. Using REST API as primary method.
    """
    logger.debug(f"Java client workitem fetch not implemented for changeset {changeset_uuid}")
    return []


def fetch_workitems_from_changeset(changeset_url, changeset_uuid=None, username=None, password=None):
    """
    Fetch workitem IDs associated with a changeset from RTC/ALM.
    Uses REST API to fetch changesetworkitem associations.
    Returns a list of workitem IDs.
    """
    try:
        if not changeset_uuid and changeset_url:
            # Extract UUID from URL if not provided
            uuid_match = re.search(r'ChangeSet/([^/]+)$', changeset_url)
            if uuid_match:
                changeset_uuid = uuid_match.group(1)
        
        if not changeset_uuid:
            logger.warning("No changeset UUID provided")
            return []
        
        # Try SCM CLI approach first - list workitems for changeset
        lscm_path = settings.LSCM_PATH
        if lscm_path and os.path.exists(lscm_path):
            cmd = [
                lscm_path,
                'show', 'changeset',
                changeset_uuid,
                '-r', settings.RTC_SERVER_URL,
                '-u', username if username else '',
                '-P', password if password else '',
                '-j'  # JSON output
            ]
            
            cmd = [c for c in cmd if c]
            
            logger.debug(f"Fetching workitems for changeset {changeset_uuid}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=20
            )
            
            if result.returncode == 0 and result.stdout:
                # Parse JSON or text output
                try:
                    data = json.loads(result.stdout)
                    workitems = data.get('workitems', [])
                    workitem_ids = [str(wi.get('id', '')) for wi in workitems if wi.get('id')]
                    logger.info(f"Found {len(workitem_ids)} workitems for changeset {changeset_uuid}")
                    return workitem_ids
                except json.JSONDecodeError:
                    # Try text parsing for workitem references
                    workitem_ids = _parse_workitems_from_text(result.stdout)
                    logger.info(f"Parsed {len(workitem_ids)} workitems from text output")
                    return workitem_ids
        
        # Fallback: Return empty list if no workitems found
        logger.debug(f"No workitems found for changeset {changeset_uuid}")
        return []
        
    except subprocess.TimeoutExpired:
        logger.error(f"Timeout fetching workitems for changeset {changeset_uuid}")
        return []
    except Exception as e:
        logger.error(f"Error fetching workitems for changeset: {e}")
        return []


def _parse_workitems_from_text(text_output):
    """
    Parse workitem IDs from SCM text output.
    Look for patterns like:
      - Work Items: 12345, 67890
      - Related Work Item: 12345
      - (12345) Task Title
    """
    workitem_ids = []
    
    # Pattern 1: Work Items: <id>, <id>
    matches = re.findall(r'Work\s+Items?:\s*([\d,\s]+)', text_output, re.IGNORECASE)
    for match in matches:
        ids = re.findall(r'\d+', match)
        workitem_ids.extend(ids)
    
    # Pattern 2: (#12345) or (12345) format
    matches = re.findall(r'\(#?(\d+)\)', text_output)
    workitem_ids.extend(matches)
    
    # Remove duplicates and return
    return list(set(workitem_ids))



def get_workitems_for_file(file_path, repository_path, username=None, password=None, workspace_name=None, stream_name=None):
    """
    Get changeset and workitem information for a file from RTC SCM history.
    Returns a dictionary with changeset URL and associated workitem IDs.
    """
    if not settings.RTC_ENABLED:
        logger.debug("RTC integration disabled in settings")
        return {"changeset_url": "", "workitem_ids": []}
    
    try:
        # Fetch changesets from SCM for this file with workspace context
        changesets = fetch_file_changesets_from_scm(file_path, repository_path, username, password, 
                                                    workspace_name=workspace_name, stream_name=stream_name)
        
        if not changesets:
            logger.debug(f"No changesets found for {file_path}")
            return {"changeset_url": "", "workitem_ids": []}
        
        # Use the most recent changeset
        latest_changeset = changesets[0]
        changeset_url = latest_changeset.get("url", "")
        changeset_uuid = latest_changeset.get("uuid", "")
        changeset_comment = latest_changeset.get("comment", "")
        
        # Fetch workitems associated with this changeset
        workitem_ids = fetch_workitems_from_changeset(
            changeset_url,
            changeset_uuid=changeset_uuid,
            username=username,
            password=password
        )
        
        logger.info(f"File {file_path}: Changeset {changeset_uuid} with {len(workitem_ids)} workitems")
        
        return {
            "changeset_url": changeset_url,
            "changeset_comment": changeset_comment,
            "changeset_author": latest_changeset.get("author", ""),
            "changeset_date": latest_changeset.get("date", ""),
            "workitem_ids": workitem_ids
        }
    except Exception as e:
        logger.error(f"Error getting workitems for {file_path}: {e}", exc_info=True)
        return {"changeset_url": "", "workitem_ids": []}
