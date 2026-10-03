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
    """Segmento de identidade de um filho. Com `key`, a identidade não
    depende mais da posição — é isso que permite mover o item de lugar
    sem perder estado nem forçar recriação no DOM."""
    if vnode.key is not None:
        return f"k:{vnode.key}"
    return f"i:{index}"


def resolve_tree(root_vnode: VNode, session: "Session") -> VNode:
    """Resolve a árvore inteira a partir da raiz, reaproveitando instâncias
    de componentes já existentes (para preservar estado dos hooks)."""
    visited: set[str] = set()
    resolved = _resolve(root_vnode, own_path=["root"], registry=session.instances,
                         session=session, visited=visited)
    stale = [k for k in session.instances if k not in visited]
    for k in stale:
        session.instances.pop(k).unmount()
    return resolved


def _resolve(vnode: VNode, own_path: list[str], registry: dict, session, visited: set,
             depth: int = 0) -> VNode:
    if vnode.is_text():
        return vnode

    if vnode.is_component():
        # A chave inclui a profundidade de aninhamento: um componente que
        # retorna outro componente (Externo -> Interno -> <div>) compartilha
        # o MESMO caminho na árvore, mas cada um precisa da sua instância.
        path_key = "/".join(own_path) + f"#{depth}"
        visited.add(path_key)

        instance = registry.get(path_key)
        if instance is None or instance.fn is not vnode.type:
            # instância nova, ou o tipo mudou nesse slot (ex: um if/else
            # trocando de componente) — nesse caso também é uma instância
            # nova: os hooks não devem ser reaproveitados de um componente
            # diferente.
            if instance is not None:
                instance.unmount()
            instance = ComponentInstance(vnode.type, session)
            registry[path_key] = instance

        with HookContext(instance):
            rendered = vnode.type(vnode.props)

        session.pending_effect_instances.append(instance)
        # componente é transparente: o resultado herda o mesmo caminho
        return _resolve(rendered, own_path, registry, session, visited, depth + 1)

    # elemento host: resolve os filhos recursivamente
    # (só instâncias de componente entram em `visited`: misturar aqui o pyid
    # do elemento fazia um componente trocado por um <em> no mesmo lugar
    # nunca ser considerado removido)
    pyid = "/".join(own_path)

    new_props = dict(vnode.props)
    children = vnode.props.get("children", [])
    resolved_children = []
    for i, child in enumerate(children):
        segment = _child_slot(child, i)
        child_path = own_path + [segment]
        resolved_children.append(_resolve(child, child_path, registry, session, visited))

    new_props["children"] = resolved_children
    new_props["data-pyid"] = pyid
    return VNode(vnode.type, new_props, key=vnode.key)
