"""Password hashing and signed-session helpers for the protected admin area.

backend.main uses these functions during login and request authorization;
admin setup tools use the same password format when creating accounts.
"""

import base64
import hashlib
import hmac
import os

from itsdangerous import URLSafeTimedSerializer

PASSWORD_MIN = 12
ROLES = {"SUPER_ADMIN", "DATA_ADMIN", "REVIEWER", "READ_ONLY"}


def hash_password(password):
    """Hash a new admin password with a random salt and scrypt.

    Connections: Admin account setup uses this format; verify_password() checks it at login.
    """
    if len(password) < PASSWORD_MIN:
        raise ValueError(f"Password must be at least {PASSWORD_MIN} characters")

    salt = os.urandom(16)
    digest = hashlib.scrypt(
        password.encode(),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
    )
    return (
        "scrypt$"
        + base64.urlsafe_b64encode(salt).decode()
        + "$"
        + base64.urlsafe_b64encode(digest).decode()
    )


def verify_password(password, encoded):
    """Check a submitted password against its stored scrypt hash.

    Connections: backend.main.login_post() calls this before creating an admin session.
    """
    try:
        _, salt_value, digest_value = encoded.split("$")
        salt = base64.urlsafe_b64decode(salt_value)
        expected = base64.urlsafe_b64decode(digest_value)
        actual = hashlib.scrypt(
            password.encode(),
            salt=salt,
            n=2**14,
            r=8,
            p=1,
        )
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def session_serializer():
    """Create the signer used for admin session cookies.

    Connections: make_session() signs login sessions and read_session() verifies them using the configured secret.
    """
    secret = os.environ.get("CET_ADMIN_SESSION_SECRET")
    if not secret:
        raise RuntimeError("CET_ADMIN_SESSION_SECRET is required")
    return URLSafeTimedSerializer(secret, salt="cet-cap-admin-session")


def make_session(user_id, role, auth_version=1):
    """Create a signed session payload for one admin account.

    Connections: The login route stores this token in the browser cookie; user() later validates it against the database.
    """
    return session_serializer().dumps({"uid": int(user_id), "role": role, "av": int(auth_version)})


def read_session(value, max_age=8 * 3600):
    """Verify a signed admin session and enforce its maximum age.

    Connections: backend.main.user() uses the decoded user ID, role and auth version to authorize requests.
    """
    try:
        return session_serializer().loads(value, max_age=max_age)
    except Exception:
        return None


def role_allowed(role, allowed):
    """Return whether an account role is included in the route's allowed roles.

    Connections: Admin authorization uses this check after resolving the signed session and database user.
    """
    return role in allowed
