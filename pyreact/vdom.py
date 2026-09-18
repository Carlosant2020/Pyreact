"""
Núcleo do Virtual DOM: representa a UI como uma árvore de objetos Python
antes de virar HTML de verdade.
"""
from __future__ import annotations
import itertools
from typing import Any, Callable, Union

_uid_counter = itertools.count(1)

TEXT_NODE = "#text"


class VNode:
    """
    Representa um nó da árvore virtual.

    type: nome da tag ('div', 'button', ...), TEXT_NODE, ou uma função de
          componente (component functions).
    props: dicionário de atributos/props (inclui 'children' e handlers
           de evento como 'onClick').
    key: identificador estável usado no diffing de listas.
    """

    __slots__ = ("type", "props", "key", "_uid")

    def __init__(self, type_: Union[str, Callable], props: dict[str, Any] | None = None,
                 key: Any = None):
        self.type = type_
        self.props = props or {}
        self.key = key
        self._uid = next(_uid_counter)

    @property
    def children(self) -> list["VNode"]:
        return self.props.get("children", [])

    def is_text(self) -> bool:
        return self.type == TEXT_NODE

    def is_component(self) -> bool:
        return callable(self.type) and not isinstance(self.type, str)

    def __repr__(self):
        name = self.type if isinstance(self.type, str) else getattr(self.type, "__name__", "Component")
        return f"<VNode {name} props={ {k: v for k, v in self.props.items() if k != 'children'} }>"


def _normalize_child(child: Any) -> VNode:
    if isinstance(child, VNode):
        return child
    if child is None or child is False or child is True:
        # nós vazios não renderizam nada
        return VNode(TEXT_NODE, {"nodeValue": ""})
    return VNode(TEXT_NODE, {"nodeValue": str(child)})


def h(type_: Union[str, Callable], props: dict[str, Any] | None = None, *children: Any) -> VNode:
    """
    Hyperscript: cria um VNode. Equivalente ao React.createElement.

        h('div', {'className': 'box'},
            h('span', None, 'Olá'),
            h('button', {'onClick': handler}, 'Clique'))
    """
    props = dict(props or {})
    key = props.pop("key", None)

    flat_children: list[Any] = []
    for c in children:
        if isinstance(c, (list, tuple)):
            flat_children.extend(c)
        else:
            flat_children.append(c)

    props["children"] = [_normalize_child(c) for c in flat_children]
    return VNode(type_, props, key=key)


def text(value: Any) -> VNode:
    return VNode(TEXT_NODE, {"nodeValue": str(value)})
