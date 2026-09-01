import logging
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from app.infrastructure.db.database import DatabasePool

logger = logging.getLogger("AuthRepository")

class AuthRepository:
    """
    Enterprise Authentication, User Management, and Scoped API Token Repository.
    """

    @classmethod
    def init_auth_schema(cls):
        """Ensures users table has role & email, and creates api_tokens table."""
        with DatabasePool.get_cursor(commit=True) as cursor:
            # Upgrade users table
            cursor.execute("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) DEFAULT 'operator';
                ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(100);
                ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;
                ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;
            """)
            
            # Create api_tokens table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_tokens (
                    id SERIAL PRIMARY KEY,
                    token_hash VARCHAR(64) UNIQUE NOT NULL,
                    name VARCHAR(100) NOT NULL,
                    scope VARCHAR(50) DEFAULT 'read_write',
                    domain_category VARCHAR(50) DEFAULT 'all',
                    created_by VARCHAR(50) DEFAULT 'admin',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP WITH TIME ZONE,
                    last_used_at TIMESTAMP WITH TIME ZONE,
                    is_active BOOLEAN DEFAULT TRUE
                );
                CREATE INDEX IF NOT EXISTS idx_api_tokens_hash ON api_tokens(token_hash);
            """)

            # Seed default admin if table is empty
            cursor.execute("SELECT COUNT(*) as count FROM users WHERE username = 'admin';")
            row = cursor.fetchone()
            if row["count"] == 0:
                # Default password: admin / admin123
                pwd_hash = cls.hash_password("admin123")
                cursor.execute("""
                    INSERT INTO users (username, password_hash, role, email, is_active)
                    VALUES ('admin', %s, 'admin', 'admin@enterprise.internal', TRUE);
                """, (pwd_hash,))
                logger.info("✓ Initialized default admin user ('admin' / 'admin123').")

    @staticmethod
    def hash_password(password: str) -> str:
        """SHA-256 with salt hashing for operator passwords."""
        salt = "deepagent_salt_2026"
        return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()

    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        return AuthRepository.hash_password(password) == hashed

    @classmethod
    def authenticate_user(cls, username: str, password: str) -> Optional[Dict[str, Any]]:
        cls.init_auth_schema()
        with DatabasePool.get_cursor() as cursor:
            cursor.execute("""
                SELECT id, username, password_hash, role, email, is_active 
                FROM users WHERE username = %s AND is_active = TRUE;
            """, (username,))
            user = cursor.fetchone()
            if not user:
                return None
            if cls.verify_password(password, user["password_hash"]):
                return {
                    "id": user["id"],
                    "username": user["username"],
                    "role": user["role"],
                    "email": user["email"]
                }
            return None

    @classmethod
    def get_all_users(cls) -> List[Dict[str, Any]]:
        cls.init_auth_schema()
        with DatabasePool.get_cursor() as cursor:
            cursor.execute("""
                SELECT id, username, role, email, created_at, is_active 
                FROM users ORDER BY id ASC;
            """)
            return cursor.fetchall()

    @classmethod
    def create_user(cls, username: str, password: str, role: str = "operator", email: str = "") -> Dict[str, Any]:
        cls.init_auth_schema()
        pwd_hash = cls.hash_password(password)
        with DatabasePool.get_cursor(commit=True) as cursor:
            cursor.execute("""
                INSERT INTO users (username, password_hash, role, email, is_active)
                VALUES (%s, %s, %s, %s, TRUE)
                RETURNING id, username, role, email, is_active;
            """, (username, pwd_hash, role, email))
            return cursor.fetchone()

    @classmethod
    def change_password(cls, username: str, old_password: Optional[str], new_password: str, is_admin_override: bool = False) -> bool:
        cls.init_auth_schema()
        with DatabasePool.get_cursor(commit=True) as cursor:
            cursor.execute("SELECT id, password_hash FROM users WHERE username = %s AND is_active = TRUE;", (username,))
            user = cursor.fetchone()
            if not user:
                return False
            
            if not is_admin_override:
                if not old_password or not cls.verify_password(old_password, user["password_hash"]):
                    return False
            
            new_hash = cls.hash_password(new_password)
            cursor.execute("UPDATE users SET password_hash = %s WHERE id = %s;", (new_hash, user["id"]))
            return cursor.rowcount > 0

    @classmethod
    def delete_user(cls, user_id: int) -> bool:
        cls.init_auth_schema()
        with DatabasePool.get_cursor(commit=True) as cursor:
            cursor.execute("UPDATE users SET is_active = FALSE WHERE id = %s;", (user_id,))
            return cursor.rowcount > 0

    @classmethod
    def generate_api_token(cls, name: str, scope: str = "read_write", domain_category: str = "all", expiry_days: Optional[int] = None, created_by: str = "admin") -> Dict[str, Any]:
        cls.init_auth_schema()
        raw_token = f"da_sec_{secrets.token_urlsafe(32)}"
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        
        expires_at = None
        if expiry_days is not None and expiry_days > 0:
            expires_at = datetime.now() + timedelta(days=expiry_days)

        with DatabasePool.get_cursor(commit=True) as cursor:
            cursor.execute("""
                INSERT INTO api_tokens (token_hash, name, scope, domain_category, created_by, expires_at, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, TRUE)
                RETURNING id, name, scope, domain_category, created_by, created_at, expires_at, is_active;
            """, (token_hash, name, scope, domain_category, created_by, expires_at))
            record = cursor.fetchone()
            
        record["raw_token"] = raw_token
        return record

    @classmethod
    def validate_api_token(cls, raw_token: str) -> Optional[Dict[str, Any]]:
        cls.init_auth_schema()
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        with DatabasePool.get_cursor(commit=True) as cursor:
            cursor.execute("""
                SELECT id, name, scope, domain_category, created_by, expires_at, is_active 
                FROM api_tokens 
                WHERE token_hash = %s AND is_active = TRUE;
            """, (token_hash,))
            token = cursor.fetchone()
            if not token:
                return None
            
            # Check expiration
            if token["expires_at"] and token["expires_at"] < datetime.now():
                return None
            
            # Update last_used_at
            cursor.execute("""
                UPDATE api_tokens SET last_used_at = CURRENT_TIMESTAMP WHERE id = %s;
            """, (token["id"],))
            return token

    @classmethod
    def get_all_api_tokens(cls) -> List[Dict[str, Any]]:
        cls.init_auth_schema()
        with DatabasePool.get_cursor() as cursor:
            cursor.execute("""
                SELECT id, name, scope, domain_category, created_by, created_at, expires_at, last_used_at, is_active 
                FROM api_tokens ORDER BY created_at DESC;
            """)
            return cursor.fetchall()

    @classmethod
    def revoke_api_token(cls, token_id: int) -> bool:
        cls.init_auth_schema()
        with DatabasePool.get_cursor(commit=True) as cursor:
            cursor.execute("UPDATE api_tokens SET is_active = FALSE WHERE id = %s;", (token_id,))
            return cursor.rowcount > 0
