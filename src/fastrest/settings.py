"""API settings, modeled after DRF's api_settings."""

from __future__ import annotations

import importlib
from typing import Any


DEFAULTS: dict[str, Any] = {
    "DEFAULT_PERMISSION_CLASSES": [
        "fastrest.permissions.AllowAny",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_THROTTLE_CLASSES": [],
    "DEFAULT_RENDERER_CLASSES": [],
    "DEFAULT_PARSER_CLASSES": [],
    "DEFAULT_PAGINATION_CLASS": None,
    "DEFAULT_FILTER_BACKENDS": [],
    "EXCEPTION_HANDLER": "fastrest.exceptions.exception_handler",
    "UNAUTHENTICATED_USER": None,
    "UNAUTHENTICATED_TOKEN": None,
    "PAGE_SIZE": None,
}

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
            val = self.defaults[attr]

        if attr in IMPORT_STRINGS:
            val = perform_import(val, attr)

        self.__dict__[attr] = val
        return val

    def reload(self, user_settings: dict[str, Any] | None = None) -> None:
        for key in self.defaults:
            self.__dict__.pop(key, None)
        if user_settings is not None:
            self._user_settings = user_settings


api_settings = APISettings()
