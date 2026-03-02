"""Exception classes matching DRF's exception hierarchy."""

from __future__ import annotations

import math
from typing import Any

from fastrest import status


class APIException(Exception):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "A server error occurred."
    default_code = "error"

    def __init__(self, detail: Any = None, code: str | None = None):
        if detail is None:
            detail = self.default_detail
        if code is None:
            code = self.default_code

        self.detail = _get_error_details(detail, code)

    def __str__(self) -> str:
        return str(self.detail)

    def get_codes(self) -> Any:
        return _get_codes(self.detail)

    def get_full_details(self) -> Any:
        return _get_full_details(self.detail)


class ValidationError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Invalid input."
    default_code = "invalid"

    def __init__(self, detail: Any = None, code: str | None = None):
        if detail is None:
            detail = self.default_detail
        if not isinstance(detail, (dict, list)):
            detail = [detail]
        if code is None:
            code = self.default_code
        self.detail = _get_error_details(detail, code)


class ParseError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Malformed request."
    default_code = "parse_error"


class AuthenticationFailed(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Incorrect authentication credentials."
    default_code = "authentication_failed"


class NotAuthenticated(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Authentication credentials were not provided."
    default_code = "not_authenticated"


class PermissionDenied(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "You do not have permission to perform this action."
    default_code = "permission_denied"


class NotFound(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Not found."
    default_code = "not_found"


class MethodNotAllowed(APIException):
    status_code = status.HTTP_405_METHOD_NOT_ALLOWED
    default_detail = 'Method "{method}" not allowed.'
    default_code = "method_not_allowed"

    def __init__(self, method: str, detail: Any = None, code: str | None = None):
        if detail is None:
            detail = self.default_detail.format(method=method)
        super().__init__(detail=detail, code=code)


class NotAcceptable(APIException):
    status_code = status.HTTP_406_NOT_ACCEPTABLE
    default_detail = "Could not satisfy the request Accept header."
    default_code = "not_acceptable"


class UnsupportedMediaType(APIException):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    default_detail = 'Unsupported media type "{media_type}" in request.'
    default_code = "unsupported_media_type"

    def __init__(self, media_type: str, detail: Any = None, code: str | None = None):
        if detail is None:
            detail = self.default_detail.format(media_type=media_type)
        super().__init__(detail=detail, code=code)


class Throttled(APIException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_detail = "Request was throttled."
    default_code = "throttled"
    extra_detail_singular = "Expected available in {wait} second."
    extra_detail_plural = "Expected available in {wait} seconds."

    def __init__(self, wait: float | None = None, detail: Any = None, code: str | None = None):
        if detail is None:
            detail = self.default_detail
        if wait is not None:
            wait = math.ceil(wait)
            if wait == 1:
                detail += " " + self.extra_detail_singular.format(wait=wait)
            else:
                detail += " " + self.extra_detail_plural.format(wait=wait)
        self.wait = wait
        super().__init__(detail=detail, code=code)


# --- Error detail helpers ---

class ErrorDetail(str):
    code: str | None = None

    def __new__(cls, string: str, code: str | None = None):
        self = super().__new__(cls, string)
        self.code = code
        return self

    def __repr__(self) -> str:
        return f"ErrorDetail(string={str(self)!r}, code={self.code!r})"

    def __eq__(self, other: object) -> bool:
        return str.__eq__(self, other)

    def __hash__(self) -> int:
        return str.__hash__(self)


def _get_error_details(data: Any, default_code: str) -> Any:
    if isinstance(data, list):
        return [_get_error_details(item, default_code) for item in data]
    if isinstance(data, dict):
        return {key: _get_error_details(value, default_code) for key, value in data.items()}
    text = str(data)
    code = getattr(data, "code", default_code)
    return ErrorDetail(text, code)


def _get_codes(detail: Any) -> Any:
    if isinstance(detail, list):
        return [_get_codes(item) for item in detail]
    if isinstance(detail, dict):
        return {key: _get_codes(value) for key, value in detail.items()}
    return detail.code


def _get_full_details(detail: Any) -> Any:
    if isinstance(detail, list):
        return [_get_full_details(item) for item in detail]
    if isinstance(detail, dict):
        return {key: _get_full_details(value) for key, value in detail.items()}
    return {"message": str(detail), "code": detail.code}


def exception_handler(exc: Exception, context: dict | None = None) -> dict | None:
    if isinstance(exc, APIException):
        headers = {}
        if isinstance(exc, Throttled) and exc.wait is not None:
            headers["Retry-After"] = str(exc.wait)
        if isinstance(exc, (MethodNotAllowed,)):
            pass  # could add Allow header

        data = exc.detail
        return {"data": data, "status": exc.status_code, "headers": headers}
    return None
