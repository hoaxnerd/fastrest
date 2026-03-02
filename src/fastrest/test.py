"""Test utilities matching DRF's test API."""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI


class APIClient:
    def __init__(self, app: FastAPI, base_url: str = "http://testserver"):
        self.app = app
        self.base_url = base_url
        self._credentials: dict = {}
        self._force_auth_user: Any = None
        self._force_auth_token: Any = None

    def _get_client(self) -> AsyncClient:
        transport = ASGITransport(app=self.app)
        return AsyncClient(transport=transport, base_url=self.base_url)

    def force_authenticate(self, user: Any = None, token: Any = None) -> None:
        self._force_auth_user = user
        self._force_auth_token = token

    def credentials(self, **kwargs: Any) -> None:
        self._credentials = kwargs

    def logout(self) -> None:
        self._force_auth_user = None
        self._force_auth_token = None
        self._credentials = {}

    async def get(self, path: str, **kwargs: Any) -> Any:
        async with self._get_client() as client:
            return await client.get(path, **kwargs)

    async def post(self, path: str, json: Any = None, **kwargs: Any) -> Any:
        async with self._get_client() as client:
            return await client.post(path, json=json, **kwargs)

    async def put(self, path: str, json: Any = None, **kwargs: Any) -> Any:
        async with self._get_client() as client:
            return await client.put(path, json=json, **kwargs)

    async def patch(self, path: str, json: Any = None, **kwargs: Any) -> Any:
        async with self._get_client() as client:
            return await client.patch(path, json=json, **kwargs)

    async def delete(self, path: str, **kwargs: Any) -> Any:
        async with self._get_client() as client:
            return await client.delete(path, **kwargs)


class APIRequestFactory:
    pass


def force_authenticate(request: Any, user: Any = None, token: Any = None) -> None:
    request.user = user
    request.auth = token
