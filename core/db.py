import logging

import pymongo
import redis

from core import settings

try:
    client = pymongo.MongoClient(settings.MONGO_HOST, settings.MONGO_PORT)
    appbuy = client.appbuy
except Exception as ex:
    logging.exception(ex)

redis = redis.from_url(settings.REDIS_URL)