class FileExplorer extends HTMLElement {
  static get observedAttributes() {
    return [
      "root",
      "list-url",
      "create-url",
      "rename-url",
      "delete-url",
      "move-url",
      "path"
    ];
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

        .file-explorer {
          border: 1px solid #dee2e6;
          border-radius: 0.5rem;
          background: #fff;
          overflow: hidden;
        }

        .file-explorer-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 1rem;
          padding: 1rem;
          border-bottom: 1px solid #dee2e6;
          background: #f8f9fa;
        }

        .title {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          font-weight: 600;
        }

        .breadcrumbs {
          display: flex;
          align-items: center;
          flex-wrap: wrap;
          gap: 0.25rem;
          padding: 0.75rem 1rem;
          border-bottom: 1px solid #dee2e6;
          background: #fff;
          font-size: 0.925rem;
        }

        .breadcrumb-button {
          border: 0;
          background: transparent;
          color: #0d6efd;
          padding: 0.125rem 0.25rem;
          cursor: pointer;
          font: inherit;
        }

        .breadcrumb-button:hover {
          text-decoration: underline;
        }

        .breadcrumb-separator {
          color: #6c757d;
        }

        .actions {
          display: flex;
          align-items: center;
          gap: 0.5rem;
        }

        button {
          font: inherit;
        }

        .btn {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          gap: 0.35rem;
          border: 1px solid #ced4da;
          background: #fff;
          border-radius: 0.375rem;
          padding: 0.375rem 0.625rem;
          cursor: pointer;
          color: #212529;
        }

        .btn:hover {
          background: #f8f9fa;
        }

        .btn-primary {
          border-color: #0d6efd;
          background: #0d6efd;
          color: #fff;
        }

        .btn-primary:hover {
          background: #0b5ed7;
        }

        .drop-zone {
          min-height: 240px;
          padding: 1rem;
          transition: background 0.15s ease, outline 0.15s ease;
        }

        .drop-zone.drag-over {
          background: rgba(13, 110, 253, 0.08);
          outline: 2px dashed #0d6efd;
          outline-offset: -0.75rem;
        }

        .items {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
          gap: 0.75rem;
        }

        .empty,
        .loading,
        .error {
          padding: 2rem;
          text-align: center;
          color: #6c757d;
        }

        .error {
          color: #dc3545;
        }

        .hidden {
          display: none;
        }

        .bi {
          line-height: 1;
        }
      </style>

      <div class="file-explorer">
        <div class="file-explorer-header">
          <div class="title">
            <i class="bi bi-folder2-open"></i>
            <span part="title">File Explorer</span>
          </div>

          <div class="actions">
            <button type="button" class="btn" id="refresh-btn">
              <i class="bi bi-arrow-clockwise"></i>
              Refresh
            </button>

            <button type="button" class="btn btn-primary" id="upload-btn">
              <i class="bi bi-upload"></i>
              Upload
            </button>

            <input id="file-input" type="file" multiple class="hidden">
          </div>
        </div>

        <nav class="breadcrumbs" part="breadcrumbs"></nav>

        <div class="drop-zone" part="drop-zone">
          <div class="loading hidden">Loading...</div>
          <div class="error hidden"></div>
          <div class="empty hidden">
            <i class="bi bi-folder-x"></i>
            <div>This folder is empty.</div>
          </div>
          <div class="items" part="items"></div>
        </div>
      </div>
    `;

    this._currentPath = "";
    this._items = [];
  }

  connectedCallback() {
    this._currentPath = this.getAttribute("path") || "";

    this.refreshButton.addEventListener("click", this.#handleRefreshClick);
    this.uploadButton.addEventListener("click", this.#handleUploadClick);
    this.fileInput.addEventListener("change", this.#handleFileInputChange);

    this.dropZone.addEventListener("dragenter", this.#handleDragEnter);
    this.dropZone.addEventListener("dragover", this.#handleDragOver);
    this.dropZone.addEventListener("dragleave", this.#handleDragLeave);
    this.dropZone.addEventListener("drop", this.#handleDrop);

    this.addEventListener("file-explorer-open-folder", this.#handleOpenFolder);
    this.addEventListener("file-explorer-delete", this.#handleDeleteItem);
    this.addEventListener("file-explorer-rename", this.#handleRenameItem);
    this.addEventListener("file-explorer-move", this.#handleMoveItem);

    this.load();
  }

  disconnectedCallback() {
    this.refreshButton.removeEventListener("click", this.#handleRefreshClick);
    this.uploadButton.removeEventListener("click", this.#handleUploadClick);
    this.fileInput.removeEventListener("change", this.#handleFileInputChange);

    this.dropZone.removeEventListener("dragenter", this.#handleDragEnter);
    this.dropZone.removeEventListener("dragover", this.#handleDragOver);
    this.dropZone.removeEventListener("dragleave", this.#handleDragLeave);
    this.dropZone.removeEventListener("drop", this.#handleDrop);

    this.removeEventListener("file-explorer-open-folder", this.#handleOpenFolder);
    this.removeEventListener("file-explorer-delete", this.#handleDeleteItem);
    this.removeEventListener("file-explorer-rename", this.#handleRenameItem);
    this.removeEventListener("file-explorer-move", this.#handleMoveItem);
  }

  attributeChangedCallback(name, oldValue, newValue) {
    if (oldValue === newValue) {
      return;
    }

    if (name === "path") {
      this._currentPath = newValue || "";

      if (this.isConnected) {
        this.load();
      }
    }
  }

  get root() {
    return this.getAttribute("root") || "";
  }

  get listUrl() {
    return this.getAttribute("list-url") || "";
  }

  get createUrl() {
    return this.getAttribute("create-url") || "";
  }

  get renameUrl() {
    return this.getAttribute("rename-url") || "";
  }

  get deleteUrl() {
    return this.getAttribute("delete-url") || "";
  }

  get moveUrl() {
    return this.getAttribute("move-url") || "";
  }

  get currentPath() {
    return this._currentPath;
  }

  set currentPath(value) {
    this._currentPath = this.#normalizePath(value || "");
    this.setAttribute("path", this._currentPath);
  }

  get refreshButton() {
    return this.shadowRoot.getElementById("refresh-btn");
  }

  get uploadButton() {
    return this.shadowRoot.getElementById("upload-btn");
  }

  get fileInput() {
    return this.shadowRoot.getElementById("file-input");
  }

  get breadcrumbsElement() {
    return this.shadowRoot.querySelector(".breadcrumbs");
  }

  get dropZone() {
    return this.shadowRoot.querySelector(".drop-zone");
  }

  get itemsElement() {
    return this.shadowRoot.querySelector(".items");
  }

  get loadingElement() {
    return this.shadowRoot.querySelector(".loading");
  }

  get errorElement() {
    return this.shadowRoot.querySelector(".error");
  }

  get emptyElement() {
    return this.shadowRoot.querySelector(".empty");
  }

  async load() {
    if (!this.listUrl) {
      this.#showError("Missing list-url attribute.");
      return;
    }

    this.#setLoading(true);
    this.#clearError();

    try {
      const url = new URL(this.listUrl, window.location.origin);

      url.searchParams.set("root", this.root);
      url.searchParams.set("path", this.currentPath);

      const response = await fetch(url.toString(), {
        method: "GET"
      });

      if (!response.ok) {
        throw new Error(await this.#readError(response, "Failed to list files."));
      }

      const payload = await response.json();

      this._currentPath = this.#normalizePath(payload.path ?? this.currentPath);
      this._items = Array.isArray(payload.items) ? payload.items : [];

      this.#render();
      this.#emit("file-explorer-loaded", {
        path: this.currentPath,
        items: this._items
      });
    } catch (error) {
      this.#showError(error.message || "Failed to list files.");
    } finally {
      this.#setLoading(false);
    }
  }

  async uploadFiles(files) {
    if (!this.createUrl) {
      this.#showError("Missing create-url attribute.");
      return;
    }

    const fileList = Array.from(files || []);

    if (fileList.length === 0) {
      return;
    }

    const formData = new FormData();
    formData.append("root", this.root);
    formData.append("path", this.currentPath);

    for (const file of fileList) {
      formData.append("files", file);
    }

    this.#setLoading(true);
    this.#clearError();

    try {
      const response = await fetch(this.createUrl, {
        method: "POST",
        body: formData
      });

      if (!response.ok) {
        throw new Error(await this.#readError(response, "Upload failed."));
      }

      await this.load();

      this.#emit("file-explorer-uploaded", {
        path: this.currentPath,
        count: fileList.length
      });
    } catch (error) {
      this.#showError(error.message || "Upload failed.");
    } finally {
      this.#setLoading(false);
      this.fileInput.value = "";
    }
  }

  async renameItem(path, newName) {
    if (!this.renameUrl) {
      this.#showError("Missing rename-url attribute.");
      return;
    }

    const formData = new FormData();
    formData.append("root", this.root);
    formData.append("path", path);
    formData.append("new_name", newName);

    await this.#postFormAndReload(this.renameUrl, formData, "Rename failed.");

    this.#emit("file-explorer-renamed", {
      path,
      newName
    });
  }

  async deleteItem(path) {
    if (!this.deleteUrl) {
      this.#showError("Missing delete-url attribute.");
      return;
    }

    const formData = new FormData();
    formData.append("root", this.root);
    formData.append("path", path);

    await this.#postFormAndReload(this.deleteUrl, formData, "Delete failed.");

    this.#emit("file-explorer-deleted", {
      path
    });
  }

  async moveItem(path, destinationPath) {
    if (!this.moveUrl) {
      this.#showError("Missing move-url attribute.");
      return;
    }

    const formData = new FormData();
    formData.append("root", this.root);
    formData.append("path", path);
    formData.append("destination_path", destinationPath);

    await this.#postFormAndReload(this.moveUrl, formData, "Move failed.");

    this.#emit("file-explorer-moved", {
      path,
      destinationPath
    });
  }

  #render() {
    this.#renderBreadcrumbs();
    this.#renderItems();
  }

  #renderBreadcrumbs() {
    const breadcrumbs = this.#getBreadcrumbs();

    this.breadcrumbsElement.innerHTML = "";

    breadcrumbs.forEach((breadcrumb, index) => {
      if (index > 0) {
        const separator = document.createElement("span");
        separator.className = "breadcrumb-separator";
        separator.textContent = "/";
        this.breadcrumbsElement.appendChild(separator);
      }

      const button = document.createElement("button");
      button.type = "button";
      button.className = "breadcrumb-button";
      button.textContent = breadcrumb.label;
      button.addEventListener("click", () => {
        this.currentPath = breadcrumb.path;
      });

      this.breadcrumbsElement.appendChild(button);
    });
  }

  #renderItems() {
    this.itemsElement.innerHTML = "";

    const folders = this._items
      .filter((item) => item.type === "folder")
      .sort((a, b) => a.name.localeCompare(b.name));

    const files = this._items
      .filter((item) => item.type !== "folder")
      .sort((a, b) => a.name.localeCompare(b.name));

    const sortedItems = [...folders, ...files];

    this.emptyElement.classList.toggle("hidden", sortedItems.length > 0);

    for (const item of sortedItems) {
      const element = item.type === "folder"
        ? document.createElement("file-explorer-folder")
        : document.createElement("file-explorer-file");

      element.item = item;
      element.root = this.root;
      element.currentPath = this.currentPath;

      this.itemsElement.appendChild(element);
    }
  }

  #getBreadcrumbs() {
    const breadcrumbs = [
      {
        label: "Root",
        path: ""
      }
    ];

    const parts = this.currentPath
      .split("/")
      .map((part) => part.trim())
      .filter(Boolean);

    let path = "";

    for (const part of parts) {
      path = path ? `${path}/${part}` : part;

      breadcrumbs.push({
        label: part,
        path
      });
    }

    return breadcrumbs;
  }

  async #postFormAndReload(url, formData, fallbackErrorMessage) {
    this.#setLoading(true);
    this.#clearError();

    try {
      const response = await fetch(url, {
        method: "POST",
        body: formData
      });

      if (!response.ok) {
        throw new Error(await this.#readError(response, fallbackErrorMessage));
      }

      await this.load();
    } catch (error) {
      this.#showError(error.message || fallbackErrorMessage);
    } finally {
      this.#setLoading(false);
    }
  }

  async #readError(response, fallbackMessage) {
    try {
      const payload = await response.json();
      return payload.message || payload.error || fallbackMessage;
    } catch {
      return fallbackMessage;
    }
  }

  #setLoading(isLoading) {
    this.loadingElement.classList.toggle("hidden", !isLoading);
  }

  #showError(message) {
    this.errorElement.textContent = message;
    this.errorElement.classList.remove("hidden");
  }

  #clearError() {
    this.errorElement.textContent = "";
    this.errorElement.classList.add("hidden");
  }

  #normalizePath(path) {
    return String(path || "")
      .replaceAll("\\", "/")
      .split("/")
      .map((part) => part.trim())
      .filter(Boolean)
      .join("/");
  }

  #emit(name, detail = {}) {
    this.dispatchEvent(
      new CustomEvent(name, {
        bubbles: true,
        composed: true,
        detail
      })
    );
  }

  #handleRefreshClick = () => {
    this.load();
  };

  #handleUploadClick = () => {
    this.fileInput.click();
  };

  #handleFileInputChange = () => {
    this.uploadFiles(this.fileInput.files);
  };

  #handleDragEnter = (event) => {
    event.preventDefault();
    this.dropZone.classList.add("drag-over");
  };

  #handleDragOver = (event) => {
    event.preventDefault();
    this.dropZone.classList.add("drag-over");
  };

  #handleDragLeave = (event) => {
    if (!this.dropZone.contains(event.relatedTarget)) {
      this.dropZone.classList.remove("drag-over");
    }
  };

  #handleDrop = (event) => {
    event.preventDefault();
    this.dropZone.classList.remove("drag-over");

    const files = event.dataTransfer?.files;

    if (files && files.length > 0) {
      this.uploadFiles(files);
    }
  };

  #handleOpenFolder = (event) => {
    event.stopPropagation();
    this.currentPath = event.detail.path;
  };

  #handleDeleteItem = async (event) => {
    event.stopPropagation();

    const { path, name } = event.detail;

    if (!confirm(`Delete "${name}"?`)) {
      return;
    }

    await this.deleteItem(path);
  };

  #handleRenameItem = async (event) => {
    event.stopPropagation();

    const { path, name } = event.detail;
    const newName = prompt("New name:", name);

    if (!newName || newName === name) {
      return;
    }

    await this.renameItem(path, newName);
  };

  #handleMoveItem = async (event) => {
    event.stopPropagation();

    const { path } = event.detail;
    const destinationPath = prompt("Move to folder path:");

    if (!destinationPath) {
      return;
    }

    await this.moveItem(path, destinationPath);
  };
}


class FileExplorerItemBase extends HTMLElement {
  constructor() {
    super();

    this.attachShadow({ mode: "open" });

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
        }

        .item {
          position: relative;
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
          border: 1px solid #dee2e6;
          border-radius: 0.5rem;
          padding: 0.75rem;
          background: #fff;
          min-height: 132px;
          cursor: default;
        }

        .item:hover {
          background: #f8f9fa;
        }

        .main {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 0.5rem;
          flex: 1;
          text-align: center;
          min-width: 0;
        }

        .icon {
          font-size: 2rem;
          line-height: 1;
        }

        .name {
          max-width: 100%;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          font-size: 0.925rem;
        }

        .meta {
          color: #6c757d;
          font-size: 0.775rem;
          text-align: center;
        }

        .actions {
          display: flex;
          justify-content: center;
          flex-wrap: wrap;
          gap: 0.25rem;
        }

        button,
        a {
          font: inherit;
        }

        .action {
          border: 1px solid #ced4da;
          border-radius: 0.25rem;
          background: #fff;
          color: #212529;
          padding: 0.2rem 0.35rem;
          cursor: pointer;
          text-decoration: none;
          font-size: 0.8rem;
        }

        .action:hover {
          background: #f8f9fa;
        }

        .danger {
          color: #dc3545;
          border-color: #dc3545;
        }

        .primary {
          color: #0d6efd;
          border-color: #0d6efd;
        }
      </style>

      <div class="item">
        <div class="main">
          <i class="icon"></i>
          <div class="name"></div>
          <div class="meta"></div>
        </div>

        <div class="actions"></div>
      </div>
    `;

    this._item = null;
  }

  connectedCallback() {
    this.render();
  }

  set item(value) {
    this._item = value;
    this.render();
  }

  get item() {
    return this._item || {};
  }

  set root(value) {
    this.setAttribute("root", value || "");
  }

  get root() {
    return this.getAttribute("root") || "";
  }

  set currentPath(value) {
    this.setAttribute("current-path", value || "");
  }

  get currentPath() {
    return this.getAttribute("current-path") || "";
  }

  get iconElement() {
    return this.shadowRoot.querySelector(".icon");
  }

  get nameElement() {
    return this.shadowRoot.querySelector(".name");
  }

  get metaElement() {
    return this.shadowRoot.querySelector(".meta");
  }

  get actionsElement() {
    return this.shadowRoot.querySelector(".actions");
  }

  render() {
    if (!this.isConnected || !this._item) {
      return;
    }

    this.iconElement.className = `icon bi ${this.getIconClass()}`;
    this.nameElement.textContent = this.item.name || "";
    this.nameElement.title = this.item.name || "";

    this.metaElement.textContent = this.getMetaText();

    this.actionsElement.innerHTML = "";
    this.renderActions();
  }

  renderActions() {
    this.actionsElement.appendChild(
      this.createActionButton({
        label: "Rename",
        icon: "bi-pencil",
        className: "action",
        onClick: () => this.emitRename()
      })
    );

    this.actionsElement.appendChild(
      this.createActionButton({
        label: "Move",
        icon: "bi-arrows-move",
        className: "action",
        onClick: () => this.emitMove()
      })
    );

    this.actionsElement.appendChild(
      this.createActionButton({
        label: "Delete",
        icon: "bi-trash",
        className: "action danger",
        onClick: () => this.emitDelete()
      })
    );
  }

  createActionButton({ label, icon, className, onClick }) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = className || "action";
    button.title = label;
    button.innerHTML = `<i class="bi ${icon}"></i>`;
    button.addEventListener("click", onClick);
    return button;
  }

  createActionLink({ label, icon, href, className }) {
    const link = document.createElement("a");
    link.className = className || "action";
    link.title = label;
    link.href = href;
    link.innerHTML = `<i class="bi ${icon}"></i>`;
    return link;
  }

  getMetaText() {
    const parts = [];

    if (this.item.size) {
      parts.push(this.item.size);
    }

    if (this.item.modified) {
      parts.push(this.item.modified);
    }

    return parts.join(" · ");
  }

  getIconClass() {
    return "bi-file-earmark";
  }

  emitRename() {
    this.#emit("file-explorer-rename", {
      path: this.item.path,
      name: this.item.name,
      type: this.item.type
    });
  }

  emitMove() {
    this.#emit("file-explorer-move", {
      path: this.item.path,
      name: this.item.name,
      type: this.item.type
    });
  }

  emitDelete() {
    this.#emit("file-explorer-delete", {
      path: this.item.path,
      name: this.item.name,
      type: this.item.type
    });
  }

  #emit(name, detail = {}) {
    this.dispatchEvent(
      new CustomEvent(name, {
        bubbles: true,
        composed: true,
        detail
      })
    );
  }
}


class FileExplorerFolder extends FileExplorerItemBase {
  connectedCallback() {
    super.connectedCallback();

    this.shadowRoot.querySelector(".main").addEventListener("dblclick", () => {
      this.open();
    });
  }

  renderActions() {
    this.actionsElement.appendChild(
      this.createActionButton({
        label: "Open",
        icon: "bi-folder2-open",
        className: "action primary",
        onClick: () => this.open()
      })
    );

    super.renderActions();
  }

  open() {
    this.dispatchEvent(
      new CustomEvent("file-explorer-open-folder", {
        bubbles: true,
        composed: true,
        detail: {
          path: this.item.path,
          name: this.item.name
        }
      })
    );
  }

  getIconClass() {
    return "bi-folder-fill";
  }
}


class FileExplorerFile extends FileExplorerItemBase {
  renderActions() {
    if (this.item.url) {
      this.actionsElement.appendChild(
        this.createActionLink({
          label: "Open",
          icon: "bi-eye",
          href: this.item.url,
          className: "action primary"
        })
      );
    }

    if (this.item.download_url) {
      this.actionsElement.appendChild(
        this.createActionLink({
          label: "Download",
          icon: "bi-download",
          href: this.item.download_url,
          className: "action"
        })
      );
    }

    super.renderActions();
  }

  getIconClass() {
    const extension = this.#getExtension();

    if (["png", "jpg", "jpeg", "gif", "webp", "svg", "bmp", "tiff"].includes(extension)) {
      return "bi-file-earmark-image";
    }

    if (extension === "pdf") {
      return "bi-file-earmark-pdf";
    }

    if (["doc", "docx", "odt", "rtf"].includes(extension)) {
      return "bi-file-earmark-word";
    }

    if (["xls", "xlsx", "ods", "csv"].includes(extension)) {
      return "bi-file-earmark-spreadsheet";
    }

    if (["ppt", "pptx", "odp"].includes(extension)) {
      return "bi-file-earmark-slides";
    }

    if (["zip", "rar", "7z", "tar", "gz"].includes(extension)) {
      return "bi-file-earmark-zip";
    }

    if (["py", "js", "ts", "html", "css", "java", "c", "cpp", "cs", "json", "xml", "yaml", "yml", "sql"].includes(extension)) {
      return "bi-file-earmark-code";
    }

    if (["mp4", "mov", "avi", "mkv", "webm"].includes(extension)) {
      return "bi-file-earmark-play";
    }

    if (["mp3", "wav", "ogg", "flac"].includes(extension)) {
      return "bi-file-earmark-music";
    }

    if (["txt", "md", "log"].includes(extension)) {
      return "bi-file-earmark-text";
    }

    return "bi-file-earmark";
  }

  #getExtension() {
    if (this.item.extension) {
      return String(this.item.extension).toLowerCase();
    }

    const name = this.item.name || "";
    const parts = name.split(".");

    if (parts.length < 2) {
      return "";
    }

    return parts.pop().toLowerCase();
  }
}

customElements.define("file-explorer", FileExplorer);
customElements.define("file-explorer-folder", FileExplorerFolder);
customElements.define("file-explorer-file", FileExplorerFile);
