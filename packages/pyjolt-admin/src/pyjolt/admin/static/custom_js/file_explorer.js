/**
 * File explorer
 */

class FileExplorer extends HTMLElement{

    constructor(){
        super();
    }

    async connectedCallback(){
        this.ctrlDown = false;
        this.insertAdjacentHTML("afterbegin", this.markup());
        this.deleteDialog = this.querySelector(".delete-dialog");
        this.selectedFiles = null;
        this.activate();
        await this.getFiles();
    }

    async getFiles(){
        let response = await fetch(`${this.baseFilesUrl}?path=${this.currentFolder}`);
        if(!response.ok){
            this.filesContainer.innerHTML = this.errorMarkup();
            return;
        }
        response = await response.json()
        this.files = response.data;
    }

    async rerender(){
        this.innerHTML = "";
        this.insertAdjacentHTML("afterbegin", this.markup());
        this.deleteDialog = this.querySelector(".delete-dialog");
        this.selectedFiles = null;
        this.activate();
        await this.getFiles();
    }

    activate(){
        let dragDepth = 0;

        this.uploadFilesBtn.addEventListener("click", (e) => {
            this.uploadFilesBtn.blur();
            this.uploadInput.click();
        })

        this.uploadInput.addEventListener("change", async (e) => {
            if(this.uploadInput.files.length == 0){
                return;
            }
            const num = this.uploadInput.files.lentgh;
            let index = 1;
            for(const file of this.uploadInput.files){
                await this.uploadFile(file, this.currentFolder+"/"+file.name, num, index);
                index++;
            }
            this.rerender();
        })

        // Needed for drop to be allowed in most browsers
        this.filesContainer.addEventListener("dragover", (e) => {
            if ([...e.dataTransfer.items].some(i => i.kind === "file")) {
            e.preventDefault();
            e.dataTransfer.dropEffect = "copy";
            }
        });

        this.filesContainer.addEventListener("dragenter", (e) => {
            if (![...e.dataTransfer.items].some(i => i.kind === "file")) return;
            e.preventDefault();
            dragDepth++;
            this.setDragUI(true);
        });

        this.filesContainer.addEventListener("dragleave", (e) => {
            e.preventDefault();
            dragDepth--;
            if (dragDepth <= 0) {
                dragDepth = 0;
                this.setDragUI(false);
            }
        });

        this.filesContainer.addEventListener("drop", (e) => this.dropHandler(e));

        this.addEventListener("file-name-change", (e) => {
            this.allFiles.forEach((el) => {
                el.classList.remove("border");
            });
            this.deleteBtn.disabled = true;
            this.downloadAllBtn.disabled = true;
        })
        document.addEventListener("keydown", (e) => {
            if(["Control"].includes(e.key)){
                this.ctrlDown = true;
            }
        })
        document.addEventListener("keyup", (e) => {
            if(["Control"].includes(e.key)){
                this.ctrlDown = false;
            }
        })
        this.addEventListener("mousedown", (e) => {
            if(e.target.closest("file-element")){
                if(!this.ctrlDown){
                    this.allFiles.forEach((el) => {
                        el.classList.remove("border");
                    })
                }
                e.target.closest("file-element").classList.add("border");
                return;
            }
            if(!e.target.closest("file-element") && !this.ctrlDown){
                this.allFiles.forEach((el) => {
                    if(el.classList.contains("border")){
                        el.classList.remove("border");
                    }
                })
            }
        })
        this.addEventListener("mouseup", (e) => {
            const clickedFiles = Array.from(this.allFiles).filter((el) => {
                return el.classList.contains("border")
            });
            this.deleteBtn.disabled = !clickedFiles.length > 0;
            this.downloadAllBtn.disabled = !clickedFiles.length > 0;
        })
        this.deleteBtn.addEventListener("mousedown", async (e) => {
            this.deleteBtn.blur();
            await this.confirmDeleteFiles(e);
        })
        this.deleteDialog.querySelector(".confirm-delete").addEventListener("click", async (e) => {
            await this.deleteFiles(e);
        })
        this.deleteDialog.querySelector(".close-delete").addEventListener("click", (e) => {
            this.deleteDialog.close();
        })
        this.downloadAllBtn.addEventListener("mousedown", async (e) => {
            const files = []
            for(const file of this.selected){
                files.push([file.name, file.path])
            }
            await this.handleZipDownload(files);
        })
        this.pathLinks.forEach((link) => {
            link.addEventListener("click", (e) => {
                this.currentFolder = link.getAttribute("data-path");
            })
        })
    }

    async handleZipDownload(files){
        let response = await fetch(this.zipDownloadUrl, {
            "method": "POST",
            body: JSON.stringify(files)
        })
        if(!response.ok){
            response = await response.json() || {message: "Something went wrong.", status: "danger"}
            setMessage(response.message, response.status)
            return;
        }
        const disposition = response.headers.get("Content-Disposition");
        let filename = "download.zip";

        if (disposition) {
            const match = disposition.match(/filename="?([^"]+)"?/);
            if (match) {
                filename = match[1];
            }
        }
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
    }

    async confirmDeleteFiles(e){
        this.selectedFiles = this.selected;
        if(!this.selectedFiles || this.selectedFiles?.length == 0){
            this.selectedFiles = null;
            return;
        }
        this.deleteDialog.showModal();
    }

    async deleteFiles(e){
        let index = 1;
        for(const sel of this.selectedFiles){
            let response = await fetch(`${this.deleteUrl}?path=${this.currentFolder}/${sel.name}`, {
                method: "DELETE"
            });
            if(!response.ok){
                setMessage(`Failed to delete file/folder ${sel.name}`);
            }
            this.updateProgress(parseInt((index/this.selectedFiles.length)*100));
        }
        this.selectedFiles = null;
        this.deleteDialog.close();
        this.rerender();
    }

    setDragUI = (on) => {
        this.filesContainer.classList.toggle("opacity-50", on);
        this.filesContainer.classList.toggle("border", on);
        this.filesContainer.classList.toggle("border-dashed", on);
        this.filesContainer.classList.toggle("border-4", on);
        this.filesContainer.classList.toggle("border-primary", on);
        this.filesContainer.classList.toggle("rounded", on);
        this.filesContainer.classList.toggle("bg-light", on);
    };

    async dropHandler(e) {
        e.preventDefault();
        this.setDragUI(false);

        const items = [...e.dataTransfer.items].filter(i => i.kind === "file");
        const entries = items
            .map(i => i.webkitGetAsEntry?.())
            .filter(Boolean);

        const out = [];
        for (const entry of entries) {
            await this.#walkEntry(entry, "", out);
        }

        let index = 1;
        const num = out.length;
        this.updateProgress(0);
        for (const { file, relativePath } of out) {
            await this.uploadFile(file, this.currentFolder + "/" + relativePath, num, index);
            index++;
        }
        this.rerender();
    }

    async uploadFile(file, path, num, index){
        const formData = new FormData()
        formData.set("path", path);
        formData.set("file", file);
        let response = await fetch(this.uploadUrl, {
            method: "POST",
            body: formData
        });
        if(!response.ok){
            response = await response.json() || {message: `Failed to upload file ${file.name}`, status: "danger"}
            setMessage(response.message, response.status);
        }
        this.updateProgress(parseInt((index/num)*100));
    }

    #walkEntry(entry, basePath, out) {
        return new Promise((resolve) => {
            if (entry.isFile) {
            entry.file((file) => {
                const relativePath = basePath + file.name;
                out.push({ file, relativePath });
                resolve();
            }, () => resolve());
            return;
            }

            if (entry.isDirectory) {
            const dirReader = entry.createReader();
            const dirPath = basePath + entry.name + "/";

            const readBatch = () => {
                dirReader.readEntries(async (entries) => {
                if (!entries.length) return resolve();
                for (const child of entries) {
                    await this.#walkEntry(child, dirPath, out);
                }
                readBatch();
                }, () => resolve());
            };

            readBatch();
            return;
            }

            resolve();
        });
    }

    noFilesMarkup(){
        return `
            <div class="text-center m-2">No files or folders...</div>
        `
    }

    errorMarkup(){
        return `
            <div class="text-center text-danger m-2">Something went wrong...</div>
        `
    }

    fileMarkup(file){
        return `
            <file-element data-is-folder="${file.is_folder}" data-mimetype="${file.mimetype}" data-file-name="${file.name}" data-file-path="${file.path}"></file-element>
        `
    }

    pathLinksParts(parts){
        let current = "";
        return parts.map(part => {
            current += `/${part}`;
            return current;
        });
    }

    pathLinksMarkup(parts, paths){
        let markup = "";
        paths.forEach((path, i) => {
            markup+=`<span class="path-link text-muted" role="button" data-path="${path}">${"/"+parts[i]}</span>`
        })
        return markup;
    }

    markup(){
        let parts = this.currentFolder;
        if(parts.startsWith("/")){
            parts = parts.substring(1);
        }
        parts = parts.split("/")
        return `
        <main class="card" aria-label="File explorer">
            <div class="card-header">
                <h2 class="title mb-0">File explorer</h2>
                <p class="text-muted">${this.pathLinksMarkup(parts, this.pathLinksParts(parts))}</p>
            </div>

            <div class="card-body">
                <div class="p-1">
                    <button type="button" class="btn btn-sm btn-secondary delete-btn" title="Delete files" disabled>
                        Delete <i class="fa-solid fa-trash"></i>
                    </button>
                    <button type="button" class="btn btn-sm btn-primary download-all-btn" title="Download all files" disabled>
                        Download <i class="fa-solid fa-download"></i>
                    </button>
                    <button type="button" class="btn btn-sm btn-primary upload-files-btn" title="Upload files">
                        Upload <i class="fa-solid fa-upload"></i>
                    </button>
                </div>
                <div class="progress" role="progressbar" hidden aria-label="Upload progress" aria-valuenow="87" aria-valuemin="0" aria-valuemax="100">
                    <div class="progress-bar progress-bar-striped progress-bar-animated" style="width: 87%"></div>
                </div>
                <div class="d-flex flex-wrap gap-4 p-2 files-container">
                    <div class="spinner-border" role="status">
                        <span class="visually-hidden">Loading...</span>
                    </div>
                </div>
                <input type="file" multiple hidden />
            </div>
            <dialog class="delete-dialog">
                <p>Are you sure you wish to delete the selected file(s)?</p>
                <div>
                    <button type="button" class="btn btn-sm btn-danger m-1 confirm-delete">Delete</button>
                    <button type="button" class="btn btn-sm btn-primary m-1 close-delete">Close</button>
                </div>
            </dialog>
        </main>`
    }

    updateProgress(perc){
        this.progress.hidden = false;
        this.progress.setAttribute("aria-valuenow", perc);
        this.progressBar.style.width = `${perc}%`;
        this.progressBar.innerHTML = `${perc}%`;
    }

    resetProgressBar(){
        this.progress.setAttribute("aria-valuenow", 0);
        this.progressBar.style.width = `${0}%`;
        this.progress.hidden = true;
        this.progressBar.innerHTML = "";
    }

    get selected(){
        return this.querySelectorAll("file-element.border");
    }

    get deleteUrl(){
        return this.getAttribute("data-delete-url");
    }

    get currentFolder(){
        return this.getAttribute("data-current-folder");
    }

    set currentFolder(folder_path){
        this.setAttribute("data-current-folder", folder_path);
        this.rerender();
    }

    get baseFilesUrl(){
        return this.getAttribute("data-base-files-url");
    }

    get fetchFileUrl(){
        return this.getAttribute("data-base-single-file-url");
    }

    get renameUrl(){
        return this.getAttribute("data-rename-url");
    }

    get pathLinks(){
        return this.querySelectorAll(".path-link");
    }

    get allFiles(){
        return this.querySelectorAll("file-element");
    }

    get uploadInput(){
        return this.querySelector('input[type="file"]')
    }

    get uploadUrl(){
        return this.getAttribute("data-upload-url");
    }

    get uploadFilesBtn(){
        return this.querySelector(".upload-files-btn");
    }

    get deleteBtn(){
        return this.querySelector(".delete-btn");
    }

    get downloadAllBtn(){
        return this.querySelector(".download-all-btn");
    }

    get filesContainer(){
        return this.querySelector(".files-container");
    }

    get progress(){
        return this.querySelector(".progress");
    }

    get progressBar(){
        return this.querySelector(".progress-bar");
    }

    get zipDownloadUrl(){
        return this.getAttribute("data-zip-file-url");
    }

    set files(files){
        if(files.length == 0){
            this.filesContainer.innerHTML = this.noFilesMarkup();
            return;
        }
        this.filesContainer.innerHTML = files.map(file => {return this.fileMarkup(file)}).join("");
    }

    get files(){
        return Array.from(this.allFiles).map((file) => {
            return {
                isFolder: file.isFolder,
                name: file.name,
                path: file.path
            }
        })
    }


}

export default FileExplorer;
