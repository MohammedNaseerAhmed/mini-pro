import logging

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from .settings import MONGO_DB, MONGO_URI

logger = logging.getLogger(__name__)


class MongoDB:
    client: MongoClient = None
    db = None


def connect_to_mongo() -> bool:
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000)
        client.admin.command("ping")
        MongoDB.client = client
        MongoDB.db = MongoDB.client[MONGO_DB]
        logger.info("MongoDB connected")
        return True
    except PyMongoError as exc:
        MongoDB.client = None
        MongoDB.db = None
        logger.warning(
            "MongoDB connection skipped: %s. The API will run, but Mongo-dependent routes will fail until the DB is reachable.",
            exc,
        )
        return False


def close_mongo_connection():
    if MongoDB.client:
        MongoDB.client.close()
        logger.info("MongoDB connection closed")


def is_mongo_connected() -> bool:
    return MongoDB.db is not None


def get_db():
    if MongoDB.db is None:
        raise RuntimeError("MongoDB not connected. Verify MONGO_URI/network and restart the backend.")
    return MongoDB.db
