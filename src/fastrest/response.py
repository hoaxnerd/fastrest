"""Response wrapper matching DRF's Response."""

from __future__ import annotations

from typing import Any

from starlette.responses import JSONResponse


class Response(JSONResponse):
    def __init__(
        self,
        data: Any = None,
        status: int = 200,
        headers: dict | None = None,
        content_type: str | None = None,
        **kwargs: Any,
    ):
        media_type = content_type or "application/json"
        super().__init__(
            content=data,
            status_code=status,
            headers=headers,
            media_type=media_type,
            **kwargs,
        )
        self.data = data
