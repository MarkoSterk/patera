from __future__ import annotations

import asyncio
from unittest.mock import Mock

import pytest

from patera.base_extension import BaseExtension
from patera.controller import Controller
from patera.ctx import child_context, request_context
from patera.middleware import MiddlewareBase
from tests.helpers import make_request


TEMPLATE = '{% for message, status in flashed_messages %}<span class="{{ status or "" }}">{{ message }}</span>{% endfor %}'


class FlashMiddleware(MiddlewareBase):
    async def middleware(self, req):
        return await self.next(req)


def test_components_delegate_to_application(make_app, monkeypatch):
    app = make_app()
    components = [Controller(app), BaseExtension(app), FlashMiddleware(app, Mock())]
    flash = Mock()
    monkeypatch.setattr(app, "flash_message", flash)
    for component in components:
        component.flash_message("Saved", status="success")
        flash.assert_called_with("Saved", "success")
        component.flash_message("Hello")
        flash.assert_called_with("Hello", None)
    assert flash.call_count == 6


def test_storage_order_children_and_context_cleanup(make_app):
    app = make_app()
    with pytest.raises(RuntimeError, match="No active request context"):
        app.flash_message("Outside")
    with request_context(app=app) as parent:
        app.flash_message("First")
        with child_context() as child:
            assert child.flashed_messages is parent.flashed_messages
            app.flash_message("Second", "success")
        assert parent.flashed_messages == [("First", None), ("Second", "success")]
        with request_context(app=app) as nested:
            assert nested.flashed_messages == []
            app.flash_message("Separate")
        assert parent.flashed_messages == [("First", None), ("Second", "success")]
    with request_context(app=app) as fresh:
        assert fresh.flashed_messages == []
    with child_context(app=app) as fresh_child:
        assert fresh_child.flashed_messages == []


@pytest.mark.parametrize("render_method", ["html", "html_from_string", "environment"])
async def test_template_rendering_and_empty_list(make_app, render_method):
    app = make_app(files={"templates/flash.html": TEMPLATE})
    req = make_request(app)

    async def render():
        if render_method == "environment":
            return await app.jinja_environment.from_string(TEMPLATE).render_async()
        source = "flash.html" if render_method == "html" else TEMPLATE
        return (await getattr(req.res, render_method)(source)).body

    assert await render() == ""
    with request_context(app=app, request=req):
        assert await render() == ""
        app.flash_message("<Saved>", "success")
        app.flash_message("Hello")
        expected = (
            '<span class="success">&lt;Saved&gt;</span><span class="">Hello</span>'
        )
        assert await render() == expected
        assert await render() == expected  # Rendering never consumes messages.
    assert await render() == ""
    template = app.jinja_environment.from_string(
        "{{ flashed_messages == [] }}|{{ flashed_messages|length }}|"
        "{% if flashed_messages %}present{% else %}empty{% endif %}"
    )
    assert await template.render_async() == "True|0|empty"


async def test_concurrent_contexts_use_same_cached_template_safely(make_app):
    app = make_app()
    template = app.jinja_environment.from_string(TEMPLATE)
    ready = asyncio.Event()
    count = 0

    async def render_request(message):
        nonlocal count
        with request_context(app=app):
            app.flash_message(message, "info")
            count += 1
            if count == 2:
                ready.set()
            await ready.wait()
            return await template.render_async()

    results = await asyncio.gather(render_request("One"), render_request("Two"))
    assert results == ['<span class="info">One</span>', '<span class="info">Two</span>']
    assert await template.render_async() == ""
