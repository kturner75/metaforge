"""FastAPI application."""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from metaforge.metadata.loader import MetadataLoader
from metaforge.persistence.sqlite import SQLiteAdapter
from metaforge.core.types import get_field_type
from metaforge.validation import (
    Operation,
    Severity,
    UserContext,
    WarningAcknowledgmentService,
    register_all_builtins,
    register_canned_validators,
)
from metaforge.validation.integration import EntityLifecycleFactory
from metaforge.auth import (
    AuthMiddleware,
    JWTService,
    PasswordService,
    get_user_context,
    can_access_entity,
)
from metaforge.auth.endpoints import create_auth_router
from metaforge.views import SavedConfigStore, ViewConfigLoader
from metaforge.views.endpoints import create_views_router


# Global instances (initialized on startup)
metadata_loader: MetadataLoader | None = None
db: SQLiteAdapter | None = None
lifecycle_factory: EntityLifecycleFactory | None = None
acknowledgment_service: WarningAcknowledgmentService | None = None
jwt_service: JWTService | None = None
password_service: PasswordService | None = None
config_store: SavedConfigStore | None = None
view_loader: ViewConfigLoader | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize on startup, cleanup on shutdown."""
    global metadata_loader, db, lifecycle_factory, acknowledgment_service, jwt_service, password_service, config_store, view_loader

    # Register validation functions and validators
    register_all_builtins()
    register_canned_validators()

    # Find metadata path (relative to cwd, which should be /backend)
    cwd = Path.cwd()
    if cwd.name == "backend":
        base_path = cwd.parent
    else:
        base_path = cwd
    metadata_path = base_path / "metadata"

    # Initialize metadata loader
    metadata_loader = MetadataLoader(metadata_path)
    metadata_loader.load_all()

    # Initialize database (allow override via environment variable for testing)
    db_path_str = os.environ.get("METAFORGE_DB_PATH")
    if db_path_str:
        db_path = Path(db_path_str)
    else:
        db_path = base_path / "data" / "metaforge.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    db = SQLiteAdapter(db_path)
    db.connect()

    # Create tables for all entities
    for entity_name in metadata_loader.list_entities():
        entity = metadata_loader.get_entity(entity_name)
        if entity:
            db.initialize_entity(entity)

    # Initialize validation lifecycle factory
    secret_key = os.environ.get("METAFORGE_SECRET_KEY", "dev-secret-key-change-in-production")
    lifecycle_factory = EntityLifecycleFactory(db, metadata_loader, secret_key)
    acknowledgment_service = WarningAcknowledgmentService(secret_key)

    # Initialize view configuration system
    config_store = SavedConfigStore(db.conn)
    view_loader = ViewConfigLoader(metadata_path / "views")
    view_loader.load_all()
    for cfg in view_loader.list_configs():
        config_store.upsert_from_yaml(cfg)

    views_router = create_views_router(
        get_config_store=lambda: config_store,
        get_view_loader=lambda: view_loader,
    )
    app.include_router(views_router)

    # Initialize auth services (can be disabled via environment variable for testing)
    if os.environ.get("METAFORGE_DISABLE_AUTH", "").lower() not in ("1", "true", "yes"):
        jwt_service = JWTService(secret_key)
        password_service = PasswordService()

        # Include auth router
        auth_router = create_auth_router(
            jwt_service=jwt_service,
            password_service=password_service,
            get_db=lambda: db,
            get_metadata_loader=lambda: metadata_loader,
        )
        app.include_router(auth_router)

    yield

    # Cleanup
    if db:
        db.close()


app = FastAPI(title="MetaForge API", lifespan=lifespan)

# CORS for frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Auth Middleware (uses global jwt_service) ---


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Extract JWT from Authorization header and set user context."""
    from metaforge.validation import UserContext as ValidationUserContext

    # Initialize to unauthenticated
    request.state.user_context = None
    request.state.token_claims = None

    # Skip if jwt_service not initialized or for auth endpoints
    if not jwt_service:
        return await call_next(request)

    skip_paths = ["/api/auth/login", "/api/auth/refresh", "/docs", "/openapi.json", "/redoc"]
    if any(request.url.path.startswith(p) for p in skip_paths):
        return await call_next(request)

    # Try to extract and validate token
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            from metaforge.auth.jwt_service import JWTError

            claims = jwt_service.decode_token(token)
            if claims.type == "access":
                request.state.token_claims = claims
                request.state.user_context = ValidationUserContext(
                    user_id=claims.user_id,
                    tenant_id=claims.tenant_id,
                    roles=[claims.role] if claims.role else [],
                )
        except Exception:
            pass  # Invalid token - leave user_context as None

    return await call_next(request)


# Helper functions for dependency injection in auth endpoints
def _get_db():
    return db


def _get_metadata_loader():
    return metadata_loader


# --- Metadata Endpoints ---


@app.get("/api/metadata")
async def list_entities() -> dict[str, Any]:
    """List all available entities."""
    if not metadata_loader:
        raise HTTPException(500, "Metadata loader not initialized")

    entities = []
    for name in metadata_loader.list_entities():
        entity = metadata_loader.get_entity(name)
        if entity:
            entities.append({
                "name": entity.name,
                "displayName": entity.display_name,
                "pluralName": entity.plural_name,
            })

    return {"entities": entities}


@app.get("/api/metadata/{entity}")
async def get_entity_metadata(entity: str) -> dict[str, Any]:
    """Get full metadata for an entity."""
    if not metadata_loader:
        raise HTTPException(500, "Metadata loader not initialized")

    entity_model = metadata_loader.get_entity(entity)
    if not entity_model:
        raise HTTPException(404, f"Entity '{entity}' not found")

    # Build field metadata with UI config
    fields = []
    for field in entity_model.fields:
        field_type = get_field_type(field.type)

        field_meta = {
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
            "ui": {
                "display": {
                    "component": field_type.ui.display_component,
                    "format": field_type.ui.format,
                },
                "edit": {
                    "component": field_type.ui.edit_component,
                },
                "filter": {
                    "component": field_type.ui.filter_component,
                    "operator": field_type.ui.filter_operator,
                },
                "grid": {
                    "component": field_type.ui.grid_component,
                    "alignment": field_type.ui.alignment,
                },
            },
        }
        fields.append(field_meta)

    return {
        "entity": entity_model.name,
        "displayName": entity_model.display_name,
        "pluralName": entity_model.plural_name,
        "primaryKey": entity_model.primary_key,
        "fields": fields,
    }


# --- CRUD Endpoints ---


class CreateRequest(BaseModel):
    """Request body for create operations."""
    data: dict[str, Any]
    acknowledgeWarnings: str | None = None


class UpdateRequest(BaseModel):
    """Request body for update operations."""
    data: dict[str, Any]
    acknowledgeWarnings: str | None = None


@app.post("/api/entities/{entity}")
async def create_entity(entity: str, request: CreateRequest, http_request: Request):
    """Create a new record with validation."""
    if not metadata_loader or not db or not lifecycle_factory or not acknowledgment_service:
        raise HTTPException(500, "Not initialized")

    entity_model = metadata_loader.get_entity(entity)
    if not entity_model:
        raise HTTPException(404, f"Entity '{entity}' not found")

    # Get user context from authentication middleware
    user_context = get_user_context(http_request)

    # Check permissions (auth required only if jwt_service is configured)
    allowed, error_msg = can_access_entity(
        entity_model.name, entity_model.scope, "create", user_context,
        auth_required=jwt_service is not None,
    )
    if not allowed:
        raise HTTPException(403, error_msg)

    # Get validation configuration
    validators = (
        lifecycle_factory.get_validators(entity_model)
        + lifecycle_factory.get_relation_validators(entity_model)
    )
    field_validators = lifecycle_factory.get_field_validators(entity_model)
    defaults = lifecycle_factory.get_static_defaults(entity_model) + lifecycle_factory.get_defaults(entity_model)
    auto_fields = lifecycle_factory.get_auto_fields(entity_model)

    # Run lifecycle (defaults + validation)
    lifecycle = lifecycle_factory.create_lifecycle(entity_model, user_context)
    result = await lifecycle.prepare(
        record=request.data,
        operation=Operation.CREATE,
        entity_name=entity,
        defaults=defaults,
        auto_fields=auto_fields,
        validators=validators,
        user_context=user_context,
        field_validators=field_validators,
    )

    # Handle validation errors
    if not result.validation.valid:
        return JSONResponse(
            status_code=422,
            content={
                "valid": False,
                "errors": [e.to_dict() for e in result.validation.errors],
                "warnings": [w.to_dict() for w in result.validation.warnings],
            },
        )

    # Handle warnings requiring acknowledgment
    if result.validation.warnings:
        if request.acknowledgeWarnings:
            # Verify acknowledgment token
            try:
                acknowledgment_service.verify_token(
                    request.acknowledgeWarnings,
                    entity,
                    result.record,
                    result.validation.warnings,
                )
            except Exception:
                return JSONResponse(
                    status_code=422,
                    content={
                        "valid": False,
                        "errors": [{
                            "message": "Please review the warnings again",
                            "code": "ACKNOWLEDGMENT_INVALID",
                            "severity": "error",
                        }],
                        "warnings": [w.to_dict() for w in result.validation.warnings],
                    },
                )
        else:
            # Generate acknowledgment token and return warnings with processed record
            token = acknowledgment_service.generate_token(
                entity,
                result.record,
                result.validation.warnings,
            )
            return JSONResponse(
                status_code=202,
                content={
                    "valid": True,
                    "requiresAcknowledgment": True,
                    "warnings": [w.to_dict() for w in result.validation.warnings],
                    "acknowledgmentToken": token,
                    "data": result.record,  # Include processed record for resubmission
                },
            )

    # Validation passed, persist (pass tenant_id for sequence scoping)
    tenant_id = user_context.tenant_id if user_context else None
    saved = db.create(entity_model, result.record, tenant_id=tenant_id)
    return JSONResponse(
        status_code=201,
        content={"data": saved},
    )


@app.get("/api/entities/{entity}/{id}")
async def get_entity(entity: str, id: str, http_request: Request) -> dict[str, Any]:
    """Get a single record."""
    if not metadata_loader or not db:
        raise HTTPException(500, "Not initialized")

    entity_model = metadata_loader.get_entity(entity)
    if not entity_model:
        raise HTTPException(404, f"Entity '{entity}' not found")

    # Get user context from authentication middleware
    user_context = get_user_context(http_request)

    # Check permissions
    allowed, error_msg = can_access_entity(
        entity_model.name, entity_model.scope, "read", user_context,
        auth_required=jwt_service is not None,
    )
    if not allowed:
        raise HTTPException(403, error_msg)

    result = db.get(entity_model, id)
    if not result:
        raise HTTPException(404, "Record not found")

    # For tenant-scoped entities, verify record belongs to user's tenant
    if entity_model.scope == "tenant" and user_context and user_context.tenant_id:
        record_tenant = result.get("tenantId")
        if record_tenant and record_tenant != user_context.tenant_id:
            raise HTTPException(404, "Record not found")

    # Hydrate relation display values
    hydrated = db.hydrate_relations([result], entity_model, metadata_loader)
    return {"data": hydrated[0] if hydrated else result}


@app.put("/api/entities/{entity}/{id}")
async def update_entity(entity: str, id: str, request: UpdateRequest, http_request: Request):
    """Update a record with validation."""
    if not metadata_loader or not db or not lifecycle_factory or not acknowledgment_service:
        raise HTTPException(500, "Not initialized")

    entity_model = metadata_loader.get_entity(entity)
    if not entity_model:
        raise HTTPException(404, f"Entity '{entity}' not found")

    # Get user context from authentication middleware
    user_context = get_user_context(http_request)

    # Check permissions
    allowed, error_msg = can_access_entity(
        entity_model.name, entity_model.scope, "update", user_context,
        auth_required=jwt_service is not None,
    )
    if not allowed:
        raise HTTPException(403, error_msg)

    # Get original record
    original = db.get(entity_model, id)
    if not original:
        raise HTTPException(404, "Record not found")

    # For tenant-scoped entities, verify record belongs to user's tenant
    if entity_model.scope == "tenant" and user_context and user_context.tenant_id:
        record_tenant = original.get("tenantId")
        if record_tenant and record_tenant != user_context.tenant_id:
            raise HTTPException(404, "Record not found")

    # Get validation configuration
    validators = (
        lifecycle_factory.get_validators(entity_model)
        + lifecycle_factory.get_relation_validators(entity_model)
    )
    field_validators = lifecycle_factory.get_field_validators(entity_model)
    defaults = lifecycle_factory.get_defaults(entity_model)  # No static defaults on update
    auto_fields = lifecycle_factory.get_auto_fields(entity_model)

    # Merge original with updates (keep original values for fields not in request)
    merged_data = {**original, **request.data}

    # Run lifecycle
    lifecycle = lifecycle_factory.create_lifecycle(entity_model, user_context)
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

    # Handle validation errors
    if not result.validation.valid:
        return JSONResponse(
            status_code=422,
            content={
                "valid": False,
                "errors": [e.to_dict() for e in result.validation.errors],
                "warnings": [w.to_dict() for w in result.validation.warnings],
            },
        )

    # Handle warnings requiring acknowledgment
    if result.validation.warnings:
        if request.acknowledgeWarnings:
            try:
                acknowledgment_service.verify_token(
                    request.acknowledgeWarnings,
                    entity,
                    result.record,
                    result.validation.warnings,
                )
            except Exception:
                return JSONResponse(
                    status_code=422,
                    content={
                        "valid": False,
                        "errors": [{
                            "message": "Please review the warnings again",
                            "code": "ACKNOWLEDGMENT_INVALID",
                            "severity": "error",
                        }],
                        "warnings": [w.to_dict() for w in result.validation.warnings],
                    },
                )
        else:
            token = acknowledgment_service.generate_token(
                entity,
                result.record,
                result.validation.warnings,
            )
            return JSONResponse(
                status_code=202,
                content={
                    "valid": True,
                    "requiresAcknowledgment": True,
                    "warnings": [w.to_dict() for w in result.validation.warnings],
                    "acknowledgmentToken": token,
                    "data": result.record,  # Include processed record for resubmission
                },
            )

    # Validation passed, persist
    saved = db.update(entity_model, id, result.record)
    return JSONResponse(
        status_code=200,
        content={"data": saved},
    )


@app.delete("/api/entities/{entity}/{id}")
async def delete_entity(entity: str, id: str, http_request: Request):
    """Delete a record with validation."""
    if not metadata_loader or not db or not lifecycle_factory:
        raise HTTPException(500, "Not initialized")

    entity_model = metadata_loader.get_entity(entity)
    if not entity_model:
        raise HTTPException(404, f"Entity '{entity}' not found")

    # Get user context from authentication middleware
    user_context = get_user_context(http_request)

    # Check permissions
    allowed, error_msg = can_access_entity(
        entity_model.name, entity_model.scope, "delete", user_context,
        auth_required=jwt_service is not None,
    )
    if not allowed:
        raise HTTPException(403, error_msg)

    # Get record to delete
    record = db.get(entity_model, id)
    if not record:
        raise HTTPException(404, "Record not found")

    # For tenant-scoped entities, verify record belongs to user's tenant
    if entity_model.scope == "tenant" and user_context and user_context.tenant_id:
        record_tenant = record.get("tenantId")
        if record_tenant and record_tenant != user_context.tenant_id:
            raise HTTPException(404, "Record not found")

    # Get delete validators only
    all_validators = lifecycle_factory.get_validators(entity_model)
    delete_validators = [v for v in all_validators if Operation.DELETE in v.on]

    if delete_validators:
        # Run validation for delete
        lifecycle = lifecycle_factory.create_lifecycle(entity_model, user_context)
        result = await lifecycle.prepare(
            record=record,
            operation=Operation.DELETE,
            entity_name=entity,
            defaults=[],
            auto_fields={},
            validators=delete_validators,
            user_context=user_context,
        )

        # Handle validation errors (no warnings for delete)
        if not result.validation.valid:
            return JSONResponse(
                status_code=422,
                content={
                    "valid": False,
                    "errors": [e.to_dict() for e in result.validation.errors],
                },
            )

    # Handle relation constraints (restrict/cascade/setNull)
    relation_errors = db.handle_delete_relations(
        entity_model, id, metadata_loader
    )
    if relation_errors:
        return JSONResponse(
            status_code=422,
            content={
                "valid": False,
                "errors": [
                    {"message": msg, "code": "DELETE_RESTRICTED", "severity": "error"}
                    for msg in relation_errors
                ],
            },
        )

    # Delete the record
    success = db.delete(entity_model, id)
    if not success:
        raise HTTPException(404, "Record not found")

    return {"success": True}


# --- Query Endpoint ---


class QueryRequest(BaseModel):
    fields: list[str] | None = None
    filter: dict[str, Any] | None = None
    sort: list[dict[str, str]] | None = None
    limit: int | None = 25
    offset: int = 0


@app.post("/api/query/{entity}")
async def query_entity(entity: str, query: QueryRequest, http_request: Request) -> dict[str, Any]:
    """Query records with filtering, sorting, and pagination."""
    if not metadata_loader or not db:
        raise HTTPException(500, "Not initialized")

    entity_model = metadata_loader.get_entity(entity)
    if not entity_model:
        raise HTTPException(404, f"Entity '{entity}' not found")

    # Get user context from authentication middleware
    user_context = get_user_context(http_request)

    # Check permissions
    allowed, error_msg = can_access_entity(
        entity_model.name, entity_model.scope, "read", user_context,
        auth_required=jwt_service is not None,
    )
    if not allowed:
        raise HTTPException(403, error_msg)

    # Apply tenant filtering for tenant-scoped entities
    effective_filter = query.filter
    if entity_model.scope == "tenant" and user_context and user_context.tenant_id:
        tenant_condition = {
            "field": "tenantId",
            "operator": "eq",
            "value": user_context.tenant_id,
        }
        if effective_filter and "conditions" in effective_filter:
            # Add tenant filter to existing conditions
            effective_filter = {
                "operator": "and",
                "conditions": effective_filter["conditions"] + [tenant_condition],
            }
        else:
            effective_filter = {"conditions": [tenant_condition]}

    result = db.query(
        entity_model,
        fields=query.fields,
        filter=effective_filter,
        sort=query.sort,
        limit=query.limit,
        offset=query.offset,
    )

    # Hydrate relation display values
    result["data"] = db.hydrate_relations(
        result["data"],
        entity_model,
        metadata_loader,
    )

    return result


# --- Aggregate Endpoint ---


class AggregateRequest(BaseModel):
    groupBy: list[str] | None = None
    measures: list[dict[str, str]] | None = None
    filter: dict[str, Any] | None = None


@app.post("/api/aggregate/{entity}")
async def aggregate_entity(
    entity: str, request: AggregateRequest, http_request: Request
) -> dict[str, Any]:
    """Aggregate records with GROUP BY and aggregate functions."""
    if not metadata_loader or not db:
        raise HTTPException(500, "Not initialized")

    entity_model = metadata_loader.get_entity(entity)
    if not entity_model:
        raise HTTPException(404, f"Entity '{entity}' not found")

    # Get user context from authentication middleware
    user_context = get_user_context(http_request)

    # Check permissions
    allowed, error_msg = can_access_entity(
        entity_model.name,
        entity_model.scope,
        "read",
        user_context,
        auth_required=jwt_service is not None,
    )
    if not allowed:
        raise HTTPException(403, error_msg)

    # Apply tenant filtering for tenant-scoped entities
    effective_filter = request.filter
    if entity_model.scope == "tenant" and user_context and user_context.tenant_id:
        tenant_condition = {
            "field": "tenantId",
            "operator": "eq",
            "value": user_context.tenant_id,
        }
        if effective_filter and "conditions" in effective_filter:
            effective_filter = {
                "operator": "and",
                "conditions": effective_filter["conditions"] + [tenant_condition],
            }
        else:
            effective_filter = {"conditions": [tenant_condition]}

    try:
        result = db.aggregate(
            entity_model,
            group_by=request.groupBy,
            measures=request.measures,
            filter=effective_filter,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    return result
