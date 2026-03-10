"""Beanie ODM adapter for MongoDB.

Beanie manages its own Motor client connections, so the ``session``
parameter is ignored in all async methods.

Usage::

    pip install fastrest[beanie]
"""

from __future__ import annotations

import datetime
import decimal
import uuid
from typing import Any, get_args, get_origin

from .base import FieldInfo, RelationInfo, ORMAdapter


# Map Python types to normalized field type strings.
_PYTHON_TYPE_MAP: dict[type, str] = {
    int: "integer",
    str: "string",
    float: "float",
    bool: "boolean",
    decimal.Decimal: "decimal",
    datetime.datetime: "datetime",
    datetime.date: "date",
    datetime.time: "time",
    datetime.timedelta: "duration",
    uuid.UUID: "uuid",
    bytes: "binary",
    dict: "json",
    list: "list",
    set: "list",
    tuple: "list",
}


def _resolve_type(annotation: Any) -> str:
    """Resolve a Python type annotation to a normalized field type string."""
    # Unwrap Optional[X] / X | None
    origin = get_origin(annotation)
    if origin is type(int | str):  # types.UnionType (3.10+)
        args = [a for a in get_args(annotation) if a is not type(None)]
        if args:
            return _resolve_type(args[0])
    # typing.Union / typing.Optional
    try:
        import typing
        if origin is typing.Union:
            args = [a for a in get_args(annotation) if a is not type(None)]
            if args:
                return _resolve_type(args[0])
    except Exception:
        pass

    # Check generic origins (list[int] → list, dict[str, Any] → dict)
    if origin is not None:
        direct = _PYTHON_TYPE_MAP.get(origin)
        if direct:
            return direct

    # Direct type lookup
    if isinstance(annotation, type):
        direct = _PYTHON_TYPE_MAP.get(annotation)
        if direct:
            return direct

        # Check by class name for special Pydantic / Beanie types
        name = annotation.__name__
        if name == "PydanticObjectId":
            return "string"
        if "Email" in name:
            return "email"
        if "Url" in name or "URL" in name:
            return "url"
        if "IP" in name or "IPv" in name:
            return "ip"

    return "string"


class BeanieAdapter(ORMAdapter):
    """Adapter for Beanie document models (MongoDB)."""

    requires_session = False

    def get_fields(self, model: Any) -> list[FieldInfo]:
        pydantic_fields = model.model_fields
        fields = []
        for name, field_info in pydantic_fields.items():
            annotation = field_info.annotation
            field_type = _resolve_type(annotation)

            # Determine if this is the PK
            is_pk = name == "id"

            # Check nullable
            nullable = False
            origin = get_origin(annotation)
            if origin is type(int | str):  # UnionType
                nullable = type(None) in get_args(annotation)
            else:
                try:
                    import typing
                    if origin is typing.Union:
                        nullable = type(None) in get_args(annotation)
                except Exception:
                    pass

            # Check default
            has_default = field_info.default is not None or is_pk
            if hasattr(field_info, "default_factory") and field_info.default_factory is not None:
                has_default = True

            # Max length from metadata
            max_length = None
            if hasattr(field_info, "metadata"):
                for m in field_info.metadata:
                    if hasattr(m, "max_length") and m.max_length is not None:
                        max_length = m.max_length

            fields.append(FieldInfo(
                name=name,
                field_type=field_type,
                primary_key=is_pk,
                nullable=nullable,
                has_default=has_default,
                max_length=max_length,
            ))
        return fields

    def get_field_type(self, field_info: FieldInfo) -> str:
        return field_info.field_type

    def get_relations(self, model: Any) -> list[RelationInfo]:
        relations = []
        for name, field_info in model.model_fields.items():
            annotation = field_info.annotation
            origin = get_origin(annotation)
            # Detect Link[T] references
            if origin is not None and getattr(origin, "__name__", "") == "Link":
                args = get_args(annotation)
                related = args[0] if args else None
                relations.append(RelationInfo(
                    name=name,
                    related_model=related,
                    field_name=name,
                    relation_type="many_to_one",
                ))
        return relations

    def get_pk_field(self, model: Any) -> FieldInfo:
        for f in self.get_fields(model):
            if f.primary_key:
                return f
        # Beanie always has an id field
        return FieldInfo(name="id", field_type="string", primary_key=True, has_default=True)

    async def get_object(self, model: Any, session: Any, **lookup: Any) -> Any:
        if "id" in lookup:
            try:
                return await model.get(lookup["id"])
            except Exception:
                return None
        # Build field-level query expressions
        conditions = {getattr(model, k): v for k, v in lookup.items() if hasattr(model, k)}
        if not conditions:
            return None
        return await model.find_one(conditions)

    async def get_queryset(self, model: Any, session: Any) -> list[Any]:
        return await model.find_all().to_list()

    async def filter_queryset(
        self, model: Any, session: Any,
        queryset: list[Any] | None = None, **filters: Any,
    ) -> list[Any]:
        conditions = {getattr(model, k): v for k, v in filters.items() if hasattr(model, k)}
        if not conditions:
            return await model.find_all().to_list()
        return await model.find(conditions).to_list()

    async def create(self, model: Any, session: Any, **data: Any) -> Any:
        doc = model(**data)
        await doc.insert()
        return doc

    async def update(self, instance: Any, session: Any, **data: Any) -> Any:
        await instance.set(data)
        return instance

    async def delete(self, instance: Any, session: Any) -> None:
        await instance.delete()

    async def count(self, model: Any, session: Any) -> int:
        return await model.count()

    async def exists(self, model: Any, session: Any, **lookup: Any) -> bool:
        obj = await self.get_object(model, session, **lookup)
        return obj is not None


# Default adapter singleton
adapter = BeanieAdapter()
