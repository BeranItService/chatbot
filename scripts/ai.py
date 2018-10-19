#!/usr/bin/env python

import rospy
import os
import logging
import time
import datetime as dt
import threading
import re
import uuid
import pandas as pd
import traceback

from chatbot.cfg import ChatbotConfig
from chatbot.client import Client
from chatbot.db import get_mongodb, MongoDB
from chatbot.polarity import Polarity
from dynamic_reconfigure.server import Server
from hr_msgs.msg import Forget, ForgetAll, Assign, State
from hr_msgs.msg import audiodata, SetGesture, Target, ChatMessage, TTS
from jinja2 import Template
from std_msgs.msg import String
import dynamic_reconfigure
import dynamic_reconfigure.client

logger = logging.getLogger('hr.chatbot.ai')
HR_CHATBOT_AUTHKEY = os.environ.get('HR_CHATBOT_AUTHKEY', 'AAAAB3NzaC')
HR_CHATBOT_REQUEST_DIR = os.environ.get('HR_CHATBOT_REQUEST_DIR') or \
    os.path.expanduser('~/.hr/chatbot/requests')
ROBOT_NAME = os.environ.get('NAME', 'default')
count = 0

def update_parameter(node, param, *args, **kwargs):
    client = dynamic_reconfigure.client.Client(node, *args, **kwargs)
    try:
        client.update_configuration(param)
    except dynamic_reconfigure.DynamicReconfigureParameterException as ex:
        logger.error("Updating {} parameter: {}".format(node, ex))
        return False
    return True

class Console(object):
    def write(self, msg):
        logger.info("Console: {}".format(msg.strip()))

class Locker(object):

    def __init__(self):
        self._lock = threading.RLock()

    def lock(self):
        self._lock.acquire()

    def unlock(self):
        self._lock.release()

class Chatbot():

    def __init__(self):
        self.botname = rospy.get_param('botname', 'sophia')
        self.client = Client(
            HR_CHATBOT_AUTHKEY, self.botname, response_listener=self,
            stdout=Console())
        self.client.chatbot_url = rospy.get_param(
            'chatbot_url', 'http://localhost:8001')
        # chatbot now saves a bit of simple state to handle sentiment analysis
        # after formulating a response it saves it in a buffer if S.A. active
        # It has a simple state transition - initialized in wait_client
        # after getting client if S.A. active go to wait_emo
        # in affect_express call back publish response and reset to wait_client
        self._response_buffer = ''
        self._state = 'wait_client'
        # argumment must be  to activate sentiment analysis
        self._sentiment_active = False
        # sentiment dictionary
        self.polarity = Polarity()
        self._polarity_threshold = 0.2
        self.speech = False
        self.enable = True
        self.mute = False
        self.insert_behavior = False
        self.enable_face_recognition = False
        self._locker = Locker()
        try:
            self.mongodb = get_mongodb()
        except Exception as ex:
            self.mongodb = MongoDB()

        self.node_name = rospy.get_name()
        self.output_dir = os.path.join(HR_CHATBOT_REQUEST_DIR,
            dt.datetime.strftime(dt.datetime.utcnow(), '%Y%m%d'))
        if not os.path.isdir(self.output_dir):
            os.makedirs(self.output_dir)
        self.requests_fname = os.path.join(
            self.output_dir, '{}.csv'.format(str(uuid.uuid1())))

        self.input_stack = []
        self.timer = None
        self.delay_response = rospy.get_param('delay_response', False)
        self.recover = False
        self.delay_time = rospy.get_param('delay_time', 5)

        self.run_id = rospy.get_param('/run_id', '')
        self.client.set_run_id(self.run_id)
        logger.info("Set run_id %s", self.run_id)

        rospy.Subscriber('chatbot_speech', ChatMessage, self._request_callback)
        rospy.Subscriber('speech_events', String, self._speech_event_callback) # robot starts to speak
        rospy.Subscriber('chat_events', String, self._chat_event_callback) # user starts to speak

        rospy.Subscriber('audio_sensors', audiodata, self._audio_sensors_callback)
        self.tts_ctrl_pub = rospy.Publisher(
            'tts_control', String, queue_size=1)

        self._response_publisher = rospy.Publisher(
            'chatbot_responses', TTS, queue_size=1)

        # send communication non-verbal blink message to behavior
        self._blink_publisher = rospy.Publisher(
            'chatbot_blink', String, queue_size=1)

        # Perceived emotional content; and emotion to express
        # Perceived: based on what chatbot heard, this is how robot should
        # feel.  Expressed: the emotional content that the chatbot should
        # put into what it says.
        self._affect_publisher = rospy.Publisher(
            'chatbot_affect_perceive', String, queue_size=1)

        # Echo chat messages as plain strings.
        self._echo_publisher = rospy.Publisher(
            'perceived_text', String, queue_size=1)
        rospy.Subscriber('chatbot_speech', ChatMessage, self._echo_callback)
        rospy.set_param('node_status/chatbot', 'running')

        self.btree_publisher = rospy.Publisher(
            '/behavior_switch', String, queue_size=1)

        self._gesture_publisher = rospy.Publisher(
            '/blender_api/set_gesture', SetGesture, queue_size=1)
        self._look_at_publisher = rospy.Publisher(
            '/blender_api/set_face_target', Target, queue_size=1)

        # r2_perception
        self._perception_assign_publisher = rospy.Publisher(
            'perception/api/assign', Assign, queue_size=1)
        self._perception_forget_publisher = rospy.Publisher(
            'perception/api/forget', Forget, queue_size=1)
        self._perception_forget_all_publisher = rospy.Publisher(
            'perception/api/forget_all', ForgetAll, queue_size=1)
        self._perception_state_subscriber = rospy.Subscriber(
            'perception/state', State, self._perception_state_callback)

        self.perception_users = {}
        self.face_cache = []
        self.main_face = None
        self.faces = {} # faceid(session) -> face
        self.current_user = None

    def _threadsafe(f):
        def wrap(self, *args, **kwargs):
            self._locker.lock()
            try:
                return f(self, *args, **kwargs)
            finally:
                self._locker.unlock()
        return wrap

    def _perception_state_callback(self, msg):
        global count
        count += 1
        self.face_cache.extend(msg.faces)
        if count % 30 == 0:
            count = 0
            self.perception_users = {}
            for face in self.face_cache:
                self.perception_users[face.fsdk_id] = face
            faces = self.perception_users.values()

            self.face_cache = []
            if faces:
                faces = sorted(faces, key=lambda face: face.position.x*face.position.x+face.position.y*face.position.y+face.position.z*face.position.z)
                active_face = None
                for face in faces:
                    if face.is_speaking:
                        active_face = face
                        logger.info("%s is speaking" % face.fsdk_id)
                if not active_face:
                    active_face = faces[0] # the closest face
                if self.main_face is None:
                    self.main_face = active_face
                    logger.warn("Assigned main face ID %s, first name %s" % (self.main_face.fsdk_id, self.main_face.first_name))
                elif self.main_face.fsdk_id != active_face.fsdk_id:
                    logger.warn("Main face ID has been changed from %s to %s" % (self.main_face.fsdk_id, active_face.fsdk_id))
                    self.main_face = active_face
            else:
                if self.main_face:
                    logger.warn("Removed main face ID %s, first name %s" % (self.main_face.fsdk_id, self.main_face.first_name))
                    self.main_face = None

    def assign_name(self, fsdk_id, firstname, lastname=None):
        assign = Assign()
        assign.fsdk_id = fsdk_id
        assign.first_name = str(firstname)
        assign.last_name = str(lastname)
        assign.formal_name = str(firstname)
        logger.info("Assigning name %s to face id %s" % (firstname, fsdk_id))
        self._perception_assign_publisher.publish(assign)
        logger.info("Assigned name %s to face id %s" % (firstname, fsdk_id))

    def forget_name(self, uid):
        self._perception_forget_publisher.publish(Forget(uid))
        logger.info("Forgot name uid %s" % uid)

    def sentiment_active(self, active):
        self._sentiment_active = active

    def ask(self, chatmessages, query=False):
        if chatmessages and len(chatmessages) > 0:
            self.client.lang = chatmessages[0].lang
            if self.enable_face_recognition and self.main_face: # visual perception
                self.client.set_user(self.main_face.fsdk_id)
                self.faces[self.main_face.fsdk_id] = self.main_face
                for face in self.faces.values():
                    if face.fsdk_id == self.main_face.fsdk_id and face.uid:
                        fullname = '{} {}'.format(face.first_name, face.last_name)
                        self.client.set_context('fullname={}'.format(fullname))
                        logger.info("Set context fullname %s" % fullname)
                        if face.formal_name:
                            self.client.set_context('firstname={}'.format(face.formal_name))
                            logger.info("Set context fistname %s" % face.first_name)
                        else:
                            self.client.set_context('firstname={}'.format(face.first_name))
                            logger.info("Set context fistname %s" % face.formal_name)
                        self.client.set_context('lastname={}'.format(face.last_name))
                        logger.info("Set context lastname %s" % face.last_name)
            else:
                if self.current_user:
                    self.client.set_user(self.current_user)
                    if '_' in self.current_user:
                        first, last = self.current_user.split('_', 1)
                        self.client.set_context('firstname={},lastname={},fullname={}'.format(first, last, self.current_user))
                        logger.info("Set context first name %s" % first)
                        logger.info("Set context last name %s" % last)
                    else:
                        self.client.set_context('name={}'.format(self.current_user))
                        logger.info("Set context name %s" % self.current_user)
        else:
            logger.error("No language is specified")
            return

        request_id = str(uuid.uuid1())
        question = ' '.join([msg.utterance for msg in chatmessages])
        logger.info("Asking {}".format(question))
        #if self.main_face:
        #    self.client.ask('[start]', query, request_id=request_id)
        self.client.ask(question, query, request_id=request_id)
        logger.info("Sent request {}".format(request_id))
        self.write_request(request_id, chatmessages)

    def _speech_event_callback(self, msg):
        if msg.data == 'start':
            self.speech = True
        if msg.data == 'stop':
            self.speech = False

    def _chat_event_callback(self, msg):
        if msg.data.startswith('speechstart'):
            if self.delay_response:
                self.reset_timer()

    def _audio_sensors_callback(self, msg):
        if msg.Speech:
            self.client.cancel_timer()

    @_threadsafe
    def _request_callback(self, chat_message):
        if not self.enable:
            logger.warn("Chatbot is disabled")
            return
        if 'shut up' in chat_message.utterance.lower():
            logger.info("Robot's talking wants to be interruptted")
            self.tts_ctrl_pub.publish("shutup")
            rospy.sleep(0.5)
            self._affect_publisher.publish(String('sad'))
            if not self.mute:
                self._response_publisher.publish(
                    TTS(text='Okay', lang=chat_message.lang))
            return
        if self.speech:
            logger.warn("In speech, ignore the question")
            return

        # Handle chatbot command
        cmd, arg, line = self.client.parseline(chat_message.utterance)
        func = None
        try:
            if cmd is not None:
                func = getattr(self.client, 'do_' + cmd)
        except AttributeError as ex:
            pass
        if func:
            try:
                func(arg)
            except Exception as ex:
                logger.error("Executing command {} error {}".format(func, ex))
            return

        chat_message.utterance = self.handle_control(chat_message.utterance)

        # blink that we heard something, request, probability defined in
        # callback
        self._blink_publisher.publish('chat_heard')

        if self.delay_response:
            logger.info("Add input: {}".format(chat_message.utterance))
            self.input_stack.append((time.clock(), chat_message))
            self._gesture_publisher.publish(SetGesture('nod-2', 0, 1, 1))
            self._gesture_publisher.publish(SetGesture('blink-relaxed', 0, 1, 1))
            self.reset_timer()
        else:
            self.ask([chat_message])

    def reset_timer(self):
        if self.timer is not None:
            self.timer.cancel()
            logger.info("Canceled timer, {}".format(self.delay_time))
            self.timer = None
        self.timer = threading.Timer(self.delay_time, self.process_input)
        self.timer.start()
        logger.info("New timer, {}".format(self.delay_time))

    @_threadsafe
    def process_input(self):
        if not self.input_stack:
            return
        questions = [i[1].utterance for i in self.input_stack]
        question = ' '.join(questions)
        logger.info("Joined input: {}".format(question))
        self.ask([i[1] for i in self.input_stack])
        del self.input_stack[:]

    def write_request(self, request_id, chatmessages):
        requests = []
        columns = ['Datetime', 'RequestId', 'Index', 'Source', 'AudioPath', 'Transcript', 'Confidence']
        for i, msg in enumerate(chatmessages):
            audio = os.path.basename(msg.audio_path)
            request = {
                'Datetime':  dt.datetime.utcnow(),
                'RequestId': request_id,
                'Index': i,
                'Source': msg.source,
                'AudioPath': audio,
                'Transcript': msg.utterance,
                'RunID': self.run_id,
                'Confidence': msg.confidence,
            }
            requests.append(request)
        if self.mongodb.client is not None:
            try:
                mongocollection = self.mongodb.client[self.mongodb.dbname][ROBOT_NAME]['chatbot']['requests']
                result = mongocollection.insert_many(requests)
                logger.info("Added requests to mongodb")
            except Exception as ex:
                self.mongodb.client = None
                logger.error(traceback.format_exc())
                logger.warn("Deactivate mongodb")

        df = pd.DataFrame(requests)
        if not os.path.isfile(self.requests_fname):
            with open(self.requests_fname, 'w') as f:
                f.write(','.join(columns))
                f.write('\n')
        df.to_csv(self.requests_fname, mode='a', index=False, header=False,
            columns=columns)
        logger.info("Write request to {}".format(self.requests_fname))

    def handle_control(self, response):
        t = Template(response)
        if hasattr(t.module, 'delay'):
            delay = t.module.delay
            if not self.delay_response:
                self.recover = True
            param = {'delay_time': delay}
            param['delay_response'] = delay > 0
            update_parameter('chatbot', param, timeout=2)
            logger.info("Set delay to {}".format(delay))
        if hasattr(t.module, 'btree'):
            btree = t.module.btree
            if btree in ['btree_on', 'on', 'true', True]:
                self.btree_publisher.publish('btree_on')
                logger.info("Enable btree")
            elif btree in ['btree_off', 'off', 'false', False]:
                self.btree_publisher.publish('btree_off')
                logger.info("Disable btree")
            else:
                logger.warn("Incorrect btree argument, {}".format(btree))
        return t.render()

    def on_response(self, sid, response):
        if response is None:
            logger.error("No response")
            return

        if sid != self.client.session:
            logger.error("Session id doesn't match")
            return

        logger.info("Get response {}".format(response))

        for k, v in response.iteritems():
            rospy.set_param('{}/response/{}'.format(self.node_name, k), v)

        text = response.get('text')
        emotion = response.get('emotion')
        lang = response.get('lang', 'en-US')

        orig_text = response.get('orig_text')
        if orig_text:
            try:
                self.handle_control(orig_text)
            except Exception as ex:
                logger.error(ex)
        #elif self.recover:
        #    param = {
        #        'delay_response': False
        #    }
        #    update_parameter('chatbot', param, timeout=2)
        #    self.recover = False
        #    logger.info("Recovered delay response")

        # Add space after punctuation for multi-sentence responses
        text = text.replace('?', '? ')
        text = text.replace('_', ' ')
        if self.insert_behavior:
            # no
            pattern=r"(\bnot\s|\bno\s|\bdon't\s|\bwon't\s|\bdidn't\s)"
            text = re.sub(pattern, '\g<1>|shake3| ', text, flags=re.IGNORECASE)

            # yes
            pattern=r'(\byes\b|\byeah\b|\byep\b)'
            text = re.sub(pattern, '\g<1>|nod|', text, flags=re.IGNORECASE)

            # question
            # pattern=r'(\?)'
            # thinks = ['thinkl', 'thinkr', 'thinklu', 'thinkld', 'thinkru', 'thinkrd']
            # random.shuffle(thinks)
            # text = re.sub(pattern, '|{}|\g<1>'.format(thinks[0]), text, flags=re.IGNORECASE)

        # if sentiment active save state and wait for affect_express to publish response
        # otherwise publish and let tts handle it
        if self._sentiment_active:
            emo = String()
            if emotion:
                emo.data = emotion
                self._affect_publisher.publish(emo)
                rospy.loginfo(
                    '[#][PERCEIVE ACTION][EMOTION] {}'.format(emo.data))
                logger.info('Chatbot perceived emo: {}'.format(emo.data))
            else:
                p = self.polarity.get_polarity(text)
                logger.debug('Polarity for "{}" is {}'.format(
                    text.encode('utf-8'), p))
                # change emotion if polarity magnitude exceeds threshold defined in constructor
                # otherwise let top level behaviors control
                if p > self._polarity_threshold:
                    emo.data = 'happy'
                    self._affect_publisher.publish(emo)
                    rospy.loginfo(
                        '[#][PERCEIVE ACTION][EMOTION] {}'.format(emo.data))
                    logger.info(
                        'Chatbot perceived emo: {}'.format(emo.data))
                    # Currently response is independant of message received so no need to wait
                    # Leave it for Opencog to handle responses later on.
                elif p < 0 and abs(p) > self._polarity_threshold:
                    emo.data = 'frustrated'
                    self._affect_publisher.publish(emo)
                    rospy.loginfo(
                        '[#][PERCEIVE ACTION][EMOTION] {}'.format(emo.data))
                    logger.info(
                        'Chatbot perceived emo: {}'.format(emo.data))
                    # Currently response is independant of message received so no need to wait
                    # Leave it for Opencog to handle responses later on.

        if not self.mute:
            self._blink_publisher.publish('chat_saying')
            log_data = {}
            log_data.update(response)
            log_data['performance_report'] = True
            logger.warn('Chatbot response: %s', text, extra={'data': log_data})
            self._response_publisher.publish(TTS(text=text, lang=lang))

        if rospy.has_param('{}/context'.format(self.node_name)):
            rospy.delete_param('{}/context'.format(self.node_name))
        context = self.client.get_context()
        logger.warn("Get context %s" % context)
        context['sid'] = self.client.session
        for k, v in context.iteritems():
            rospy.set_param('{}/context/{}'.format(self.node_name, k), v)
            logger.info("Set param {}={}".format(k, v))

        if self.enable_face_recognition:
            # Assign known name to the percepted faces
            face_id = self.client.user
            if face_id in self.perception_users:
                uid = self.perception_users[face_id].uid
                context_firstname = context.get('firstname')
                context_lastname = context.get('lastname')
                firstname = self.perception_users[face_id].first_name
                if not uid:
                    self.assign_name(face_id, context_firstname, context_lastname)
                elif uid and firstname != context_firstname:
                    logger.warn("Update the name of face id %s from %s to %s" % (
                        face_id, firstname, context_firstname))
                    self.forget_name(uid)
                    self.assign_name(face_id, context_firstname, context_lastname)
                else:
                    logger.warn("Failed to update name of face id %s from %s to %s" % (
                        face_id, firstname, context_firstname))
            else:
                logger.warn("User %s is out of scene" % face_id)
                logger.warn("Perception face %s" % str(self.perception_users.keys()))

    # Just repeat the chat message, as a plain string.
    def _echo_callback(self, chat_message):
        message = String()
        message.data = chat_message.utterance
        self._echo_publisher.publish(message)

    def reconfig(self, config, level):
        self.sentiment_active(config.sentiment)
        self.client.chatbot_url = config.chatbot_url
        self.enable = config.enable
        if not self.enable:
            self.client.cancel_timer()
        self.delay_response = config.delay_response
        self.delay_time = config.delay_time
        self.client.ignore_indicator = config.ignore_indicator
        if config.set_that:
            self.client.do_said(config.set_that)
            config.set_that = ''

        if config.set_context:
            self.client.set_context(config.set_context)

        self.enable_face_recognition = config.enable_face_recognition
        if not self.enable_face_recognition:
            self.client.set_user()

        marker = '%s:%s' % (config.type_of_marker, config.marker)
        self.client.set_marker(marker)
        self.mute = config.mute
        self.insert_behavior = config.insert_behavior
        if config.preset_user and config.preset_user != self.current_user:
            self.current_user = config.preset_user
            config.user = ''
            logger.info("Set preset user %s" % self.current_user)
        if config.user and config.user != self.current_user:
            self.current_user = config.user
            config.preset_user = ''
            logger.info("Set current user %s" % self.current_user)

        if config.reset_session:
            self.client.reset_session()
            config.reset_session = Fales
        return config

if __name__ == '__main__':
    rospy.init_node('chatbot')
    bot = Chatbot()
    from rospkg import RosPack
    rp = RosPack()
    data_dir = os.path.join(rp.get_path('chatbot'), 'scripts/aiml')
    sent3_file = os.path.join(data_dir, "senticnet3.props.csv")
    bot.polarity.load_sentiment_csv(sent3_file)
    Server(ChatbotConfig, bot.reconfig)
    rospy.spin()
