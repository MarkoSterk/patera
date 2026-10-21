(() => {
  const PATTERN = /\\\$|\$\$([^$]+?)\$\$|\$([^$]+?)\$/g;
  const parser = new DOMParser();

  function segments(text) {
    const parts = [];
    let plain = '';
    let last = 0;
    for (const match of text.matchAll(PATTERN)) {
      plain += text.slice(last, match.index);
      last = match.index + match[0].length;
      if (match[0] === '\\$') {
        plain += '$';
        continue;
      }
      if (plain) parts.push({text: plain});
      plain = '';
      const display = match[1] !== undefined;
      parts.push({tex: display ? match[1] : match[2], display});
    }
    plain += text.slice(last);
    if (plain) parts.push({text: plain});
    return parts;
  }

  function mathNode(tex, display) {
    const delimiter = display ? '$$' : '$';
    if (!window.temml) return document.createTextNode(delimiter + tex + delimiter);
    try {
      const markup = temml.renderToString(tex, {displayMode: display, throwOnError: true})
        .replace(/ style="([^"]*)"/g, ' data-tml-style="$1"');
      const math = document.importNode(parser.parseFromString(markup, 'text/html').body.firstElementChild, true);
      for (const element of [math, ...math.querySelectorAll('[data-tml-style]')]) {
        if (!element.dataset.tmlStyle) continue;
        element.style.cssText = element.dataset.tmlStyle;
        delete element.dataset.tmlStyle;
      }
      return math;
    } catch (error) {
      const code = document.createElement('code');
      code.className = 'math-error';
      code.title = error.message;
      code.textContent = delimiter + tex + delimiter;
      return code;
    }
  }

  function render(text, container) {
    container.replaceChildren(...segments(String(text ?? '')).map(part =>
      part.text !== undefined ? document.createTextNode(part.text) : mathNode(part.tex, part.display)));
  }

  function renderAll(root = document) {
    root.querySelectorAll('.math-text:not([data-rendered])').forEach(element => {
      element.dataset.rendered = '';
      render(element.textContent, element);
    });
  }

  function observe(root = document.body) {
    renderAll(root);
    new MutationObserver(() => renderAll(root)).observe(root, {childList: true, subtree: true});
  }

  window.QuickExamsMath = {render, renderAll, observe};
})();
