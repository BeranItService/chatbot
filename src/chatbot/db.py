import threading
import sys
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('hr.chatbot.db')

class MongoDB(object):
    def __init__(self, dbname):
        self.client = None
        self.dbname = dbname

def _init_mongodb(mongodb, host='localhost', port=27017, socketTimeoutMS=1000, serverSelectionTimeoutMS=1000):
    import pymongo
    def _init_mongo_client(mongodb):
        while mongodb.client is None:
            mongodb.client = pymongo.MongoClient(
                'mongodb://{}:{}/'.format(host, port),
                socketTimeoutMS=socketTimeoutMS,
                serverSelectionTimeoutMS=serverSelectionTimeoutMS)
            try:
                mongodb.client.admin.command('ismaster')
                logger.warn("Activate mongodb, %s", mongodb)
            except pymongo.errors.ConnectionFailure:
                logger.error("Server not available")
                mongodb.client = None
            time.sleep(0.2)

    timer = threading.Timer(0, _init_mongo_client, (mongodb,))
    timer.daemon = True
    timer.start()
    logger.info("Thread starts")

def get_mongodb(dbname='hr', **kwargs):
    mongodb = MongoDB(dbname)
    _init_mongodb(mongodb, **kwargs)
    return mongodb

if __name__ == '__main__':
    mongodb = get_mongodb()
    while mongodb.client is None:
        time.sleep(0.1)
    print mongodb.client.server_info()
    print mongodb.client.HOST
