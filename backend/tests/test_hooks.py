"""Tests for the entity lifecycle hook system (ADR-0009)."""

import logging
import os
import pytest
from pathlib import Path
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient

from metaforge.hooks import (
    HookContext,
    HookDefinition,
    HookRegistry,
    HookResult,
    HookService,
    VALID_HOOK_POINTS,
    compute_changes,
    hook,
    register_builtin_hooks,
)
from metaforge.hooks.registry import HookFn
from metaforge.metadata.loader import EntityModel, HookConfig, MetadataLoader
from metaforge.validation.types import Operation, UserContext
from metaforge.validation.integration import hook_config_to_definition


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def clear_hook_registry():
    """Clear hook registry before and after each test."""
    HookRegistry.clear()
    yield
    HookRegistry.clear()


@pytest.fixture
def hook_service():
    return HookService()


@pytest.fixture
def base_context():
    """A basic HookContext for tests."""
    return HookContext(
        entity_name="Contact",
        operation=Operation.CREATE,
        record={"id": "C001", "firstName": "John", "lastName": "Doe", "status": "active"},
        original=None,
        changes=None,
        user_context=UserContext(user_id="U001", tenant_id="T001", roles=["user"]),
    )


@pytest.fixture
def update_context():
    """A HookContext for update operations."""
    original = {"id": "C001", "firstName": "John", "lastName": "Doe", "status": "active"}
    record = {"id": "C001", "firstName": "Jane", "lastName": "Doe", "status": "inactive"}
    return HookContext(
        entity_name="Contact",
        operation=Operation.UPDATE,
        record=record,
        original=original,
        changes=compute_changes(record, original),
        user_context=UserContext(user_id="U001", tenant_id="T001", roles=["user"]),
    )


# =============================================================================
# compute_changes tests
# =============================================================================


class TestComputeChanges:
    def test_returns_none_for_create(self):
        assert compute_changes({"a": 1}, None) is None

    def test_detects_changed_fields(self):
        original = {"a": 1, "b": 2, "c": 3}
        record = {"a": 1, "b": 99, "c": 3}
        changes = compute_changes(record, original)
        assert changes == {"b": 99}

    def test_detects_new_fields(self):
        original = {"a": 1}
        record = {"a": 1, "b": 2}
        changes = compute_changes(record, original)
        assert changes == {"b": 2}

    def test_empty_when_no_changes(self):
        record = {"a": 1, "b": 2}
        changes = compute_changes(record, record)
        assert changes == {}

    def test_multiple_changes(self):
        original = {"a": 1, "b": 2, "c": 3}
        record = {"a": 10, "b": 20, "c": 3}
        changes = compute_changes(record, original)
        assert changes == {"a": 10, "b": 20}


# =============================================================================
# HookRegistry tests
# =============================================================================


class TestHookRegistry:
    def test_register_and_get(self):
        async def my_hook(ctx):
            return None

        HookRegistry.register("myHook", my_hook)
        assert HookRegistry.get("myHook") is my_hook

    def test_register_idempotent(self):
        async def hook_a(ctx):
            return None

        async def hook_b(ctx):
            return None

        HookRegistry.register("myHook", hook_a)
        HookRegistry.register("myHook", hook_b)  # should be no-op
        assert HookRegistry.get("myHook") is hook_a

    def test_get_unknown_raises(self):
        with pytest.raises(ValueError, match="not registered"):
            HookRegistry.get("nonExistent")

    def test_is_registered(self):
        async def my_hook(ctx):
            return None

        assert not HookRegistry.is_registered("myHook")
        HookRegistry.register("myHook", my_hook)
        assert HookRegistry.is_registered("myHook")

    def test_list_registered(self):
        async def hook_a(ctx):
            return None

        async def hook_b(ctx):
            return None

        HookRegistry.register("beta", hook_a)
        HookRegistry.register("alpha", hook_b)
        assert HookRegistry.list_registered() == ["alpha", "beta"]  # sorted

    def test_clear(self):
        async def my_hook(ctx):
            return None

        HookRegistry.register("myHook", my_hook)
        HookRegistry.clear()
        assert not HookRegistry.is_registered("myHook")
        assert HookRegistry.list_registered() == []


# =============================================================================
# @hook decorator tests
# =============================================================================


class TestHookDecorator:
    def test_decorator_registers(self):
        @hook("decoratedHook")
        async def my_decorated_hook(ctx):
            return HookResult(update={"x": 1})

        assert HookRegistry.is_registered("decoratedHook")
        assert HookRegistry.get("decoratedHook") is my_decorated_hook

    def test_decorator_preserves_function(self):
        @hook("preserveTest")
        async def original_fn(ctx):
            return None

        assert original_fn.__name__ == "original_fn"


# =============================================================================
# HookDefinition tests
# =============================================================================


class TestHookDefinition:
    def test_from_dict_defaults(self):
        defn = HookDefinition.from_dict({"name": "testHook"})
        assert defn.name == "testHook"
        assert defn.on == [Operation.CREATE, Operation.UPDATE]
        assert defn.when is None
        assert defn.description == ""

    def test_from_dict_full(self):
        defn = HookDefinition.from_dict({
            "name": "testHook",
            "on": ["create"],
            "when": "status == 'active'",
            "description": "A test hook",
        })
        assert defn.name == "testHook"
        assert defn.on == [Operation.CREATE]
        assert defn.when == "status == 'active'"
        assert defn.description == "A test hook"

    def test_from_dict_string_on(self):
        defn = HookDefinition.from_dict({"name": "testHook", "on": "update"})
        assert defn.on == [Operation.UPDATE]


# =============================================================================
# HookService tests
# =============================================================================


class TestHookService:
    @pytest.mark.asyncio
    async def test_empty_definitions_returns_none(self, hook_service, base_context):
        result = await hook_service.run_hooks("beforeSave", [], base_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_hook_receives_context(self, hook_service, base_context):
        received_ctx = None

        async def capture_ctx(ctx):
            nonlocal received_ctx
            received_ctx = ctx
            return None

        HookRegistry.register("captureCtx", capture_ctx)
        defn = HookDefinition(name="captureCtx")

        await hook_service.run_hooks("beforeSave", [defn], base_context)
        assert received_ctx is base_context
        assert received_ctx.entity_name == "Contact"
        assert received_ctx.operation == Operation.CREATE

    @pytest.mark.asyncio
    async def test_operation_filtering(self, hook_service, base_context):
        """Hooks with non-matching on: are skipped."""
        call_count = 0

        async def counting_hook(ctx):
            nonlocal call_count
            call_count += 1
            return None

        HookRegistry.register("countingHook", counting_hook)
        # This hook only runs on UPDATE, but context is CREATE
        defn = HookDefinition(name="countingHook", on=[Operation.UPDATE])

        await hook_service.run_hooks("beforeSave", [defn], base_context)
        assert call_count == 0

    @pytest.mark.asyncio
    async def test_when_condition_true(self, hook_service, base_context):
        """Hook runs when when: condition evaluates to true."""
        ran = False

        async def conditional_hook(ctx):
            nonlocal ran
            ran = True
            return None

        HookRegistry.register("conditionalHook", conditional_hook)
        defn = HookDefinition(
            name="conditionalHook",
            when="status == 'active'",
        )

        await hook_service.run_hooks("beforeSave", [defn], base_context)
        assert ran is True

    @pytest.mark.asyncio
    async def test_when_condition_false(self, hook_service, base_context):
        """Hook is skipped when when: condition evaluates to false."""
        ran = False

        async def conditional_hook(ctx):
            nonlocal ran
            ran = True
            return None

        HookRegistry.register("conditionalHook", conditional_hook)
        defn = HookDefinition(
            name="conditionalHook",
            when="status == 'inactive'",
        )

        await hook_service.run_hooks("beforeSave", [defn], base_context)
        assert ran is False

    @pytest.mark.asyncio
    async def test_when_condition_with_original(self, hook_service, update_context):
        """when: expression can reference original values."""
        ran = False

        async def change_detect_hook(ctx):
            nonlocal ran
            ran = True
            return None

        HookRegistry.register("changeDetect", change_detect_hook)
        defn = HookDefinition(
            name="changeDetect",
            on=[Operation.UPDATE],
            when="status != original.status",
        )

        await hook_service.run_hooks("beforeSave", [defn], update_context)
        assert ran is True

    @pytest.mark.asyncio
    async def test_when_condition_bad_expression_skips(self, hook_service, base_context):
        """Bad when: expression is skipped (not crashed)."""
        ran = False

        async def hook_fn(ctx):
            nonlocal ran
            ran = True
            return None

        HookRegistry.register("badWhen", hook_fn)
        defn = HookDefinition(name="badWhen", when="this_is_invalid!!!")

        await hook_service.run_hooks("beforeSave", [defn], base_context)
        assert ran is False

    @pytest.mark.asyncio
    async def test_sequential_execution_order(self, hook_service, base_context):
        """Hooks run in declared order."""
        order = []

        async def hook_a(ctx):
            order.append("a")
            return None

        async def hook_b(ctx):
            order.append("b")
            return None

        async def hook_c(ctx):
            order.append("c")
            return None

        HookRegistry.register("hookA", hook_a)
        HookRegistry.register("hookB", hook_b)
        HookRegistry.register("hookC", hook_c)

        defs = [
            HookDefinition(name="hookA"),
            HookDefinition(name="hookB"),
            HookDefinition(name="hookC"),
        ]

        await hook_service.run_hooks("beforeSave", defs, base_context)
        assert order == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_update_merges_into_record(self, hook_service, base_context):
        """HookResult.update merges into context.record."""
        async def set_full_name(ctx):
            return HookResult(
                update={"fullName": f"{ctx.record['firstName']} {ctx.record['lastName']}"}
            )

        HookRegistry.register("setFullName", set_full_name)
        defn = HookDefinition(name="setFullName")

        result = await hook_service.run_hooks("beforeSave", [defn], base_context)
        assert result is not None
        assert result.update == {"fullName": "John Doe"}
        assert base_context.record["fullName"] == "John Doe"

    @pytest.mark.asyncio
    async def test_compounding_updates(self, hook_service, base_context):
        """Multiple hooks compound their updates."""
        async def hook_a(ctx):
            return HookResult(update={"computed_a": "A"})

        async def hook_b(ctx):
            # Can see the result of hook_a
            val = ctx.record.get("computed_a", "")
            return HookResult(update={"computed_b": f"B+{val}"})

        HookRegistry.register("hookA", hook_a)
        HookRegistry.register("hookB", hook_b)

        defs = [
            HookDefinition(name="hookA"),
            HookDefinition(name="hookB"),
        ]

        result = await hook_service.run_hooks("beforeSave", defs, base_context)
        assert result.update == {"computed_a": "A", "computed_b": "B+A"}
        assert base_context.record["computed_a"] == "A"
        assert base_context.record["computed_b"] == "B+A"

    @pytest.mark.asyncio
    async def test_abort_stops_execution(self, hook_service, base_context):
        """HookResult.abort stops subsequent hooks."""
        order = []

        async def hook_a(ctx):
            order.append("a")
            return HookResult(abort="Blocked by hook A")

        async def hook_b(ctx):
            order.append("b")
            return None

        HookRegistry.register("hookA", hook_a)
        HookRegistry.register("hookB", hook_b)

        defs = [
            HookDefinition(name="hookA"),
            HookDefinition(name="hookB"),
        ]

        result = await hook_service.run_hooks("beforeSave", defs, base_context)
        assert result.abort == "Blocked by hook A"
        assert order == ["a"]  # hook_b never ran

    @pytest.mark.asyncio
    async def test_hook_returning_none(self, hook_service, base_context):
        """Hook returning None is a no-op."""
        async def noop_hook(ctx):
            return None

        HookRegistry.register("noopHook", noop_hook)
        defn = HookDefinition(name="noopHook")

        result = await hook_service.run_hooks("beforeSave", [defn], base_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_unregistered_hook_skipped(self, hook_service, base_context):
        """Unregistered hook names are skipped with warning."""
        defn = HookDefinition(name="doesNotExist")
        result = await hook_service.run_hooks("beforeSave", [defn], base_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_after_commit_catches_exceptions(self, hook_service, base_context, caplog):
        """afterCommit hooks catch exceptions instead of propagating."""
        async def failing_hook(ctx):
            raise RuntimeError("Email service down")

        HookRegistry.register("failingHook", failing_hook)
        defn = HookDefinition(name="failingHook")

        with caplog.at_level(logging.ERROR):
            result = await hook_service.run_hooks("afterCommit", [defn], base_context)

        # Should not abort — afterCommit is fire-and-forget
        assert result is None
        assert "Email service down" in caplog.text

    @pytest.mark.asyncio
    async def test_non_aftercommit_exception_becomes_abort(self, hook_service, base_context):
        """Non-afterCommit hook exceptions become abort results."""
        async def exploding_hook(ctx):
            raise RuntimeError("Unexpected error")

        HookRegistry.register("explodingHook", exploding_hook)
        defn = HookDefinition(name="explodingHook")

        result = await hook_service.run_hooks("beforeSave", [defn], base_context)
        assert result.abort is not None
        assert "Unexpected error" in result.abort

    @pytest.mark.asyncio
    async def test_after_commit_continues_after_failure(self, hook_service, base_context, caplog):
        """afterCommit continues executing hooks after one fails."""
        order = []

        async def failing_hook(ctx):
            order.append("fail")
            raise RuntimeError("boom")

        async def success_hook(ctx):
            order.append("success")
            return None

        HookRegistry.register("failHook", failing_hook)
        HookRegistry.register("successHook", success_hook)

        defs = [
            HookDefinition(name="failHook"),
            HookDefinition(name="successHook"),
        ]

        with caplog.at_level(logging.ERROR):
            await hook_service.run_hooks("afterCommit", defs, base_context)

        assert order == ["fail", "success"]


# =============================================================================
# HookConfig metadata parsing tests
# =============================================================================


class TestHookConfigParsing:
    def test_hook_config_to_definition(self):
        config = HookConfig(
            name="computeValue",
            on=["create", "update"],
            when="amount > 0",
            description="Compute total",
        )
        defn = hook_config_to_definition(config)
        assert defn.name == "computeValue"
        assert defn.on == [Operation.CREATE, Operation.UPDATE]
        assert defn.when == "amount > 0"
        assert defn.description == "Compute total"

    def test_hook_config_default_on(self):
        config = HookConfig(name="simpleHook")
        defn = hook_config_to_definition(config)
        assert defn.on == [Operation.CREATE, Operation.UPDATE]

    def test_entity_model_hooks_field(self):
        """EntityModel supports hooks dict."""
        from metaforge.metadata.loader import FieldDefinition

        entity = EntityModel(
            name="Test",
            display_name="Test",
            plural_name="Tests",
            primary_key="id",
            fields=[FieldDefinition(name="id", type="id", display_name="ID", primary_key=True)],
            hooks={
                "beforeSave": [
                    HookConfig(name="hookA", on=["create"]),
                    HookConfig(name="hookB", on=["update"], when="x > 0"),
                ],
                "afterCommit": [
                    HookConfig(name="hookC"),
                ],
            },
        )

        assert len(entity.hooks["beforeSave"]) == 2
        assert entity.hooks["beforeSave"][0].name == "hookA"
        assert entity.hooks["afterCommit"][0].name == "hookC"
        assert "afterSave" not in entity.hooks


# =============================================================================
# EntityLifecycleFactory.get_hook_definitions tests
# =============================================================================


class TestLifecycleFactoryHooks:
    def test_get_hook_definitions(self):
        from metaforge.metadata.loader import FieldDefinition
        from metaforge.validation.integration import EntityLifecycleFactory

        entity = EntityModel(
            name="Test",
            display_name="Test",
            plural_name="Tests",
            primary_key="id",
            fields=[FieldDefinition(name="id", type="id", display_name="ID", primary_key=True)],
            hooks={
                "beforeSave": [
                    HookConfig(name="hookA", on=["create"]),
                ],
            },
        )

        # EntityLifecycleFactory needs adapter and loader but get_hook_definitions
        # only reads entity.hooks, so we can use mocks
        factory = EntityLifecycleFactory(
            adapter=None,  # type: ignore
            metadata_loader=None,  # type: ignore
        )

        defs = factory.get_hook_definitions(entity, "beforeSave")
        assert len(defs) == 1
        assert defs[0].name == "hookA"
        assert defs[0].on == [Operation.CREATE]

    def test_get_hook_definitions_empty(self):
        from metaforge.metadata.loader import FieldDefinition
        from metaforge.validation.integration import EntityLifecycleFactory

        entity = EntityModel(
            name="Test",
            display_name="Test",
            plural_name="Tests",
            primary_key="id",
            fields=[FieldDefinition(name="id", type="id", display_name="ID", primary_key=True)],
        )

        factory = EntityLifecycleFactory(adapter=None, metadata_loader=None)  # type: ignore
        defs = factory.get_hook_definitions(entity, "beforeSave")
        assert defs == []


# =============================================================================
# YAML parsing integration test
# =============================================================================


class TestYamlHookParsing:
    def test_resolve_hooks_from_yaml(self, tmp_path):
        """Test that hooks section in entity YAML is parsed correctly."""
        entities_dir = tmp_path / "entities"
        entities_dir.mkdir()

        (entities_dir / "contract.yaml").write_text("""
entity: Contract
displayName: Contract
pluralName: Contracts
abbreviation: CTR
scope: tenant
fields:
  - name: id
    type: id
    primaryKey: true
  - name: totalValue
    type: currency
  - name: status
    type: picklist
    options:
      - { value: draft, label: Draft }
      - { value: approved, label: Approved }
hooks:
  beforeSave:
    - name: computeContractValue
      on: [create, update]
      description: "Recalculate total value from line items"
    - name: enforceApprovalWorkflow
      on: [update]
      when: 'status != original.status'
      description: "Require manager role for approval transitions"
  afterCommit:
    - name: sendStatusChangeEmail
      on: [update]
      when: 'status != original.status'
      description: "Notify stakeholders of status changes"
  beforeDelete:
    - name: archiveInsteadOfDelete
      description: "Soft-delete by setting status to archived"
""")

        loader = MetadataLoader(tmp_path)
        loader.load_all()

        entity = loader.get_entity("Contract")
        assert entity is not None

        # beforeSave
        assert len(entity.hooks["beforeSave"]) == 2
        assert entity.hooks["beforeSave"][0].name == "computeContractValue"
        assert entity.hooks["beforeSave"][0].on == ["create", "update"]
        assert entity.hooks["beforeSave"][1].name == "enforceApprovalWorkflow"
        assert entity.hooks["beforeSave"][1].on == ["update"]
        assert entity.hooks["beforeSave"][1].when == "status != original.status"

        # afterCommit
        assert len(entity.hooks["afterCommit"]) == 1
        assert entity.hooks["afterCommit"][0].name == "sendStatusChangeEmail"

        # beforeDelete
        assert len(entity.hooks["beforeDelete"]) == 1
        assert entity.hooks["beforeDelete"][0].name == "archiveInsteadOfDelete"

        # afterSave not declared
        assert "afterSave" not in entity.hooks

    def test_entity_without_hooks(self, tmp_path):
        """Entities without hooks section parse normally."""
        entities_dir = tmp_path / "entities"
        entities_dir.mkdir()

        (entities_dir / "simple.yaml").write_text("""
entity: Simple
abbreviation: SMP
fields:
  - name: id
    type: id
    primaryKey: true
  - name: name
    type: text
""")

        loader = MetadataLoader(tmp_path)
        loader.load_all()

        entity = loader.get_entity("Simple")
        assert entity is not None
        assert entity.hooks == {}


# =============================================================================
# register_builtin_hooks test
# =============================================================================


class TestRegisterBuiltinHooks:
    def test_register_builtin_hooks_no_error(self):
        """register_builtin_hooks() runs without error (currently a no-op)."""
        register_builtin_hooks()


# =============================================================================
# Constants test
# =============================================================================


class TestConstants:
    def test_valid_hook_points(self):
        assert VALID_HOOK_POINTS == ("beforeSave", "afterSave", "afterCommit", "beforeDelete")
