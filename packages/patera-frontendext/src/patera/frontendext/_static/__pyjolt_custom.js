class CustomElement extends HTMLElement {
    constructor(){
        super();
    }
}
const __customElements = {}
function __pyjolt__registerComponent(tagName, component, markup, methods, beforeInit, afterInit, onDisconnect, style, snippets){
    __customElements[tagName] = {};
    __customElements[tagName]["markup"] = markup;
    __customElements[tagName]["template_snippets"] = snippets;
    __customElements[tagName]["methods"] = methods;
    __customElements[tagName]["beforeInit"] = beforeInit;
    __customElements[tagName]["afterInit"] = afterInit;
    __customElements[tagName]['onDisconnect'] = onDisconnect;
    __customElements[tagName]['style'] = style
    //console.log(component)
    eval(component);
}
function __pyjolt__convertValue(value){
    try{{
        return JSON.parse(value)
    }}catch{{}}
    return value;
}
