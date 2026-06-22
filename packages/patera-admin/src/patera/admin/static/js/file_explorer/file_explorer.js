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

    this._currentPath = "";
    this._items = [];
    this._selectedPaths = new Set();
    this._lastSelectedIndex = null;
    this._initialized = false;
  }

  connectedCallback() {
    if (!this._initialized) {
      this.#renderShell();
      this._initialized = true;
    }

    this._currentPath = this.getAttribute("path") || "";

    this.refreshButton.addEventListener("click", this.#handleRefreshClick);
    this.uploadButton.addEventListener("click", this.#handleUploadClick);
    this.renameButton.addEventListener("click", this.#handleRenameSelectedClick);
    this.deleteButton.addEventListener("click", this.#handleDeleteSelectedClick);
    this.fileInput.addEventListener("change", this.#handleFileInputChange);

    this.dropZone.addEventListener("dragenter", this.#handleDragEnter);
    this.dropZone.addEventListener("dragover", this.#handleDragOver);
    this.dropZone.addEventListener("dragleave", this.#handleDragLeave);
    this.dropZone.addEventListener("drop", this.#handleUploadDrop);

    this.addEventListener("file-explorer-item-selected", this.#handleItemSelected);
    this.addEventListener("file-explorer-open-folder", this.#handleOpenFolder);
    this.addEventListener("file-explorer-move-to-folder", this.#handleMoveToFolder);
    this.dropZone.addEventListener("click", this.#handleEmptySpaceClick);

    this.load();
  }

  disconnectedCallback() {
    this.refreshButton?.removeEventListener("click", this.#handleRefreshClick);
    this.uploadButton?.removeEventListener("click", this.#handleUploadClick);
    this.renameButton?.removeEventListener("click", this.#handleRenameSelectedClick);
    this.deleteButton?.removeEventListener("click", this.#handleDeleteSelectedClick);
    this.fileInput?.removeEventListener("change", this.#handleFileInputChange);

    this.dropZone?.removeEventListener("dragenter", this.#handleDragEnter);
    this.dropZone?.removeEventListener("dragover", this.#handleDragOver);
    this.dropZone?.removeEventListener("dragleave", this.#handleDragLeave);
    this.dropZone?.removeEventListener("drop", this.#handleUploadDrop);
    this.dropZone?.removeEventListener("click", this.#handleEmptySpaceClick);

    this.removeEventListener("file-explorer-item-selected", this.#handleItemSelected);
    this.removeEventListener("file-explorer-open-folder", this.#handleOpenFolder);
    this.removeEventListener("file-explorer-move-to-folder", this.#handleMoveToFolder);
  }

  attributeChangedCallback(name, oldValue, newValue) {
    if (oldValue === newValue) {
      return;
    }

    if (name === "path") {
      this._currentPath = newValue || "";

      if (this.isConnected && this._initialized) {
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

  get selectedPaths() {
    return Array.from(this._selectedPaths);
  }

  get refreshButton() {
    return this.querySelector("#file-explorer-refresh-btn");
  }

  get uploadButton() {
    return this.querySelector("#file-explorer-upload-btn");
  }

  get renameButton() {
    return this.querySelector("#file-explorer-rename-btn");
  }

  get deleteButton() {
    return this.querySelector("#file-explorer-delete-btn");
  }

  get fileInput() {
    return this.querySelector("#file-explorer-file-input");
  }

  get breadcrumbsElement() {
    return this.querySelector(".file-explorer-breadcrumbs");
  }

  get dropZone() {
    return this.querySelector(".file-explorer-drop-zone");
  }

  get itemsElement() {
    return this.querySelector(".file-explorer-items");
  }

  get loadingElement() {
    return this.querySelector(".file-explorer-loading");
  }

  get errorElement() {
    return this.querySelector(".file-explorer-error");
  }

  get emptyElement() {
    return this.querySelector(".file-explorer-empty");
  }

  get selectedCountElement() {
    return this.querySelector(".file-explorer-selected-count");
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
      const data = payload.data || payload;

      this._currentPath = this.#normalizePath(
        data.path ?? data.current_relative_path ?? this.currentPath
      );

      this._items = Array.isArray(data.items) ? data.items : [];
      this.#clearSelection();
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

  async deleteItems(paths) {
    if (!this.deleteUrl) {
      this.#showError("Missing delete-url attribute.");
      return;
    }

    const selectedPaths = Array.from(paths || []);

    if (selectedPaths.length === 0) {
      return;
    }

    const formData = new FormData();
    formData.append("root", this.root);

    for (const path of selectedPaths) {
      formData.append("paths", path);
      formData.append("files", path);
    }

    await this.#postFormAndReload(this.deleteUrl, formData, "Delete failed.");

    this.#emit("file-explorer-deleted", {
      paths: selectedPaths
    });
  }

  async moveItems(paths, destinationPath) {
    if (!this.moveUrl) {
      this.#showError("Missing move-url attribute.");
      return;
    }

    const selectedPaths = Array.from(paths || []);

    if (selectedPaths.length === 0 || !destinationPath) {
      return;
    }

    const formData = new FormData();
    formData.append("root", this.root);
    formData.append("destination_path", destinationPath);

    for (const path of selectedPaths) {
      formData.append("paths", path);
      formData.append("files", path);
    }

    await this.#postFormAndReload(this.moveUrl, formData, "Move failed.");

    this.#emit("file-explorer-moved", {
      paths: selectedPaths,
      destinationPath
    });
  }

  #renderShell() {
    this.classList.add("file-explorer-element");

    this.innerHTML = `
      <div class="file-explorer border rounded bg-white overflow-hidden">
        <div class="file-explorer-header d-flex flex-column flex-lg-row justify-content-between align-items-lg-center gap-3 p-3 border-bottom bg-light">
          <div class="d-flex align-items-center gap-2 fw-semibold">
            <i class="bi bi-folder2-open"></i>
            <span>File Explorer</span>
          </div>

          <div class="file-explorer-controls d-flex align-items-center flex-wrap gap-2">
            <button type="button" class="btn btn-outline-secondary btn-sm" id="file-explorer-refresh-btn">
              <i class="bi bi-arrow-clockwise me-1"></i>
              Refresh
            </button>

            <button type="button" class="btn btn-outline-secondary btn-sm" id="file-explorer-rename-btn" disabled>
              <i class="bi bi-pencil me-1"></i>
              Rename
            </button>

            <button type="button" class="btn btn-outline-danger btn-sm" id="file-explorer-delete-btn" disabled>
              <i class="bi bi-trash me-1"></i>
              Delete
            </button>

            <button type="button" class="btn btn-primary btn-sm" id="file-explorer-upload-btn">
              <i class="bi bi-upload me-1"></i>
              Upload
            </button>

            <input id="file-explorer-file-input" type="file" multiple class="d-none">
          </div>
        </div>

        <div class="file-explorer-toolbar d-flex flex-column flex-md-row justify-content-between align-items-md-center gap-2 px-3 py-2 border-bottom bg-white">
          <nav class="file-explorer-breadcrumbs d-flex align-items-center flex-wrap gap-1 small"></nav>

          <div class="file-explorer-selected-count text-muted small">
            0 selected
          </div>
        </div>

        <div class="file-explorer-drop-zone p-3">
          <div class="file-explorer-loading text-center text-muted py-5 d-none">
            <div class="spinner-border spinner-border-sm me-1" aria-hidden="true"></div>
            Loading...
          </div>

          <div class="file-explorer-error alert alert-danger d-none mb-3"></div>

          <div class="file-explorer-empty text-center text-muted py-5 d-none">
            <i class="bi bi-folder-x fs-1 d-block mb-2"></i>
            <div class="fw-semibold">This folder is empty.</div>
          </div>

          <div class="file-explorer-items"></div>
        </div>
      </div>
    `;
  }

  #render() {
    this.#renderBreadcrumbs();
    this.#renderItems();
    this.#syncSelectionUi();
  }

  #renderBreadcrumbs() {
    const breadcrumbs = this.#getBreadcrumbs();

    this.breadcrumbsElement.innerHTML = "";

    breadcrumbs.forEach((breadcrumb, index) => {
      if (index > 0) {
        const separator = document.createElement("span");
        separator.className = "text-muted";
        separator.textContent = "/";
        this.breadcrumbsElement.appendChild(separator);
      }

      const button = document.createElement("button");
      button.type = "button";
      button.className = "btn btn-link btn-sm p-0 text-decoration-none";
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
      .filter((item) => item.type === "folder" || item.is_folder === true)
      .sort((a, b) => a.name.localeCompare(b.name));

    const files = this._items
      .filter((item) => item.type !== "folder" && item.is_folder !== true)
      .sort((a, b) => a.name.localeCompare(b.name));

    const sortedItems = [...folders, ...files];

    this.emptyElement.classList.toggle("d-none", sortedItems.length > 0);
    this.itemsElement.className = "file-explorer-items d-flex flex-wrap align-content-start gap-2";

    sortedItems.forEach((item, index) => {
      const element = item.type === "folder" || item.is_folder === true
        ? document.createElement("file-explorer-folder")
        : document.createElement("file-explorer-file");

      element.item = item;
      element.index = index;
      element.root = this.root;
      element.currentPath = this.currentPath;
      element.selected = this._selectedPaths.has(item.path);

      this.itemsElement.appendChild(element);
    });
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

  #selectSingle(path, index) {
    this._selectedPaths.clear();
    this._selectedPaths.add(path);
    this._lastSelectedIndex = index;
    this.#syncSelectionUi();
  }

  #toggleSelection(path, index) {
    if (this._selectedPaths.has(path)) {
      this._selectedPaths.delete(path);
    } else {
      this._selectedPaths.add(path);
    }

    this._lastSelectedIndex = index;
    this.#syncSelectionUi();
  }

  #selectRange(index) {
    if (this._lastSelectedIndex === null) {
      const item = this.#itemAt(index);

      if (item) {
        this.#selectSingle(item.path, index);
      }

      return;
    }

    const start = Math.min(this._lastSelectedIndex, index);
    const end = Math.max(this._lastSelectedIndex, index);

    this._selectedPaths.clear();

    for (let i = start; i <= end; i += 1) {
      const item = this.#itemAt(i);

      if (item) {
        this._selectedPaths.add(item.path);
      }
    }

    this.#syncSelectionUi();
  }

  #clearSelection() {
    this._selectedPaths.clear();
    this._lastSelectedIndex = null;
    this.#syncSelectionUi();
  }

  #syncSelectionUi() {
    const selectedCount = this._selectedPaths.size;

    this.renameButton.disabled = selectedCount !== 1;
    this.deleteButton.disabled = selectedCount < 1;

    if (this.selectedCountElement) {
      this.selectedCountElement.textContent =
        selectedCount === 1
          ? "1 selected"
          : `${selectedCount} selected`;
    }

    this.querySelectorAll("file-explorer-file, file-explorer-folder").forEach((element) => {
      element.selected = this._selectedPaths.has(element.item.path);
    });
  }

  #itemAt(index) {
    const elements = Array.from(
      this.querySelectorAll("file-explorer-folder, file-explorer-file")
    );

    const element = elements[index];

    return element?.item || null;
  }

  #getSelectedItems() {
    return this._items.filter((item) => this._selectedPaths.has(item.path));
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
    this.loadingElement.classList.toggle("d-none", !isLoading);
  }

  #showError(message) {
    this.errorElement.textContent = message;
    this.errorElement.classList.remove("d-none");
  }

  #clearError() {
    this.errorElement.textContent = "";
    this.errorElement.classList.add("d-none");
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

  #handleRenameSelectedClick = async () => {
    const selectedItems = this.#getSelectedItems();

    if (selectedItems.length !== 1) {
      return;
    }

    const selectedItem = selectedItems[0];
    const newName = prompt("New name:", selectedItem.name);

    if (!newName || newName === selectedItem.name) {
      return;
    }

    await this.renameItem(selectedItem.path, newName);
  };

  #handleDeleteSelectedClick = async () => {
    const selectedItems = this.#getSelectedItems();

    if (selectedItems.length === 0) {
      return;
    }

    const message =
      selectedItems.length === 1
        ? `Delete "${selectedItems[0].name}"?`
        : `Delete ${selectedItems.length} selected items?`;

    if (!confirm(message)) {
      return;
    }

    await this.deleteItems(selectedItems.map((item) => item.path));
  };

  #handleFileInputChange = () => {
    this.uploadFiles(this.fileInput.files);
  };

  #handleDragEnter = (event) => {
    event.preventDefault();
    this.dropZone.classList.add("file-explorer-drag-over");
  };

  #handleDragOver = (event) => {
    event.preventDefault();
    this.dropZone.classList.add("file-explorer-drag-over");
  };

  #handleDragLeave = (event) => {
    if (!this.dropZone.contains(event.relatedTarget)) {
      this.dropZone.classList.remove("file-explorer-drag-over");
    }
  };

  #handleUploadDrop = (event) => {
    event.preventDefault();
    this.dropZone.classList.remove("file-explorer-drag-over");

    const files = event.dataTransfer?.files;

    if (files && files.length > 0) {
      this.uploadFiles(files);
    }
  };

  #handleItemSelected = (event) => {
    event.stopPropagation();

    const { path, index, ctrlKey, metaKey, shiftKey } = event.detail;

    if (shiftKey) {
      this.#selectRange(index);
      return;
    }

    if (ctrlKey || metaKey) {
      this.#toggleSelection(path, index);
      return;
    }

    this.#selectSingle(path, index);
  };

  #handleOpenFolder = (event) => {
    event.stopPropagation();
    this.currentPath = event.detail.path;
  };

  #handleMoveToFolder = async (event) => {
    event.stopPropagation();

    const destinationPath = event.detail.destinationPath;
    const draggedPaths = event.detail.paths || [];

    const pathsToMove = draggedPaths.length > 0
      ? draggedPaths
      : this.selectedPaths;

    const filteredPaths = pathsToMove.filter((path) => path !== destinationPath);

    if (filteredPaths.length === 0) {
      return;
    }

    await this.moveItems(filteredPaths, destinationPath);
  };


  #handleEmptySpaceClick = (event) => {
    const clickedItem = event.target.closest?.(
        "file-explorer-file, file-explorer-folder, .file-explorer-item-button"
    );

    if (clickedItem) {
        return;
    }

    this.#clearSelection();
};
}


class FileExplorerItemBase extends HTMLElement {
  constructor() {
    super();

    this._item = null;
    this._index = 0;
    this._selected = false;
    this._initialized = false;
  }

  connectedCallback() {
    if (!this._initialized) {
      this.#renderShell();
      this._initialized = true;
    }

    this.render();
  }

  set item(value) {
    this._item = value;
    this.render();
  }

  get item() {
    return this._item || {};
  }

  set index(value) {
    this._index = Number(value) || 0;
  }

  get index() {
    return this._index;
  }

  set selected(value) {
    this._selected = Boolean(value);
    this.#syncSelectedState();
  }

  get selected() {
    return this._selected;
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

  get itemButton() {
    return this.querySelector(".file-explorer-item-button");
  }

  get iconElement() {
    return this.querySelector(".file-explorer-item-icon");
  }

  get nameElement() {
    return this.querySelector(".file-explorer-item-name");
  }

  get metaElement() {
    return this.querySelector(".file-explorer-item-meta");
  }

  render() {
    if (!this.isConnected || !this._item || !this._initialized) {
        return;
    }

    this.iconElement.className = `file-explorer-item-icon bi ${this.getIconClass()}`;
    this.nameElement.textContent = this.item.name || "";
    this.nameElement.title = this.item.name || "";
    this.metaElement.textContent = this.getMetaText();

    this.itemButton.draggable = true;
    this.itemButton.dataset.path = this.item.path || "";
    this.itemButton.dataset.name = this.item.name || "";
    this.itemButton.dataset.type = this.item.type || "";
    this.itemButton.title = this.getTooltipText();

    this.#syncSelectedState();
    }

    getTooltipText() {
        const parts = [];

        if (this.item.name) {
            parts.push(this.item.name);
        }

        if (this.item.is_folder || this.item.type === "folder") {
            parts.push("Type: Folder");
        } else {
            parts.push("Type: File");
        }

        if (this.item.size) {
            parts.push(`Size: ${this.#formatSize(this.item.size)}`);
        }

        if (this.item.modified) {
            parts.push(`Modified: ${this.item.modified}`);
        } else if (this.item.last_modified) {
            parts.push(`Modified: ${this.#formatDate(this.item.last_modified)}`);
        }

        if (this.item.path) {
            parts.push(`Path: ${this.item.path}`);
        }

        return parts.join("\n");
    }

  getMetaText() {
    if (this.item.is_folder || this.item.type === "folder") {
      return "Folder";
    }

    const parts = [];

    if (this.item.size) {
      parts.push(this.#formatSize(this.item.size));
    }

    if (this.item.modified) {
      parts.push(this.item.modified);
    } else if (this.item.last_modified) {
      parts.push(this.#formatDate(this.item.last_modified));
    }

    return parts.join(" · ");
  }

  getIconClass() {
    return "bi-file-earmark text-muted";
  }

  #renderShell() {
    this.classList.add("file-explorer-item-element");

    this.innerHTML = `
      <button type="button" class="file-explorer-item-button">
        <span class="file-explorer-item-icon-wrap">
          <i class="file-explorer-item-icon bi bi-file-earmark text-muted"></i>
        </span>

        <span class="file-explorer-item-name text-truncate"></span>
        <span class="file-explorer-item-meta text-truncate"></span>
      </button>
    `;

    this.itemButton.addEventListener("click", this.#handleClick);
    this.itemButton.addEventListener("dblclick", this.handleDoubleClick);
    this.itemButton.addEventListener("dragstart", this.#handleDragStart);
    this.itemButton.addEventListener("dragend", this.#handleDragEnd);
  }

  #syncSelectedState() {
    if (!this._initialized) {
      return;
    }

    this.itemButton.classList.toggle("selected", this.selected);
    this.itemButton.setAttribute("aria-selected", this.selected ? "true" : "false");
  }

  #handleClick = (event) => {
    this.dispatchEvent(
      new CustomEvent("file-explorer-item-selected", {
        bubbles: true,
        composed: true,
        detail: {
          path: this.item.path,
          name: this.item.name,
          type: this.item.type,
          index: this.index,
          ctrlKey: event.ctrlKey,
          metaKey: event.metaKey,
          shiftKey: event.shiftKey
        }
      })
    );
  };

  handleDoubleClick = () => {
    // Files do nothing by default. Folders override this.
  };

  #handleDragStart = (event) => {
    const explorer = this.closest("file-explorer");
    const selectedPaths = explorer?.selectedPaths || [];
    const paths = selectedPaths.includes(this.item.path)
      ? selectedPaths
      : [this.item.path];

    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData(
      "application/x-file-explorer-paths",
      JSON.stringify(paths)
    );
    event.dataTransfer.setData("text/plain", paths.join("\n"));

    this.itemButton.classList.add("dragging");
  };

  #handleDragEnd = () => {
    this.itemButton.classList.remove("dragging");
  };

  #formatSize(size) {
    const numericSize = Number(size);

    if (Number.isNaN(numericSize)) {
      return String(size);
    }

    if (numericSize < 1024) {
      return `${numericSize} B`;
    }

    if (numericSize < 1024 * 1024) {
      return `${(numericSize / 1024).toFixed(1)} KB`;
    }

    if (numericSize < 1024 * 1024 * 1024) {
      return `${(numericSize / 1024 / 1024).toFixed(1)} MB`;
    }

    return `${(numericSize / 1024 / 1024 / 1024).toFixed(1)} GB`;
  }

  #formatDate(timestamp) {
    const numericTimestamp = Number(timestamp);

    if (Number.isNaN(numericTimestamp)) {
      return String(timestamp);
    }

    return new Date(numericTimestamp * 1000).toLocaleString();
  }
}


class FileExplorerFolder extends FileExplorerItemBase {
  getIconClass() {
    return "bi-folder-fill text-warning";
  }

  connectedCallback() {
    super.connectedCallback();

    this.itemButton.addEventListener("dragenter", this.#handleFolderDragEnter);
    this.itemButton.addEventListener("dragover", this.#handleFolderDragOver);
    this.itemButton.addEventListener("dragleave", this.#handleFolderDragLeave);
    this.itemButton.addEventListener("drop", this.#handleFolderDrop);
  }

  handleDoubleClick = () => {
    this.open();};

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

  #handleFolderDragEnter = (event) => {
    event.preventDefault();
    this.itemButton.classList.add("drop-target");
  };

  #handleFolderDragOver = (event) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    this.itemButton.classList.add("drop-target");
  };

  #handleFolderDragLeave = () => {
    this.itemButton.classList.remove("drop-target");
  };

  #handleFolderDrop = (event) => {
    event.preventDefault();
    event.stopPropagation();

    this.itemButton.classList.remove("drop-target");

    const rawPaths = event.dataTransfer.getData("application/x-file-explorer-paths");

    if (!rawPaths) {
      return;
    }

    let paths = [];

    try {
      paths = JSON.parse(rawPaths);
    } catch {
      paths = [];
    }

    this.dispatchEvent(
      new CustomEvent("file-explorer-move-to-folder", {
        bubbles: true,
        composed: true,
        detail: {
          destinationPath: this.item.path,
          paths
        }
      })
    );
  };
}


class FileExplorerFile extends FileExplorerItemBase {
  getIconClass() {
    const extension = this.#getExtension();

    if (["png", "jpg", "jpeg", "gif", "webp", "svg", "bmp", "tiff"].includes(extension)) {
      return "bi-file-earmark-image text-success";
    }

    if (extension === "pdf") {
      return "bi-file-earmark-pdf text-danger";
    }

    if (["doc", "docx", "odt", "rtf"].includes(extension)) {
      return "bi-file-earmark-word text-primary";
    }

    if (["xls", "xlsx", "ods", "csv"].includes(extension)) {
      return "bi-file-earmark-spreadsheet text-success";
    }

    if (["ppt", "pptx", "odp"].includes(extension)) {
      return "bi-file-earmark-slides text-warning";
    }

    if (["zip", "rar", "7z", "tar", "gz"].includes(extension)) {
      return "bi-file-earmark-zip text-secondary";
    }

    if (["py", "js", "ts", "html", "css", "java", "c", "cpp", "cs", "json", "xml", "yaml", "yml", "sql"].includes(extension)) {
      return "bi-file-earmark-code text-info";
    }

    if (["mp4", "mov", "avi", "mkv", "webm"].includes(extension)) {
      return "bi-file-earmark-play text-danger";
    }

    if (["mp3", "wav", "ogg", "flac"].includes(extension)) {
      return "bi-file-earmark-music text-primary";
    }

    if (["txt", "md", "log"].includes(extension)) {
      return "bi-file-earmark-text text-secondary";
    }

    return "bi-file-earmark text-muted";
  }

  #getExtension() {
    if (this.item.extension) {
      return String(this.item.extension).toLowerCase();
    }

    if (this.item.ext) {
      return String(this.item.ext).replace(".", "").toLowerCase();
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
