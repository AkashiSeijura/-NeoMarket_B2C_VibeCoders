from __future__ import annotations

import base64
import json
import uuid

from fastapi import Header

from src.services.cart_service import CartIdentity
from src.services.errors import MissingCartIdentityError, UnauthorizedError


def get_cart_identity(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
) -> CartIdentity:
    user_id = _user_id_from_authorization(authorization) if authorization else None
    if user_id is None and x_user_id:
        user_id = _parse_uuid(x_user_id)
    if user_id is not None:
        return CartIdentity(user_id=user_id)

    if x_session_id:
        return CartIdentity(session_id=x_session_id)

    raise MissingCartIdentityError("Pass Authorization, X-User-Id, or X-Session-Id")


def get_required_user_id(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> uuid.UUID:
    user_id = _user_id_from_authorization(authorization) if authorization else None
    if user_id is None and x_user_id:
        user_id = _parse_uuid(x_user_id)
    if user_id is None:
        raise UnauthorizedError("Missing or invalid user identity")
    return user_id


def get_required_session_id(x_session_id: str | None = Header(default=None, alias="X-Session-Id")) -> str:
    if not x_session_id:
        raise MissingCartIdentityError("Pass X-Session-Id")
    return x_session_id


def _user_id_from_authorization(authorization: str | None) -> uuid.UUID | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise UnauthorizedError("Invalid Authorization header")

    direct_uuid = _try_uuid(token)
    if direct_uuid is not None:
        return direct_uuid

    parts = token.split(".")
    if len(parts) < 2:
        raise UnauthorizedError("Invalid JWT")
    try:
        payload = json.loads(_b64url_decode(parts[1]))
    except (ValueError, json.JSONDecodeError) as exc:
        raise UnauthorizedError("Invalid JWT") from exc

    sub = payload.get("sub")
    user_id = _try_uuid(sub)
    if user_id is None:
        raise UnauthorizedError("JWT sub must be a UUID")
    return user_id


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode())


def _parse_uuid(value: str) -> uuid.UUID:
    parsed = _try_uuid(value)
    if parsed is None:
        raise UnauthorizedError("Identity must be a UUID")
    return parsed


def _try_uuid(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None

