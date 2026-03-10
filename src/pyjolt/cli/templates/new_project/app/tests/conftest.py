"""
Test setup
"""

import pytest
from pyjolt.testing import PyJoltTestClient
from app import Application


@pytest.fixture
async def application():
    yield Application()


@pytest.fixture
async def client(application):
    async with PyJoltTestClient(application) as c:
        yield c
