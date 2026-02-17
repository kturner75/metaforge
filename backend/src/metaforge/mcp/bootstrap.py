"""Initialize MetaForge services for the MCP server process.

Mirrors the initialization in api/app.py lifespan but returns a services
container instead of setting module globals.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from metaforge.metadata.loader import MetadataLoader
from metaforge.persistence import DatabaseConfig, PersistenceAdapter, create_adapter
from metaforge.validation import (
    UserContext,
    WarningAcknowledgmentService,
    register_all_builtins,
    register_canned_validators,
)
from metaforge.validation.integration import EntityLifecycleFactory
from metaforge.views import SavedConfigStore, ViewConfigLoader


@dataclass
class MetaForgeServices:
    """Container for all initialized MetaForge services."""

    metadata_loader: MetadataLoader
    db: PersistenceAdapter
    lifecycle_factory: EntityLifecycleFactory
    acknowledgment_service: WarningAcknowledgmentService
    config_store: SavedConfigStore


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

    # Create tables for all entities
    for entity_name in metadata_loader.list_entities():
        entity = metadata_loader.get_entity(entity_name)
        if entity:
            db.initialize_entity(entity)

    # Validation lifecycle
    secret_key = os.environ.get(
        "METAFORGE_SECRET_KEY", "dev-secret-key-change-in-production"
    )
    lifecycle_factory = EntityLifecycleFactory(db, metadata_loader, secret_key)
    acknowledgment_service = WarningAcknowledgmentService(secret_key)

    # View configs
    config_store = SavedConfigStore(db.conn)
    view_loader = ViewConfigLoader(metadata_path / "views")
    view_loader.load_all()
    for cfg in view_loader.list_configs():
        config_store.upsert_from_yaml(cfg)

    return MetaForgeServices(
        metadata_loader=metadata_loader,
        db=db,
        lifecycle_factory=lifecycle_factory,
        acknowledgment_service=acknowledgment_service,
        config_store=config_store,
    )
