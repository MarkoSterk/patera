from __future__ import annotations
import re
from typing import Any, Dict, Callable, List

from html.parser import HTMLParser
from typing import Optional, Tuple


def extract_data_bind_templates(html: str) -> Dict[str, str]:
    """
    Extract innerHTML of all elements that have data-bind="<name>".

    Returns:
        dict mapping { "<name>": "<inner html of the element>" }

    Notes:
      - Uses Python stdlib only (html.parser).
      - Preserves nested markup/text exactly as it appears in the input.
      - If the same data-bind value appears multiple times, the *last one wins*.
        (Easy to change to list aggregation if you prefer.)
    """
    if not isinstance(html, str):
        raise TypeError("html must be a string")

    # HTML void elements (no closing tag / no inner HTML)
    VOID = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    class _Parser(HTMLParser):
        def __init__(self) -> None:
            # convert_charrefs=False to preserve entities as-is (e.g. "&nbsp;")
            super().__init__(convert_charrefs=False)
            self.result: Dict[str, str] = {}

            # Stack of open tags for reconstruction of inner html
            self._open_tags: List[str] = []

            # Active capture frames: list of (bind_name, depth_at_start, chunks)
            # depth_at_start is the open tag stack depth *after* pushing the capturing tag.
            self._captures: List[Tuple[str, int, List[str]]] = []

        def _attrs_to_str(self, attrs: List[Tuple[str, Optional[str]]]) -> str:
            # Reconstruct attribute text (best-effort; may not preserve original quoting)
            out = []
            for k, v in attrs:
                if v is None:
                    out.append(k)
                else:
                    # Minimal escaping for quotes; input is valid HTML
                    vv = v.replace('"', "&quot;")
                    out.append(f'{k}="{vv}"')
            return (" " + " ".join(out)) if out else ""

        def _emit_to_captures(self, s: str) -> None:
            for _, __, chunks in self._captures:
                chunks.append(s)

        def handle_starttag(
            self, tag: str, attrs: List[Tuple[str, Optional[str]]]
        ) -> None:
            tag_l = tag.lower()
            attr_map = {k: v for k, v in attrs}

            # Push tag on stack (even for void, to simplify depth logic; pop immediately)
            self._open_tags.append(tag_l)

            # If we're already capturing, this start tag is part of innerHTML.
            # But if THIS tag is the capturing tag itself, its own start tag should NOT be included.
            start_text = f"<{tag}{self._attrs_to_str(attrs)}>"
            is_void = tag_l in VOID

            bind = attr_map.get("data-bind")
            if bind is not None:
                # Start a new capture for this element.
                # Inner HTML begins AFTER this start tag.
                depth_after_push = len(self._open_tags)
                self._captures.append((bind, depth_after_push, []))
            else:
                # Regular element start tag is inside any currently-active captures
                self._emit_to_captures(start_text)

            if is_void:
                # Void tag has no end tag; close immediately.
                self._open_tags.pop()
                # For void tags, nothing else to do.

        def handle_endtag(self, tag: str) -> None:
            tag_l = tag.lower()

            # Determine if we're closing a capture root.
            # A capture root closes when the open tag depth equals its start depth and this endtag occurs.
            # Since endtag happens while tag is still "open" in our stack, the stack should currently end with tag_l.
            if self._open_tags and self._open_tags[-1] == tag_l:
                current_depth = len(self._open_tags)

                # If the top-most capture started at this depth, we're closing it now.
                if self._captures and self._captures[-1][1] == current_depth:
                    bind, _, chunks = self._captures.pop()
                    self.result[bind] = "".join(chunks)
                else:
                    # Otherwise this end tag is part of innerHTML for any active captures.
                    self._emit_to_captures(f"</{tag}>")

                # Pop the tag
                self._open_tags.pop()
            else:
                # Malformed/odd HTML; best-effort: still emit end tag into captures
                self._emit_to_captures(f"</{tag}>")

        def handle_startendtag(
            self, tag: str, attrs: List[Tuple[str, Optional[str]]]
        ) -> None:
            # Handles <tag ... /> explicitly (XML-style). Treat as void.
            start_text = f"<{tag}{self._attrs_to_str(attrs)} />"
            attr_map = {k: v for k, v in attrs}
            bind = attr_map.get("data-bind")
            if bind is not None:
                # Self-closing element with data-bind has empty innerHTML
                self.result[bind] = ""
            else:
                self._emit_to_captures(start_text)

        def handle_data(self, data: str) -> None:
            self._emit_to_captures(data)

        def handle_comment(self, data: str) -> None:
            self._emit_to_captures(f"<!--{data}-->")

        def handle_entityref(self, name: str) -> None:
            self._emit_to_captures(f"&{name};")

        def handle_charref(self, name: str) -> None:
            self._emit_to_captures(f"&#{name};")

        def handle_decl(self, decl: str) -> None:
            self._emit_to_captures(f"<!{decl}>")

        def unknown_decl(self, data: str) -> None:
            self._emit_to_captures(f"<![{data}]>")

    p = _Parser()
    p.feed(html)
    p.close()
    return p.result


class MiniTemplate:
    """
    Tiny template engine supporting:

      - {{ expr }}                         -> expression interpolation
      - {% if expr %} / {% elif %} / {% else %} / {% endif %}
      - {% for x in xs %} ... {% endfor %}
      - {% set name = expr %}              -> variable declaration/assignment
      - {% py ... %}                       -> raw python statements (escape hatch)
      - {% raw %} ... {% endraw %}         -> everything inside is emitted verbatim,
                                             including any {{ ... }} or {% ... %} text.
    Security: Executes Python expressions/statements. Do NOT use with untrusted templates/data.
    """

    # Tokenize template into: "{{...}}", "{%...%}", or "other text".
    _token_re = re.compile(r"({{.*?}}|{%-?.*?-?%})", re.S)

    def __init__(self, template: str):
        self.template = template
        self._render_fn: Callable = self._compile(template)

    def render(self, context: Dict[str, Any]) -> str:
        if not isinstance(context, dict):
            context = {"ctx": context}
        return self._render_fn(context)

    @staticmethod
    def _compile(tpl: str) -> Callable[[Dict[str, Any]], str]:
        tokens = MiniTemplate._token_re.split(tpl)

        code_lines: List[str] = []
        add = code_lines.append

        add("def __render(__ctx):")
        add("    __out = []")
        add("    __append = __out.append")
        add("    # __ctx acts as globals+locals for eval/exec")
        indent = 1

        def emit(line: str) -> None:
            add(("    " * indent) + line)

        def emit_text(s: str) -> None:
            if s:
                emit(f"__append({s!r})")

        stack: List[str] = []  # "if", "for", "raw"
        raw_depth = 0
        raw_buf: List[str] = []

        def flush_raw_buf() -> None:
            nonlocal raw_buf
            if raw_buf:
                emit_text("".join(raw_buf))
                raw_buf = []

        def normalize_tag(inner: str) -> str:
            inner = inner.strip()
            inner = inner.lstrip("-").rstrip("-").strip()
            return inner

        # Helper: when in raw, we do NOT interpret tokens; we just accumulate text.
        def raw_add(s: str) -> None:
            raw_buf.append(s)

        for tok in tokens:
            if tok is None or tok == "":
                continue

            # Everything is treated as raw text except for the beginning and end blocks
            # Even internal blocks (including raw) are treated as raw text
            if raw_depth > 0:
                if tok.startswith("{%") and tok.endswith("%}"):
                    inner = normalize_tag(tok[2:-2])
                    if inner == "raw":
                        raw_depth += 1
                        raw_add(tok)
                        continue
                    if inner == "endraw":
                        raw_depth -= 1
                        if raw_depth == 0:
                            flush_raw_buf()
                        else:
                            raw_add(tok)
                        continue
                raw_add(tok)
                continue

            if tok.startswith("{{") and tok.endswith("}}"):
                expr = tok[2:-2].strip()
                emit(f"__append(str(eval({expr!r}, __ctx, __ctx)))")
                continue

            if tok.startswith("{%") and tok.endswith("%}"):
                inner = normalize_tag(tok[2:-2])

                if inner == "raw":
                    stack.append("raw")
                    raw_depth = 1
                    raw_buf = []
                    continue
                if inner == "endraw":
                    raise SyntaxError("endraw without matching raw")

                if inner.startswith("if "):
                    cond = inner[3:].strip()
                    emit(f"if eval({cond!r}, __ctx, __ctx):")
                    stack.append("if")
                    indent += 1
                    continue

                if inner.startswith("elif "):
                    if not stack or stack[-1] != "if":
                        raise SyntaxError("elif without matching if")
                    indent -= 1
                    cond = inner[5:].strip()
                    emit(f"elif eval({cond!r}, __ctx, __ctx):")
                    indent += 1
                    continue

                if inner == "else":
                    if not stack or stack[-1] != "if":
                        raise SyntaxError("else without matching if")
                    indent -= 1
                    emit("else:")
                    indent += 1
                    continue

                if inner == "endif":
                    if not stack or stack[-1] != "if":
                        raise SyntaxError("endif without matching if")
                    stack.pop()
                    indent -= 1
                    continue

                if inner.startswith("for "):
                    m = re.match(r"for\s+(.+?)\s+in\s+(.+)", inner)
                    if not m:
                        raise SyntaxError(f"Invalid for syntax: {inner!r}")
                    targets, it_expr = m.group(1).strip(), m.group(2).strip()
                    emit(f"for {targets} in eval({it_expr!r}, __ctx, __ctx):")
                    # Expose loop vars to __ctx so {{ var }} works inside the loop.
                    emit("    __ctx.update(locals())")
                    stack.append("for")
                    indent += 1
                    continue

                if inner == "endfor":
                    if not stack or stack[-1] != "for":
                        raise SyntaxError("endfor without matching for")
                    stack.pop()
                    indent -= 1
                    continue

                if inner.startswith("set "):
                    m = re.match(r"set\s+(.+?)\s*=\s*(.+)", inner)
                    if not m:
                        raise SyntaxError(f"Invalid set syntax: {inner!r}")
                    target, expr = m.group(1).strip(), m.group(2).strip()

                    # Keep "set" intentionally simple: single name key in __ctx.
                    if not re.fullmatch(r"[A-Za-z_]\w*", target):
                        raise SyntaxError(
                            "set only supports simple variable names (e.g. {% set x = 1 %})"
                        )

                    emit(f"__ctx[{target!r}] = eval({expr!r}, __ctx, __ctx)")
                    continue

                if inner.startswith("py "):
                    stmt = inner[3:].strip()
                    emit(f"exec({stmt!r}, __ctx, __ctx)")
                    continue

                raise SyntaxError(f"Unknown tag: {inner!r}")

            emit_text(tok)

        if raw_depth > 0:
            raise SyntaxError("Unclosed raw block (missing {% endraw %})")

        if stack:
            # If stack isn't empty here, it's because of unclosed if/for blocks.
            unclosed = [x for x in stack if x != "raw"]
            if unclosed:
                raise SyntaxError(f"Unclosed block(s): {unclosed}")

        emit("return ''.join(__out)")

        src = "\n".join(code_lines)
        ns: Dict[str, Any] = {}
        exec(src, ns, ns)
        return ns["__render"]
