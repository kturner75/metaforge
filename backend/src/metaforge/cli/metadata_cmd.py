"""Metadata CLI commands — validate and diff."""

from pathlib import Path

import click

from metaforge.metadata.loader import MetadataLoader
from metaforge.migrations.diff import compute_diff
from metaforge.migrations.snapshot import (
    create_snapshot_from_metadata,
    load_snapshot,
)


def _resolve_paths():
    """Resolve metadata and migrations paths from cwd."""
    cwd = Path.cwd()
    if cwd.name == "backend":
        base_path = cwd.parent
    else:
        base_path = cwd
    metadata_path = base_path / "metadata"
    migrations_path = base_path / "migrations"
    return base_path, metadata_path, migrations_path


@click.group()
def metadata():
    """Metadata commands."""
    pass


@metadata.command()
def validate():
    """Validate all entity metadata YAML files."""
    _, metadata_path, _ = _resolve_paths()

    if not metadata_path.exists():
        click.echo(f"Error: Metadata directory not found at {metadata_path}", err=True)
        raise SystemExit(1)

    try:
        loader = MetadataLoader(metadata_path)
        loader.load_all()
    except Exception as e:
        click.echo(f"Validation failed: {e}", err=True)
        raise SystemExit(1)

    entities = loader.list_entities()
    click.echo(f"Validated {len(entities)} entities:")
    for name in sorted(entities):
        entity = loader.get_entity(name)
        field_count = len(entity.fields) if entity else 0
        click.echo(f"  {name} ({field_count} fields, scope: {entity.scope})")

    click.echo("\nAll metadata is valid.")


@metadata.command("diff")
def diff_cmd():
    """Show what migration operations would be generated (dry-run)."""
    _, metadata_path, migrations_path = _resolve_paths()

    if not metadata_path.exists():
        click.echo(f"Error: Metadata directory not found at {metadata_path}", err=True)
        raise SystemExit(1)

    # Load current metadata
    loader = MetadataLoader(metadata_path)
    loader.load_all()
    current = create_snapshot_from_metadata(loader)

    # Load previous snapshot
    snapshot_path = migrations_path / "schema_snapshot.json"
    previous = load_snapshot(snapshot_path)

    # Compute diff
    ops = compute_diff(previous, current, allow_destructive=False)

    if not ops:
        click.echo("No changes detected.")
        return

    click.echo(f"Detected {len(ops)} change(s):\n")
    for i, op in enumerate(ops, 1):
        prefix = "!" if op.destructive else "+"
        click.echo(f"  {prefix} {op.describe()}")

    click.echo(
        "\nRun 'metaforge migrate generate --message \"description\"' to create a migration."
    )
