from __future__ import annotations

import pytest

from patera import HttpStatus, abort, html_abort
from patera.exceptions import (
    AborterException,
    BaseHttpException,
    ExceptionHandler,
    StaticAssetNotFound,
    StaticPageNotFound,
    exception_handler,
    handles,
)
from patera.exceptions.http_exceptions import HtmlAborterException


def test_base_http_exception_has_message():
    exc = BaseHttpException("broken", HttpStatus.CONFLICT, data={"a": 1})
    assert str(exc) == "broken"
    assert exc.status_code == 409
    assert exc.data == {"a": 1}


def test_static_page_not_found_is_a_regular_http_exception():
    exc = StaticPageNotFound("about")
    assert isinstance(exc, Exception)
    assert isinstance(exc, BaseHttpException)
    assert exc.status_code == 404
    assert "about" in exc.message


def test_static_asset_not_found_defaults():
    assert StaticAssetNotFound().status_code == 404


def test_abort_helpers():
    with pytest.raises(AborterException) as exc:
        abort("nope", HttpStatus.NOT_FOUND, data=[1])
    assert exc.value.status_code == 404
    assert exc.value.data == [1]

    with pytest.raises(HtmlAborterException) as html_exc:
        html_abort("err.html", HttpStatus.FORBIDDEN, {"x": 1})
    assert html_exc.value.template == "err.html"
    assert html_exc.value.status_code == 403


def test_handles_does_not_share_state_between_methods(make_app):
    @exception_handler
    class Handlers(ExceptionHandler):
        @handles(ValueError)
        async def value(self, req, exc):
            return req.res.text("v")

        @handles(KeyError, TypeError)
        async def other(self, req, exc):
            return req.res.text("o")

    app = make_app(exception_handlers=[Handlers])
    mapping = app._exception_handlers
    assert mapping[ValueError].__name__ == "value"
    assert mapping[KeyError].__name__ == "other"
    assert mapping[TypeError].__name__ == "other"
