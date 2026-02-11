"""Alembic migration runner.

Wraps Alembic's programmatic API to apply, rollback, and inspect
migrations without requiring a static alembic.ini file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory


@dataclass
class MigrationInfo:
    """Info about a single migration."""

    revision: str
    description: str
    is_applied: bool


def _make_alembic_config(database_url: str, migrations_dir: Path) -> Config:
    """Create an Alembic Config object programmatically.

    This replaces the need for a static alembic.ini file.
    """
    cfg = Config()
    cfg.set_main_option("sqlalchemy.url", database_url)

    cfg.set_main_option("script_location", str(migrations_dir))

    # Alembic needs env.py inside the script_location. We'll create
    # a minimal directory structure if it doesn't exist.
    _ensure_alembic_structure(migrations_dir)

    return cfg


def _ensure_alembic_structure(migrations_dir: Path) -> None:
    """Ensure the migrations directory has the Alembic structure.

    Creates:
      migrations_dir/
        env.py (symlink or copy of our env.py)
        versions/
        script.py.mako (minimal template)
    """
    migrations_dir.mkdir(parents=True, exist_ok=True)
    versions_dir = migrations_dir / "versions"
    versions_dir.mkdir(exist_ok=True)

    # Copy our env.py into the migrations dir if not present
    env_target = migrations_dir / "env.py"
    if not env_target.exists():
        env_source = Path(__file__).parent / "env.py"
        env_target.write_text(env_source.read_text())

    # Create script.py.mako if not present (Alembic requires it)
    mako_target = migrations_dir / "script.py.mako"
    if not mako_target.exists():
        mako_target.write_text(_SCRIPT_MAKO_TEMPLATE)


_SCRIPT_MAKO_TEMPLATE = '''\
"""${message}"""

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}

from alembic import op
import sqlalchemy as sa

def upgrade():
    ${upgrades if upgrades else "pass"}

def downgrade():
    ${downgrades if downgrades else "pass"}
'''


def apply_migrations(
    database_url: str,
    migrations_dir: Path,
    target: str | None = None,
) -> None:
    """Apply pending migrations.

    Args:
        database_url: Database connection URL.
        migrations_dir: Path to the migrations directory.
        target: Target revision (default: "head" = all pending).
    """
    cfg = _make_alembic_config(database_url, migrations_dir)
    command.upgrade(cfg, target or "head")


def stamp_migration(
    database_url: str,
    migrations_dir: Path,
    revision: str = "head",
) -> None:
    """Stamp the database as being at a specific revision without running migrations.

    Use this to adopt migrations on an existing database whose tables
    were created outside Alembic (e.g., by initialize_entity()).

    Args:
        database_url: Database connection URL.
        migrations_dir: Path to the migrations directory.
        revision: Revision to stamp as applied (default: "head" = latest).
    """
    cfg = _make_alembic_config(database_url, migrations_dir)
    command.stamp(cfg, revision)


def rollback_migration(
    database_url: str,
    migrations_dir: Path,
) -> None:
    """Rollback the last applied migration.

    Args:
        database_url: Database connection URL.
        migrations_dir: Path to the migrations directory.
    """
    cfg = _make_alembic_config(database_url, migrations_dir)
    command.downgrade(cfg, "-1")


def get_migration_status(
    database_url: str,
    migrations_dir: Path,
) -> list[MigrationInfo]:
    """Get the status of all migrations.

    Returns:
        List of MigrationInfo with applied/pending status.
    """
    cfg = _make_alembic_config(database_url, migrations_dir)

    script = ScriptDirectory.from_config(cfg)

    # Get current head revision(s) from the database.
    # Alembic's alembic_version table stores only the current head,
    # not a full history. All revisions up to and including the head
    # are considered "applied".
    from sqlalchemy import create_engine, text

    engine = create_engine(database_url)
    current_heads: set[str] = set()

    try:
        with engine.connect() as conn:
            try:
                result = conn.execute(text("SELECT version_num FROM alembic_version"))
                current_heads = {row[0] for row in result}
            except Exception:
                # alembic_version table doesn't exist yet
                pass
    finally:
        engine.dispose()

    # Build the set of applied revisions by walking backwards from
    # each current head through the down_revision chain.
    applied: set[str] = set()
    for head_rev in current_heads:
        rev_obj = script.get_revision(head_rev)
        while rev_obj is not None:
            applied.add(rev_obj.revision)
            if rev_obj.down_revision:
                rev_obj = script.get_revision(str(rev_obj.down_revision))
            else:
                break

    # Walk all revisions
    migrations: list[MigrationInfo] = []
    for rev in script.walk_revisions():
        migrations.append(
            MigrationInfo(
                revision=rev.revision,
                description=rev.doc or "",
                is_applied=rev.revision in applied,
            )
        )

    # Reverse to get chronological order (walk_revisions goes newest-first)
    migrations.reverse()
    return migrations
