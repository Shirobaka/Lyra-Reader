from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from .database import get_db, User
import os
from pathlib import Path
from dotenv import load_dotenv

script_dir = Path(__file__).resolve().parent
main_dir = script_dir.parent
dotenv_path = main_dir / ".env"
load_dotenv(dotenv_path=dotenv_path)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now() + expires_delta
    else:
        expire = datetime.now() + timedelta(days=int(os.getenv("ACCESS_TOKEN_EXPIRE_DAYS", 30)))  # Default to 30 days
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, os.getenv("SECRET_KEY"), algorithm=os.getenv("ALGORITHM", "HS256"))
    return encoded_jwt

def verify_token(token: str):
    try:
        payload = jwt.decode(token, os.getenv("SECRET_KEY"), algorithms=[os.getenv("ALGORITHM", "HS256")])
        username: str = payload.get("sub")
        if username is None:
            return None
        return username
    except JWTError:
        return None

def get_user_from_token(token: str, db: Session) -> Optional[User]:
    try:
        payload = jwt.decode(token, os.getenv("SECRET_KEY"), algorithms=[os.getenv("ALGORITHM", "HS256")])
        username: str = payload.get("sub")
        if username is None:
            return None
        
        user = db.query(User).filter(User.username == username).first()
        return user
    except JWTError:
        return None

def get_token_from_request(request: Request) -> Optional[str]:
    """Extract token from request (either Authorization header or cookie)"""
    # Try Authorization header first
    authorization = request.headers.get("authorization")
    if authorization and authorization.startswith("Bearer "):
        return authorization.split(" ")[1]
    
    # Try cookie
    return request.cookies.get("access_token")

def get_current_user_optional(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    """Get current user from token (either Bearer token or cookie) - optional"""
    token = get_token_from_request(request)
    if token:
        return get_user_from_token(token, db)
    return None

def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Get current user - required"""
    user = get_current_user_optional(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

def require_admin(request: Request, db: Session = Depends(get_db)) -> User:
    """Require admin access"""
    user = get_current_user(request, db)
    if "Admin" not in user.rights:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

# For API endpoints that need Bearer token authentication
def get_current_user_api(
    credentials: HTTPAuthorizationCredentials = Depends(security), 
    db: Session = Depends(get_db)
) -> User:
    """Get current user for API endpoints using Bearer token"""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = get_user_from_token(credentials.credentials, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

def require_admin_api(current_user: User = Depends(get_current_user_api)) -> User:
    """Require admin access for API endpoints"""
    if "Admin" not in current_user.rights:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user