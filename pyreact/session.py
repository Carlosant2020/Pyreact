"""
Session: representa o estado vivo de UMA aba/conexão do navegador.

Guarda a árvore de instâncias de componentes (pra hooks persistirem entre
re-renders), a última árvore host renderizada (pra diffar contra a
próxima) e o registro de handlers de evento atuais.
"""
from __future__ import annotations
import asyncio
import inspect
import logging
import time
import uuid
from typing import Callable
from .vdom import VNode
from .reconciler import resolve_tree
from .renderer import render_to_html, collect_handlers
from .diff import diff

logger = logging.getLogger(__name__)


def _accepts_argument(fn: Callable) -> bool:
    """True se `fn` aceita pelo menos um argumento posicional. Decidir isso
    pela assinatura (e não tentando chamar e capturando TypeError) evita
    executar o handler duas vezes quando o TypeError vem de dentro dele."""
    try:
        params = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return True  # builtins/callables sem assinatura inspecionável
    return any(
        p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD, p.VAR_POSITIONAL)
        for p in params
    )


class Session:
    def __init__(self, root_fn: Callable):
        self.id = uuid.uuid4().hex
        self.root_fn = root_fn
        self.instances: dict = {}
        self.pending_effect_instances: list = []
        self.handlers: dict = {}
        self.tree: VNode | None = None
        self._needs_rerender = False
        # ciclo de vida da conexão (usado pelo app pra expirar sessões órfãs)
        self.created_at = time.monotonic()
        self.disconnected_at: float | None = None
        self.connect_count = 0
        self.connected = False
        # server push: o app registra o event loop e um Event que acorda o
        # "empurrador" de patches sempre que o estado muda (de qualquer thread)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._wakeup: asyncio.Event | None = None
        # handlers async em andamento (cancelados no close())
        self._tasks: set = set()

    def mark_connected(self) -> int:
        """Registra uma (re)conexão de WebSocket e devolve um token que
        identifica ESSA conexão — assim um socket antigo que fecha depois
        não derruba o estado 'conectado' de um socket mais novo."""
        self.connect_count += 1
        self.connected = True
        self.disconnected_at = None
        return self.connect_count

    def mark_disconnected(self, token: int) -> None:
        if token == self.connect_count:
            self.connected = False
            self.disconnected_at = time.monotonic()

    def is_expired(self, ttl: float, now: float | None = None) -> bool:
        """Sessão sem WebSocket há mais de `ttl` segundos (contando desde a
        criação, se nunca conectou, ou desde a última desconexão)."""
        if self.connected:
            return False
        now = time.monotonic() if now is None else now
        reference = self.disconnected_at if self.disconnected_at is not None else self.created_at
        return now - reference > ttl

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Liga a sessão a um event loop (chamado a cada nova conexão). O
        Event é recriado de propósito: um "empurrador" antigo, de uma
        conexão que já caiu, fica esperando num Event órfão e nunca acorda."""
        self._loop = loop
        self._wakeup = asyncio.Event()

    def wake(self) -> None:
        """Acorda o empurrador de patches. Seguro de chamar de QUALQUER thread
        (um Thread ou Timer chamando set_state cai aqui)."""
        loop, wakeup = self._loop, self._wakeup
        if loop is None or wakeup is None:
            return  # ainda sem conexão: a mudança fica marcada e é enviada ao conectar
        try:
            loop.call_soon_threadsafe(wakeup.set)
        except RuntimeError:
            pass  # o event loop já foi fechado

    async def wait_for_update(self) -> None:
        """Espera até que algo peça um novo render."""
        wakeup = self._wakeup
        if wakeup is None:
            raise RuntimeError("attach_loop() precisa ser chamado antes de wait_for_update()")
        await wakeup.wait()
        wakeup.clear()  # limpa ANTES de renderizar: mudanças durante o render acordam de novo

    def close(self) -> None:
        """Encerra a sessão: cancela handlers async em andamento e roda o
        cleanup de todos os efeitos ativos (o que também cancela as tarefas
        de efeitos async, como use_interval)."""
        for task in list(self._tasks):
            task.cancel()
        self._tasks.clear()
        for instance in list(self.instances.values()):
            instance.unmount()
        self.instances.clear()
        self._loop = None
        self._wakeup = None

    def schedule_rerender(self) -> None:
        self._needs_rerender = True
        self.wake()

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

    def full_html(self) -> str:
        """HTML completo da árvore atual — usado pra ressincronizar um
        cliente que reconectou."""
        self.handlers.clear()
        return render_to_html(self.tree, self.handlers)

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
            if _accepts_argument(handler):
                result = handler(value)
            else:
                result = handler()
            if inspect.isawaitable(result):
                # handler `async def`: roda como tarefa, então a aba continua
                # respondendo a outros eventos enquanto ele espera
                self._spawn_handler(result, event_name, pyid)
        except Exception:
            # um handler com bug não pode derrubar a conexão da aba inteira
            logger.exception("Erro no handler do evento %r em %r", event_name, pyid)
        finally:
            self.schedule_rerender()

    def _spawn_handler(self, awaitable, event_name: str, pyid: str) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            if hasattr(awaitable, "close"):
                awaitable.close()  # evita o aviso "coroutine was never awaited"
            logger.error("Handler async precisa de um event loop em execução "
                         "(rode a app via PyReactApp.run()).")
            return
        task = loop.create_task(self._run_handler(awaitable, event_name, pyid))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run_handler(self, awaitable, event_name: str, pyid: str) -> None:
        try:
            await awaitable
        except Exception:
            logger.exception("Erro no handler async do evento %r em %r", event_name, pyid)
        finally:
            self.schedule_rerender()  # o handler pode ter mudado dados que não são hooks
