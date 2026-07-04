"""FastAPI application."""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from metaforge.metadata.loader import EntityModel, MetadataLoader
from metaforge.metadata.validator import validate_metadata_dir
from metaforge.persistence import PersistenceAdapter, DatabaseConfig, create_adapter, DraftAdapter
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
from metaforge.hooks import (
    HookContext,
    HookService,
    compute_changes,
    register_builtin_hooks,
)
from metaforge.auth import (
    AuthMiddleware,
    JWTService,
    PasswordService,
    get_user_context,
    can_access_entity,
    apply_field_read_policy,
    apply_field_write_policy,
    get_field_access,
)
from metaforge.auth.endpoints import create_auth_router
from metaforge.views import SavedConfigStore, ViewConfigLoader
from metaforge.views.endpoints import create_views_router
from metaforge.screens.loader import ScreenConfigLoader
from metaforge.screens.endpoints import create_screens_router
from metaforge.sandbox.fake_data import FakeDataService
from metaforge.sandbox.service import SandboxService


# Global instances (initialized on startup)
metadata_loader: MetadataLoader | None = None
db: PersistenceAdapter | None = None
draft_db: PersistenceAdapter | None = None
lifecycle_factory: EntityLifecycleFactory | None = None
draft_lifecycle_factory: EntityLifecycleFactory | None = None
acknowledgment_service: WarningAcknowledgmentService | None = None
jwt_service: JWTService | None = None
password_service: PasswordService | None = None
config_store: SavedConfigStore | None = None
view_loader: ViewConfigLoader | None = None
screen_loader: ScreenConfigLoader | None = None
hook_service: HookService | None = None
sandbox_service: SandboxService | None = None
fake_data_service: FakeDataService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize on startup, cleanup on shutdown."""
    global metadata_loader, db, draft_db, lifecycle_factory, draft_lifecycle_factory
    global acknowledgment_service, jwt_service, password_service, config_store
    global view_loader, screen_loader, hook_service, sandbox_service, fake_data_service

    # Register validation functions, validators, and hooks
    register_all_builtins()
    register_canned_validators()
    register_builtin_hooks()

    # Find metadata path (relative to cwd, which should be /backend)
    cwd = Path.cwd()
    if cwd.name == "backend":
        base_path = cwd.parent
    else:
        base_path = cwd
    metadata_path = base_path / "metadata"

    # Validate metadata YAML files against JSON Schemas (warn on errors, don't block startup)
    schema_issues = validate_metadata_dir(metadata_path)
    if schema_issues:
        import logging
        _val_log = logging.getLogger(__name__)
        error_count = sum(1 for i in schema_issues if i.severity == "error")
        warn_count = sum(1 for i in schema_issues if i.severity == "warning")
        for issue in schema_issues:
            if issue.severity == "error":
                _val_log.error("Metadata schema error: %s", issue)
            else:
                _val_log.warning("Metadata schema warning: %s", issue)
        _val_log.warning(
            "Metadata validation: %d error(s), %d warning(s). "
            "Run 'metaforge metadata validate' for details.",
            error_count,
            warn_count,
        )

    # Initialize metadata loader
    metadata_loader = MetadataLoader(metadata_path)
    metadata_loader.load_all()

    # Initialize database (supports DATABASE_URL or METAFORGE_DB_PATH env vars)
    db_config = DatabaseConfig.from_env(base_path)

    # Ensure parent directory exists for SQLite databases
    if db_config.is_sqlite:
        sqlite_path = db_config.url.replace("sqlite:///", "")
        if sqlite_path and sqlite_path != ":memory:":
            Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)

    db = create_adapter(db_config)
    db.connect()

    # Create tables for all non-draft entities (drafts use a separate DB)
    for entity_name in metadata_loader.list_entities():
        entity = metadata_loader.get_entity(entity_name)
        if entity and not entity.is_draft:
            db.initialize_entity(entity)

    # Initialize draft database (separate SQLite file for draft entity tables)
    draft_db = DraftAdapter.from_base_path(base_path)
    draft_db.connect()
    for entity_name in metadata_loader.list_entities():
        entity = metadata_loader.get_entity(entity_name)
        if entity and entity.is_draft:
            draft_db.initialize_entity(entity)

    # Initialize validation lifecycle factory
    secret_key = os.environ.get("METAFORGE_SECRET_KEY", "dev-secret-key-change-in-production")
    lifecycle_factory = EntityLifecycleFactory(db, metadata_loader, secret_key)
    draft_lifecycle_factory = EntityLifecycleFactory(draft_db, metadata_loader, secret_key)
    acknowledgment_service = WarningAcknowledgmentService(secret_key)
    hook_service = HookService()

    # Initialize view configuration system
    config_store = SavedConfigStore(db_config.sqlalchemy_url)
    view_loader = ViewConfigLoader(metadata_path / "views")
    view_loader.load_all()
    for cfg in view_loader.list_configs():
        config_store.upsert_from_yaml(cfg)

    views_router = create_views_router(
        get_config_store=lambda: config_store,
        get_view_loader=lambda: view_loader,
    )
    app.include_router(views_router)

    # Initialize screen configuration system
    screen_loader = ScreenConfigLoader(metadata_path / "screens")
    screen_loader.load_all()

    screens_router = create_screens_router(
        get_screen_loader=lambda: screen_loader,
        get_metadata_loader=lambda: metadata_loader,
    )
    app.include_router(screens_router)

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

    # Initialize sandbox service
    sandbox_service = SandboxService(
        _AppServices(metadata_loader, db, draft_db),
        base_path,
        reload_fn=_sync_reload_metadata,
    )
    fake_data_service = FakeDataService()

    yield

    # Cleanup
    if db:
        db.close()
    if draft_db:
        draft_db.close()


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


def _resolve_adapter(entity_model: EntityModel) -> PersistenceAdapter:
    """Return the right DB adapter for an entity (draft vs live)."""
    if entity_model.is_draft:
        if draft_db is None:
            raise HTTPException(500, "Draft database not initialized")
        return draft_db
    if db is None:
        raise HTTPException(500, "Database not initialized")
    return db


def _resolve_lifecycle(entity_model: EntityModel) -> EntityLifecycleFactory:
    """Return the right lifecycle factory for an entity (draft vs live)."""
    if entity_model.is_draft:
        if draft_lifecycle_factory is None:
            raise HTTPException(500, "Draft lifecycle factory not initialized")
        return draft_lifecycle_factory
    if lifecycle_factory is None:
        raise HTTPException(500, "Lifecycle factory not initialized")
    return lifecycle_factory


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
                "isDraft": entity.is_draft,
            })

    return {"entities": entities}


@app.get("/api/metadata/{entity}")
async def get_entity_metadata(entity: str, http_request: Request) -> dict[str, Any]:
    """Get full metadata for an entity."""
    if not metadata_loader:
        raise HTTPException(500, "Metadata loader not initialized")

    entity_model = metadata_loader.get_entity(entity)
    if not entity_model:
        raise HTTPException(404, f"Entity '{entity}' not found")

    user_context = get_user_context(http_request)

    # Build field metadata with UI config
    fields = []
    for field in entity_model.fields:
        field_type = get_field_type(field.type)

        field_access = get_field_access(field, user_context, entity_model)
        field_meta = {
            "name": field.name,
            "displayName": field.display_name,
            "type": field.type,
            "primaryKey": field.primary_key,
            "readOnly": field.read_only,
            "access": field_access,
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

    # Compute entity-level operation permissions for the current user
    def _can_op(op: str) -> bool:
        allowed, _ = can_access_entity(
            entity_model.name, entity_model.scope, op, user_context,
            auth_required=jwt_service is not None,
            entity_model=entity_model,
        )
        return allowed

    operations = {
        "create": _can_op("create"),
        "update": _can_op("update"),
        "delete": _can_op("delete"),
    }

    return {
        "entity": entity_model.name,
        "displayName": entity_model.display_name,
        "pluralName": entity_model.plural_name,
        "primaryKey": entity_model.primary_key,
        "labelField": entity_model.label_field,
        "isDraft": entity_model.is_draft,
        "operations": operations,
        "fields": fields,
    }


# --- Admin Endpoints ---


@app.post("/api/admin/metadata/reload")
async def reload_metadata_endpoint() -> dict[str, Any]:
    """Reload all metadata from disk without restarting the server.

    Re-scans metadata/entities/, metadata/drafts/, metadata/views/, and
    metadata/screens/ directories.  New entity tables are created via
    ``CREATE TABLE IF NOT EXISTS``; existing tables are left intact.
    Returns counts of the reloaded entities, view configs, and screens.
    """
    global lifecycle_factory, draft_lifecycle_factory

    if (
        not metadata_loader
        or not db
        or not draft_db
        or not view_loader
        or not screen_loader
        or not config_store
    ):
        raise HTTPException(500, "Services not initialized")

    secret_key = os.environ.get(
        "METAFORGE_SECRET_KEY", "dev-secret-key-change-in-production"
    )

    # 1. Reload entity definitions
    metadata_loader.reload()
    entity_count = len(metadata_loader.list_entities())

    # 2. Ensure DB tables exist for any newly-discovered entities (idempotent)
    for entity_name in metadata_loader.list_entities():
        entity = metadata_loader.get_entity(entity_name)
        if entity:
            if entity.is_draft:
                draft_db.initialize_entity(entity)
            else:
                db.initialize_entity(entity)

    # 3. Recreate lifecycle factories so they reflect the updated metadata
    lifecycle_factory = EntityLifecycleFactory(db, metadata_loader, secret_key)
    draft_lifecycle_factory = EntityLifecycleFactory(draft_db, metadata_loader, secret_key)

    # 4. Reload view configs and re-upsert into the config store
    view_loader.reload()
    for cfg in view_loader.list_configs():
        config_store.upsert_from_yaml(cfg)
    view_count = len(view_loader.list_configs())

    # 5. Reload screen configs
    screen_loader.reload()
    screen_count = len(screen_loader.list_screens())

    return {
        "reloaded": True,
        "entities": entity_count,
        "views": view_count,
        "screens": screen_count,
    }


# --- Sandbox Endpoints (ADR-0013) ---


class _AppServices:
    """Minimal adapter so SandboxService can use module-level globals."""

    def __init__(self, ml: Any, db_: Any, draft_db_: Any) -> None:
        self.metadata_loader = ml
        self.db = db_
        self.draft_db = draft_db_


def _sync_reload_metadata() -> None:
    """Synchronous metadata reload — called by SandboxService after YAML changes."""
    global lifecycle_factory, draft_lifecycle_factory

    if not metadata_loader or not db or not draft_db or not view_loader or not screen_loader or not config_store:
        return

    secret_key = os.environ.get("METAFORGE_SECRET_KEY", "dev-secret-key-change-in-production")

    metadata_loader.reload()

    for entity_name in metadata_loader.list_entities():
        entity = metadata_loader.get_entity(entity_name)
        if entity:
            if entity.is_draft:
                draft_db.initialize_entity(entity)
            else:
                db.initialize_entity(entity)

    lifecycle_factory = EntityLifecycleFactory(db, metadata_loader, secret_key)
    draft_lifecycle_factory = EntityLifecycleFactory(draft_db, metadata_loader, secret_key)

    view_loader.reload()
    for cfg in view_loader.list_configs():
        config_store.upsert_from_yaml(cfg)

    screen_loader.reload()


class DraftEntityRequest(BaseModel):
    yaml: str
    generateDoc: bool = False


@app.post("/api/admin/sandbox/draft")
def create_draft_entity_endpoint(body: DraftEntityRequest) -> dict[str, Any]:
    """Write a draft entity YAML, create its table, hot-reload."""
    if not sandbox_service:
        raise HTTPException(500, "Sandbox service not initialized")
    return sandbox_service.draft_entity(body.yaml)


@app.post("/api/admin/sandbox/promote/{entity}")
def promote_entity_endpoint(entity: str, body: DraftEntityRequest | None = None) -> dict[str, Any]:
    """Promote a draft entity to production."""
    if not sandbox_service:
        raise HTTPException(500, "Sandbox service not initialized")
    generate_doc = body.generateDoc if body else False
    result = sandbox_service.promote_entity(entity, generate_doc=generate_doc)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@app.post("/api/admin/sandbox/dismiss/{entity}")
def dismiss_entity_endpoint(entity: str) -> dict[str, Any]:
    """Dismiss (delete) a draft entity."""
    if not sandbox_service:
        raise HTTPException(500, "Sandbox service not initialized")
    result = sandbox_service.dismiss_entity(entity)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


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

    # Route to draft DB if entity is a draft
    active_db = _resolve_adapter(entity_model)
    active_lf = _resolve_lifecycle(entity_model)

    # Get user context from authentication middleware
    user_context = get_user_context(http_request)

    # Check permissions (auth required only if jwt_service is configured)
    allowed, error_msg = can_access_entity(
        entity_model.name, entity_model.scope, "create", user_context,
        auth_required=jwt_service is not None,
        entity_model=entity_model,
    )
    if not allowed:
        raise HTTPException(403, error_msg)

    # Strip fields the user cannot write before processing
    request.data = apply_field_write_policy(request.data, entity_model, user_context)

    # Get validation configuration
    validators = (
        active_lf.get_validators(entity_model)
        + active_lf.get_relation_validators(entity_model)
    )
    field_validators = active_lf.get_field_validators(entity_model)
    defaults = active_lf.get_static_defaults(entity_model) + active_lf.get_defaults(entity_model)
    auto_fields = active_lf.get_auto_fields(entity_model)

    # Run lifecycle (defaults + validation)
    lifecycle = active_lf.create_lifecycle(entity_model, user_context)
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

    # Validation passed — run hooks and persist
    tenant_id = user_context.tenant_id if user_context else None

    # Build hook context
    hook_ctx = HookContext(
        entity_name=entity,
        operation=Operation.CREATE,
        record=result.record,
        original=None,
        changes=None,
        user_context=user_context,
    )

    # Phase 3a: beforeSave hooks
    before_save_defs = active_lf.get_hook_definitions(entity_model, "beforeSave")
    if before_save_defs and hook_service:
        hook_result = await hook_service.run_hooks("beforeSave", before_save_defs, hook_ctx)
        if hook_result and hook_result.abort:
            return JSONResponse(
                status_code=422,
                content={
                    "valid": False,
                    "errors": [{
                        "message": hook_result.abort,
                        "code": "HOOK_ABORT",
                        "severity": "error",
                    }],
                },
            )

    # Phase 3b: Persist (no commit yet if we have afterSave hooks)
    after_save_defs = active_lf.get_hook_definitions(entity_model, "afterSave")
    after_commit_defs = active_lf.get_hook_definitions(entity_model, "afterCommit")
    has_post_hooks = bool(after_save_defs or after_commit_defs)

    if has_post_hooks:
        saved = active_db.create_no_commit(entity_model, hook_ctx.record, tenant_id=tenant_id)
    else:
        saved = active_db.create(entity_model, hook_ctx.record, tenant_id=tenant_id)

    # Phase 3c: afterSave hooks (same transaction)
    if after_save_defs and hook_service:
        hook_ctx.record = saved
        hook_result = await hook_service.run_hooks("afterSave", after_save_defs, hook_ctx)
        if hook_result and hook_result.abort:
            active_db.rollback()
            return JSONResponse(
                status_code=422,
                content={
                    "valid": False,
                    "errors": [{
                        "message": hook_result.abort,
                        "code": "HOOK_ABORT",
                        "severity": "error",
                    }],
                },
            )

    # Phase 3d: Commit
    if has_post_hooks:
        active_db.commit()

    # Phase 4: afterCommit hooks (fire-and-forget)
    if after_commit_defs and hook_service:
        hook_ctx.record = saved
        await hook_service.run_hooks("afterCommit", after_commit_defs, hook_ctx)

    return JSONResponse(
        status_code=201,
        content={"data": apply_field_read_policy(saved, entity_model, user_context)},
    )


@app.get("/api/entities/{entity}/{id}")
async def get_entity(entity: str, id: str, http_request: Request) -> dict[str, Any]:
    """Get a single record."""
    if not metadata_loader or not db:
        raise HTTPException(500, "Not initialized")

    entity_model = metadata_loader.get_entity(entity)
    if not entity_model:
        raise HTTPException(404, f"Entity '{entity}' not found")

    # Route to draft DB if entity is a draft
    active_db = _resolve_adapter(entity_model)

    # Get user context from authentication middleware
    user_context = get_user_context(http_request)

    # Check permissions
    allowed, error_msg = can_access_entity(
        entity_model.name, entity_model.scope, "read", user_context,
        auth_required=jwt_service is not None,
        entity_model=entity_model,
    )
    if not allowed:
        raise HTTPException(403, error_msg)

    result = active_db.get(entity_model, id)
    if not result:
        raise HTTPException(404, "Record not found")

    # For tenant-scoped entities, verify record belongs to user's tenant
    if entity_model.scope == "tenant" and user_context and user_context.tenant_id:
        record_tenant = result.get("tenantId")
        if record_tenant and record_tenant != user_context.tenant_id:
            raise HTTPException(404, "Record not found")

    # Hydrate relation display values, then apply field read policy
    hydrated = active_db.hydrate_relations([result], entity_model, metadata_loader)
    record = hydrated[0] if hydrated else result
    return {"data": apply_field_read_policy(record, entity_model, user_context)}


@app.put("/api/entities/{entity}/{id}")
async def update_entity(entity: str, id: str, request: UpdateRequest, http_request: Request):
    """Update a record with validation."""
    if not metadata_loader or not db or not lifecycle_factory or not acknowledgment_service:
        raise HTTPException(500, "Not initialized")

    entity_model = metadata_loader.get_entity(entity)
    if not entity_model:
        raise HTTPException(404, f"Entity '{entity}' not found")

    # Route to draft DB if entity is a draft
    active_db = _resolve_adapter(entity_model)
    active_lf = _resolve_lifecycle(entity_model)

    # Get user context from authentication middleware
    user_context = get_user_context(http_request)

    # Check permissions
    allowed, error_msg = can_access_entity(
        entity_model.name, entity_model.scope, "update", user_context,
        auth_required=jwt_service is not None,
        entity_model=entity_model,
    )
    if not allowed:
        raise HTTPException(403, error_msg)

    # Strip fields the user cannot write before processing
    request.data = apply_field_write_policy(request.data, entity_model, user_context)

    # Get original record
    original = active_db.get(entity_model, id)
    if not original:
        raise HTTPException(404, "Record not found")

    # For tenant-scoped entities, verify record belongs to user's tenant
    if entity_model.scope == "tenant" and user_context and user_context.tenant_id:
        record_tenant = original.get("tenantId")
        if record_tenant and record_tenant != user_context.tenant_id:
            raise HTTPException(404, "Record not found")

    # Get validation configuration
    validators = (
        active_lf.get_validators(entity_model)
        + active_lf.get_relation_validators(entity_model)
    )
    field_validators = active_lf.get_field_validators(entity_model)
    defaults = active_lf.get_defaults(entity_model)  # No static defaults on update
    auto_fields = active_lf.get_auto_fields(entity_model)

    # Merge original with updates (keep original values for fields not in request)
    merged_data = {**original, **request.data}

    # Run lifecycle
    lifecycle = active_lf.create_lifecycle(entity_model, user_context)
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

    # Validation passed — run hooks and persist
    hook_ctx = HookContext(
        entity_name=entity,
        operation=Operation.UPDATE,
        record=result.record,
        original=original,
        changes=compute_changes(result.record, original),
        user_context=user_context,
    )

    # Phase 3a: beforeSave hooks
    before_save_defs = active_lf.get_hook_definitions(entity_model, "beforeSave")
    if before_save_defs and hook_service:
        hook_result = await hook_service.run_hooks("beforeSave", before_save_defs, hook_ctx)
        if hook_result and hook_result.abort:
            return JSONResponse(
                status_code=422,
                content={
                    "valid": False,
                    "errors": [{
                        "message": hook_result.abort,
                        "code": "HOOK_ABORT",
                        "severity": "error",
                    }],
                },
            )

    # Phase 3b: Persist
    after_save_defs = active_lf.get_hook_definitions(entity_model, "afterSave")
    after_commit_defs = active_lf.get_hook_definitions(entity_model, "afterCommit")
    has_post_hooks = bool(after_save_defs or after_commit_defs)

    if has_post_hooks:
        saved = active_db.update_no_commit(entity_model, id, hook_ctx.record)
    else:
        saved = active_db.update(entity_model, id, hook_ctx.record)

    # Phase 3c: afterSave hooks (same transaction)
    if after_save_defs and hook_service:
        hook_ctx.record = saved
        hook_result = await hook_service.run_hooks("afterSave", after_save_defs, hook_ctx)
        if hook_result and hook_result.abort:
            active_db.rollback()
            return JSONResponse(
                status_code=422,
                content={
                    "valid": False,
                    "errors": [{
                        "message": hook_result.abort,
                        "code": "HOOK_ABORT",
                        "severity": "error",
                    }],
                },
            )

    # Phase 3d: Commit
    if has_post_hooks:
        active_db.commit()

    # Phase 4: afterCommit hooks (fire-and-forget)
    if after_commit_defs and hook_service:
        hook_ctx.record = saved
        await hook_service.run_hooks("afterCommit", after_commit_defs, hook_ctx)

    return JSONResponse(
        status_code=200,
        content={"data": apply_field_read_policy(saved, entity_model, user_context)},
    )


@app.delete("/api/entities/{entity}/{id}")
async def delete_entity(entity: str, id: str, http_request: Request):
    """Delete a record with validation."""
    if not metadata_loader or not db or not lifecycle_factory:
        raise HTTPException(500, "Not initialized")

    entity_model = metadata_loader.get_entity(entity)
    if not entity_model:
        raise HTTPException(404, f"Entity '{entity}' not found")

    # Route to draft DB if entity is a draft
    active_db = _resolve_adapter(entity_model)
    active_lf = _resolve_lifecycle(entity_model)

    # Get user context from authentication middleware
    user_context = get_user_context(http_request)

    # Check permissions
    allowed, error_msg = can_access_entity(
        entity_model.name, entity_model.scope, "delete", user_context,
        auth_required=jwt_service is not None,
        entity_model=entity_model,
    )
    if not allowed:
        raise HTTPException(403, error_msg)

    # Get record to delete
    record = active_db.get(entity_model, id)
    if not record:
        raise HTTPException(404, "Record not found")

    # For tenant-scoped entities, verify record belongs to user's tenant
    if entity_model.scope == "tenant" and user_context and user_context.tenant_id:
        record_tenant = record.get("tenantId")
        if record_tenant and record_tenant != user_context.tenant_id:
            raise HTTPException(404, "Record not found")

    # Get delete validators only
    all_validators = active_lf.get_validators(entity_model)
    delete_validators = [v for v in all_validators if Operation.DELETE in v.on]

    if delete_validators:
        # Run validation for delete
        lifecycle = active_lf.create_lifecycle(entity_model, user_context)
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

    # Phase 3a: beforeDelete hooks
    hook_ctx = HookContext(
        entity_name=entity,
        operation=Operation.DELETE,
        record=record,
        original=None,
        changes=None,
        user_context=user_context,
    )

    before_delete_defs = active_lf.get_hook_definitions(entity_model, "beforeDelete")
    if before_delete_defs and hook_service:
        hook_result = await hook_service.run_hooks("beforeDelete", before_delete_defs, hook_ctx)
        if hook_result and hook_result.abort:
            return JSONResponse(
                status_code=422,
                content={
                    "valid": False,
                    "errors": [{
                        "message": hook_result.abort,
                        "code": "HOOK_ABORT",
                        "severity": "error",
                    }],
                },
            )

    # Handle relation constraints (restrict/cascade/setNull)
    relation_errors = active_db.handle_delete_relations(
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
    after_commit_defs = active_lf.get_hook_definitions(entity_model, "afterCommit")
    if after_commit_defs:
        success = active_db.delete_no_commit(entity_model, id)
        active_db.commit()
    else:
        success = active_db.delete(entity_model, id)

    if not success:
        raise HTTPException(404, "Record not found")

    # Phase 4: afterCommit hooks (fire-and-forget)
    if after_commit_defs and hook_service:
        await hook_service.run_hooks("afterCommit", after_commit_defs, hook_ctx)

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

    # Route to draft DB if entity is a draft
    active_db = _resolve_adapter(entity_model)

    # Get user context from authentication middleware
    user_context = get_user_context(http_request)

    # Check permissions
    allowed, error_msg = can_access_entity(
        entity_model.name, entity_model.scope, "read", user_context,
        auth_required=jwt_service is not None,
        entity_model=entity_model,
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

    result = active_db.query(
        entity_model,
        fields=query.fields,
        filter=effective_filter,
        sort=query.sort,
        limit=query.limit,
        offset=query.offset,
    )

    # Hydrate relation display values, then apply field read policy to each row
    result["data"] = active_db.hydrate_relations(
        result["data"],
        entity_model,
        metadata_loader,
    )
    result["data"] = [
        apply_field_read_policy(row, entity_model, user_context)
        for row in result["data"]
    ]

    return result


# --- Aggregate Endpoint ---


class AggregateRequest(BaseModel):
    groupBy: list[str] | None = None
    measures: list[dict[str, str]] | None = None
    filter: dict[str, Any] | None = None
    dateTrunc: dict[str, str] | None = None


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

    # Route to draft DB if entity is a draft
    active_db = _resolve_adapter(entity_model)

    # Get user context from authentication middleware
    user_context = get_user_context(http_request)

    # Check permissions
    allowed, error_msg = can_access_entity(
        entity_model.name,
        entity_model.scope,
        "read",
        user_context,
        auth_required=jwt_service is not None,
        entity_model=entity_model,
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
        result = active_db.aggregate(
            entity_model,
            group_by=request.groupBy,
            measures=request.measures,
            filter=effective_filter,
            date_trunc=request.dateTrunc,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    return result
