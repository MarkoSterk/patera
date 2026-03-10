/**
 * Richtext editor for admin interface
 */

class RichTextEditor extends HTMLElement{
    constructor() {
        super();
        this.editor = null;
        this.editorId = `richtext-editor-${this.randomInt(10000)}`;
    }

    randomInt(max){
        return Math.floor(Math.random() * max);
    }

    markup() {
        return `
            <div id="${this.editorId}"></div>
        `;
    }

    connectedCallback() {
        this.innerHTML = this.markup();
        this.initializeEditor();
    }

    initializeEditor() {
        $(`#${this.editorId}`).summernote({
            placeholder: this.placeholder,
            tabsize: this.tabsize,
            height: this.height,
            minHeight: this.minHeight,
            maxHeight: this.maxHeight,
            focus: this.focusAttr,
            toolbar: [
                ['style', this.styleOptions],
                ['font', this.fontOptions],
                ['color', this.colorOptions],
                ['para', this.paragraphOptions],
                ['table', this.tableOptions],
                ['insert', this.insertOptions],
                ['view', this.viewOptions]
            ],
            callbacks: {
                onImageUpload: (files) => {
                    for(const file of files){
                        this.uploadImage(file);
                    }
                }
            }
        });
    }

    async uploadImage(file){
        const data = new FormData();
        data.append("file", file);
        data.append("path", `${this.uploadFolder}/${file.name}`);
        let response = await fetch('/admin/dashboard/files/upload', {
            method: 'POST',
            body: data
        });

        if(response.ok){
            response = await response.json();
            $(`#${this.editorId}`).summernote('insertImage',
                response.data.path
            );
        }
    }

    get styleOptions(){
        const options = this.getAttribute('style-option') || 'style';
        return options.split(',').map(opt => opt.trim());
    }

    get fontOptions(){
        const options = this.getAttribute('font-option') || 'bold, underline, clear';
        return options.split(',').map(opt => opt.trim());
    }

    get colorOptions(){
        return this.getAttribute('color-option') || 'color';
    }

    get paragraphOptions(){
        const options = this.getAttribute('paragraph-option') || 'ul, ol, paragraph';
        return options.split(',').map(opt => opt.trim());
    }

    get insertOptions(){
        const options = this.getAttribute('insert-option') || 'link, picture, video';
        return options.split(',').map(opt => opt.trim());
    }

    get viewOptions(){
        const options = this.getAttribute('view-option') || 'fullscreen, codeview, help';
        return options.split(',').map(opt => opt.trim());
    }

    get tableOptions(){
        const options = this.getAttribute('table-option') || 'table';
        return options.split(',').map(opt => opt.trim());
    }

    get value(){
        return $(`#${this.editorId}`).summernote('code');
    }

    set value(val){
        $(`#${this.editorId}`).summernote('code', val);
    }

    get height(){
        return this.getAttribute('height') || 250;
    }

    get minHeight(){
        return this.getAttribute('min-height') || null;
    }

    get maxHeight(){
        return this.getAttribute('max-height') || null;
    }

    get focusAttr(){
        return this.getAttribute('focus') || false;
    }

    get placeholder(){
        return this.getAttribute('placeholder') || '';
    }

    get tabsize(){
        return this.getAttribute('tabsize') || 2;
    }

    get editorElement(){
        return this.getElementById(this.editorId);
    }

    get uploadFolder(){
        const uploadFolder = this.getAttribute('upload-folder') || undefined;
        if(!uploadFolder){
            throw new Error("upload-folder attribute is required for RichTextEditor.");
        }
        return uploadFolder;
    }

}

export default RichTextEditor;
