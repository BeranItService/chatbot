import threading
import sys
import time
import logging
import os
import traceback
from collections import defaultdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('hr.chatbot.db')

SHARE_COLLECTION_NAME = 'runtime'
SHARE_COLLECTION_SIZE = 1e9

class MongoDBCollectionListener(object):
    def handle_incoming_data(self, data):
        return NotImplemented

class MongoDB(object):
    def __init__(self, dbname):
        self.client = None
        self.dbname = dbname
        self.listeners = []
        self.subscribers = defaultdict(list)

    def get_share_collection(self):
        collection_names = self.client[self.dbname].collection_names()
        if SHARE_COLLECTION_NAME not in collection_names:
            logger.info("Creating shared collection")
            self.client[self.dbname].create_collection(
                SHARE_COLLECTION_NAME, capped=True, size=SHARE_COLLECTION_SIZE)
        return self.client[self.dbname][SHARE_COLLECTION_NAME]

    def add_listener(self, listener):
        if isinstance(listener, MongoDBCollectionListener):
            self.listeners.append(listener)
        else:
            raise ValueError("Listener must be the class or sub-class of \
                MongoDBCollectionListener")

    def publish(self, topic, msg):
        collection = self.get_share_collection()
        try:
            collection.insert_one({'topic': topic, 'msg': msg})
        except Exception as ex:
            logger.error(ex)

    def subscribe(self, topic, subscriber):
        if isinstance(subscriber, MongoDBCollectionListener):
            if subscriber in self.subscribers[topic]:
                logger.warn("Subscriber has already registered")
                return
            self.subscribers[topic].append(subscriber)
            self.start_monitoring({'topic': topic})
        else:
            raise ValueError("Subscriber must be the class or sub-class of \
                MongoDBCollectionListener")

    def start_monitoring(self, filter={}):
        timer = threading.Timer(0, self._start_monitoring, kwargs=filter)
        timer.daemon = True
        timer.start()

    def _start_monitoring(self, **filter):
        import pymongo
        while self.client is None:
            time.sleep(0.1)
        collection = self.get_share_collection()
        tailN = 0
        while True:
            cursor = collection.find(filter,
                cursor_type=pymongo.CursorType.TAILABLE_AWAIT,
                no_cursor_timeout=True)
            count = collection.find(filter).count()
            cursor.skip(count - tailN)
            logger.info('Cursor created')
            try:
                while cursor.alive:
                    for doc in cursor:
                        for l in self.listeners:
                            l.handle_incoming_data(doc)
                        for topic, subscribers in self.subscribers.iteritems():
                            if doc.get('topic') == topic:
                                for sub in subscribers:
                                    sub.handle_incoming_data(doc)
                    time.sleep(0.2)
                logger.info('Cursor alive %s', cursor.alive)
            except Exception as ex:
                logger.error(traceback.format_exc())
            finally:
                cursor.close()
            time.sleep(2)


def _init_mongodb(mongodb, host='localhost', port=27017,
        socketTimeoutMS=2000, serverSelectionTimeoutMS=1000):
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

    def print_fps():
        global counter
        start_ts = time.time()
        while True:
            time.sleep(1)
            end_ts = time.time()
            print counter/(end_ts - start_ts)
            with lock:
                counter = 0
            start_ts = end_ts

    counter = 0
    lock = threading.RLock()
    class Listener(MongoDBCollectionListener):
        def handle_incoming_data(self, data):
            print data['msg']['width'], data['msg']['height']
            global counter
            with lock:
                counter += 1

    mongodb.subscribe('camera', Listener())

    job = threading.Timer(0, print_fps)
    job.daemon = True
    job.start()

    while True:
        time.sleep(1)
