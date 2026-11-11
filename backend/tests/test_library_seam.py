"""Tests for MF-003 (slimmed): MetaForge as an embeddable library (ADR-0015).

Covers:
  - packaging: light core dependencies, a ``server`` extra, schemas as package data
  - the core imports and works with every server-only package blocked
  - the CLI loads subcommands lazily and names the extra when one is missing
  - ``MetadataLoader`` with explicit entity, block and draft directories
  - ``referenced_fields``
  - ``validate_record``: defaults, rules, query callback, skips, parity with
    ``EntityLifecycle.prepare``, and use inside a running event loop
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
import tomllib
from pathlib import Path

import pytest

from metaforge.metadata.loader import MetadataLoader
from metaforge.validation import (
    Operation,
    UserContext,
    referenced_fields,
    validate_record,
)
from metaforge.validation.expressions import ParseError
from metaforge.validation.record import AsyncQueryCallbackError

BACKEND = Path(__file__).resolve().parent.parent
REPO_METADATA = BACKEND.parent / "metadata"
SCHEMAS_DIR = BACKEND / "src" / "metaforge" / "metadata" / "schemas"

SERVER_ONLY = [
    "alembic",
    "bcrypt",
    "click",
    "faker",
    "fastapi",
    "fastmcp",
    "httpx",
    "jwt",
    "passlib",
    "psycopg",
    "pydantic",
    "sqlalchemy",
    "starlette",
    "uvicorn",
]


def _run_blocked(code: str, blocked: list[str]) -> subprocess.CompletedProcess[str]:
    """Run ``code`` in a fresh interpreter where ``blocked`` packages can't import."""
    prelude = textwrap.dedent(
        f"""
        import importlib.abc, sys
        BLOCKED = {blocked!r}

        class _Block(importlib.abc.MetaPathFinder):
            def find_spec(self, name, path=None, target=None):
                if name.split(".")[0] in BLOCKED:
                    raise ModuleNotFoundError(f"blocked: {{name}}", name=name)
                return None

        sys.meta_path.insert(0, _Block())
        """
    )
    return subprocess.run(
        [sys.executable, "-c", prelude + textwrap.dedent(code)],
        capture_output=True,
        text=True,
        cwd=BACKEND,
        timeout=60,
    )


# ---------------------------------------------------------------------------
# Packaging
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def project() -> dict:
    return tomllib.loads((BACKEND / "pyproject.toml").read_text())


class TestPackaging:
    def test_core_dependencies_are_light(self, project: dict) -> None:
        names = {
            d.split(">")[0].split("<")[0].split("[")[0] for d in project["project"]["dependencies"]
        }
        assert names == {"pyyaml", "jsonschema"}

    def test_server_extra_holds_the_server_stack(self, project: dict) -> None:
        server = " ".join(project["project"]["optional-dependencies"]["server"])
        for pkg in ("fastapi", "sqlalchemy", "alembic", "pyjwt", "fastmcp", "click", "faker"):
            assert pkg in server

    def test_dev_extra_installs_server(self, project: dict) -> None:
        assert "metaforge[server]" in project["project"]["optional-dependencies"]["dev"]

    def test_schemas_are_package_data(self, project: dict) -> None:
        globs = project["tool"]["setuptools"]["package-data"]["metaforge.metadata"]
        shipped = {p.name for g in globs for p in (SCHEMAS_DIR.parent).glob(g)}
        on_disk = {p.name for p in SCHEMAS_DIR.glob("*.json")}
        assert on_disk and shipped == on_disk


# ---------------------------------------------------------------------------
# Core without the server stack
# ---------------------------------------------------------------------------


class TestCoreWithoutServer:
    def test_core_imports_and_validates_without_server_packages(self) -> None:
        result = _run_blocked(
            f"""
            from pathlib import Path
            import metaforge.core.types
            import metaforge.layouts
            from metaforge.metadata.loader import MetadataLoader
            from metaforge.metadata.validator import validate_metadata_dir
            from metaforge.validation import validate_record, referenced_fields

            root = Path({str(REPO_METADATA)!r})
            validate_metadata_dir(root)  # needs the packaged JSON Schemas
            loader = MetadataLoader(root)
            loader.load_all()
            out = validate_record(loader.get_entity("Contact"), {{"firstName": "Ada"}})
            assert not out.valid
            assert referenced_fields("a > b") == {{"a", "b"}}
            leaked = sorted(m for m in sys.modules if m.split(".")[0] in BLOCKED)
            assert not leaked, leaked
            print("ok")
            """,
            SERVER_ONLY,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip().endswith("ok")

    def test_server_modules_still_need_the_extra(self) -> None:
        result = _run_blocked("import metaforge.api.app", SERVER_ONLY)
        assert result.returncode != 0
        assert "blocked" in result.stderr


class TestLazyCli:
    def test_metadata_command_runs_with_click_only(self) -> None:
        blocked = [p for p in SERVER_ONLY if p != "click"]
        result = _run_blocked(
            """
            from click.testing import CliRunner
            from metaforge.cli.main import cli
            r = CliRunner().invoke(cli, ["metadata", "--help"])
            assert r.exit_code == 0, r.output
            r = CliRunner().invoke(cli, ["--help"])
            assert r.exit_code == 0 and "migrate" in r.output, r.output
            print("ok")
            """,
            blocked,
        )
        assert result.returncode == 0, result.stderr

    def test_server_command_names_the_extra(self) -> None:
        blocked = [p for p in SERVER_ONLY if p != "click"]
        result = _run_blocked(
            """
            from click.testing import CliRunner
            from metaforge.cli.main import cli
            r = CliRunner().invoke(cli, ["migrate", "--help"])
            assert r.exit_code != 0
            assert "metaforge[server]" in r.output, r.output
            print("ok")
            """,
            blocked,
        )
        assert result.returncode == 0, result.stderr

    def test_unknown_command_is_still_an_error(self) -> None:
        from click.testing import CliRunner

        from metaforge.cli.main import cli

        r = CliRunner().invoke(cli, ["nope"])
        assert r.exit_code != 0
        assert "No such command" in r.output


# ---------------------------------------------------------------------------
# MetadataLoader directories
# ---------------------------------------------------------------------------

VENDOR = """\
entity: Vendor
abbreviation: VEN
includes:
  - block: Contactable
fields:
  - name: id
    type: id
    primaryKey: true
  - name: name
    type: name
    validation:
      required: true
"""

CONTACTABLE = """\
block: Contactable
fields:
  - name: email
    type: email
"""


class TestLoaderDirectories:
    def test_host_layout_with_blocks_under_entities(self, tmp_path: Path) -> None:
        schema = tmp_path / "schema"
        (schema / "blocks").mkdir(parents=True)
        (schema / "Vendor.yaml").write_text(VENDOR)
        (schema / "blocks" / "Contactable.yaml").write_text(CONTACTABLE)

        loader = MetadataLoader(entities_dir=schema, blocks_dir=schema / "blocks")
        loader.load_all()

        vendor = loader.get_entity("Vendor")
        assert vendor is not None
        assert {f.name for f in vendor.fields} >= {"id", "name", "email"}
        assert loader.drafts_dir is None

    def test_string_paths_are_accepted(self, tmp_path: Path) -> None:
        (tmp_path / "e").mkdir()
        (tmp_path / "e" / "Vendor.yaml").write_text(
            VENDOR.replace("includes:\n  - block: Contactable\n", "")
        )
        loader = MetadataLoader(entities_dir=str(tmp_path / "e"))
        loader.load_all()
        assert loader.get_entity("Vendor") is not None

    def test_default_layout_unchanged(self, tmp_path: Path) -> None:
        for sub in ("entities", "blocks", "drafts"):
            (tmp_path / sub).mkdir()
        (tmp_path / "entities" / "Vendor.yaml").write_text(VENDOR)
        (tmp_path / "blocks" / "Contactable.yaml").write_text(CONTACTABLE)
        (tmp_path / "drafts" / "Draft.yaml").write_text(
            "entity: Draft\nabbreviation: DRF\n"
            "fields:\n  - name: id\n    type: id\n    primaryKey: true\n"
        )
        loader = MetadataLoader(tmp_path)
        loader.load_all()
        assert loader.entities_dir == tmp_path / "entities"
        assert loader.get_entity("Vendor") is not None
        assert loader.get_entity("Draft").is_draft

    def test_explicit_dir_overrides_metadata_path(self, tmp_path: Path) -> None:
        (tmp_path / "entities").mkdir()
        (tmp_path / "other").mkdir()
        (tmp_path / "other" / "Vendor.yaml").write_text(
            VENDOR.replace("includes:\n  - block: Contactable\n", "")
        )
        loader = MetadataLoader(tmp_path, entities_dir=tmp_path / "other")
        loader.load_all()
        assert loader.get_entity("Vendor") is not None

    def test_needs_a_directory(self) -> None:
        with pytest.raises(ValueError):
            MetadataLoader()

    def test_reload_uses_explicit_dirs(self, tmp_path: Path) -> None:
        (tmp_path / "e").mkdir()
        loader = MetadataLoader(entities_dir=tmp_path / "e")
        loader.load_all()
        assert loader.get_entity("Vendor") is None
        (tmp_path / "e" / "Vendor.yaml").write_text(
            VENDOR.replace("includes:\n  - block: Contactable\n", "")
        )
        loader.reload()
        assert loader.get_entity("Vendor") is not None


# ---------------------------------------------------------------------------
# referenced_fields
# ---------------------------------------------------------------------------


class TestReferencedFields:
    @pytest.mark.parametrize(
        ("expression", "expected"),
        [
            ('status == "active"', {"status"}),
            ("a > b && (c || !d)", {"a", "b", "c", "d"}),
            ("len(name) > 3", {"name"}),
            ("daysBetween(startDate, today()) > 30", {"startDate"}),
            ("record.total > original.total", {"total"}),
            ("address.city == null", {"address"}),
            ("items[idx] > 0", {"items", "idx"}),
            ('exists("Contract", {"parentId": id, "status": "active"})', {"id"}),
            ('status in ["a", "b"]', {"status"}),
            ("context.tenantId == tenantId", {"tenantId"}),
            ("1 + 2", set()),
            ("true", set()),
        ],
    )
    def test_fields(self, expression: str, expected: set[str]) -> None:
        assert referenced_fields(expression) == expected

    def test_custom_variables(self) -> None:
        assert referenced_fields("rate * qty", variables=("rate",)) == {"qty"}

    def test_accepts_an_ast(self) -> None:
        from metaforge.validation.expressions import parse

        assert referenced_fields(parse("x + y")) == {"x", "y"}

    def test_bad_expression_raises(self) -> None:
        with pytest.raises(ParseError):
            referenced_fields("a ==")


# ---------------------------------------------------------------------------
# validate_record
# ---------------------------------------------------------------------------

ORDER = """\
entity: Order
abbreviation: ORD
fields:
  - name: id
    type: id
    primaryKey: true
  - name: tenantId
    type: string
    auto: context.tenantId
  - name: code
    type: string
    validation:
      required: true
  - name: status
    type: picklist
    default: draft
    options:
      - {value: draft, label: Draft}
      - {value: placed, label: Placed}
  - name: customerId
    type: relation
    relation: {entity: Customer, displayField: name}
  - name: quantity
    type: number
    validation:
      min: 1
  - name: label
    type: string
defaults:
  - field: label
    expression: 'concat(code, "-", status)'
    policy: overwrite
    on: [create, update]
validators:
  - type: unique
    params: {fields: [code], scope: global}
    message: "Code {code} is taken"
    code: DUPLICATE_CODE
  - type: expression
    params: {rule: 'quantity == null || quantity <= 100'}
    message: "{quantity:label} is large"
    code: BIG_ORDER
    severity: warning
  - type: immutable
    params: {fields: [code]}
    on: [update]
    message: "Code can't change"
    code: CODE_LOCKED
  - type: someHostOnlyCheck
    params: {field: code}
"""

CUSTOMER = """\
entity: Customer
abbreviation: CUS
fields:
  - name: id
    type: id
    primaryKey: true
  - name: name
    type: name
"""


@pytest.fixture
def order_loader(tmp_path: Path) -> MetadataLoader:
    (tmp_path / "entities").mkdir()
    (tmp_path / "entities" / "Order.yaml").write_text(ORDER)
    (tmp_path / "entities" / "Customer.yaml").write_text(CUSTOMER)
    loader = MetadataLoader(tmp_path)
    loader.load_all()
    return loader


@pytest.fixture
def order(order_loader: MetadataLoader):
    return order_loader.get_entity("Order")


def _codes(errors) -> set[str]:
    return {e.code for e in errors}


class _Store:
    """In-memory query callback using the validation filter format."""

    def __init__(self, rows: dict[str, list[dict]]):
        self.rows = rows
        self.calls: list[tuple] = []

    def __call__(self, entity: str, filter: dict, tenant_id: str | None) -> list[dict]:
        self.calls.append((entity, filter, tenant_id))
        out = []
        for row in self.rows.get(entity, []):
            ok = True
            for cond in filter.get("and", []):
                value = row.get(cond["field"])
                if cond["op"] == "eq" and value != cond["value"]:
                    ok = False
                if cond["op"] == "neq" and value == cond["value"]:
                    ok = False
            if ok:
                out.append(row)
        return out


class TestValidateRecord:
    def test_defaults_auto_fields_and_required(self, order) -> None:
        record = {"quantity": 2}
        out = validate_record(order, record, user_context=UserContext(tenant_id="t1"))

        assert not out.valid
        assert any(e.field == "code" for e in out.errors)
        assert out.record["status"] == "draft"
        assert out.record["tenantId"] == "t1"
        assert record == {"quantity": 2}  # input untouched

    def test_valid_record(self, order) -> None:
        out = validate_record(order, {"code": "A1", "quantity": 5}, query=_Store({}))
        assert out.valid, out.errors
        assert out.errors == [] and out.warnings == []
        assert out.record["label"] == "A1-draft"
        assert out.skipped and out.skipped[0].type == "someHostOnlyCheck"

    def test_field_rule_and_warning_with_interpolation(self, order) -> None:
        out = validate_record(order, {"code": "A1", "quantity": 0}, query=_Store({}))
        assert any(e.field == "quantity" for e in out.errors)

        out = validate_record(order, {"code": "A1", "quantity": 500}, query=_Store({}))
        assert out.valid
        assert [w.code for w in out.warnings] == ["BIG_ORDER"]
        assert out.warnings[0].message == "Quantity is large"

    def test_data_validators_skip_without_query(self, order, caplog) -> None:
        with caplog.at_level("WARNING", logger="metaforge.validation.record"):
            out = validate_record(order, {"code": "A1", "customerId": "CUS-9"})
        assert out.valid
        skipped = {(s.type, s.field) for s in out.skipped}
        assert ("unique", "code") in skipped
        assert ("referenceExists", "customerId") in skipped
        assert ("someHostOnlyCheck", "code") in skipped
        assert "Skipped unique validator on Order.code" in caplog.text

    def test_query_callback_drives_unique_and_reference(self, order) -> None:
        store = _Store({"Order": [{"id": "ORD-1", "code": "A1"}], "Customer": []})
        out = validate_record(order, {"code": "A1", "customerId": "CUS-9"}, query=store)
        assert _codes(out.errors) == {"DUPLICATE_CODE", "REFERENCE_NOT_FOUND"}
        assert any(e.message == "Code A1 is taken" for e in out.errors)
        assert (
            "Customer",
            {"and": [{"field": "id", "op": "eq", "value": "CUS-9"}]},
            None,
        ) in store.calls

        store.rows["Customer"] = [{"id": "CUS-9"}]
        out = validate_record(order, {"code": "B2", "customerId": "CUS-9"}, query=store)
        assert out.valid, out.errors
        assert [s.type for s in out.skipped] == ["someHostOnlyCheck"]

    def test_update_excludes_self_and_checks_original(self, order) -> None:
        store = _Store({"Order": [{"id": "ORD-1", "code": "A1"}]})
        original = {"id": "ORD-1", "code": "A1", "status": "draft"}

        out = validate_record(
            order, {**original, "status": "placed"}, "update", store, original=original
        )
        assert out.valid, out.errors
        assert out.record["label"] == "A1-placed"

        out = validate_record(
            order, {**original, "code": "Z9"}, Operation.UPDATE, store, original=original
        )
        assert "CODE_LOCKED" in _codes(out.errors)

    def test_async_callback_is_rejected(self, order) -> None:
        async def query(entity, filter, tenant_id):
            return []

        with pytest.raises(AsyncQueryCallbackError):
            validate_record(order, {"code": "A1"}, query=query)

    def test_validator_exception_becomes_an_error(self, order, monkeypatch) -> None:
        def broken(entity, filter, tenant_id):
            raise RuntimeError("db down")

        out = validate_record(order, {"code": "A1"}, query=broken)
        assert "VALIDATOR_ERROR" in _codes(out.errors)

    async def test_works_inside_a_running_event_loop(self, order) -> None:
        out = validate_record(order, {"code": "A1"}, query=_Store({}))
        assert out.valid, out.errors


class TestParityWithServerLifecycle:
    """validate_record gives the same answer as the server's save path."""

    @pytest.fixture
    def loader(self) -> MetadataLoader:
        loader = MetadataLoader(REPO_METADATA)
        loader.load_all()
        return loader

    @pytest.mark.parametrize(
        "record",
        [
            {"firstName": "Ada"},
            {"firstName": "Ada", "lastName": "Lovelace", "status": "active"},
            {"firstName": "Ada", "lastName": "Lovelace", "email": "nope", "companyId": "CMP-1"},
            {"firstName": "Ada", "lastName": "Lovelace", "email": "ada@example.com"},
        ],
    )
    async def test_contact_create(self, loader: MetadataLoader, record: dict) -> None:
        from metaforge.validation import register_all_builtins, register_canned_validators
        from metaforge.validation.integration import EntityLifecycleFactory

        register_all_builtins()
        register_canned_validators()

        class _EmptyAdapter:
            def query(self, entity, filter=None, **kwargs):
                return {"data": []}

        entity = loader.get_entity("Contact")
        lf = EntityLifecycleFactory(_EmptyAdapter(), loader)
        user = UserContext(tenant_id="TEN-1", user_id="USR-1")
        server = await lf.create_lifecycle(entity, user).prepare(
            record=dict(record),
            operation=Operation.CREATE,
            entity_name=entity.name,
            defaults=lf.get_static_defaults(entity) + lf.get_defaults(entity),
            auto_fields=lf.get_auto_fields(entity),
            validators=lf.get_validators(entity) + lf.get_relation_validators(entity),
            user_context=user,
            field_validators=lf.get_field_validators(entity),
        )

        host = validate_record(entity, record, query=lambda e, f, t: [], user_context=user)

        def key(errors):
            return sorted((e.code, e.field, e.message, e.severity.value) for e in errors)

        def stable(rec):  # auto timestamps differ by microseconds between runs
            return {k: v for k, v in rec.items() if k not in ("createdAt", "updatedAt")}

        assert stable(host.record) == stable(server.record)
        assert set(host.record) == set(server.record)
        assert host.valid == server.validation.valid
        assert key(host.errors) == key(server.validation.errors)
        assert key(host.warnings) == key(server.validation.warnings)
        assert host.skipped == []
