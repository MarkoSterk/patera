import pytest
from werkzeug.exceptions import MethodNotAllowed, NotFound

from patera.router import Router


def handler():
    return None


def other():
    return None


def test_match_returns_endpoint_and_params():
    router = Router()
    router.add_route("/users/<int:user_id>", handler, ["GET"], "users.get")
    endpoint, params = router.match("/users/5", "GET")
    assert endpoint is handler
    assert params == {"user_id": 5}


def test_duplicate_endpoint_name_is_rejected():
    router = Router()
    router.add_route("/a", handler, ["GET"], "dup")
    with pytest.raises(ValueError):
        router.add_route("/b", other, ["GET"], "dup")


def test_unknown_path_raises_not_found():
    router = Router()
    router.add_route("/a", handler, ["GET"], "a")
    with pytest.raises(NotFound):
        router.match("/missing", "GET")


@pytest.mark.parametrize("path", ["/items/", "/items"])
def test_method_not_allowed_regardless_of_trailing_slash(path):
    router = Router(strict_slashes=False)
    router.add_route("/items/", handler, ["GET"], "items")
    assert router.match(path, "GET")[0] is handler
    with pytest.raises(MethodNotAllowed) as exc:
        router.match(path, "POST")
    assert "GET" in exc.value.valid_methods


def test_strict_slashes_keeps_not_found_for_other_form():
    router = Router(strict_slashes=True)
    router.add_route("/items/", handler, ["GET"], "items")
    with pytest.raises(NotFound):
        router.match("/items", "POST")
