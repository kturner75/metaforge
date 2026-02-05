"""Sanity check for local dev Python environment."""

from __future__ import annotations

import sys


def main() -> int:
    print("Python executable:", sys.executable)
    try:
        import uvicorn  # noqa: F401
    except Exception as exc:  # pragma: no cover - dev-only script
        print("FAILED: uvicorn import error:", repr(exc))
        return 1

    print("OK: uvicorn is installed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
