"""Fake data generator for MetaForge entities.

Generates realistic fake records for any entity defined in metadata, respecting
field types, picklist options, and validation constraints (min/max, min_length/max_length).

Usage::

    from metaforge.sandbox.fake_data import FakeDataService

    svc = FakeDataService()
    records = svc.generate(entity, count=20, adapter=draft_db, tenant_id="T-00001")

Relation fields are handled via the optional ``relation_ids`` parameter — a mapping
of ``{EntityName: [id1, id2, ...]}`` that the generator randomly samples from.
Fields whose relation entity is absent from the mapping are skipped (left out of the
payload so the adapter omits them from the INSERT rather than inserting NULL, which
would fail NOT NULL constraints on required FK columns).
"""

from __future__ import annotations

import random
from typing import Any

from faker import Faker

from metaforge.metadata.loader import EntityModel, FieldDefinition
from metaforge.persistence.adapter import PersistenceAdapter

# Field types that carry no user-supplied data — the adapter/sequencer owns them.
_SKIP_TYPES = frozenset({"id", "uuid"})

# Field types that are auto-populated by the adapter (audit columns, tenant FK).
_AUTO_VALUES = frozenset({"now", "context.userId", "context.tenantId"})


def _clamp_str(value: str, min_length: int | None, max_length: int | None) -> str:
    """Ensure string satisfies length constraints by truncating or padding."""
    if max_length is not None and len(value) > max_length:
        value = value[:max_length]
    if min_length is not None and len(value) < min_length:
        value = value.ljust(min_length)
    return value


def _clamp_num(
    value: float,
    min_val: float | None,
    max_val: float | None,
) -> float:
    if min_val is not None:
        value = max(value, min_val)
    if max_val is not None:
        value = min(value, max_val)
    return value


class FakeDataService:
    """Generate and insert fake records for MetaForge entities.

    A single service instance is reusable across multiple ``generate()`` calls.
    Each call creates its own ``Faker`` instance so locale and seed are isolated.
    """

    def generate(
        self,
        entity: EntityModel,
        count: int,
        adapter: PersistenceAdapter,
        *,
        tenant_id: str | None = None,
        locale: str = "en_US",
        relation_ids: dict[str, list[str]] | None = None,
        seed: int | None = None,
    ) -> list[dict[str, Any]]:
        """Generate ``count`` fake records for ``entity`` and insert them via ``adapter``.

        Args:
            entity: The entity to generate records for.
            count: Number of records to create.
            adapter: Persistence adapter to insert into (draft or live DB).
            tenant_id: Tenant scope for the records (required for tenant-scoped entities).
            locale: Faker locale string, e.g. ``"en_US"``, ``"de_DE"``.
            relation_ids: Maps related entity names to lists of existing IDs that
                relation fields may reference.  E.g.
                ``{"Company": ["CMP-00001", "CMP-00002"]}``.
            seed: Optional integer seed for reproducible output.

        Returns:
            List of created records as returned by the adapter (includes generated IDs).
        """
        if count <= 0:
            return []

        faker = Faker(locale)
        if seed is not None:
            Faker.seed(seed)
            random.seed(seed)

        created: list[dict[str, Any]] = []
        for _ in range(count):
            data = self._build_record(entity, faker, relation_ids or {})
            record = adapter.create(entity, data, tenant_id)
            created.append(record)

        return created

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_record(
        self,
        entity: EntityModel,
        faker: Faker,
        relation_ids: dict[str, list[str]],
    ) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for field_def in entity.fields:
            if self._should_skip(field_def):
                continue
            value = self._generate_value(field_def, faker, relation_ids)
            if value is not None:
                data[field_def.name] = value
        return data

    @staticmethod
    def _should_skip(field_def: FieldDefinition) -> bool:
        """Return True for fields whose value is owned by the adapter/sequencer."""
        if field_def.primary_key:
            return True
        if field_def.type in _SKIP_TYPES:
            return True
        if field_def.auto and field_def.auto in _AUTO_VALUES:
            return True
        if field_def.read_only:
            return True
        return False

    def _generate_value(
        self,
        field_def: FieldDefinition,
        faker: Faker,
        relation_ids: dict[str, list[str]],
    ) -> Any:
        ft = field_def.type
        v = field_def.validation

        if ft == "name":
            return _clamp_str(faker.name(), v.min_length, v.max_length)

        if ft in ("text", "string"):
            return _clamp_str(faker.sentence(nb_words=6), v.min_length, v.max_length)

        if ft == "description":
            return _clamp_str(faker.paragraph(nb_sentences=3), v.min_length, v.max_length)

        if ft == "email":
            return faker.email()

        if ft == "phone":
            return faker.phone_number()

        if ft == "url":
            return faker.url()

        if ft in ("number", "percent"):
            lo = v.min if v.min is not None else 0.0
            hi = v.max if v.max is not None else 1000.0
            lo, hi = float(lo), float(hi)
            raw = faker.pyfloat(min_value=lo, max_value=hi, right_digits=2)
            return _clamp_num(raw, lo, hi)

        if ft == "currency":
            lo = v.min if v.min is not None else 0.0
            hi = v.max if v.max is not None else 100_000.0
            lo, hi = float(lo), float(hi)
            raw = faker.pyfloat(min_value=lo, max_value=hi, right_digits=2)
            return round(_clamp_num(raw, lo, hi), 2)

        if ft in ("boolean", "checkbox"):
            return faker.pybool()

        if ft == "date":
            return faker.date()

        if ft == "datetime":
            return faker.iso8601()

        if ft == "picklist":
            if field_def.options:
                return faker.random_element([o["value"] for o in field_def.options])
            return None

        if ft == "multi_picklist":
            if field_def.options:
                all_values = [o["value"] for o in field_def.options]
                k = random.randint(1, min(3, len(all_values)))
                choices = random.sample(all_values, k)
                return ",".join(choices)
            return None

        if ft == "relation":
            if field_def.relation:
                ids = relation_ids.get(field_def.relation.entity, [])
                if ids:
                    return faker.random_element(ids)
            return None

        if ft == "address":
            return (
                f"{faker.street_address()}, "
                f"{faker.city()}, "
                f"{faker.state_abbr()} {faker.postcode()}"
            )

        if ft == "attachment":
            return f"/uploads/{faker.uuid4()}/{faker.file_name()}"

        return None
