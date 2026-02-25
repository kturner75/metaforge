"""Initialize MetaForge services for the MCP server process.

Mirrors the initialization in api/app.py lifespan but returns a services
container instead of setting module globals.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from metaforge.metadata.loader import MetadataLoader
from metaforge.persistence import DatabaseConfig, DraftAdapter, PersistenceAdapter, create_adapter
from metaforge.validation import (
    UserContext,
    WarningAcknowledgmentService,
    register_all_builtins,
    register_canned_validators,
)
from metaforge.validation.integration import EntityLifecycleFactory
from metaforge.views import SavedConfigStore, ViewConfigLoader
from metaforge.screens.loader import ScreenConfigLoader


@dataclass
class MetaForgeServices:
    """Container for all initialized MetaForge services."""

    metadata_loader: MetadataLoader
    db: PersistenceAdapter
    draft_db: PersistenceAdapter
    lifecycle_factory: EntityLifecycleFactory
    draft_lifecycle_factory: EntityLifecycleFactory
    acknowledgment_service: WarningAcknowledgmentService
    config_store: SavedConfigStore
    view_loader: ViewConfigLoader
    screen_loader: ScreenConfigLoader


def get_mcp_user_context() -> UserContext | None:
    """Build a UserContext from MCP environment variables.

    Set METAFORGE_MCP_USER_ID, METAFORGE_MCP_TENANT_ID, and
    METAFORGE_MCP_ROLE to configure the identity used by MCP tools.
    If METAFORGE_MCP_USER_ID is not set, returns None (unauthenticated).
    """
    user_id = os.environ.get("METAFORGE_MCP_USER_ID")
    if not user_id:
        return None
    return UserContext(
        user_id=user_id,
        tenant_id=os.environ.get("METAFORGE_MCP_TENANT_ID"),
        roles=[os.environ.get("METAFORGE_MCP_ROLE", "admin")],
    )


def initialize_services(base_path: Path | None = None) -> MetaForgeServices:
    """Initialize all MetaForge services for MCP.

    Follows the same sequence as api/app.py lifespan.
    """
    if base_path is None:
        cwd = Path.cwd()
        base_path = cwd.parent if cwd.name == "backend" else cwd

    metadata_path = base_path / "metadata"

    # Register validation functions
    register_all_builtins()
    register_canned_validators()

    # Load metadata
    metadata_loader = MetadataLoader(metadata_path)
    metadata_loader.load_all()

    # Initialize database
    db_config = DatabaseConfig.from_env(base_path)
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

    # Validation lifecycle
    secret_key = os.environ.get(
        "METAFORGE_SECRET_KEY", "dev-secret-key-change-in-production"
    )
    lifecycle_factory = EntityLifecycleFactory(db, metadata_loader, secret_key)
    draft_lifecycle_factory = EntityLifecycleFactory(draft_db, metadata_loader, secret_key)
    acknowledgment_service = WarningAcknowledgmentService(secret_key)

    # View configs
    config_store = SavedConfigStore(db_config.sqlalchemy_url)
    view_loader = ViewConfigLoader(metadata_path / "views")
    view_loader.load_all()
    for cfg in view_loader.list_configs():
        config_store.upsert_from_yaml(cfg)

    # Screen configs
    screen_loader = ScreenConfigLoader(metadata_path / "screens")
    screen_loader.load_all()

    return MetaForgeServices(
        metadata_loader=metadata_loader,
        db=db,
        draft_db=draft_db,
        lifecycle_factory=lifecycle_factory,
        draft_lifecycle_factory=draft_lifecycle_factory,
        acknowledgment_service=acknowledgment_service,
        config_store=config_store,
        view_loader=view_loader,
        screen_loader=screen_loader,
    )


def reload_metadata(services: MetaForgeServices) -> dict[str, int]:
    """Reload all metadata from disk without reinitializing database connections.

    Re-scans metadata/entities/, metadata/drafts/, metadata/views/, and
    metadata/screens/.  New entity tables are created via
    ``CREATE TABLE IF NOT EXISTS``; existing tables are left intact.
    Lifecycle factories are recreated so they reference the updated metadata.

    Returns a count summary dict with keys ``entities``, ``views``, ``screens``.
    """
    secret_key = os.environ.get(
        "METAFORGE_SECRET_KEY", "dev-secret-key-change-in-production"
    )

    # 1. Reload entity definitions
    services.metadata_loader.reload()
    entity_count = len(services.metadata_loader.list_entities())

    # 2. Ensure tables exist for any newly-discovered entities (idempotent)
    for entity_name in services.metadata_loader.list_entities():
        entity = services.metadata_loader.get_entity(entity_name)
        if entity:
            if entity.is_draft:
                services.draft_db.initialize_entity(entity)
            else:
                services.db.initialize_entity(entity)

    # 3. Recreate lifecycle factories so they reflect the updated metadata
    services.lifecycle_factory = EntityLifecycleFactory(
        services.db, services.metadata_loader, secret_key
    )
    services.draft_lifecycle_factory = EntityLifecycleFactory(
        services.draft_db, services.metadata_loader, secret_key
    )

    # 4. Reload view configs and re-upsert into the config store
    services.view_loader.reload()
    for cfg in services.view_loader.list_configs():
        services.config_store.upsert_from_yaml(cfg)
    view_count = len(services.view_loader.list_configs())

    # 5. Reload screen configs
    services.screen_loader.reload()
    screen_count = len(services.screen_loader.list_screens())

    return {"entities": entity_count, "views": view_count, "screens": screen_count}
