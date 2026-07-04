"""Sandbox service: draft entity lifecycle management.

Implements the four sandbox operations described in ADR-0013:
  - draft_entity   — write YAML to drafts/, hot-reload, create draft table
  - update_draft_entity — replace YAML, drop+recreate draft table, hot-reload
  - promote_entity — move YAML to entities/, create prod table, drop draft, reload
  - dismiss_entity — delete YAML, drop draft table, reload
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

import yaml

if TYPE_CHECKING:
    from metaforge.mcp.bootstrap import MetaForgeServices


class SandboxService:
    """Manages the lifecycle of draft entities."""

    def __init__(
        self,
        services: MetaForgeServices,
        base_path: Path,
        reload_fn: Callable[[], None] | None = None,
    ) -> None:
        self._svc = services
        self._base_path = base_path
        self._drafts_dir = base_path / "metadata" / "drafts"
        self._entities_dir = base_path / "metadata" / "entities"
        self._reload_fn = reload_fn

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def draft_entity(self, yaml_str: str) -> dict[str, Any]:
        """Write a draft entity YAML to metadata/drafts/ and hot-reload.

        Args:
            yaml_str: Full entity YAML string. Must have an `entity:` key.

        Returns:
            Dict with ``entity``, ``isDraft``, ``yaml_path``, ``fields``, ``reloaded``.
        """
        try:
            parsed = yaml.safe_load(yaml_str)
        except yaml.YAMLError as e:
            return {"error": f"Invalid YAML: {e}"}

        if not isinstance(parsed, dict):
            return {"error": "YAML must be a mapping with an 'entity:' key"}

        entity_name = parsed.get("entity") or parsed.get("name")
        if not entity_name:
            return {"error": "YAML must contain an 'entity:' key"}

        if not parsed.get("abbreviation"):
            return {"error": "YAML must contain an 'abbreviation:' key"}

        # Reject if a production entity with this name already exists
        existing = self._svc.metadata_loader.get_entity(entity_name)
        if existing and not existing.is_draft:
            return {
                "error": (
                    f"Entity '{entity_name}' already exists in production. "
                    "Use update_record / migrations to modify it."
                )
            }

        self._drafts_dir.mkdir(parents=True, exist_ok=True)
        yaml_path = self._drafts_dir / f"{entity_name.lower()}.yaml"
        yaml_path.write_text(yaml_str)

        reloaded = self._reload()

        entity = self._svc.metadata_loader.get_entity(entity_name)
        if not entity:
            return {"error": f"Entity '{entity_name}' failed to load after writing YAML"}

        return {
            "entity": entity_name,
            "isDraft": True,
            "yaml_path": str(yaml_path.relative_to(self._base_path)),
            "fields": [
                {"name": f.name, "type": f.type, "displayName": f.display_name}
                for f in entity.fields
                if not f.primary_key
            ],
            "reloaded": reloaded,
        }

    def update_draft_entity(self, name: str, yaml_str: str) -> dict[str, Any]:
        """Replace a draft entity YAML and recreate its table.

        Draft data is cleared because the schema may have changed.

        Args:
            name: Entity name (e.g. ``"Deal"``).
            yaml_str: Updated full entity YAML string.

        Returns:
            Dict with ``entity``, ``fields``, ``note``.
        """
        entity = self._svc.metadata_loader.get_entity(name)
        if not entity:
            return {"error": f"Entity '{name}' not found"}
        if not entity.is_draft:
            return {
                "error": (
                    f"Entity '{name}' is not a draft. "
                    "Use production migration tools to modify it."
                )
            }

        try:
            parsed = yaml.safe_load(yaml_str)
        except yaml.YAMLError as e:
            return {"error": f"Invalid YAML: {e}"}

        if not isinstance(parsed, dict):
            return {"error": "YAML must be a mapping with an 'entity:' key"}

        if not (parsed.get("entity") or parsed.get("name")):
            return {"error": "YAML must contain an 'entity:' key"}

        yaml_path = self._drafts_dir / f"{name.lower()}.yaml"
        if not yaml_path.exists():
            return {"error": f"Draft YAML not found: {yaml_path}"}

        # Drop the old table so initialize_entity recreates it with the new schema
        self._drop_draft_table(name)

        yaml_path.write_text(yaml_str)
        self._reload()

        updated = self._svc.metadata_loader.get_entity(name)
        if not updated:
            return {"error": f"Entity '{name}' failed to load after update"}

        return {
            "entity": name,
            "fields": [
                {"name": f.name, "type": f.type, "displayName": f.display_name}
                for f in updated.fields
                if not f.primary_key
            ],
            "note": "Draft data was cleared due to schema change",
        }

    def promote_entity(
        self, name: str, generate_doc: bool = False
    ) -> dict[str, Any]:
        """Promote a draft entity to production.

        Steps:
        1. Copy YAML from drafts/ → entities/
        2. Create table in production DB (``initialize_entity``)
        3. Delete draft YAML + drop draft table
        4. Hot-reload (entity now live, DRAFT badge disappears)
        5. Optionally write docs/entities/{name}.md

        Args:
            name: Entity name.
            generate_doc: If True, write a Markdown reference doc.

        Returns:
            Dict with ``promoted``, ``entity``, ``yaml_path``, ``doc_path``.
        """
        entity = self._svc.metadata_loader.get_entity(name)
        if not entity:
            return {"error": f"Entity '{name}' not found"}
        if not entity.is_draft:
            return {"error": f"Entity '{name}' is not a draft"}

        draft_yaml = self._drafts_dir / f"{name.lower()}.yaml"
        if not draft_yaml.exists():
            return {"error": f"Draft YAML not found: {draft_yaml}"}

        # 1. Copy to entities/
        self._entities_dir.mkdir(parents=True, exist_ok=True)
        prod_yaml = self._entities_dir / f"{name.lower()}.yaml"
        prod_yaml.write_text(draft_yaml.read_text())

        # 2. Create table in production DB
        self._svc.db.initialize_entity(entity)

        # 3. Clean up draft
        draft_yaml.unlink()
        self._drop_draft_table(name)

        # 4. Reload so the entity is live and no longer marked DRAFT
        self._reload()

        # 5. Optional reference doc
        doc_path: Path | None = None
        if generate_doc:
            live_entity = self._svc.metadata_loader.get_entity(name)
            doc_path = self._generate_doc(name, live_entity or entity)

        return {
            "promoted": True,
            "entity": name,
            "yaml_path": str(prod_yaml.relative_to(self._base_path)),
            "doc_generated": generate_doc,
            "doc_path": (
                str(doc_path.relative_to(self._base_path)) if doc_path else None
            ),
        }

    def dismiss_entity(self, name: str) -> dict[str, Any]:
        """Delete a draft entity, its YAML, and all draft data.

        Args:
            name: Entity name.

        Returns:
            Dict with ``dismissed``, ``entity``.
        """
        entity = self._svc.metadata_loader.get_entity(name)
        if not entity:
            return {"error": f"Entity '{name}' not found"}
        if not entity.is_draft:
            return {"error": f"Entity '{name}' is not a draft"}

        draft_yaml = self._drafts_dir / f"{name.lower()}.yaml"
        if draft_yaml.exists():
            draft_yaml.unlink()

        self._drop_draft_table(name)
        self._reload()

        return {"dismissed": True, "entity": name}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _reload(self) -> dict[str, int]:
        if self._reload_fn is not None:
            self._reload_fn()
            return {}
        else:
            from metaforge.mcp.bootstrap import reload_metadata

            return reload_metadata(self._svc)

    def _drop_draft_table(self, entity_name: str) -> None:
        """Drop the draft table for an entity (idempotent)."""
        from metaforge.persistence.sqlite import SQLiteAdapter

        if isinstance(self._svc.draft_db, SQLiteAdapter):
            self._svc.draft_db.drop_entity_table(entity_name)

    def _generate_doc(self, name: str, entity: Any) -> Path:
        """Write a Markdown reference doc for the entity to docs/entities/."""
        docs_dir = self._base_path / "docs" / "entities"
        docs_dir.mkdir(parents=True, exist_ok=True)
        doc_path = docs_dir / f"{name.lower()}.md"

        lines = [
            f"# {entity.display_name}",
            "",
            f"*Auto-generated from `metadata/entities/{name.lower()}.yaml`*",
            "",
            "## Fields",
            "",
            "| Field | Type | Required | Notes |",
            "|-------|------|----------|-------|",
        ]

        for field in entity.fields:
            if field.primary_key:
                continue
            required = "yes" if field.validation.required else "no"
            notes_parts: list[str] = []
            if field.options:
                labels = [
                    (o.get("label") or o.get("value") or str(o))
                    if isinstance(o, dict)
                    else str(o)
                    for o in field.options
                ]
                notes_parts.append(f"Options: {', '.join(labels)}")
            if field.relation:
                notes_parts.append(f"→ {field.relation.entity}")
            lines.append(
                f"| {field.name} | {field.type} | {required} | {' '.join(notes_parts)} |"
            )

        if entity.validators:
            lines += ["", "## Validations", ""]
            for v in entity.validators:
                lines.append(f"- {v.name}")

        doc_path.write_text("\n".join(lines) + "\n")
        return doc_path
