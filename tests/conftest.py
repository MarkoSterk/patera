"""
Shared fixtures for the Patera test-suite.
"""

from __future__ import annotations

import pytest

from patera.testing import PateraTestClient

from tests.helpers import AppFactory


@pytest.fixture
def make_app(tmp_path):
    """Factory fixture: make_app(controllers=[...], **config) -> Patera app."""
    factory = AppFactory(tmp_path)
    yield factory
    factory.cleanup()


@pytest.fixture
def client_for():
    """
    Returns an async context manager factory running the app's lifespan:

        async with client_for(app) as client:
            await client.get("/")
    """

    def _client(application):
        return PateraTestClient(application)

    return _client
