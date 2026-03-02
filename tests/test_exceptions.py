from fastrest.exceptions import (
    APIException, ValidationError, ParseError, NotAuthenticated,
    AuthenticationFailed, PermissionDenied, NotFound, MethodNotAllowed,
    Throttled, ErrorDetail, exception_handler,
)
from fastrest import status


class TestExceptionStatusCodes:
    def test_api_exception(self):
        assert APIException().status_code == 500

    def test_validation_error(self):
        assert ValidationError().status_code == 400

    def test_parse_error(self):
        assert ParseError().status_code == 400

    def test_not_authenticated(self):
        assert NotAuthenticated().status_code == 401

    def test_authentication_failed(self):
        assert AuthenticationFailed().status_code == 401

    def test_permission_denied(self):
        assert PermissionDenied().status_code == 403

    def test_not_found(self):
        assert NotFound().status_code == 404

    def test_method_not_allowed(self):
        exc = MethodNotAllowed("POST")
        assert exc.status_code == 405

    def test_throttled(self):
        assert Throttled().status_code == 429


class TestExceptionDetail:
    def test_default_detail(self):
        exc = NotFound()
        assert "Not found" in str(exc)

    def test_custom_detail(self):
        exc = NotFound(detail="Custom message")
        assert "Custom message" in str(exc)

    def test_validation_error_list(self):
        exc = ValidationError(["Error 1", "Error 2"])
        assert len(exc.detail) == 2

    def test_validation_error_dict(self):
        exc = ValidationError({"field": "Error"})
        assert "field" in exc.detail

    def test_get_codes(self):
        exc = NotFound()
        assert exc.get_codes() == "not_found"

    def test_get_full_details(self):
        exc = NotFound()
        details = exc.get_full_details()
        assert details["code"] == "not_found"
        assert "Not found" in details["message"]


class TestErrorDetail:
    def test_str(self):
        ed = ErrorDetail("test", code="invalid")
        assert str(ed) == "test"
        assert ed.code == "invalid"


class TestExceptionHandler:
    def test_handles_api_exception(self):
        exc = NotFound()
        result = exception_handler(exc, {})
        assert result["status"] == 404

    def test_returns_none_for_non_api(self):
        result = exception_handler(ValueError("oops"), {})
        assert result is None

    def test_throttled_retry_after(self):
        exc = Throttled(wait=30)
        result = exception_handler(exc, {})
        assert result["headers"]["Retry-After"] == "30"
