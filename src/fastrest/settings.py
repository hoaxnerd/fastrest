"""API settings, modeled after DRF's api_settings."""

from __future__ import annotations

import importlib
from typing import Any


DEFAULTS: dict[str, Any] = {
    # Auth & permissions
    "DEFAULT_PERMISSION_CLASSES": [
        "fastrest.permissions.AllowAny",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_THROTTLE_CLASSES": [],
    "DEFAULT_THROTTLE_RATES": {},

    # Rendering & parsing
    "DEFAULT_RENDERER_CLASSES": [],
    "DEFAULT_PARSER_CLASSES": [],

    # Pagination & filtering
    "DEFAULT_PAGINATION_CLASS": None,
    "DEFAULT_FILTER_BACKENDS": [],
    "PAGE_SIZE": None,

    # Error handling
    "EXCEPTION_HANDLER": "fastrest.exceptions.exception_handler",
    "UNAUTHENTICATED_USER": None,
    "UNAUTHENTICATED_TOKEN": None,

    # Agent integration
    "SKILL_ENABLED": True,
    "SKILL_NAME": None,
    "SKILL_BASE_URL": None,
    "SKILL_DESCRIPTION": None,
    "SKILL_AUTH_DESCRIPTION": None,
    "SKILL_INCLUDE_EXAMPLES": True,
    "SKILL_MAX_EXAMPLES_PER_RESOURCE": 3,
    "MCP_ENABLED": True,
    "MCP_PREFIX": "/mcp",
    "MCP_TOOL_NAME_FORMAT": "{basename}_{action}",
    "MCP_DEFAULT_SCOPES": [],
    "MCP_EXCLUDE_VIEWSETS": [],
}

VALID_KEYS = set(DEFAULTS.keys()) | {"STRICT_SETTINGS"}

IMPORT_STRINGS: list[str] = [
    "DEFAULT_PERMISSION_CLASSES",
    "DEFAULT_AUTHENTICATION_CLASSES",
    "DEFAULT_THROTTLE_CLASSES",
    "DEFAULT_RENDERER_CLASSES",
    "DEFAULT_PARSER_CLASSES",
    "DEFAULT_PAGINATION_CLASS",
    "DEFAULT_FILTER_BACKENDS",
    "EXCEPTION_HANDLER",
]


def import_string(dotted_path: str) -> Any:
    module_path, _, class_name = dotted_path.rpartition(".")
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def perform_import(val: Any, setting_name: str) -> Any:
    if val is None:
        return None
    if isinstance(val, str):
        return import_string(val)
    if isinstance(val, (list, tuple)):
        return [perform_import(item, setting_name) for item in val]
    return val


def _validate_settings(user_settings: dict[str, Any]) -> dict[str, Any]:
    """Validate user settings. Raises on unknown keys if STRICT_SETTINGS is True."""
    strict = user_settings.get("STRICT_SETTINGS", True)
    unknown = set(user_settings.keys()) - VALID_KEYS
    if unknown and strict:
        raise ValueError(
            f"Unknown FastREST settings: {unknown}. "
            f"Set STRICT_SETTINGS=False to ignore unknown keys."
        )
    return user_settings


class APISettings:
    def __init__(self, user_settings: dict[str, Any] | None = None, defaults: dict[str, Any] | None = None):
        self._user_settings = user_settings or {}
        self.defaults = defaults or DEFAULTS

    def __getattr__(self, attr: str) -> Any:
        if attr.startswith("_"):
            raise AttributeError(attr)

        try:
            val = self._user_settings[attr]
        except KeyError:
            try:
                val = self.defaults[attr]
            except KeyError:
                raise AttributeError(f"Invalid FastREST setting: {attr!r}")

        if attr in IMPORT_STRINGS:
            val = perform_import(val, attr)

        self.__dict__[attr] = val
        return val

    def reload(self, user_settings: dict[str, Any] | None = None) -> None:
        for key in self.defaults:
            self.__dict__.pop(key, None)
        if user_settings is not None:
            self._user_settings = user_settings


def configure(app: Any, settings: dict[str, Any]) -> None:
    """Bind FastREST settings to a FastAPI app instance.

    Usage:
        from fastrest.settings import configure
        configure(app, {"DEFAULT_PAGINATION_CLASS": PageNumberPagination, ...})
    """
    validated = _validate_settings(settings)
    app.state.fastrest_settings = APISettings(user_settings=validated)


def get_settings(request_or_app: Any) -> APISettings:
    """Resolve settings from request.app.state or app.state, falling back to global defaults."""
    app = None
    if hasattr(request_or_app, 'app'):
        app = request_or_app.app
    elif hasattr(request_or_app, 'state'):
        app = request_or_app

    if app is not None:
        settings = getattr(getattr(app, 'state', None), 'fastrest_settings', None)
        if settings is not None:
            return settings

    return api_settings


# Global fallback (used when configure() is not called)
api_settings = APISettings()
