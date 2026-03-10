"""SQLModel ORM adapter.

SQLModel uses SQLAlchemy under the hood, so this adapter subclasses
``SQLAlchemyAdapter`` and overrides field introspection to leverage
SQLModel's Pydantic metadata.

Usage::

    pip install fastrest[sqlmodel]

    from fastrest.compat.orm import set_default_adapter
    from fastrest.compat.orm.sqlmodel import adapter
    set_default_adapter(adapter)
"""

from __future__ import annotations

from typing import Any

from .base import FieldInfo, ORMAdapter
from .sqlalchemy import SQLAlchemyAdapter, _TYPE_MAP


class SQLModelAdapter(SQLAlchemyAdapter):
    """Adapter for SQLModel (SQLAlchemy + Pydantic) models."""

    def get_fields(self, model: Any) -> list[FieldInfo]:
        from sqlalchemy import inspect as sa_inspect

        mapper = sa_inspect(model)
        pydantic_fields = getattr(model, "model_fields", {})
        fields = []
        for col in mapper.columns:
            type_name = type(col.type).__name__.upper()
            field_type = _TYPE_MAP.get(type_name, "string")
            max_length = getattr(col.type, "length", None)

            # Enrich with Pydantic metadata if available
            pf = pydantic_fields.get(col.key)
            if pf is not None:
                metadata = getattr(pf, "metadata", [])
                for m in metadata:
                    if hasattr(m, "max_length") and m.max_length is not None:
                        max_length = m.max_length

            fields.append(FieldInfo(
                name=col.key,
                field_type=field_type,
                primary_key=col.primary_key,
                nullable=col.nullable or False,
                has_default=col.default is not None or col.server_default is not None or col.primary_key,
                max_length=max_length,
                column=col,
            ))
        return fields


# Default adapter singleton
adapter = SQLModelAdapter()
