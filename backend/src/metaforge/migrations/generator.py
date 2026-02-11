"""Migration file generator.

Renders a list of MigrationOps into an Alembic-compatible migration
Python file with upgrade() and downgrade() functions.
"""

from __future__ import annotations

import re
from pathlib import Path

from metaforge.migrations.types import MigrationOp

MIGRATION_TEMPLATE = '''\
"""${message}"""

revision = "${revision}"
down_revision = ${down_revision}

from alembic import op
import sqlalchemy as sa


def upgrade():
${upgrade_body}


def downgrade():
${downgrade_body}
'''


def _next_revision(versions_dir: Path) -> tuple[str, str | None]:
    """Determine the next revision ID and the current head.

    Returns:
        (next_revision, down_revision) where down_revision is None for
        the first migration.
    """
    if not versions_dir.exists():
        return "0001", None

    existing = sorted(versions_dir.glob("*.py"))
    if not existing:
        return "0001", None

    # Extract revision numbers from filenames: 0001_xxx.py → "0001"
    revisions = []
    for f in existing:
        match = re.match(r"^(\d{4})_", f.name)
        if match:
            revisions.append(match.group(1))

    if not revisions:
        return "0001", None

    latest = max(revisions)
    next_num = int(latest) + 1
    return f"{next_num:04d}", latest


def _slugify(message: str) -> str:
    """Convert a message to a filename-safe slug."""
    slug = message.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    slug = slug.strip("_")
    return slug[:50]  # limit length


def generate_migration(
    ops: list[MigrationOp],
    message: str,
    output_dir: Path,
    revision: str | None = None,
    down_revision: str | None = None,
) -> Path:
    """Generate an Alembic-compatible migration file.

    Args:
        ops: List of migration operations.
        message: Human-readable description.
        output_dir: Base migrations directory (will contain versions/).
        revision: Override revision ID (auto-detected if None).
        down_revision: Override down_revision (auto-detected if None).

    Returns:
        Path to the generated migration file.
    """
    versions_dir = output_dir / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)

    # Auto-detect revision IDs if not provided
    if revision is None:
        revision, auto_down = _next_revision(versions_dir)
        if down_revision is None:
            down_revision = auto_down

    # Render upgrade/downgrade bodies
    upgrade_lines: list[str] = []
    downgrade_lines: list[str] = []

    for op in ops:
        upgrade_lines.extend(op.render_upgrade())
        downgrade_lines.extend(op.render_downgrade())

    if not upgrade_lines:
        upgrade_lines = ["    pass"]
    if not downgrade_lines:
        downgrade_lines = ["    pass"]

    upgrade_body = "\n".join(upgrade_lines)
    downgrade_body = "\n".join(downgrade_lines)

    # Format down_revision
    if down_revision is None:
        down_revision_str = "None"
    else:
        down_revision_str = f'"{down_revision}"'

    # Render template
    content = MIGRATION_TEMPLATE
    content = content.replace("${message}", message)
    content = content.replace("${revision}", revision)
    content = content.replace("${down_revision}", down_revision_str)
    content = content.replace("${upgrade_body}", upgrade_body)
    content = content.replace("${downgrade_body}", downgrade_body)

    # Write file
    slug = _slugify(message)
    filename = f"{revision}_{slug}.py"
    filepath = versions_dir / filename

    with open(filepath, "w") as f:
        f.write(content)

    return filepath
