"""MetaForge CLI entry point."""

import click


@click.group()
def cli():
    """MetaForge — metadata-driven framework CLI."""
    pass


# Register subcommand groups
from metaforge.cli.metadata_cmd import metadata  # noqa: E402
from metaforge.cli.migrate_cmd import migrate  # noqa: E402

cli.add_command(metadata)
cli.add_command(migrate)
