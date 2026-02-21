"""
metadata/validator.py — JSON Schema validation for MetaForge YAML metadata files.

Validates entity, block, view, and screen YAML files against JSON Schemas.

Usage:
    from metaforge.metadata.validator import validate_metadata_dir, validate_yaml_file

    issues = validate_metadata_dir(Path("metadata"))
    for issue in issues:
        print(issue)

PyYAML quirk: the bare key ``on:`` is parsed as boolean ``True``, not the string
``"on"``.  We preprocess loaded dicts to rename that key before schema validation.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

try:
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import ValidationError
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012

    _JSONSCHEMA_AVAILABLE = True
except ImportError:  # pragma: no cover
    _JSONSCHEMA_AVAILABLE = False

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------

_SCHEMAS_DIR = Path(__file__).parent / "schemas"

# Map subdirectory name → schema filename
_SUBDIR_SCHEMA: dict[str, str] = {
    "entities": "entity.schema.json",
    "blocks": "block.schema.json",
    "views": "view.schema.json",
    "screens": "screen.schema.json",
}


@dataclass
class ValidationIssue:
    """A single validation finding for a metadata YAML file."""

    file: Path
    message: str
    path: str = ""          # JSON pointer path within the document, e.g. "entity/fields/0"
    severity: str = "error" # "error" | "warning"

    def __str__(self) -> str:
        loc = f" at {self.path}" if self.path else ""
        return f"[{self.severity.upper()}] {self.file}{loc}: {self.message}"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_schema(name: str) -> dict[str, Any]:
    schema_path = _SCHEMAS_DIR / name
    with schema_path.open() as fh:
        return json.load(fh)


def _load_registry() -> Registry:
    """Build a jsonschema Registry containing all MetaForge schemas."""
    if not _JSONSCHEMA_AVAILABLE:
        raise ImportError("jsonschema>=4.18.0 is required for metadata validation")

    schema_names = [
        "_defs.schema.json",
        "entity.schema.json",
        "block.schema.json",
        "view.schema.json",
        "screen.schema.json",
    ]
    resources = []
    for name in schema_names:
        schema = _load_schema(name)
        resources.append(
            (schema["$id"], Resource(contents=schema, specification=DRAFT202012))
        )
    return Registry().with_resources(resources)


def _preprocess_on_key(obj: Any) -> Any:
    """
    Recursively rename the boolean key ``True`` → ``"on"`` in a parsed YAML dict.

    PyYAML parses the bare key ``on:`` as boolean ``True`` (YAML 1.1 spec).
    The JSON Schema uses the string key ``"on"`` so we must fix this before
    validation.
    """
    if isinstance(obj, dict):
        result: dict[Any, Any] = {}
        for k, v in obj.items():
            new_key = "on" if k is True else k
            result[new_key] = _preprocess_on_key(v)
        return result
    if isinstance(obj, list):
        return [_preprocess_on_key(item) for item in obj]
    return obj


def _json_path(error: ValidationError) -> str:
    """Convert a jsonschema ValidationError path to a readable string."""
    parts = []
    for p in error.absolute_path:
        if isinstance(p, int):
            parts.append(f"[{p}]")
        else:
            parts.append(str(p))
    return "/".join(parts).replace("/[", "[")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_yaml_file(
    yaml_path: Path,
    schema_name: str,
    *,
    registry: Registry | None = None,
) -> list[ValidationIssue]:
    """
    Validate a single YAML file against the named schema.

    Args:
        yaml_path:   Path to the YAML file to validate.
        schema_name: Filename of the schema (e.g. ``"entity.schema.json"``).
        registry:    Pre-built schema registry.  Built automatically if omitted.

    Returns:
        A list of :class:`ValidationIssue` objects (empty on success).
    """
    if not _JSONSCHEMA_AVAILABLE:
        logger.warning("jsonschema not installed — skipping validation of %s", yaml_path)
        return []

    issues: list[ValidationIssue] = []

    # 1. Parse YAML
    try:
        with yaml_path.open() as fh:
            raw = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        return [ValidationIssue(file=yaml_path, message=f"YAML parse error: {exc}")]

    if raw is None:
        return [
            ValidationIssue(file=yaml_path, message="File is empty or contains only whitespace")
        ]

    # 2. Pre-process PyYAML quirks
    doc = _preprocess_on_key(raw)

    # 3. Load schema + registry
    if registry is None:
        registry = _load_registry()

    schema = _load_schema(schema_name)
    validator = Draft202012Validator(schema, registry=registry)

    # 4. Collect validation errors
    for error in sorted(validator.iter_errors(doc), key=lambda e: e.path):
        issues.append(
            ValidationIssue(
                file=yaml_path,
                message=error.message,
                path=_json_path(error),
            )
        )

    return issues


def validate_metadata_dir(
    metadata_dir: Path,
    *,
    strict: bool = False,
) -> list[ValidationIssue]:
    """
    Validate all YAML files under *metadata_dir*.

    Walks ``entities/``, ``blocks/``, ``views/``, and ``screens/`` subdirectories,
    validating each ``.yaml`` file against the appropriate JSON Schema.

    Args:
        metadata_dir: Root metadata directory (contains ``entities/``, ``blocks/``, etc.).
        strict:       If ``True``, warnings are escalated to errors (reserved for future use).

    Returns:
        A flat list of :class:`ValidationIssue` objects across all files.
        Empty list means all files are valid.
    """
    if not _JSONSCHEMA_AVAILABLE:
        logger.warning("jsonschema not installed — skipping metadata validation")
        return []

    if not metadata_dir.is_dir():
        return [
            ValidationIssue(
                file=metadata_dir,
                message=f"Metadata directory does not exist: {metadata_dir}",
            )
        ]

    # Build registry once — shared across all file validations
    try:
        registry = _load_registry()
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        return [
            ValidationIssue(
                file=_SCHEMAS_DIR,
                message=f"Failed to load JSON Schema files: {exc}",
            )
        ]

    all_issues: list[ValidationIssue] = []

    for subdir, schema_name in _SUBDIR_SCHEMA.items():
        target = metadata_dir / subdir
        if not target.is_dir():
            continue
        for yaml_file in sorted(target.glob("*.yaml")):
            file_issues = validate_yaml_file(yaml_file, schema_name, registry=registry)
            if strict:
                for issue in file_issues:
                    if issue.severity == "warning":
                        issue.severity = "error"
            all_issues.extend(file_issues)

    return all_issues
