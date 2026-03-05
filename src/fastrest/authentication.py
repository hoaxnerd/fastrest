"""Authentication classes matching DRF's authentication API."""

from __future__ import annotations

import base64
import binascii
from typing import Any

from fastrest.exceptions import AuthenticationFailed


class BaseAuthentication:
    """Base class for authentication backends.

    Subclasses must implement `authenticate(request)` which returns
    a `(user, auth)` tuple or `None` if the backend does not apply.
    """

    def authenticate(self, request: Any) -> tuple[Any, Any] | None:
        raise NotImplementedError

    def authenticate_header(self, request: Any) -> str | None:
        """Return a string to use as the WWW-Authenticate header value.

        If None, a 403 is returned instead of 401 on auth failure.
        """
        return None


class BasicAuthentication(BaseAuthentication):
    """HTTP Basic authentication.

    Users must supply a `get_user_by_credentials(username, password)`
    callable that returns a user object or None.
    """

    def __init__(self, get_user_by_credentials: Any = None):
        self.get_user_by_credentials = get_user_by_credentials

    def authenticate(self, request: Any) -> tuple[Any, Any] | None:
        auth_header = request.headers.get("authorization", "")
        if not auth_header.lower().startswith("basic "):
            return None

        try:
            encoded = auth_header.split(" ", 1)[1]
            decoded = base64.b64decode(encoded).decode("utf-8")
            username, password = decoded.split(":", 1)
        except (binascii.Error, UnicodeDecodeError, ValueError):
            raise AuthenticationFailed("Invalid basic authentication header.")

        if self.get_user_by_credentials is None:
            raise AuthenticationFailed("Basic auth backend not configured.")

        user = self.get_user_by_credentials(username, password)
        if user is None:
            raise AuthenticationFailed("Invalid username or password.")

        return (user, None)

    def authenticate_header(self, request: Any) -> str | None:
        return 'Basic realm="api"'


class TokenAuthentication(BaseAuthentication):
    """Token-based authentication via the Authorization header.

    Expects: `Authorization: Token <key>` (or Bearer).

    Users must supply a `get_user_by_token(token_key)` callable
    that returns a user object or None.
    """

    keyword: str = "Token"

    def __init__(self, get_user_by_token: Any = None, keyword: str | None = None):
        self.get_user_by_token = get_user_by_token
        if keyword is not None:
            self.keyword = keyword

    def authenticate(self, request: Any) -> tuple[Any, Any] | None:
        auth_header = request.headers.get("authorization", "")
        if not auth_header:
            return None

        parts = auth_header.split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != self.keyword.lower():
            return None

        token_key = parts[1].strip()
        if not token_key:
            raise AuthenticationFailed("Invalid token header. No token provided.")

        if self.get_user_by_token is None:
            raise AuthenticationFailed("Token auth backend not configured.")

        user = self.get_user_by_token(token_key)
        if user is None:
            raise AuthenticationFailed("Invalid token.")

        return (user, token_key)

    def authenticate_header(self, request: Any) -> str | None:
        return self.keyword


class SessionAuthentication(BaseAuthentication):
    """Session-based authentication.

    Reads the user from `request.session` or a configurable
    `get_user_from_session` callable.
    """

    def __init__(self, get_user_from_session: Any = None):
        self.get_user_from_session = get_user_from_session

    def authenticate(self, request: Any) -> tuple[Any, Any] | None:
        if self.get_user_from_session is not None:
            user = self.get_user_from_session(request)
            if user is None:
                return None
            return (user, None)

        # Fallback: try to read from Starlette session
        session = getattr(request, "session", None)
        if session is None:
            return None

        user_id = session.get("user_id")
        if user_id is None:
            return None

        # Return a minimal user dict — real apps should override
        return ({"id": user_id}, None)

    def authenticate_header(self, request: Any) -> str | None:
        return None
