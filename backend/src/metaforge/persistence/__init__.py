"""Persistence layer - database adapters and operations."""

from metaforge.persistence.adapter import PersistenceAdapter
from metaforge.persistence.config import DatabaseConfig, create_adapter

__all__ = ["PersistenceAdapter", "DatabaseConfig", "create_adapter"]
