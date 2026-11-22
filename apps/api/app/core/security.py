from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import get_settings

_ph = PasswordHasher()


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


ISSUER = "ps05x-api"
AUDIENCE = "ps05x-web"


def create_access_token(user_id: str, role: str, *, minutes: int | None = None, scope: str = "full", case_id: str | None = None, epoch: int = 0) -> str:
    """Mint a bearer token.

    `case_id` binds a scoped upload/download token to one case, so it cannot be replayed against another case the
    holder happens to be a member of. A full session token is never case-bound: it is the ordinary session.
    """
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": role,
        "scope": scope,
        "epoch": epoch,
        "iss": ISSUER,
        "aud": AUDIENCE,
        "nbf": int(now.timestamp()) - 5,          # small leeway for clock skew between the web tier and the API
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes if minutes is not None else s.access_token_minutes)).timestamp()),
    }
    if case_id:
        payload["case"] = case_id
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def decode_token(token: str) -> dict:
    """Validate signature, algorithm, expiry, not-before, issuer and audience, and require the claims we rely on.

    Tokens issued before issuer/audience were introduced no longer validate; they are short-lived, so the effect is
    that anyone holding one signs in again.
    """
    s = get_settings()
    payload = jwt.decode(
        token,
        s.jwt_secret,
        algorithms=[s.jwt_algorithm],
        audience=AUDIENCE,
        issuer=ISSUER,
        options={"require": ["exp", "iat", "sub", "iss", "aud"], "verify_signature": True, "verify_exp": True, "verify_aud": True, "verify_iss": True},
    )
    if not payload.get("sub"):
        raise jwt.InvalidTokenError("missing subject")
    return payload
