"""Filter backends matching DRF's filter API."""

from __future__ import annotations

from typing import Any


class BaseFilterBackend:
    """Base class for filter backends."""

    def filter_queryset(self, request: Any, queryset: list, view: Any) -> list:
        raise NotImplementedError


class SearchFilter(BaseFilterBackend):
    """Filter that searches across specified fields with ?search=term."""

    search_param: str = "search"

    def filter_queryset(self, request: Any, queryset: list, view: Any) -> list:
        search_fields = getattr(view, "search_fields", None)
        search_term = request.query_params.get(self.search_param, "").strip()
        if not search_fields or not search_term:
            return queryset

        term_lower = search_term.lower()
        return [
            obj for obj in queryset
            if any(
                term_lower in str(getattr(obj, field, "")).lower()
                for field in search_fields
            )
        ]


class OrderingFilter(BaseFilterBackend):
    """Filter that orders results with ?ordering=-price,name."""

    ordering_param: str = "ordering"

    def filter_queryset(self, request: Any, queryset: list, view: Any) -> list:
        ordering = request.query_params.get(self.ordering_param, "")
        if not ordering:
            default = getattr(view, "ordering", None)
            if default:
                ordering = ",".join(default) if isinstance(default, (list, tuple)) else default
            else:
                return queryset

        allowed = getattr(view, "ordering_fields", None)
        fields = [f.strip() for f in ordering.split(",") if f.strip()]

        for field_expr in reversed(fields):
            reverse = field_expr.startswith("-")
            field_name = field_expr.lstrip("-")
            if allowed and field_name not in allowed:
                continue
            queryset = sorted(
                queryset,
                key=lambda obj, f=field_name: (getattr(obj, f, None) is None, getattr(obj, f, None)),
                reverse=reverse,
            )
        return queryset
