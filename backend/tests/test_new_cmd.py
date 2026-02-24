"""Tests for `metaforge new entity` scaffolding command."""

import pytest
from click.testing import CliRunner

from metaforge.cli.new_cmd import entity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(*args):
    """Run the entity command with the given args and return the result."""
    runner = CliRunner()
    return runner.invoke(entity, list(args))


def run_dry(*args):
    """Run with --dry-run so no files are written."""
    return run(*args, "--dry-run")


# ---------------------------------------------------------------------------
# Basic generation — dry-run (no disk I/O)
# ---------------------------------------------------------------------------

class TestEntityYaml:
    def test_no_fields_generates_stub(self):
        result = run_dry("Widget")
        assert result.exit_code == 0
        output = result.output
        assert "entity: Widget" in output
        assert "pluralName: Widgets" in output
        assert "labelField: name" in output
        assert "primaryKey: true" in output
        assert "block: AuditTrail" in output
        # Stub name field
        assert "- name: name" in output
        assert "type: name" in output

    def test_name_type_field_becomes_label_field(self):
        result = run_dry("Deal", "--field", "title:name")
        assert result.exit_code == 0
        assert "labelField: title" in result.output

    def test_first_non_name_field_as_label_when_no_name_type(self):
        result = run_dry("Deal", "--field", "amount:currency")
        assert result.exit_code == 0
        assert "labelField: amount" in result.output

    def test_currency_field(self):
        result = run_dry("Deal", "--field", "amount:currency")
        assert result.exit_code == 0
        assert "- name: amount" in result.output
        assert "type: currency" in result.output

    def test_picklist_field_has_placeholder_options(self):
        result = run_dry("Deal", "--field", "status:picklist")
        assert result.exit_code == 0
        assert "type: picklist" in result.output
        assert "value: option1" in result.output
        assert "value: option2" in result.output

    def test_relation_field_has_full_block(self):
        result = run_dry("Deal", "--field", "companyId:relation:Company")
        assert result.exit_code == 0
        output = result.output
        assert "- name: companyId" in output
        assert "type: relation" in output
        assert "entity: Company" in output
        assert "displayField: name" in output

    def test_multiple_fields(self):
        result = run_dry(
            "Deal",
            "--field", "name:name",
            "--field", "amount:currency",
            "--field", "closeDate:date",
        )
        assert result.exit_code == 0
        output = result.output
        assert "name: name" in output
        assert "name: amount" in output
        assert "name: closeDate" in output

    def test_tenant_scoped_by_default(self):
        result = run_dry("Deal")
        assert result.exit_code == 0
        output = result.output
        assert "scope: tenant" in output
        assert "tenantId" in output

    def test_no_tenant_omits_tenant_fields(self):
        result = run_dry("Deal", "--no-tenant")
        assert result.exit_code == 0
        output = result.output
        assert "scope: tenant" not in output
        assert "tenantId" not in output


class TestScreenYaml:
    def test_screen_generated_by_default(self):
        result = run_dry("Deal", "--field", "name:name")
        assert result.exit_code == 0
        output = result.output
        assert "screen:" in output
        assert "slug: deal" in output
        assert "type: entity" in output
        assert "entityName: Deal" in output
        assert "yaml:deal-grid" in output
        assert "yaml:deal-form" in output
        assert "yaml:deal-detail" in output

    def test_custom_nav_section_and_icon(self):
        result = run_dry("Deal", "--nav-section", "CRM", "--nav-icon", "briefcase")
        assert result.exit_code == 0
        assert "section: CRM" in result.output
        assert "icon: briefcase" in result.output

    def test_no_screen_omits_screen_yaml(self):
        result = run_dry("Deal", "--no-screen")
        assert result.exit_code == 0
        assert "screen:" not in result.output


class TestViewYamls:
    def test_views_generated_by_default(self):
        result = run_dry("Deal", "--field", "name:name")
        assert result.exit_code == 0
        output = result.output
        assert "style: grid" in output
        assert "style: form" in output
        assert "style: detail" in output

    def test_grid_lists_columns(self):
        result = run_dry("Deal", "--field", "name:name", "--field", "amount:currency")
        assert result.exit_code == 0
        output = result.output
        assert "field: name" in output
        assert "field: amount" in output
        assert "pinned: left" in output

    def test_form_and_detail_list_fields_in_section(self):
        result = run_dry("Deal", "--field", "title:name", "--field", "notes:text")
        assert result.exit_code == 0
        output = result.output
        assert "- title" in output
        assert "- notes" in output
        assert "label: Details" in output

    def test_no_views_omits_view_yamls(self):
        result = run_dry("Deal", "--no-views")
        assert result.exit_code == 0
        assert "style: grid" not in result.output
        assert "style: form" not in result.output
        assert "style: detail" not in result.output

    def test_no_screen_no_views_only_entity_yaml(self):
        result = run_dry("Deal", "--no-screen", "--no-views")
        assert result.exit_code == 0
        output = result.output
        assert "entity: Deal" in output
        assert "screen:" not in output
        assert "style: grid" not in output


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_lowercase_name_errors(self):
        result = run_dry("deal")
        assert result.exit_code != 0
        assert "uppercase" in result.output.lower() or "uppercase" in (result.output + (result.exception or "")).lower()

    def test_malformed_field_spec_warns_and_continues(self):
        # Missing type — should warn but not crash
        result = run_dry("Deal", "--field", "badspec")
        assert result.exit_code == 0

    def test_unknown_field_type_warns_and_continues(self):
        result = run_dry("Deal", "--field", "foo:weirdtype")
        assert result.exit_code == 0
        assert "entity: Deal" in result.output


# ---------------------------------------------------------------------------
# File writing (uses CliRunner isolated filesystem)
# ---------------------------------------------------------------------------

class TestFileWriting:
    def _invoke_in_fs(self, runner, args):
        """Run entity command inside CliRunner's isolated filesystem."""
        with runner.isolated_filesystem():
            import os
            # Create expected metadata directory structure
            for d in ("metadata/entities", "metadata/screens", "metadata/views"):
                os.makedirs(d, exist_ok=True)
            return runner.invoke(entity, args)

    def test_writes_five_files_by_default(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            import os
            for d in ("metadata/entities", "metadata/screens", "metadata/views"):
                os.makedirs(d, exist_ok=True)
            result = runner.invoke(entity, ["Widget", "--field", "name:name"])
            assert result.exit_code == 0
            assert os.path.exists("metadata/entities/widget.yaml")
            assert os.path.exists("metadata/screens/widget.yaml")
            assert os.path.exists("metadata/views/widget-grid.yaml")
            assert os.path.exists("metadata/views/widget-form.yaml")
            assert os.path.exists("metadata/views/widget-detail.yaml")

    def test_conflict_detection_aborts_without_force(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            import os
            for d in ("metadata/entities", "metadata/screens", "metadata/views"):
                os.makedirs(d, exist_ok=True)
            # First run
            runner.invoke(entity, ["Widget", "--field", "name:name"])
            # Second run — should fail
            result = runner.invoke(entity, ["Widget", "--field", "name:name"])
            assert result.exit_code != 0
            assert "already exist" in result.output

    def test_force_overwrites_existing_files(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            import os
            for d in ("metadata/entities", "metadata/screens", "metadata/views"):
                os.makedirs(d, exist_ok=True)
            runner.invoke(entity, ["Widget", "--field", "name:name"])
            result = runner.invoke(entity, ["Widget", "--field", "name:name", "--force"])
            assert result.exit_code == 0

    def test_success_output_mentions_next_steps(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            import os
            for d in ("metadata/entities", "metadata/screens", "metadata/views"):
                os.makedirs(d, exist_ok=True)
            result = runner.invoke(entity, ["Widget", "--field", "name:name"])
            assert result.exit_code == 0
            assert "migrate generate" in result.output

    def test_picklist_next_steps_mention_field(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            import os
            for d in ("metadata/entities", "metadata/screens", "metadata/views"):
                os.makedirs(d, exist_ok=True)
            result = runner.invoke(entity, ["Widget", "--field", "status:picklist"])
            assert result.exit_code == 0
            assert "status" in result.output
