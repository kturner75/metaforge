# ADR-0005: Validation Message Interpolation

## Status
Accepted

## Context
Validation error/warning messages need to include dynamic values:
- Field values (current and original)
- Field labels
- Formatted for human readability (not raw database values)

## Decision
We will implement template interpolation with presentation-aware formatting.

### Template Syntax

| Syntax | Output | Example |
|--------|--------|---------|
| `{fieldName}` | Formatted/presented value | `"Active"` (picklist label) |
| `{fieldName:value}` | Same as above (explicit) | `"January 15, 2024"` (date) |
| `{fieldName:raw}` | Raw stored value | `"active"`, `"2024-01-15"` |
| `{fieldName:label}` | Field's display label | `"Contract Status"` |
| `{original.fieldName}` | Original value (updates) | Previous value before change |

### Presentation Rules by Field Type

| Field Type | Presentation |
|------------|--------------|
| `picklist` | Option label (not value) |
| `multi_picklist` | Comma-separated labels |
| `date` | Locale-formatted date (`"January 15, 2024"`) |
| `datetime` | Locale-formatted datetime |
| `currency` | Formatted with symbol (`"$1,234.56"`) |
| `percent` | Formatted with symbol (`"25%"`) |
| `boolean` | `"Yes"` / `"No"` (localizable) |
| `relation` | Display field of related record |
| `text`, `string`, etc. | Value as-is |

### Example

```yaml
# Metadata
fields:
  - name: status
    type: picklist
    label: "Contract Status"
    options:
      - value: active
        label: Active
      - value: terminated
        label: Terminated

  - name: discountPercent
    type: percent
    label: "Discount"

validators:
  - type: expression
    rule: 'status != "terminated" || original.status == "terminated"'
    message: "Cannot change {status:label} from {original.status} to {status}"

  - type: expression
    rule: "discountPercent <= 50"
    message: "{discountPercent:label} of {discountPercent} exceeds maximum of 50%"
```

**Rendered messages:**
```
"Cannot change Contract Status from Active to Terminated"
"Discount of 75% exceeds maximum of 50%"
```

### Implementation

```python
class MessageInterpolator:
    PATTERN = re.compile(
        r"\{(?P<prefix>original\.)?(?P<field>\w+)(?::(?P<modifier>value|raw|label))?\}"
    )

    def interpolate(
        self,
        template: str,
        record: dict,
        original: dict | None,
        entity: EntityMetadata,
        locale: str = "en-US"
    ) -> str:
        def replace(match: re.Match) -> str:
            prefix = match.group("prefix")
            field_name = match.group("field")
            modifier = match.group("modifier") or "value"

            field_def = entity.get_field(field_name)
            if not field_def:
                return match.group(0)  # Leave unchanged

            source = original if prefix else record
            value = source.get(field_name) if source else None

            if modifier == "label":
                return field_def.label
            elif modifier == "raw":
                return str(value) if value is not None else ""
            else:  # "value" - formatted presentation
                return self.presenter.present(field_def, value, locale)

        return self.PATTERN.sub(replace, template)
```

### Locale Support
- Dates, numbers, and currencies format according to user's locale
- Locale determined from user context or request header
- Boolean labels (`"Yes"/"No"`) are localizable

## Consequences

### Positive
- Human-readable messages with context
- Consistent formatting across all messages
- Support for comparing original vs new values
- Locale-aware presentation

### Negative
- Template parsing overhead (minimal, can cache compiled patterns)
- Requires field metadata available at message rendering time
- Relation display requires additional lookup

### Edge Cases
- Unknown field: Leave token unchanged `{unknownField}`
- Null value: Empty string `""`
- Missing original on create: Empty string for `{original.*}`
