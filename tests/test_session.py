import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pyreact.vdom import h
from pyreact.hooks import use_state, use_effect
from pyreact.session import Session


def Counter(props):
    count, set_count = use_state(0)

    def on_increment(_value):
        set_count(count + 1)

    return h("div", {"data-testid": "wrapper"},
        h("p", None, count),
        h("button", {"onClick": on_increment}, "+1"),
    )


def test_render_initial_produz_html_com_valor_inicial():
    session = Session(Counter)
    html = session.render_initial()
    assert ">0</p>" in html
    assert 'data-events="click"' in html


def test_render_initial_registra_handlers():
    session = Session(Counter)
    session.render_initial()
    assert len(session.handlers) == 1
    pyid = next(iter(session.handlers))
    assert "click" in session.handlers[pyid]


def test_dispatch_event_atualiza_estado_e_gera_patch_minimo():
    session = Session(Counter)
    session.render_initial()

    pyid_botao = next(iter(session.handlers))
    session.dispatch_event(pyid_botao, "click", None)
    patches = session.rerender_if_needed()

    assert len(patches) == 1
    assert patches[0]["op"] == "set_text"
    assert patches[0]["value"] == "1"


def test_dispatch_event_sem_handler_correspondente_nao_quebra():
    session = Session(Counter)
    session.render_initial()
    session.dispatch_event("pyid-que-nao-existe", "click", None)
    patches = session.rerender_if_needed()
    assert patches == []  # não deve levantar exceção, nem gerar patch


def test_estado_correto_apos_varios_cliques_na_mesma_sessao():
    session = Session(Counter)
    session.render_initial()
    pyid_botao = next(iter(session.handlers))

    for _ in range(5):
        session.dispatch_event(pyid_botao, "click", None)
        session.rerender_if_needed()

    valor_final = session.tree.children[0].children[0].props["nodeValue"]
    assert valor_final == "5"


def test_use_effect_roda_apos_render_com_deps_novas():
    logs = []

    def ComEfeito(props):
        count, set_count = use_state(0)
        use_effect(lambda: logs.append(count), deps=[count])
        return h("button", {"onClick": lambda v: set_count(count + 1)}, str(count))

    session = Session(ComEfeito)
    session.render_initial()
    assert logs == [0]

    pyid_botao = next(iter(session.handlers))
    session.dispatch_event(pyid_botao, "click", None)
    session.rerender_if_needed()
    assert logs == [0, 1]
