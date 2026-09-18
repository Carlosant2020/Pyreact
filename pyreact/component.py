"""
ComponentInstance: representa uma instância viva de um componente na árvore.
Persiste entre re-renders para que hooks (useState, useEffect) mantenham
seu estado — exatamente como um Fiber no React.
"""
from __future__ import annotations
from typing import Callable, Any


class ComponentInstance:
    def __init__(self, fn: Callable, session: "Session"):
        self.fn = fn
        self.session = session
        self.hooks: list[dict] = []
        self.hook_index: int = 0
        self.pending_effects: list[tuple] = []

    def request_rerender(self) -> None:
        self.session.schedule_rerender()

    def run_pending_effects(self) -> None:
        for slot, effect, deps in self.pending_effects:
            if slot.get("cleanup"):
                try:
                    slot["cleanup"]()
                except Exception:
                    pass
            cleanup = effect()
            slot["cleanup"] = cleanup if callable(cleanup) else None
            slot["deps"] = deps
        self.pending_effects.clear()
