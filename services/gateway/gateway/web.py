"""Dashboard HTTP routes: auth, invites, members, keys. D-012, D-013.

Every state-changing route runs two guards before it does anything:
  * `_origin(request)` - CSRF. A browser attaches Origin to exactly the
    cross-site requests that matter; a mismatch is rejected.
  * `_require(...)`    - authentication, and role where the action is
    admin-only. Server-side, not a hidden button.
"""

from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Body, Request, Response
from fastapi.responses import JSONResponse

from . import accounts, apikeys
from .accounts import ROLE_ADMIN, ROLE_MEMBER, ROLES, SESSION_COOKIE, User


class HttpError(Exception):
    def __init__(self, status: int, message: str) -> None:
        self.status = status
        self.message = message


def _origin(request: Request) -> None:
    """Reject a state-changing request whose Origin is not ours."""
    if not accounts.origin_allowed(
        request.headers.get("origin"), request.headers.get("host")
    ):
        raise HttpError(403, "cross-origin request rejected")


async def _current_user(request: Request, db) -> User | None:
    sid = request.cookies.get(SESSION_COOKIE)
    if not sid:
        return None
    row = await db.get_session(sid)
    if not row:
        return None
    user_id, expires_at, email, name, role, disabled_at = row
    if accounts.is_expired(expires_at) or disabled_at is not None:
        await db.delete_session(sid)
        return None
    return User(id=user_id, email=email, name=name, role=role)


async def _require(request: Request, db, admin: bool = False) -> User:
    user = await _current_user(request, db)
    if user is None:
        raise HttpError(401, "not signed in")
    if admin and not user.is_admin:
        raise HttpError(403, "admin role required")
    return user


def build_router(gw) -> APIRouter:
    r = APIRouter()
    db = gw.db

    # ------------------------------------------------------------ auth

    @r.post("/auth/login")
    async def login(request: Request, response: Response,
                    payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        _origin(request)
        email = str(payload.get("email", "")).strip().lower()
        password = str(payload.get("password", ""))
        row = await db.get_user_by_email(email)
        ok = False
        if row and row[4] and row[5] is None:
            ok = accounts.verify_password(password, row[4])
        if not ok:
            # One message for "no such user" and "wrong password", so the
            # endpoint cannot be used to enumerate who has an account.
            await db.audit(email or "anonymous", None, None, 0, "rejected",
                           "failed dashboard login")
            raise HttpError(401, "email or password is incorrect")

        sid = secrets.token_urlsafe(32)
        await db.create_session(sid, row[0], accounts.expiry(accounts.SESSION_TTL))
        response.set_cookie(
            SESSION_COOKIE, sid,
            httponly=True,              # script cannot read it
            samesite="lax",             # not sent on a cross-site form post
            secure=request.url.scheme == "https",
            max_age=int(accounts.SESSION_TTL.total_seconds()),
            path="/",
        )
        return {"email": row[1], "name": row[2], "role": row[3]}

    @r.post("/auth/logout")
    async def logout(request: Request, response: Response) -> dict[str, str]:
        _origin(request)
        sid = request.cookies.get(SESSION_COOKIE)
        if sid:
            await db.delete_session(sid)
        response.delete_cookie(SESSION_COOKIE, path="/")
        return {"status": "signed out"}

    @r.get("/auth/me")
    async def me(request: Request) -> dict[str, Any]:
        user = await _require(request, db)
        return {"email": user.email, "name": user.name, "role": user.role}

    @r.post("/auth/accept")
    async def accept(request: Request, response: Response,
                     payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        """Consume an invite: set a name and password, get a session."""
        _origin(request)
        token = str(payload.get("token", "")).strip()
        name = str(payload.get("name", "")).strip()
        password = str(payload.get("password", ""))
        if not token or not name:
            raise HttpError(400, "token and name are required")
        problem = accounts.password_problem(password)
        if problem:
            raise HttpError(400, problem)

        inv = await db.find_invite(accounts.token_hash(token))
        if not inv:
            raise HttpError(400, "invite not found")
        invite_id, email, role, expires_at, consumed_at = inv
        if consumed_at is not None:
            raise HttpError(400, "invite has already been used")
        if accounts.is_expired(expires_at):
            raise HttpError(400, "invite has expired")
        # Single-use is enforced by the UPDATE's WHERE clause, so two
        # simultaneous accepts cannot both win.
        if not await db.consume_invite(invite_id):
            raise HttpError(400, "invite has already been used")

        uid = await db.create_user(email, name, role, accounts.hash_password(password))
        sid = secrets.token_urlsafe(32)
        await db.create_session(sid, uid, accounts.expiry(accounts.SESSION_TTL))
        response.set_cookie(
            SESSION_COOKIE, sid, httponly=True, samesite="lax",
            secure=request.url.scheme == "https",
            max_age=int(accounts.SESSION_TTL.total_seconds()), path="/")
        return {"email": email, "name": name, "role": role}

    # ------------------------------------------------------------ members

    @r.get("/admin/users")
    async def admin_users(request: Request) -> list[dict[str, Any]]:
        await _require(request, db, admin=True)
        return await db.list_users()

    @r.get("/admin/invites")
    async def admin_invites(request: Request) -> list[dict[str, Any]]:
        await _require(request, db, admin=True)
        return await db.list_invites()

    @r.post("/admin/invites")
    async def create_invite(request: Request,
                            payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        _origin(request)
        user = await _require(request, db, admin=True)
        email = str(payload.get("email", "")).strip().lower()
        role = str(payload.get("role", ROLE_MEMBER)).strip()
        if "@" not in email:
            raise HttpError(400, "a valid email is required")
        if role not in ROLES:
            raise HttpError(400, "role must be one of %s" % ", ".join(ROLES))
        raw, h = accounts.new_token()
        await db.create_invite(email, role, h, user.id,
                               accounts.expiry(accounts.INVITE_TTL))
        # The raw token is returned exactly once, to the admin who made it.
        # Only its hash is stored.
        return {"email": email, "role": role, "invite_path": "/accept?token=%s" % raw}

    # ------------------------------------------------------------ keys

    @r.get("/me/keys")
    async def my_keys(request: Request) -> list[dict[str, Any]]:
        user = await _require(request, db)
        return await db.list_keys_for_user(user.id)

    @r.post("/me/keys")
    async def create_my_key(request: Request,
                            payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        _origin(request)
        user = await _require(request, db)
        name = str((payload or {}).get("name", "")).strip() or "default"
        full, prefix, h = apikeys.generate()
        await db.create_user_key(user.id, name, prefix, h, user.role)
        # Shown once. Only the SHA-256 is stored, so it cannot be shown again.
        return {"name": name, "prefix": prefix, "api_key": full,
                "warning": "copy this now, it will not be shown again"}

    @r.post("/me/keys/{key_id}/revoke")
    async def revoke_my_key(request: Request, key_id: int) -> dict[str, Any]:
        _origin(request)
        user = await _require(request, db)
        owner = await db.key_owner(key_id)
        # A member may revoke only their own key. Checked against the stored
        # owner, not against anything the client sent.
        if owner != user.id and not user.is_admin:
            raise HttpError(403, "that key belongs to someone else")
        if owner is None and not user.is_admin:
            raise HttpError(403, "that key belongs to someone else")
        ok = await db.revoke_key_by_id(key_id)
        return {"revoked": ok}

    @r.get("/admin/keys")
    async def admin_keys(request: Request) -> list[dict[str, Any]]:
        await _require(request, db, admin=True)
        return await db.list_all_keys()

    # ------------------------------------------------------------ upstreams

    @r.post("/admin/upstreams/{slug}/enabled")
    async def set_upstream_enabled(request: Request, slug: str,
                                   payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        _origin(request)
        await _require(request, db, admin=True)
        enabled = bool(payload.get("enabled"))
        await db.set_enabled(slug, enabled)
        await gw.refresh(force=True)
        return {"slug": slug, "enabled": enabled}

    return r


def install_error_handler(api) -> None:
    @api.exception_handler(HttpError)
    async def _handle(_request: Request, exc: HttpError):
        return JSONResponse({"error": exc.message}, status_code=exc.status)
