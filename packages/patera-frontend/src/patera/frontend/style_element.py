from __future__ import annotations
from abc import abstractmethod, ABC


class Style(ABC):
    def __init__(self, scoped: bool = False):
        self._scoped = scoped

    @abstractmethod
    def style(self) -> str: ...

    def _scope(self, style: str, el) -> str:
        if not self._scoped:
            return scope_css(style, "")
        return scope_css(style, el.tagName)

    def __call__(self, el) -> str:
        style_markup = self._scope(self.style(), el)
        return style_markup


def scope_css(css: str, root_placeholder: str) -> str:
    """
    Convert a CSS stylesheet into "scoped" CSS by rewriting selectors so rules only
    apply within a root element.

    - All *qualified rules* like:  h1, .a > b { ... }
      become:                    __ROOT__ h1, __ROOT__ .a > b { ... }

    - @media / @supports / @container / @layer blocks are processed recursively.
    - @keyframes blocks are left untouched (their inner selectors must NOT be prefixed).
    - @font-face, @page, @property, etc. are left untouched.

    The root is dynamic: pass your own placeholder (e.g. "[data-scope='X']" or ":where(.root)").
    """

    def is_whitespace(ch: str) -> bool:
        return ch in " \t\r\n\f"

    def skip_ws_and_comments(s: str, i: int) -> int:
        n = len(s)
        while i < n:
            if is_whitespace(s[i]):
                i += 1
                continue
            if s.startswith("/*", i):
                j = s.find("*/", i + 2)
                if j == -1:
                    return n
                i = j + 2
                continue
            break
        return i

    def consume_string(s: str, i: int) -> int:
        # s[i] is quote
        quote = s[i]
        i += 1
        n = len(s)
        while i < n:
            if s[i] == "\\":
                i += 2
                continue
            if s[i] == quote:
                return i + 1
            i += 1
        return n

    def find_matching_brace(s: str, i: int) -> int:
        # s[i] must be '{'
        depth = 0
        n = len(s)
        while i < n:
            if s.startswith("/*", i):
                j = s.find("*/", i + 2)
                if j == -1:
                    return n - 1
                i = j + 2
                continue
            ch = s[i]
            if ch in ("'", '"'):
                i = consume_string(s, i)
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i
            i += 1
        return n - 1

    def split_selectors(selector_text: str) -> list[str]:
        """
        Split a selector list by commas, but only at top-level (not inside (), [], strings).
        """
        parts: list[str] = []
        buf: list[str] = []
        n = len(selector_text)
        i = 0
        depth_paren = 0
        depth_brack = 0
        while i < n:
            if selector_text.startswith("/*", i):
                j = selector_text.find("*/", i + 2)
                if j == -1:
                    buf.append(selector_text[i:])
                    break
                buf.append(selector_text[i : j + 2])
                i = j + 2
                continue

            ch = selector_text[i]
            if ch in ("'", '"'):
                j = consume_string(selector_text, i)
                buf.append(selector_text[i:j])
                i = j
                continue

            if ch == "(":
                depth_paren += 1
            elif ch == ")":
                depth_paren = max(0, depth_paren - 1)
            elif ch == "[":
                depth_brack += 1
            elif ch == "]":
                depth_brack = max(0, depth_brack - 1)

            if ch == "," and depth_paren == 0 and depth_brack == 0:
                parts.append("".join(buf).strip())
                buf = []
                i += 1
                continue

            buf.append(ch)
            i += 1

        tail = "".join(buf).strip()
        if tail:
            parts.append(tail)
        return parts

    def scope_selector(sel: str) -> str:
        """
        Prefix a single selector with the root placeholder.
        Also replaces :host and :root with the placeholder as a convenience.
        """
        s = sel.strip()
        if not s:
            return s

        # Common "scoped style" conveniences:
        # - Treat :host and :root as the scope root itself
        # (very simple text replacement; good enough for typical usage)
        s = s.replace(":host", root_placeholder).replace(":root", root_placeholder)

        # If selector already begins with the placeholder (user already scoped it), keep it.
        if s.startswith(root_placeholder):
            return s

        # If it starts with a combinator, insert placeholder before it:  "> .a" -> "__ROOT__ > .a"
        if s[0] in (">", "+", "~"):
            return f"{root_placeholder} {s}"

        return f"{root_placeholder} {s}"

    def process_block(block: str, in_keyframes: bool) -> str:
        """
        Process a chunk of CSS that contains multiple top-level rules.
        """
        out: list[str] = []
        i = 0
        n = len(block)

        while i < n:
            start = i
            i = skip_ws_and_comments(block, i)
            if i >= n:
                out.append(block[start:])
                break

            # Preserve any whitespace/comments we skipped by appending them as-is
            if start != i:
                out.append(block[start:i])

            if block[i] == "@":
                # Parse at-rule name
                j = i + 1
                while j < n and (block[j].isalpha() or block[j] in "-_"):
                    j += 1
                at_name = block[i + 1 : j].strip().lower()

                # Read prelude until ';' or '{' at top-level (respect strings/comments)
                k = j
                while k < n:
                    if block.startswith("/*", k):
                        cend = block.find("*/", k + 2)
                        if cend == -1:
                            k = n
                            break
                        k = cend + 2
                        continue
                    ch = block[k]
                    if ch in ("'", '"'):
                        k = consume_string(block, k)
                        continue
                    if ch == ";":
                        # at-rule without block
                        out.append(block[i : k + 1])
                        i = k + 1
                        break
                    if ch == "{":
                        end = find_matching_brace(block, k)
                        header = block[i:k].rstrip()
                        inner = block[k + 1 : end]
                        trailer = block[end : end + 1]  # "}"

                        # Recurse into some at-rules that contain nested rules
                        recurse_names = {
                            "media",
                            "supports",
                            "container",
                            "layer",
                            "document",
                            "-moz-document",
                        }
                        keyframes_names = {
                            "keyframes",
                            "-webkit-keyframes",
                            "-moz-keyframes",
                            "-o-keyframes",
                        }

                        if at_name in recurse_names:
                            out.append(header + "{")
                            out.append(process_block(inner, in_keyframes=False))
                            out.append(trailer)
                        elif at_name in keyframes_names:
                            # Don't scope frame selectors (from/to/0% etc.)
                            out.append(header + "{")
                            out.append(process_block(inner, in_keyframes=True))
                            out.append(trailer)
                        else:
                            # Leave other at-rules untouched
                            out.append(block[i : end + 1])

                        i = end + 1
                        break
                    k += 1
                else:
                    # ran out
                    out.append(block[i:])
                    break

                continue

            # Qualified rule: selector { declarations }
            # Find next '{' at top-level
            j = i
            while j < n:
                if block.startswith("/*", j):
                    cend = block.find("*/", j + 2)
                    if cend == -1:
                        j = n
                        break
                    j = cend + 2
                    continue
                ch = block[j]
                if ch in ("'", '"'):
                    j = consume_string(block, j)
                    continue
                if ch == "{":
                    end = find_matching_brace(block, j)
                    selector_text = block[i:j].strip()
                    decls = block[j + 1 : end]
                    closing = block[end : end + 1]  # "}"

                    if in_keyframes:
                        # Don't scope frame selectors like "from", "to", "0%"
                        new_selector = selector_text
                    else:
                        sels = split_selectors(selector_text)
                        new_selector = ", ".join(scope_selector(s) for s in sels)

                    out.append(new_selector)
                    out.append(" {")
                    out.append(decls)
                    out.append(closing)
                    i = end + 1
                    break
                j += 1
            else:
                # No more blocks; append rest
                out.append(block[i:])
                break

        return "".join(out)

    return process_block(css, in_keyframes=False)
