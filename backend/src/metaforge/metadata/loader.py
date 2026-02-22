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
    permissions: "FieldPermissions | None" = None


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
class FieldPermissions:
    """Per-field access control policy."""

    read: str = "readonly"   # Minimum role to read this field
    write: str = "readonly"  # Minimum role to write this field


@dataclass
class EntityPermissions:
    """Entity-level and field-level permission configuration."""

    read: str = "readonly"
    create: str = "user"
    update: str = "user"
    delete: str = "manager"
    # Field policies keyed by field name for O(1) lookup
    field_policies: dict[str, FieldPermissions] = field(default_factory=dict)


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
    permissions: "EntityPermissions | None" = None


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

        # Parse entity-level permissions (optional)
        entity_permissions = self._resolve_entity_permissions(data.get("permissions"), fields)

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
            permissions=entity_permissions,
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

        # Parse field-level permissions (optional)
        perm_data = data.get("permissions")
        field_permissions = None
        if perm_data:
            field_permissions = FieldPermissions(
                read=perm_data.get("read", "readonly"),
                write=perm_data.get("write", "readonly"),
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
            permissions=field_permissions,
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

    def _resolve_entity_permissions(
        self,
        data: dict | None,
        fields: list[FieldDefinition],
    ) -> "EntityPermissions | None":
        """Parse the entity-level permissions block from YAML.

        Returns None only when no permissions are configured at either the
        entity level or individual field level.
        """
        # Check if any field has inline permissions
        fields_with_perms = [f for f in fields if f.permissions]

        if not data and not fields_with_perms:
            return None

        # Parse access block (use defaults when block absent)
        access = data.get("access", {}) if data else {}
        entity_perms = EntityPermissions(
            read=access.get("read", "readonly"),
            create=access.get("create", "user"),
            update=access.get("update", "user"),
            delete=access.get("delete", "manager"),
        )

        # Parse fieldPolicies list into a dict keyed by field name
        for policy in (data.get("fieldPolicies", []) if data else []):
            field_name = policy.get("field")
            if not field_name:
                continue
            entity_perms.field_policies[field_name] = FieldPermissions(
                read=policy.get("read", "readonly"),
                write=policy.get("write", "readonly"),
            )

        # Promote inline field-level permissions (entity-level block takes precedence)
        for f in fields_with_perms:
            if f.name not in entity_perms.field_policies:
                entity_perms.field_policies[f.name] = f.permissions  # type: ignore[arg-type]

        return entity_perms

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
