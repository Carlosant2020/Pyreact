"""
Reconciliação: percorre a árvore de VNodes, chama funções de componente
(passando hooks), e produz uma árvore final contendo só elementos "host"
(tags HTML e texto) — nada de funções de componente sobrando.

Cada "slot" da árvore (posição + key) recebe um caminho de identidade
estável. Um componente é transparente: ele reaproveita o MESMO caminho do
elemento host que ele efetivamente renderiza, já que um componente não
insere um nível novo na árvore real do DOM.
"""
from __future__ import annotations
from .vdom import VNode
from .hooks import HookContext
from .component import ComponentInstance


def _child_slot(vnode: VNode, index: int) -> str:
    if vnode.key is not None:
        return f"k:{vnode.key}"
    if vnode.is_component():
        name = getattr(vnode.type, "__qualname__", "Component")
        return f"c:{name}"
    return f"i:{index}"


def resolve_tree(root_vnode: VNode, session: "Session") -> VNode:
    """Resolve a árvore inteira a partir da raiz, reaproveitando instâncias
    de componentes já existentes (para preservar estado dos hooks)."""
    visited: set[str] = set()
    resolved = _resolve(root_vnode, own_path=["root"], registry=session.instances,
                         session=session, visited=visited)
    stale = [k for k in session.instances if k not in visited]
    for k in stale:
        del session.instances[k]
    return resolved


def _resolve(vnode: VNode, own_path: list[str], registry: dict, session, visited: set) -> VNode:
    if vnode.is_text():
        return vnode

    if vnode.is_component():
        path_key = "/".join(own_path)
        visited.add(path_key)

        instance = registry.get(path_key)
        if instance is None:
            instance = ComponentInstance(vnode.type, session)
            registry[path_key] = instance

        with HookContext(instance):
            rendered = instance.fn(vnode.props)

        session.pending_effect_instances.append(instance)
        # componente é transparente: o resultado herda o mesmo caminho
        return _resolve(rendered, own_path, registry, session, visited)

    # elemento host: resolve os filhos recursivamente
    pyid = "/".join(own_path)
    visited.add(pyid)

    new_props = dict(vnode.props)
    children = vnode.props.get("children", [])
    resolved_children = []
    for i, child in enumerate(children):
        segment = _child_slot(child, i)
        child_path = own_path + [f"{i}:{segment}"]
        resolved_children.append(_resolve(child, child_path, registry, session, visited))

    new_props["children"] = resolved_children
    new_props["data-pyid"] = pyid
    return VNode(vnode.type, new_props, key=vnode.key)
