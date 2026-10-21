import { renderLatex } from "./latex.js";

const ASSETS = {
  styles: ["../vendors/temml/Temml-Local.css", "./latexInput.css"],
  script: "../vendors/temml/temml.min.js",
};

let assetsLoaded = null;

function load(element) {
  return new Promise((resolve, reject) => {
    element.addEventListener("load", resolve, { once: true });
    element.addEventListener(
      "error",
      () => reject(new Error(`Could not load ${element.src || element.href}`)),
      { once: true }
    );
    document.head.append(element);
  });
}

/** Loads Temml and its styles from Admin's static assets, once per page. */
function loadAssets() {
  if (!assetsLoaded) {
    const url = (path) => new URL(path, import.meta.url).href;

    assetsLoaded = Promise.all([
      ...ASSETS.styles.map((path) =>
        load(Object.assign(document.createElement("link"), { rel: "stylesheet", href: url(path) }))
      ),
      window.temml
        ? Promise.resolve()
        : load(Object.assign(document.createElement("script"), { src: url(ASSETS.script) })),
    ]);
  }

  return assetsLoaded;
}

/**
 * <latex-input>
 *   <textarea name="..."></textarea>
 *   <div data-preview></div>
 * </latex-input>
 *
 * The inner control is an ordinary form field, so it is submitted and
 * validated with the form. The preview shows the text with its LaTeX math
 * rendered by Temml and is redrawn on every change.
 */
export default class LatexInput extends HTMLElement {
  constructor() {
    super();

    this._frame = 0;
    this._pendingValue = null;
    this._assets = null;
    this._control = null;
    this._preview = null;
  }

  connectedCallback() {
    if (this._control) {
      return;
    }

    this._control = this.querySelector("textarea, input");
    this._preview = this.querySelector("[data-preview]");

    if (!this._control) {
      return;
    }

    if (!this._preview) {
      this._preview = document.createElement("div");
      this._preview.dataset.preview = "";
      this.append(this._preview);
    }

    if (this._pendingValue !== null) {
      this._control.value = this._pendingValue;
      this._pendingValue = null;
    }

    this._assets = loadAssets();
    this._control.addEventListener("input", () => this.refresh());
    this._control.form?.addEventListener("reset", () => setTimeout(() => this.refresh()));
    this.refresh();
  }

  get value() {
    return this._control ? this._control.value : this._pendingValue || "";
  }

  set value(value) {
    const text = value === null || value === undefined ? "" : String(value);

    if (!this._control) {
      this._pendingValue = text;
      return;
    }

    this._control.value = text;
    this.refresh();
  }

  get name() {
    return this._control?.name || "";
  }

  focus(options) {
    this._control?.focus(options);
  }

  refresh() {
    if (!this._control || this._frame) {
      return;
    }

    this._frame = requestAnimationFrame(async () => {
      this._frame = 0;

      try {
        await this._assets;
      } catch (error) {
        console.error(error);
      }

      this.#draw();
    });
  }

  #draw() {
    const text = this._control.value;

    this._preview.hidden = text.trim() === "";

    if (this._preview.hidden) {
      this._preview.replaceChildren();
      return;
    }

    try {
      renderLatex(text, this._preview);
    } catch (error) {
      console.error(error);
      this._preview.textContent = text;
    }
  }
}
