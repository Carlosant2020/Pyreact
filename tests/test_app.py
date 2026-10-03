import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from pyreact import h, use_state, use_effect, PyReactApp


def Counter(props):
    count, set_count = use_state(0)
    return h("div", None,
        h("p", None, count),
        h("button", {"onClick": lambda: set_count(count + 1)}, "+1"),
    )


def abrir_pagina(app):
    """GET / e devolve (client, session_id, pyid_do_botao)."""
    client = TestClient(app.fastapi)
    response = client.get("/")
    assert response.status_code == 200
    session_id = re.search(r'__PYREACT_SESSION__ = "(.*?)"', response.text).group(1)
    pyid_botao = next(iter(app.sessions[session_id].handlers), None)
    return client, session_id, pyid_botao


def test_get_index_devolve_html_ssr_com_sessao():
    app = PyReactApp(Counter, title="Meu app")
    client, session_id, _ = abrir_pagina(app)
    html = client.get("/").text
    assert "<title>Meu app</title>" in html
    assert 'id="pyreact-root"' in html
    assert session_id in app.sessions


def test_client_js_e_servido_como_estatico():
    app = PyReactApp(Counter)
    response = TestClient(app.fastapi).get("/pyreact-static/client.js")
    assert response.status_code == 200
    assert "WebSocket" in response.text


def test_websocket_clique_devolve_patch_minimo():
    app = PyReactApp(Counter)
    client, session_id, pyid_botao = abrir_pagina(app)
    with client.websocket_connect(f"/ws/{session_id}") as ws:
        ws.send_json({"pyid": pyid_botao, "event": "click", "value": None})
        msg = ws.receive_json()
    assert msg["type"] == "patches"
    assert len(msg["patches"]) == 1
    assert msg["patches"][0]["op"] == "set_text"
    assert msg["patches"][0]["value"] == "1"


def test_websocket_com_sessao_inexistente_fecha_com_4404():
    app = PyReactApp(Counter)
    client = TestClient(app.fastapi)
    with client.websocket_connect("/ws/sessao-que-nao-existe") as ws:
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    assert exc.value.code == 4404


def test_handler_com_bug_nao_derruba_o_websocket():
    def Instavel(props):
        n, set_n = use_state(0)

        def handler():
            set_n(n + 1)
            raise RuntimeError("bug no handler")

        return h("button", {"onClick": handler}, str(n))

    app = PyReactApp(Instavel)
    client, session_id, pyid = abrir_pagina(app)
    with client.websocket_connect(f"/ws/{session_id}") as ws:
        for esperado in ("1", "2"):  # a conexão continua viva depois do erro
            ws.send_json({"pyid": pyid, "event": "click", "value": None})
            msg = ws.receive_json()
            assert msg["patches"][0]["value"] == esperado


# ---------- reconexão ----------

def test_sessao_sobrevive_a_desconexao_e_reconexao_recebe_html_completo():
    app = PyReactApp(Counter)
    client, session_id, pyid_botao = abrir_pagina(app)

    with client.websocket_connect(f"/ws/{session_id}") as ws:
        ws.send_json({"pyid": pyid_botao, "event": "click", "value": None})
        ws.receive_json()  # count -> 1

    assert session_id in app.sessions  # não foi apagada ao desconectar
    assert app.sessions[session_id].connected is False

    with client.websocket_connect(f"/ws/{session_id}") as ws:
        msg = ws.receive_json()  # 1ª mensagem de uma reconexão: resync
        assert msg["type"] == "full"
        assert ">1</p>" in msg["html"]  # o estado sobreviveu
        # e o handler continua funcionando depois do resync
        ws.send_json({"pyid": pyid_botao, "event": "click", "value": None})
        assert ws.receive_json()["patches"][0]["value"] == "2"


def test_primeira_conexao_nao_recebe_resync():
    app = PyReactApp(Counter)
    client, session_id, pyid_botao = abrir_pagina(app)
    with client.websocket_connect(f"/ws/{session_id}") as ws:
        ws.send_json({"pyid": pyid_botao, "event": "click", "value": None})
        assert ws.receive_json()["type"] == "patches"  # e não "full"


# ---------- expiração de sessões ----------

def test_sessao_que_nunca_conectou_e_removida_apos_o_ttl():
    app = PyReactApp(Counter, session_ttl=10)
    _, session_id, _ = abrir_pagina(app)
    assert app._purge_stale_sessions(now=time.monotonic() + 5) == 0
    assert session_id in app.sessions
    assert app._purge_stale_sessions(now=time.monotonic() + 11) == 1
    assert session_id not in app.sessions


def test_sessao_expirada_roda_cleanup_dos_efeitos():
    logs = []

    def ComEfeito(props):
        use_effect(lambda: (lambda: logs.append("cleanup")), deps=[])
        return h("div", None, "x")

    app = PyReactApp(ComEfeito, session_ttl=10)
    abrir_pagina(app)
    app._purge_stale_sessions(now=time.monotonic() + 11)
    assert logs == ["cleanup"]


def test_sessao_conectada_nao_e_removida_pelo_purge():
    app = PyReactApp(Counter, session_ttl=1)
    client, session_id, pyid_botao = abrir_pagina(app)
    with client.websocket_connect(f"/ws/{session_id}") as ws:
        assert app._purge_stale_sessions(now=time.monotonic() + 1000) == 0
        assert session_id in app.sessions


def test_run_nao_aceita_mais_o_parametro_reload_que_era_ignorado():
    import inspect
    assert "reload" not in inspect.signature(PyReactApp.run).parameters
