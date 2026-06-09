"""Authentication endpoints: token-paste login, logout, and whoami.

On OpenShift the oauth-proxy sidecar supplies the user token via header and no
login call is needed; these endpoints back the vanilla-Kubernetes token-paste
flow and report the current identity in both cases.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from kubertree.auth._auth import (
    SESSION_COOKIE,
    AuthError,
    ambient_clients,
    clients_for_token,
    current_username,
    is_local_mode,
    token_from_request,
    validate_token,
)

router = APIRouter(prefix="/api")

_COOKIE_MAX_AGE = 12 * 60 * 60


class LoginRequest(BaseModel):
    token: str


@router.post("/login")
def login(body: LoginRequest, request: Request, response: Response) -> dict:
    token = body.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="Token is required")
    clients = clients_for_token(token)
    try:
        validate_token(clients)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )
    return {"user": current_username(clients)}


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(SESSION_COOKIE)
    return {"loggedOut": True}


@router.get("/whoami")
def whoami(request: Request) -> dict:
    token = token_from_request(request)
    if not token:
        if is_local_mode():
            return {"user": current_username(ambient_clients()), "local": True}
        raise HTTPException(status_code=401, detail="Not authenticated")
    clients = clients_for_token(token)
    try:
        validate_token(clients)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return {"user": current_username(clients)}
