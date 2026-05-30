"""Tests for FakeDataService."""
import re

import pytest

from metaforge.fake import FakeDataService
from metaforge.metadata.loader import EntityModel, FieldDefinition, ValidationRules


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _field(
    name: str,
    ftype: str,
    *,
    primary_key: bool = False,
    read_only: bool = False,
    auto: str | None = None,
    options: list[dict] | None = None,
    validation: ValidationRules | None = None,
) -> FieldDefinition:
    return FieldDefinition(
        name=name,
        type=ftype,
        display_name=name.capitalize(),
        primary_key=primary_key,
        read_only=read_only,
        auto=auto,
        options=options,
        validation=validation or ValidationRules(),
    )


def _entity(*fields: FieldDefinition, name: str = "Widget") -> EntityModel:
    return EntityModel(
        name=name,
        display_name=name,
        plural_name=name + "s",
        primary_key="id",
        fields=list(fields),
        abbreviation="WGT",
    )


STATUS_OPTIONS = [
    {"value": "active", "label": "Active"},
    {"value": "inactive", "label": "Inactive"},
    {"value": "pending", "label": "Pending"},
]

TAGS_OPTIONS = [
    {"value": "alpha", "label": "Alpha"},
    {"value": "beta", "label": "Beta"},
    {"value": "gamma", "label": "Gamma"},
]


# ---------------------------------------------------------------------------
# Basic count and empty cases
# ---------------------------------------------------------------------------


class TestGenerateCount:
    def test_returns_requested_count(self):
        svc = FakeDataService()
        entity = _entity(_field("id", "id", primary_key=True), _field("title", "name"))
        records = svc.generate(entity, 5)
        assert len(records) == 5

    def test_zero_count_returns_empty_list(self):
        svc = FakeDataService()
        entity = _entity(_field("id", "id", primary_key=True))
        assert svc.generate(entity, 0) == []

    def test_each_record_is_a_dict(self):
        svc = FakeDataService()
        entity = _entity(_field("id", "id", primary_key=True), _field("label", "name"))
        for record in svc.generate(entity, 3):
            assert isinstance(record, dict)


# ---------------------------------------------------------------------------
# Field skipping rules
# ---------------------------------------------------------------------------


class TestFieldSkipping:
    def test_primary_key_field_excluded(self):
        svc = FakeDataService()
        entity = _entity(_field("id", "id", primary_key=True), _field("title", "name"))
        for record in svc.generate(entity, 3):
            assert "id" not in record

    def test_auto_field_excluded(self):
        svc = FakeDataService()
        entity = _entity(
            _field("id", "id", primary_key=True),
            _field("tenantId", "relation", auto="context.tenantId"),
            _field("createdAt", "datetime", auto="now"),
            _field("title", "name"),
        )
        for record in svc.generate(entity, 3):
            assert "tenantId" not in record
            assert "createdAt" not in record

    def test_read_only_field_excluded(self):
        svc = FakeDataService()
        entity = _entity(
            _field("id", "id", primary_key=True),
            _field("slug", "text", read_only=True),
            _field("title", "name"),
        )
        for record in svc.generate(entity, 3):
            assert "slug" not in record

    def test_relation_field_excluded(self):
        svc = FakeDataService()
        entity = _entity(
            _field("id", "id", primary_key=True),
            _field("companyId", "relation"),
            _field("title", "name"),
        )
        for record in svc.generate(entity, 3):
            assert "companyId" not in record

    def test_address_field_excluded(self):
        svc = FakeDataService()
        entity = _entity(
            _field("id", "id", primary_key=True),
            _field("mailingAddress", "address"),
            _field("title", "name"),
        )
        for record in svc.generate(entity, 3):
            assert "mailingAddress" not in record

    def test_attachment_field_excluded(self):
        svc = FakeDataService()
        entity = _entity(
            _field("id", "id", primary_key=True),
            _field("resume", "attachment"),
            _field("title", "name"),
        )
        for record in svc.generate(entity, 3):
            assert "resume" not in record


# ---------------------------------------------------------------------------
# Field type → value type assertions
# ---------------------------------------------------------------------------


class TestFieldTypes:
    def _single(self, ftype: str, **kwargs) -> object:
        svc = FakeDataService()
        entity = _entity(
            _field("id", "id", primary_key=True),
            _field("value", ftype, **kwargs),
        )
        return svc.generate(entity, 1)[0].get("value")

    def test_name_is_nonempty_string(self):
        v = self._single("name")
        assert isinstance(v, str) and len(v) > 0

    def test_text_is_nonempty_string(self):
        v = self._single("text")
        assert isinstance(v, str) and len(v) > 0

    def test_string_is_nonempty_string(self):
        v = self._single("string")
        assert isinstance(v, str) and len(v) > 0

    def test_description_is_nonempty_string(self):
        v = self._single("description")
        assert isinstance(v, str) and len(v) > 0

    def test_email_looks_like_email(self):
        v = self._single("email")
        assert isinstance(v, str) and "@" in v

    def test_phone_is_nonempty_string(self):
        v = self._single("phone")
        assert isinstance(v, str) and len(v) > 0

    def test_url_starts_with_http(self):
        v = self._single("url")
        assert isinstance(v, str) and v.startswith("http")

    def test_boolean_is_bool(self):
        v = self._single("boolean")
        assert isinstance(v, bool)

    def test_checkbox_is_bool(self):
        v = self._single("checkbox")
        assert isinstance(v, bool)

    def test_date_is_iso_date_string(self):
        v = self._single("date")
        assert isinstance(v, str)
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", v), f"Not an ISO date: {v!r}"

    def test_datetime_is_iso_datetime_string(self):
        v = self._single("datetime")
        assert isinstance(v, str) and "T" in v

    def test_currency_is_float(self):
        v = self._single("currency")
        assert isinstance(v, float)

    def test_percent_is_float_in_range(self):
        v = self._single("percent")
        assert isinstance(v, float)
        assert 0.0 <= v <= 100.0

    def test_number_is_int(self):
        v = self._single("number")
        assert isinstance(v, int)


# ---------------------------------------------------------------------------
# Picklist / multi-picklist
# ---------------------------------------------------------------------------


class TestPicklist:
    def test_picklist_value_in_options(self):
        svc = FakeDataService()
        entity = _entity(
            _field("id", "id", primary_key=True),
            _field("status", "picklist", options=STATUS_OPTIONS),
        )
        valid = {o["value"] for o in STATUS_OPTIONS}
        for record in svc.generate(entity, 10):
            assert record["status"] in valid

    def test_picklist_no_options_returns_string(self):
        svc = FakeDataService()
        entity = _entity(
            _field("id", "id", primary_key=True),
            _field("status", "picklist"),
        )
        for record in svc.generate(entity, 5):
            assert isinstance(record["status"], str)

    def test_multi_picklist_values_are_subset_of_options(self):
        svc = FakeDataService()
        entity = _entity(
            _field("id", "id", primary_key=True),
            _field("tags", "multi_picklist", options=TAGS_OPTIONS),
        )
        valid = {o["value"] for o in TAGS_OPTIONS}
        for record in svc.generate(entity, 10):
            assert isinstance(record["tags"], list)
            assert len(record["tags"]) >= 1
            assert set(record["tags"]).issubset(valid)

    def test_multi_picklist_no_options_returns_empty_list(self):
        svc = FakeDataService()
        entity = _entity(
            _field("id", "id", primary_key=True),
            _field("tags", "multi_picklist"),
        )
        for record in svc.generate(entity, 5):
            assert record["tags"] == []

    def test_multi_picklist_no_duplicates(self):
        svc = FakeDataService()
        entity = _entity(
            _field("id", "id", primary_key=True),
            _field("tags", "multi_picklist", options=TAGS_OPTIONS),
        )
        for record in svc.generate(entity, 20):
            tags = record["tags"]
            assert len(tags) == len(set(tags)), "duplicate values in multi_picklist"


# ---------------------------------------------------------------------------
# Validation constraint respect
# ---------------------------------------------------------------------------


class TestValidationConstraints:
    def test_number_respects_min_max(self):
        svc = FakeDataService()
        entity = _entity(
            _field("id", "id", primary_key=True),
            _field("score", "number", validation=ValidationRules(min=50, max=60)),
        )
        for record in svc.generate(entity, 20):
            assert 50 <= record["score"] <= 60

    def test_currency_respects_min_max(self):
        svc = FakeDataService()
        entity = _entity(
            _field("id", "id", primary_key=True),
            _field("price", "currency", validation=ValidationRules(min=10, max=20)),
        )
        for record in svc.generate(entity, 20):
            assert 10.0 <= record["price"] <= 20.0

    def test_text_respects_max_length(self):
        svc = FakeDataService()
        entity = _entity(
            _field("id", "id", primary_key=True),
            _field("code", "text", validation=ValidationRules(max_length=10)),
        )
        for record in svc.generate(entity, 10):
            assert len(record["code"]) <= 10

    def test_text_respects_min_length(self):
        svc = FakeDataService()
        entity = _entity(
            _field("id", "id", primary_key=True),
            _field("bio", "text", validation=ValidationRules(min_length=50)),
        )
        for record in svc.generate(entity, 5):
            assert len(record["bio"]) >= 50


# ---------------------------------------------------------------------------
# Locale parameter
# ---------------------------------------------------------------------------


class TestLocale:
    def test_default_locale_works(self):
        svc = FakeDataService()
        entity = _entity(_field("id", "id", primary_key=True), _field("name", "name"))
        records = svc.generate(entity, 3)
        assert len(records) == 3

    def test_explicit_locale_works(self):
        svc = FakeDataService()
        entity = _entity(_field("id", "id", primary_key=True), _field("name", "name"))
        records = svc.generate(entity, 3, locale="fr_FR")
        assert len(records) == 3

    def test_different_locales_produce_records(self):
        svc = FakeDataService()
        entity = _entity(_field("id", "id", primary_key=True), _field("email", "email"))
        for locale in ("en_US", "de_DE", "ja_JP"):
            records = svc.generate(entity, 2, locale=locale)
            assert len(records) == 2
            for r in records:
                assert "@" in r["email"]


# ---------------------------------------------------------------------------
# Entity with realistic mix of fields
# ---------------------------------------------------------------------------


class TestRealisticEntity:
    def _contact_entity(self) -> EntityModel:
        return _entity(
            _field("id", "id", primary_key=True),
            _field("tenantId", "relation", auto="context.tenantId", read_only=True),
            _field("createdAt", "datetime", auto="now", read_only=True),
            _field("fullName", "name"),
            _field("email", "email"),
            _field("phone", "phone"),
            _field("status", "picklist", options=STATUS_OPTIONS),
            _field("notes", "description"),
            _field("score", "number", validation=ValidationRules(min=0, max=100)),
            _field("companyId", "relation"),
            name="Contact",
        )

    def test_all_expected_keys_present(self):
        svc = FakeDataService()
        entity = self._contact_entity()
        record = svc.generate(entity, 1)[0]
        expected_keys = {"fullName", "email", "phone", "status", "notes", "score"}
        assert expected_keys.issubset(record.keys())

    def test_no_skipped_keys_present(self):
        svc = FakeDataService()
        entity = self._contact_entity()
        record = svc.generate(entity, 1)[0]
        skipped_keys = {"id", "tenantId", "createdAt", "companyId"}
        assert not skipped_keys.intersection(record.keys())

    def test_generates_multiple_distinct_records(self):
        svc = FakeDataService()
        entity = self._contact_entity()
        records = svc.generate(entity, 10)
        names = [r["fullName"] for r in records]
        # Not all names should be identical (extremely unlikely with faker)
        assert len(set(names)) > 1
