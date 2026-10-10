import pytest_asyncio

from app.db.database import engine


@pytest_asyncio.fixture(autouse=True)
async def _dispose_engine_pool():
    """pytest-asyncio runs each test in a fresh event loop, but the app's module-level
    engine pools asyncpg connections bound to the loop that opened them. Reusing one
    from a closed loop fails with "Event loop is closed" / "another operation is in
    progress". Dropping the pool after each test gives the next test new connections."""
    yield
    await engine.dispose()
