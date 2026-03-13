/**
 * File picker for picking files from static assets
 */

class FilePicker extends HTMLElement{

    constructor(){
        super();
    }

    async connectedCallback(){
        this.ctrlDown = false;
        this.insertAdjacentHTML("afterbegin", this.markup());
        this.activate();
        this.multiple = this.hasAttribute("multiple");
        this.asString = this.hasAttribute("as-string");
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
        <style>
            .files-container{
                display: flex;
                flex-wrap: wrap;
                align-items: flex-start;
                gap: .5rem;
            }

            .file{
                display: inline-flex;
                align-items: center;
                gap: .35rem;

                white-space: nowrap;
                max-width: 100%;
                overflow: hidden;
                text-overflow: ellipsis;

                border-radius: .375rem;
                padding: .25rem .5rem;
            }

            .file.border{
                border-width: 1px;
            }
        </style>
        <div>
            <div>
                <button type="button" ${this.multiple ? 'title="You can select multiple files."' : ''}
                    class="select-btn btn btn-sm border">
                    <i class="fa-solid fa-paperclip"></i>
                    Select file${this.multiple ? "s" : ""}
                </button>
            </div>

            <div class="selected-files"></div>

            <dialog style="width: ${this.getAttribute("data-width") || '60%'};">
                <div class="border-bottom mb-1">
                    <span class="text-muted current-path">
                        ${this.pathLinksMarkup(parts, this.pathLinksParts(parts))}
                    </span>
                    <span class="float-end">
                        <button type="button" class="btn btn-sm close-select-btn">
                            <i class="fa-solid fa-xmark"></i>
                        </button>
                    </span>
                </div>

                <div class="files-container p-1"></div>

                <div class="text-end">
                    <button class="btn btn-sm btn-primary mx-1 confirm-btn" type="button">Ok</button>
                    <button class="btn btn-sm btn-secondary mx-1 close-select-btn" type="button">Cancel</button>
                </div>
            </dialog>
        </div>`
    }

    rerender(){
        this.getFiles();
    }

    selectedFile(fileName, path){
        return `
            <span data-path="${path}" data-name="${fileName}" class="mx-1 border rounded p-1">${fileName}</span>
        `
    }

    activate(){
        this.selectBtn.addEventListener("click", async (e) => {
            this.openSelectModal();
        });
        this.closeSelectBtn.forEach(btn => {
            btn.addEventListener("click", (e) => {
                btn.blur();
                this.dialog.close();
            })
        })
        this.confirmSelectBtn.addEventListener("click", (e) => {
            this.selectedFiles.innerHTML = "";
            const selectedFiles = []
            this.dialog.querySelectorAll(".border").forEach(file => {
                let path = file.getAttribute("data-path");
                path = path.replaceAll("\"", "/");
                if(!path.endsWith("/")){
                    path = path + "/";
                }
                path = path + file.getAttribute("data-name");
                selectedFiles.push(path);
            })
            this.selectedFiles.innerHTML = selectedFiles.map(sel => {
                return this.selectedFileMarkup(sel);
            });
            this.activateSelectedFiles();
            this.dialog.close();
        })

    }

    activateSelectedFiles(){
        this.querySelectorAll(".remove-file").forEach(sel => {
            sel.addEventListener("click", (e) => {
                sel.closest("small")?.remove();
            })
        })
    }

    selectedFileMarkup(sel){
        return `<small class="d-block selected-file my-1" data-path="${sel}">${sel} <span class="remove-file" role="button"><i class="fa-solid fa-xmark"></i></span></small>`
    }

    activateFiles(){
        this.querySelectorAll(".file").forEach(file => {
            if(["true", true, "1", "is-folder"].includes(file.getAttribute("data-is-folder"))){
                file.addEventListener("dblclick", (e) => {
                    e.preventDefault();
                    this.handleFolderDblClick(file);
                })
            }else{
                file.addEventListener("click", (e) => {
                    this.handleFileClick(file);
                })
            }
        })
    }

    handleFolderDblClick(file){
        let currentFolder = this.currentFolder;
        currentFolder = currentFolder + "/" + file.getAttribute("data-name");
        this.currentFolder = currentFolder;
    }

    handleFileClick(file){
        if(!this.multiple){
            this.filesContainer.querySelectorAll(".file").forEach(sel => {
                if(sel != file){
                    sel.classList.remove("border");
                }
            })
        }
        file.classList.toggle("border");
    }

    async openSelectModal(){
        await this.getFiles();
        this.dialog.showModal();
    }

    async getFiles(){
        let response = await fetch(`${this.baseFilesUrl}?path=${this.currentFolder}`);
        if(!response.ok){
            this.filesContainer.innerHTML = this.errorMarkup();
            return;
        }
        response = await response.json()
        this.files = response.data;
        this.activateFiles();
    }

    errorMarkup(){
        return `
            <div class="text-center text-danger m-2">Something went wrong...</div>
        `
    }

    noFilesMarkup(){
        return `<p class="m-1 text-center">No files available...</p>`
    }

    fileMarkup(file){
        return `<span role="button" class="file m-1 p-1" data-is-folder="${file.is_folder}"
                data-name="${file.name}" data-path="${file.path}">
            ${file.is_folder ? '<i class="fa-solid fa-folder"></i>' : '<i class="fa-solid fa-file"></i>'}
            ${file.name}
        </span>`
    }

    get selectBtn(){
        return this.querySelector(".select-btn")
    }

    get closeSelectBtn(){
        return this.querySelectorAll(".close-select-btn")
    }

    get confirmSelectBtn(){
        return this.querySelector(".confirm-btn");
    }

    get filesContainer(){
        return this.querySelector(".files-container");
    }

    get files(){
        const files = []
        this.querySelectorAll('span[data-path]').forEach(elem => {
            files.push(elem.getAttribute("data-path"));
        })
        return files;
    }

    set files(files){
        if(files.length == 0){
            this.filesContainer.innerHTML = this.noFilesMarkup();
            return;
        }
        this.filesContainer.innerHTML = files.map(file => {return this.fileMarkup(file)}).join("");
    }

    get dialog(){
        return this.querySelector("dialog")
    }

    get baseFilesUrl(){
        return this.getAttribute("data-base-files-url");
    }

    get currentFolder(){
        return this.getAttribute("data-current-folder");
    }

    set currentFolder(folder_path){
        this.setAttribute("data-current-folder", folder_path);
        this.rerender();
    }

    get selectedFiles(){
        return this.querySelector(".selected-files");
    }

    getFilesList(){
        const sels = this.querySelectorAll('.selected-file');
        const files = []
        sels.forEach(sel => {
            files.push(sel.getAttribute("data-path"));
        });
        if(files.length == 0){
            return null;
        }
        if(this.asString){
            return files.join(",")
        }
        return files;
    }

    get value(){
        if(this.multiple){
            return this.getFilesList();
        }
        const sel = this.selectedFiles.querySelector('.selected-file');
        if(!sel){
            return null;
        }
        return sel.getAttribute("data-path");
    }

    set value(files){
        if(!files){
            return;
        }
        if(typeof files === "string"){
            files = files.split(",");
        }
        this.selectedFiles.innerHTML = files.map(sel => {
                return this.selectedFileMarkup(sel);
        });
        this.activateSelectedFiles();
    }

}

export default FilePicker
