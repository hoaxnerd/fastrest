"""Tests for the configuration layer."""

import pytest
from fastapi import FastAPI

from fastrest.settings import (
    APISettings,
    DEFAULTS,
    configure,
    get_settings,
    api_settings,
    _validate_settings,
)
from fastrest.permissions import AllowAny, IsAuthenticated


class TestAPISettings:
    def test_defaults(self):
        s = APISettings()
        assert s.PAGE_SIZE is None
        assert s.UNAUTHENTICATED_USER is None

    def test_user_settings_override(self):
        s = APISettings(user_settings={"PAGE_SIZE": 50})
        assert s.PAGE_SIZE == 50

    def test_import_strings(self):
        s = APISettings()
        perms = s.DEFAULT_PERMISSION_CLASSES
        assert perms[0] is AllowAny

    def test_unknown_setting_raises(self):
        s = APISettings()
        with pytest.raises(AttributeError, match="Invalid FastREST setting"):
            _ = s.NONEXISTENT_SETTING

    def test_reload(self):
        s = APISettings(user_settings={"PAGE_SIZE": 10})
        assert s.PAGE_SIZE == 10
        s.reload(user_settings={"PAGE_SIZE": 25})
        assert s.PAGE_SIZE == 25


class TestValidateSettings:
    def test_valid_keys_pass(self):
        result = _validate_settings({"PAGE_SIZE": 10, "STRICT_SETTINGS": True})
        assert result["PAGE_SIZE"] == 10

    def test_unknown_key_raises_strict(self):
        with pytest.raises(ValueError, match="Unknown FastREST settings"):
            _validate_settings({"TYPO_SETTING": True})

    def test_unknown_key_allowed_non_strict(self):
        result = _validate_settings({"TYPO_SETTING": True, "STRICT_SETTINGS": False})
        assert result["TYPO_SETTING"] is True

    def test_strict_is_default(self):
        with pytest.raises(ValueError):
            _validate_settings({"BOGUS": 123})


class TestConfigure:
    def test_configure_binds_to_app(self):
        app = FastAPI()
        configure(app, {"PAGE_SIZE": 30})
        settings = app.state.fastrest_settings
        assert settings.PAGE_SIZE == 30

    def test_configure_validates(self):
        app = FastAPI()
        with pytest.raises(ValueError, match="Unknown"):
            configure(app, {"BAD_KEY": True})

    def test_configure_non_strict(self):
        app = FastAPI()
        configure(app, {"BAD_KEY": True, "STRICT_SETTINGS": False})
        assert hasattr(app.state, "fastrest_settings")


class TestGetSettings:
    def test_returns_app_settings_from_app(self):
        app = FastAPI()
        configure(app, {"PAGE_SIZE": 42})
        settings = get_settings(app)
        assert settings.PAGE_SIZE == 42

    def test_returns_global_fallback(self):
        settings = get_settings(object())
        assert settings is api_settings

    def test_returns_from_request_like_object(self):
        app = FastAPI()
        configure(app, {"PAGE_SIZE": 99})

        class FakeRequest:
            pass
        req = FakeRequest()
        req.app = app

        settings = get_settings(req)
        assert settings.PAGE_SIZE == 99

    def test_unconfigured_app_falls_back(self):
        app = FastAPI()
        settings = get_settings(app)
        assert settings is api_settings


class TestAgentSettings:
    """Verify new agent-related settings have defaults."""

    def test_skill_defaults(self):
        s = APISettings()
        assert s.SKILL_ENABLED is True
        assert s.SKILL_NAME is None
        assert s.SKILL_INCLUDE_EXAMPLES is True

    def test_mcp_defaults(self):
        s = APISettings()
        assert s.MCP_ENABLED is True
        assert s.MCP_PREFIX == "/mcp"
        assert s.MCP_DEFAULT_SCOPES == []

    def test_override_agent_settings(self):
        s = APISettings(user_settings={
            "SKILL_ENABLED": False,
            "MCP_ENABLED": False,
            "MCP_PREFIX": "/tools",
        })
        assert s.SKILL_ENABLED is False
        assert s.MCP_ENABLED is False
        assert s.MCP_PREFIX == "/tools"
