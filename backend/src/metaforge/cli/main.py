"""MetaForge CLI entry point.

Subcommands are imported only when they run, so a command that needs the
server stack (``migrate``, ``mcp``) does not break the others when MetaForge
is installed without the ``server`` extra (ADR-0015).
"""

from __future__ import annotations

import importlib

import click

# command name -> (module, attribute, short help shown by `metaforge --help`)
_COMMANDS: dict[str, tuple[str, str, str]] = {
    "metadata": ("metaforge.cli.metadata_cmd", "metadata", "Metadata commands."),
    "migrate": ("metaforge.cli.migrate_cmd", "migrate", "Migration commands."),
    "mcp": ("metaforge.cli.mcp_cmd", "mcp_serve", "Start the MetaForge MCP server."),
    "new": ("metaforge.cli.new_cmd", "new", "Scaffold new MetaForge artifacts."),
}

SERVER_EXTRA_HINT = "Install the server extra: pip install 'metaforge[server]'"


class LazyGroup(click.Group):
    """A click group that imports each subcommand on first use."""

    def list_commands(self, ctx: click.Context) -> list[str]:
        return sorted(_COMMANDS)

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        target = _COMMANDS.get(cmd_name)
        if target is None:
            return None
        module_name, attr, _ = target
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if (exc.name or "").split(".")[0] == "metaforge":
                raise  # our own bug, not a missing extra
            missing = exc.name or "a dependency"
            raise click.ClickException(
                f"'metaforge {cmd_name}' needs {missing}, which is not installed. "
                f"{SERVER_EXTRA_HINT}"
            ) from exc
        return getattr(module, attr)

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        # List commands from the table so `--help` imports none of them.
        rows = [(name, _COMMANDS[name][2]) for name in self.list_commands(ctx)]
        with formatter.section("Commands"):
            formatter.write_dl(rows)


@click.group(cls=LazyGroup)
def cli():
    """MetaForge — metadata-driven framework CLI."""
    pass
