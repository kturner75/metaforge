"""Migrate CLI commands — generate, apply, rollback, status."""

from pathlib import Path

import click

from metaforge.metadata.loader import MetadataLoader
from metaforge.migrations.diff import compute_diff
from metaforge.migrations.generator import generate_migration
from metaforge.migrations.runner import (
    apply_migrations,
    get_migration_status,
    rollback_migration,
    stamp_migration,
)
from metaforge.migrations.snapshot import (
    create_snapshot_from_metadata,
    load_snapshot,
    save_snapshot,
)
from metaforge.persistence.config import DatabaseConfig


def _resolve_paths():
    """Resolve base, metadata, and migrations paths from cwd."""
    cwd = Path.cwd()
    if cwd.name == "backend":
        base_path = cwd.parent
    else:
        base_path = cwd
    metadata_path = base_path / "metadata"
    migrations_path = base_path / "migrations"
    return base_path, metadata_path, migrations_path


@click.group()
def migrate():
    """Migration commands."""
    pass


@migrate.command()
@click.option(
    "--message", "-m", default="initial schema",
    help="Description for the baseline migration.",
)
def init(message: str):
    """Bootstrap migrations for an existing database.

    Generates an initial migration representing the current metadata,
    then stamps it as applied WITHOUT executing any SQL.  This tells
    Alembic "the database already matches this schema" so future
    incremental migrations work correctly.

    Use this once when adopting migrations on a database whose tables
    were created by initialize_entity().

    After init, the normal workflow resumes:

        metaforge migrate init                  # one-time bootstrap
        # ... edit YAML, add a field ...
        metaforge migrate generate -m "add field"
        metaforge migrate apply
    """
    base_path, metadata_path, migrations_path = _resolve_paths()

    if not metadata_path.exists():
        click.echo(f"Error: Metadata directory not found at {metadata_path}", err=True)
        raise SystemExit(1)

    # Guard: don't re-init if migrations already exist
    versions_dir = migrations_path / "versions"
    if versions_dir.exists() and any(versions_dir.glob("*.py")):
        click.echo(
            "Error: Migrations already exist. "
            "'migrate init' is only for first-time bootstrap.",
            err=True,
        )
        raise SystemExit(1)

    # Load current metadata and snapshot it
    loader = MetadataLoader(metadata_path)
    loader.load_all()
    current_snapshot = create_snapshot_from_metadata(loader)

    # Diff from empty → current = all CREATE TABLE ops
    from metaforge.migrations.snapshot import SchemaSnapshot

    empty = SchemaSnapshot.empty()
    ops = compute_diff(empty, current_snapshot, allow_destructive=False)

    if not ops:
        click.echo("No entities found in metadata. Nothing to initialise.")
        return

    click.echo(f"Creating baseline migration with {len(ops)} table(s):")
    for op in ops:
        click.echo(f"  + {op.describe()}")

    # Generate the migration file
    filepath = generate_migration(ops=ops, message=message, output_dir=migrations_path)

    # Save the snapshot so future 'generate' knows the baseline
    snapshot_path = migrations_path / "schema_snapshot.json"
    current_snapshot.version = 1
    save_snapshot(current_snapshot, snapshot_path)

    # Stamp the database at this migration (no SQL executed)
    db_config = DatabaseConfig.from_env(base_path)
    sa_url = db_config.sqlalchemy_url

    if db_config.is_sqlite:
        sqlite_path = db_config.url.replace("sqlite:///", "")
        if sqlite_path and sqlite_path != ":memory:":
            Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)

    stamp_migration(sa_url, migrations_path, revision="head")

    click.echo(f"\nGenerated: {filepath.relative_to(base_path)}")
    click.echo(f"Snapshot saved: {snapshot_path.relative_to(base_path)}")
    click.echo(f"Database stamped at revision 0001 (no SQL executed).")
    click.echo(
        "\nBaseline complete. You can now make YAML changes and run:\n"
        "  metaforge migrate generate -m 'description'\n"
        "  metaforge migrate apply"
    )


@migrate.command()
@click.option("--message", "-m", required=True, help="Description of the migration.")
@click.option(
    "--allow-destructive",
    is_flag=True,
    default=False,
    help="Allow DROP TABLE and DROP COLUMN operations.",
)
def generate(message: str, allow_destructive: bool):
    """Generate a migration from metadata changes."""
    base_path, metadata_path, migrations_path = _resolve_paths()

    if not metadata_path.exists():
        click.echo(f"Error: Metadata directory not found at {metadata_path}", err=True)
        raise SystemExit(1)

    # Load current metadata
    loader = MetadataLoader(metadata_path)
    loader.load_all()
    current_snapshot = create_snapshot_from_metadata(loader)

    # Load previous snapshot
    snapshot_path = migrations_path / "schema_snapshot.json"
    previous_snapshot = load_snapshot(snapshot_path)

    # Compute diff
    ops = compute_diff(previous_snapshot, current_snapshot, allow_destructive=allow_destructive)

    if not ops:
        click.echo("No changes detected.")
        return

    # Show what will be generated
    click.echo(f"Detected {len(ops)} change(s):")
    for op in ops:
        prefix = "!" if op.destructive else "+"
        click.echo(f"  {prefix} {op.describe()}")

    # Generate migration file
    filepath = generate_migration(
        ops=ops,
        message=message,
        output_dir=migrations_path,
    )

    # Update snapshot version
    current_snapshot.version = previous_snapshot.version + 1
    save_snapshot(current_snapshot, snapshot_path)

    click.echo(f"\nGenerated: {filepath.relative_to(base_path)}")
    click.echo(f"Snapshot updated: {snapshot_path.relative_to(base_path)}")
    click.echo("\nRun 'metaforge migrate apply' to apply this migration.")


@migrate.command()
@click.option("--to", "target", default=None, help="Apply up to a specific revision.")
def apply(target: str | None):
    """Apply pending migrations."""
    base_path, _, migrations_path = _resolve_paths()

    versions_dir = migrations_path / "versions"
    if not versions_dir.exists() or not any(versions_dir.glob("*.py")):
        click.echo("No migrations found. Run 'metaforge migrate generate' first.")
        return

    db_config = DatabaseConfig.from_env(base_path)

    # Ensure parent dir exists for SQLite
    if db_config.is_sqlite:
        sqlite_path = db_config.url.replace("sqlite:///", "")
        if sqlite_path and sqlite_path != ":memory:":
            Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)

    sa_url = db_config.sqlalchemy_url
    click.echo(f"Applying migrations to: {db_config.url}")

    try:
        apply_migrations(sa_url, migrations_path, target=target)
        click.echo("Migrations applied successfully.")
    except Exception as e:
        click.echo(f"Error applying migrations: {e}", err=True)
        raise SystemExit(1)

    # Show current status
    _print_status(sa_url, migrations_path)


@migrate.command()
def rollback():
    """Rollback the last applied migration."""
    base_path, _, migrations_path = _resolve_paths()

    db_config = DatabaseConfig.from_env(base_path)
    sa_url = db_config.sqlalchemy_url

    click.echo(f"Rolling back last migration on: {db_config.url}")

    try:
        rollback_migration(sa_url, migrations_path)
        click.echo("Rollback successful.")
    except Exception as e:
        click.echo(f"Error rolling back: {e}", err=True)
        raise SystemExit(1)

    _print_status(sa_url, migrations_path)


@migrate.command()
@click.option(
    "--revision", "-r", default=None,
    help="Revision to stamp (default: latest initial migration).",
)
def stamp(revision: str | None):
    """Mark migrations as applied without running them.

    Use this when adopting migrations on an existing database whose tables
    were already created by the app startup (initialize_entity). This tells
    Alembic "the database is already at this revision" so future incremental
    migrations can run cleanly.

    Typical workflow for existing databases:

        metaforge migrate generate -m "initial schema"
        metaforge migrate stamp           # marks 0001 as applied
        # ... edit YAML, add a field ...
        metaforge migrate generate -m "add hq_state"
        metaforge migrate apply           # only runs 0002
    """
    base_path, _, migrations_path = _resolve_paths()

    versions_dir = migrations_path / "versions"
    if not versions_dir.exists() or not any(versions_dir.glob("*.py")):
        click.echo("No migrations found. Run 'metaforge migrate generate' first.")
        return

    db_config = DatabaseConfig.from_env(base_path)
    sa_url = db_config.sqlalchemy_url

    # Ensure parent dir exists for SQLite
    if db_config.is_sqlite:
        sqlite_path = db_config.url.replace("sqlite:///", "")
        if sqlite_path and sqlite_path != ":memory:":
            Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)

    target = revision or "head"
    click.echo(f"Stamping database as revision '{target}' (no migrations executed).")

    try:
        stamp_migration(sa_url, migrations_path, revision=target)
        click.echo("Stamp successful.")
    except Exception as e:
        click.echo(f"Error stamping: {e}", err=True)
        raise SystemExit(1)

    _print_status(sa_url, migrations_path)


@migrate.command()
def status():
    """Show migration status (applied and pending)."""
    base_path, _, migrations_path = _resolve_paths()

    versions_dir = migrations_path / "versions"
    if not versions_dir.exists() or not any(versions_dir.glob("*.py")):
        click.echo("No migrations found.")
        return

    db_config = DatabaseConfig.from_env(base_path)
    _print_status(db_config.sqlalchemy_url, migrations_path)


def _print_status(database_url: str, migrations_dir: Path) -> None:
    """Print migration status table."""
    try:
        infos = get_migration_status(database_url, migrations_dir)
    except Exception as e:
        click.echo(f"Could not read migration status: {e}", err=True)
        return

    if not infos:
        click.echo("No migrations found.")
        return

    applied_count = sum(1 for i in infos if i.is_applied)
    pending_count = sum(1 for i in infos if not i.is_applied)

    click.echo(f"\nMigration status ({applied_count} applied, {pending_count} pending):")
    for info in infos:
        marker = "[x]" if info.is_applied else "[ ]"
        click.echo(f"  {marker} {info.revision}: {info.description}")
