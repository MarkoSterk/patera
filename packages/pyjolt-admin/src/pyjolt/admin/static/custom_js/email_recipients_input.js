/**
 * Custom element for email recipients
 */

class RecipientsInput extends HTMLElement {

    constructor() {
        super();
        this._value = [];
        this._placeholder = this.getAttribute("placeholder") || "Input a recipient email and press enter";
        this.shadow = this.attachShadow({ mode: 'closed' });
    }

    connectedCallback() {
        this.shadow.innerHTML = this.markup();
        this.recipientInput = this.shadow.querySelector(".recipient-input");
        this.recipientsContainer = this.shadow.querySelector(".recipients");
        this.suggestions = this.shadow.querySelector(".suggestions-container");
        const url = new URL(location.href);
        this.client = url.searchParams.get("client");
        this.queryUrl = this.getAttribute("query-url")
        if(!this.queryUrl){
            throw new Error("Missing query url parameter");
        }
        this.activate();
        this.populateInitialRecipients();
        this.cache = new Map();
    }

    markup(){
        return `
            <style>
                .recipient-input {
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

                .recipient-input:focus {
                    color: #212529;
                    background-color: #fff;
                    border-color: #86b7fe;          /* Bootstrap focus border */
                    outline: 0;
                    box-shadow: 0 0 0 0.25rem rgba(13,110,253,.25); /* BS5 focus glow */
                }

                .recipients {
                    margin-top: 8px;
                }
                .recipient {
                    display: inline-block;
                    background-color: #007bff;
                    color: white;
                    padding: 4px 8px;
                    border-radius: 4px;
                    margin-right: 4px;
                    margin-bottom: 4px;
                    font-size: 14px;
                }

                .active-suggestion {
                    background-color: #007bff;
                    margin: 0;
                    padding: 4px;
                }

                .suggestion {
                    border-left: 1px solid black;
                    border-right: 1px solid black;
                    cursor: pointer;
                }

                .suggestion:hover {
                    background-color: #4c6580ff
                }

                .suggestions-container {
                    position: absolute;
                    top: 35px;
                    width: 100%;
                    background-color: #e1dedeff;
                    max-height: 150px;
                    overflow-y: scroll;
                }

                .suggestions-container:first-child {
                    border-top: 1px solid black;
                }

                .suggestions-container:last-child {
                    border-bottom: 1px solid black;
                }
            </style>
            <div style="position: relative;">
                <div>
                    <input type="text" role="presentation" id="recipient-input" name="recipient-input"
                     class="recipient-input" placeholder="${this._placeholder}"/>
                </div>
                <div class="suggestions-container">

                </div>
                <div class="recipients">

                </div>
            </div>
        `
    }

    activate(){
        this.recipientInput.addEventListener("keyup", async (e) => {
            if(["ArrowUp", "ArrowDown"].includes(e.key)){
                e.preventDefault();
                const current = this.suggestions.querySelector(".active-suggestion");
                let next = e.key == "ArrowDown" ? current.nextElementSibling : current.previousElementSibling;
                if(!next){
                    const all = this.suggestions.querySelectorAll(".suggestion");
                    next = e.key == "ArrowDown" ? all[0] : all[all.length - 1];
                }
                current.classList.remove("active-suggestion");
                next.classList.add("active-suggestion");
                next.scrollIntoView();
                return;
            }
            if(!["Enter"].includes(e.key)){
                if(["", undefined, null].includes(this.recipientInput.value)){
                    this.suggestions.innerHTML = "";
                    return;
                }
                const query = this.recipientInput.value.trim();
                if(this.cache.has(query)){
                    return this.populateSuggestions(this.cache.get(query), query);
                }
                await this.querySuggestions(query);
            }
        });
        this.recipientInput.addEventListener("keydown", (e) => {
            if(["ArrowUp", "ArrowDown"].includes(e.key)){
                e.preventDefault();
                return;
            }
            if(e.key == "Enter"){
                e.preventDefault()
                const current = this.suggestions.querySelector(".active-suggestion");
                if(!current){
                    return;
                }
                this.useSuggestion({target: current})
            }
        });
        this.recipientInput.addEventListener("blur", (e) => {
            this.suggestions.innerHTML = "";
        });
        this.recipientInput.addEventListener("focus", async (e) => {
            const query = this.recipientInput?.value?.trim();
            if(["", undefined, null].includes(query)){
                return;
            }
            if(this.cache.has(query)){
                return this.populateSuggestions(this.cache.get(query), query);
            }
            await this.querySuggestions(query);
        })
    }

    async querySuggestions(query){
        const url = this.queryUrl+`?client=${this.client}&query=${query}`
        const response = await fetch(url)
        if(!response.ok){
            throw new Error("Failed to perform query for email recipients with query: " + url)
        }
        const suggestions = (await response.json()).data
        this.cache.set(query, suggestions)
        this.populateSuggestions(suggestions, query);
    }

    /**
     *
     * @param {Array<Array>} suggestions
     * @param {string} query
     */
    populateSuggestions(suggestions, query){
        suggestions = suggestions.map((s) => {
            return `
                <div class="suggestion" value="${s[1]}">
                    <span>${s[0]} [${s[1].substring(0, 100)}]<span>
                </div>
            `
        });
        suggestions.unshift([`
                <div class="suggestion" value="${query}">
                    Use: <span>${query.substring(0,100)} [${query.substring(0,100)}]<span>
                </div>
            `])
        this.suggestions.innerHTML = suggestions.join("");
        this.activateSuggestions();
    }

    activateSuggestions(){
        const allSuggestions = this.suggestions.querySelectorAll(".suggestion");
        allSuggestions[0].classList.add("active-suggestion");
        allSuggestions.forEach((s) => {
            s.addEventListener("mousedown", (e) => {
                e.preventDefault();
                this.useSuggestion(e)
            })
        })
    }

    useSuggestion(event){
        const sugg = event.target.closest(".suggestion");
        const val = sugg.getAttribute("value");
        const text = sugg.querySelector("span").innerHTML;
        this.createRecipientElement([text, val]);
        this.removeSuggestions();
        this.recipientInput.value = "";
    }

    removeSuggestions(){
        this.suggestions.innerHTML = "";
    }

    populateInitialRecipients(){
        const initialRecipients = this.getAttribute("value")?.split(",") || [];
        initialRecipients.forEach(tag => {
            const trimmedRecipient = tag.trim();
            if(trimmedRecipient.length > 0){
                this.createRecipientElement(trimmedRecipient);
            }
        });
    }

    createRecipientElement(tag){
        const recipientEl = document.createElement("span");
        recipientEl.classList.add("recipient");
        recipientEl.innerHTML = `<span class="recipient-content" value="${tag[1]}">${tag[0]}</span> <span class="remove-recipient" style="cursor:pointer; margin-left:4px;" title="Remove recipient">&times;</span>`;
        this.recipientsContainer.appendChild(recipientEl);
        recipientEl.querySelector(".remove-recipient").addEventListener("click", () => {
            this.recipientsContainer.removeChild(recipientEl);
        });
        return recipientEl;
    }

    get value(){
        return this.getList();
    }

    getList(){
        const recipients = Array.from(this.recipientsContainer.querySelectorAll(".recipient-content")).map(tagEl => tagEl.getAttribute("value"));
        let allRecipients = [];
        for(const recipient of recipients){
            const val = [...recipient.split(",").map((r) => r.trim())]
            allRecipients = allRecipients.concat(val)
        }
        if(allRecipients.length > 0){
            return allRecipients;
        }
        return null;
    }

    appendValues(newValues){
        const currentValues = this.getList() || [];
        this.value = currentValues.concat(newValues);
    }

    set value(val){
        this.recipientsContainer.innerHTML = "";
        if(!val){
            return;
        }
        val.forEach(tag => this.createRecipientElement(tag));
    }
}

export default RecipientsInput;
