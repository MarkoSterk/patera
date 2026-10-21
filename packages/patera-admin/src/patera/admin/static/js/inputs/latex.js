const PATTERN = /\\\$|\$\$([^$]+?)\$\$|\$([^$]+?)\$/g;
const parser = new DOMParser();

/**
 * Splits text into plain parts and math between $...$ (inline) or
 * $$...$$ (display); \$ is a literal dollar sign.
 */
export function segments(text) {
  const parts = [];
  let plain = "";
  let last = 0;

  for (const match of text.matchAll(PATTERN)) {
    plain += text.slice(last, match.index);
    last = match.index + match[0].length;

    if (match[0] === "\\$") {
      plain += "$";
      continue;
    }

    if (plain) {
      parts.push({ text: plain });
    }

    plain = "";
    const display = match[1] !== undefined;
    parts.push({ tex: display ? match[1] : match[2], display });
  }

  plain += text.slice(last);

  if (plain) {
    parts.push({ text: plain });
  }

  return parts;
}

/**
 * Temml's MathML for one formula. Its few inline styles are applied through
 * the DOM rather than as style attributes, so a Content Security Policy
 * without 'unsafe-inline' styles does not block them.
 */
function mathNode(tex, display) {
  const delimiter = display ? "$$" : "$";

  if (!window.temml) {
    return document.createTextNode(delimiter + tex + delimiter);
  }

  try {
    const markup = window.temml
      .renderToString(tex, { displayMode: display, throwOnError: true })
      .replace(/ style="([^"]*)"/g, ' data-tml-style="$1"');
    const math = document.importNode(
      parser.parseFromString(markup, "text/html").body.firstElementChild,
      true
    );

    for (const element of [math, ...math.querySelectorAll("[data-tml-style]")]) {
      if (!element.dataset.tmlStyle) {
        continue;
      }

      element.style.cssText = element.dataset.tmlStyle;
      delete element.dataset.tmlStyle;
    }

    return math;
  } catch (error) {
    const code = document.createElement("code");
    code.className = "latex-error";
    code.title = error.message;
    code.textContent = delimiter + tex + delimiter;
    return code;
  }
}

/** Replaces the container's content with the rendered text. */
export function renderLatex(text, container) {
  container.replaceChildren(
    ...segments(String(text ?? "")).map((part) =>
      part.text !== undefined
        ? document.createTextNode(part.text)
        : mathNode(part.tex, part.display)
    )
  );
}
