"""
Session: representa o estado vivo de UMA aba/conexão do navegador.

Guarda a árvore de instâncias de componentes (pra hooks persistirem entre
re-renders), a última árvore host renderizada (pra diffar contra a
próxima) e o registro de handlers de evento atuais.
"""
from __future__ import annotations
import uuid
from typing import Callable
from .vdom import VNode
from .reconciler import resolve_tree
from .renderer import render_to_html, collect_handlers
from .diff import diff


class Session:
    def __init__(self, root_fn: Callable):
        self.id = uuid.uuid4().hex
        self.root_fn = root_fn
        self.instances: dict = {}
        self.pending_effect_instances: list = []
        self.handlers: dict = {}
        self.tree: VNode | None = None
        self._needs_rerender = False

    def schedule_rerender(self) -> None:
        self._needs_rerender = True

    def _run_effects(self) -> None:
        instances = self.pending_effect_instances
        self.pending_effect_instances = []
        for instance in instances:
            instance.run_pending_effects()

    def render_initial(self) -> str:
        from .vdom import h
        root_vnode = h(self.root_fn, {})
        self.tree = resolve_tree(root_vnode, self)
        self.handlers.clear()
        html = render_to_html(self.tree, self.handlers)
        self._run_effects()
        return html

    def rerender(self) -> list:
        """Roda uma nova renderização e retorna a lista de patches em
        relação à árvore anterior."""
        from .vdom import h
        root_vnode = h(self.root_fn, {})
        new_tree = resolve_tree(root_vnode, self)
        patches = diff(self.tree, new_tree)
        self.tree = new_tree
        self.handlers.clear()
        collect_handlers(self.tree, self.handlers)
        self._run_effects()
        return patches

    def rerender_if_needed(self) -> list:
        if not self._needs_rerender:
            return []
        self._needs_rerender = False
        patches = self.rerender()
        # um efeito pode ter chamado set_state de novo; renderiza em cascata
        while self._needs_rerender:
            self._needs_rerender = False
            patches += self.rerender()
        return patches

    def dispatch_event(self, pyid: str, event_name: str, value) -> None:
        node_handlers = self.handlers.get(pyid)
        if not node_handlers:
            return
        handler = node_handlers.get(event_name)
        if handler is None:
            return
        try:
            handler(value)
        except TypeError:
            handler()
        self.schedule_rerender()
