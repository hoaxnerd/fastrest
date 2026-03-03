"""Pagination classes matching DRF's pagination API."""

from __future__ import annotations

import math
from typing import Any


class BasePagination:
    """Base class for pagination backends."""

    def paginate_queryset(self, queryset: list, request: Any, view: Any = None) -> list | None:
        raise NotImplementedError

    def get_paginated_response(self, data: list) -> dict:
        raise NotImplementedError


class PageNumberPagination(BasePagination):
    """Pagination using ?page=N&page_size=M query parameters."""

    page_size: int | None = None
    page_size_query_param: str = "page_size"
    page_query_param: str = "page"
    max_page_size: int | None = None

    def paginate_queryset(self, queryset: list, request: Any, view: Any = None) -> list | None:
        page_size = self.get_page_size(request)
        if page_size is None:
            return None

        page_number = 1
        try:
            page_number = int(request.query_params.get(self.page_query_param, 1))
        except (TypeError, ValueError):
            pass
        if page_number < 1:
            page_number = 1

        self._count = len(queryset)
        self._page_size = page_size
        self._page_number = page_number
        self._request = request

        start = (page_number - 1) * page_size
        end = start + page_size
        self._page = queryset[start:end]
        return self._page

    def get_page_size(self, request: Any) -> int | None:
        from fastrest.settings import api_settings

        size = self.page_size or api_settings.PAGE_SIZE
        if size is None:
            return None
        if self.page_size_query_param:
            try:
                requested = request.query_params.get(self.page_size_query_param)
                if requested is not None:
                    size = int(requested)
            except (TypeError, ValueError):
                pass
        if self.max_page_size and size:
            size = min(size, self.max_page_size)
        return size

    def get_paginated_response(self, data: list) -> dict:
        return {
            "count": self._count,
            "next": self._get_next_link(),
            "previous": self._get_previous_link(),
            "results": data,
        }

    def _get_next_link(self) -> str | None:
        if self._page_number * self._page_size >= self._count:
            return None
        return f"?{self.page_query_param}={self._page_number + 1}&{self.page_size_query_param}={self._page_size}"

    def _get_previous_link(self) -> str | None:
        if self._page_number <= 1:
            return None
        return f"?{self.page_query_param}={self._page_number - 1}&{self.page_size_query_param}={self._page_size}"


class LimitOffsetPagination(BasePagination):
    """Pagination using ?limit=N&offset=M query parameters."""

    default_limit: int | None = None
    limit_query_param: str = "limit"
    offset_query_param: str = "offset"
    max_limit: int | None = None

    def paginate_queryset(self, queryset: list, request: Any, view: Any = None) -> list | None:
        limit = self.get_limit(request)
        if limit is None:
            return None

        offset = self.get_offset(request)
        self._count = len(queryset)
        self._limit = limit
        self._offset = offset
        self._request = request
        return queryset[offset:offset + limit]

    def get_limit(self, request: Any) -> int | None:
        from fastrest.settings import api_settings

        limit = self.default_limit or api_settings.PAGE_SIZE
        if limit is None:
            return None
        try:
            requested = request.query_params.get(self.limit_query_param)
            if requested is not None:
                limit = int(requested)
        except (TypeError, ValueError):
            pass
        if self.max_limit and limit:
            limit = min(limit, self.max_limit)
        return limit

    def get_offset(self, request: Any) -> int:
        try:
            offset = request.query_params.get(self.offset_query_param)
            if offset is not None:
                return max(int(offset), 0)
        except (TypeError, ValueError):
            pass
        return 0

    def get_paginated_response(self, data: list) -> dict:
        return {
            "count": self._count,
            "next": self._get_next_link(),
            "previous": self._get_previous_link(),
            "results": data,
        }

    def _get_next_link(self) -> str | None:
        if self._offset + self._limit >= self._count:
            return None
        return f"?{self.limit_query_param}={self._limit}&{self.offset_query_param}={self._offset + self._limit}"

    def _get_previous_link(self) -> str | None:
        if self._offset <= 0:
            return None
        prev_offset = max(self._offset - self._limit, 0)
        return f"?{self.limit_query_param}={self._limit}&{self.offset_query_param}={prev_offset}"
