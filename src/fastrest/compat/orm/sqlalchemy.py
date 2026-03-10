"""SQLAlchemy ORM adapter."""

from __future__ import annotations

from typing import Any

from sqlalchemy import inspect, select, func, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import RelationshipProperty

from .base import ORMAdapter, FieldInfo, RelationInfo


# Map SQLAlchemy type names to generic field type strings.
# Covers generic CamelCase types, SQL standard UPPERCASE types,
# and dialect-specific types (PostgreSQL, MySQL, MSSQL, Oracle).
_TYPE_MAP: dict[str, str] = {
    # ── Integer types ──
    "INTEGER": "integer", "BIGINTEGER": "integer", "SMALLINTEGER": "integer",
    "INT": "integer", "BIGINT": "integer", "SMALLINT": "integer",
    "TINYINT": "integer", "MEDIUMINT": "integer",

    # ── String types ──
    "VARCHAR": "string", "STRING": "string", "CHAR": "string",
    "NCHAR": "string", "NVARCHAR": "string",
    "UNICODE": "string",
    "NVARCHAR2": "string", "VARCHAR2": "string",  # Oracle
    "CITEXT": "string",  # PostgreSQL

    # ── Text types ──
    "TEXT": "text", "UNICODETEXT": "text", "CLOB": "text", "NCLOB": "text",
    "TINYTEXT": "text", "MEDIUMTEXT": "text", "LONGTEXT": "text",  # MySQL
    "LONG": "text",  # Oracle

    # ── Boolean ──
    "BOOLEAN": "boolean", "MATCHTYPE": "boolean",

    # ── Floating point ──
    "FLOAT": "float", "REAL": "float",
    "DOUBLE": "float", "DOUBLE_PRECISION": "float",

    # ── Decimal / Numeric ──
    "NUMERIC": "decimal", "DECIMAL": "decimal",
    "NUMBER": "decimal",  # Oracle
    "MONEY": "decimal",  # PostgreSQL

    # ── Date / Time ──
    "DATE": "date",
    "DATETIME": "datetime", "TIMESTAMP": "datetime",
    "TIME": "time",
    "INTERVAL": "duration",

    # ── JSON ──
    "JSON": "json", "JSONB": "json",

    # ── UUID ──
    "UUID": "uuid", "UNIQUEIDENTIFIER": "uuid",  # MSSQL

    # ── Binary ──
    "BLOB": "binary", "BINARY": "binary", "VARBINARY": "binary",
    "LARGEBINARY": "binary", "BYTEA": "binary",  # PostgreSQL
    "TINYBLOB": "binary", "MEDIUMBLOB": "binary", "LONGBLOB": "binary",  # MySQL
    "IMAGE": "binary",  # MSSQL
    "RAW": "binary", "BFILE": "binary",  # Oracle
    "PICKLETYPE": "binary",

    # ── Enum ──
    "ENUM": "choice",

    # ── Array (PostgreSQL) ──
    "ARRAY": "list",

    # ── Key-value (PostgreSQL) ──
    "HSTORE": "dict",

    # ── Network types (PostgreSQL) ──
    "INET": "ip", "CIDR": "ip",
    "MACADDR": "string", "MACADDR8": "string",

    # ── Full-text search (PostgreSQL) ──
    "TSVECTOR": "string", "TSQUERY": "string",

    # ── PostgreSQL misc ──
    "BIT": "string", "JSONPATH": "string",
    "OID": "integer", "REGCLASS": "string", "REGCONFIG": "string",

    # ── PostgreSQL range types ──
    "INT4RANGE": "json", "INT8RANGE": "json", "NUMRANGE": "json",
    "DATERANGE": "json", "TSRANGE": "json", "TSTZRANGE": "json",
    "INT4MULTIRANGE": "json", "INT8MULTIRANGE": "json",
    "NUMMULTIRANGE": "json", "DATEMULTIRANGE": "json",
    "TSMULTIRANGE": "json", "TSTZMULTIRANGE": "json",

    # ── MySQL-specific ──
    "YEAR": "integer", "SET": "list",
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
