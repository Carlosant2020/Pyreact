"""
Exemplo do PyReact: um relógio que atualiza sozinho na tela, e um contador
que incrementa em segundo plano — nenhum dos dois espera o usuário clicar
em nada. Isso é "server push": o servidor decide quando mandar uma
atualização, não só quando o navegador avisa de um evento.

Também mostra um handler `async def` (o botão "Carregar dados"): a UI
continua respondendo a outros cliques enquanto ele "carrega".

Rode com:
    python examples/live_clock.py
E abra http://127.0.0.1:8000 em duas abas pra ver as duas atualizando juntas.
"""
import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pyreact import h, use_state, use_interval, PyReactApp


def Relogio(props):
    agora, set_agora = use_state(lambda: datetime.now().strftime("%H:%M:%S"))
    use_interval(lambda: set_agora(datetime.now().strftime("%H:%M:%S")), 1.0)
    return h("p", {"style": {"fontSize": "2rem", "fontFamily": "monospace"}}, agora)


def ContadorAutomatico(props):
    n, set_n = use_state(0)
    pausado, set_pausado = use_state(False)
    use_interval(lambda: set_n(n + 1), None if pausado else 0.3)

    return h("div", None,
        h("p", None, f"Tick: {n}"),
        h("button", {"onClick": lambda: set_pausado(not pausado)},
          "▶ Retomar" if pausado else "⏸ Pausar"),
    )


def CarregamentoAssincrono(props):
    status, set_status = use_state("parado")
    cliques_durante, set_cliques_durante = use_state(0)

    async def carregar(_value):
        set_status("carregando...")
        await asyncio.sleep(2)  # simula uma chamada de rede/IO lenta
        set_status("pronto!")

    return h("div", None,
        h("button", {"onClick": carregar}, "Carregar dados"),
        h("button", {"onClick": lambda: set_cliques_durante(cliques_durante + 1)},
          f"Clique em mim enquanto isso ({cliques_durante})"),
        h("p", None, f"status: {status}"),
    )


def App(props):
    return h("div", {"style": {"fontFamily": "sans-serif", "maxWidth": "420px",
                                "margin": "2rem auto", "padding": "0 1rem"}},
        h("h1", None, "Server push"),
        h("h3", None, "Relógio (atualiza sozinho, a cada 1s)"),
        h(Relogio, None),
        h("h3", None, "Contador automático (pode pausar)"),
        h(ContadorAutomatico, None),
        h("h3", None, "Handler async (não trava a UI)"),
        h(CarregamentoAssincrono, None),
    )


app = PyReactApp(App, title="Server push — PyReact")

if __name__ == "__main__":
    print("Rodando em http://127.0.0.1:8000")
    app.run()
