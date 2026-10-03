import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pyreact.vdom import h
from pyreact.hooks import use_state, use_effect
from pyreact.session import Session


def _com_efeito(logs, nome):
    """Componente cujo efeito registra 'mount:<nome>' e devolve um cleanup
    que registra 'cleanup:<nome>'."""
    def Componente(props):
        def efeito():
            logs.append(f"mount:{nome}")
            return lambda: logs.append(f"cleanup:{nome}")
        use_effect(efeito, deps=[])
        return h("span", None, nome)
    return Componente


# ---------- cleanup de efeitos ao desmontar ----------

def test_cleanup_roda_quando_componente_sai_da_arvore():
    logs = []
    Filho = _com_efeito(logs, "filho")

    def Raiz(props):
        mostrar, set_mostrar = use_state(True)
        return h("div", {"onClick": lambda: set_mostrar(False)},
                 h(Filho, None) if mostrar else h("em", None, "vazio"))

    session = Session(Raiz)
    session.render_initial()
    assert logs == ["mount:filho"]

    session.dispatch_event("root", "click", None)
    session.rerender_if_needed()
    assert logs == ["mount:filho", "cleanup:filho"]


def test_cleanup_nao_roda_enquanto_componente_continua_na_tela():
    logs = []
    Filho = _com_efeito(logs, "filho")

    def Raiz(props):
        n, set_n = use_state(0)
        return h("div", {"onClick": lambda: set_n(n + 1)}, h(Filho, None), str(n))

    session = Session(Raiz)
    session.render_initial()
    for _ in range(3):
        session.dispatch_event("root", "click", None)
        session.rerender_if_needed()
    assert logs == ["mount:filho"]  # deps=[] -> nem remontou, nem limpou


def test_cleanup_roda_quando_o_tipo_do_componente_muda_no_slot():
    logs = []
    A = _com_efeito(logs, "A")
    B = _com_efeito(logs, "B")

    def Raiz(props):
        usar_a, set_usar_a = use_state(True)
        return h("div", {"onClick": lambda: set_usar_a(False)}, h(A if usar_a else B, None))

    session = Session(Raiz)
    session.render_initial()
    session.dispatch_event("root", "click", None)
    session.rerender_if_needed()
    assert logs == ["mount:A", "cleanup:A", "mount:B"]


def test_session_close_roda_cleanup_de_todos_os_efeitos():
    logs = []
    A = _com_efeito(logs, "A")
    B = _com_efeito(logs, "B")

    def Raiz(props):
        return h("div", None, h(A, None), h(B, None))

    session = Session(Raiz)
    session.render_initial()
    session.close()
    assert sorted(logs) == ["cleanup:A", "cleanup:B", "mount:A", "mount:B"]
    assert session.instances == {}


def test_unmount_de_efeito_sem_cleanup_nao_quebra():
    def Filho(props):
        use_effect(lambda: None, deps=[])
        return h("span", None, "x")

    def Raiz(props):
        return h("div", None, h(Filho, None))

    session = Session(Raiz)
    session.render_initial()
    session.close()  # não deve levantar


def test_cleanup_que_levanta_excecao_nao_impede_os_demais():
    logs = []

    def Ruim(props):
        def efeito():
            def cleanup():
                raise RuntimeError("cleanup com bug")
            return cleanup
        use_effect(efeito, deps=[])
        return h("span", None, "ruim")

    Bom = _com_efeito(logs, "bom")

    def Raiz(props):
        return h("div", None, h(Ruim, None), h(Bom, None))

    session = Session(Raiz)
    session.render_initial()
    session.close()
    assert "cleanup:bom" in logs


# ---------- handlers de evento ----------

def _sessao_com_handler(handler):
    def Raiz(props):
        return h("button", {"onClick": handler}, "x")
    session = Session(Raiz)
    session.render_initial()
    return session


def test_handler_sem_argumentos_e_chamado_sem_argumentos():
    calls = []
    session = _sessao_com_handler(lambda: calls.append("ok"))
    session.dispatch_event("root", "click", "valor-ignorado")
    assert calls == ["ok"]


def test_handler_com_argumento_recebe_o_valor():
    calls = []
    session = _sessao_com_handler(lambda v: calls.append(v))
    session.dispatch_event("root", "click", "abc")
    assert calls == ["abc"]


def test_handler_com_varargs_recebe_o_valor():
    calls = []
    session = _sessao_com_handler(lambda *args: calls.append(args))
    session.dispatch_event("root", "click", "abc")
    assert calls == [("abc",)]


def test_typeerror_dentro_do_handler_nao_executa_o_handler_duas_vezes():
    calls = []

    def handler(v):
        calls.append(1)
        raise TypeError("bug interno do handler")

    session = _sessao_com_handler(handler)
    session.dispatch_event("root", "click", None)  # não deve propagar
    assert calls == [1]  # antes do fix, rodava 2x (a 2ª sem argumento)


def test_excecao_no_handler_nao_derruba_a_sessao_e_ainda_re_renderiza():
    def Raiz(props):
        n, set_n = use_state(0)

        def handler(v):
            set_n(n + 1)
            raise ValueError("falhou depois de mudar o estado")

        return h("button", {"onClick": handler}, str(n))

    session = Session(Raiz)
    session.render_initial()
    session.dispatch_event("root", "click", None)
    patches = session.rerender_if_needed()
    assert any(p["op"] == "set_text" and p["value"] == "1" for p in patches)


# ---------- expiração de sessões ----------

def _sessao_simples():
    return Session(lambda props: h("div", None, "x"))


def test_sessao_que_nunca_conectou_expira_apos_o_ttl():
    s = _sessao_simples()
    assert not s.is_expired(ttl=60, now=s.created_at + 59)
    assert s.is_expired(ttl=60, now=s.created_at + 61)


def test_sessao_conectada_nunca_expira():
    s = _sessao_simples()
    s.mark_connected()
    assert not s.is_expired(ttl=1, now=s.created_at + 10_000)


def test_sessao_desconectada_expira_contando_desde_a_desconexao():
    s = _sessao_simples()
    token = s.mark_connected()
    s.mark_disconnected(token)
    assert not s.is_expired(ttl=60, now=s.disconnected_at + 59)
    assert s.is_expired(ttl=60, now=s.disconnected_at + 61)


def test_socket_antigo_fechando_nao_desconecta_o_socket_novo():
    s = _sessao_simples()
    token_antigo = s.mark_connected()
    s.mark_connected()  # reconectou: token novo
    s.mark_disconnected(token_antigo)  # o socket velho só agora percebeu que caiu
    assert s.connected is True


# ---------- identidade de instâncias no reconciler ----------

def test_componente_que_retorna_componente_mantem_estado_de_cada_nivel():
    """Externo -> Interno -> <button> compartilham o mesmo caminho na árvore;
    cada um precisa manter o próprio estado (antes, um sobrescrevia o outro)."""
    def Interno(props):
        m, set_m = use_state(100)

        def clique():
            props["bump"]()
            set_m(m + 1)

        return h("button", {"onClick": clique}, f"{props['n']}-{m}")

    def Externo(props):
        n, set_n = use_state(0)
        return h(Interno, {"n": n, "bump": lambda: set_n(n + 1)})

    def Raiz(props):
        return h("div", None, h(Externo, None))

    session = Session(Raiz)
    session.render_initial()
    for _ in range(2):
        session.dispatch_event("root/i:0", "click", None)
        session.rerender_if_needed()

    assert session.tree.children[0].children[0].props["nodeValue"] == "2-102"
    assert len(session.instances) == 3  # Raiz, Externo e Interno


def test_componente_removido_e_recolocado_comeca_com_estado_novo():
    """Antes, um <em> no lugar do componente 'marcava o slot como visitado',
    a instância antiga nunca era descartada e o estado 'ressuscitava'."""
    def Filho(props):
        n, set_n = use_state(0)
        return h("button", {"onClick": lambda: set_n(n + 1)}, str(n))

    def Raiz(props):
        mostrar, set_mostrar = use_state(True)
        return h("div", {"onClick": lambda: set_mostrar(not mostrar)},
                 h(Filho, None) if mostrar else h("em", None, "vazio"))

    session = Session(Raiz)
    session.render_initial()

    session.dispatch_event("root/i:0", "click", None)  # Filho vai pra 1
    session.rerender_if_needed()
    assert session.tree.children[0].children[0].props["nodeValue"] == "1"

    session.dispatch_event("root", "click", None)  # esconde o Filho
    session.rerender_if_needed()
    session.dispatch_event("root", "click", None)  # mostra de novo
    session.rerender_if_needed()

    assert session.tree.children[0].children[0].props["nodeValue"] == "0"
