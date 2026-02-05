# ADR-0002: Expression Language DSL

## Status
Accepted

## Context
MetaForge needs an expression language for:
- Validation rules (`discountPercent <= 50`)
- Conditional logic (`when: 'status == "active"'`)
- Computed defaults (`concat(firstName, " ", lastName)`)

Requirements:
- Readable syntax familiar to developers
- Safe execution (no arbitrary code)
- Evaluable on both Python backend and JavaScript frontend (for client-evaluable expressions)
- Extensible via registered functions

## Decision
We will implement a custom DSL with familiar syntax, parsed to an AST and evaluated in a sandbox.

### Syntax

#### Field References
```
discountPercent              # Current record value
original.discountPercent     # Original value (for updates)
record.status                # Explicit record prefix (optional)
```

#### Operators
```
==, !=, <, <=, >, >=         # Comparison
&&, ||, !                    # Logical (aliases: and, or, not)
+, -, *, /, %                # Arithmetic
in, not in                   # Collection membership
```

#### Literals
```
42, 3.14                     # Numbers
"active", 'active'           # Strings
true, false                  # Booleans
null                         # Null
["a", "b"]                   # Arrays
```

#### Functions
```
len(fieldName)               # String/array length
isEmpty(fieldName)           # Null or empty
now()                        # Current datetime
today()                      # Current date
daysBetween(date1, date2)    # Date math
concat(str1, str2, ...)      # String concatenation
coalesce(val1, val2, ...)    # First non-null
matches(field, "regex")      # Regex match
exists(entity, filter)       # Query (server-only)
count(entity, filter)        # Query (server-only)
```

### Function Registry
Functions are explicitly registered with metadata:
- Name, description, parameters, return type
- `client_evaluable` flag for frontend execution
- Implementation function (Python backend)

API endpoint `GET /api/functions` returns registry for documentation and tooling.

### Implementation Strategy
- Parser: Use `lark` or hand-rolled recursive descent to produce AST
- Evaluator: Walk AST with evaluation context (record, original, functions)
- JavaScript: Mirror implementation for client-side evaluation
- Functions marked `client_evaluable: false` cause expression to be server-only

## Examples

```yaml
# Simple comparison
rule: "discountPercent <= 50"

# Cross-field validation
rule: "minQuantity <= maxQuantity"

# Status transition (update only)
rule: "status != 'terminated' || original.status == 'terminated'"

# Date validation with function
rule: "expirationDate == null || daysBetween(effectiveDate, expirationDate) >= 30"

# Collection check
rule: "status in ['draft', 'pending'] || approvedBy != null"

# Query function (server-only)
rule: "!exists('Contract', {'parentId': id, 'status': 'active'})"
```

## Consequences

### Positive
- Familiar syntax reduces learning curve
- Safe sandbox execution prevents security issues
- Cross-platform evaluation enables client-side feedback
- Extensible function registry

### Negative
- Custom parser/evaluator to build and maintain
- Two implementations (Python + JavaScript) to keep in sync
- Limited expressiveness compared to full programming language

### Alternatives Considered
- **JSONLogic**: Too verbose, less readable
- **Python expressions**: Can't run on frontend, security concerns
- **JavaScript expressions**: Backend would need JS runtime, security concerns
- **CEL (Common Expression Language)**: Good option but adds dependency
