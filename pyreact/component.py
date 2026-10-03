"""
ComponentInstance: representa uma instância viva de um componente na árvore.
Persiste entre re-renders para que hooks (useState, useEffect) mantenham
seu estado — exatamente como um Fiber no React.
"""
from __future__ import annotations
import asyncio
import inspect
import logging
from typing import Callable, Any

logger = logging.getLogger(__name__)


def report_task_error(task: "asyncio.Task") -> None:
    """done-callback: uma tarefa em segundo plano que morre com exceção não
    pode falhar em silêncio (o asyncio só reclama quando o objeto é coletado)."""
    if task.cancelled():
        return
    error = task.exception()
    if error is not None:
        logger.error("Tarefa em segundo plano falhou", exc_info=error)


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
                    logger.exception("Erro no cleanup de um efeito")
            try:
                result = effect()
                if inspect.iscoroutine(result):
                    # efeito `async def`: vira uma tarefa em segundo plano,
                    # cancelada automaticamente no cleanup (deps mudaram ou
                    # o componente saiu da tela)
                    result = self._start_async_effect(result)
            except Exception:
                logger.exception("Erro ao executar um efeito")
                result = None
            slot["cleanup"] = result if callable(result) else None
            slot["deps"] = deps
        self.pending_effects.clear()

    @staticmethod
    def _start_async_effect(coro) -> Callable | None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            coro.close()  # evita o aviso "coroutine was never awaited"
            logger.error("Efeito async precisa de um event loop em execução "
                         "(rode a app via PyReactApp.run()).")
            return None
        task = loop.create_task(coro)
        task.add_done_callback(report_task_error)
        return task.cancel

    def unmount(self) -> None:
        """Chamado quando o componente sai da árvore: roda o cleanup de todo
        efeito que ainda estiver ativo (timers, conexões, etc.), pra não
        vazar recursos — equivalente ao `return () => ...` do useEffect."""
        for slot in self.hooks:
            cleanup = slot.get("cleanup")
            if callable(cleanup):
                try:
                    cleanup()
                except Exception:
                    logger.exception("Erro no cleanup de um efeito ao desmontar")
                slot["cleanup"] = None
        self.pending_effects.clear()
