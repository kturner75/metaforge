"""MetaForge entity lifecycle hook system.

Provides extension points for logic that runs at specific points
in the entity save/delete lifecycle:
- beforeSave: After validation, before persist (can modify record, can abort)
- afterSave: After persist, before commit (same transaction, can abort)
- afterCommit: After commit (fire-and-forget side effects)
- beforeDelete: Before delete (can abort)

Usage:
    from metaforge.hooks import hook, HookContext, HookResult

    @hook("computeContractValue")
    async def compute_contract_value(ctx: HookContext) -> HookResult:
        total = sum(item["amount"] for item in line_items)
        return HookResult(update={"totalValue": total})
"""

from metaforge.hooks.registry import HookRegistry, hook
from metaforge.hooks.service import HookService
from metaforge.hooks.types import (
    HookContext,
    HookDefinition,
    HookResult,
    compute_changes,
)

VALID_HOOK_POINTS = ("beforeSave", "afterSave", "afterCommit", "beforeDelete")


def register_builtin_hooks() -> None:
    """Register framework-provided hooks.

    Called at application startup. Currently a no-op placeholder
    for future built-in hooks (e.g., audit logging).
    """
    pass


__all__ = [
    "HookContext",
    "HookDefinition",
    "HookRegistry",
    "HookResult",
    "HookService",
    "VALID_HOOK_POINTS",
    "compute_changes",
    "hook",
    "register_builtin_hooks",
]
