# Browser type definitions

`__init__.pyi` is derived from **webtypy 0.1.8.dev1**, by Simone Giacomelli
and contributors: https://github.com/pyodide/webtypy

Upstream wheel: https://pypi.org/project/webtypy/0.1.8.dev1/
Upstream `js-stubs/__init__.pyi` SHA256:
`64b0ac185ed8ba04024bd41d5dfc16a844175189f1e8f34b5430c76ae35d1e29`.

This derived file is distributed under Mozilla Public License 2.0, supplied in
`LICENSE-MPL-2.0`. The rest of Patera's original code remains under its existing
license. Preserve this notice and the MPL license when redistributing these
definitions. The editable `.pyi` is the preferred source form and is shipped
in the wheel and source distribution.

Changes: normalize WebIDL integer/string aliases and callback declarations;
add missing ECMAScript buffer types; annotate void returns; replace JS default
expressions with stub ellipses; deduplicate dictionary bases and merge overload
groups. JS constructor/mixin override differences are exempted from Python's
override rule. Two genuine WebIDL property-type differences have local ignores.
No missing-name or untyped-call errors are suppressed.

Regenerate with `tools/generate_browser_types.py` and the exact upstream file.
The script checks its hash. `_ecma.pyi` is an original, manually maintained
supplement. Regeneration does not require importing or executing upstream code.
