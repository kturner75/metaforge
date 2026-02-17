"""Run MetaForge MCP server.

Usage:
    python -m metaforge.mcp                    # stdio transport (Claude Desktop)
    python -m metaforge.mcp --transport sse    # SSE transport (web clients)
"""

import sys


def main():
    transport = "stdio"
    if "--transport" in sys.argv:
        idx = sys.argv.index("--transport")
        if idx + 1 < len(sys.argv):
            transport = sys.argv[idx + 1]

    from metaforge.mcp.server import mcp
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
