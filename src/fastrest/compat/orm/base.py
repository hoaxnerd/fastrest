"""Abstract ORM adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FieldInfo:
    name: str
    field_type: str  # e.g. "integer", "string", "boolean", "datetime", "text", "float", "decimal"
    primary_key: bool = False
    nullable: bool = False
    has_default: bool = False
    max_length: int | None = None
    related_model: Any = None
    column: Any = None  # raw ORM column reference


@dataclass
class RelationInfo:
    name: str
    related_model: Any
    field_name: str  # FK column name
    relation_type: str = "many_to_one"  # many_to_one, one_to_many, many_to_many
    reverse: bool = False


class ORMAdapter(ABC):
    requires_session: bool = True

    @abstractmethod
    def get_fields(self, model: Any) -> list[FieldInfo]:
        ...

    @abstractmethod
    def get_field_type(self, field_info: FieldInfo) -> str:
        ...

    @abstractmethod
    def get_relations(self, model: Any) -> list[RelationInfo]:
        ...

    @abstractmethod
    def get_pk_field(self, model: Any) -> FieldInfo:
        ...

    @abstractmethod
    async def get_object(self, model: Any, session: Any, **lookup: Any) -> Any:
        ...

    @abstractmethod
    async def get_queryset(self, model: Any, session: Any) -> list[Any]:
        ...

    @abstractmethod
    async def filter_queryset(self, model: Any, session: Any, queryset: list[Any] | None = None, **filters: Any) -> list[Any]:
        ...

    @abstractmethod
    async def create(self, model: Any, session: Any, **data: Any) -> Any:
        ...

    @abstractmethod
    async def update(self, instance: Any, session: Any, **data: Any) -> Any:
        ...

    @abstractmethod
    async def delete(self, instance: Any, session: Any) -> None:
        ...

    @abstractmethod
    async def count(self, model: Any, session: Any) -> int:
        ...

    @abstractmethod
    async def exists(self, model: Any, session: Any, **lookup: Any) -> bool:
        ...
