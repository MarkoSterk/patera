import pytest
from conftest import SECRET


@pytest.mark.parametrize(
    ("tunnel", "expected"),
    [
        (None, "http://localhost:3000"),
        ("", "http://localhost:3000"),
        ("cool-name-here", "https://cool-name-here.trycloudflare.com"),
        (
            "cool-name-here.trycloudflare.com",
            "https://cool-name-here.trycloudflare.com",
        ),
        (
            "https://cool-name-here.trycloudflare.com/",
            "https://cool-name-here.trycloudflare.com",
        ),
    ],
)
def test_exam_base_url(tunnel, expected):
    from app.configs import Config

    config = Config(SECRET_KEY=SECRET, CLOUDFLARE_TUNNEL_URL=tunnel)
    assert config.exam_base_url == expected


def test_tunnel_from_environment(monkeypatch):
    from app.configs import Config

    monkeypatch.setenv("PATERA_CLOUDFLARE_TUNNEL_URL", "from-env")
    config = Config(SECRET_KEY=SECRET)
    assert config.exam_base_url == "https://from-env.trycloudflare.com"
