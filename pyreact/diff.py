"""
Diffing: compara a árvore host antiga com a nova e gera uma lista de
"patches" (operações mínimas) para o cliente aplicar no DOM real, sem
precisar re-renderizar a página inteira.

Simplificação assumida (documentada no README): filhos são comparados por
posição (índice), não por reordenação via key. Isso cobre bem listas que
crescem/encolhem no fim ou têm itens atualizados no lugar — o caso mais
comum em UIs de formulário/dashboard.
"""
from __future__ import annotations
from .vdom import VNode
from .renderer import render_to_html, _EVENT_PROPS, _style_to_css

_MISSING = object()


def diff_props(old_props: dict, new_props: dict) -> dict:
    changes: dict = {}
    keys = set(old_props) | set(new_props)
    skip = {"children", "data-pyid", "nodeValue"}
    for k in keys:
        if k in skip or k in _EVENT_PROPS:
            continue
        ov = old_props.get(k, _MISSING)
        nv = new_props.get(k, _MISSING)
        if ov == nv:
            continue
        out_key = "class" if k == "className" else k
        if nv is _MISSING or nv is False or nv is None:
            changes[out_key] = None  # sinaliza remoção do atributo no cliente
        elif out_key == "style" and isinstance(nv, dict):
            changes[out_key] = _style_to_css(nv)
        else:
            changes[out_key] = nv
    return changes


def diff_node(parent_id: str, index: int, old: VNode, new: VNode, patches: list) -> None:
    if old.is_text() and new.is_text():
        if old.props.get("nodeValue") != new.props.get("nodeValue"):
            patches.append({"op": "set_text", "parent_id": parent_id,
                             "index": index, "value": new.props.get("nodeValue")})
        return

    if old.is_text() != new.is_text() or (not old.is_text() and old.type != new.type):
        patches.append({"op": "replace_at", "parent_id": parent_id, "index": index,
                         "html": render_to_html(new, {})})
        return

    pyid = new.props.get("data-pyid")
    prop_changes = diff_props(old.props, new.props)
    if prop_changes:
        patches.append({"op": "update_props", "id": pyid, "props": prop_changes})

    diff_children(pyid, old.children, new.children, patches)


def diff_children(parent_id: str, old_children: list, new_children: list, patches: list) -> None:
    common = min(len(old_children), len(new_children))
    for i in range(common):
        diff_node(parent_id, i, old_children[i], new_children[i], patches)

    if len(new_children) > len(old_children):
        for i in range(len(old_children), len(new_children)):
            patches.append({"op": "insert", "parent_id": parent_id, "index": i,
                             "html": render_to_html(new_children[i], {})})
    elif len(old_children) > len(new_children):
        for i in range(len(old_children) - 1, len(new_children) - 1, -1):
            patches.append({"op": "remove_at", "parent_id": parent_id, "index": i})


def diff(old_root: VNode, new_root: VNode) -> list:
    patches: list = []
    diff_node("__root_parent__", 0, old_root, new_root, patches)
    # a raiz em si é sempre a mesma tag (garantido pelo app), então na
    # prática só update_props/diff_children da raiz é usado.
    return patches
