"""Field type registry with storage and UI defaults."""

from dataclasses import dataclass


@dataclass
class UIDefaults:
    display_component: str
    edit_component: str
    filter_component: str
    grid_component: str
    filter_operator: str = "eq"
    alignment: str = "left"
    format: str | None = None


@dataclass
class FieldType:
    name: str
    storage_type: str
    ui: UIDefaults
    query_operators: list[str]


# Built-in field types
FIELD_TYPES: dict[str, FieldType] = {
    "id": FieldType(
        name="id",
        storage_type="TEXT",  # Sequence-based IDs like "CMP-00001"
        ui=UIDefaults(
            display_component="Text",
            edit_component="TextInput",
            filter_component="TextInput",
            grid_component="Text",
        ),
        query_operators=["eq", "in", "isNull"],
    ),
    "uuid": FieldType(
        name="uuid",
        storage_type="TEXT",
        ui=UIDefaults(
            display_component="Text",
            edit_component="TextInput",
            filter_component="TextInput",
            grid_component="Text",
        ),
        query_operators=["eq", "in", "isNull"],
    ),
    "string": FieldType(
        name="string",
        storage_type="TEXT",
        ui=UIDefaults(
            display_component="Text",
            edit_component="TextInput",
            filter_component="TextInput",
            grid_component="Text",
        ),
        query_operators=["eq", "neq", "contains", "startsWith", "in", "isNull"],
    ),
    "name": FieldType(
        name="name",
        storage_type="TEXT",
        ui=UIDefaults(
            display_component="Text",
            edit_component="TextInput",
            filter_component="TextInput",
            grid_component="Text",
        ),
        query_operators=["eq", "neq", "contains", "startsWith", "in", "isNull"],
    ),
    "text": FieldType(
        name="text",
        storage_type="TEXT",
        ui=UIDefaults(
            display_component="Text",
            edit_component="TextArea",
            filter_component="TextInput",
            grid_component="Text",
        ),
        query_operators=["contains", "isNull"],
    ),
    "description": FieldType(
        name="description",
        storage_type="TEXT",
        ui=UIDefaults(
            display_component="Text",
            edit_component="TextArea",
            filter_component="TextInput",
            grid_component="Text",
        ),
        query_operators=["contains", "isNull"],
    ),
    "email": FieldType(
        name="email",
        storage_type="TEXT",
        ui=UIDefaults(
            display_component="Text",
            edit_component="TextInput",
            filter_component="TextInput",
            grid_component="Text",
        ),
        query_operators=["eq", "contains", "isNull"],
    ),
    "phone": FieldType(
        name="phone",
        storage_type="TEXT",
        ui=UIDefaults(
            display_component="Text",
            edit_component="TextInput",
            filter_component="TextInput",
            grid_component="Text",
        ),
        query_operators=["eq", "contains", "isNull"],
    ),
    "url": FieldType(
        name="url",
        storage_type="TEXT",
        ui=UIDefaults(
            display_component="UrlLink",
            edit_component="TextInput",
            filter_component="TextInput",
            grid_component="UrlLink",
        ),
        query_operators=["eq", "contains", "isNull"],
    ),
    "picklist": FieldType(
        name="picklist",
        storage_type="TEXT",
        ui=UIDefaults(
            display_component="Badge",
            edit_component="Select",
            filter_component="Select",
            grid_component="Badge",
            filter_operator="in",
        ),
        query_operators=["eq", "in", "notIn", "isNull"],
    ),
    "multi_picklist": FieldType(
        name="multi_picklist",
        storage_type="TEXT",  # JSON array stored as text
        ui=UIDefaults(
            display_component="MultiPicklistBadges",
            edit_component="Select",
            filter_component="Select",
            grid_component="MultiPicklistBadges",
            filter_operator="in",
        ),
        query_operators=["contains", "isNull"],
    ),
    "checkbox": FieldType(
        name="checkbox",
        storage_type="INTEGER",  # 0/1
        ui=UIDefaults(
            display_component="Badge",
            edit_component="Checkbox",
            filter_component="Select",
            grid_component="Badge",
        ),
        query_operators=["eq", "isNull"],
    ),
    "date": FieldType(
        name="date",
        storage_type="TEXT",  # ISO format
        ui=UIDefaults(
            display_component="Text",
            edit_component="DatePicker",
            filter_component="DateRangePicker",
            grid_component="Text",
            filter_operator="between",
            format="MMM D, YYYY",
        ),
        query_operators=["eq", "gt", "gte", "lt", "lte", "between", "isNull"],
    ),
    "datetime": FieldType(
        name="datetime",
        storage_type="TEXT",  # ISO format
        ui=UIDefaults(
            display_component="Text",
            edit_component="DateTimePicker",
            filter_component="DateRangePicker",
            grid_component="Text",
            filter_operator="between",
            format="MMM D, YYYY h:mm A",
        ),
        query_operators=["eq", "gt", "gte", "lt", "lte", "between", "isNull"],
    ),
    "number": FieldType(
        name="number",
        storage_type="REAL",
        ui=UIDefaults(
            display_component="Text",
            edit_component="NumberInput",
            filter_component="NumberRange",
            grid_component="Text",
            filter_operator="between",
            alignment="right",
        ),
        query_operators=["eq", "gt", "gte", "lt", "lte", "between", "isNull"],
    ),
    "currency": FieldType(
        name="currency",
        storage_type="REAL",
        ui=UIDefaults(
            display_component="Text",
            edit_component="CurrencyInput",
            filter_component="NumberRange",
            grid_component="Text",
            filter_operator="between",
            alignment="right",
            format="$#,##0.00",
        ),
        query_operators=["eq", "gt", "gte", "lt", "lte", "between", "isNull"],
    ),
    "percent": FieldType(
        name="percent",
        storage_type="REAL",
        ui=UIDefaults(
            display_component="Text",
            edit_component="NumberInput",
            filter_component="NumberRange",
            grid_component="Text",
            filter_operator="between",
            alignment="right",
            format="#,##0.##%",
        ),
        query_operators=["eq", "gt", "gte", "lt", "lte", "between", "isNull"],
    ),
    "boolean": FieldType(
        name="boolean",
        storage_type="INTEGER",  # 0/1
        ui=UIDefaults(
            display_component="Badge",
            edit_component="Checkbox",
            filter_component="Select",
            grid_component="Badge",
        ),
        query_operators=["eq", "isNull"],
    ),
    "relation": FieldType(
        name="relation",
        storage_type="TEXT",  # Stores foreign key (e.g., "CMP-00001")
        ui=UIDefaults(
            display_component="Text",
            edit_component="RelationSelect",
            filter_component="RelationSelect",
            grid_component="Text",
        ),
        query_operators=["eq", "in", "notIn", "isNull"],
    ),
    "address": FieldType(
        name="address",
        storage_type="TEXT",  # JSON or structured text
        ui=UIDefaults(
            display_component="Text",
            edit_component="TextArea",
            filter_component="TextInput",
            grid_component="Text",
        ),
        query_operators=["contains", "isNull"],
    ),
    "attachment": FieldType(
        name="attachment",
        storage_type="TEXT",  # URL/path to file
        ui=UIDefaults(
            display_component="UrlLink",
            edit_component="TextInput",
            filter_component="TextInput",
            grid_component="UrlLink",
        ),
        query_operators=["isNull"],
    ),
}


def get_field_type(type_name: str) -> FieldType:
    """Get field type definition, defaulting to string if unknown."""
    return FIELD_TYPES.get(type_name, FIELD_TYPES["string"])


def get_storage_type(type_name: str) -> str:
    """Get SQLite storage type for a field type."""
    return get_field_type(type_name).storage_type
