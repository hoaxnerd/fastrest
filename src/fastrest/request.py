"""Request wrapper matching DRF's Request."""

from __future__ import annotations

from typing import Any

from starlette.requests import Request as StarletteRequest


class Request:
    def __init__(self, request: StarletteRequest, parsers: list | None = None,
                 authenticators: list | None = None):
        self._request = request
        self.parsers = parsers or []
        self.authenticators = authenticators or []
        self._data: Any = None
        self._user: Any = None
        self._auth: Any = None

    @property
    def query_params(self) -> dict:
        return dict(self._request.query_params)

    @property
    def data(self) -> Any:
        return self._data

    @data.setter
    def data(self, value: Any) -> None:
        self._data = value

    @property
    def user(self) -> Any:
        return self._user

    @user.setter
    def user(self, value: Any) -> None:
        self._user = value

    @property
    def auth(self) -> Any:
        return self._auth

    @auth.setter
    def auth(self, value: Any) -> None:
        self._auth = value

    @property
    def method(self) -> str:
        return self._request.method

    @property
    def content_type(self) -> str:
        return self._request.headers.get("content-type", "")

    @property
    def headers(self) -> Any:
        return self._request.headers

    @property
    def path_params(self) -> dict:
        return self._request.path_params

    def __getattr__(self, attr: str) -> Any:
        return getattr(self._request, attr)
