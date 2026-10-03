"""
Diffing: compara a árvore host antiga com a nova e gera uma lista de
"patches" (operações mínimas) para o cliente aplicar no DOM real, sem
precisar re-renderizar a página inteira.

Duas estratégias, escolhidas automaticamente por lista de filhos:

- **Diff posicional** (quando algum filho é texto solto, ex.: `h("p", None,
  "Olá, ", nome)`): compara por índice. Simples e suficiente pra esse caso,
  mas trata reordenação como remover+inserir.
- **Diff por key** (quando TODOS os filhos são elementos, cada um com sua
  `data-pyid` estável): casa os filhos pela identidade de verdade e usa uma
  *longest increasing subsequence* (LIS) sobre as posições antigas — a
  mesma técnica usada por Vue/Inferno — pra descobrir o conjunto mínimo de
  itens que precisam ser *movidos*, em vez de recriar a lista inteira.
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


def _lis(seq: list) -> list:
    """Longest increasing subsequence: retorna os ÍNDICES (dentro de `seq`)
    de uma subsequência estritamente crescente mais longa, via patience
    sorting (O(n log n)). Usada pra achar quais itens já estão numa ordem
    relativa correta e por isso NÃO precisam ser movidos."""
    piles_idx: list = []   # piles_idx[k] = índice (em seq) do topo da pilha k
    parent = [-1] * len(seq)

    for i, x in enumerate(seq):
        lo, hi = 0, len(piles_idx)
        while lo < hi:
            mid = (lo + hi) // 2
            if seq[piles_idx[mid]] < x:
                lo = mid + 1
            else:
                hi = mid
        if lo > 0:
            parent[i] = piles_idx[lo - 1]
        if lo == len(piles_idx):
            piles_idx.append(i)
        else:
            piles_idx[lo] = i

    result = []
    k = piles_idx[-1] if piles_idx else -1
    while k != -1:
        result.append(k)
        k = parent[k]
    result.reverse()
    return result


def diff_node(parent_id: str, index: int, old: VNode, new: VNode, patches: list) -> None:
    """Compara dois nós que ocupam a MESMA posição (índice) dentro do
    parent — usado pelo diff posicional (fallback para listas com texto
    solto)."""
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


def _diff_children_positional(parent_id: str, old_children: list, new_children: list, patches: list) -> None:
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


def _diff_children_keyed(parent_id: str, old_children: list, new_children: list, patches: list) -> None:
    old_index_by_id = {c.props["data-pyid"]: i for i, c in enumerate(old_children)}
    old_by_id = {c.props["data-pyid"]: c for c in old_children}
    new_ids = [c.props["data-pyid"] for c in new_children]
    new_id_set = set(new_ids)

    # 1) remove os que sumiram
    for old_child in old_children:
        pyid = old_child.props["data-pyid"]
        if pyid not in new_id_set:
            patches.append({"op": "remove", "id": pyid})

    # 2) atualiza conteúdo dos pares que casaram por id (antes de mexer em posição)
    for new_child in new_children:
        pyid = new_child.props["data-pyid"]
        old_child = old_by_id.get(pyid)
        if old_child is None:
            continue  # é novo — tratado no passo 4 (insert_before)
        if old_child.type != new_child.type:
            patches.append({"op": "replace", "id": pyid, "html": render_to_html(new_child, {})})
            continue
        prop_changes = diff_props(old_child.props, new_child.props)
        if prop_changes:
            patches.append({"op": "update_props", "id": pyid, "props": prop_changes})
        diff_children(pyid, old_child.children, new_child.children, patches)

    # 3) LIS sobre os índices antigos (na ordem nova) = itens que já estão
    #    em ordem relativa correta e não precisam de patch de posição
    matched_old_idx = []
    matched_new_pos = []
    for pos, pyid in enumerate(new_ids):
        if pyid in old_index_by_id:
            matched_old_idx.append(old_index_by_id[pyid])
            matched_new_pos.append(pos)
    keep_positions = {matched_new_pos[i] for i in _lis(matched_old_idx)}

    # 4) percorre de trás pra frente: assim, quando geramos o patch de um
    #    item, o "ref_id" (próximo irmão na ordem final) já foi resolvido
    #    pelos patches anteriores desta mesma passada.
    for pos in range(len(new_children) - 1, -1, -1):
        new_child = new_children[pos]
        pyid = new_child.props["data-pyid"]
        ref_id = new_children[pos + 1].props["data-pyid"] if pos + 1 < len(new_children) else None

        if pyid not in old_index_by_id:
            patches.append({"op": "insert_before", "parent_id": parent_id, "ref_id": ref_id,
                             "html": render_to_html(new_child, {})})
        elif pos not in keep_positions:
            patches.append({"op": "move", "id": pyid, "parent_id": parent_id, "ref_id": ref_id})


def _all_keyed(children: list) -> bool:
    """True quando todo filho é um elemento (não texto solto) — condição
    pra poder confiar em data-pyid como identidade de verdade."""
    return all(not c.is_text() for c in children)


def diff_children(parent_id: str, old_children: list, new_children: list, patches: list) -> None:
    if _all_keyed(old_children) and _all_keyed(new_children):
        _diff_children_keyed(parent_id, old_children, new_children, patches)
    else:
        _diff_children_positional(parent_id, old_children, new_children, patches)


def diff(old_root: VNode, new_root: VNode) -> list:
    patches: list = []
    diff_node("__root_parent__", 0, old_root, new_root, patches)
    return patches
