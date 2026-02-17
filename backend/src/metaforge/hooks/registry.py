"""Hook registry for MetaForge.

Provides registration and lookup for hook implementations.
Follows the same pattern as ValidatorRegistry.
"""

from collections.abc import Awaitable, Callable

from metaforge.hooks.types import HookContext, HookResult

# Hook function signature: async (HookContext) -> HookResult | None
HookFn = Callable[[HookContext], Awaitable[HookResult | None]]


class HookRegistry:
    """Registry for hook implementations.

    Hooks must be explicitly registered before they can be referenced
    from entity metadata. Registration is typically done at application
    startup via register_builtin_hooks() or the @hook decorator.

    Example:
        @hook("computeContractValue")
        async def compute_contract_value(ctx: HookContext) -> HookResult:
            ...
    """

    _hooks: dict[str, HookFn] = {}

    @classmethod
    def register(cls, name: str, hook_fn: HookFn) -> None:
        """Register a hook function by name.

        Idempotent — re-registering the same name is a no-op.

        Args:
            name: Unique identifier for the hook
            hook_fn: Async function implementing the hook
        """
        if name in cls._hooks:
            return
        cls._hooks[name] = hook_fn

    @classmethod
    def get(cls, name: str) -> HookFn:
        """Get a registered hook function by name.

        Args:
            name: The hook name

        Returns:
            The hook function

        Raises:
            ValueError: If hook is not registered
        """
        if name not in cls._hooks:
            raise ValueError(
                f"Hook '{name}' is not registered. "
                "Hooks must be explicitly registered at application startup."
            )
        return cls._hooks[name]

    @classmethod
    def is_registered(cls, name: str) -> bool:
        """Check if a hook is registered."""
        return name in cls._hooks

    @classmethod
    def list_registered(cls) -> list[str]:
        """List all registered hook names."""
        return sorted(cls._hooks.keys())

    @classmethod
    def clear(cls) -> None:
        """Clear all registrations. Primarily for testing."""
        cls._hooks.clear()


def hook(name: str) -> Callable[[HookFn], HookFn]:
    """Decorator to register a hook function.

    Usage:
        @hook("computeContractValue")
        async def compute_contract_value(ctx: HookContext) -> HookResult:
            ...
    """

    def decorator(fn: HookFn) -> HookFn:
        HookRegistry.register(name, fn)
        return fn

    return decorator
