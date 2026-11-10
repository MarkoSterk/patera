"""
Exports an exam's questions as a Word document (.docx).

Questions are numbered, their answers labelled a) to d), and the correct
answer is bold. LaTeX math between $…$ or $$…$$ is written as plain text
with Unicode symbols (e.g. ``$\\frac{\\sqrt{3}}{2} W$`` becomes ``√3/2 W``),
since Word documents have no LaTeX renderer.
"""

from __future__ import annotations

import base64
import re
from io import BytesIO
from typing import Iterable, Protocol

from docx import Document
from docx.shared import Cm, Pt

LABELS = ("a)", "b)", "c)", "d)")


class ExportedQuestion(Protocol):
    question_text: str
    image: str
    answers: list[str]
    correct_answer: int


def exam_docx(title: str, questions: Iterable[ExportedQuestion]) -> bytes:
    document = Document()
    normal = document.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    document.add_heading(title, level=1)

    for number, question in enumerate(questions, start=1):
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.space_before = Pt(12)
        paragraph.paragraph_format.space_after = Pt(4)
        paragraph.paragraph_format.keep_with_next = True
        paragraph.add_run(f"{number}. ")
        paragraph.add_run(plain_text(question.question_text))
        _add_image(document, question.image)
        for index, answer in enumerate(question.answers):
            line = document.add_paragraph()
            line.paragraph_format.left_indent = Cm(0.75)
            line.paragraph_format.space_after = Pt(2)
            line.paragraph_format.keep_with_next = index < len(question.answers) - 1
            run = line.add_run(f"{LABELS[index]} {plain_text(answer)}")
            run.bold = index == question.correct_answer

    output = BytesIO()
    document.save(output)
    return output.getvalue()


def _add_image(document, data_url: str) -> None:
    """Adds a question image stored as a data URL; WebP cannot go into Word."""
    match = re.fullmatch(r"data:image/(png|jpeg|gif|webp);base64,(.+)", data_url or "")
    if not match:
        return
    if match.group(1) == "webp":
        document.add_paragraph("[Image in WebP format – not supported in Word]")
        return
    picture = document.add_paragraph()
    picture.paragraph_format.keep_with_next = True
    try:
        picture.add_run().add_picture(
            BytesIO(base64.b64decode(match.group(2))), width=Cm(12)
        )
    except Exception:  # an image Word cannot read must not break the export
        picture.text = "[Image could not be included]"


# ---------------------------------------------------------------- LaTeX → text

MATH = re.compile(r"(?<!\\)\$\$(.+?)(?<!\\)\$\$|(?<!\\)\$(.+?)(?<!\\)\$", re.S)

GREEK = {
    "alpha": "α",
    "beta": "β",
    "gamma": "γ",
    "delta": "δ",
    "epsilon": "ε",
    "varepsilon": "ε",
    "zeta": "ζ",
    "eta": "η",
    "theta": "θ",
    "kappa": "κ",
    "lambda": "λ",
    "mu": "μ",
    "nu": "ν",
    "xi": "ξ",
    "pi": "π",
    "rho": "ρ",
    "sigma": "σ",
    "tau": "τ",
    "phi": "φ",
    "varphi": "φ",
    "chi": "χ",
    "psi": "ψ",
    "omega": "ω",
    "Gamma": "Γ",
    "Delta": "Δ",
    "Theta": "Θ",
    "Lambda": "Λ",
    "Pi": "Π",
    "Sigma": "Σ",
    "Phi": "Φ",
    "Psi": "Ψ",
    "Omega": "Ω",
}
SYMBOLS = {
    "cdot": "·",
    "times": "×",
    "div": "÷",
    "pm": "±",
    "mp": "∓",
    "le": "≤",
    "leq": "≤",
    "ge": "≥",
    "geq": "≥",
    "ne": "≠",
    "neq": "≠",
    "approx": "≈",
    "sim": "∼",
    "propto": "∝",
    "infty": "∞",
    "to": "→",
    "rightarrow": "→",
    "leftarrow": "←",
    "Rightarrow": "⇒",
    "leftrightarrow": "↔",
    "partial": "∂",
    "nabla": "∇",
    "sum": "∑",
    "prod": "∏",
    "int": "∫",
    "circ": "°",
    "degree": "°",
    "ldots": "…",
    "dots": "…",
    "cdots": "⋯",
    "quad": " ",
    "qquad": "  ",
    ",": " ",
    ";": " ",
    ":": " ",
    "!": "",
    " ": " ",
    "%": "%",
    "$": "$",
    "&": "&",
    "#": "#",
    "_": "_",
    "{": "{",
    "}": "}",
    "angle": "∠",
    "perp": "⊥",
    "parallel": "∥",
    "in": "∈",
}
OPERATORS = {
    "cdot",
    "times",
    "div",
    "pm",
    "mp",
    "le",
    "leq",
    "ge",
    "geq",
    "ne",
    "neq",
    "approx",
    "sim",
    "propto",
    "to",
    "rightarrow",
    "leftarrow",
    "Rightarrow",
    "leftrightarrow",
    "in",
    "perp",
    "parallel",
}
FUNCTIONS = {
    "sin",
    "cos",
    "tan",
    "cot",
    "arcsin",
    "arccos",
    "arctan",
    "log",
    "ln",
    "exp",
    "lim",
    "max",
    "min",
    "det",
}
TEXT_COMMANDS = {
    "text",
    "mathrm",
    "mathbf",
    "mathit",
    "operatorname",
    "textrm",
    "mathsf",
    "boldsymbol",
    "vec",
    "overline",
    "bar",
    "hat",
}
SUPERSCRIPTS = dict(zip("0123456789+-=()niox", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱᵒˣ"))
SUBSCRIPTS = dict(zip("0123456789+-=()aeoxnmt", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₒₓₙₘₜ"))
SUPERSCRIPT = str.maketrans(SUPERSCRIPTS)


def plain_text(text: str) -> str:
    """The text with its $…$ and $$…$$ math converted to plain Unicode text."""
    converted = MATH.sub(lambda m: latex_to_text(m.group(1) or m.group(2)), text)
    return converted.replace("\\$", "$")


def latex_to_text(source: str) -> str:
    text, _ = _parse(source.strip(), 0, stop=None)
    return re.sub(r"\s+", " ", text).strip()


def _parse(src: str, i: int, stop: str | None) -> tuple[str, int]:
    out: list[str] = []
    while i < len(src):
        char = src[i]
        if stop and char == stop:
            return "".join(out), i + 1
        if char == "{":
            inner, i = _parse(src, i + 1, "}")
            out.append("," if inner == "," else inner)  # 9{,}81 → 9,81
        elif char == "\\":
            piece, i = _command(src, i + 1)
            out.append(piece)
        elif char in "^_":
            arg, i = _argument(src, i + 1)
            out.append(_script(arg, char == "^"))
        elif char == "~":
            out.append(" ")
            i += 1
        else:
            out.append(char)
            i += 1
    return "".join(out), i


def _argument(src: str, i: int) -> tuple[str, int]:
    while i < len(src) and src[i] == " ":
        i += 1
    if i >= len(src):
        return "", i
    if src[i] == "{":
        return _parse(src, i + 1, "}")
    if src[i] == "\\":
        return _command(src, i + 1)
    return src[i], i + 1


def _command(src: str, i: int) -> tuple[str, int]:
    match = re.match(r"[A-Za-z]+", src[i:])
    if not match:  # a single-character command such as \, or \%
        return SYMBOLS.get(src[i : i + 1], src[i : i + 1]), i + 1
    name = match.group()
    i += len(name)
    # LaTeX ignores spaces after a command name; keep them before an operator
    # (\sigma = F) but join a following symbol (\Delta F → ΔF).
    spaces = re.match(r" +(?=[A-Za-z0-9({\\])", src[i:])
    if spaces:
        i += len(spaces.group())
    if name == "frac" or name in ("dfrac", "tfrac"):
        numerator, i = _argument(src, i)
        denominator, i = _argument(src, i)
        return f"{_wrap(numerator)}/{_wrap(denominator)}", i
    if name == "sqrt":
        degree = ""
        if i < len(src) and src[i] == "[":
            end = src.index("]", i)
            degree, i = src[i + 1 : end], end + 1
        radicand, i = _argument(src, i)
        prefix = degree.translate(SUPERSCRIPT) if degree else ""
        return f"{prefix}√{_wrap(radicand)}", i
    if name in TEXT_COMMANDS:
        return _argument(src, i)
    if name in ("left", "right", "big", "Big", "bigl", "bigr", "displaystyle"):
        return "", i
    if name in GREEK:
        return GREEK[name], i
    if name in OPERATORS:  # binary operators and relations get spaces around them
        return f" {SYMBOLS[name]} ", i
    if name in SYMBOLS:
        return SYMBOLS[name], i
    if name in FUNCTIONS:
        return name, i
    return name, i


def _wrap(value: str) -> str:
    """Parenthesises a fraction part or radicand made of several terms."""
    value = value.strip()
    if (
        len(value) > 1
        and re.search(r"[\s+\-−·×/]", value)
        and not (value.startswith("(") and value.endswith(")"))
    ):
        return f"({value})"
    return value


def _script(value: str, superscript: bool) -> str:
    """Unicode super/subscript characters when all exist, else ^x / _x."""
    if superscript and value == "°":  # ^\circ
        return "°"
    table = SUPERSCRIPTS if superscript else SUBSCRIPTS
    if value and all(char in table for char in value):
        return "".join(table[char] for char in value)
    return ("^" if superscript else "_") + (value if len(value) == 1 else f"({value})")
