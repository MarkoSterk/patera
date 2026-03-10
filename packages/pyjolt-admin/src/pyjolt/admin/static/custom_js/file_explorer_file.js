/**
 * FileElement for file explorer
 */


class FileElement extends HTMLElement {

    constructor() {
        super();
    }

    connectedCallback() {
        this.innerHTML = this.markup();
        this.activate();
    }

    markup(){
        return `
            <div class="d-flex flex-column align-items-center text-center p-1"
                    style="width: 120px;" role="button" tabindex="0">
                <div hidden class="file-actions">
                </div>
                <div class="mb-1">
                    ${this.isFolder ? '<i class="fa-regular fa-folder fa-4x"></i>' : this.getIcon()}
                </div>
                <div class="text-truncate w-100 name-container" title="${this.name}">
                    ${this.name}
                </div>
            </div>
        `
    }

    getIcon(){
        if(!this.mimetype){
            return '<i class="fa-solid fa-file fa-4x"></i>';
        }
        if(this.mimetype && !this.mimetype.includes("image")){
            return '<i class="fa-solid fa-file fa-4x"></i>';
        }
        if(this.mimetype && this.mimetype.includes("image")){
            return `<img src="${this.folder}/${this.name}" width="60" height="65" alt="Image ${this.name}">`;
        }
        return '<i class="fa-solid fa-file fa-4x"></i>'
    }

    activate(){

        this.container.addEventListener("dblclick", async (e) => {
            if(this.isFolder){
                this.handleFolderDblClick(e);
            }else{
                await this.downloadFile(e);
            }
        });

        this.nameContainer.addEventListener("dblclick", (e) => {
            this.handleNameContainerDblClick(e);
        })

        this.nameContainer.addEventListener("focusout", async (e) => {
            this.nameContainer.removeAttribute("contenteditable");
            const nameChanged = this.name != this.nameContainer.innerHTML.trim();
            if(!nameChanged){
                return;
            }
            const oldName = this.name;
            const newName = this.nameContainer.innerHTML.trim();
            await this.changeFileName(e, oldName, newName);
        });
    }

    /**
     *
     * @param {Event} e
     */
    handleFolderDblClick(e){
        let currentFolder = this.explorer.currentFolder;
        currentFolder = currentFolder + "/" + this.name;
        this.explorer.currentFolder = currentFolder;
    }

    /**
     * @param {Event} e
     */
    async downloadFile(e){
        let response = await fetch(`${this.explorer.fetchFileUrl}?path=${this.path}/${this.name}`);
        if(!response.ok){
            response = await response.json() || {message: "Something went wrong", status: "danger"}
            setMessage(response.message, response.status);
            return;
        }
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = this.name;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
        const event = new Event("file-name-change");
        this.explorer.dispatchEvent(event);
    }

    /**
     *
     * @param {Event} e
     */
    handleNameContainerDblClick(e){
        e.preventDefault();
        e.stopPropagation();
        this.nameContainer.setAttribute("contenteditable", "true");
        this.nameContainer.innerHTML = this.nameContainer.innerHTML.trim();
        const event = new Event("file-name-change");
        this.explorer.dispatchEvent(event);
        this.nameContainer.focus();
    }

    async changeFileName(e, oldName, newName){
        let response = await fetch(`${this.explorer.renameUrl}?path=${this.path}&oldName=${oldName}&newName=${newName}`);
        const status = response.ok
        response = await response.json() || {message: "Something went wrong", status: "danger"}
        setMessage(response.message, response.status);
        if(status){
            this.setAttribute("data-file-name", newName)
        }else{
            this.nameContainer.innerHTML = oldName.trim();
        }
    }

    get isFolder(){
        return ["True", true, "true", "data-is-folder", "is-folder", 1, "1"].includes(this.getAttribute("data-is-folder"));
    }

    get name(){
        return this.getAttribute("data-file-name");
    }

    get path(){
        return this.getAttribute("data-file-path");
    }

    get mimetype(){
        return this.getAttribute("data-mimetype");
    }

    get container(){
        return this.querySelector('div[role="button"]');
    }

    get nameContainer(){
        return this.querySelector(".name-container");
    }

    get explorer(){
        return this.closest("file-explorer");
    }

    get folder(){
        return this.explorer.currentFolder;
    }

    get value(){
        return {
            name: this.name,
            path: this.path,
            isFolder: this.isFolder
        }
    }

}

export default FileElement;
