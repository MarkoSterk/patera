# patera-desktop

Experimental desktop applications with Patera and pywebview. Part of [Patera](https://github.com/MarkoSterk/Patera), a modular async-first Python web framework.

> **Experimental.** This package is not yet ready for production use; its API may change in any release.

## Installation

```sh
pip install patera-desktop
# or, with uv
uv add "patera[desktop]"
```

Requires Python 3.13 or newer and `patera>=0.121`.

## Usage

`patera-desktop` runs the application in a native window ([pywebview](https://pywebview.flowrl.com)):
`uv run patera desktop --mode dev`. Window options are read from `PATERA_DESKTOP_*` environment
variables (`TITLE`, `WIDTH`, `HEIGHT`, `RESIZABLE`, `FULLSCREEN`, `ICON`, ...).

See the [Desktop applications section of the Patera documentation](https://github.com/MarkoSterk/Patera#desktop-applications) for the full guide.

## License

MIT. See [LICENSE](https://github.com/MarkoSterk/Patera/blob/main/LICENSE).
