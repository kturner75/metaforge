"""Integration between metadata loader and validation system.

This module bridges the gap between:
- Metadata loader types (ValidatorConfig, DefaultConfig)
- Validation system types (ValidatorDefinition, DefaultDefinition)
- Persistence layer (PersistenceAdapter)
"""

from typing import Any

from metaforge.metadata.loader import (
    DefaultConfig,
    EntityModel,
    FieldDefinition,
    HookConfig,
    ValidatorConfig,
)
from metaforge.hooks.types import HookDefinition
from metaforge.persistence.adapter import PersistenceAdapter
from metaforge.validation.services import (
    DefaultDefinition,
    DefaultingService,
    DefaultPolicy,
    EntityLifecycle,
    MessageInterpolator,
    ValidationService,
)
from metaforge.validation.types import (
    Operation,
    QueryService,
    Severity,
    UserContext,
    ValidatorDefinition,
)
from metaforge.validation.validators.field_constraints import (
    FieldConstraintValidator,
    generate_field_validators,
)


# =============================================================================
# Type Converters
# =============================================================================


def validator_config_to_definition(config: ValidatorConfig) -> ValidatorDefinition:
    """Convert metadata ValidatorConfig to validation ValidatorDefinition."""
    return ValidatorDefinition(
        type=config.type,
        params=config.params,
        message=config.message,
        code=config.code,
        severity=Severity(config.severity),
        on=[Operation(op) for op in config.on],
        when=config.when,
    )


def default_config_to_definition(config: DefaultConfig) -> DefaultDefinition:
    """Convert metadata DefaultConfig to validation DefaultDefinition."""
    return DefaultDefinition(
        field=config.field,
        value=config.value,
        expression=config.expression,
        policy=DefaultPolicy(config.policy),
        when=config.when,
        on=[Operation(op) for op in config.on],
    )


def hook_config_to_definition(config: HookConfig) -> HookDefinition:
    """Convert metadata HookConfig to HookDefinition."""
    return HookDefinition(
        name=config.name,
        on=[Operation(op) for op in config.on],
        when=config.when,
        description=config.description,
    )


def get_auto_fields(entity: EntityModel) -> dict[str, str]:
    """Extract auto-populated field definitions from entity metadata."""
    auto_fields: dict[str, str] = {}
    for field in entity.fields:
        if field.auto:
            auto_fields[field.name] = field.auto
    return auto_fields


def get_field_labels(entity: EntityModel) -> dict[str, str]:
    """Extract field labels for message interpolation."""
    return {f.name: f.display_name for f in entity.fields}


def get_field_options(entity: EntityModel) -> dict[str, list[dict[str, str]]]:
    """Extract picklist options for message interpolation."""
    options: dict[str, list[dict[str, str]]] = {}
    for field in entity.fields:
        if field.options:
            options[field.name] = field.options
    return options


# =============================================================================
# QueryService Implementation
# =============================================================================


class AdapterQueryService:
    """QueryService implementation that wraps a PersistenceAdapter.

    This allows validators to query the database for uniqueness checks,
    reference validation, etc.
    """

    def __init__(self, adapter: PersistenceAdapter, metadata_loader: Any):
        self.adapter = adapter
        self.metadata_loader = metadata_loader

    async def query(
        self,
        entity: str,
        filter: dict[str, Any],
        tenant_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query records matching the filter."""
        entity_model = self.metadata_loader.get_entity(entity)
        if not entity_model:
            return []

        # Convert validation filter format to persistence filter format
        persistence_filter = self._convert_filter(filter, tenant_id, entity_model)

        result = self.adapter.query(
            entity_model,
            filter=persistence_filter,
        )
        return result.get("data", [])

    async def exists(
        self,
        entity: str,
        filter: dict[str, Any],
        tenant_id: str | None = None,
    ) -> bool:
        """Check if any record matches the filter."""
        results = await self.query(entity, filter, tenant_id)
        return len(results) > 0

    async def count(
        self,
        entity: str,
        filter: dict[str, Any],
        tenant_id: str | None = None,
    ) -> int:
        """Count records matching the filter."""
        results = await self.query(entity, filter, tenant_id)
        return len(results)

    def _convert_filter(
        self,
        filter: dict[str, Any],
        tenant_id: str | None,
        entity_model: EntityModel,
    ) -> dict[str, Any] | None:
        """Convert validation filter format to persistence filter format.

        Validation format: {"and": [{"field": "x", "op": "eq", "value": "y"}]}
        Persistence format: {"operator": "and", "conditions": [...]}
        """
        if not filter:
            return None

        conditions: list[dict[str, Any]] = []

        # Handle "and" filter
        if "and" in filter:
            for cond in filter["and"]:
                conditions.append({
                    "field": cond.get("field"),
                    "operator": cond.get("op"),
                    "value": cond.get("value"),
                })

        # Add tenant filter if entity is tenant-scoped
        if tenant_id and entity_model.scope == "tenant":
            # Check if entity has a tenantId field
            has_tenant_field = any(f.name == "tenantId" for f in entity_model.fields)
            if has_tenant_field:
                conditions.append({
                    "field": "tenantId",
                    "operator": "eq",
                    "value": tenant_id,
                })

        if not conditions:
            return None

        return {
            "operator": "and",
            "conditions": conditions,
        }


# =============================================================================
# Entity Lifecycle Factory
# =============================================================================


class EntityLifecycleFactory:
    """Factory for creating EntityLifecycle instances with proper configuration."""

    def __init__(
        self,
        adapter: PersistenceAdapter,
        metadata_loader: Any,
        secret_key: str = "default-secret-key-change-in-production",
    ):
        self.adapter = adapter
        self.metadata_loader = metadata_loader
        self.secret_key = secret_key
        self._query_service = AdapterQueryService(adapter, metadata_loader)

    def create_lifecycle(
        self,
        entity: EntityModel,
        user_context: UserContext | None = None,
    ) -> EntityLifecycle:
        """Create an EntityLifecycle configured for the given entity."""
        # Create message interpolator with field metadata
        interpolator = MessageInterpolator(
            field_labels=get_field_labels(entity),
            field_options=get_field_options(entity),
        )

        # Create services
        defaulting_service = DefaultingService(user_context)
        validation_service = ValidationService(self._query_service)

        return EntityLifecycle(
            defaulting_service=defaulting_service,
            validation_service=validation_service,
            message_interpolator=interpolator,
        )

    def get_validators(self, entity: EntityModel) -> list[ValidatorDefinition]:
        """Get validator definitions for an entity."""
        return [validator_config_to_definition(v) for v in entity.validators]

    def get_defaults(self, entity: EntityModel) -> list[DefaultDefinition]:
        """Get default definitions for an entity."""
        return [default_config_to_definition(d) for d in entity.defaults]

    def get_auto_fields(self, entity: EntityModel) -> dict[str, str]:
        """Get auto-populated field definitions."""
        return get_auto_fields(entity)

    def get_static_defaults(self, entity: EntityModel) -> list[DefaultDefinition]:
        """Get static defaults from field definitions."""
        defaults: list[DefaultDefinition] = []
        for field in entity.fields:
            if field.default is not None and not field.auto:
                defaults.append(
                    DefaultDefinition(
                        field=field.name,
                        value=field.default,
                        policy=DefaultPolicy.DEFAULT,
                        on=[Operation.CREATE],
                    )
                )
        return defaults

    def get_field_validators(
        self, entity: EntityModel
    ) -> list[FieldConstraintValidator]:
        """Get field constraint validators from field definitions.

        These validators (Layer 0) automatically enforce:
        - required fields
        - type-specific formats (email, phone, url)
        - numeric bounds (min/max)
        - string length (minLength/maxLength)
        - custom patterns
        - picklist valid values
        """
        return generate_field_validators(entity.fields)

    def get_relation_validators(
        self, entity: EntityModel
    ) -> list[ValidatorDefinition]:
        """Auto-generate FK validators for relation fields.

        For each relation field, generates a referenceExists validator
        to ensure the referenced entity exists.
        """
        validators: list[ValidatorDefinition] = []

        for field in entity.fields:
            if field.type == "relation" and field.relation:
                validators.append(
                    ValidatorDefinition(
                        type="referenceExists",
                        params={
                            "field": field.name,
                            "entity": field.relation.entity,
                        },
                        message=f"Referenced {field.relation.entity} not found",
                        code="REFERENCE_NOT_FOUND",
                        severity=Severity.ERROR,
                        on=[Operation.CREATE, Operation.UPDATE],
                    )
                )

        return validators

    def get_hook_definitions(
        self, entity: EntityModel, hook_point: str
    ) -> list[HookDefinition]:
        """Get hook definitions for an entity at a specific hook point.

        Args:
            entity: The entity model
            hook_point: One of beforeSave, afterSave, afterCommit, beforeDelete

        Returns:
            List of HookDefinition for the given hook point (empty if none declared)
        """
        hook_configs = entity.hooks.get(hook_point, [])
        return [hook_config_to_definition(h) for h in hook_configs]


# Backward-compat alias
SQLiteQueryService = AdapterQueryService
