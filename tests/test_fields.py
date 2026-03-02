import datetime
import decimal
import uuid

import pytest
from fastrest.fields import (
    Field, BooleanField, CharField, EmailField, SlugField, URLField,
    IntegerField, FloatField, DecimalField, DateTimeField, DateField,
    TimeField, ChoiceField, ListField, DictField, JSONField, UUIDField,
    SerializerMethodField, ReadOnlyField, HiddenField, empty,
)
from fastrest.exceptions import ValidationError


class TestField:
    def test_required_by_default(self):
        f = Field()
        assert f.required is True

    def test_not_required_with_default(self):
        f = Field(default="x")
        assert f.required is False

    def test_read_only_not_required(self):
        f = Field(read_only=True)
        assert f.required is False

    def test_run_validation_required(self):
        f = Field()
        f.bind("test", None)
        with pytest.raises(ValidationError):
            f.run_validation(empty)

    def test_run_validation_null_disallowed(self):
        f = Field()
        f.bind("test", None)
        with pytest.raises(ValidationError):
            f.run_validation(None)

    def test_allow_null(self):
        f = Field(allow_null=True)
        f.bind("test", None)
        assert f.run_validation(None) is None


class TestBooleanField:
    def test_true_values(self):
        f = BooleanField()
        assert f.to_internal_value(True) is True
        assert f.to_internal_value("true") is True
        assert f.to_internal_value(1) is True

    def test_false_values(self):
        f = BooleanField()
        assert f.to_internal_value(False) is False
        assert f.to_internal_value("false") is False
        assert f.to_internal_value(0) is False

    def test_invalid(self):
        f = BooleanField()
        with pytest.raises(ValidationError):
            f.to_internal_value("maybe")


class TestCharField:
    def test_valid(self):
        f = CharField()
        assert f.to_internal_value("hello") == "hello"

    def test_blank_disallowed(self):
        f = CharField()
        with pytest.raises(ValidationError):
            f.to_internal_value("")

    def test_allow_blank(self):
        f = CharField(allow_blank=True)
        assert f.to_internal_value("") == ""

    def test_max_length(self):
        f = CharField(max_length=5)
        with pytest.raises(ValidationError):
            f.to_internal_value("toolong")

    def test_min_length(self):
        f = CharField(min_length=3)
        with pytest.raises(ValidationError):
            f.to_internal_value("ab")

    def test_trim_whitespace(self):
        f = CharField()
        assert f.to_internal_value("  hello  ") == "hello"

    def test_no_trim(self):
        f = CharField(trim_whitespace=False)
        assert f.to_internal_value("  hello  ") == "  hello  "


class TestEmailField:
    def test_valid(self):
        f = EmailField()
        assert f.to_internal_value("a@b.com") == "a@b.com"

    def test_invalid(self):
        f = EmailField()
        with pytest.raises(ValidationError):
            f.to_internal_value("notanemail")


class TestSlugField:
    def test_valid(self):
        f = SlugField()
        assert f.to_internal_value("my-slug_1") == "my-slug_1"

    def test_invalid(self):
        f = SlugField()
        with pytest.raises(ValidationError):
            f.to_internal_value("invalid slug!")


class TestURLField:
    def test_valid(self):
        f = URLField()
        assert f.to_internal_value("https://example.com") == "https://example.com"

    def test_invalid(self):
        f = URLField()
        with pytest.raises(ValidationError):
            f.to_internal_value("not-a-url")


class TestIntegerField:
    def test_valid(self):
        f = IntegerField()
        assert f.to_internal_value("42") == 42

    def test_invalid(self):
        f = IntegerField()
        with pytest.raises(ValidationError):
            f.to_internal_value("abc")

    def test_max_value(self):
        f = IntegerField(max_value=10)
        with pytest.raises(ValidationError):
            f.to_internal_value(11)

    def test_min_value(self):
        f = IntegerField(min_value=5)
        with pytest.raises(ValidationError):
            f.to_internal_value(3)


class TestFloatField:
    def test_valid(self):
        f = FloatField()
        assert f.to_internal_value("3.14") == 3.14

    def test_invalid(self):
        f = FloatField()
        with pytest.raises(ValidationError):
            f.to_internal_value("abc")


class TestDecimalField:
    def test_valid(self):
        f = DecimalField(max_digits=5, decimal_places=2)
        assert f.to_internal_value("3.14") == decimal.Decimal("3.14")

    def test_invalid(self):
        f = DecimalField()
        with pytest.raises(ValidationError):
            f.to_internal_value("abc")


class TestDateTimeField:
    def test_valid_string(self):
        f = DateTimeField()
        result = f.to_internal_value("2024-01-15T10:30:00")
        assert isinstance(result, datetime.datetime)

    def test_valid_datetime(self):
        f = DateTimeField()
        dt = datetime.datetime(2024, 1, 15, 10, 30)
        assert f.to_internal_value(dt) == dt

    def test_invalid(self):
        f = DateTimeField()
        with pytest.raises(ValidationError):
            f.to_internal_value("not-a-date")

    def test_representation(self):
        f = DateTimeField()
        dt = datetime.datetime(2024, 1, 15, 10, 30)
        assert "2024-01-15" in f.to_representation(dt)


class TestDateField:
    def test_valid(self):
        f = DateField()
        assert f.to_internal_value("2024-01-15") == datetime.date(2024, 1, 15)

    def test_invalid(self):
        f = DateField()
        with pytest.raises(ValidationError):
            f.to_internal_value("nope")


class TestTimeField:
    def test_valid(self):
        f = TimeField()
        assert f.to_internal_value("10:30:00") == datetime.time(10, 30)


class TestUUIDField:
    def test_valid(self):
        f = UUIDField()
        val = "12345678-1234-5678-1234-567812345678"
        assert f.to_internal_value(val) == uuid.UUID(val)

    def test_invalid(self):
        f = UUIDField()
        with pytest.raises(ValidationError):
            f.to_internal_value("not-a-uuid")


class TestChoiceField:
    def test_valid(self):
        f = ChoiceField(choices=["a", "b", "c"])
        assert f.to_internal_value("a") == "a"

    def test_invalid(self):
        f = ChoiceField(choices=["a", "b"])
        with pytest.raises(ValidationError):
            f.to_internal_value("z")


class TestListField:
    def test_valid(self):
        f = ListField(child=IntegerField())
        assert f.to_internal_value([1, 2, 3]) == [1, 2, 3]

    def test_not_a_list(self):
        f = ListField()
        with pytest.raises(ValidationError):
            f.to_internal_value("not a list")


class TestDictField:
    def test_valid(self):
        f = DictField()
        assert f.to_internal_value({"a": 1}) == {"a": 1}

    def test_not_a_dict(self):
        f = DictField()
        with pytest.raises(ValidationError):
            f.to_internal_value("not a dict")


class TestJSONField:
    def test_passthrough(self):
        f = JSONField()
        assert f.to_internal_value({"key": [1, 2]}) == {"key": [1, 2]}


class TestReadOnlyField:
    def test_read_only(self):
        f = ReadOnlyField()
        assert f.read_only is True


class TestHiddenField:
    def test_requires_default(self):
        with pytest.raises(AssertionError):
            HiddenField()

    def test_get_value(self):
        f = HiddenField(default="secret")
        assert f.get_value({}) == "secret"
