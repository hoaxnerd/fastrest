"""Serializer → Pydantic model conversion for OpenAPI schema generation."""

from __future__ import annotations

import datetime
import uuid
from typing import Any, Optional

from pydantic import create_model

from fastrest import fields as f

_model_cache: dict[tuple, type] = {}

# Map field classes to Python types
FIELD_PYTHON_TYPE: dict[type, type] = {
    f.CharField: str,
    f.EmailField: str,
    f.RegexField: str,
    f.SlugField: str,
    f.URLField: str,
    f.IPAddressField: str,
    f.IntegerField: int,
    f.FloatField: float,
    f.BooleanField: bool,
    f.DecimalField: str,
    f.DateTimeField: datetime.datetime,
    f.DateField: datetime.date,
    f.TimeField: datetime.time,
    f.DurationField: float,
    f.UUIDField: uuid.UUID,
    f.ListField: list,
    f.DictField: dict,
    f.JSONField: Any,
    f.FileField: str,
    f.ImageField: str,
    f.ChoiceField: str,
    f.MultipleChoiceField: list,
    f.SerializerMethodField: Any,
    f.ReadOnlyField: Any,
    f.HiddenField: Any,
}


def _python_type_for_field(field: f.Field) -> type:
    for cls in type(field).__mro__:
        if cls in FIELD_PYTHON_TYPE:
            return FIELD_PYTHON_TYPE[cls]
    return Any


def _get_serializer_fields(serializer_cls) -> dict[str, f.Field]:
    """Instantiate serializer to get bound fields."""
    instance = serializer_cls()
    return instance.fields


def serializer_to_response_model(serializer_cls, name: str | None = None):
    """Build a Pydantic model for readable (non-write-only) fields."""
    name = name or f"{serializer_cls.__name__}Response"
    cache_key = (serializer_cls, name)
    if cache_key in _model_cache:
        return _model_cache[cache_key]

    fields_dict = {}
    for field_name, field in _get_serializer_fields(serializer_cls).items():
        if field.write_only:
            continue
        py_type = _python_type_for_field(field)
        if field.allow_null:
            py_type = Optional[py_type]
        fields_dict[field_name] = (py_type, ...)

    model = create_model(name, **fields_dict)
    _model_cache[cache_key] = model
    return model


def paginated_response_model(item_model, name: str):
    """Build a Pydantic model for paginated envelope responses."""
    return create_model(
        name,
        count=(int, ...),
        next=(Optional[str], None),
        previous=(Optional[str], None),
        results=(list[item_model], ...),
    )


def serializer_to_request_model(serializer_cls, name: str | None = None, partial: bool = False):
    """Build a Pydantic model for writable (non-read-only) fields."""
    suffix = "PatchRequest" if partial else "Request"
    name = name or f"{serializer_cls.__name__}{suffix}"
    cache_key = (serializer_cls, name)
    if cache_key in _model_cache:
        return _model_cache[cache_key]

    fields_dict = {}
    for field_name, field in _get_serializer_fields(serializer_cls).items():
        if field.read_only:
            continue
        py_type = _python_type_for_field(field)
        if field.allow_null or partial:
            py_type = Optional[py_type]
        if partial or not field.required:
            default = None
            if not partial and field.default is not f.empty:
                default = field.default if not callable(field.default) else None
            fields_dict[field_name] = (py_type, default)
        else:
            fields_dict[field_name] = (py_type, ...)

    model = create_model(name, **fields_dict)
    _model_cache[cache_key] = model
    return model
