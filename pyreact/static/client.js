// Runtime mínimo do PyReact: conecta no WebSocket, aplica patches recebidos
// do servidor e reencaminha eventos do DOM para o servidor decidir o que fazer.

(function () {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const sessionId = window.__PYREACT_SESSION__;
  const socket = new WebSocket(`${proto}//${location.host}/ws/${sessionId}`);

  function findByPyId(pyid) {
    return document.querySelector(`[data-pyid="${CSS.escape(pyid)}"]`);
  }

  function applyPatch(patch) {
    switch (patch.op) {
      case "update_props": {
        const el = findByPyId(patch.id);
        if (!el) return;
        for (const [key, value] of Object.entries(patch.props)) {
          if (value === null) {
            el.removeAttribute(key);
          } else if (key === "value" && "value" in el) {
            el.value = value; // inputs: precisa setar a propriedade, não só o atributo
          } else {
            el.setAttribute(key, value);
          }
        }
        break;
      }
      case "set_text": {
        const parent = findByPyId(patch.parent_id) || document.body;
        const node = parent.childNodes[patch.index];
        if (node) node.nodeValue = patch.value;
        break;
      }
      case "replace_at": {
        const parent = findByPyId(patch.parent_id) || document.body;
        const node = parent.childNodes[patch.index];
        const tmp = document.createElement("template");
        tmp.innerHTML = patch.html;
        if (node) parent.replaceChild(tmp.content.firstChild, node);
        break;
      }
      case "insert": {
        const parent = findByPyId(patch.parent_id) || document.body;
        const tmp = document.createElement("template");
        tmp.innerHTML = patch.html;
        const ref = parent.childNodes[patch.index] || null;
        parent.insertBefore(tmp.content.firstChild, ref);
        break;
      }
      case "remove_at": {
        const parent = findByPyId(patch.parent_id) || document.body;
        const node = parent.childNodes[patch.index];
        if (node) parent.removeChild(node);
        break;
      }
    }
  }

  socket.addEventListener("message", (msg) => {
    const data = JSON.parse(msg.data);
    if (data.type === "patches") {
      data.patches.forEach(applyPatch);
    }
  });

  function sendEvent(pyid, eventName, value) {
    socket.send(JSON.stringify({ pyid, event: eventName, value }));
  }

  // Delegação de eventos: um único listener por tipo de evento no document,
  // que sobe a árvore procurando o elemento mais próximo com data-events.
  ["click", "input", "change", "submit", "keydown", "keyup", "focus", "blur"].forEach((eventType) => {
    document.addEventListener(
      eventType,
      (e) => {
        let el = e.target;
        while (el && el !== document.body) {
          const events = el.getAttribute && el.getAttribute("data-events");
          if (events && events.split(",").includes(eventType)) {
            if (eventType === "submit") e.preventDefault();
            const value = "value" in el ? el.value : null;
            sendEvent(el.getAttribute("data-pyid"), eventType, value);
            break;
          }
          el = el.parentElement;
        }
      },
      true
    );
  });
})();
