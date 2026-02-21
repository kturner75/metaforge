"""Database configuration and adapter factory."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from metaforge.persistence.adapter import PersistenceAdapter


@dataclass
class DatabaseConfig:
    """Database connection configuration.

    Supports sqlite:/// and postgresql:// URL schemes.
    """

    url: str

    @classmethod
    def from_env(cls, base_path: Path | None = None) -> DatabaseConfig:
        """Create config from environment variables.

        Resolution order:
        1. DATABASE_URL env var (standard)
        2. METAFORGE_DB_PATH env var (legacy, converted to sqlite:/// URL)
        3. Default: sqlite:///{base_path}/data/metaforge.db
        """
        url = os.environ.get("DATABASE_URL")
        if url:
            return cls(url=url)

        db_path = os.environ.get("METAFORGE_DB_PATH")
        if db_path:
            return cls(url=f"sqlite:///{db_path}")

        if base_path:
            return cls(url=f"sqlite:///{base_path / 'data' / 'metaforge.db'}")

        return cls(url="sqlite:///metaforge.db")

    @property
    def is_sqlite(self) -> bool:
        return self.url.startswith("sqlite")

    @property
    def is_postgresql(self) -> bool:
        return self.url.startswith("postgresql")

    @property
    def sqlalchemy_url(self) -> str:
        """URL suitable for SQLAlchemy engine creation.

        Ensures postgresql:// URLs use the psycopg (v3) driver since
        the project depends on psycopg[binary], not psycopg2.
        """
        if self.url.startswith("postgresql://"):
            return self.url.replace("postgresql://", "postgresql+psycopg://", 1)
        return self.url


def create_adapter(config: DatabaseConfig) -> PersistenceAdapter:
    """Create a persistence adapter based on the database URL scheme.

    Args:
        config: Database configuration with URL.

    Returns:
        A PersistenceAdapter instance (not yet connected).

    Raises:
        ValueError: For unsupported URL schemes.
    """
    if config.is_sqlite:
        from metaforge.persistence.sqlite import SQLiteAdapter

        # Extract path from sqlite:///path
        db_path = config.url.replace("sqlite:///", "")
        if not db_path:
            db_path = ":memory:"
        return SQLiteAdapter(db_path)

    if config.is_postgresql:
        from metaforge.persistence.postgresql import PostgreSQLAdapter

        return PostgreSQLAdapter(config.url)

    raise ValueError(f"Unsupported database URL scheme: {config.url}")
