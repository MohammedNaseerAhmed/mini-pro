from pymongo import MongoClient

from .settings import MONGO_DB, MONGO_URI


class MongoDB:
    client: MongoClient = None
    db = None


def connect_to_mongo():
    MongoDB.client = MongoClient(MONGO_URI)
    MongoDB.db = MongoDB.client[MONGO_DB]
    print("MongoDB Atlas connected")


def close_mongo_connection():
    if MongoDB.client:
        MongoDB.client.close()
        print("MongoDB connection closed")


def get_db():
    if MongoDB.db is None:
        raise Exception("MongoDB not connected. Startup event not triggered.")
    return MongoDB.db
