from datetime import datetime, timedelta, timezone
from uuid import uuid4
import jwt
from jwt.exceptions import InvalidTokenError as JWTError
from pwdlib import PasswordHash
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.config import settings
from app.db import get_db
from app.models import User

passwords = PasswordHash.recommended()
oauth = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return passwords.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return passwords.verify(password, hashed)


def make_token(user: User, token_id: str | None = None) -> str:
    token_id = token_id or uuid4().hex
    payload = {
        "sub": user.username,
        "role": user.role,
        "jti": token_id,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.token_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def current_user(token: str = Depends(oauth), db: Session = Depends(get_db)) -> User:
    error = HTTPException(
        status_code=401, detail="Invalid or expired token", headers={"WWW-Authenticate": "Bearer"}
    )
    try:
        claims = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        username = claims.get("sub")
        token_id = claims.get("jti")
    except JWTError:
        raise error
    user = db.query(User).filter_by(username=username, active=True).first()
    if not user:
        raise error
    if token_id:
        from app.models import AuthSession

        session = db.query(AuthSession).filter_by(token_id=token_id, username=username).first()
        if not session or session.revoked_at is not None:
            raise error
    return user


def allow(*roles: str):
    def dependency(user: User = Depends(current_user)):
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return user

    return dependency
