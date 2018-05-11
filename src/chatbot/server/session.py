import threading
import time
import os
import sys
import datetime as dt
import logging
import traceback
import uuid
from config import HISTORY_DIR, TEST_HISTORY_DIR, SESSION_REMOVE_TIMEOUT
from response_cache import ResponseCache
from collections import defaultdict
from chatbot.server.character import TYPE_AIML
from chatbot.db import get_mongodb, MongoDB

logger = logging.getLogger('hr.chatbot.server.session')

try:
    mongodb = get_mongodb()
except ImportError as ex:
    mongodb = MongoDB()
    logger.error(ex)

ROBOT_NAME = os.environ.get('NAME', 'default')

class SessionContext(dict):

    def __init__(self):
        self.context = defaultdict(dict)

    def __setitem__(self, key, item):
        self.__dict__[key] = item

    def __getitem__(self, key):
        return self.__dict__[key]

    def __len__(self):
        return len(self.__dict__)

    def __delitem__(self, key):
        del self.__dict__[key]

    def __repr__(self):
        return repr(self.__dict__)

    def set_context(self, cid, context):
        self.context[cid].update(context)

    def get_context(self, cid):
        return self.context[cid]

    def reset_context(self, cid):
        self.context[cid] = {}

class Session(object):

    def __init__(self, sid):
        self.sid = sid
        self.session_context = SessionContext()
        self.cache = ResponseCache()
        self.created = dt.datetime.utcnow()
        self.characters = []
        dirname = os.path.join(HISTORY_DIR, self.created.strftime('%Y%m%d'))
        test_dirname = os.path.join(
            TEST_HISTORY_DIR, self.created.strftime('%Y%m%d'))
        self.fname = os.path.join(dirname, '{}.csv'.format(self.sid))
        self.test_fname = os.path.join(test_dirname, '{}.csv'.format(self.sid))
        self.dump_file = None
        self.closed = False
        self.active = False
        self.last_active_time = None
        self.test = False
        self.last_used_character = None
        self.open_character = None

    def set_test(self, test):
        if test:
            logger.info("Set test session")
        self.test = test

    def add(self, question, answer, **kwargs):
        if not self.closed:
            time = dt.datetime.utcnow()
            self.cache.add(question, answer, time, **kwargs)
            self.dump()
            self.last_active_time = self.cache.last_time
            self.active = True
            if mongodb.client is not None:
                chatlog = {'Datetime': time.timestamp(), 'Question': question, "Answer": answer}
                chatlog.update(kwargs)
                try:
                    mongocollection = mongodb.client[mongodb.dbname][ROBOT_NAME]['chatbot']['chatlogs']
                    result = mongocollection.insert_one(chatlog)
                    logger.info("Added chatlog to mongodb, id %s", result.inserted_id)
                    sharecollection = mongodb.get_share_collection()
                    result = sharecollection.insert_one({'node': 'chatbot', 'msg':chatlog})
                    logger.info("Added chatlog to share collection, id %s", result.inserted_id)
                except Exception as ex:
                    mongodb.client = None
                    logger.error(traceback.format_exc())
                    logger.warn("Deactivate mongodb")
            return True
        return False

    def rate(self, rate, idx):
        return self.cache.rate(rate, idx)

    def set_characters(self, characters):
        self.characters = characters
        for c in self.characters:
            if c.type != TYPE_AIML:
                continue
            prop = c.get_properties()
            context = {}
            for key in ['weather', 'location', 'temperature']:
                if key in prop:
                    context[key] = prop.get(key)
            now = dt.datetime.utcnow()
            context['time'] = dt.datetime.strftime(now, '%I:%M %p')
            context['date'] = dt.datetime.strftime(now, '%B %d %Y')
            try:
                c.set_context(self, context)
            except Exception as ex:
                pass

    def close(self):
        self.reset()
        self.closed = True

    def reset(self):
        self.cache.clean()
        self.last_used_character = None
        self.open_character = None
        for c in self.characters:
            try:
                c.refresh(self)
            except NotImplementedError:
                pass

    def check(self, question, answer):
        return self.cache.check(question, answer)

    def dump(self):
        if self.test:
            self.dump_file = self.test_fname
        else:
            self.dump_file = self.fname
        return self.test or self.cache.dump(self.dump_file)

    def since_idle(self, since):
        if self.last_active_time is not None:
            return (since - self.last_active_time).total_seconds()
        else:
            return (since - self.created).total_seconds()

    def __repr__(self):
        return "<Session {} created {} active {}>".format(
            self.sid, self.created, self.cache.last_time)


class Locker(object):

    def __init__(self):
        self._lock = threading.RLock()

    def lock(self):
        self._lock.acquire()

    def unlock(self):
        self._lock.release()


class SessionManager(object):

    def __init__(self, auto_clean=True):
        self._sessions = dict()
        self._users = defaultdict(dict)
        self._locker = Locker()
        self._session_cleaner = threading.Thread(
            target=self._clean_sessions, name="SessionCleaner")
        self._session_cleaner.daemon = True
        if auto_clean:
            self._session_cleaner.start()

    def _threadsafe(f):
        def wrap(self, *args, **kwargs):
            self._locker.lock()
            try:
                return f(self, *args, **kwargs)
            finally:
                self._locker.unlock()
        return wrap

    @_threadsafe
    def remove_session(self, sid):
        if sid in self._sessions:
            session = self._sessions.pop(sid)
            session.dump()
            session.close()
            del session
            logger.info("Removed session {}".format(sid))

    def reset_session(self, sid):
        if sid in self._sessions:
            session = self._sessions.get(sid)
            if session.active:
                session.reset()
                logger.warn("Reset session {}".format(sid))
 
    def get_session(self, sid):
        if sid is not None:
            return self._sessions.get(sid, None)

    def get_sid(self, client_id, user):
        if client_id in self._users:
            sessions = self._users.get(client_id)
            if sessions:
                sid = sessions.get(user)
                session = self._sessions.get(sid)
                if session:
                    return sid

    def gen_sid(self):
        return str(uuid.uuid1())

    @_threadsafe
    def add_session(self, client_id, user, sid):
        if sid in self._sessions:
            return False
        if sid is None:
            return False
        session = Session(sid)
        session.session_context.user = user
        session.session_context.client_id = client_id
        self._sessions[sid] = session
        self._users[client_id][user] = sid
        return True

    def start_session(self, client_id, user, test=False, refresh=False):
        """
        client_id: client id
        user: user to identify session in user scope
        test: if it's a session for test
        refresh: if true, it will generate new session id
        """
        _sid = self.get_sid(client_id, user)
        if _sid and refresh:
            self.remove_session(_sid)
            _sid = None
        if not _sid:
            _sid = self.gen_sid()
            self.add_session(client_id, user, _sid)
        session = self.get_session(_sid)
        assert(session is not None)
        session.set_test(test)
        return _sid

    def has_session(self, sid):
        return sid in self._sessions

    def _clean_sessions(self):
        while True:
            remove_sessions = []
            since = dt.datetime.utcnow()
            for sid, s in self._sessions.iteritems():
                if s.since_idle(since) > SESSION_REMOVE_TIMEOUT:
                    remove_sessions.append(sid)
            for sid in remove_sessions:
                self.remove_session(sid)
            time.sleep(0.1)

    def list_sessions(self):
        return self._sessions.values()


class ChatSessionManager(SessionManager):

    def __init__(self, auto_clean=True):
        super(ChatSessionManager, self).__init__(auto_clean)

    def dump_all(self):
        fnames = []
        for sid, sess in self._sessions.iteritems():
            if sess and sess.dump():
                fnames.append(sess.dump_file)
        return fnames

    def dump(self, sid):
        fname = None
        sess = self._sessions.get(sid)
        if sess:
            sess.dump()
            fname = sess.dump_file
        return fname
