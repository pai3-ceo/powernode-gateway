"""
State Management System
Centralized state management with persistence and caching
"""

import os
import json
import sqlite3
import threading
from typing import Any, Dict, Optional, List
from datetime import datetime, timedelta
from pathlib import Path
import pickle
import hashlib


class StateManager:
    """Manages application state with persistence and caching"""
    
    def __init__(self, db_path: Optional[str] = None, cache_size: int = 1000):
        """
        Initialize StateManager
        
        Args:
            db_path: Path to SQLite database for persistence
            cache_size: Maximum number of items in memory cache
        """
        if db_path is None:
            db_path = os.path.expanduser("~/.powernode/state.db")
        
        self.db_path = db_path
        self.cache_size = cache_size
        self._cache: Dict[str, Any] = {}
        self._cache_timestamps: Dict[str, datetime] = {}
        self._lock = threading.RLock()
        
        self._ensure_db_exists()
    
    def _ensure_db_exists(self):
        """Create database and schema if it doesn't exist"""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # State storage table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS state (
                key TEXT PRIMARY KEY,
                value BLOB NOT NULL,
                namespace TEXT DEFAULT 'default',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                metadata TEXT  -- JSON metadata
            )
        """)
        
        # State history table for audit trail
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS state_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL,
                namespace TEXT,
                action TEXT NOT NULL,  -- set, delete, expire
                old_value BLOB,
                new_value BLOB,
                changed_by TEXT,
                changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_namespace ON state(namespace)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_expires ON state(expires_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_key ON state_history(key)")
        
        conn.commit()
        conn.close()
    
    def _serialize_value(self, value: Any) -> bytes:
        """Serialize value to bytes"""
        try:
            return pickle.dumps(value)
        except Exception:
            # Fallback to JSON for simple types
            return json.dumps(value).encode('utf-8')
    
    def _deserialize_value(self, data: bytes) -> Any:
        """Deserialize bytes to value"""
        try:
            return pickle.loads(data)
        except Exception:
            # Fallback to JSON
            return json.loads(data.decode('utf-8'))
    
    def _make_key(self, key: str, namespace: str = "default") -> str:
        """Create namespaced key"""
        return f"{namespace}:{key}"
    
    def set(
        self,
        key: str,
        value: Any,
        namespace: str = "default",
        ttl: Optional[int] = None,
        metadata: Optional[Dict] = None,
        changed_by: Optional[str] = None
    ):
        """Set a state value"""
        with self._lock:
            full_key = self._make_key(key, namespace)
            serialized_value = self._serialize_value(value)
            
            expires_at = None
            if ttl:
                expires_at = (datetime.utcnow() + timedelta(seconds=ttl)).isoformat()
            
            metadata_json = json.dumps(metadata) if metadata else None
            
            # Update cache
            self._cache[full_key] = value
            self._cache_timestamps[full_key] = datetime.utcnow()
            
            # Manage cache size
            if len(self._cache) > self.cache_size:
                # Remove oldest entry
                oldest_key = min(self._cache_timestamps.items(), key=lambda x: x[1])[0]
                del self._cache[oldest_key]
                del self._cache_timestamps[oldest_key]
            
            # Persist to database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get old value for history
            cursor.execute("SELECT value FROM state WHERE key = ?", (full_key,))
            old_row = cursor.fetchone()
            old_value = old_row[0] if old_row else None
            
            cursor.execute("""
                INSERT OR REPLACE INTO state (key, value, namespace, updated_at, expires_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                full_key,
                serialized_value,
                namespace,
                datetime.utcnow().isoformat(),
                expires_at,
                metadata_json
            ))
            
            # Record history
            cursor.execute("""
                INSERT INTO state_history (key, namespace, action, old_value, new_value, changed_by)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                full_key,
                namespace,
                "set",
                old_value,
                serialized_value,
                changed_by
            ))
            
            conn.commit()
            conn.close()
    
    def get(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        """Get a state value"""
        with self._lock:
            full_key = self._make_key(key, namespace)
            
            # Check cache first
            if full_key in self._cache:
                return self._cache[full_key]
            
            # Check database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT value, expires_at FROM state
                WHERE key = ? AND (expires_at IS NULL OR expires_at > ?)
            """, (full_key, datetime.utcnow().isoformat()))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                value = self._deserialize_value(row[0])
                # Update cache
                self._cache[full_key] = value
                self._cache_timestamps[full_key] = datetime.utcnow()
                return value
            
            return default
    
    def delete(self, key: str, namespace: str = "default", changed_by: Optional[str] = None):
        """Delete a state value"""
        with self._lock:
            full_key = self._make_key(key, namespace)
            
            # Remove from cache
            if full_key in self._cache:
                del self._cache[full_key]
                del self._cache_timestamps[full_key]
            
            # Remove from database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get old value for history
            cursor.execute("SELECT value FROM state WHERE key = ?", (full_key,))
            old_row = cursor.fetchone()
            old_value = old_row[0] if old_row else None
            
            cursor.execute("DELETE FROM state WHERE key = ?", (full_key,))
            
            # Record history
            if old_value:
                cursor.execute("""
                    INSERT INTO state_history (key, namespace, action, old_value, changed_by)
                    VALUES (?, ?, ?, ?, ?)
                """, (full_key, namespace, "delete", old_value, changed_by))
            
            conn.commit()
            conn.close()
    
    def exists(self, key: str, namespace: str = "default") -> bool:
        """Check if a key exists"""
        full_key = self._make_key(key, namespace)
        
        if full_key in self._cache:
            return True
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 1 FROM state
            WHERE key = ? AND (expires_at IS NULL OR expires_at > ?)
        """, (full_key, datetime.utcnow().isoformat()))
        
        exists = cursor.fetchone() is not None
        conn.close()
        
        return exists
    
    def list_keys(self, namespace: str = "default", pattern: Optional[str] = None) -> List[str]:
        """List all keys in a namespace, optionally filtered by pattern"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if pattern:
            cursor.execute("""
                SELECT key FROM state
                WHERE namespace = ? AND key LIKE ? AND (expires_at IS NULL OR expires_at > ?)
            """, (namespace, pattern, datetime.utcnow().isoformat()))
        else:
            cursor.execute("""
                SELECT key FROM state
                WHERE namespace = ? AND (expires_at IS NULL OR expires_at > ?)
            """, (namespace, datetime.utcnow().isoformat()))
        
        keys = [row[0].replace(f"{namespace}:", "") for row in cursor.fetchall()]
        conn.close()
        
        return keys
    
    def clear_namespace(self, namespace: str = "default", changed_by: Optional[str] = None):
        """Clear all keys in a namespace"""
        with self._lock:
            # Clear from cache
            keys_to_remove = [k for k in self._cache.keys() if k.startswith(f"{namespace}:")]
            for key in keys_to_remove:
                del self._cache[key]
                del self._cache_timestamps[key]
            
            # Clear from database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT key, value FROM state WHERE namespace = ?", (namespace,))
            old_values = cursor.fetchall()
            
            cursor.execute("DELETE FROM state WHERE namespace = ?", (namespace,))
            
            # Record history
            for key, value in old_values:
                cursor.execute("""
                    INSERT INTO state_history (key, namespace, action, old_value, changed_by)
                    VALUES (?, ?, ?, ?, ?)
                """, (key, namespace, "delete", value, changed_by))
            
            conn.commit()
            conn.close()
    
    def get_history(self, key: str, namespace: str = "default", limit: int = 100) -> List[Dict]:
        """Get history of changes for a key"""
        full_key = self._make_key(key, namespace)
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM state_history
            WHERE key = ?
            ORDER BY changed_at DESC
            LIMIT ?
        """, (full_key, limit))
        
        history = []
        for row in cursor.fetchall():
            history.append({
                "id": row['id'],
                "key": row['key'],
                "namespace": row['namespace'],
                "action": row['action'],
                "changed_by": row['changed_by'],
                "changed_at": row['changed_at']
            })
        
        conn.close()
        return history
    
    def cleanup_expired(self):
        """Remove expired entries"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT key FROM state WHERE expires_at IS NOT NULL AND expires_at <= ?
            """, (datetime.utcnow().isoformat(),))
            
            expired_keys = [row[0] for row in cursor.fetchall()]
            
            for key in expired_keys:
                # Remove from cache
                if key in self._cache:
                    del self._cache[key]
                    del self._cache_timestamps[key]
                
                # Record history
                cursor.execute("SELECT value FROM state WHERE key = ?", (key,))
                old_row = cursor.fetchone()
                if old_row:
                    cursor.execute("""
                        INSERT INTO state_history (key, namespace, action, old_value)
                        VALUES (?, ?, ?, ?)
                    """, (key, key.split(":")[0], "expire", old_row[0]))
            
            cursor.execute("DELETE FROM state WHERE expires_at IS NOT NULL AND expires_at <= ?",
                         (datetime.utcnow().isoformat(),))
            
            conn.commit()
            conn.close()









