class TagsInput extends HTMLElement {
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

        input {
          width: 100%;
          box-sizing: border-box;
          padding: 0.5rem 0.75rem;
          border: 1px solid #ced4da;
          border-radius: 0.375rem;
          font: inherit;
        }

        input:focus {
          outline: none;
          border-color: #86b7fe;
          box-shadow: 0 0 0 0.25rem rgba(13, 110, 253, 0.25);
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
  }

  disconnectedCallback() {
    this.inputElement.removeEventListener("keydown", this.#handleInputKeydown);
    this.tagsElement.removeEventListener("click", this.#handleTagClick);
  }

  get inputElement() {
    return this.shadowRoot.querySelector("input");
  }

  get tagsElement() {
    return this.shadowRoot.querySelector(".tags");
  }

  get value() {
    return [...this.tagsElement.querySelectorAll(".tag")]
      .map((tagElement) => tagElement.dataset.value);
  }

  set value(tags) {
    if (!Array.isArray(tags)) {
      throw new TypeError("TagsInput value must be an array of strings.");
    }

    this.tagsElement.innerHTML = "";

    for (const tag of tags) {
      this.#appendTag(tag);
    }
  }

  #handleInputKeydown = (event) => {
    if (event.key !== "Enter") {
      return;
    }

    event.preventDefault();

    const value = this.inputElement.value.trim();

    if (!value) {
      return;
    }

    this.#appendTag(value);
    this.inputElement.value = "";

    this.dispatchEvent(new Event("change", { bubbles: true }));
  };

  #handleTagClick = (event) => {
    const removeButton = event.target.closest(".tag-remove");

    if (!removeButton) {
      return;
    }

    removeButton.closest(".tag")?.remove();

    this.dispatchEvent(new Event("change", { bubbles: true }));
  };

  #appendTag(value) {
    const normalizedValue = String(value).trim();

    if (!normalizedValue) {
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
}

//customElements.define("tags-input", TagsInput);
