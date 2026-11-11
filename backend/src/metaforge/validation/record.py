"""Synchronous, database-free record validation for host applications (ADR-0015).

``validate_record`` runs the same steps as the server's save path (defaults,
auto fields, field rules, metadata validators, message interpolation) without
an event loop, a ``PersistenceAdapter`` or the server stack::

    from metaforge.metadata.loader import MetadataLoader
    from metaforge.validation import validate_record

    loader = MetadataLoader(entities_dir="schema")
    loader.load_all()
    result = validate_record(loader.get_entity("Vendor"), {"name": "Acme"})
    if not result.valid:
        for error in result.errors:
            print(error.field, error.message)

Validators that need data (``unique``, ``referenceExists``, ``noActiveChildren``)
call the host's ``query`` callback. Without one they are skipped, logged as a
warning and listed in ``RecordValidation.skipped``; they never fail the record.

Why it is sync without ``asyncio.run``: the validators are coroutines, but none
of them awaits anything except the query service, and here the query service
is a plain function. So each coroutine finishes on its first step and is driven
by hand. That works inside a host's running event loop too (a FastAPI
handler), where ``asyncio.run`` would refuse.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable, Coroutine, Sequence
from dataclasses import dataclass, field
from typing import Any

from metaforge.metadata.loader import EntityModel
from metaforge.validation.expressions.builtins import register_all_builtins
from metaforge.validation.integration import (
    create_message_interpolator,
    get_auto_fields,
    get_default_definitions,
    get_relation_validators,
    get_static_defaults,
    get_validator_definitions,
)
from metaforge.validation.registry import ValidatorRegistry
from metaforge.validation.services import DefaultingService
from metaforge.validation.types import (
    Operation,
    Severity,
    UserContext,
    ValidationContext,
    ValidationError,
    ValidationResult,
    ValidatorDefinition,
)
from metaforge.validation.validators import register_canned_validators
from metaforge.validation.validators.field_constraints import generate_field_validators

logger = logging.getLogger(__name__)

QueryCallback = Callable[[str, dict[str, Any], "str | None"], Sequence[dict[str, Any]]]
"""``query(entity, filter, tenant_id) -> matching records``.

``filter`` is MetaForge's validation filter, for example
``{"and": [{"field": "email", "op": "eq", "value": "a@b.co"},
{"field": "id", "op": "neq", "value": "VEN-1"}]}``. Ops used by the canned
validators are ``eq`` and ``neq``. ``tenant_id`` is set when a
validator is tenant-scoped and a ``user_context`` was given.
"""


@dataclass(frozen=True)
class SkippedValidator:
    """A validator that did not run, and why."""

    type: str
    field: str | None
    reason: str


@dataclass
class RecordValidation:
    """Outcome of ``validate_record``.

    ``record`` is the input with defaults and auto fields applied. ``validation``
    holds errors (block the save) and warnings (need acknowledgment), with
    messages interpolated. ``skipped`` lists validators that could not run.
    """

    record: dict[str, Any]
    validation: ValidationResult
    skipped: list[SkippedValidator] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return self.validation.valid

    @property
    def errors(self) -> list[ValidationError]:
        return self.validation.errors

    @property
    def warnings(self) -> list[ValidationError]:
        return self.validation.warnings


class _QueryUnavailable(Exception):
    """Raised by the stand-in query service when the host gave no callback."""


class AsyncQueryCallbackError(TypeError):
    """The host passed an async ``query`` callback to the sync entry point."""


class _CallbackQueryService:
    """Adapts a plain ``query`` callback to the async QueryService protocol."""

    def __init__(self, query: QueryCallback | None):
        self._query = query

    async def query(
        self, entity: str, filter: dict[str, Any], tenant_id: str | None = None
    ) -> list[dict[str, Any]]:
        if self._query is None:
            raise _QueryUnavailable(entity)
        rows = self._query(entity, filter, tenant_id)
        if inspect.isawaitable(rows):
            if inspect.iscoroutine(rows):
                rows.close()
            raise AsyncQueryCallbackError(
                "validate_record's query callback must be a plain function, "
                "not async; use EntityLifecycle for async data access"
            )
        return list(rows)

    async def exists(
        self, entity: str, filter: dict[str, Any], tenant_id: str | None = None
    ) -> bool:
        return len(await self.query(entity, filter, tenant_id)) > 0

    async def count(self, entity: str, filter: dict[str, Any], tenant_id: str | None = None) -> int:
        return len(await self.query(entity, filter, tenant_id))


def _run_sync(coro: Coroutine[Any, Any, Any]) -> Any:
    """Drive a coroutine that never suspends; fail clearly if it does."""
    try:
        coro.send(None)
    except StopIteration as done:
        return done.value
    coro.close()
    raise RuntimeError(
        "A validator awaited something that needs an event loop; "
        "validate_record supports only validators that await the query service"
    )


def _definition_field(definition: ValidatorDefinition) -> str | None:
    params = definition.params or {}
    if params.get("field"):
        return params["field"]
    fields = params.get("fields")
    if isinstance(fields, str):
        return fields
    if isinstance(fields, list) and fields:
        return fields[0]
    return None


def _ensure_registered() -> None:
    # Both are idempotent; hosts should not need a startup hook to validate.
    register_all_builtins()
    register_canned_validators()


def validate_record(
    entity: EntityModel,
    record: dict[str, Any],
    operation: Operation | str = Operation.CREATE,
    query: QueryCallback | None = None,
    *,
    original: dict[str, Any] | None = None,
    user_context: UserContext | None = None,
) -> RecordValidation:
    """Apply defaults and auto fields to ``record`` and validate it.

    Args:
        entity: The entity's metadata (``MetadataLoader.get_entity``).
        record: Field values. Not modified; the prepared copy is returned.
        operation: ``"create"``, ``"update"`` or ``"delete"`` (or ``Operation``).
            For an update, pass the full merged record and the stored one as
            ``original``, as the server does.
        query: Optional sync callback for data-dependent validators. See
            ``QueryCallback``. Without it those validators are skipped.
        original: The stored record, for updates (``original.x`` in rules,
            ``immutable`` validators).
        user_context: Tenant and user, for tenant-scoped checks and defaults
            that read ``currentUser``.

    Returns:
        ``RecordValidation`` with the prepared record, errors, warnings and
        any skipped validators.
    """
    _ensure_registered()
    op = operation if isinstance(operation, Operation) else Operation(operation)

    # Phase 1: defaults and auto fields (same order as EntityLifecycle.prepare)
    defaulting = DefaultingService(user_context)
    defaults = get_static_defaults(entity) + get_default_definitions(entity)
    prepared = defaulting.apply_defaults(dict(record), defaults, op, original)
    prepared = defaulting.apply_auto_fields(prepared, op, get_auto_fields(entity))

    ctx = ValidationContext(
        entity_name=entity.name,
        record=prepared,
        operation=op,
        user_context=user_context,
        original_record=original,
    )
    query_service = _CallbackQueryService(query)
    found: list[ValidationError] = []
    skipped: list[SkippedValidator] = []

    # Layer 0: field rules (required, formats, bounds, picklist values)
    for validator in generate_field_validators(entity.fields):
        try:
            found.extend(_run_sync(validator.validate(ctx, query_service)))
        except Exception as exc:  # mirror ValidationService: report, don't raise
            found.append(
                ValidationError(
                    message=f"Field validator error: {exc}",
                    code="FIELD_VALIDATOR_ERROR",
                    severity=Severity.ERROR,
                )
            )

    # Layers 1 and 2: metadata validators plus auto-generated relation checks
    definitions = get_validator_definitions(entity) + get_relation_validators(entity)
    for definition in definitions:
        if op not in definition.on:
            continue
        try:
            validator = ValidatorRegistry.create(definition)
        except ValueError:
            skipped.append(
                SkippedValidator(
                    type=definition.type,
                    field=_definition_field(definition),
                    reason="validator type is not registered",
                )
            )
            continue
        try:
            found.extend(_run_sync(validator.validate(ctx, query_service)))
        except _QueryUnavailable:
            skip = SkippedValidator(
                type=definition.type,
                field=_definition_field(definition),
                reason="needs data; no query callback given",
            )
            logger.warning(
                "Skipped %s validator on %s.%s: %s",
                skip.type,
                entity.name,
                skip.field,
                skip.reason,
            )
            skipped.append(skip)
        except AsyncQueryCallbackError:
            raise  # a misused callback is the host's bug, not a validation result
        except Exception as exc:
            found.append(
                ValidationError(
                    message=f"Validator error: {exc}",
                    code="VALIDATOR_ERROR",
                    severity=Severity.ERROR,
                )
            )

    interpolator = create_message_interpolator(entity)

    def interpolated(e: ValidationError) -> ValidationError:
        return ValidationError(
            message=interpolator.interpolate(e.message, prepared, original),
            code=e.code,
            field=e.field,
            severity=e.severity,
        )

    errors = [interpolated(e) for e in found if e.severity == Severity.ERROR]
    warnings = [interpolated(e) for e in found if e.severity == Severity.WARNING]
    return RecordValidation(
        record=prepared,
        validation=ValidationResult(valid=not errors, errors=errors, warnings=warnings),
        skipped=skipped,
    )
