"""Fake data generation for draft entities."""
from __future__ import annotations

from typing import Any

from faker import Faker

from metaforge.metadata.loader import EntityModel, FieldDefinition

_SKIP_TYPES = frozenset({"id", "relation", "address", "attachment"})


class FakeDataService:
    """Generate realistic fake records shaped to a MetaForge entity's field definitions."""

    def generate(
        self, entity: EntityModel, count: int, locale: str = "en_US"
    ) -> list[dict[str, Any]]:
        """Return `count` fake records for `entity`, each as a field-name → value dict.

        Skips primary-key, auto-filled, and read-only fields.
        Relation/address/attachment fields are omitted.
        """
        fake = Faker(locale)
        return [self._record(entity, fake) for _ in range(count)]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _record(self, entity: EntityModel, fake: Faker) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for field in entity.fields:
            if self._skip(field):
                continue
            value = self._value(field, fake)
            if value is not None:
                result[field.name] = value
        return result

    def _skip(self, field: FieldDefinition) -> bool:
        return field.primary_key or field.auto is not None or field.read_only

    def _value(self, field: FieldDefinition, fake: Faker) -> Any:
        ft = field.type
        v = field.validation

        if ft in _SKIP_TYPES:
            return None
        if ft == "name":
            return fake.name()
        if ft in ("text", "string"):
            return self._bounded_text(fake, v.min_length, v.max_length)
        if ft == "description":
            return fake.paragraph(nb_sentences=3)
        if ft == "email":
            return fake.email()
        if ft == "phone":
            return fake.phone_number()
        if ft == "url":
            return fake.url()
        if ft in ("boolean", "checkbox"):
            return fake.boolean()
        if ft == "picklist":
            return self._pick_one(field, fake)
        if ft == "multi_picklist":
            return self._pick_many(field, fake)
        if ft == "date":
            return fake.date_between(start_date="-2y", end_date="today").isoformat()
        if ft == "datetime":
            return fake.date_time_between(start_date="-2y", end_date="now").isoformat()
        if ft == "currency":
            lo = float(v.min) if v.min is not None else 0.0
            hi = float(v.max) if v.max is not None else 100_000.0
            return round(fake.pyfloat(min_value=lo, max_value=hi), 2)
        if ft == "percent":
            return round(fake.pyfloat(min_value=0.0, max_value=100.0), 1)
        if ft == "number":
            lo = int(v.min) if v.min is not None else 0
            hi = int(v.max) if v.max is not None else 1_000
            return fake.random_int(min=lo, max=hi)
        # Unknown type — fall back to a single word so the record is never missing
        # a field that might be required.
        return fake.word()

    def _bounded_text(
        self, fake: Faker, min_length: int | None, max_length: int | None
    ) -> str:
        upper = max_length if max_length is not None else 200
        # faker.text returns up to max_nb_chars; ensure it's at least 5 chars
        text = fake.text(max_nb_chars=max(upper, 5))
        # Pad if a minimum length is required
        if min_length and len(text) < min_length:
            while len(text) < min_length:
                text += " " + fake.word()
        # Hard-trim to honour max_length
        if max_length and len(text) > max_length:
            text = text[:max_length]
        return text.strip()

    def _pick_one(self, field: FieldDefinition, fake: Faker) -> str | None:
        if not field.options:
            return fake.word()
        return fake.random_element([opt["value"] for opt in field.options])

    def _pick_many(self, field: FieldDefinition, fake: Faker) -> list[str]:
        if not field.options:
            return []
        values = [opt["value"] for opt in field.options]
        k = fake.random_int(min=1, max=len(values))
        return list(fake.random_elements(elements=values, length=k, unique=True))
