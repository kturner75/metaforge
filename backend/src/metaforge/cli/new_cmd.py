"""MetaForge scaffolding commands — `metaforge new entity <Name>`."""

from __future__ import annotations

import sys
from pathlib import Path

import click


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

KNOWN_TYPES = {
    "name", "text", "description", "email", "phone", "url",
    "number", "currency", "percent", "date", "datetime",
    "checkbox", "picklist", "relation",
}


def _resolve_metadata_path() -> Path:
    """Resolve the metadata/ directory from the current working directory."""
    cwd = Path.cwd()
    base = cwd.parent if cwd.name == "backend" else cwd
    return base / "metadata"


def _to_slug(name: str) -> str:
    """PascalCase entity name → lowercase slug.  Deal → deal, FundingDoc → fundingdoc."""
    return name.lower()


def _to_plural(name: str) -> str:
    """Very simple pluralisation — appends 's'."""
    if name.endswith("s"):
        return name + "es"
    return name + "s"


def _parse_field(spec: str) -> dict:
    """Parse a field spec string into a dict.

    Formats:
        fieldName:type                  → plain field
        fieldName:relation:TargetEntity → relation field
    """
    parts = spec.split(":")
    if len(parts) < 2:
        click.echo(f"  Warning: ignoring malformed field spec '{spec}' (expected fieldName:type)", err=True)
        return {}
    field_name = parts[0].strip()
    field_type = parts[1].strip()
    relation_entity = parts[2].strip() if len(parts) >= 3 else None

    if field_type not in KNOWN_TYPES:
        click.echo(f"  Warning: unknown field type '{field_type}' for field '{field_name}' — included as-is", err=True)

    return {"name": field_name, "type": field_type, "relation_entity": relation_entity}


def _label_field(parsed_fields: list[dict]) -> str:
    """Return the name of the label field (first name-type field, else first field)."""
    for f in parsed_fields:
        if f.get("type") == "name":
            return f["name"]
    if parsed_fields:
        return parsed_fields[0]["name"]
    return "name"


# ---------------------------------------------------------------------------
# YAML generators
# ---------------------------------------------------------------------------

def _field_yaml(f: dict, indent: int = 2) -> str:
    """Render a single field definition as YAML lines."""
    pad = " " * indent
    lines = [f"{pad}- name: {f['name']}"]
    lines.append(f"{pad}  type: {f['type']}")

    if f["type"] == "relation" and f.get("relation_entity"):
        target = f["relation_entity"]
        # Guess a display field — use 'name' as convention
        lines.append(f"{pad}  displayName: {target}")
        lines.append(f"{pad}  relation:")
        lines.append(f"{pad}    entity: {target}")
        lines.append(f"{pad}    displayField: name")

    elif f["type"] == "picklist":
        lines.append(f"{pad}  options:")
        lines.append(f"{pad}    - value: option1")
        lines.append(f"{pad}      label: Option 1")
        lines.append(f"{pad}    - value: option2")
        lines.append(f"{pad}      label: Option 2")

    return "\n".join(lines)


def _entity_yaml(
    name: str,
    slug: str,
    label_field: str,
    parsed_fields: list[dict],
    tenant: bool,
) -> str:
    plural = _to_plural(name)
    lines = [
        f"entity: {name}",
        f"displayName: {name}",
        f"pluralName: {plural}",
        f"labelField: {label_field}",
    ]
    if tenant:
        lines.append("scope: tenant")

    lines.append("")
    lines.append("includes:")
    lines.append("  - block: AuditTrail")
    lines.append("")
    lines.append("fields:")
    lines.append("  - name: id")
    lines.append("    type: id")
    lines.append("    primaryKey: true")
    lines.append("")

    if tenant:
        lines.append("  - name: tenantId")
        lines.append("    type: relation")
        lines.append("    displayName: Tenant")
        lines.append("    relation:")
        lines.append("      entity: Tenant")
        lines.append("      displayField: name")
        lines.append("    auto: context.tenantId")
        lines.append("    readOnly: true")
        lines.append("")

    if not parsed_fields:
        # Stub — add a single name field as a placeholder
        lines.append("  - name: name")
        lines.append("    type: name")
        lines.append("    validation:")
        lines.append("      required: true")
    else:
        for i, f in enumerate(parsed_fields):
            lines.append(_field_yaml(f))
            if i < len(parsed_fields) - 1:
                lines.append("")

    lines.append("")
    return "\n".join(lines)


def _screen_yaml(
    name: str,
    slug: str,
    nav_section: str,
    nav_icon: str,
) -> str:
    plural = _to_plural(name)
    return "\n".join([
        "screen:",
        f"  name: {plural}",
        f"  slug: {slug}",
        "  type: entity",
        f"  entityName: {name}",
        "  nav:",
        f"    section: {nav_section}",
        "    order: 10",
        f"    icon: {nav_icon}",
        "  views:",
        f"    list: yaml:{slug}-grid",
        f"    detail: yaml:{slug}-detail",
        f"    create: yaml:{slug}-form",
        f"    edit: yaml:{slug}-form",
        "",
    ])


def _grid_yaml(name: str, slug: str, parsed_fields: list[dict]) -> str:
    plural = _to_plural(name)
    lines = [
        "view:",
        f"  name: {plural}",
        f"  entityName: {name}",
        "  pattern: query",
        "  style: grid",
        "  data:",
        "    pageSize: 25",
        "  styleConfig:",
    ]
    if not parsed_fields:
        lines.append("    columns: []")
    else:
        lines.append("    columns:")
        for i, f in enumerate(parsed_fields):
            pinned = "\n        pinned: left" if i == 0 else ""
            lines.append(f"      - field: {f['name']}{pinned}")
    lines.append("    selectable: false")
    lines.append("    inlineEdit: false")
    lines.append("")
    return "\n".join(lines)


def _form_yaml(name: str, slug: str, parsed_fields: list[dict]) -> str:
    field_names = [f["name"] for f in parsed_fields] if parsed_fields else ["name"]
    fields_yaml = "\n".join(f"          - {fn}" for fn in field_names)
    return "\n".join([
        "view:",
        f"  name: {name} Form",
        f"  entityName: {name}",
        "  pattern: record",
        "  style: form",
        "  data: {}",
        "  styleConfig:",
        "    sections:",
        "      - label: Details",
        f"        fields:",
        fields_yaml,
        "",
    ])


def _detail_yaml(name: str, slug: str, parsed_fields: list[dict]) -> str:
    field_names = [f["name"] for f in parsed_fields] if parsed_fields else ["name"]
    fields_yaml = "\n".join(f"          - {fn}" for fn in field_names)
    return "\n".join([
        "view:",
        f"  name: {name} Detail",
        f"  entityName: {name}",
        "  pattern: record",
        "  style: detail",
        "  data: {}",
        "  styleConfig:",
        "    sections:",
        "      - label: Details",
        f"        fields:",
        fields_yaml,
        "",
    ])


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

@click.group()
def new():
    """Scaffold new MetaForge artifacts."""
    pass


@new.command("entity")
@click.argument("name")
@click.option(
    "--field", "-f", multiple=True,
    help='Field spec: "fieldName:type" or "fieldName:relation:TargetEntity". Repeatable.',
    metavar="FIELD_SPEC",
)
@click.option("--nav-section", default="Entities", show_default=True, help="Sidebar nav section.")
@click.option("--nav-icon", default="file", show_default=True, help="Lucide icon name.")
@click.option("--tenant/--no-tenant", default=True, help="Tenant-scope the entity (default: yes).")
@click.option("--no-screen", is_flag=True, help="Skip screen YAML generation.")
@click.option("--no-views", is_flag=True, help="Skip view YAML generation.")
@click.option("--dry-run", is_flag=True, help="Print generated YAML to stdout; don't write files.")
@click.option("--force", is_flag=True, help="Overwrite existing files.")
def entity(
    name: str,
    field: tuple[str, ...],
    nav_section: str,
    nav_icon: str,
    tenant: bool,
    no_screen: bool,
    no_views: bool,
    dry_run: bool,
    force: bool,
) -> None:
    """Scaffold a new entity with YAML metadata files.

    NAME must be PascalCase (e.g. Deal, FundingDocument).

    \b
    Examples:
      metaforge new entity Deal \\
        --field name:name \\
        --field amount:currency \\
        --field status:picklist \\
        --field companyId:relation:Company \\
        --nav-section CRM --nav-icon briefcase

      metaforge new entity Requirement --no-tenant --nav-section Requirements
    """
    # --- Validate name
    if not name[0].isupper():
        click.echo(
            f"Error: entity name '{name}' must start with an uppercase letter "
            f"(e.g. '{name.capitalize()}').",
            err=True,
        )
        sys.exit(1)

    slug = _to_slug(name)
    metadata_path = _resolve_metadata_path()

    # --- Parse fields
    parsed_fields: list[dict] = []
    for spec in field:
        f = _parse_field(spec)
        if f:
            parsed_fields.append(f)

    label = _label_field(parsed_fields)

    # --- Build file map {target_path: content}
    files: dict[Path, str] = {}

    files[metadata_path / "entities" / f"{slug}.yaml"] = _entity_yaml(
        name, slug, label, parsed_fields, tenant
    )

    if not no_screen:
        files[metadata_path / "screens" / f"{slug}.yaml"] = _screen_yaml(
            name, slug, nav_section, nav_icon
        )

    if not no_views:
        files[metadata_path / "views" / f"{slug}-grid.yaml"] = _grid_yaml(name, slug, parsed_fields)
        files[metadata_path / "views" / f"{slug}-form.yaml"] = _form_yaml(name, slug, parsed_fields)
        files[metadata_path / "views" / f"{slug}-detail.yaml"] = _detail_yaml(name, slug, parsed_fields)

    # --- Conflict detection
    if not force and not dry_run:
        conflicts = [p for p in files if p.exists()]
        if conflicts:
            click.echo("Error: the following files already exist (use --force to overwrite):", err=True)
            for p in conflicts:
                click.echo(f"  {p}", err=True)
            sys.exit(1)

    # --- Write or print
    if dry_run:
        for path, content in files.items():
            click.echo(f"# {'='*60}")
            click.echo(f"# {path}")
            click.echo(f"# {'='*60}")
            click.echo(content)
        return

    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        click.echo(f"  \u2713 {path}")

    click.echo("")
    click.echo(f"Entity '{name}' scaffolded. Next steps:")

    picklist_fields = [f["name"] for f in parsed_fields if f["type"] == "picklist"]
    if picklist_fields:
        fields_str = ", ".join(picklist_fields)
        click.echo(f"  1. Edit placeholder picklist options ({fields_str}) in metadata/entities/{slug}.yaml")
        click.echo(f"  2. Run: metaforge migrate generate -m \"add {name} entity\"")
        click.echo(f"  3. Run: metaforge migrate apply")
    else:
        click.echo(f"  1. Run: metaforge migrate generate -m \"add {name} entity\"")
        click.echo(f"  2. Run: metaforge migrate apply")
