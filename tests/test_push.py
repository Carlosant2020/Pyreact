"""Server push: efeitos async, threads, use_interval e handlers async."""
import asyncio
import functools
import gc
import logging
import sys
import threading
import time
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from pyreact import h, use_state, use_effect, use_interval
from pyreact.session import Session


def async_test(fn):
    """Roda um teste `async def` sem depender de plugin (pytest-asyncio)."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        return asyncio.run(fn(*args, **kwargs))
    return wrapper


def nova_sessao(root_fn):
    s = Session(root_fn)
    s.attach_loop(asyncio.get_running_loop())
    s.render_initial()
    return s


def texto(s):
    """Texto do primeiro <p> da árvore atual (os componentes de teste
    mostram o que interessa num <p>)."""
    def achar(no):
        if no.is_text():
            return None
        if no.type == "p":
            return no.children[0].props["nodeValue"] if no.children else ""
        for filho in no.children:
            r = achar(filho)
            if r is not None:
                return r
        return None
    return achar(s.tree)


async def esperar(s, predicado, timeout=2.0):
    """Faz o papel do empurrador de patches: re-renderiza a cada aviso de
    mudança até o texto do <p> satisfazer `predicado`."""
    fim = time.monotonic() + timeout
    while not predicado(texto(s)):
        restante = fim - time.monotonic()
        assert restante > 0, f"timeout; texto atual: {texto(s)!r}"
        try:
            await asyncio.wait_for(s.wait_for_update(), restante)
        except asyncio.TimeoutError:
            pass
        s.rerender_if_needed()


# ---------- efeitos async ----------

@async_test
async def test_efeito_async_atualiza_a_ui_sem_evento_do_cliente():
    def Relogio(props):
        n, set_n = use_state(0)

        async def tick():
            while True:
                await asyncio.sleep(0.01)
                set_n(lambda c: c + 1)

        use_effect(tick, deps=[])
        return h("p", None, str(n))

    s = nova_sessao(Relogio)
    await esperar(s, lambda t: int(t) >= 3)
    s.close()


@async_test
async def test_efeito_async_e_cancelado_quando_o_componente_sai_da_tela():
    cancelado = []

    def Filho(props):
        async def trabalho():
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelado.append(True)
                raise

        use_effect(trabalho, deps=[])
        return h("span", None, "filho")

    def Raiz(props):
        mostrar, set_mostrar = use_state(True)
        return h("div", {"onClick": lambda: set_mostrar(False)},
                 h(Filho, None) if mostrar else h("em", None, "vazio"))

    s = nova_sessao(Raiz)
    await asyncio.sleep(0)  # deixa a tarefa do efeito começar
    s.dispatch_event("root", "click", None)
    s.rerender_if_needed()
    await asyncio.sleep(0.01)
    assert cancelado == [True]


@async_test
async def test_efeito_async_reinicia_quando_as_deps_mudam():
    eventos = []

    def Comp(props):
        x, set_x = use_state(1)

        async def trabalho():
            eventos.append(f"inicio:{x}")
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                eventos.append(f"cancelado:{x}")
                raise

        use_effect(trabalho, deps=[x])
        return h("button", {"onClick": lambda: set_x(x + 1)}, str(x))

    s = nova_sessao(Comp)
    await asyncio.sleep(0)
    s.dispatch_event("root", "click", None)
    s.rerender_if_needed()
    await asyncio.sleep(0.01)
    assert eventos == ["inicio:1", "cancelado:1", "inicio:2"]
    s.close()


@async_test
async def test_lambda_que_devolve_corrotina_tambem_vira_efeito_async():
    def Comp(props):
        n, set_n = use_state(0)

        async def trabalho():
            await asyncio.sleep(0.01)
            set_n(7)

        use_effect(lambda: trabalho(), deps=[])
        return h("p", None, str(n))

    s = nova_sessao(Comp)
    await esperar(s, lambda t: t == "7")


@async_test
async def test_excecao_em_efeito_async_e_logada_e_a_sessao_continua(caplog):
    def Comp(props):
        async def quebra():
            raise RuntimeError("boom")

        use_effect(quebra, deps=[])
        return h("p", None, "ok")

    with caplog.at_level(logging.ERROR):
        s = nova_sessao(Comp)
        await asyncio.sleep(0.02)
    assert any("Tarefa em segundo plano falhou" in r.getMessage() for r in caplog.records)
    assert texto(s) == "ok"


@async_test
async def test_excecao_em_efeito_sincrono_nao_derruba_o_render(caplog):
    def Comp(props):
        def efeito():
            raise RuntimeError("efeito com bug")

        use_effect(efeito, deps=[])
        return h("p", None, "renderizou")

    with caplog.at_level(logging.ERROR):
        s = nova_sessao(Comp)
    assert texto(s) == "renderizou"
    assert any("Erro ao executar um efeito" in r.getMessage() for r in caplog.records)


def test_efeito_async_sem_event_loop_nao_quebra_nem_deixa_corrotina_pendente(caplog):
    def Comp(props):
        async def trabalho():
            pass

        use_effect(trabalho, deps=[])
        return h("p", None, "x")

    s = Session(Comp)
    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always")
        with caplog.at_level(logging.ERROR):
            s.render_initial()
        gc.collect()
    assert not [a for a in avisos if "never awaited" in str(a.message)]
    assert any("event loop" in r.getMessage() for r in caplog.records)


# ---------- threads ----------

@async_test
async def test_thread_chamando_set_state_acorda_a_sessao():
    def Comp(props):
        n, set_n = use_state(0)

        def efeito():
            threading.Thread(target=lambda: (time.sleep(0.02), set_n(42))).start()

        use_effect(efeito, deps=[])
        return h("p", None, str(n))

    s = nova_sessao(Comp)
    await esperar(s, lambda t: t == "42")


# ---------- use_interval ----------

@async_test
async def test_use_interval_usa_sempre_o_callback_mais_recente():
    def Contador(props):
        n, set_n = use_state(0)
        use_interval(lambda: set_n(n + 1), 0.01)  # lê `n` direto, sem lambda c: c+1
        return h("p", None, str(n))

    s = nova_sessao(Contador)
    # com closure velha travaria em 1 (set_n(0 + 1) pra sempre)
    await esperar(s, lambda t: int(t) >= 5)
    s.close()


@async_test
async def test_use_interval_com_none_fica_pausado():
    def Comp(props):
        n, set_n = use_state(0)
        use_interval(lambda: set_n(n + 1), None)
        return h("p", None, str(n))

    s = nova_sessao(Comp)
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(s.wait_for_update(), 0.1)
    assert texto(s) == "0"


@async_test
async def test_use_interval_aceita_callback_async():
    def Comp(props):
        n, set_n = use_state(0)

        async def tick():
            await asyncio.sleep(0)
            set_n(n + 1)

        use_interval(tick, 0.01)
        return h("p", None, str(n))

    s = nova_sessao(Comp)
    await esperar(s, lambda t: int(t) >= 3)
    s.close()


@async_test
async def test_use_interval_para_quando_a_sessao_fecha():
    chamadas = []

    def Comp(props):
        use_interval(lambda: chamadas.append(1), 0.01)
        return h("p", None, "x")

    s = nova_sessao(Comp)
    await asyncio.sleep(0.06)
    s.close()
    await asyncio.sleep(0.01)
    total = len(chamadas)
    assert total >= 2
    await asyncio.sleep(0.06)
    assert len(chamadas) == total


@async_test
async def test_excecao_no_callback_do_interval_nao_para_o_intervalo(caplog):
    chamadas = []

    def Comp(props):
        def cb():
            chamadas.append(1)
            raise RuntimeError("callback com bug")

        use_interval(cb, 0.01)
        return h("p", None, "x")

    with caplog.at_level(logging.ERROR):
        s = nova_sessao(Comp)
        await asyncio.sleep(0.06)
        s.close()
    assert len(chamadas) >= 2
    assert any("Erro no callback de use_interval" in r.getMessage() for r in caplog.records)


def test_use_interval_rejeita_intervalo_invalido():
    def Comp(props):
        use_interval(lambda: None, 0)
        return h("p", None, "x")

    with pytest.raises(ValueError):
        Session(Comp).render_initial()


# ---------- handlers async ----------

def Tela(props):
    status, set_status = use_state("parado")
    cliques, set_cliques = use_state(0)

    async def carregar():
        set_status("carregando")
        await asyncio.sleep(0.05)
        set_status("pronto")

    return h("div", None,
        h("button", {"onClick": carregar}, "carregar"),
        h("button", {"onClick": lambda: set_cliques(cliques + 1)}, "contar"),
        h("p", None, f"{status}|{cliques}"),
    )


@async_test
async def test_handler_async_mostra_estado_intermediario_e_final():
    s = nova_sessao(Tela)
    s.dispatch_event("root/i:0", "click", None)
    await esperar(s, lambda t: t.startswith("carregando"))
    await esperar(s, lambda t: t.startswith("pronto"))


@async_test
async def test_handler_async_lento_nao_bloqueia_outros_eventos():
    s = nova_sessao(Tela)
    s.dispatch_event("root/i:0", "click", None)  # começa o carregamento (lento)
    s.dispatch_event("root/i:1", "click", None)  # clique síncrono logo em seguida
    # o clique foi processado enquanto o carregamento AINDA estava em andamento
    await esperar(s, lambda t: t == "carregando|1")
    await esperar(s, lambda t: t == "pronto|1")


@async_test
async def test_excecao_em_handler_async_e_logada_e_a_sessao_continua(caplog):
    def Comp(props):
        n, set_n = use_state(0)

        async def falha():
            set_n(n + 1)
            raise RuntimeError("handler async com bug")

        return h("div", None,
                 h("button", {"onClick": falha}, "x"),
                 h("p", None, str(n)))

    s = nova_sessao(Comp)
    with caplog.at_level(logging.ERROR):
        s.dispatch_event("root/i:0", "click", None)
        await esperar(s, lambda t: t == "1")
    assert any("Erro no handler async" in r.getMessage() for r in caplog.records)


@async_test
async def test_close_cancela_handlers_async_em_andamento():
    cancelado = []

    def Comp(props):
        async def lento():
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelado.append(True)
                raise

        return h("button", {"onClick": lento}, "x")

    s = nova_sessao(Comp)
    s.dispatch_event("root", "click", None)
    await asyncio.sleep(0)
    s.close()
    await asyncio.sleep(0.01)
    assert cancelado == [True]


def test_handler_async_sem_event_loop_nao_quebra_nem_deixa_corrotina_pendente(caplog):
    def Comp(props):
        async def h_async():
            pass

        return h("button", {"onClick": h_async}, "x")

    s = Session(Comp)
    s.render_initial()
    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always")
        with caplog.at_level(logging.ERROR):
            s.dispatch_event("root", "click", None)
        gc.collect()
    assert not [a for a in avisos if "never awaited" in str(a.message)]
    assert any("event loop" in r.getMessage() for r in caplog.records)


# ---------- sinal de "estado mudou" ----------

def test_wait_for_update_sem_attach_loop_levanta_erro_claro():
    s = Session(lambda props: h("p", None, "x"))
    with pytest.raises(RuntimeError, match="attach_loop"):
        asyncio.run(s.wait_for_update())


@async_test
async def test_mudanca_antes_de_conectar_fica_pendente_e_wake_entrega():
    def Comp(props):
        n, set_n = use_state(0)
        return h("p", None, str(n))

    s = Session(Comp)          # ainda sem loop (fase de SSR)
    s.render_initial()
    s.instances["root#0"].hooks[0]["value"] = 5
    s.schedule_rerender()      # não pode falhar sem loop
    assert s._needs_rerender

    s.attach_loop(asyncio.get_running_loop())  # a aba conectou
    s.wake()
    await asyncio.wait_for(s.wait_for_update(), 1)
    assert s.rerender_if_needed()[0]["value"] == "5"
