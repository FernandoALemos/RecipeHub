from functools import lru_cache

from django.conf import settings
from pymongo import MongoClient
from pymongo.database import Database


@lru_cache(maxsize=1)
def get_client() -> MongoClient:
    return MongoClient(settings.MONGO_URI)


def get_db() -> Database:
    return get_client()[settings.MONGO_DB_NAME]
