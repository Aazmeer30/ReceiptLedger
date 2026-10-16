"""
ReceiptLedger – Authentication & Session Endpoints
POST /api/v1/auth/login
POST /api/v1/auth/register
GET  /api/v1/auth/me
POST /api/v1/auth/logout
"""

from __future__ import annotations

import logging
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import (
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    UserSession,
    authenticate_user,
    create_access_token,
    get_current_user,
    register_user,
    require_auth,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication & Sessions"])


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Authenticate user and issue session JWT",
)
async def login(credentials: LoginRequest) -> AuthResponse:
    """
    Authenticate with email and password.
    Returns a signed JWT bearer token and user session details.

    Demo Account:
      - Email: `user@receiptledger.com`
      - Password: `demo1234`
    """
    user = authenticate_user(credentials.email, credentials.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(user)
    logger.info("User logged in: %s (%s)", user.email, user.user_id)
    return AuthResponse(access_token=token, user=user)


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def register(payload: RegisterRequest) -> AuthResponse:
    """Register a new user account, initialize their session, and issue a token."""
    try:
        user = register_user(
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

    token = create_access_token(user)
    logger.info("New user registered: %s (%s)", user.email, user.user_id)
    return AuthResponse(access_token=token, user=user)


@router.get(
    "/me",
    response_model=UserSession,
    summary="Get current user session profile",
)
async def get_me(user: UserSession = Depends(get_current_user)) -> UserSession:
    """Return the profile and authentication state of the current user session."""
    return user


@router.post(
    "/logout",
    summary="Terminate current session",
)
async def logout(user: UserSession = Depends(get_current_user)) -> Dict[str, str]:
    """Client-side session termination endpoint."""
    return {"status": "success", "message": "Successfully logged out."}
