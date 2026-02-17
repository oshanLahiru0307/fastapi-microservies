# gateway/auth.py
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
import os
from dotenv import load_dotenv

load_dotenv()

# JWT Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-this-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Password hashing - use a lazy initialization to avoid bcrypt import issues
_pwd_context = None
_users_db_initialized = False

def get_pwd_context():
    """Get password context, initializing it lazily"""
    global _pwd_context
    if _pwd_context is None:
        _pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    return _pwd_context

# HTTP Bearer token scheme
security = HTTPBearer()

# Users database - will be initialized lazily
USERS_DB = {}

def _init_users_db():
    """Initialize users database with hashed passwords (lazy initialization)"""
    global _users_db_initialized, USERS_DB
    if _users_db_initialized:
        return
    
    try:
        ctx = get_pwd_context()
        # Compute hashes - this may trigger bcrypt initialization, but only on first auth
        USERS_DB = {
            "admin": {
                "username": "admin",
                "hashed_password": ctx.hash("admin123"),
                "role": "admin"
            },
            "user": {
                "username": "user",
                "hashed_password": ctx.hash("user123"),
                "role": "user"
            }
        }
        _users_db_initialized = True
    except Exception as e:
        # Fallback: use plain text comparison if bcrypt fails (NOT for production!)
        # This is a workaround for bcrypt initialization issues
        import warnings
        warnings.warn(f"Bcrypt initialization failed: {e}. Using plain text fallback (NOT SECURE!)")
        USERS_DB = {
            "admin": {
                "username": "admin",
                "hashed_password": "admin123",  # Plain text fallback
                "role": "admin"
            },
            "user": {
                "username": "user",
                "hashed_password": "user123",  # Plain text fallback
                "role": "user"
            }
        }
        _users_db_initialized = True


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return get_pwd_context().verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password"""
    return get_pwd_context().hash(password)


def authenticate_user(username: str, password: str) -> Optional[dict]:
    """Authenticate a user and return user info if valid"""
    # Initialize users DB on first authentication attempt
    if not _users_db_initialized:
        _init_users_db()
    
    user = USERS_DB.get(username)
    if not user:
        return None
    
    # Check if we're using plain text fallback
    if user["hashed_password"] == password:
        # Plain text fallback (bcrypt failed)
        return {"username": user["username"], "role": user["role"]}
    
    # Normal bcrypt verification
    if not verify_password(password, user["hashed_password"]):
        return None
    return {"username": user["username"], "role": user["role"]}


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Verify JWT token and return current user"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = USERS_DB.get(username)
    if user is None:
        raise credentials_exception
    
    return {"username": user["username"], "role": user["role"]}


async def get_current_active_user(current_user: dict = Depends(get_current_user)) -> dict:
    """Get current active user (can be extended for user status checks)"""
    return current_user
