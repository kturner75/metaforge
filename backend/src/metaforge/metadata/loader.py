"""Load and resolve entity metadata from YAML files."""

from pathlib import Path
from dataclasses import dataclass, field
from typing import Any
import yaml


@dataclass
class FieldUI:
    component: str | None = None
    format: str | None = None
    mode: str | None = None
    alignment: str | None = None
    visible: bool = True


@dataclass
class FieldUIConfig:
    display: FieldUI = field(default_factory=FieldUI)
    edit: FieldUI = field(default_factory=FieldUI)
    filter: FieldUI = field(default_factory=FieldUI)
    grid: FieldUI = field(default_factory=FieldUI)


@dataclass
class ValidationRules:
    required: bool = False
    min: float | None = None
    max: float | None = None
    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None


@dataclass
class RelationConfig:
    """Configuration for a relation field."""

    entity: str  # The related entity name
    display_field: str = "name"  # Field or expression for display
    on_delete: str = "restrict"  # "restrict" | "cascade" | "setNull"


@dataclass
class FieldDefinition:
    name: str
    type: str
    display_name: str
    primary_key: bool = False
    read_only: bool = False
    default: Any = None
    auto: str | None = None  # "now", "context.userId", "context.tenantId"
    options: list[dict] | None = None
    validation: ValidationRules = field(default_factory=ValidationRules)
    ui: FieldUIConfig = field(default_factory=FieldUIConfig)
    relation: RelationConfig | None = None


@dataclass
class ValidatorConfig:
    """Validator definition from YAML metadata."""

    type: str
    params: dict[str, Any] = field(default_factory=dict)
    message: str = ""
    code: str = ""
    severity: str = "error"
    on: list[str] = field(default_factory=lambda: ["create", "update"])
    when: str | None = None


@dataclass
class DefaultConfig:
    """Default definition from YAML metadata."""

    field: str
    value: Any = None
    expression: str | None = None
    policy: str = "default"  # "default" or "overwrite"
    when: str | None = None
    on: list[str] = field(default_factory=lambda: ["create", "update"])


@dataclass
class HookConfig:
    """Hook definition from YAML metadata."""

    name: str
    on: list[str] = field(default_factory=lambda: ["create", "update"])
    when: str | None = None
    description: str = ""


@dataclass
class EntityModel:
    name: str
    display_name: str
    plural_name: str
    primary_key: str
    fields: list[FieldDefinition]
    abbreviation: str = ""  # 2-5 chars, uppercase, globally unique
    auditable: bool = False
    scope: str = "tenant"  # "tenant" or "global"
    validators: list[ValidatorConfig] = field(default_factory=list)
    defaults: list[DefaultConfig] = field(default_factory=list)
    hooks: dict[str, list[HookConfig]] = field(default_factory=dict)
    label_field: str | None = None  # Field used as human-readable record label (breadcrumbs, titles)


class MetadataLoader:
    """Loads entity and block definitions from YAML files."""

    def __init__(self, metadata_path: Path):
        self.metadata_path = metadata_path
        self.entities: dict[str, EntityModel] = {}
        self.blocks: dict[str, list[dict]] = {}

    def load_all(self) -> None:
        """Load all blocks and entities."""
        self._load_blocks()
        self._load_entities()
        self._validate_abbreviations()

    def _validate_abbreviations(self) -> None:
        """Validate entity abbreviations are unique and properly formatted."""
        seen: dict[str, str] = {}  # abbreviation -> entity name

        for entity_name, entity in self.entities.items():
            abbrev = entity.abbreviation

            # Validate format: 2-5 uppercase alphanumeric characters
            if not abbrev:
                raise ValueError(f"Entity '{entity_name}' has no abbreviation")
            if len(abbrev) < 2 or len(abbrev) > 5:
                raise ValueError(
                    f"Entity '{entity_name}' abbreviation '{abbrev}' must be 2-5 characters"
                )
            if not abbrev.isalnum():
                raise ValueError(
                    f"Entity '{entity_name}' abbreviation '{abbrev}' must be alphanumeric"
                )

            # Check uniqueness
            if abbrev in seen:
                raise ValueError(
                    f"Duplicate abbreviation '{abbrev}' used by both "
                    f"'{seen[abbrev]}' and '{entity_name}'"
                )
            seen[abbrev] = entity_name

    def _load_blocks(self) -> None:
        """Load reusable block definitions."""
        blocks_path = self.metadata_path / "blocks"
        if not blocks_path.exists():
            return

        for yaml_file in blocks_path.glob("*.yaml"):
            with open(yaml_file) as f:
                data = yaml.safe_load(f)
                if data and "block" in data:
                    self.blocks[data["block"]] = data.get("fields", [])

    def _load_entities(self) -> None:
        """Load entity definitions."""
        entities_path = self.metadata_path / "entities"
        if not entities_path.exists():
            return

        for yaml_file in entities_path.glob("*.yaml"):
            with open(yaml_file) as f:
                data = yaml.safe_load(f)
                if data and "entity" in data:
                    entity = self._resolve_entity(data)
                    self.entities[entity.name] = entity

    def _resolve_entity(self, data: dict) -> EntityModel:
        """Resolve an entity definition, expanding blocks."""
        name = data["entity"]

        # Collect fields
        all_fields: list[dict] = []

        # Expand included blocks
        for include in data.get("includes", []):
            block_name = include["block"]
            prefix = include.get("prefix", "")

            if block_name in self.blocks:
                for block_field in self.blocks[block_name]:
                    field_copy = block_field.copy()
                    if prefix:
                        field_copy["name"] = prefix + field_copy["name"]
                    all_fields.append(field_copy)

        # Add entity's own fields
        all_fields.extend(data.get("fields", []))

        # Convert to FieldDefinition objects
        fields = [self._resolve_field(f) for f in all_fields]

        # Find primary key
        primary_key = "id"
        for f in fields:
            if f.primary_key:
                primary_key = f.name
                break

        # Parse validators
        validators = [
            self._resolve_validator(v) for v in data.get("validators", [])
        ]

        # Parse defaults
        defaults = [
            self._resolve_default(d) for d in data.get("defaults", [])
        ]

        # Parse or generate abbreviation
        abbreviation = data.get("abbreviation")
        if not abbreviation:
            # Auto-generate from name (first 3 chars, uppercase)
            abbreviation = name[:3].upper()
        else:
            abbreviation = abbreviation.upper()

        # Parse hooks
        hooks = self._resolve_hooks(data.get("hooks", {}))

        # Determine label field: explicit YAML value, or auto-detect first 'name'-type field
        label_field: str | None = data.get("labelField")
        if not label_field:
            for f in fields:
                if f.type == "name":
                    label_field = f.name
                    break

        return EntityModel(
            name=name,
            display_name=data.get("displayName", name),
            plural_name=data.get("pluralName", name + "s"),
            primary_key=primary_key,
            fields=fields,
            abbreviation=abbreviation,
            auditable=data.get("auditable", False),
            scope=data.get("scope", "tenant"),
            validators=validators,
            defaults=defaults,
            hooks=hooks,
            label_field=label_field,
        )

    def _resolve_field(self, data: dict) -> FieldDefinition:
        """Convert field dict to FieldDefinition."""
        name = data["name"]
        field_type = data.get("type", "string")

        # Generate display name from field name
        display_name = data.get("displayName", self._to_display_name(name))

        # Parse validation
        validation_data = data.get("validation", {})
        validation = ValidationRules(
            required=validation_data.get("required", False),
            min=validation_data.get("min"),
            max=validation_data.get("max"),
            min_length=validation_data.get("minLength"),
            max_length=validation_data.get("maxLength"),
            pattern=validation_data.get("pattern"),
        )

        # Parse relation config
        relation_data = data.get("relation")
        relation = None
        if relation_data:
            relation = RelationConfig(
                entity=relation_data.get("entity", ""),
                display_field=relation_data.get("displayField", "name"),
                on_delete=relation_data.get("onDelete", "restrict"),
            )

        return FieldDefinition(
            name=name,
            type=field_type,
            display_name=display_name,
            primary_key=data.get("primaryKey", False),
            read_only=data.get("readOnly", False),
            default=data.get("default"),
            auto=data.get("auto"),
            options=data.get("options"),
            validation=validation,
            relation=relation,
        )

    def _get_on(self, data: dict, default: list[str] | None = None) -> list[str]:
        """Extract the 'on' field from a YAML dict.

        PyYAML parses the bare key `on:` as boolean True, so we check
        both the string key "on" and the boolean key True.
        """
        if default is None:
            default = ["create", "update"]
        on = data.get("on") or data.get(True, default)
        if isinstance(on, str):
            on = [on]
        return on

    def _resolve_validator(self, data: dict) -> ValidatorConfig:
        """Convert validator dict to ValidatorConfig."""
        return ValidatorConfig(
            type=data["type"],
            params=data.get("params", {}),
            message=data.get("message", ""),
            code=data.get("code", ""),
            severity=data.get("severity", "error"),
            on=self._get_on(data),
            when=data.get("when"),
        )

    def _resolve_default(self, data: dict) -> DefaultConfig:
        """Convert default dict to DefaultConfig."""
        return DefaultConfig(
            field=data["field"],
            value=data.get("value"),
            expression=data.get("expression"),
            policy=data.get("policy", "default"),
            when=data.get("when"),
            on=self._get_on(data),
        )

    def _resolve_hooks(self, data: dict) -> dict[str, list[HookConfig]]:
        """Convert hooks dict from YAML to HookConfig lists by hook point."""
        valid_points = ("beforeSave", "afterSave", "afterCommit", "beforeDelete")
        hooks: dict[str, list[HookConfig]] = {}
        for point, hook_list in data.items():
            if point not in valid_points:
                continue
            if isinstance(hook_list, list):
                hooks[point] = [self._resolve_hook(h) for h in hook_list]
        return hooks

    def _resolve_hook(self, data: dict) -> HookConfig:
        """Convert hook dict to HookConfig."""
        return HookConfig(
            name=data["name"],
            on=self._get_on(data),
            when=data.get("when"),
            description=data.get("description", ""),
        )

    def _to_display_name(self, name: str) -> str:
        """Convert camelCase to Title Case."""
        result = []
        for i, char in enumerate(name):
            if char.isupper() and i > 0:
                result.append(" ")
            result.append(char)
        return "".join(result).title()

    def get_entity(self, name: str) -> EntityModel | None:
        """Get a resolved entity by name."""
        return self.entities.get(name)

    def list_entities(self) -> list[str]:
        """List all entity names."""
        return list(self.entities.keys())
