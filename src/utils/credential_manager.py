"""
Secure credential manager for RTC login caching
Uses system keyring if available, otherwise encrypted file-based storage
"""

import os
import json
import base64
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Try to import keyring for secure storage
try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False

# Try to import cryptography for encryption
try:
    from cryptography.fernet import Fernet
    ENCRYPTION_AVAILABLE = True
except ImportError:
    ENCRYPTION_AVAILABLE = False


class CredentialManager:
    """Manage secure storage and retrieval of RTC credentials"""
    
    SERVICE_NAME = "WP8152-Migration-Tool"
    CRED_FILE = os.path.expanduser("~/.wp8152_rtc_creds")
    
    @staticmethod
    def _get_encryption_key():
        """Get or generate encryption key"""
        key_file = os.path.expanduser("~/.wp8152_rtc_key")
        
        # If encryption not available, return None (skip encryption)
        if not ENCRYPTION_AVAILABLE:
            return None
        
        if os.path.exists(key_file):
            try:
                with open(key_file, 'rb') as f:
                    return f.read()
            except Exception as e:
                logger.warning(f"Failed to read encryption key: {e}")
                return None
        else:
            try:
                key = Fernet.generate_key()
                # Create key file with restricted permissions
                with open(key_file, 'wb') as f:
                    f.write(key)
                os.chmod(key_file, 0o600)  # Read/write for owner only
                logger.info("Generated new encryption key")
                return key
            except Exception as e:
                logger.warning(f"Failed to generate encryption key: {e}")
                return None
    
    @staticmethod
    def _encrypt(data: str) -> Optional[str]:
        """Encrypt data using Fernet."""
        if not ENCRYPTION_AVAILABLE:
            logger.warning("cryptography is not installed; encrypted file storage is unavailable")
            return None
        
        key = CredentialManager._get_encryption_key()
        if not key:
            logger.warning("Encryption key is unavailable; credentials will not be cached")
            return None
        
        try:
            cipher = Fernet(key)
            encrypted = cipher.encrypt(data.encode())
            return encrypted.decode()
        except Exception as e:
            logger.warning(f"Encryption failed: {e}")
            return None
    
    @staticmethod
    def _decrypt(encrypted_data: str) -> Optional[str]:
        """Decrypt data using Fernet (if available)"""
        if not ENCRYPTION_AVAILABLE:
            # Try base64 decode
            try:
                return base64.b64decode(encrypted_data).decode()
            except Exception:
                return None
        
        key = CredentialManager._get_encryption_key()
        if not key:
            # Try base64 decode as fallback
            try:
                return base64.b64decode(encrypted_data).decode()
            except Exception:
                return None
        
        try:
            cipher = Fernet(key)
            decrypted = cipher.decrypt(encrypted_data.encode())
            return decrypted.decode()
        except Exception as e:
            logger.warning(f"Decryption failed: {e}")
            # Try base64 decode as fallback
            try:
                return base64.b64decode(encrypted_data).decode()
            except Exception:
                return None
    
    @staticmethod
    def save_credentials(username: str, password: str, server_url: str) -> bool:
        """
        Save credentials securely.
        
        Tries multiple methods in order:
        1. System keyring (most secure)
        2. Encrypted file (fallback)
        
        Returns:
            True if saved successfully, False otherwise
        """
        try:
            logger.info(f"Attempting to save credentials for {username}@{server_url}")
            
            # Method 1: Use system keyring if available
            if KEYRING_AVAILABLE:
                try:
                    keyring.set_password(CredentialManager.SERVICE_NAME, 
                                        f"{server_url}:username", 
                                        username)
                    keyring.set_password(CredentialManager.SERVICE_NAME, 
                                        f"{server_url}:password", 
                                        password)
                    logger.info("✓ Credentials saved to system keyring successfully")
                    return True
                except Exception as e:
                    logger.warning(f"⚠ Keyring save failed, falling back to encrypted file: {e}")
            else:
                logger.warning("⚠ keyring library not available, using encrypted file storage")
            
            # Method 2: Save to encrypted file
            if not ENCRYPTION_AVAILABLE:
                logger.error("✗ cryptography library not available - cannot save credentials")
                logger.error("Install with: pip install cryptography")
                return False
            
            encrypted_username = CredentialManager._encrypt(username)
            encrypted_password = CredentialManager._encrypt(password)
            
            if not encrypted_username or not encrypted_password:
                logger.error("✗ Encryption failed - cannot save credentials")
                return False
            
            credentials = {
                'username': encrypted_username,
                'password': encrypted_password,
                'server_url': server_url,
                'version': '1.0'
            }
            
            # Write to file with restricted permissions
            try:
                with open(CredentialManager.CRED_FILE, 'w') as f:
                    json.dump(credentials, f)
                os.chmod(CredentialManager.CRED_FILE, 0o600)  # Read/write for owner only
                logger.info(f"✓ Credentials saved to encrypted file: {CredentialManager.CRED_FILE}")
                return True
            except PermissionError as e:
                logger.error(f"✗ Permission denied writing to {CredentialManager.CRED_FILE}: {e}")
                return False
            except Exception as e:
                logger.error(f"✗ Failed to write credential file: {e}")
                return False
        
        except Exception as e:
            logger.error(f"✗ Unexpected error saving credentials: {e}", exc_info=True)
            return False
    
    @staticmethod
    def load_credentials(server_url: str) -> Optional[Tuple[str, str]]:
        """
        Load credentials from secure storage.
        
        Tries multiple methods in order:
        1. System keyring (most secure)
        2. Encrypted file (decent security)
        3. Base64 file (fallback)
        
        Returns:
            Tuple of (username, password) if found, None otherwise
        """
        try:
            # Method 1: Try system keyring
            if KEYRING_AVAILABLE:
                try:
                    username = keyring.get_password(CredentialManager.SERVICE_NAME, 
                                                   f"{server_url}:username")
                    password = keyring.get_password(CredentialManager.SERVICE_NAME, 
                                                   f"{server_url}:password")
                    
                    if username and password:
                        logger.info("✓ Credentials loaded from system keyring")
                        return (username, password)
                except Exception as e:
                    logger.warning(f"Keyring load failed: {e}")
            
            # Method 2: Try file-based storage
            if os.path.exists(CredentialManager.CRED_FILE):
                try:
                    with open(CredentialManager.CRED_FILE, 'r') as f:
                        credentials = json.load(f)
                    
                    # Verify server URL matches
                    if credentials.get('server_url') != server_url:
                        logger.warning("Server URL mismatch in cached credentials")
                        return None
                    
                    # Decrypt credentials
                    username = CredentialManager._decrypt(credentials.get('username', ''))
                    password = CredentialManager._decrypt(credentials.get('password', ''))
                    
                    if username and password:
                        logger.info("✓ Credentials loaded from encrypted file")
                        return (username, password)
                except Exception as e:
                    logger.warning(f"File-based credential load failed: {e}")
            
            return None
        
        except Exception as e:
            logger.error(f"Error loading credentials: {e}")
            return None
    
    @staticmethod
    def clear_credentials(server_url: str) -> bool:
        """
        Clear stored credentials (logout).
        
        Removes credentials from both keyring and file storage.
        
        Returns:
            True if at least one method succeeded
        """
        cleared = False
        
        try:
            # Method 1: Clear from keyring
            if KEYRING_AVAILABLE:
                try:
                    keyring.delete_password(CredentialManager.SERVICE_NAME, 
                                          f"{server_url}:username")
                    keyring.delete_password(CredentialManager.SERVICE_NAME, 
                                          f"{server_url}:password")
                    logger.info("✓ Credentials cleared from system keyring")
                    cleared = True
                except Exception as e:
                    logger.warning(f"Keyring clear failed: {e}")
            
            # Method 2: Remove credential file
            if os.path.exists(CredentialManager.CRED_FILE):
                try:
                    os.remove(CredentialManager.CRED_FILE)
                    logger.info("✓ Credential file deleted")
                    cleared = True
                except Exception as e:
                    logger.warning(f"File deletion failed: {e}")
            
            return cleared
        
        except Exception as e:
            logger.error(f"Error clearing credentials: {e}")
            return False
    
    @staticmethod
    def has_cached_credentials(server_url: str) -> bool:
        """Check if credentials are cached for the given server"""
        try:
            if KEYRING_AVAILABLE:
                try:
                    username = keyring.get_password(CredentialManager.SERVICE_NAME, 
                                                   f"{server_url}:username")
                    if username:
                        return True
                except Exception:
                    pass
            
            if os.path.exists(CredentialManager.CRED_FILE):
                try:
                    with open(CredentialManager.CRED_FILE, 'r') as f:
                        credentials = json.load(f)
                    
                    if credentials.get('server_url') == server_url:
                        return True
                except Exception:
                    pass
            
            return False
        except Exception as e:
            logger.warning(f"Error checking cached credentials: {e}")
            return False
