"""SQLAlchemy ORM adapter."""

from __future__ import annotations

from typing import Any

from sqlalchemy import inspect, select, func, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import RelationshipProperty

from .base import ORMAdapter, FieldInfo, RelationInfo


# Map SQLAlchemy type names to generic field type strings
_TYPE_MAP: dict[str, str] = {
    "INTEGER": "integer",
    "BIGINTEGER": "integer",
    "SMALLINTEGER": "integer",
    "VARCHAR": "string",
    "STRING": "string",
    "TEXT": "text",
    "BOOLEAN": "boolean",
    "FLOAT": "float",
    "NUMERIC": "decimal",
    "DECIMAL": "decimal",
    "DATE": "date",
    "DATETIME": "datetime",
    "TIME": "time",
    "JSON": "json",
    "UUID": "uuid",
}


class SQLAlchemyAdapter(ORMAdapter):
    def get_fields(self, model: Any) -> list[FieldInfo]:
        mapper = inspect(model)
        fields = []
        for col in mapper.columns:
            type_name = type(col.type).__name__.upper()
            field_type = _TYPE_MAP.get(type_name, "string")
            max_length = getattr(col.type, "length", None)
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

    def get_field_type(self, field_info: FieldInfo) -> str:
        return field_info.field_type

    def get_relations(self, model: Any) -> list[RelationInfo]:
        mapper = inspect(model)
        relations = []
        for rel in mapper.relationships:
            relations.append(RelationInfo(
                name=rel.key,
                related_model=rel.mapper.class_,
                field_name=rel.key,
                relation_type="many_to_one" if rel.direction.name == "MANYTOONE" else "one_to_many",
            ))
        return relations

    def get_pk_field(self, model: Any) -> FieldInfo:
        for f in self.get_fields(model):
            if f.primary_key:
                return f
        raise ValueError(f"No primary key found on {model}")

    async def get_object(self, model: Any, session: AsyncSession, **lookup: Any) -> Any:
        stmt = select(model)
        for key, value in lookup.items():
            stmt = stmt.where(getattr(model, key) == value)
        result = await session.execute(stmt)
        return result.scalars().first()

    async def get_queryset(self, model: Any, session: AsyncSession) -> list[Any]:
        result = await session.execute(select(model))
        return list(result.scalars().all())

    async def filter_queryset(self, model: Any, session: AsyncSession, queryset: list[Any] | None = None, **filters: Any) -> list[Any]:
        stmt = select(model)
        for key, value in filters.items():
            stmt = stmt.where(getattr(model, key) == value)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, model: Any, session: AsyncSession, **data: Any) -> Any:
        instance = model(**data)
        session.add(instance)
        await session.flush()
        await session.refresh(instance)
        return instance

    async def update(self, instance: Any, session: AsyncSession, **data: Any) -> Any:
        for key, value in data.items():
            setattr(instance, key, value)
        session.add(instance)
        await session.flush()
        await session.refresh(instance)
        return instance

    async def delete(self, instance: Any, session: AsyncSession) -> None:
        await session.delete(instance)
        await session.flush()

    async def count(self, model: Any, session: AsyncSession) -> int:
        result = await session.execute(select(func.count()).select_from(model))
        return result.scalar() or 0

    async def exists(self, model: Any, session: AsyncSession, **lookup: Any) -> bool:
        obj = await self.get_object(model, session, **lookup)
        return obj is not None


# Default adapter singleton
adapter = SQLAlchemyAdapter()
