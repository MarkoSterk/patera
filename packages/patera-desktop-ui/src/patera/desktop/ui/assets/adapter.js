// Stable custom-element adapter: no generated JavaScript or eval.
const roots = new WeakMap();
const owners = new WeakMap();
const retired = new WeakSet();
let moving = 0;
const declared = new WeakMap();
const attributeMap = node => new Map(Array.from(node.attributes, attr => [attr.name, attr.value]).filter(([name]) => name !== 'data-ui-instance'));
const eventAttribute = name => /^(?:@|data-ui-on-|jolt-)/.test(name);

function move(parent, node, before) {
  if (node.nextSibling === before && node.parentNode === parent) return;
  // Keep Patera component lifetimes intact on engines without moveBefore.
  moving++;
  try {
    if (parent.moveBefore && node.isConnected && parent.isConnected) parent.moveBefore(node, before);
    else parent.insertBefore(node, before);
  } finally { moving--; }
}

function attributes(current, desired, result) {
  let eventsChanged = false;
  const previous = declared.get(current) || attributeMap(current);
  for (const name of previous.keys()) {
    if (desired.hasAttribute(name)) continue;
    current.removeAttribute(name);
    if (name === 'checked') current.checked = false;
    if (name === 'selected') current.selected = false;
    if (name === 'value' && 'value' in current) current.value = '';
    eventsChanged ||= eventAttribute(name);
  }
  for (const attr of desired.attributes) {
    if (previous.get(attr.name) === attr.value) continue;
    // Cloning parsed attributes also supports shorthand names such as @click
    // and :argument on engines that reject them in setAttribute().
    current.setAttributeNodeNS(attr.cloneNode(true));
    if (attr.name === 'value' && 'value' in current) current.value = attr.value;
    if (attr.name === 'checked') current.checked = true;
    if (attr.name === 'selected') current.selected = true;
    eventsChanged ||= eventAttribute(attr.name);
  }
  declared.set(current, attributeMap(desired));
  if (eventsChanged) result.changed.push(current);
}

function patch(current, desired, result) {
  if (current.nodeType !== desired.nodeType || current.nodeName !== desired.nodeName) {
    current.replaceWith(desired);
    result.inserted.push(desired);
    return desired;
  }
  if (current.nodeType !== Node.ELEMENT_NODE) {
    if (current.data !== desired.data) current.data = desired.data;
    return current;
  }
  attributes(current, desired, result);
  if (current.hasAttribute('data-ui-instance')) {
    // A mounted child owns its interior; Python updates its args separately.
    result.components.push(current);
    return current;
  }
  const oldChildren = Array.from(current.childNodes);
  const newChildren = Array.from(desired.childNodes);
  for (let i = 0; i < Math.max(oldChildren.length, newChildren.length); i++) {
    if (!newChildren[i]) oldChildren[i].remove();
    else if (!oldChildren[i]) { current.appendChild(newChildren[i]); result.inserted.push(newChildren[i]); }
    else patch(oldChildren[i], newChildren[i], result);
  }
  return current;
}

function keyed(parent, oldNodes, newNodes, end, result) {
  const rows = nodes => nodes.filter(node => node.nodeType === Node.ELEMENT_NODE);
  const incoming = rows(newNodes), existing = new Map();
  const seen = new Set();
  for (const node of incoming) {
    const key = node.getAttribute('data-ui-key');
    if (!key || seen.has(key)) throw new Error('Keyed rows require unique non-empty data-ui-key values');
    seen.add(key);
  }
  for (const node of rows(oldNodes)) existing.set(node.getAttribute('data-ui-key'), node);
  const reconciled = new Map();
  for (const desired of incoming) {
    const key = desired.getAttribute('data-ui-key');
    const current = existing.get(key);
    if (current) { existing.delete(key); reconciled.set(key, patch(current, desired, result)); }
    else { reconciled.set(key, desired); result.inserted.push(desired); }
  }
  for (const node of existing.values()) node.remove();
  for (const node of oldNodes) if (node.nodeType !== Node.ELEMENT_NODE) node.remove();
  const ordered = newNodes.map(node => node.nodeType === Node.ELEMENT_NODE ? reconciled.get(node.getAttribute('data-ui-key')) : node);
  // Right-to-left placement avoids moving rows already in their final position.
  let before = end;
  for (const node of ordered.reverse()) {
    if (!node.isConnected) parent.insertBefore(node, before);
    else move(parent, node, before);
    before = node;
  }
}

window.pateraUI = {
  remember(node) { if (!declared.has(node)) declared.set(node, attributeMap(node)); },
  saveScroll() {
    history.replaceState({...history.state, __pateraScroll: [scrollX, scrollY]}, '', location.href);
  },
  scrollState() { return history.state?.__pateraScroll || [0, 0]; },
  replaceBinding(host, id, markup, mode = 'replace') {
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
    if (mode !== 'replace') {
      const result = {inserted: [], changed: [], components: []};
      const oldNodes = [];
      for (let node = start.nextSibling; node && node !== end; node = node.nextSibling) oldNodes.push(node);
      const focus = document.activeElement;
      const selection = focus && typeof focus.selectionStart === 'number' ? [focus.selectionStart, focus.selectionEnd, focus.selectionDirection] : null;
      if (mode === 'virtual') {
        const current = oldNodes.find(node => node.nodeType === Node.ELEMENT_NODE);
        const desired = fragment.firstElementChild;
        attributes(current, desired, result);
        attributes(current.children[0], desired.children[0], result);
        attributes(current.children[2], desired.children[2], result);
        keyed(current.children[1], Array.from(current.children[1].childNodes), Array.from(desired.children[1].childNodes), null, result);
        current.scrollTop = Number(desired.getAttribute('data-ui-scroll-top'));
      } else keyed(start.parentNode, oldNodes, Array.from(fragment.childNodes), end, result);
      if (focus?.isConnected) {
        if (document.activeElement !== focus) focus.focus({preventScroll: true});
        if (selection) focus.setSelectionRange(...selection);
      }
      return result;
    }
    const inserted = Array.from(fragment.childNodes);
    range.deleteContents();
    range.insertNode(fragment);
    return inserted;
  },
  insertHTML(target, position, markup) {
    const range = document.createRange();
    range.selectNodeContents(target);
    const fragment = range.createContextualFragment(markup);
    const inserted = Array.from(fragment.childNodes);
    if (position === 'afterbegin') target.prepend(fragment);
    else target.append(fragment);
    return inserted;
  },
  attach(root, connected, disconnected) { roots.set(root, {connected, disconnected}); },
  detach(root) { roots.delete(root); },
  define(tag) {
    if (customElements.get(tag)) return;
    customElements.define(tag, class extends HTMLElement {
      connectedCallback() {
        if (moving) return;
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
        if (moving) return;
        retired.add(this);
        const owner = owners.get(this);
        owners.delete(this);
        if (owner) owner.disconnected(this);
      }
    });
  },
};
