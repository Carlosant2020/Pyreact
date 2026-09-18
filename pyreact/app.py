"""
App: junta tudo — serve o HTML inicial (SSR) e mantém um WebSocket por aba
para receber eventos do navegador e mandar de volta só os patches
necessários (sem recarregar a página).
"""
from __future__ import annotations
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .session import Session

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
                 extra_head: str = ""):
        self.root_component = root_component
        self.title = title
        self.extra_head = extra_head
        self.sessions: dict[str, Session] = {}
        self.fastapi = FastAPI()
        self.fastapi.mount("/pyreact-static", StaticFiles(directory=str(_STATIC_DIR)),
                            name="pyreact-static")
        self._register_routes()

    def _register_routes(self) -> None:
        @self.fastapi.get("/", response_class=HTMLResponse)
        async def index():
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
            try:
                while True:
                    data = await websocket.receive_json()
                    session.dispatch_event(data["pyid"], data["event"], data.get("value"))
                    patches = session.rerender_if_needed()
                    if patches:
                        await websocket.send_json({"type": "patches", "patches": patches})
            except WebSocketDisconnect:
                self.sessions.pop(session_id, None)

    def run(self, host: str = "127.0.0.1", port: int = 8000, reload: bool = False) -> None:
        import uvicorn
        uvicorn.run(self.fastapi, host=host, port=port)
