/**
 * File upload input
 */

class FilesInput extends HTMLElement{

    filesIcons = {
        "default": '<i class="fa-solid fa-file fa-2xl"></i>',
        ".txt": '<i class="fa-solid fa-file-lines fa-2xl"></i>',
        ".pdf": '<i class="fa-solid fa-file-pdf fa-2xl"></i>',
        ".docx": '<i class="fa-solid fa-file-word fa-2xl"></i>',
        ".doc": '<i class="fa-solid fa-file-word fa-2xl"></i>',
        ".csv": '<i class="fa-solid fa-file-csv fa-2xl"></i>',
        ".xlsx": '<i class="fa-solid fa-file-excel fa-2xl"></i>',
        ".xlsb": '<i class="fa-solid fa-file-excel fa-2xl"></i>',
        ".xlsm": '<i class="fa-solid fa-file-excel fa-2xl"></i>',
        ".zip": '<i class="fa-solid fa-file-pdf fa-2xl"></i>',
        ".rar": '<i class="fa-solid fa-file-pdf fa-2xl"></i>',
        ".tar": '<i class="fa-solid fa-file-pdf fa-2xl"></i>',
        ".gz": '<i class="fa-solid fa-file-pdf fa-2xl"></i>',
        ".html": '<i class="fa-solid fa-file-code fa-2xl"></i>',
        ".htm": '<i class="fa-solid fa-file-code fa-2xl"></i>',
        ".py": '<i class="fa-solid fa-file-code fa-2xl"></i>',
        ".cpp": '<i class="fa-solid fa-file-code fa-2xl"></i>',
        ".c": '<i class="fa-solid fa-file-code fa-2xl"></i>',
        ".jpg": '<i class="fa-solid fa-file-image fa-2xl"></i>',
        ".jpeg": '<i class="fa-solid fa-file-image fa-2xl"></i>',
        ".gif": '<i class="fa-solid fa-file-image fa-2xl"></i>',
        ".png": '<i class="fa-solid fa-file-image fa-2xl"></i>'
    }

    constructor(){
        super();
        this.multiple = this.hasAttribute("multiple");
        this.accept = this.getAttribute("accept")?.split(",")?.map(format => format.trim());
        this.files = null;
    }

    connectedCallback(){
        this.innerHTML = this.markup();
        this.fileInput = this.querySelector(".file-input");
        this.filesContainer = this.querySelector(".uploads");
        this.uploadBtn = this.querySelector(".upload-btn");
        this.fileInput.addEventListener("change", (e) => {this.handleUpload(e)});
        this.uploadBtn.addEventListener("click", (e) => {this.handleUploadClick(e)})
    }

    markup(){
        return `
            <style>
                .upload-btn:hover {
                    opacity: 0.75;
                }
            </style>
            <div>
                <input type="file" class="file-input" ${this.accept ? this.accept.join("") : ""}
                ${this.multiple ? "multiple" : ""} hidden />
                <button type="button" ${this.multiple ? 'title="You can select multiple files."' : ''} class="upload-btn btn btn-sm border">
                    <i class="fa-solid fa-paperclip"></i> Add attachment${this.multiple ? "s" : ""}
                </button>
                <div class="uploads row mt-2">

                </div>
            </div>
        `
    }

    fileIconMarkup(fileName, ext){
        return `
            <div class="file-icon col-auto m-1 p-1 border" file-name="${fileName}">
                ${this.filesIcons[ext] || this.filesIcons.default}
                <small>${fileName}</small>
                <button type="button" title="Remove ${fileName}" class="btn remove-file"><i class="fa-solid fa-xmark"></i></button>
            </div>
        `
    }

    async handleUpload(e){
        const files = await this.filesToBase64Map(e);
        this.addFileIcons(files);
        this.activateIcons();
        this.files = this.files ? {...this.files, ...files} : files
    }

    activateIcons(){
        this.filesContainer.querySelectorAll(".remove-file").forEach(el => {
            if(!el.classList.contains("is-active")){
                el.classList.add("is-active")
                el.addEventListener("click", e => {
                    const file = e.target.closest(".file-icon");
                    const fileName = file.getAttribute("file-name");
                    const remainingFiles = {};
                    for(const name of Object.keys(this.files)){
                        if(name != fileName){
                            remainingFiles[name] = this.files[name];
                        }
                    }
                    this.files = Object.keys(remainingFiles).length > 0 ? remainingFiles : null;
                    file.remove();
                })
            }
        })
    }

    handleUploadClick(e){
        const btn = e.target.closest("button");
        btn.blur();
        this.fileInput.click();
    }

    addFileIcons(files){
        if(!files){
            return;
        }
        const icons = []
        for(const fileName of Object.keys(files)){
            icons.push(this.fileIconMarkup(fileName, this.extension(fileName)))
        }
        this.filesContainer.insertAdjacentHTML("beforeend", icons.join(""));
    }

    extension(fileName){
        const parts = fileName.split(".");
        return `.${parts[parts.length - 1]}`
    }

    async filesToBase64Map(event) {
        const input = event.target;
        if (!input.files || input.files.length === 0) return {};
        const fileArray = Array.from(input.files);

        const fileToBase64 = file =>
            new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => resolve(reader.result);
                reader.onerror = reject;
                reader.readAsDataURL(file);
            });

        const base64List = await Promise.all(fileArray.map(file => fileToBase64(file)));

        const result = {};
        fileArray.forEach((file, index) => {
            result[file.name] = base64List[index];
        });

        return result;
    }

    get value(){
        return this.files;
    }

    set value(files){
        if(files != null && typeof files != "object"){
            throw new Error("Value for FilesInput element must be null or an object of fileName-base64 pairs.")
        }
        this.files = files;
        if(!this.files){
            this.filesContainer.innerHTML = "";
            return;
        }
        this.addFileIcons(this.files);
        this.activateIcons()
    }

}

export default FilesInput;
