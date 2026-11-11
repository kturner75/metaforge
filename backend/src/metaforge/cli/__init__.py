"""MetaForge CLI."""


def main() -> None:
    """Console entry point; explains the missing extra instead of a traceback."""
    try:
        from metaforge.cli.main import cli
    except ModuleNotFoundError as exc:
        if exc.name != "click":
            raise
        raise SystemExit(
            "The metaforge command needs the server extra: pip install 'metaforge[server]'"
        ) from None
    cli()
