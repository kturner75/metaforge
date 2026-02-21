"""Metadata CLI commands — validate and diff."""

from pathlib import Path

import click

from metaforge.metadata.loader import MetadataLoader
from metaforge.metadata.validator import _SUBDIR_SCHEMA, validate_metadata_dir, validate_yaml_file
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
@click.option(
    "--strict",
    is_flag=True,
    default=False,
    help="Treat warnings as errors.",
)
@click.option(
    "--path",
    "target_path",
    default=None,
    type=click.Path(exists=True, path_type=Path),
    help="Validate a single YAML file instead of the whole metadata directory.",
)
def validate(strict: bool, target_path: Path | None):
    """Validate metadata YAML files against JSON Schemas."""
    _, metadata_path, _ = _resolve_paths()

    # ── Schema (JSON Schema) validation ─────────────────────────────────────
    if target_path is not None:
        # Single-file mode: infer schema from parent directory name
        parent = target_path.parent.name
        schema_name = _SUBDIR_SCHEMA.get(parent)
        if schema_name is None:
            click.echo(
                f"Warning: cannot determine schema for directory '{parent}'. "
                "Expected one of: entities, blocks, views, screens.",
                err=True,
            )
            schema_issues = []
        else:
            schema_issues = validate_yaml_file(target_path, schema_name)
    else:
        if not metadata_path.exists():
            click.echo(f"Error: Metadata directory not found at {metadata_path}", err=True)
            raise SystemExit(1)
        schema_issues = validate_metadata_dir(metadata_path, strict=strict)

    # Report schema issues
    errors = [i for i in schema_issues if i.severity == "error"]
    warnings = [i for i in schema_issues if i.severity == "warning"]

    for issue in schema_issues:
        colour = "red" if issue.severity == "error" else "yellow"
        click.echo(click.style(str(issue), fg=colour))

    if errors:
        click.echo(
            click.style(
                f"\n{len(errors)} schema error(s) found"
                + (f", {len(warnings)} warning(s)" if warnings else ""),
                fg="red",
                bold=True,
            )
        )
        raise SystemExit(1)

    if warnings:
        click.echo(
            click.style(f"{len(warnings)} warning(s) found.", fg="yellow")
        )

    # ── Semantic (loader) validation ─────────────────────────────────────────
    # Only runs when validating the full directory (target_path is None)
    if target_path is None:
        try:
            loader = MetadataLoader(metadata_path)
            loader.load_all()
        except Exception as e:
            click.echo(click.style(f"\nSemantic validation failed: {e}", fg="red"), err=True)
            raise SystemExit(1)

        entities = loader.list_entities()
        click.echo(f"\nLoaded {len(entities)} entities:")
        for name in sorted(entities):
            entity = loader.get_entity(name)
            field_count = len(entity.fields) if entity else 0
            click.echo(f"  ✓ {name} ({field_count} fields, scope: {entity.scope})")

    click.echo(click.style("\nAll metadata is valid.", fg="green", bold=True))


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
