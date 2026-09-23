import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pyreact.vdom import h
from pyreact.diff import diff


def host_tree():
    """Uma pequena árvore host, como o reconciler produziria (com data-pyid
    já atribuído em cada elemento)."""
    return h("div", {"data-pyid": "root", "style": {"color": "seagreen"}},
        h("p", {"data-pyid": "root/0"}, "0"),
        h("button", {"data-pyid": "root/1"}, "clique"),
    )


def test_diff_arvores_identicas_nao_gera_patches():
    a = host_tree()
    b = host_tree()
    assert diff(a, b) == []


def test_diff_texto_gera_set_text_com_indice_certo():
    a = host_tree()
    b = h("div", {"data-pyid": "root", "style": {"color": "seagreen"}},
        h("p", {"data-pyid": "root/0"}, "1"),
        h("button", {"data-pyid": "root/1"}, "clique"),
    )
    patches = diff(a, b)
    assert {"op": "set_text", "parent_id": "root/0", "index": 0, "value": "1"} in patches


def test_diff_style_gera_update_props():
    a = host_tree()
    b = h("div", {"data-pyid": "root", "style": {"color": "crimson"}},
        h("p", {"data-pyid": "root/0"}, "0"),
        h("button", {"data-pyid": "root/1"}, "clique"),
    )
    patches = diff(a, b)
    assert any(p["op"] == "update_props" and p["id"] == "root"
               and p["props"].get("style") == "color:crimson" for p in patches)


def test_diff_atributo_removido_vira_none():
    a = h("input", {"data-pyid": "root", "disabled": True})
    b = h("input", {"data-pyid": "root"})
    patches = diff(a, b)
    assert {"op": "update_props", "id": "root", "props": {"disabled": None}} in patches


def test_diff_adicionar_filho_gera_insert():
    a = h("ul", {"data-pyid": "root"}, h("li", {"data-pyid": "root/0"}, "um"))
    b = h("ul", {"data-pyid": "root"},
          h("li", {"data-pyid": "root/0"}, "um"),
          h("li", {"data-pyid": "root/1"}, "dois"))
    patches = diff(a, b)
    assert len(patches) == 1
    assert patches[0]["op"] == "insert"
    assert patches[0]["parent_id"] == "root"
    assert patches[0]["index"] == 1
    assert "dois" in patches[0]["html"]


def test_diff_remover_filho_gera_remove_at():
    a = h("ul", {"data-pyid": "root"},
          h("li", {"data-pyid": "root/0"}, "um"),
          h("li", {"data-pyid": "root/1"}, "dois"))
    b = h("ul", {"data-pyid": "root"}, h("li", {"data-pyid": "root/0"}, "um"))
    patches = diff(a, b)
    assert patches == [{"op": "remove_at", "parent_id": "root", "index": 1}]


def test_diff_remover_varios_filhos_em_ordem_decrescente():
    a = h("ul", {"data-pyid": "root"},
          h("li", {"data-pyid": "root/0"}, "um"),
          h("li", {"data-pyid": "root/1"}, "dois"),
          h("li", {"data-pyid": "root/2"}, "três"))
    b = h("ul", {"data-pyid": "root"})
    patches = diff(a, b)
    # remove do índice mais alto pro mais baixo, pra não bagunçar os índices
    # restantes no meio da aplicação dos patches
    assert [p["index"] for p in patches] == [2, 1, 0]


def test_diff_troca_de_tag_gera_replace_at():
    a = h("div", {"data-pyid": "root"}, h("span", {"data-pyid": "root/0"}, "x"))
    b = h("div", {"data-pyid": "root"}, h("strong", {"data-pyid": "root/0"}, "x"))
    patches = diff(a, b)
    assert len(patches) == 1
    assert patches[0]["op"] == "replace_at"
    assert "<strong" in patches[0]["html"]
