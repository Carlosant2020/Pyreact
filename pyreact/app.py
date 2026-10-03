"""
App: junta tudo — serve o HTML inicial (SSR) e mantém um WebSocket por aba
para receber eventos do navegador e mandar de volta só os patches
necessários (sem recarregar a página).
"""
from __future__ import annotations
import asyncio
import contextlib
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .session import Session

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"

_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="pt-br">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  {extra_head}
</head>
<body>
  <div id="pyreact-root">{body_html}</div>
  <script>window.__PYREACT_SESSION__ = "{session_id}";</script>
  <script src="/pyreact-static/client.js"></script>
</body>
</html>"""


class PyReactApp:
    def __init__(self, root_component: Callable, title: str = "PyReact App",
                 extra_head: str = "", session_ttl: float = 60.0,
                 reap_interval: float | None = None):
        self.root_component = root_component
        self.title = title
        self.extra_head = extra_head
        # segundos que uma sessão sem WebSocket é mantida na memória: cobre
        # tanto páginas que nunca conectaram (bots, abas fechadas cedo)
        # quanto o tempo de tolerância pra uma aba reconectar.
        self.session_ttl = session_ttl
        # de quanto em quanto tempo o faxineiro em segundo plano procura
        # sessões expiradas (sessões com timers ativos não podem esperar a
        # próxima requisição chegar pra serem limpas)
        self.reap_interval = (reap_interval if reap_interval is not None
                              else min(10.0, max(1.0, session_ttl / 4)))
        self.sessions: dict[str, Session] = {}
        self.fastapi = FastAPI(lifespan=self._lifespan)
        self.fastapi.mount("/pyreact-static", StaticFiles(directory=str(_STATIC_DIR)),
                            name="pyreact-static")
        self._register_routes()

    def _purge_stale_sessions(self, now: float | None = None) -> int:
        """Remove (e encerra) as sessões expiradas. Devolve quantas saíram."""
        now = time.monotonic() if now is None else now
        expired = [sid for sid, s in self.sessions.items()
                   if s.is_expired(self.session_ttl, now)]
        for sid in expired:
            self.sessions.pop(sid).close()
        return len(expired)

    @asynccontextmanager
    async def _lifespan(self, _app):
        reaper = asyncio.create_task(self._reap_forever())
        try:
            yield
        finally:
            reaper.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reaper
            # desligando: encerra todas as sessões (cleanup dos efeitos, timers, tarefas)
            for sid in list(self.sessions):
                self.sessions.pop(sid).close()

    async def _reap_forever(self) -> None:
        while True:
            await asyncio.sleep(self.reap_interval)
            try:
                self._purge_stale_sessions()
            except Exception:
                logger.exception("Erro ao limpar sessões expiradas")

    async def _push_loop(self, websocket: WebSocket, session: Session) -> None:
        """Espera o estado da sessão mudar (evento do cliente, timer, thread,
        tarefa async...) e manda os patches — é isso que permite o servidor
        falar sem o cliente ter falado antes."""
        while True:
            await session.wait_for_update()
            try:
                patches = session.rerender_if_needed()
            except Exception:
                # um componente com bug no render não pode matar o empurrador
                logger.exception("Erro ao renderizar a sessão %s", session.id)
                continue
            if not patches:
                continue
            try:
                await websocket.send_json({"type": "patches", "patches": patches})
            except Exception:
                return  # conexão quebrada: o laço de leitura vai perceber e encerrar

    def _register_routes(self) -> None:
        @self.fastapi.get("/", response_class=HTMLResponse)
        async def index():
            self._purge_stale_sessions()
            session = Session(self.root_component)
            body_html = session.render_initial()
            self.sessions[session.id] = session
            return _PAGE_TEMPLATE.format(
                title=self.title,
                extra_head=self.extra_head,
                body_html=body_html,
                session_id=session.id,
            )

        @self.fastapi.websocket("/ws/{session_id}")
        async def ws_endpoint(websocket: WebSocket, session_id: str):
            await websocket.accept()
            session = self.sessions.get(session_id)
            if session is None:
                await websocket.close(code=4404)
                return
            token = session.mark_connected()
            session.attach_loop(asyncio.get_running_loop())
            pusher = None
            try:
                if token > 1:
                    # reconexão: aplica o que ficou pendente enquanto estava
                    # desconectado e manda o HTML completo pra garantir que o
                    # navegador e o servidor concordam sobre o estado da UI
                    session.rerender_if_needed()
                    await websocket.send_json({"type": "full", "html": session.full_html()})
                pusher = asyncio.create_task(self._push_loop(websocket, session))
                session.wake()  # envia o que mudou entre o SSR e a conexão (ex.: timers)
                while True:
                    data = await websocket.receive_json()
                    session.dispatch_event(data["pyid"], data["event"], data.get("value"))
            except WebSocketDisconnect:
                pass
            finally:
                if pusher is not None:
                    pusher.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await pusher
                # a sessão NÃO é apagada aqui: fica disponível pelo `session_ttl`
                # pra aba poder reconectar sem perder o estado
                session.mark_disconnected(token)
                self._purge_stale_sessions()

    def run(self, host: str = "127.0.0.1", port: int = 8000) -> None:
        import uvicorn
        uvicorn.run(self.fastapi, host=host, port=port)
