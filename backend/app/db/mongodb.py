"""
Isolated MongoDB access. All database I/O goes through this module -- no
other module should import `motor` directly. Connection lifecycle is
managed by the FastAPI app's lifespan handler in main.py.
"""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings

_client: AsyncIOMotorClient | None = None


def connect() -> None:
    global _client
    _client = AsyncIOMotorClient(settings.mongodb_uri)


def close() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None


def get_database() -> AsyncIOMotorDatabase:
    if _client is None:
        raise RuntimeError("MongoDB client is not connected. Call connect() first.")
    return _client[settings.mongodb_db_name]
