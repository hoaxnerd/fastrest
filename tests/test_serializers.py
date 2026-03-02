import pytest
from collections import OrderedDict

from fastrest.fields import CharField, IntegerField, FloatField, empty
from fastrest.serializers import Serializer, ModelSerializer, ListSerializer
from fastrest.exceptions import ValidationError


class SimpleSerializer(Serializer):
    name = CharField()
    age = IntegerField(required=False, default=0)


class TestSerializer:
    def test_valid_data(self):
        s = SimpleSerializer(data={"name": "Alice", "age": 25})
        assert s.is_valid() is True
        assert s.validated_data["name"] == "Alice"
        assert s.validated_data["age"] == 25

    def test_missing_required(self):
        s = SimpleSerializer(data={"age": 25})
        assert s.is_valid() is False
        assert "name" in s.errors

    def test_default_value(self):
        s = SimpleSerializer(data={"name": "Bob"})
        assert s.is_valid() is True
        assert s.validated_data["age"] == 0

    def test_raise_exception(self):
        s = SimpleSerializer(data={})
        with pytest.raises(ValidationError):
            s.is_valid(raise_exception=True)

    def test_representation(self):
        s = SimpleSerializer(instance={"name": "Alice", "age": 25})
        assert s.data["name"] == "Alice"
        assert s.data["age"] == 25

    def test_partial_update(self):
        s = SimpleSerializer(data={"age": 30}, partial=True)
        assert s.is_valid() is True
        assert "name" not in s.validated_data
        assert s.validated_data["age"] == 30

    def test_many(self):
        s = SimpleSerializer(
            instance=[{"name": "A", "age": 1}, {"name": "B", "age": 2}],
            many=True,
        )
        assert isinstance(s, ListSerializer)
        assert len(s.data) == 2

    def test_write_only_not_in_representation(self):
        class S(Serializer):
            name = CharField()
            password = CharField(write_only=True)

        s = S(instance={"name": "A", "password": "secret"})
        assert "password" not in s.data

    def test_read_only_not_validated(self):
        class S(Serializer):
            name = CharField()
            computed = CharField(read_only=True)

        s = S(data={"name": "A", "computed": "ignored"})
        assert s.is_valid() is True
        assert "computed" not in s.validated_data


class TestValidateHook:
    def test_validate_field_hook(self):
        class S(Serializer):
            name = CharField()

            def validate_name(self, value):
                if value == "bad":
                    raise ValidationError("Name cannot be 'bad'.")
                return value.upper()

        s = S(data={"name": "good"})
        assert s.is_valid() is True
        assert s.validated_data["name"] == "GOOD"

    def test_validate_field_hook_error(self):
        class S(Serializer):
            name = CharField()

            def validate_name(self, value):
                raise ValidationError("Always fails.")

        s = S(data={"name": "test"})
        assert s.is_valid() is False
        assert "name" in s.errors

    def test_validate_object_level(self):
        class S(Serializer):
            start = IntegerField()
            end = IntegerField()

            def validate(self, attrs):
                if attrs["start"] >= attrs["end"]:
                    raise ValidationError("start must be less than end")
                return attrs

        s = S(data={"start": 10, "end": 5})
        assert s.is_valid() is False


class TestModelSerializer:
    def test_auto_fields(self):
        from tests.conftest import Item

        class ItemSerializer(ModelSerializer):
            class Meta:
                model = Item
                fields = "__all__"

        s = ItemSerializer()
        field_names = list(s.fields.keys())
        assert "id" in field_names
        assert "name" in field_names
        assert "price" in field_names

    def test_pk_read_only(self):
        from tests.conftest import Item

        class ItemSerializer(ModelSerializer):
            class Meta:
                model = Item
                fields = "__all__"

        s = ItemSerializer()
        assert s.fields["id"].read_only is True

    def test_exclude(self):
        from tests.conftest import Item

        class ItemSerializer(ModelSerializer):
            class Meta:
                model = Item
                fields = "__all__"
                exclude = ["description"]

        s = ItemSerializer()
        assert "description" not in s.fields

    def test_validation(self):
        from tests.conftest import Item

        class ItemSerializer(ModelSerializer):
            class Meta:
                model = Item
                fields = ["name", "price"]

        s = ItemSerializer(data={"name": "Widget", "price": 9.99})
        assert s.is_valid() is True
