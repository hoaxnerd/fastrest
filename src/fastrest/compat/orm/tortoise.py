"""Tortoise ORM adapter.

Tortoise manages its own connections internally, so the ``session``
parameter is ignored in all async methods.

Usage::

    pip install fastrest[tortoise]
"""

from __future__ import annotations

from typing import Any

from .base import FieldInfo, RelationInfo, ORMAdapter


# Map Tortoise field type names (from Model.describe()) to normalized types.
_TYPE_MAP: dict[str, str] = {
    # Integer types
    "IntField": "integer",
    "BigIntField": "integer",
    "SmallIntField": "integer",
    "IntEnumField": "choice",

    # String types
    "CharField": "string",
    "CharEnumField": "choice",

    # Text
    "TextField": "text",

    # Boolean
    "BooleanField": "boolean",

    # Floating point
    "FloatField": "float",

    # Decimal
    "DecimalField": "decimal",

    # Date / Time
    "DateField": "date",
    "DatetimeField": "datetime",
    "TimeField": "time",
    "TimeDeltaField": "duration",

    # JSON
    "JSONField": "json",

    # UUID
    "UUIDField": "uuid",

    # Binary
    "BinaryField": "binary",

    # Database-specific
    "GeometryField": "string",
    "TSVectorField": "string",
}


class TortoiseAdapter(ORMAdapter):
    """Adapter for Tortoise ORM models."""

    requires_session = False

    def get_fields(self, model: Any) -> list[FieldInfo]:
        desc = model.describe()
        fields = []

        # Process PK field
        pk = desc.get("pk_field")
        if pk:
            fields.append(self._field_from_desc(pk, is_pk=True))

        # Process data fields
        for f in desc.get("data_fields", []):
            fields.append(self._field_from_desc(f, is_pk=False))

        # Process FK fields (the concrete FK column, e.g. author_id)
        for f in desc.get("fk_fields", []):
            fields.append(self._field_from_desc(f, is_pk=False))

        return fields

    def _field_from_desc(self, desc: dict, *, is_pk: bool) -> FieldInfo:
        ft = desc.get("field_type", "")
        field_type = _TYPE_MAP.get(ft, "string")
        nullable = desc.get("nullable", False)
        has_default = desc.get("default") is not None or is_pk
        max_length = desc.get("constraints", {}).get("max_length")

        # FK fields store a raw_field name like "author_id"
        name = desc.get("raw_field", desc.get("name", ""))

        return FieldInfo(
            name=name,
            field_type=field_type,
            primary_key=is_pk,
            nullable=nullable,
            has_default=has_default,
            max_length=max_length,
        )

    def get_field_type(self, field_info: FieldInfo) -> str:
        return field_info.field_type

    def get_relations(self, model: Any) -> list[RelationInfo]:
        desc = model.describe()
        relations = []

        for f in desc.get("fk_fields", []):
            raw_field = f.get("raw_field", f.get("name", ""))
            python_type = f.get("python_type", "")
            relations.append(RelationInfo(
                name=f.get("name", ""),
                related_model=python_type,
                field_name=raw_field,
                relation_type="many_to_one",
            ))

        for f in desc.get("backward_fk_fields", []):
            relations.append(RelationInfo(
                name=f.get("name", ""),
                related_model=f.get("python_type", ""),
                field_name=f.get("name", ""),
                relation_type="one_to_many",
                reverse=True,
            ))

        for f in desc.get("m2m_fields", []):
            relations.append(RelationInfo(
                name=f.get("name", ""),
                related_model=f.get("python_type", ""),
                field_name=f.get("name", ""),
                relation_type="many_to_many",
            ))

        return relations

    def get_pk_field(self, model: Any) -> FieldInfo:
        for f in self.get_fields(model):
            if f.primary_key:
                return f
        raise ValueError(f"No primary key found on {model}")

    async def get_object(self, model: Any, session: Any, **lookup: Any) -> Any:
        return await model.get_or_none(**lookup)

    async def get_queryset(self, model: Any, session: Any) -> list[Any]:
        return await model.all()

    async def filter_queryset(
        self, model: Any, session: Any,
        queryset: list[Any] | None = None, **filters: Any,
    ) -> list[Any]:
        return await model.filter(**filters)

    async def create(self, model: Any, session: Any, **data: Any) -> Any:
        return await model.create(**data)

    async def update(self, instance: Any, session: Any, **data: Any) -> Any:
        for key, value in data.items():
            setattr(instance, key, value)
        await instance.save()
        return instance

    async def delete(self, instance: Any, session: Any) -> None:
        await instance.delete()

    async def count(self, model: Any, session: Any) -> int:
        return await model.all().count()

    async def exists(self, model: Any, session: Any, **lookup: Any) -> bool:
        return await model.exists(**lookup)


# Default adapter singleton
adapter = TortoiseAdapter()
