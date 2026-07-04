"""Tests for FakeDataService."""

import pytest

from metaforge.metadata.loader import (
    EntityModel,
    FieldDefinition,
    RelationConfig,
    ValidationRules,
)
from metaforge.sandbox.fake_data import FakeDataService
from metaforge.persistence.sqlite import SQLiteAdapter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _field(name: str, ftype: str, *, required: bool = False, **kwargs) -> FieldDefinition:
    validation = ValidationRules(required=required)
    return FieldDefinition(
        name=name,
        type=ftype,
        display_name=name.title(),
        validation=validation,
        **kwargs,
    )


def _entity(*fields: FieldDefinition, name: str = "Widget", abbrev: str = "WGT") -> EntityModel:
    id_field = FieldDefinition(name="id", type="id", display_name="ID", primary_key=True)
    return EntityModel(
        name=name,
        display_name=name,
        plural_name=name + "s",
        primary_key="id",
        fields=[id_field, *fields],
        abbreviation=abbrev,
    )


@pytest.fixture
def adapter(tmp_path):
    db = SQLiteAdapter(str(tmp_path / "test.db"))
    db.connect()
    yield db
    db.close()


@pytest.fixture
def svc() -> FakeDataService:
    return FakeDataService()


# ---------------------------------------------------------------------------
# Basic generation
# ---------------------------------------------------------------------------


class TestGenerateBasic:
    def test_returns_correct_count(self, adapter, svc):
        entity = _entity(_field("name", "name"))
        adapter.initialize_entity(entity)
        records = svc.generate(entity, count=5, adapter=adapter)
        assert len(records) == 5

    def test_returns_zero_for_count_zero(self, adapter, svc):
        entity = _entity(_field("name", "name"))
        adapter.initialize_entity(entity)
        records = svc.generate(entity, count=0, adapter=adapter)
        assert records == []

    def test_records_persisted_in_db(self, adapter, svc):
        entity = _entity(_field("name", "name"))
        adapter.initialize_entity(entity)
        svc.generate(entity, count=3, adapter=adapter)
        result = adapter.query(entity)
        assert result["pagination"]["total"] == 3

    def test_each_record_has_generated_id(self, adapter, svc):
        entity = _entity(_field("name", "name"))
        adapter.initialize_entity(entity)
        records = svc.generate(entity, count=2, adapter=adapter)
        for r in records:
            assert r["id"].startswith("WGT-")

    def test_ids_are_unique(self, adapter, svc):
        entity = _entity(_field("name", "name"))
        adapter.initialize_entity(entity)
        records = svc.generate(entity, count=10, adapter=adapter)
        ids = [r["id"] for r in records]
        assert len(set(ids)) == 10

    def test_seed_produces_reproducible_output(self, adapter, svc, tmp_path):
        entity = _entity(_field("name", "name"), _field("email", "email"))
        adapter.initialize_entity(entity)
        records_a = svc.generate(entity, count=3, adapter=adapter, seed=42)

        db2 = SQLiteAdapter(str(tmp_path / "test2.db"))
        db2.connect()
        entity2 = _entity(_field("name", "name"), _field("email", "email"))
        db2.initialize_entity(entity2)
        records_b = svc.generate(entity2, count=3, adapter=db2, seed=42)
        db2.close()

        names_a = [r["name"] for r in records_a]
        names_b = [r["name"] for r in records_b]
        assert names_a == names_b


# ---------------------------------------------------------------------------
# Field type coverage
# ---------------------------------------------------------------------------


class TestFieldTypes:
    def _make_and_generate(self, adapter, svc, *fields):
        entity = _entity(*fields)
        adapter.initialize_entity(entity)
        return svc.generate(entity, count=3, adapter=adapter, seed=1)

    def test_name_field(self, adapter, svc):
        records = self._make_and_generate(adapter, svc, _field("fullName", "name"))
        for r in records:
            assert isinstance(r["fullName"], str)
            assert len(r["fullName"]) > 0

    def test_text_field(self, adapter, svc):
        records = self._make_and_generate(adapter, svc, _field("notes", "text"))
        for r in records:
            assert isinstance(r["notes"], str)

    def test_description_field(self, adapter, svc):
        records = self._make_and_generate(adapter, svc, _field("bio", "description"))
        for r in records:
            assert isinstance(r["bio"], str)

    def test_email_field(self, adapter, svc):
        records = self._make_and_generate(adapter, svc, _field("email", "email"))
        for r in records:
            assert "@" in r["email"]

    def test_phone_field(self, adapter, svc):
        records = self._make_and_generate(adapter, svc, _field("phone", "phone"))
        for r in records:
            assert isinstance(r["phone"], str)
            assert len(r["phone"]) > 0

    def test_url_field(self, adapter, svc):
        records = self._make_and_generate(adapter, svc, _field("website", "url"))
        for r in records:
            assert r["website"].startswith("http")

    def test_number_field(self, adapter, svc):
        records = self._make_and_generate(adapter, svc, _field("count", "number"))
        for r in records:
            assert isinstance(r["count"], (int, float))

    def test_currency_field(self, adapter, svc):
        records = self._make_and_generate(adapter, svc, _field("amount", "currency"))
        for r in records:
            assert isinstance(r["amount"], (int, float))
            assert r["amount"] >= 0

    def test_percent_field(self, adapter, svc):
        records = self._make_and_generate(adapter, svc, _field("rate", "percent"))
        for r in records:
            assert isinstance(r["rate"], (int, float))

    def test_boolean_field(self, adapter, svc):
        records = self._make_and_generate(adapter, svc, _field("active", "boolean"))
        for r in records:
            assert r["active"] in (True, False, 0, 1)

    def test_checkbox_field(self, adapter, svc):
        records = self._make_and_generate(adapter, svc, _field("checked", "checkbox"))
        for r in records:
            assert r["checked"] in (True, False, 0, 1)

    def test_date_field(self, adapter, svc):
        records = self._make_and_generate(adapter, svc, _field("dob", "date"))
        for r in records:
            assert isinstance(r["dob"], str)
            parts = r["dob"].split("-")
            assert len(parts) == 3

    def test_datetime_field(self, adapter, svc):
        records = self._make_and_generate(adapter, svc, _field("createdAt", "datetime"))
        for r in records:
            assert isinstance(r["createdAt"], str)
            assert "T" in r["createdAt"] or "-" in r["createdAt"]

    def test_address_field(self, adapter, svc):
        records = self._make_and_generate(adapter, svc, _field("address", "address"))
        for r in records:
            assert isinstance(r["address"], str)
            assert len(r["address"]) > 5

    def test_attachment_field(self, adapter, svc):
        records = self._make_and_generate(adapter, svc, _field("file", "attachment"))
        for r in records:
            assert r["file"].startswith("/uploads/")


# ---------------------------------------------------------------------------
# Picklist fields
# ---------------------------------------------------------------------------


class TestPicklistFields:
    def test_picklist_picks_from_options(self, adapter, svc):
        field_def = _field("status", "picklist")
        field_def.options = [
            {"value": "active", "label": "Active"},
            {"value": "inactive", "label": "Inactive"},
            {"value": "pending", "label": "Pending"},
        ]
        entity = _entity(field_def)
        adapter.initialize_entity(entity)
        records = svc.generate(entity, count=10, adapter=adapter, seed=7)
        valid = {"active", "inactive", "pending"}
        for r in records:
            assert r["status"] in valid

    def test_picklist_without_options_omits_field(self, adapter, svc):
        field_def = _field("status", "picklist")
        field_def.options = None
        entity = _entity(field_def)
        adapter.initialize_entity(entity)
        records = svc.generate(entity, count=3, adapter=adapter)
        for r in records:
            assert "status" not in r or r.get("status") is None

    def test_multi_picklist_picks_from_options(self, adapter, svc):
        field_def = _field("tags", "multi_picklist")
        field_def.options = [
            {"value": "a", "label": "A"},
            {"value": "b", "label": "B"},
            {"value": "c", "label": "C"},
        ]
        entity = _entity(field_def)
        adapter.initialize_entity(entity)
        records = svc.generate(entity, count=5, adapter=adapter, seed=3)
        valid = {"a", "b", "c"}
        for r in records:
            choices = set(r["tags"].split(","))
            assert choices <= valid
            assert len(choices) >= 1


# ---------------------------------------------------------------------------
# Validation constraints
# ---------------------------------------------------------------------------


class TestValidationConstraints:
    def test_string_max_length_respected(self, adapter, svc):
        field_def = FieldDefinition(
            name="code",
            type="name",
            display_name="Code",
            validation=ValidationRules(max_length=5),
        )
        entity = _entity(field_def)
        adapter.initialize_entity(entity)
        records = svc.generate(entity, count=10, adapter=adapter, seed=99)
        for r in records:
            assert len(r["code"]) <= 5

    def test_number_min_max_respected(self, adapter, svc):
        field_def = FieldDefinition(
            name="score",
            type="number",
            display_name="Score",
            validation=ValidationRules(min=10.0, max=20.0),
        )
        entity = _entity(field_def)
        adapter.initialize_entity(entity)
        records = svc.generate(entity, count=10, adapter=adapter, seed=5)
        for r in records:
            assert 10.0 <= r["score"] <= 20.0


# ---------------------------------------------------------------------------
# Relation fields
# ---------------------------------------------------------------------------


class TestRelationFields:
    def test_relation_field_uses_provided_ids(self, adapter, svc, tmp_path):
        company_entity = EntityModel(
            name="Company",
            display_name="Company",
            plural_name="Companies",
            primary_key="id",
            fields=[
                FieldDefinition(name="id", type="id", display_name="ID", primary_key=True),
                FieldDefinition(name="name", type="name", display_name="Name"),
            ],
            abbreviation="CMP",
        )
        adapter.initialize_entity(company_entity)
        c1 = adapter.create(company_entity, {"name": "Acme"})
        c2 = adapter.create(company_entity, {"name": "Globex"})

        company_field = FieldDefinition(
            name="companyId",
            type="relation",
            display_name="Company",
            relation=RelationConfig(entity="Company", display_field="name"),
        )
        contact_entity = _entity(
            _field("fullName", "name"),
            company_field,
            name="Contact",
            abbrev="CON",
        )
        adapter.initialize_entity(contact_entity)

        relation_ids = {"Company": [c1["id"], c2["id"]]}
        records = svc.generate(
            contact_entity, count=5, adapter=adapter, relation_ids=relation_ids, seed=11
        )
        valid = {c1["id"], c2["id"]}
        for r in records:
            assert r["companyId"] in valid

    def test_relation_field_omitted_when_no_ids_provided(self, adapter, svc):
        company_field = FieldDefinition(
            name="companyId",
            type="relation",
            display_name="Company",
            relation=RelationConfig(entity="Company", display_field="name"),
        )
        entity = _entity(_field("fullName", "name"), company_field)
        adapter.initialize_entity(entity)
        records = svc.generate(entity, count=3, adapter=adapter)
        for r in records:
            assert "companyId" not in r or r.get("companyId") is None


# ---------------------------------------------------------------------------
# Skipped fields
# ---------------------------------------------------------------------------


class TestSkippedFields:
    def test_primary_key_not_in_payload(self, adapter, svc):
        entity = _entity(_field("name", "name"))
        adapter.initialize_entity(entity)
        records = svc.generate(entity, count=2, adapter=adapter)
        for r in records:
            assert r["id"].startswith("WGT-")

    def test_readonly_field_not_generated(self, adapter, svc):
        ro_field = FieldDefinition(
            name="computed",
            type="text",
            display_name="Computed",
            read_only=True,
        )
        entity = _entity(ro_field)
        adapter.initialize_entity(entity)
        records = svc.generate(entity, count=3, adapter=adapter)
        for r in records:
            assert r.get("computed") is None


# ---------------------------------------------------------------------------
# Locale support
# ---------------------------------------------------------------------------


class TestLocale:
    def test_non_default_locale_accepted(self, adapter, svc):
        entity = _entity(_field("name", "name"))
        adapter.initialize_entity(entity)
        records = svc.generate(entity, count=3, adapter=adapter, locale="de_DE")
        assert len(records) == 3

    def test_multiple_locales_produce_records(self, adapter, svc, tmp_path):
        entity = _entity(_field("name", "name"))
        adapter.initialize_entity(entity)
        for locale in ("en_US", "fr_FR", "ja_JP"):
            records = svc.generate(entity, count=2, adapter=adapter, locale=locale)
            assert len(records) == 2
