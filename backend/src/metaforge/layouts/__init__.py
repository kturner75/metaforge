"""MetaForge file-layout system (MF-020).

A *file layout* is metadata describing how a flat file (delimited or
fixed-width) maps to and from entity values. It works both directions:

    from metaforge.layouts import LayoutLoader, read, write

    loader = LayoutLoader(metadata_path / "layouts")
    loader.load_all()
    layout = loader.get_layout("ContactCsv")

    result = read(layout, csv_bytes, entity=contact_model)   # file -> records
    out = write(layout, result.data, entity=contact_model)   # records -> file

Reads carry exact provenance (row / column / byte offset) and fail loudly on
drift. Transforms are declarative and bidirectional, with an expression-DSL
escape hatch for edge cases.
"""

from metaforge.layouts.loader import LayoutLoader, parse_layout
from metaforge.layouts.reader import read
from metaforge.layouts.transforms import (
    TRANSFORMS,
    TransformSpec,
    apply_transforms,
    invert_transforms,
    is_known_transform,
)
from metaforge.layouts.types import (
    CellLocation,
    CoercionError,
    FieldMapping,
    FileFormat,
    LayoutConfigError,
    LayoutDefinition,
    LayoutError,
    LayoutReadError,
    ReadIssue,
    ReadRecord,
    ReadResult,
    RecordType,
    RecordTypeSelector,
    SourceSpec,
    TransformError,
    TransformStep,
)
from metaforge.layouts.writer import write

__all__ = [
    # Loader
    "LayoutLoader",
    "parse_layout",
    # Engine
    "read",
    "write",
    # Transforms
    "TRANSFORMS",
    "TransformSpec",
    "apply_transforms",
    "invert_transforms",
    "is_known_transform",
    # Types
    "CellLocation",
    "FieldMapping",
    "FileFormat",
    "LayoutDefinition",
    "ReadIssue",
    "ReadRecord",
    "ReadResult",
    "RecordType",
    "RecordTypeSelector",
    "SourceSpec",
    "TransformStep",
    # Errors
    "CoercionError",
    "LayoutConfigError",
    "LayoutError",
    "LayoutReadError",
    "TransformError",
]
