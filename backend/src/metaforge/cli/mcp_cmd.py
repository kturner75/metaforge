"""MCP server CLI command."""

import click


@click.command("mcp")
@click.option(
    "--transport",
    default="stdio",
    type=click.Choice(["stdio", "sse"]),
    help="MCP transport protocol.",
)
def mcp_serve(transport: str):
    """Start the MetaForge MCP server."""
    from metaforge.mcp.server import mcp as mcp_server

    mcp_server.run(transport=transport)
