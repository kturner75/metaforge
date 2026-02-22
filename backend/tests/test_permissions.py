"""Tests for the declarative auth & permissions model (ADR-0010).

Covers:
- can_access_entity() with per-entity access overrides
- apply_field_read_policy() / apply_field_write_policy()
- get_field_access() annotations
- MetadataLoader parsing of permissions YAML block
"""

import textwrap
from pathlib import Path

import pytest
import yaml

from metaforge.validation import UserContext
from metaforge.auth.permissions import (
    can_access_entity,
    apply_field_read_policy,
    apply_field_write_policy,
    get_field_access,
    ROLE_HIERARCHY,
)
from metaforge.metadata.loader import (
    MetadataLoader,
    EntityModel,
    EntityPermissions,
    FieldPermissions,
    FieldDefinition,
    ValidationRules,
    FieldUIConfig,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def make_user(role: str, tenant_id: str = "t1") -> UserContext:
    return UserContext(user_id="u1", tenant_id=tenant_id, roles=[role])


def make_field(name: str, read_only: bool = False, primary_key: bool = False) -> FieldDefinition:
    return FieldDefinition(
        name=name,
        type="text",
        display_name=name.title(),
        primary_key=primary_key,
        read_only=read_only,
        validation=ValidationRules(),
        ui=FieldUIConfig(),
    )


def make_entity(
    name: str = "Deal",
    scope: str = "tenant",
    permissions: "EntityPermissions | None" = None,
    fields: list | None = None,
) -> EntityModel:
    if fields is None:
        fields = [make_field("id", primary_key=True), make_field("title"), make_field("notes")]
    return EntityModel(
        name=name,
        display_name=name,
        plural_name=name + "s",
        primary_key="id",
        fields=fields,
        abbreviation=name[:3].upper(),
        scope=scope,
        permissions=permissions,
    )


# ── can_access_entity — default behaviour unchanged ───────────────────────────


def test_no_user_returns_auth_required():
    allowed, msg = can_access_entity("Contact", "tenant", "read", None)
    assert not allowed
    assert "Authentication" in msg


def test_readonly_can_read_tenant_entity():
    allowed, msg = can_access_entity("Contact", "tenant", "read", make_user("readonly"))
    assert allowed
    assert msg is None


def test_readonly_cannot_create_by_default():
    allowed, msg = can_access_entity("Contact", "tenant", "create", make_user("readonly"))
    assert not allowed


def test_user_can_create_by_default():
    allowed, msg = can_access_entity("Contact", "tenant", "create", make_user("user"))
    assert allowed


def test_user_cannot_delete_by_default():
    allowed, msg = can_access_entity("Contact", "tenant", "delete", make_user("user"))
    assert not allowed


def test_manager_can_delete_by_default():
    allowed, msg = can_access_entity("Contact", "tenant", "delete", make_user("manager"))
    assert allowed


# ── can_access_entity — per-entity overrides ─────────────────────────────────


def test_entity_override_read_requires_higher_role():
    """Entity requires manager to read → readonly and user are blocked."""
    perms = EntityPermissions(read="manager", create="manager", update="manager", delete="admin")
    entity = make_entity(permissions=perms)

    for role in ("readonly", "user"):
        allowed, _ = can_access_entity("Deal", "tenant", "read", make_user(role), entity_model=entity)
        assert not allowed, f"Expected {role} to be denied read"

    allowed, _ = can_access_entity("Deal", "tenant", "read", make_user("manager"), entity_model=entity)
    assert allowed


def test_entity_override_delete_requires_admin():
    perms = EntityPermissions(read="readonly", create="user", update="user", delete="admin")
    entity = make_entity(permissions=perms)

    allowed, _ = can_access_entity("Deal", "tenant", "delete", make_user("manager"), entity_model=entity)
    assert not allowed

    allowed, _ = can_access_entity("Deal", "tenant", "delete", make_user("admin"), entity_model=entity)
    assert allowed


def test_entity_override_create_readonly_allowed():
    """Entity explicitly allows readonly to create (unusual but valid)."""
    perms = EntityPermissions(read="readonly", create="readonly", update="readonly", delete="user")
    entity = make_entity(permissions=perms)

    allowed, _ = can_access_entity("Deal", "tenant", "create", make_user("readonly"), entity_model=entity)
    assert allowed


# ── apply_field_read_policy ───────────────────────────────────────────────────


def test_no_permissions_returns_record_unchanged():
    entity = make_entity(permissions=None)
    record = {"id": "1", "title": "Hello", "notes": "secret"}
    result = apply_field_read_policy(record, entity, make_user("readonly"))
    assert result == record


def test_field_read_policy_strips_restricted_field():
    """Field 'notes' requires user role to read — readonly should not see it."""
    perms = EntityPermissions()
    perms.field_policies["notes"] = FieldPermissions(read="user", write="manager")
    entity = make_entity(permissions=perms)

    record = {"id": "1", "title": "Hello", "notes": "secret"}

    readonly_result = apply_field_read_policy(record, entity, make_user("readonly"))
    assert "notes" not in readonly_result
    assert readonly_result["title"] == "Hello"

    user_result = apply_field_read_policy(record, entity, make_user("user"))
    assert "notes" in user_result


def test_field_read_policy_strips_display_value_too():
    """When a restricted field is stripped, its _display sibling is also removed."""
    perms = EntityPermissions()
    perms.field_policies["companyId"] = FieldPermissions(read="manager", write="manager")
    entity = make_entity(permissions=perms)

    record = {"id": "1", "companyId": "c1", "companyId_display": "Acme Corp"}
    result = apply_field_read_policy(record, entity, make_user("user"))
    assert "companyId" not in result
    assert "companyId_display" not in result


def test_field_read_policy_no_user_strips_restricted():
    """No user context → level 0 → all policies above readonly are blocked."""
    perms = EntityPermissions()
    perms.field_policies["notes"] = FieldPermissions(read="user", write="user")
    entity = make_entity(permissions=perms)

    record = {"id": "1", "notes": "secret"}
    result = apply_field_read_policy(record, entity, None)
    assert "notes" not in result


# ── apply_field_write_policy ──────────────────────────────────────────────────


def test_write_policy_strips_below_write_threshold():
    """'notes' requires manager to write — user payload should have notes removed."""
    perms = EntityPermissions()
    perms.field_policies["notes"] = FieldPermissions(read="user", write="manager")
    entity = make_entity(permissions=perms)

    data = {"title": "Hello", "notes": "My note"}
    user_result = apply_field_write_policy(data, entity, make_user("user"))
    assert "notes" not in user_result
    assert user_result["title"] == "Hello"

    manager_result = apply_field_write_policy(data, entity, make_user("manager"))
    assert "notes" in manager_result


def test_write_policy_strips_when_read_blocked():
    """Cannot write a field you cannot even read."""
    perms = EntityPermissions()
    perms.field_policies["salary"] = FieldPermissions(read="manager", write="manager")
    entity = make_entity(permissions=perms)

    data = {"title": "Hello", "salary": "100000"}
    result = apply_field_write_policy(data, entity, make_user("user"))
    assert "salary" not in result


def test_write_policy_no_permissions_unchanged():
    entity = make_entity(permissions=None)
    data = {"title": "Hello", "notes": "ok"}
    assert apply_field_write_policy(data, entity, make_user("readonly")) == data


# ── get_field_access ──────────────────────────────────────────────────────────


def test_get_field_access_no_policy_returns_full_access():
    field = make_field("title")
    entity = make_entity(permissions=None)
    access = get_field_access(field, make_user("readonly"), entity)
    assert access["read"] is True
    assert access["write"] is True


def test_get_field_access_readonly_field_write_false():
    field = make_field("fullName", read_only=True)
    entity = make_entity(permissions=None)
    access = get_field_access(field, make_user("admin"), entity)
    assert access["read"] is True
    assert access["write"] is False


def test_get_field_access_policy_restricts_read():
    field = make_field("notes")
    perms = EntityPermissions()
    perms.field_policies["notes"] = FieldPermissions(read="user", write="manager")
    entity = make_entity(permissions=perms)

    readonly_access = get_field_access(field, make_user("readonly"), entity)
    assert readonly_access["read"] is False
    assert readonly_access["write"] is False  # can't write what you can't read

    user_access = get_field_access(field, make_user("user"), entity)
    assert user_access["read"] is True
    assert user_access["write"] is False  # read ✓ but write requires manager

    manager_access = get_field_access(field, make_user("manager"), entity)
    assert manager_access["read"] is True
    assert manager_access["write"] is True


def test_get_field_access_no_user_blocks_non_readonly_policies():
    field = make_field("notes")
    perms = EntityPermissions()
    perms.field_policies["notes"] = FieldPermissions(read="user", write="manager")
    entity = make_entity(permissions=perms)

    access = get_field_access(field, None, entity)
    assert access["read"] is False
    assert access["write"] is False


# ── MetadataLoader — permissions YAML parsing ─────────────────────────────────


@pytest.fixture
def tmp_metadata_dir(tmp_path: Path) -> Path:
    blocks_dir = tmp_path / "blocks"
    blocks_dir.mkdir()
    entities_dir = tmp_path / "entities"
    entities_dir.mkdir()
    return tmp_path


def write_entity_yaml(entities_dir: Path, name: str, content: str) -> None:
    (entities_dir / f"{name.lower()}.yaml").write_text(textwrap.dedent(content))


def test_loader_parses_entity_permissions(tmp_metadata_dir: Path):
    write_entity_yaml(
        tmp_metadata_dir / "entities",
        "Deal",
        """
        entity: Deal
        abbreviation: DL
        scope: tenant
        permissions:
          access:
            read: readonly
            create: user
            update: user
            delete: admin
          fieldPolicies:
            - field: commission
              read: manager
              write: admin
        fields:
          - name: id
            type: id
            primaryKey: true
          - name: title
            type: name
          - name: commission
            type: currency
        """,
    )
    loader = MetadataLoader(tmp_metadata_dir)
    loader.load_all()

    entity = loader.get_entity("Deal")
    assert entity is not None
    assert entity.permissions is not None

    perms = entity.permissions
    assert perms.read == "readonly"
    assert perms.create == "user"
    assert perms.delete == "admin"

    assert "commission" in perms.field_policies
    fp = perms.field_policies["commission"]
    assert fp.read == "manager"
    assert fp.write == "admin"


def test_loader_entity_without_permissions_has_none(tmp_metadata_dir: Path):
    write_entity_yaml(
        tmp_metadata_dir / "entities",
        "Simple",
        """
        entity: Simple
        abbreviation: SI
        fields:
          - name: id
            type: id
            primaryKey: true
          - name: name
            type: name
        """,
    )
    loader = MetadataLoader(tmp_metadata_dir)
    loader.load_all()

    entity = loader.get_entity("Simple")
    assert entity is not None
    assert entity.permissions is None


def test_loader_parses_field_level_permissions(tmp_metadata_dir: Path):
    """Permissions declared directly on a field are promoted to entity_perms."""
    write_entity_yaml(
        tmp_metadata_dir / "entities",
        "Employee",
        """
        entity: Employee
        abbreviation: EM
        fields:
          - name: id
            type: id
            primaryKey: true
          - name: name
            type: name
          - name: salary
            type: currency
            permissions:
              read: manager
              write: admin
        """,
    )
    loader = MetadataLoader(tmp_metadata_dir)
    loader.load_all()

    entity = loader.get_entity("Employee")
    assert entity is not None
    # No top-level permissions block, but field-level permissions present
    assert entity.permissions is not None
    assert "salary" in entity.permissions.field_policies
    fp = entity.permissions.field_policies["salary"]
    assert fp.read == "manager"
    assert fp.write == "admin"
