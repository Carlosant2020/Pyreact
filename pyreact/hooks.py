"""
Hooks no estilo React (useState, useEffect, useMemo).

Cada "instância" de componente (ver component.py) guarda uma lista de
hooks em ordem de chamada — exatamente como o React faz. Por isso, hooks
devem ser chamados sempre na mesma ordem, sem estarem dentro de if/for.
"""
from __future__ import annotations
import contextvars
from typing import Any, Callable

_current_instance: contextvars.ContextVar = contextvars.ContextVar("current_instance")


class HookContext:
    """Contexto ativo durante a renderização de UM componente."""

    def __init__(self, instance: "ComponentInstance"):
        self.instance = instance
        self._token = None

    def __enter__(self):
        self.instance.hook_index = 0
        self._token = _current_instance.set(self.instance)
        return self.instance

    def __exit__(self, *exc):
        _current_instance.reset(self._token)


def _get_instance() -> "ComponentInstance":
    try:
        return _current_instance.get()
    except LookupError as e:
        raise RuntimeError(
            "Hooks só podem ser chamados durante a renderização de um componente."
        ) from e


def use_state(initial: Any) -> tuple[Any, Callable]:
    instance = _get_instance()
    idx = instance.hook_index
    instance.hook_index += 1

    if idx >= len(instance.hooks):
        value = initial() if callable(initial) else initial
        instance.hooks.append({"value": value})

    slot = instance.hooks[idx]

    def set_state(new_value, _slot=slot, _instance=instance):
        next_value = new_value(_slot["value"]) if callable(new_value) else new_value
        if next_value != _slot["value"]:
            _slot["value"] = next_value
            _instance.request_rerender()

    return slot["value"], set_state


def use_effect(effect: Callable, deps: list | None = None) -> None:
    instance = _get_instance()
    idx = instance.hook_index
    instance.hook_index += 1

    if idx >= len(instance.hooks):
        instance.hooks.append({"deps": None, "cleanup": None})

    slot = instance.hooks[idx]
    changed = deps is None or slot["deps"] != deps

    if changed:
        instance.pending_effects.append((slot, effect, deps))


def use_memo(factory: Callable, deps: list) -> Any:
    instance = _get_instance()
    idx = instance.hook_index
    instance.hook_index += 1

    if idx >= len(instance.hooks):
        instance.hooks.append({"deps": None, "value": None})

    slot = instance.hooks[idx]
    if slot["deps"] != deps:
        slot["value"] = factory()
        slot["deps"] = deps
    return slot["value"]
