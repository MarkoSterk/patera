export default class TagsInput extends HTMLElement {
  static get observedAttributes() {
    return ["value", "name", "placeholder", "disabled", "readonly", "required"];
  }

  constructor() {
    super();

    this.attachShadow({ mode: "open" });

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: inherit;
        }

        .tags-input-wrapper {
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
        }

        input[type="text"] {
          width: 100%;
          box-sizing: border-box;
          padding: 0.5rem 0.75rem;
          border: 1px solid #ced4da;
          border-radius: 0.375rem;
          font: inherit;
        }

        input[type="text"]:focus {
          outline: none;
          border-color: #86b7fe;
          box-shadow: 0 0 0 0.25rem rgba(13, 110, 253, 0.25);
        }

        input[type="text"]:disabled {
          background: #e9ecef;
          cursor: not-allowed;
        }

        .tags {
          display: flex;
          flex-wrap: wrap;
          gap: 0.4rem;
        }

        .tag {
          display: inline-flex;
          align-items: center;
          gap: 0.35rem;
          padding: 0.25rem 0.5rem;
          border-radius: 999px;
          background: #e9ecef;
          color: #212529;
          font-size: 0.875rem;
        }

        .tag-remove {
          border: 0;
          background: transparent;
          color: inherit;
          cursor: pointer;
          font: inherit;
          line-height: 1;
          padding: 0;
        }

        .tag-remove:hover {
          color: #dc3545;
        }

        :host([disabled]) .tag-remove,
        :host([readonly]) .tag-remove {
          display: none;
        }
      </style>

      <div class="tags-input-wrapper">
        <input type="text" part="input">
        <div class="tags" part="tags"></div>
      </div>
    `;
  }

  connectedCallback() {
    this.inputElement.addEventListener("keydown", this.#handleInputKeydown);
    this.tagsElement.addEventListener("click", this.#handleTagClick);

    this.#upgradeProperty("value");
    this.#syncInputAttributes();
    this.#syncHiddenInput();

    if (this.hasAttribute("value")) {
      this.#setValueFromAttribute(this.getAttribute("value"));
    }
  }

  disconnectedCallback() {
    this.inputElement.removeEventListener("keydown", this.#handleInputKeydown);
    this.tagsElement.removeEventListener("click", this.#handleTagClick);
  }

  attributeChangedCallback(name, oldValue, newValue) {
    if (oldValue === newValue || !this.shadowRoot) {
      return;
    }

    if (name === "value") {
      this.#setValueFromAttribute(newValue);
      this.#syncHiddenInput();
      return;
    }

    if (name === "name") {
      this.#syncHiddenInput();
      return;
    }

    this.#syncInputAttributes();
  }

  get inputElement() {
    return this.shadowRoot.querySelector('input[type="text"]');
  }

  get tagsElement() {
    return this.shadowRoot.querySelector(".tags");
  }

  get formElement() {
    return this.closest("form");
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
    return [...this.tagsElement.querySelectorAll(".tag")]
      .map((tagElement) => tagElement.dataset.value)
      .filter((value) => value !== undefined);
  }

  set value(tags) {
    if (!Array.isArray(tags)) {
      throw new TypeError("TagsInput value must be an array of strings.");
    }

    this.tagsElement.innerHTML = "";

    for (const tag of tags) {
      this.#appendTag(tag);
    }

    this.#syncHiddenInput();
  }

  get serializedValue() {
    return JSON.stringify(this.value);
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

  #handleInputKeydown = (event) => {
    if (event.key !== "Enter") {
      return;
    }

    event.preventDefault();

    if (this.disabled || this.readonly) {
      return;
    }

    const value = this.inputElement.value.trim();

    if (!value) {
      return;
    }

    this.#appendTag(value);
    this.inputElement.value = "";
    this.#commitValue();
  };

  #handleTagClick = (event) => {
    if (this.disabled || this.readonly) {
      return;
    }

    const removeButton = event.target.closest(".tag-remove");

    if (!removeButton) {
      return;
    }

    removeButton.closest(".tag")?.remove();
    this.#commitValue();
  };

  #appendTag(value) {
    const normalizedValue = String(value).trim();

    if (!normalizedValue) {
      return;
    }

    if (this.value.includes(normalizedValue)) {
      return;
    }

    const tagElement = document.createElement("span");
    tagElement.className = "tag";
    tagElement.dataset.value = normalizedValue;

    const labelElement = document.createElement("span");
    labelElement.textContent = normalizedValue;

    const removeButton = document.createElement("button");
    removeButton.type = "button";
    removeButton.className = "tag-remove";
    removeButton.setAttribute("aria-label", `Remove ${normalizedValue}`);
    removeButton.textContent = "×";

    tagElement.append(labelElement, removeButton);
    this.tagsElement.appendChild(tagElement);
  }

  #commitValue() {
    this.#syncHiddenInput();

    this.dispatchEvent(
      new InputEvent("input", {
        bubbles: true,
        composed: true,
      })
    );

    this.dispatchEvent(
      new Event("change", {
        bubbles: true,
        composed: true,
      })
    );
  }

  #setValueFromAttribute(rawValue) {
    if (rawValue === null || rawValue.trim() === "") {
      this.value = [];
      return;
    }

    try {
      const parsed = JSON.parse(rawValue);

      if (Array.isArray(parsed)) {
        this.value = parsed.map((item) => String(item));
        return;
      }
    } catch {
      // Fall back to comma-separated values below.
    }

    this.value = rawValue
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  }

  #syncInputAttributes() {
    if (!this.inputElement) {
      return;
    }

    this.inputElement.disabled = this.disabled;
    this.inputElement.readOnly = this.readonly;
    this.inputElement.required = this.hasAttribute("required");
    this.inputElement.placeholder = this.getAttribute("placeholder") || "";
  }

  #syncHiddenInput() {
    const name = this.name;

    if (!name) {
      this.#removeHiddenInput();
      return;
    }

    let hiddenInput = this.querySelector(':scope > input[type="hidden"][data-tags-input-value]');

    if (!hiddenInput) {
      hiddenInput = document.createElement("input");
      hiddenInput.type = "hidden";
      hiddenInput.dataset.tagsInputValue = "true";
      this.appendChild(hiddenInput);
    }

    hiddenInput.name = name;
    hiddenInput.value = this.serializedValue;
    hiddenInput.disabled = this.disabled;
  }

  #removeHiddenInput() {
    this.querySelector(':scope > input[type="hidden"][data-tags-input-value]')?.remove();
  }

  #upgradeProperty(propertyName) {
    if (!Object.prototype.hasOwnProperty.call(this, propertyName)) {
      return;
    }

    const value = this[propertyName];
    delete this[propertyName];
    this[propertyName] = value;
  }
}

//customElements.define("tags-input", TagsInput);
