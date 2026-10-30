// Carry the package version into imports: versioning only index.js leaves
// browsers free to reuse a previous release's cached input implementations.
const version = new URL(import.meta.url).search;
const [{ default: TagsInput }, { default: SummernoteEditor }, { default: LatexInput }] =
  await Promise.all([
    import(`./tagsInput.js${version}`),
    import(`./summernoteInput.js${version}`),
    import(`./latexInput.js${version}`),
  ]);

customElements.define("tags-input", TagsInput);
customElements.define("summernote-editor", SummernoteEditor);
customElements.define("latex-input", LatexInput);
