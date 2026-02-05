"""Local dev entrypoint for the MetaForge API."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _ensure_src_on_path() -> None:
    backend_dir = Path(__file__).resolve().parent
    src_dir = backend_dir / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


if __name__ == "__main__":
    _ensure_src_on_path()

    import uvicorn

    uvicorn.run(
        "metaforge.api:app",
        host="127.0.0.1",
        port=int(os.environ.get("METAFORGE_PORT", "8000")),
        reload=True,
        log_level=os.environ.get("METAFORGE_LOG_LEVEL", "debug"),
    )
