export default class SummernoteEditor extends HTMLElement {
  static get observedAttributes() {
    return [
      "name",
      "value",
      "placeholder",
      "height",
      "upload-url",
      "features",
      "disabled",
      "readonly",
      "required"
    ];
  }

  constructor() {
    super();

    this._initialized = false;
    this._pendingValue = null;
    this._editorElement = null;
  }

  connectedCallback() {
    this.#upgradeProperty("value");

    if (!this.#hasSummernote()) {
      throw new Error(
        "SummernoteEditor requires jQuery and summernote-lite.js to be loaded before the element is connected."
      );
    }

    this.#ensureDom();
    this.#initializeSummernote();
    this.#syncHiddenInput();

    if (this.hasAttribute("value")) {
      this.value = this.getAttribute("value") || "";
    }
  }

  disconnectedCallback() {
    if (!this._initialized) {
      return;
    }

    this.#jqueryEditor.summernote("destroy");
    this._initialized = false;
  }

  attributeChangedCallback(name, oldValue, newValue) {
    if (oldValue === newValue) {
      return;
    }

    if (name === "name") {
      this.#syncHiddenInput();
      return;
    }

    if (name === "value") {
      this.value = newValue || "";
      return;
    }

    if (name === "disabled" || name === "readonly") {
      this.#syncEditorState();
      this.#syncHiddenInput();
      return;
    }

    if (
      name === "placeholder" ||
      name === "height" ||
      name === "upload-url" ||
      name === "features"
    ) {
      this.#reinitializeSummernote();
    }
  }

  get name() {
    return this.getAttribute("name") || "";
  }

  set name(value) {
    if (value === null || value === undefined || value === "") {
      this.removeAttribute("name");
      return;
    }

    this.setAttribute("name", String(value));
  }

  get value() {
    if (!this._initialized) {
      return this._pendingValue || "";
    }

    return this.#jqueryEditor.summernote("code");
  }

  set value(value) {
    const html = value === null || value === undefined ? "" : String(value);

    if (!this._initialized) {
      this._pendingValue = html;
      return;
    }

    this.#jqueryEditor.summernote("code", html);
    this.#syncHiddenInput();
  }

  get uploadUrl() {
    return this.getAttribute("upload-url") || "";
  }

  get features() {
    const rawFeatures = this.getAttribute("features");

    if (!rawFeatures || !rawFeatures.trim()) {
      return this.#defaultFeatures;
    }

    return rawFeatures
      .split(",")
      .map((feature) => feature.trim().toLowerCase())
      .filter(Boolean);
  }

  get #defaultFeatures() {
    const features = ["headings", "font", "alignment"];

    if (this.uploadUrl) {
      features.push("image");
    }

    return features;
  }

  get disabled() {
    return this.hasAttribute("disabled");
  }

  set disabled(value) {
    this.toggleAttribute("disabled", Boolean(value));
  }

  get readonly() {
    return this.hasAttribute("readonly");
  }

  set readonly(value) {
    this.toggleAttribute("readonly", Boolean(value));
  }

  focus() {
    if (!this._initialized) {
      return;
    }

    this.#jqueryEditor.summernote("focus");
  }

  get #jqueryEditor() {
    return window.jQuery(this._editorElement);
  }

  #ensureDom() {
    if (this._editorElement) {
      return;
    }

    this.classList.add("summernote-editor-element");

    this._editorElement = document.createElement("div");
    this._editorElement.className = "summernote-editor-host";

    this.appendChild(this._editorElement);
  }

  #initializeSummernote() {
    if (this._initialized) {
      return;
    }

    this.#jqueryEditor.summernote({
      height: this.#getHeight(),
      placeholder: this.getAttribute("placeholder") || "",
      toolbar: this.#buildToolbar(),
      dialogsInBody: true,
      callbacks: {
        onChange: () => {
          this.#commitValue();
        },
        onImageUpload: (files) => {
          this.#handleImageUpload(files);
        }
      }
    });

    this._initialized = true;

    if (this._pendingValue !== null) {
      this.#jqueryEditor.summernote("code", this._pendingValue);
      this._pendingValue = null;
    } else if (this.hasAttribute("value")) {
      this.#jqueryEditor.summernote("code", this.getAttribute("value") || "");
    }

    this.#syncEditorState();
    this.#syncHiddenInput();
  }

  #reinitializeSummernote() {
    if (!this.isConnected || !this.#hasSummernote() || !this._editorElement) {
      return;
    }

    const currentValue = this.value;

    if (this._initialized) {
      this.#jqueryEditor.summernote("destroy");
      this._initialized = false;
    }

    this._pendingValue = currentValue;
    this.#initializeSummernote();
  }

  #buildToolbar() {
    const features = new Set(this.features);
    const toolbar = [];

    if (features.has("headings")) {
      toolbar.push(["style", ["style"]]);
    }

    if (features.has("font")) {
      toolbar.push(["font", ["bold", "italic", "underline", "clear"]]);
      toolbar.push(["fontsize", ["fontsize"]]);
    }

    if (features.has("color")) {
      toolbar.push(["color", ["color"]]);
    }

    if (features.has("alignment")) {
      toolbar.push(["para", ["ul", "ol", "paragraph"]]);
    }

    if (features.has("link")) {
      toolbar.push(["insert-link", ["link"]]);
    }

    if (features.has("image") && this.uploadUrl) {
      toolbar.push(["insert-image", ["picture"]]);
    }

    if (features.has("table")) {
      toolbar.push(["table", ["table"]]);
    }

    if (features.has("code")) {
      toolbar.push(["view", ["codeview"]]);
    }

    return toolbar;
  }

  #getHeight() {
    const rawHeight = this.getAttribute("height");

    if (!rawHeight) {
      return 220;
    }

    const parsed = Number.parseInt(rawHeight, 10);

    if (Number.isNaN(parsed) || parsed <= 0) {
      return 220;
    }

    return parsed;
  }

  async #handleImageUpload(files) {
    if (!this.uploadUrl) {
      return;
    }

    for (const file of files) {
      await this.#uploadImage(file);
    }
  }

  async #uploadImage(file) {
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch(this.uploadUrl, {
      method: "POST",
      body: formData
    });

    if (!response.ok) {
      throw new Error("Image upload failed.");
    }

    const payload = await response.json();
    const imageUrl = payload.url || payload.location || payload.src;

    if (!imageUrl) {
      throw new Error("Image upload response must contain url, location or src.");
    }

    this.#jqueryEditor.summernote("insertImage", imageUrl);
    this.#commitValue();
  }

  #commitValue() {
    this.#syncHiddenInput();

    this.dispatchEvent(
      new InputEvent("input", {
        bubbles: true,
        composed: true
      })
    );

    this.dispatchEvent(
      new Event("change", {
        bubbles: true,
        composed: true
      })
    );
  }

  #syncHiddenInput() {
    const name = this.name;

    if (!name) {
      this.#removeHiddenInput();
      return;
    }

    let hiddenInput = this.querySelector(':scope > input[type="hidden"][data-summernote-editor-value]');

    if (!hiddenInput) {
      hiddenInput = document.createElement("input");
      hiddenInput.type = "hidden";
      hiddenInput.dataset.summernoteEditorValue = "true";
      this.appendChild(hiddenInput);
    }

    hiddenInput.name = name;
    hiddenInput.value = this.value;
    hiddenInput.disabled = this.disabled;
    hiddenInput.required = false;
  }

  #removeHiddenInput() {
    this.querySelector(':scope > input[type="hidden"][data-summernote-editor-value]')?.remove();
  }

  #syncEditorState() {
    if (!this._initialized) {
      return;
    }

    if (this.disabled || this.readonly) {
      this.#jqueryEditor.summernote("disable");
      return;
    }

    this.#jqueryEditor.summernote("enable");
  }

  #hasSummernote() {
    return Boolean(
      window.jQuery &&
      window.jQuery.fn &&
      window.jQuery.fn.summernote
    );
  }

  #upgradeProperty(propertyName) {
    if (!Object.prototype.hasOwnProperty.call(this, propertyName)) {
      return;
    }

    const value = this[propertyName];
    delete this[propertyName];
    this[propertyName] = value;
  }

  refresh() {
    if (!this._initialized) {
      return;
    }

    const currentValue = this.value;

    this.#jqueryEditor.summernote("destroy");
    this._initialized = false;
    this._pendingValue = currentValue;

    this.#initializeSummernote();
  }
}

//customElements.define("summernote-editor", SummernoteEditor);
