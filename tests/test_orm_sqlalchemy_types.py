"""Tests for the expanded SQLAlchemy type mappings."""

import pytest
from sqlalchemy import (
    Column, Integer, BigInteger, SmallInteger, String, Text, Boolean,
    Float, Numeric, Date, DateTime, Time, JSON, LargeBinary, Enum,
    Interval,
)
from sqlalchemy.orm import DeclarativeBase

from fastrest.compat.orm.sqlalchemy import SQLAlchemyAdapter, _TYPE_MAP


class Base(DeclarativeBase):
    pass


class AllTypesModel(Base):
    __tablename__ = "all_types"
    id = Column(Integer, primary_key=True)
    big_int = Column(BigInteger)
    small_int = Column(SmallInteger)
    name = Column(String(100))
    description = Column(Text)
    is_active = Column(Boolean)
    price = Column(Float)
    amount = Column(Numeric(10, 2))
    created_date = Column(Date)
    created_at = Column(DateTime)
    start_time = Column(Time)
    data = Column(JSON)
    binary_data = Column(LargeBinary)
    duration = Column(Interval)
    status = Column(Enum("active", "inactive", name="status_enum"))


@pytest.fixture
def adapter():
    return SQLAlchemyAdapter()


class TestSQLAlchemyExpandedTypeMap:
    def test_all_model_field_types(self, adapter):
        fields = adapter.get_fields(AllTypesModel)
        type_map = {f.name: f.field_type for f in fields}

        assert type_map["id"] == "integer"
        assert type_map["big_int"] == "integer"
        assert type_map["small_int"] == "integer"
        assert type_map["name"] == "string"
        assert type_map["description"] == "text"
        assert type_map["is_active"] == "boolean"
        assert type_map["price"] == "float"
        assert type_map["amount"] == "decimal"
        assert type_map["created_date"] == "date"
        assert type_map["created_at"] == "datetime"
        assert type_map["start_time"] == "time"
        assert type_map["data"] == "json"
        assert type_map["binary_data"] == "binary"
        assert type_map["duration"] == "duration"
        assert type_map["status"] == "choice"

    def test_max_length_on_string(self, adapter):
        fields = adapter.get_fields(AllTypesModel)
        field_map = {f.name: f for f in fields}
        assert field_map["name"].max_length == 100

    def test_type_map_covers_integer_variants(self):
        for key in ["INTEGER", "BIGINTEGER", "SMALLINTEGER", "INT", "BIGINT",
                     "SMALLINT", "TINYINT", "MEDIUMINT"]:
            assert _TYPE_MAP[key] == "integer", f"{key} should map to 'integer'"

    def test_type_map_covers_string_variants(self):
        for key in ["VARCHAR", "STRING", "CHAR", "NCHAR", "NVARCHAR",
                     "UNICODE", "CITEXT", "NVARCHAR2", "VARCHAR2"]:
            assert _TYPE_MAP[key] == "string", f"{key} should map to 'string'"

    def test_type_map_covers_text_variants(self):
        for key in ["TEXT", "UNICODETEXT", "CLOB", "NCLOB",
                     "TINYTEXT", "MEDIUMTEXT", "LONGTEXT", "LONG"]:
            assert _TYPE_MAP[key] == "text", f"{key} should map to 'text'"

    def test_type_map_covers_float_variants(self):
        for key in ["FLOAT", "REAL", "DOUBLE", "DOUBLE_PRECISION"]:
            assert _TYPE_MAP[key] == "float", f"{key} should map to 'float'"

    def test_type_map_covers_decimal_variants(self):
        for key in ["NUMERIC", "DECIMAL", "NUMBER", "MONEY"]:
            assert _TYPE_MAP[key] == "decimal", f"{key} should map to 'decimal'"

    def test_type_map_covers_datetime_variants(self):
        assert _TYPE_MAP["DATE"] == "date"
        assert _TYPE_MAP["DATETIME"] == "datetime"
        assert _TYPE_MAP["TIMESTAMP"] == "datetime"
        assert _TYPE_MAP["TIME"] == "time"
        assert _TYPE_MAP["INTERVAL"] == "duration"

    def test_type_map_covers_json_variants(self):
        assert _TYPE_MAP["JSON"] == "json"
        assert _TYPE_MAP["JSONB"] == "json"

    def test_type_map_covers_uuid_variants(self):
        assert _TYPE_MAP["UUID"] == "uuid"
        assert _TYPE_MAP["UNIQUEIDENTIFIER"] == "uuid"

    def test_type_map_covers_binary_variants(self):
        for key in ["BLOB", "BINARY", "VARBINARY", "LARGEBINARY", "BYTEA",
                     "TINYBLOB", "MEDIUMBLOB", "LONGBLOB", "IMAGE", "RAW",
                     "BFILE", "PICKLETYPE"]:
            assert _TYPE_MAP[key] == "binary", f"{key} should map to 'binary'"

    def test_type_map_covers_postgresql_types(self):
        assert _TYPE_MAP["HSTORE"] == "dict"
        assert _TYPE_MAP["INET"] == "ip"
        assert _TYPE_MAP["CIDR"] == "ip"
        assert _TYPE_MAP["TSVECTOR"] == "string"
        assert _TYPE_MAP["TSQUERY"] == "string"
        assert _TYPE_MAP["BIT"] == "string"
        assert _TYPE_MAP["OID"] == "integer"
        assert _TYPE_MAP["MACADDR"] == "string"

    def test_type_map_covers_postgresql_range_types(self):
        for key in ["INT4RANGE", "INT8RANGE", "NUMRANGE", "DATERANGE",
                     "TSRANGE", "TSTZRANGE", "INT4MULTIRANGE", "INT8MULTIRANGE",
                     "NUMMULTIRANGE", "DATEMULTIRANGE", "TSMULTIRANGE", "TSTZMULTIRANGE"]:
            assert _TYPE_MAP[key] == "json", f"{key} should map to 'json'"

    def test_type_map_covers_mysql_types(self):
        assert _TYPE_MAP["YEAR"] == "integer"
        assert _TYPE_MAP["SET"] == "list"

    def test_type_map_covers_enum(self):
        assert _TYPE_MAP["ENUM"] == "choice"

    def test_type_map_covers_array(self):
        assert _TYPE_MAP["ARRAY"] == "list"

    def test_unknown_type_defaults_to_string(self, adapter):
        """Unknown types should fall back to 'string' via the .get default."""
        assert _TYPE_MAP.get("SOMEFUTURETYPE", "string") == "string"

    def test_requires_session_true(self, adapter):
        assert adapter.requires_session is True


class TestFieldTypeMapExpansion:
    """Test that FIELD_TYPE_MAP in fields.py covers all new normalized types."""

    def test_all_normalized_types_in_field_type_map(self):
        from fastrest.fields import FIELD_TYPE_MAP
        expected = {
            "integer", "string", "text", "boolean", "float", "decimal",
            "date", "datetime", "time", "duration", "json", "uuid",
            "email", "url", "slug", "ip", "choice", "list", "dict", "binary",
        }
        for t in expected:
            assert t in FIELD_TYPE_MAP, f"Normalized type '{t}' not in FIELD_TYPE_MAP"

    def test_field_type_map_returns_correct_classes(self):
        from fastrest.fields import (
            FIELD_TYPE_MAP, IntegerField, CharField, BooleanField, FloatField,
            DecimalField, DateField, DateTimeField, TimeField, DurationField,
            JSONField, UUIDField, EmailField, URLField, SlugField,
            IPAddressField, ChoiceField, ListField, DictField,
        )
        assert FIELD_TYPE_MAP["integer"] is IntegerField
        assert FIELD_TYPE_MAP["string"] is CharField
        assert FIELD_TYPE_MAP["text"] is CharField
        assert FIELD_TYPE_MAP["boolean"] is BooleanField
        assert FIELD_TYPE_MAP["float"] is FloatField
        assert FIELD_TYPE_MAP["decimal"] is DecimalField
        assert FIELD_TYPE_MAP["date"] is DateField
        assert FIELD_TYPE_MAP["datetime"] is DateTimeField
        assert FIELD_TYPE_MAP["time"] is TimeField
        assert FIELD_TYPE_MAP["duration"] is DurationField
        assert FIELD_TYPE_MAP["json"] is JSONField
        assert FIELD_TYPE_MAP["uuid"] is UUIDField
        assert FIELD_TYPE_MAP["email"] is EmailField
        assert FIELD_TYPE_MAP["url"] is URLField
        assert FIELD_TYPE_MAP["slug"] is SlugField
        assert FIELD_TYPE_MAP["ip"] is IPAddressField
        assert FIELD_TYPE_MAP["choice"] is ChoiceField
        assert FIELD_TYPE_MAP["list"] is ListField
        assert FIELD_TYPE_MAP["dict"] is DictField
        assert FIELD_TYPE_MAP["binary"] is CharField
