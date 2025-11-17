"""
Authentication and Authorization System
Self-hosted JWT-based authentication with role-based access control
"""

import os
import jwt
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Set
from enum import Enum
import sqlite3
from pathlib import Path


class Permission(Enum):
    """Permission types"""
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"
    EXECUTE = "execute"


class Role(Enum):
    """User roles"""
    USER = "user"
    ADMIN = "admin"
    SERVICE = "service"
    GUEST = "guest"


class AuthManager:
    """Manages authentication and authorization"""
    
    def __init__(self, db_path: Optional[str] = None, secret_key: Optional[str] = None):
        """
        Initialize AuthManager
        
        Args:
            db_path: Path to SQLite database for storing users and sessions
            secret_key: Secret key for JWT signing (generated if not provided)
        """
        if db_path is None:
            db_path = os.path.expanduser("~/.powernode/auth.db")
        
        self.db_path = db_path
        self._ensure_db_exists()
        
        # Generate secret key if not provided
        if secret_key is None:
            secret_file = Path(self.db_path).parent / ".auth_secret"
            if secret_file.exists():
                with open(secret_file, 'r') as f:
                    self.secret_key = f.read().strip()
            else:
                self.secret_key = secrets.token_urlsafe(32)
                secret_file.parent.mkdir(parents=True, exist_ok=True)
                with open(secret_file, 'w') as f:
                    f.write(self.secret_key)
        else:
            self.secret_key = secret_key
        
        self.token_manager = TokenManager(self.secret_key)
        self._init_default_admin()
    
    def _ensure_db_exists(self):
        """Create database and schema if it doesn't exist"""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                permissions TEXT,  -- JSON array of permissions
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                active BOOLEAN DEFAULT 1
            )
        """)
        
        # Sessions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                token_hash TEXT NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ip_address TEXT,
                user_agent TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        
        # API keys table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                key_hash TEXT NOT NULL,
                name TEXT,
                permissions TEXT,  -- JSON array
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used_at TIMESTAMP,
                active BOOLEAN DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        
        conn.commit()
        conn.close()
    
    def _init_default_admin(self):
        """Initialize default admin user if none exists"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
        admin_count = cursor.fetchone()[0]
        
        if admin_count == 0:
            import uuid
            admin_id = str(uuid.uuid4())
            admin_password = "admin123"  # Should be changed on first login
            password_hash = self._hash_password(admin_password)
            
            cursor.execute("""
                INSERT INTO users (id, username, email, password_hash, role, permissions)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                admin_id,
                "admin",
                "admin@powernode.local",
                password_hash,
                "admin",
                '["read", "write", "admin", "execute"]'
            ))
            conn.commit()
        
        conn.close()
    
    def _hash_password(self, password: str) -> str:
        """Hash password using SHA-256 with salt"""
        salt = secrets.token_hex(16)
        hash_obj = hashlib.sha256()
        hash_obj.update((password + salt).encode())
        return f"{salt}:{hash_obj.hexdigest()}"
    
    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verify password against hash"""
        try:
            salt, stored_hash = password_hash.split(":", 1)
            hash_obj = hashlib.sha256()
            hash_obj.update((password + salt).encode())
            return hash_obj.hexdigest() == stored_hash
        except:
            return False
    
    def create_user(
        self,
        username: str,
        password: str,
        email: Optional[str] = None,
        role: Role = Role.USER,
        permissions: Optional[List[Permission]] = None
    ) -> Dict:
        """Create a new user"""
        import uuid
        import json
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Check if username exists
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            conn.close()
            raise ValueError(f"Username {username} already exists")
        
        user_id = str(uuid.uuid4())
        password_hash = self._hash_password(password)
        
        perm_list = permissions or []
        perm_json = json.dumps([p.value for p in perm_list])
        
        cursor.execute("""
            INSERT INTO users (id, username, email, password_hash, role, permissions)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, username, email, password_hash, role.value, perm_json))
        
        conn.commit()
        conn.close()
        
        return {
            "id": user_id,
            "username": username,
            "email": email,
            "role": role.value,
            "permissions": [p.value for p in perm_list]
        }
    
    def authenticate(self, username: str, password: str, ip_address: Optional[str] = None) -> Optional[Dict]:
        """Authenticate user and return token"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, username, email, password_hash, role, permissions, active
            FROM users WHERE username = ?
        """, (username,))
        
        user_row = cursor.fetchone()
        conn.close()
        
        if not user_row or not user_row['active']:
            return None
        
        if not self._verify_password(password, user_row['password_hash']):
            return None
        
        import json
        permissions = json.loads(user_row['permissions'] or '[]')
        
        # Generate token
        token_data = {
            "user_id": user_row['id'],
            "username": user_row['username'],
            "role": user_row['role'],
            "permissions": permissions,
            "exp": datetime.utcnow() + timedelta(days=7)
        }
        
        token = self.token_manager.generate_token(token_data)
        
        # Store session
        self._create_session(user_row['id'], token, ip_address)
        
        return {
            "token": token,
            "user": {
                "id": user_row['id'],
                "username": user_row['username'],
                "email": user_row['email'],
                "role": user_row['role'],
                "permissions": permissions
            }
        }
    
    def _create_session(self, user_id: str, token: str, ip_address: Optional[str] = None):
        """Create a session record"""
        import uuid
        import hashlib
        
        session_id = str(uuid.uuid4())
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        expires_at = datetime.utcnow() + timedelta(days=7)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO sessions (id, user_id, token_hash, expires_at, ip_address)
            VALUES (?, ?, ?, ?, ?)
        """, (session_id, user_id, token_hash, expires_at.isoformat(), ip_address))
        
        conn.commit()
        conn.close()
    
    def verify_token(self, token: str) -> Optional[Dict]:
        """Verify JWT token and return user info"""
        try:
            payload = self.token_manager.verify_token(token)
            if not payload:
                return None
            
            # Check if session exists and is valid
            import hashlib
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT s.*, u.active
                FROM sessions s
                JOIN users u ON s.user_id = u.id
                WHERE s.token_hash = ? AND s.expires_at > ? AND u.active = 1
            """, (token_hash, datetime.utcnow().isoformat()))
            
            session = cursor.fetchone()
            conn.close()
            
            if not session:
                return None
            
            return payload
        except Exception as e:
            return None
    
    def check_permission(self, user_info: Dict, permission: Permission) -> bool:
        """Check if user has a specific permission"""
        if user_info.get('role') == 'admin':
            return True
        
        user_perms = user_info.get('permissions', [])
        return permission.value in user_perms
    
    def create_api_key(
        self,
        user_id: str,
        name: str,
        permissions: Optional[List[Permission]] = None,
        expires_days: Optional[int] = None
    ) -> str:
        """Create an API key for a user"""
        import uuid
        import json
        
        api_key = f"pn_{secrets.token_urlsafe(32)}"
        api_key_id = str(uuid.uuid4())
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        perm_list = permissions or []
        perm_json = json.dumps([p.value for p in perm_list])
        
        expires_at = None
        if expires_days:
            expires_at = (datetime.utcnow() + timedelta(days=expires_days)).isoformat()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO api_keys (id, user_id, key_hash, name, permissions, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (api_key_id, user_id, key_hash, name, perm_json, expires_at))
        
        conn.commit()
        conn.close()
        
        return api_key
    
    def verify_api_key(self, api_key: str) -> Optional[Dict]:
        """Verify API key and return user info"""
        import hashlib
        import json
        
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT ak.*, u.username, u.email, u.role
            FROM api_keys ak
            JOIN users u ON ak.user_id = u.id
            WHERE ak.key_hash = ? AND ak.active = 1 AND u.active = 1
            AND (ak.expires_at IS NULL OR ak.expires_at > ?)
        """, (key_hash, datetime.utcnow().isoformat()))
        
        key_row = cursor.fetchone()
        
        if key_row:
            # Update last used
            cursor.execute("""
                UPDATE api_keys SET last_used_at = ? WHERE id = ?
            """, (datetime.utcnow().isoformat(), key_row['id']))
            conn.commit()
            
            permissions = json.loads(key_row['permissions'] or '[]')
            
            result = {
                "user_id": key_row['user_id'],
                "username": key_row['username'],
                "email": key_row['email'],
                "role": key_row['role'],
                "permissions": permissions
            }
        else:
            result = None
        
        conn.close()
        return result


class TokenManager:
    """Manages JWT token generation and verification"""
    
    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        """
        Initialize TokenManager
        
        Args:
            secret_key: Secret key for signing tokens
            algorithm: JWT algorithm to use
        """
        self.secret_key = secret_key
        self.algorithm = algorithm
    
    def generate_token(self, payload: Dict) -> str:
        """Generate a JWT token"""
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def verify_token(self, token: str) -> Optional[Dict]:
        """Verify and decode a JWT token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None
    
    def refresh_token(self, token: str, extend_days: int = 7) -> Optional[str]:
        """Refresh a token, extending its expiration"""
        payload = self.verify_token(token)
        if not payload:
            return None
        
        # Remove exp from payload and add new expiration
        payload.pop('exp', None)
        payload['exp'] = datetime.utcnow() + timedelta(days=extend_days)
        
        return self.generate_token(payload)









