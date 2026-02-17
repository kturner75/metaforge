"""Hook execution service for MetaForge.

Orchestrates the execution of hooks at each lifecycle point,
handling conditional execution, sequential ordering, result merging,
and error handling for afterCommit hooks.
"""

import logging
from typing import Any

from metaforge.hooks.registry import HookRegistry
from metaforge.hooks.types import HookContext, HookDefinition, HookResult
from metaforge.validation.expressions import evaluate_bool

logger = logging.getLogger(__name__)


class HookService:
    """Orchestrates hook execution for entity lifecycle events.

    Hooks within a hook point execute sequentially in declared order.
    Each hook's update output is merged before the next hook runs.
    """

    async def run_hooks(
        self,
        hook_point: str,
        definitions: list[HookDefinition],
        context: HookContext,
    ) -> HookResult | None:
        """Execute hooks for a given hook point.

        Args:
            hook_point: The lifecycle point (beforeSave, afterSave, afterCommit, beforeDelete)
            definitions: Hook definitions from entity metadata (in declared order)
            context: The hook context with current record state

        Returns:
            Merged HookResult with all updates applied, or None if no hooks ran.
            If any hook aborts, returns immediately with the abort message.
        """
        if not definitions:
            return None

        is_after_commit = hook_point == "afterCommit"
        merged_updates: dict[str, Any] = {}

        for definition in definitions:
            # Check if hook applies to this operation
            if context.operation not in definition.on:
                continue

            # Evaluate when condition
            if definition.when:
                try:
                    if not evaluate_bool(
                        definition.when, context.record, context.original
                    ):
                        continue
                except Exception:
                    # If condition can't be evaluated, skip this hook
                    logger.warning(
                        "Hook '%s' when condition failed to evaluate: %s",
                        definition.name,
                        definition.when,
                    )
                    continue

            # Resolve the hook function
            try:
                hook_fn = HookRegistry.get(definition.name)
            except ValueError:
                logger.warning(
                    "Hook '%s' is not registered, skipping", definition.name
                )
                continue

            # Execute the hook
            try:
                result = await hook_fn(context)
            except Exception as e:
                if is_after_commit:
                    # afterCommit hooks are fire-and-forget
                    logger.error(
                        "afterCommit hook '%s' failed: %s",
                        definition.name,
                        e,
                    )
                    continue
                else:
                    # Other hooks propagate errors as aborts
                    return HookResult(abort=f"Hook '{definition.name}' failed: {e}")

            if result is None:
                continue

            # Check for abort
            if result.abort:
                return result

            # Merge updates into context record (compounding)
            if result.update:
                context.record.update(result.update)
                merged_updates.update(result.update)

        if merged_updates:
            return HookResult(update=merged_updates)

        return None
