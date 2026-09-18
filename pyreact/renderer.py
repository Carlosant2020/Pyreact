"""
Converte a árvore "host" (só tags/texto) resultante do reconciler em uma
string HTML, e registra os handlers de evento (onClick, onInput, ...) num
dicionário `handlers` indexado por data-pyid, para o app.py poder invocá-los
quando o cliente reportar um evento via WebSocket.
"""
from __future__ import annotations
import html as html_lib
from .vdom import VNode

VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
             "link", "meta", "param", "source", "track", "wbr"}

_EVENT_PROPS = {"onClick": "click", "onInput": "input", "onChange": "change",
                "onSubmit": "submit", "onKeyDown": "keydown", "onKeyUp": "keyup",
                "onFocus": "focus", "onBlur": "blur"}


def _style_to_css(style: dict) -> str:
    parts = []
    for k, v in style.items():
        css_key = "".join(f"-{c.lower()}" if c.isupper() else c for c in k)
        parts.append(f"{css_key}:{v}")
    return ";".join(parts)


def render_to_html(vnode: VNode, handlers: dict) -> str:
    if vnode.is_text():
        return html_lib.escape(str(vnode.props.get("nodeValue", "")))

    tag = vnode.type
    attrs = []
    events_for_node = {}

    for key, value in vnode.props.items():
        if key in ("children", "nodeValue"):
            continue
        if key in _EVENT_PROPS:
            events_for_node[_EVENT_PROPS[key]] = value
            continue
        if key == "className":
            key = "class"
        if key == "style" and isinstance(value, dict):
            value = _style_to_css(value)
        if value is False or value is None:
            continue
        if value is True:
            attrs.append(f'{key}')
            continue
        attrs.append(f'{key}="{html_lib.escape(str(value), quote=True)}"')

    if events_for_node:
        pyid = vnode.props.get("data-pyid", "root")
        handlers[pyid] = events_for_node
        attrs.append(f'data-events="{",".join(events_for_node.keys())}"')

    attr_str = (" " + " ".join(attrs)) if attrs else ""

    if tag in VOID_TAGS:
        return f"<{tag}{attr_str}>"

    children_html = "".join(render_to_html(c, handlers) for c in vnode.children)
    return f"<{tag}{attr_str}>{children_html}</{tag}>"


def collect_handlers(vnode: VNode, handlers: dict) -> None:
    """Percorre a árvore inteira só para (re)registrar os handlers de
    evento atuais, sem gerar HTML. Chamado a cada render para garantir que
    o servidor sempre invoque a closure mais recente (com o estado mais
    recente capturado)."""
    if vnode.is_text():
        return
    events_for_node = {}
    for key, value in vnode.props.items():
        if key in _EVENT_PROPS:
            events_for_node[_EVENT_PROPS[key]] = value
    if events_for_node:
        handlers[vnode.props.get("data-pyid", "root")] = events_for_node
    for child in vnode.children:
        collect_handlers(child, handlers)
