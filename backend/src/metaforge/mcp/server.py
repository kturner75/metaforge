"""MetaForge MCP server — tool definitions for AI agents.

Tools are organized into three categories:
- Metadata discovery: list_entities, get_entity_metadata
- Read operations: query_records, get_record, aggregate_records, list/get_view_configs
- Write operations: create/update/delete_record, create/update_view_config
"""

from typing import Any

from fastmcp import FastMCP

from metaforge.mcp.bootstrap import MetaForgeServices, get_mcp_user_context, initialize_services
from metaforge.validation import Operation
from metaforge.views.types import (
    ConfigScope,
    ConfigSource,
    DataPattern,
    OwnerType,
    SavedConfig,
)

mcp = FastMCP(
    name="MetaForge",
    instructions=(
        "MetaForge is a metadata-driven framework for data-centric applications. "
        "Workflow: (1) call list_entities to discover entities, "
        "(2) call get_entity_metadata to understand fields/types/validation, "
        "(3) use query_records or aggregate_records to read data, "
        "(4) use create/update/delete_record to write data, "
        "(5) use create_view_config to build live dashboards and views.\n\n"
        "Filter format: {\"operator\": \"and\", \"conditions\": ["
        "{\"field\": \"status\", \"operator\": \"eq\", \"value\": \"active\"}]}\n"
        "Filter operators: eq, neq, gt, gte, lt, lte, in, notIn, contains, "
        "startsWith, isNull, isNotNull, between\n"
        "Sort format: [{\"field\": \"name\", \"direction\": \"asc\"}]\n"
        "Measure format: [{\"field\": \"id\", \"aggregate\": \"count\"}]\n"
        "Aggregates: count, sum, avg, min, max"
    ),
)

# Lazy-initialized services
_services: MetaForgeServices | None = None


def _get_services() -> MetaForgeServices:
    global _services
    if _services is None:
        _services = initialize_services()
    return _services


def _serialize_field(field) -> dict[str, Any]:
    """Serialize a FieldDefinition to a dict."""
    result: dict[str, Any] = {
        "name": field.name,
        "displayName": field.display_name,
        "type": field.type,
        "primaryKey": field.primary_key,
        "readOnly": field.read_only,
        "validation": {
            "required": field.validation.required,
            "min": field.validation.min,
            "max": field.validation.max,
            "minLength": field.validation.min_length,
            "maxLength": field.validation.max_length,
            "pattern": field.validation.pattern,
        },
        "options": field.options,
        "relation": {
            "entity": field.relation.entity,
            "displayField": field.relation.display_field,
            "onDelete": field.relation.on_delete,
        } if field.relation else None,
    }
    return result


def _apply_tenant_filter(
    entity_model, user_context, filter: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Inject tenant filter for tenant-scoped entities."""
    if entity_model.scope != "tenant" or not user_context or not user_context.tenant_id:
        return filter

    tenant_condition = {
        "field": "tenantId",
        "operator": "eq",
        "value": user_context.tenant_id,
    }
    if filter and "conditions" in filter:
        return {
            "operator": "and",
            "conditions": filter["conditions"] + [tenant_condition],
        }
    return {"conditions": [tenant_condition]}


# =============================================================================
# Metadata Discovery Tools
# =============================================================================


@mcp.tool()
def list_entities() -> list[dict[str, str]]:
    """List all available entities in MetaForge.

    Returns entity names, display names, and plural names.
    Call this first to discover what data is available.
    """
    svc = _get_services()
    result = []
    for name in svc.metadata_loader.list_entities():
        entity = svc.metadata_loader.get_entity(name)
        if entity:
            result.append({
                "name": entity.name,
                "displayName": entity.display_name,
                "pluralName": entity.plural_name,
            })
    return result


@mcp.tool()
def get_entity_metadata(entity: str) -> dict[str, Any]:
    """Get complete field definitions, validation rules, and relationships for an entity.

    Use this to understand what fields exist, their types, validation rules,
    picklist options, and relationships before querying or creating records.
    """
    svc = _get_services()
    entity_model = svc.metadata_loader.get_entity(entity)
    if not entity_model:
        return {"error": f"Entity '{entity}' not found"}

    fields = [_serialize_field(f) for f in entity_model.fields]
    return {
        "entity": entity_model.name,
        "displayName": entity_model.display_name,
        "pluralName": entity_model.plural_name,
        "primaryKey": entity_model.primary_key,
        "scope": entity_model.scope,
        "fields": fields,
    }


# =============================================================================
# Read Tools
# =============================================================================


@mcp.tool()
def query_records(
    entity: str,
    fields: list[str] | None = None,
    filter: dict[str, Any] | None = None,
    sort: list[dict[str, str]] | None = None,
    limit: int = 25,
    offset: int = 0,
) -> dict[str, Any]:
    """Query records with filtering, sorting, and pagination.

    Call get_entity_metadata first to know valid field names and types.

    Args:
        entity: Entity name (e.g. "Contact", "Company").
        fields: Optional list of field names to return. None returns all fields.
        filter: Optional filter. See server instructions for format.
        sort: Optional sort. Format: [{"field": "name", "direction": "asc"}]
        limit: Max records to return (default 25).
        offset: Number of records to skip for pagination.
    """
    svc = _get_services()
    entity_model = svc.metadata_loader.get_entity(entity)
    if not entity_model:
        return {"error": f"Entity '{entity}' not found"}

    user_context = get_mcp_user_context()
    effective_filter = _apply_tenant_filter(entity_model, user_context, filter)

    result = svc.db.query(
        entity_model,
        fields=fields,
        filter=effective_filter,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    result["data"] = svc.db.hydrate_relations(
        result["data"], entity_model, svc.metadata_loader
    )
    return result


@mcp.tool()
def get_record(entity: str, id: str) -> dict[str, Any]:
    """Get a single record by ID with hydrated relation display values.

    Args:
        entity: Entity name (e.g. "Contact").
        id: Record ID (e.g. "CON-00001").
    """
    svc = _get_services()
    entity_model = svc.metadata_loader.get_entity(entity)
    if not entity_model:
        return {"error": f"Entity '{entity}' not found"}

    record = svc.db.get(entity_model, id)
    if not record:
        return {"error": f"Record '{id}' not found in {entity}"}

    # Tenant isolation check
    user_context = get_mcp_user_context()
    if entity_model.scope == "tenant" and user_context and user_context.tenant_id:
        if record.get("tenantId") and record["tenantId"] != user_context.tenant_id:
            return {"error": f"Record '{id}' not found in {entity}"}

    hydrated = svc.db.hydrate_relations([record], entity_model, svc.metadata_loader)
    return {"data": hydrated[0] if hydrated else record}


@mcp.tool()
def aggregate_records(
    entity: str,
    group_by: list[str] | None = None,
    measures: list[dict[str, str]] | None = None,
    filter: dict[str, Any] | None = None,
    date_trunc: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Aggregate records with GROUP BY and aggregate functions.

    Args:
        entity: Entity name.
        group_by: Fields to group by (e.g. ["status"]).
        measures: Aggregate measures. Format: [{"field": "id", "aggregate": "count"}].
            Supported aggregates: count, sum, avg, min, max.
        filter: Optional filter (same format as query_records).
        date_trunc: Optional date bucketing. Format: {"createdAt": "month"}.
            Supported: day, week, month, year.
    """
    svc = _get_services()
    entity_model = svc.metadata_loader.get_entity(entity)
    if not entity_model:
        return {"error": f"Entity '{entity}' not found"}

    user_context = get_mcp_user_context()
    effective_filter = _apply_tenant_filter(entity_model, user_context, filter)

    try:
        return svc.db.aggregate(
            entity_model,
            group_by=group_by,
            measures=measures,
            filter=effective_filter,
            date_trunc=date_trunc,
        )
    except ValueError as e:
        return {"error": str(e)}


@mcp.tool()
def list_view_configs(
    entity_name: str | None = None,
    pattern: str | None = None,
    style: str | None = None,
) -> list[dict[str, Any]]:
    """List saved view/dashboard configurations.

    Args:
        entity_name: Filter by entity (e.g. "Contact").
        pattern: Filter by data pattern: query, aggregate, record, compose.
        style: Filter by style: grid, card-list, kanban, bar-chart, pie-chart, etc.
    """
    svc = _get_services()
    configs = svc.config_store.list(
        entity_name=entity_name,
        pattern=pattern,
        style=style,
    )
    return [c.to_dict() for c in configs]


@mcp.tool()
def get_view_config(config_id: str) -> dict[str, Any]:
    """Get a single view configuration by ID.

    Args:
        config_id: The config ID (e.g. "contact-grid" for YAML configs,
            or a UUID for user-created ones).
    """
    svc = _get_services()
    config = svc.config_store.get(config_id)
    if not config:
        return {"error": f"Config '{config_id}' not found"}
    return config.to_dict()


# =============================================================================
# Write Tools
# =============================================================================


@mcp.tool()
async def create_record(
    entity: str,
    data: dict[str, Any],
    acknowledge_token: str | None = None,
) -> dict[str, Any]:
    """Create a new record with full validation.

    Runs defaults, field constraints, and custom validators.
    If warnings are returned with requiresAcknowledgment=true, call again
    with the same data plus the acknowledgmentToken as acknowledge_token.

    Args:
        entity: Entity name (e.g. "Contact").
        data: Field values. Use get_entity_metadata to see required fields and valid values.
        acknowledge_token: Token from a previous call that returned warnings.
    """
    svc = _get_services()
    entity_model = svc.metadata_loader.get_entity(entity)
    if not entity_model:
        return {"error": f"Entity '{entity}' not found"}

    user_context = get_mcp_user_context()

    # Validation pipeline (same as app.py create_entity)
    validators = (
        svc.lifecycle_factory.get_validators(entity_model)
        + svc.lifecycle_factory.get_relation_validators(entity_model)
    )
    field_validators = svc.lifecycle_factory.get_field_validators(entity_model)
    defaults = (
        svc.lifecycle_factory.get_static_defaults(entity_model)
        + svc.lifecycle_factory.get_defaults(entity_model)
    )
    auto_fields = svc.lifecycle_factory.get_auto_fields(entity_model)

    lifecycle = svc.lifecycle_factory.create_lifecycle(entity_model, user_context)
    result = await lifecycle.prepare(
        record=data,
        operation=Operation.CREATE,
        entity_name=entity,
        defaults=defaults,
        auto_fields=auto_fields,
        validators=validators,
        user_context=user_context,
        field_validators=field_validators,
    )

    if not result.validation.valid:
        return {
            "valid": False,
            "errors": [e.to_dict() for e in result.validation.errors],
            "warnings": [w.to_dict() for w in result.validation.warnings],
        }

    if result.validation.warnings:
        if acknowledge_token:
            try:
                svc.acknowledgment_service.verify_token(
                    acknowledge_token, entity, result.record, result.validation.warnings
                )
            except Exception:
                return {
                    "valid": False,
                    "errors": [
                        {"message": "Please review the warnings again",
                         "code": "ACKNOWLEDGMENT_INVALID"},
                    ],
                    "warnings": [w.to_dict() for w in result.validation.warnings],
                }
        else:
            token = svc.acknowledgment_service.generate_token(
                entity, result.record, result.validation.warnings
            )
            return {
                "valid": True,
                "requiresAcknowledgment": True,
                "warnings": [w.to_dict() for w in result.validation.warnings],
                "acknowledgmentToken": token,
                "data": result.record,
            }

    tenant_id = user_context.tenant_id if user_context else None
    saved = svc.db.create(entity_model, result.record, tenant_id=tenant_id)
    return {"data": saved}


@mcp.tool()
async def update_record(
    entity: str,
    id: str,
    data: dict[str, Any],
    acknowledge_token: str | None = None,
) -> dict[str, Any]:
    """Update an existing record with validation.

    Only include fields you want to change; existing values are preserved.

    Args:
        entity: Entity name.
        id: Record ID to update.
        data: Fields to update. Omitted fields keep their current values.
        acknowledge_token: Token from a previous call that returned warnings.
    """
    svc = _get_services()
    entity_model = svc.metadata_loader.get_entity(entity)
    if not entity_model:
        return {"error": f"Entity '{entity}' not found"}

    original = svc.db.get(entity_model, id)
    if not original:
        return {"error": f"Record '{id}' not found in {entity}"}

    user_context = get_mcp_user_context()

    # Tenant isolation check
    if entity_model.scope == "tenant" and user_context and user_context.tenant_id:
        if original.get("tenantId") and original["tenantId"] != user_context.tenant_id:
            return {"error": f"Record '{id}' not found in {entity}"}

    # Merge original with updates
    merged_data = {**original, **data}

    validators = (
        svc.lifecycle_factory.get_validators(entity_model)
        + svc.lifecycle_factory.get_relation_validators(entity_model)
    )
    field_validators = svc.lifecycle_factory.get_field_validators(entity_model)
    defaults = svc.lifecycle_factory.get_defaults(entity_model)  # No static defaults on update
    auto_fields = svc.lifecycle_factory.get_auto_fields(entity_model)

    lifecycle = svc.lifecycle_factory.create_lifecycle(entity_model, user_context)
    result = await lifecycle.prepare(
        record=merged_data,
        operation=Operation.UPDATE,
        entity_name=entity,
        defaults=defaults,
        auto_fields=auto_fields,
        validators=validators,
        original=original,
        user_context=user_context,
        field_validators=field_validators,
    )

    if not result.validation.valid:
        return {
            "valid": False,
            "errors": [e.to_dict() for e in result.validation.errors],
            "warnings": [w.to_dict() for w in result.validation.warnings],
        }

    if result.validation.warnings:
        if acknowledge_token:
            try:
                svc.acknowledgment_service.verify_token(
                    acknowledge_token, entity, result.record, result.validation.warnings
                )
            except Exception:
                return {
                    "valid": False,
                    "errors": [
                        {"message": "Please review the warnings again",
                         "code": "ACKNOWLEDGMENT_INVALID"},
                    ],
                    "warnings": [w.to_dict() for w in result.validation.warnings],
                }
        else:
            token = svc.acknowledgment_service.generate_token(
                entity, result.record, result.validation.warnings
            )
            return {
                "valid": True,
                "requiresAcknowledgment": True,
                "warnings": [w.to_dict() for w in result.validation.warnings],
                "acknowledgmentToken": token,
                "data": result.record,
            }

    saved = svc.db.update(entity_model, id, result.record)
    return {"data": saved}


@mcp.tool()
async def delete_record(entity: str, id: str) -> dict[str, Any]:
    """Delete a record. May fail due to relation constraints.

    Args:
        entity: Entity name.
        id: Record ID to delete.
    """
    svc = _get_services()
    entity_model = svc.metadata_loader.get_entity(entity)
    if not entity_model:
        return {"error": f"Entity '{entity}' not found"}

    record = svc.db.get(entity_model, id)
    if not record:
        return {"error": f"Record '{id}' not found in {entity}"}

    user_context = get_mcp_user_context()

    # Tenant isolation check
    if entity_model.scope == "tenant" and user_context and user_context.tenant_id:
        if record.get("tenantId") and record["tenantId"] != user_context.tenant_id:
            return {"error": f"Record '{id}' not found in {entity}"}

    # Run delete validators
    all_validators = svc.lifecycle_factory.get_validators(entity_model)
    delete_validators = [v for v in all_validators if Operation.DELETE in v.on]

    if delete_validators:
        lifecycle = svc.lifecycle_factory.create_lifecycle(entity_model, user_context)
        result = await lifecycle.prepare(
            record=record,
            operation=Operation.DELETE,
            entity_name=entity,
            defaults=[],
            auto_fields={},
            validators=delete_validators,
            user_context=user_context,
        )
        if not result.validation.valid:
            return {
                "valid": False,
                "errors": [e.to_dict() for e in result.validation.errors],
            }

    # Handle relation constraints
    relation_errors = svc.db.handle_delete_relations(entity_model, id, svc.metadata_loader)
    if relation_errors:
        return {
            "valid": False,
            "errors": [
                {"message": msg, "code": "DELETE_RESTRICTED"}
                for msg in relation_errors
            ],
        }

    success = svc.db.delete(entity_model, id)
    if not success:
        return {"error": f"Record '{id}' not found in {entity}"}

    return {"success": True}


@mcp.tool()
def create_view_config(
    name: str,
    pattern: str,
    style: str,
    data_config: dict[str, Any],
    style_config: dict[str, Any],
    entity_name: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Create a new view configuration that renders immediately in the UI.

    This is the primary way AI agents create live dashboards, grids, charts, etc.

    Args:
        name: Human-readable name for the view.
        pattern: Data pattern — query, aggregate, record, or compose.
        style: Presentation style — grid, card-list, kanban, bar-chart, pie-chart,
            kpi-card, summary-grid, time-series, funnel, detail, form,
            dashboard, detail-page, search-list, tree, calendar.
        data_config: Data fetching configuration (entity, filter, sort, limit, etc.).
        style_config: Presentation configuration (columns, colors, layout, etc.).
        entity_name: Entity this view is for (e.g. "Contact").
        description: Optional description.
    """
    svc = _get_services()
    user_context = get_mcp_user_context()

    config = SavedConfig(
        id="",
        name=name,
        description=description,
        entity_name=entity_name,
        pattern=DataPattern(pattern),
        style=style,
        owner_type=OwnerType.GLOBAL,
        owner_id=None,
        tenant_id=user_context.tenant_id if user_context else None,
        scope=ConfigScope.GLOBAL,
        data_config=data_config,
        style_config=style_config,
        source=ConfigSource.DATABASE,
        created_by=user_context.user_id if user_context else None,
        updated_by=user_context.user_id if user_context else None,
    )
    created = svc.config_store.create(config)
    return created.to_dict()


@mcp.tool()
def update_view_config(
    config_id: str,
    name: str | None = None,
    description: str | None = None,
    data_config: dict[str, Any] | None = None,
    style_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Update an existing view configuration. Cannot modify YAML-sourced configs.

    Args:
        config_id: ID of the config to update.
        name: New name (optional).
        description: New description (optional).
        data_config: New data config (optional, replaces entire data_config).
        style_config: New style config (optional, replaces entire style_config).
    """
    svc = _get_services()
    existing = svc.config_store.get(config_id)
    if not existing:
        return {"error": f"Config '{config_id}' not found"}

    if existing.source == ConfigSource.YAML:
        return {"error": "Cannot modify YAML-sourced configs. Create a new config instead."}

    updates: dict[str, Any] = {}
    if name is not None:
        updates["name"] = name
    if description is not None:
        updates["description"] = description
    if data_config is not None:
        updates["data_config"] = data_config
    if style_config is not None:
        updates["style_config"] = style_config

    user_context = get_mcp_user_context()
    updates["updated_by"] = user_context.user_id if user_context else None

    updated = svc.config_store.update(config_id, updates)
    if not updated:
        return {"error": "Update failed"}

    return updated.to_dict()
