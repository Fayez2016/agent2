import logging
import secrets
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Depends, Header
from app.infrastructure.db.auth_repository import AuthRepository

logger = logging.getLogger("AuthAPI")
router = APIRouter(prefix="/v1/auth", tags=["Authentication & User Management"])

class LoginRequest(BaseModel):
    username: str
    password: str

class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "operator"
    email: str = ""

class GenerateTokenRequest(BaseModel):
    name: str
    scope: str = "read_write"
    domain_category: str = "all"
    expiry_option: str = "30d"  # "7d", "30d", "90d", "1y", "never"

# In-memory active session tokens for simple operator session tracking
_ACTIVE_SESSIONS: Dict[str, Dict[str, Any]] = {}

@router.post("/login")
def login(req: LoginRequest):
    """Authenticates user and returns session token and profile info."""
    user = AuthRepository.authenticate_user(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    session_token = f"sess_{secrets.token_hex(24)}"
    _ACTIVE_SESSIONS[session_token] = {
        "user_id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "email": user["email"]
    }
    
    return {
        "status": "success",
        "session_token": session_token,
        "user": user
    }

@router.get("/me")
def get_current_user(authorization: Optional[str] = Header(None)):
    """Validates session or bearer token and returns current user info."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    
    token = authorization.replace("Bearer ", "").strip()
    
    # Check operator sessions
    if token in _ACTIVE_SESSIONS:
        return {"type": "session", "user": _ACTIVE_SESSIONS[token]}
    
    # Check scoped API token
    api_token = AuthRepository.validate_api_token(token)
    if api_token:
        return {
            "type": "api_token",
            "token_info": api_token,
            "user": {"username": f"token:{api_token['name']}", "role": "service_account"}
        }
    
    # Fallback to default admin session if token is "hermes-api-secret"
    if token == "hermes-api-secret":
        return {
            "type": "master_secret",
            "user": {"username": "admin", "role": "admin", "email": "admin@enterprise.internal"}
        }

    raise HTTPException(status_code=401, detail="Invalid or expired session token")

@router.get("/users")
def list_users():
    """Lists all registered enterprise operators and admins."""
    users = AuthRepository.get_all_users()
    return {"users": users}

@router.post("/users")
def create_user(req: CreateUserRequest):
    """Creates a new user with RBAC role."""
    try:
        user = AuthRepository.create_user(
            username=req.username,
            password=req.password,
            role=req.role,
            email=req.email
        )
        return {"status": "success", "user": user}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to create user: {str(e)}")

@router.get("/tokens")
def list_api_tokens():
    """Lists all active and expired scoped API tokens."""
    tokens = AuthRepository.get_all_api_tokens()
    return {"tokens": tokens}

@router.post("/tokens")
def generate_api_token(req: GenerateTokenRequest):
    """Generates a scoped API token with configurable expiration period."""
    expiry_map = {
        "7d": 7,
        "30d": 30,
        "90d": 90,
        "1y": 365,
        "never": None
    }
    days = expiry_map.get(req.expiry_option.lower(), 30)
    
    try:
        record = AuthRepository.generate_api_token(
            name=req.name,
            scope=req.scope,
            domain_category=req.domain_category,
            expiry_days=days
        )
        return {
            "status": "success",
            "token_record": record
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to generate token: {str(e)}")

@router.delete("/tokens/{token_id}")
def revoke_api_token(token_id: int):
    """Revokes a scoped API token."""
    success = AuthRepository.revoke_api_token(token_id)
    if not success:
        raise HTTPException(status_code=404, detail="Token not found")
    return {"status": "success", "message": f"Token {token_id} revoked"}
