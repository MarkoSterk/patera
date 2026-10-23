// Stable custom-element adapter: no generated JavaScript or eval.
const roots = new WeakMap();
const owners = new WeakMap();
const retired = new WeakSet();
window.pateraUI = {
  saveScroll() {
    history.replaceState({...history.state, __pateraScroll: [scrollX, scrollY]}, '', location.href);
  },
  scrollState() { return history.state?.__pateraScroll || [0, 0]; },
  replaceBinding(host, id, markup) {
    const walker = document.createTreeWalker(host, NodeFilter.SHOW_COMMENT);
    let start = null, end = null;
    while (walker.nextNode()) {
      const node = walker.currentNode;
      if (node.parentElement?.closest('[data-ui-instance]') !== host) continue;
      if (node.data === `ui-bind:${id}`) start = node;
      if (node.data === `/ui-bind:${id}`) { end = node; break; }
    }
    if (!start || !end) return;
    const range = document.createRange();
    range.setStartAfter(start);
    range.setEndBefore(end);
    const fragment = range.createContextualFragment(markup);
    range.deleteContents();
    range.insertNode(fragment);
  },
  attach(root, connected, disconnected) { roots.set(root, {connected, disconnected}); },
  detach(root) { roots.delete(root); },
  define(tag) {
    if (customElements.get(tag)) return;
    customElements.define(tag, class extends HTMLElement {
      connectedCallback() {
        if (retired.has(this)) return;
        let root = this.parentElement;
        while (root && !roots.has(root)) root = root.parentElement;
        if (root) {
          const owner = roots.get(root);
          owners.set(this, owner);
          owner.connected(this);
        }
      }
      disconnectedCallback() {
        retired.add(this);
        const owner = owners.get(this);
        owners.delete(this);
        if (owner) owner.disconnected(this);
      }
    });
  },
};
