"""Consumer checks ensure the bundled stubs provide real, precise types."""

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def check(path: Path):
    return subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_browser_types_strict_consumers_and_native_import(tmp_path):
    source = tmp_path / "consumer.py"
    source.write_text("""from __future__ import annotations
from typing import TYPE_CHECKING, assert_type, cast
from patera.desktop.ui import Component, event, tag
if TYPE_CHECKING:
    from patera.desktop.ui.types import (
        Event, MouseEvent, KeyboardEvent, InputEvent, SubmitEvent,
        HTMLInputElement, Document, Element, EventTarget, Uint8Array, Promise,
    )

@tag("typed-counter")
class Counter(Component):
    @event("click")
    def click(self, event: MouseEvent) -> None:
        event.preventDefault()
        assert_type(event.button, int)
        assert_type(event.target, EventTarget | None)

def inspect(doc: Document, key: KeyboardEvent, change: InputEvent,
            submit: SubmitEvent, base: Event) -> None:
    assert_type(key.key, str)
    assert_type(change.data, str | None)
    assert_type(doc.querySelector("input"), Element | None)
    field = cast("HTMLInputElement", doc.querySelector("input"))
    assert_type(field.value, str)
    submit.preventDefault()
    base.stopPropagation()

async def builtins(buffer: Uint8Array, promise: Promise[str]) -> None:
    assert_type(buffer[0], int)
    assert_type(buffer.slice(0), Uint8Array)
    assert_type(await promise, str)
""")
    result = check(source)
    assert result.returncode == 0, result.stdout + result.stderr
    subprocess.run([sys.executable, str(source)], cwd=ROOT, check=True)


def test_browser_types_reject_wrong_members_and_values(tmp_path):
    source = tmp_path / "invalid_consumer.py"
    source.write_text("""from patera.desktop.ui.types import MouseEvent, HTMLInputElement
def bad(event: MouseEvent, field: HTMLInputElement) -> None:
    event.not_a_real_property
    field.value = 123
    button: str = event.button
""")
    result = check(source)
    assert result.returncode == 1
    assert 'has no attribute "not_a_real_property"' in result.stdout
    assert result.stdout.count("[assignment]") == 2
    assert "Found 3 errors" in result.stdout


def test_browser_stub_definitions_pass_strict_checking():
    result = check(ROOT / "packages/patera-desktop-ui/src/patera/desktop/ui/types")
    assert result.returncode == 0, result.stdout + result.stderr
