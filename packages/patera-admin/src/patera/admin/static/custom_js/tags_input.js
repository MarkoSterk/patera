/**
 * Custom JS for tags input functionality
 */

class TagsInput extends HTMLElement {

    constructor() {
        super();
        this._value = [];
        this._as_string = this.hasAttribute("as-string")
        this._placeholder = this.getAttribute("placeholder") || "Input a tag and press enter";
        this.shadow = this.attachShadow({ mode: 'closed' });
    }

    connectedCallback() {
        this.shadow.innerHTML = this.markup();
        this.tagInput = this.shadow.querySelector(".tag-input");
        this.tagsContainer = this.shadow.querySelector(".tags");
        this.activate();
        this.populateInitialTags();
    }

    markup(){
        return `
            <style>
                .tag-input {
                    width: 100%;
                    padding: 0.375rem 0.75rem;      /* Same as Bootstrap */
                    font-size: 1rem;
                    line-height: 1.5;
                    color: #212529;
                    background-color: #fff;
                    background-clip: padding-box;

                    border: 1px solid #ced4da;      /* Bootstrap border */
                    border-radius: 0.375rem;        /* Bootstrap rounded corners */

                    transition: border-color .15s ease-in-out,
                                box-shadow .15s ease-in-out;
                    box-sizing: border-box;
                }

                .tag-input:focus {
                    color: #212529;
                    background-color: #fff;
                    border-color: #86b7fe;          /* Bootstrap focus border */
                    outline: 0;
                    box-shadow: 0 0 0 0.25rem rgba(13,110,253,.25); /* BS5 focus glow */
                }

                .tags {
                    margin-top: 8px;
                }
                .tag {
                    display: inline-block;
                    background-color: #007bff;
                    color: white;
                    padding: 4px 8px;
                    border-radius: 4px;
                    margin-right: 4px;
                    margin-bottom: 4px;
                    font-size: 14px;
                }
            </style>
            <div>
                <div>
                    <input type="text" role="presentation" id="tag-input" name="tag-input" class="tag-input" placeholder="${this._placeholder}"/>
                </div>
                <div class="tags">

                </div>
            </div>
        `
    }

    activate(){
        this.tagInput.addEventListener("keydown", (e) => {
            if(e.key === "Enter"){
                e.preventDefault();
                const tag = this.tagInput.value.trim();
                if(tag.length > 0){
                    this.createTagElement(tag);
                    this.tagInput.value = "";
                }
            }
        });
    }

    populateInitialTags(){
        const initialTags = this.getAttribute("value")?.split(",") || [];
        initialTags.forEach(tag => {
            const trimmedTag = tag.trim();
            if(trimmedTag.length > 0){
                this.createTagElement(trimmedTag);
            }
        });
    }

    createTagElement(tag){
        const tagEl = document.createElement("span");
        tagEl.classList.add("tag");
        tagEl.innerHTML = `<span class="tag-content">${tag}</span> <span class="remove-tag" style="cursor:pointer; margin-left:4px;" title="Remove tag">&times;</span>`;
        this.tagsContainer.appendChild(tagEl);
        tagEl.querySelector(".remove-tag").addEventListener("click", () => {
            this.tagsContainer.removeChild(tagEl);
        });
        return tagEl;
    }

    get value(){
        if(this._as_string){
            return this.getString();
        }
        return this.getList();
    }

    getList(){
        const tags = Array.from(this.tagsContainer.querySelectorAll(".tag-content")).map(tagEl => tagEl.textContent);
        if(tags.length > 0){
            return tags;
        }
        return null;
    }

    getString(){
        return this.getList() ? this.getList().join(", ") : null;
    }

    appendValues(newValues){
        if(typeof newValues === "string"){
            newValues = newValues.split(",").map(v => v.trim()).filter(v => v.length > 0);
        }
        const currentValues = this.getList() || [];
        this.value = currentValues.concat(newValues);
    }

    set value(val){
        this.tagsContainer.innerHTML = "";
        if(!val){
            return;
        }
        if(typeof val === "string"){
            val = val.split(",").map(v => v.trim()).filter(v => v.length > 0);
        }
        val.forEach(tag => this.createTagElement(tag));
    }
}

export default TagsInput;
