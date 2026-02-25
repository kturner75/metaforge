"""Draft persistence adapter backed by a separate SQLite draft.db.

Draft entities are transient dev-time records that live outside the main
application database. Using a dedicated file ensures they never pollute
production data and can be discarded cleanly on dismiss.
"""

from pathlib import Path

from metaforge.persistence.sqlite import SQLiteAdapter


class DraftAdapter(SQLiteAdapter):
    """SQLiteAdapter targeting a separate draft.db for isolated draft entity storage.

    Subclasses SQLiteAdapter with no behavioral changes — the only distinction
    is the database file it connects to. The named subclass makes intent clear
    at call sites (e.g. ``DraftAdapter.from_base_path(base_path)``).
    """

    @classmethod
    def from_base_path(cls, base_path: Path) -> "DraftAdapter":
        """Create a DraftAdapter using the standard draft.db path.

        Places draft.db alongside metaforge.db in ``{base_path}/data/``.
        Creates the directory if it doesn't exist.
        """
        draft_path = base_path / "data" / "draft.db"
        draft_path.parent.mkdir(parents=True, exist_ok=True)
        return cls(str(draft_path))
