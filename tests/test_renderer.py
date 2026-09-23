import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pyreact.vdom import h
from pyreact.renderer import render_to_html, collect_handlers


def test_render_elemento_simples():
    html = render_to_html(h("div", None, "olá"), {})
    assert html == "<div>olá</div>"


def test_render_escapa_texto():
    html = render_to_html(h("p", None, "<script>"), {})
    assert "&lt;script&gt;" in html
    assert "<script>" not in html


def test_render_className_vira_class():
    html = render_to_html(h("div", {"className": "box ativo"}), {})
    assert 'class="box ativo"' in html
    assert "className" not in html


def test_render_style_dict_vira_css_kebab_case():
    html = render_to_html(h("div", {"style": {"fontSize": "12px", "color": "red"}}), {})
    assert 'style="font-size:12px;color:red"' in html


def test_render_atributo_booleano_true():
    html = render_to_html(h("input", {"disabled": True}), {})
    assert "disabled" in html
    assert "disabled=" not in html  # atributo booleano não deve ganhar ="true"


def test_render_atributo_false_ou_none_e_omitido():
    html = render_to_html(h("input", {"disabled": False, "value": None}), {})
    assert "disabled" not in html
    assert "value" not in html


def test_render_tag_void_nao_tem_fechamento():
    html = render_to_html(h("input", {"value": "x"}), {})
    assert html == '<input value="x">'
    assert "</input>" not in html


def test_render_registra_handler_e_marca_data_events():
    handlers = {}
    node = h("button", {"onClick": lambda v: None, "data-pyid": "root/0"}, "clique")
    html = render_to_html(node, handlers)
    assert 'data-events="click"' in html
    assert handlers["root/0"]["click"] is not None


def test_render_nao_vaza_onclick_como_atributo_html():
    handlers = {}
    html = render_to_html(h("button", {"onClick": lambda v: None}, "x"), handlers)
    assert "onClick" not in html
    assert "onclick" not in html.lower().replace("data-events", "")


def test_collect_handlers_pega_handlers_da_arvore_inteira():
    tree = h("div", {"data-pyid": "root"}, [
        h("button", {"onClick": lambda v: "a", "data-pyid": "root/0"}, "A"),
        h("input", {"onInput": lambda v: "b", "data-pyid": "root/1"}),
    ])
    handlers = {}
    collect_handlers(tree, handlers)
    assert set(handlers.keys()) == {"root/0", "root/1"}
    assert "click" in handlers["root/0"]
    assert "input" in handlers["root/1"]


def test_render_arvore_aninhada():
    tree = h("ul", None, h("li", None, "um"), h("li", None, "dois"))
    html = render_to_html(tree, {})
    assert html == "<ul><li>um</li><li>dois</li></ul>"
