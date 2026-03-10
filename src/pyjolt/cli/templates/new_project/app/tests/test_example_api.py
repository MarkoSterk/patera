"""
User API tests

Add as many tests as you want here.
"""


async def test_get_users(client):
    res = await client.get("/api/v1/examples")
    assert res.status_code == 200
