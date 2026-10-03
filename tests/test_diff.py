import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pyreact.vdom import h
from pyreact.diff import diff, _lis


def host_tree_com_texto():
    """Árvore com um filho de TEXTO solto entre elementos -> força o
    fallback posicional (não dá pra confiar em pyid pra tudo)."""
    return h("div", {"data-pyid": "root", "style": {"color": "seagreen"}},
        "Contador: ",
        h("span", {"data-pyid": "root/1"}, "0"),
    )


def lista_de_itens(labels, ids=None):
    """Uma <ul><li>...</li></ul> onde cada <li> tem key (quando `ids` é
    passado) — cenário que aciona o diff por key."""
    ids = ids or list(range(len(labels)))
    return h("ul", {"data-pyid": "root"}, *[
        h("li", {"key": i, "data-pyid": f"root/k:{i}"}, label)
        for i, label in zip(ids, labels)
    ])


# ---------- diff posicional (fallback, quando há texto solto) ----------

def test_diff_arvores_identicas_nao_gera_patches():
    a = host_tree_com_texto()
    b = host_tree_com_texto()
    assert diff(a, b) == []


def test_diff_texto_gera_set_text_com_indice_certo():
    a = host_tree_com_texto()
    b = h("div", {"data-pyid": "root", "style": {"color": "seagreen"}},
        "Contador: ",
        h("span", {"data-pyid": "root/1"}, "1"),
    )
    patches = diff(a, b)
    assert {"op": "set_text", "parent_id": "root/1", "index": 0, "value": "1"} in patches


def test_diff_style_gera_update_props():
    a = host_tree_com_texto()
    b = h("div", {"data-pyid": "root", "style": {"color": "crimson"}},
        "Contador: ",
        h("span", {"data-pyid": "root/1"}, "0"),
    )
    patches = diff(a, b)
    assert any(p["op"] == "update_props" and p["id"] == "root"
               and p["props"].get("style") == "color:crimson" for p in patches)


def test_diff_atributo_removido_vira_none():
    a = h("input", {"data-pyid": "root", "disabled": True})
    b = h("input", {"data-pyid": "root"})
    patches = diff(a, b)
    assert {"op": "update_props", "id": "root", "props": {"disabled": None}} in patches


# ---------- diff por key (listas de elementos) ----------

def test_diff_lista_sem_mudanca_nao_gera_patches():
    a = lista_de_itens(["um", "dois"])
    b = lista_de_itens(["um", "dois"])
    assert diff(a, b) == []


def test_diff_adicionar_item_gera_insert_before():
    a = lista_de_itens(["um"], ids=["a"])
    b = lista_de_itens(["um", "dois"], ids=["a", "b"])
    patches = diff(a, b)
    assert len(patches) == 1
    assert patches[0] == {"op": "insert_before", "parent_id": "root",
                           "ref_id": None, "html": patches[0]["html"]}
    assert "dois" in patches[0]["html"]


def test_diff_remover_item_gera_remove_por_id():
    a = lista_de_itens(["um", "dois"], ids=["a", "b"])
    b = lista_de_itens(["um"], ids=["a"])
    patches = diff(a, b)
    assert patches == [{"op": "remove", "id": "root/k:b"}]


def test_diff_remover_varios_itens():
    a = lista_de_itens(["um", "dois", "três"], ids=["a", "b", "c"])
    b = lista_de_itens([], ids=[])
    patches = diff(a, b)
    assert {p["id"] for p in patches} == {"root/k:a", "root/k:b", "root/k:c"}
    assert all(p["op"] == "remove" for p in patches)


def test_diff_trocar_tag_de_um_item_gera_replace_por_id():
    a = h("ul", {"data-pyid": "root"}, h("li", {"key": "x", "data-pyid": "root/k:x"}, "a"))
    b = h("ul", {"data-pyid": "root"}, h("strong", {"key": "x", "data-pyid": "root/k:x"}, "a"))
    patches = diff(a, b)
    assert len(patches) == 1
    assert patches[0]["op"] == "replace"
    assert patches[0]["id"] == "root/k:x"
    assert "<strong" in patches[0]["html"]


def test_diff_reordenar_lista_gera_moves_em_vez_de_recriar():
    a = lista_de_itens(["primeiro", "segundo", "terceiro"], ids=["x", "y", "z"])
    b = lista_de_itens(["terceiro", "primeiro", "segundo"], ids=["z", "x", "y"])
    patches = diff(a, b)

    # nada foi recriado — só reposicionado
    assert all(p["op"] == "move" for p in patches)
    moved_ids = {p["id"] for p in patches}
    # z foi da posição 2 pra 0: precisa mover. x e y mantêm a ordem relativa
    # entre si (1,2 -> 1,2 na nova lista), então a LIS pode manter um dos
    # dois sem patch — o importante é que NENHUM item foi removido/recriado.
    assert moved_ids <= {"root/k:x", "root/k:y", "root/k:z"}
    assert "root/k:z" in moved_ids  # o que mais se moveu com certeza precisa de patch


def test_diff_reordenar_e_atualizar_conteudo_ao_mesmo_tempo():
    a = lista_de_itens(["primeiro", "segundo"], ids=["x", "y"])
    b = lista_de_itens(["SEGUNDO (editado)", "primeiro"], ids=["y", "x"])
    patches = diff(a, b)

    set_text_patches = [p for p in patches if p["op"] == "set_text"]
    move_patches = [p for p in patches if p["op"] == "move"]
    assert len(move_patches) >= 1
    assert any(p["value"] == "SEGUNDO (editado)" for p in set_text_patches)


def test_diff_move_referencia_o_proximo_irmao_final_ou_none_no_fim():
    a = lista_de_itens(["a", "b"], ids=["a", "b"])
    b = lista_de_itens(["b", "a"], ids=["b", "a"])
    patches = diff(a, b)
    move = next(p for p in patches if p["op"] == "move")
    assert move["ref_id"] in ("root/k:a", "root/k:b", None)


# ---------- longest increasing subsequence (usado internamente pelo diff) ----------

def test_lis_sequencia_vazia():
    assert _lis([]) == []


def test_lis_ja_crescente_mantem_tudo():
    assert _lis([0, 1, 2, 3]) == [0, 1, 2, 3]


def test_lis_encontra_subsequencia_correta():
    # subsequência crescente mais longa em [3, 1, 2, 0] é [1, 2] (valores),
    # nos índices 1 e 2
    assert _lis([3, 1, 2, 0]) == [1, 2]


def test_lis_ordem_totalmente_invertida():
    # nenhum par está em ordem crescente -> mantém só 1 elemento
    result = _lis([3, 2, 1, 0])
    assert len(result) == 1
