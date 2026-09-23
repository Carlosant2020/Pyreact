import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pyreact.vdom import h, text, VNode, TEXT_NODE


def test_h_cria_vnode_com_tag_e_props():
    node = h("div", {"className": "box"})
    assert node.type == "div"
    assert node.props["className"] == "box"
    assert node.children == []


def test_h_extrai_key_das_props():
    node = h("li", {"key": "abc", "id": "x"})
    assert node.key == "abc"
    assert "key" not in node.props  # key não deve sobrar como atributo HTML


def test_h_aceita_props_none():
    node = h("div")
    assert node.props["children"] == []


def test_h_normaliza_texto_e_numeros_como_filhos():
    node = h("p", None, "olá", 42)
    assert len(node.children) == 2
    assert node.children[0].is_text()
    assert node.children[0].props["nodeValue"] == "olá"
    assert node.children[1].props["nodeValue"] == "42"


def test_h_normaliza_none_e_bool_como_texto_vazio():
    node = h("div", None, None, False, True)
    assert len(node.children) == 3
    assert all(c.is_text() and c.props["nodeValue"] == "" for c in node.children)


def test_h_achata_listas_de_filhos():
    itens = [h("li", None, "a"), h("li", None, "b")]
    node = h("ul", None, itens)
    assert len(node.children) == 2
    assert node.children[0].type == "li"


def test_h_aceita_componente_como_type():
    def MeuComponente(props):
        return h("div")

    node = h(MeuComponente, {"foo": "bar"})
    assert node.is_component()
    assert not node.is_text()


def test_text_helper_cria_no_de_texto():
    node = text(123)
    assert node.type == TEXT_NODE
    assert node.props["nodeValue"] == "123"


def test_vnode_repr_nao_quebra():
    node = h("div", {"className": "x"}, "conteúdo")
    assert "div" in repr(node)
