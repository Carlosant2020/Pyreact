import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from pyreact.hooks import use_state, use_effect, use_memo, HookContext
from pyreact.component import ComponentInstance


class FakeSession:
    """Substitui Session nos testes: só precisa saber contar quantas vezes
    pediram um re-render."""
    def __init__(self):
        self.rerender_requests = 0

    def schedule_rerender(self):
        self.rerender_requests += 1


def make_instance(fn=lambda props: None):
    return ComponentInstance(fn, FakeSession())


def test_use_state_retorna_valor_inicial():
    instance = make_instance()
    with HookContext(instance):
        value, _ = use_state(10)
    assert value == 10


def test_use_state_persiste_entre_renders():
    instance = make_instance()
    with HookContext(instance):
        _, set_value = use_state(0)
    set_value(5)

    with HookContext(instance):
        value, _ = use_state(0)  # valor inicial é ignorado na 2ª chamada
    assert value == 5


def test_use_state_aceita_funcao_de_atualizacao():
    instance = make_instance()
    with HookContext(instance):
        _, set_value = use_state(1)
    set_value(lambda prev: prev + 1)
    set_value(lambda prev: prev + 1)

    with HookContext(instance):
        value, _ = use_state(0)
    assert value == 3


def test_use_state_so_agenda_rerender_se_valor_mudar():
    instance = make_instance()
    with HookContext(instance):
        _, set_value = use_state(7)

    set_value(7)  # mesmo valor, não deveria agendar nada
    assert instance.session.rerender_requests == 0

    set_value(8)
    assert instance.session.rerender_requests == 1


def test_hooks_multiplos_mantem_ordem_e_identidade():
    instance = make_instance()
    with HookContext(instance):
        count, set_count = use_state(0)
        name, set_name = use_state("Ana")

    assert (count, name) == (0, "Ana")
    set_count(1)
    set_name("Bia")

    with HookContext(instance):
        count2, _ = use_state(0)
        name2, _ = use_state("")

    assert (count2, name2) == (1, "Bia")


def test_use_state_fora_de_hookcontext_gera_erro():
    with pytest.raises(RuntimeError):
        use_state(0)


def test_use_effect_roda_quando_deps_mudam():
    instance = make_instance()
    calls = []

    with HookContext(instance):
        use_effect(lambda: calls.append("run"), deps=[1])
    instance.run_pending_effects()
    assert calls == ["run"]

    # mesmas deps -> não roda de novo
    with HookContext(instance):
        use_effect(lambda: calls.append("run"), deps=[1])
    instance.run_pending_effects()
    assert calls == ["run"]

    # deps diferentes -> roda de novo
    with HookContext(instance):
        use_effect(lambda: calls.append("run"), deps=[2])
    instance.run_pending_effects()
    assert calls == ["run", "run"]


def test_use_effect_chama_cleanup_antes_do_proximo_efeito():
    instance = make_instance()
    order = []

    with HookContext(instance):
        use_effect(lambda: (order.append("effect1"), lambda: order.append("cleanup1"))[1], deps=[1])
    instance.run_pending_effects()

    with HookContext(instance):
        use_effect(lambda: order.append("effect2"), deps=[2])
    instance.run_pending_effects()

    assert order == ["effect1", "cleanup1", "effect2"]


def test_use_memo_recalcula_so_quando_deps_mudam():
    instance = make_instance()
    calls = []

    def factory():
        calls.append("calc")
        return 42

    with HookContext(instance):
        value = use_memo(factory, deps=[1])
    assert value == 42
    assert calls == ["calc"]

    with HookContext(instance):
        value2 = use_memo(factory, deps=[1])  # mesmas deps -> não recalcula
    assert value2 == 42
    assert calls == ["calc"]

    with HookContext(instance):
        value3 = use_memo(factory, deps=[2])  # deps mudaram -> recalcula
    assert value3 == 42
    assert calls == ["calc", "calc"]
