from datetime import datetime, timedelta, timezone
import hashlib

import jwt
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.config import (
    REFRESH_TOKEN_EXPIRE_DAYS,
    SECRET_KEY,
    ALGORITHM,
    COOKIE_SECURE,
)
from backend.core.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
)
from backend.database import get_db
from backend.dependencies import get_current_user
from backend.models.auth_security import LoginRateLimit, RefreshSession
from backend.models.identity import User
from backend.schemas.auth import LoginRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])

LOGIN_WINDOW = timedelta(minutes=15)
LOGIN_BLOCK = timedelta(minutes=15)
LOGIN_MAX_ATTEMPTS = 8


def _utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _rate_limit_key(request: Request, email: str) -> str:
    # Store only a digest, not the submitted email or IP address.
    client_ip = request.client.host if request.client else "unknown"
    raw = f"{email.strip().lower()}|{client_ip}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _check_and_record_login_attempt(db: Session, key_hash: str) -> None:
    now = _utc_naive()
    try:
        entry = (
            db.query(LoginRateLimit)
            .filter(LoginRateLimit.key_hash == key_hash)
            .with_for_update()
            .first()
        )
        if entry is None:
            entry = LoginRateLimit(
                key_hash=key_hash,
                window_started_at=now,
                attempts=1,
            )
            db.add(entry)
        else:
            if entry.blocked_until and entry.blocked_until > now:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many login attempts. Try again later.",
                    headers={"Retry-After": str(max(1, int((entry.blocked_until - now).total_seconds())))},
                )
            if now - entry.window_started_at >= LOGIN_WINDOW:
                entry.window_started_at = now
                entry.attempts = 1
                entry.blocked_until = None
            else:
                entry.attempts += 1
            if entry.attempts > LOGIN_MAX_ATTEMPTS:
                entry.blocked_until = now + LOGIN_BLOCK
        db.commit()
        if entry.blocked_until and entry.blocked_until > now:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many login attempts. Try again later.",
                headers={"Retry-After": str(int(LOGIN_BLOCK.total_seconds()))},
            )
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        # Concurrent first attempts may race to create the same digest row.
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Login is temporarily busy. Retry shortly.",
            headers={"Retry-After": "2"},
        )


def _reset_login_attempts(db: Session, key_hash: str) -> None:
    entry = (
        db.query(LoginRateLimit)
        .filter(LoginRateLimit.key_hash == key_hash)
        .with_for_update()
        .first()
    )
    if entry:
        entry.attempts = 0
        entry.blocked_until = None
        entry.window_started_at = _utc_naive()
        db.commit()


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="refresh_token",
        value=token,
        httponly=True,
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        samesite="lax",
        secure=COOKIE_SECURE,
        path="/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key="refresh_token",
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
        path="/auth",
    )


def _register_refresh_session(db: Session, user_id: int, token: str) -> None:
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    jti = payload.get("jti")
    exp = payload.get("exp")
    if not jti or not exp:
        raise RuntimeError("Generated refresh token is missing required claims.")
    expires_at = datetime.fromtimestamp(exp, timezone.utc).replace(tzinfo=None)
    db.add(RefreshSession(user_id=user_id, jti=jti, expires_at=expires_at))


def _revoke_refresh_session(db: Session, token: str, user_id: int | None = None) -> bool:
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    if payload.get("token_type") != "refresh":
        return False
    jti = payload.get("jti")
    if not jti:
        return False
    query = db.query(RefreshSession).filter(RefreshSession.jti == jti)
    if user_id is not None:
        query = query.filter(RefreshSession.user_id == user_id)
    session = query.with_for_update().first()
    if session is None or session.revoked_at is not None or session.expires_at <= _utc_naive():
        return False
    session.revoked_at = _utc_naive()
    return True


@router.post("/login", response_model=TokenResponse)
def login(request: Request, response: Response, credentials: LoginRequest, db: Session = Depends(get_db)):
    key_hash = _rate_limit_key(request, credentials.email)
    _check_and_record_login_attempt(db, key_hash)

    generic_401 = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    user = db.query(User).filter(User.email == credentials.email).first()
    if not user or not verify_password(credentials.password, user.password_hash):
        raise generic_401
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")

    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})
    _register_refresh_session(db, user.id, refresh_token)
    _reset_login_attempts(db, key_hash)
    db.commit()
    _set_refresh_cookie(response, refresh_token)
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token missing")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("token_type") != "refresh" or not payload.get("jti"):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
        user_id = int(payload["sub"])
    except HTTPException:
        raise
    except (jwt.PyJWTError, ValueError, TypeError, KeyError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    session = (
        db.query(RefreshSession)
        .filter(RefreshSession.jti == payload["jti"], RefreshSession.user_id == user_id)
        .with_for_update()
        .first()
    )
    now = _utc_naive()
    if session is None or session.revoked_at is not None or session.expires_at <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token has been revoked or expired")
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        session.revoked_at = now
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    # Revoke old token and register its replacement in one transaction.
    session.revoked_at = now
    new_access_token = create_access_token(data={"sub": str(user.id)})
    new_refresh_token = create_refresh_token(data={"sub": str(user.id)})
    _register_refresh_session(db, user.id, new_refresh_token)
    db.commit()
    _set_refresh_cookie(response, new_refresh_token)
    return {"access_token": new_access_token, "token_type": "bearer"}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get("refresh_token")
    if token:
        try:
            _revoke_refresh_session(db, token)
            db.commit()
        except (jwt.PyJWTError, ValueError, TypeError):
            db.rollback()
    _clear_refresh_cookie(response)
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
        "role": current_user.role,
        "department_id": current_user.department_id,
    }
