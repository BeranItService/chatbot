# -*- coding: utf-8 -*-
import traceback
import logging
import random
import os
import re
import sys
import numpy as np
import datetime as dt
reload(sys)
sys.setdefaultencoding('utf-8')
import atexit
from collections import defaultdict, OrderedDict

from threading import RLock
sync = RLock()

import codes

SUCCESS = 0
WRONG_CHARACTER_NAME = 1
NO_PATTERN_MATCH = 2
INVALID_SESSION = 3
INVALID_QUESTION = 4
TRANSLATE_ERROR = 5

logger = logging.getLogger('hr.chatbot.server.chatbot_agent')

from loader import load_characters, dyn_properties
from config import CHARACTER_PATH, RESET_SESSION_BY_HELLO, config
CHARACTERS = load_characters(CHARACTER_PATH)
REVISION = os.environ.get('HR_CHATBOT_REVISION')
LOCATION = dyn_properties.get('location')
IP = dyn_properties.get('ip')

from session import ChatSessionManager
session_manager = ChatSessionManager()
DISABLE_QUIBBLE = True
FALLBACK_LANG = 'en-US'

from chatbot.utils import (shorten, str_cleanup, get_weather, parse_weather,
        do_translate, norm2)
from chatbot.words2num import words2num
from chatbot.server.character import TYPE_AIML, TYPE_CS
from operator import add, sub, mul, truediv, pow
import math
from chatbot.server.template import render
from model import Response, Request
from response import Response

RESPONSE_TYPE_WEIGHTS = {
    'pass': 100,
    'nogoodmatch': 50,
    'quibble': 40,
    'gambit': 50,
    'repeat': 0,
    'pickup': 0,
    'es': 20,
    'markov': 5,
}

def get_character(id, lang=None, ns=None):
    for character in CHARACTERS:
        if (ns is not None and character.name != ns) or character.id != id:
            continue
        if lang is None:
            return character
        elif lang in character.languages:
            return character


def add_character(character):
    if character.id not in [c.id for c in CHARACTERS]:
        CHARACTERS.append(character)
        return True, "Character added"
    # TODO: Update character
    else:
        return False, "Character exists"


def is_local_character(character):
    return character.local


def get_characters_by_name(name, local=True, lang=None, user=None):
    characters = []
    _characters = [c for c in CHARACTERS if c.name == name]
    if local:
        _characters = [c for c in _characters if is_local_character(c)]
    if lang is not None:
        _characters = [c for c in _characters if lang in c.languages]

    if user is not None:
        for c in _characters:
            toks = c.id.split('/')
            if len(toks) == 2:
                if toks[0] == user:
                    characters.append(c)
            else:
                characters.append(c)
    else:
        characters = _characters
    if not characters:
        logger.warn('No character is satisfied')
    return characters


def list_character(lang, sid):
    session = session_manager.get_session(sid)
    if session is None:
        return []
    characters = get_responding_characters(lang, sid)
    weights = get_weights(characters, session)
    return [(c.name, c.id, w, c.level, c.dynamic_level) for c, w in zip(characters, weights)]


def list_character_names():
    names = list(set([c.name for c in CHARACTERS if c.name != 'dummy']))
    return names


def set_weights(param, lang, sid):
    session = session_manager.get_session(sid)
    if session is None:
        return False, "No session"

    if param == 'reset':
        session.session_context.weights = {}
        return True, "Weights are reset"

    weights = {}
    characters = get_responding_characters(lang, sid)
    try:
        for w in param.split(','):
            k, v = w.split('=')
            v = float(v)
            if v>1 or v<0:
                return False, "Weight must be in the range [0, 1]"
            try:
                k = int(k)
                weights[characters[k].id] = v
            except ValueError:
                weights[k] = v
    except Exception as ex:
        logger.error(ex)
        logger.error(traceback.format_exc())
        return False, "Wrong weight format"

    session.session_context.weights = weights
    return True, "Weights are updated"

def get_weights(characters, session):
    weights = []
    if hasattr(session.session_context, 'weights') and session.session_context.weights:
        for c in characters:
            if c.id in session.session_context.weights:
                weights.append(session.session_context.weights.get(c.id))
            else:
                weights.append(c.weight)
    else:
        weights = [c.weight for c in characters]
    return weights

def set_context(prop, sid):
    session = session_manager.get_session(sid)
    if session is None:
        return False, "No session"
    for c in CHARACTERS:
        try:
            c.set_context(session, prop)
        except Exception:
            pass
    return True, "Context is updated"

def remove_context(keys, sid):
    session = session_manager.get_session(sid)
    if session is None:
        return False, "No session"
    for c in CHARACTERS:
        if c.type != TYPE_AIML and c.type != TYPE_CS:
            continue
        try:
            for key in keys:
                c.remove_context(session, key)
        except Exception:
            pass
    return True, "Context is updated"

def get_context(sid, lang):
    session = session_manager.get_session(sid)
    if session is None:
        return False, "No session"
    characters = get_responding_characters(lang, sid)
    context = {}
    for c in characters:
        if not c.stateful:
            continue
        try:
            context.update(c.get_context(session))
        except Exception as ex:
            logger.error("Get context error, {}".format(ex))
            logger.error(traceback.format_exc())
    for k in context.keys():
        if k.startswith('_'):
            del context[k]
    return True, context

def update_config(**kwargs):
    keys = []
    for key, value in kwargs.items():
        if key in config:
            if isinstance(value, unicode):
                value = str(value)
            config[key] = value
            if key not in keys:
                keys.append(key)
        else:
            logger.warn("Unknown config {}".format(key))

    if len(keys) > 0:
        logger.warn("Configuration is updated")
        for key in keys:
            logger.warn("{}={}".format(key, config[key]))
        return True, "Configuration is updated"
    else:
        return False, "No configuration is updated"

def preprocessing(question, lang):
    question = question.lower().strip()
    question = ' '.join(question.split())  # remove consecutive spaces
    question = question.replace('sofia', 'sophia')
    return question

def _ask_characters(characters, request, response):
    session = session_manager.get_session(request.sid)
    if session is None:
        return

    used_charaters = []
    data = session.session_context
    user = getattr(data, 'user')
    botname = getattr(data, 'botname')
    weights = get_weights(characters, session)
    weighted_characters = zip(characters, weights)
    weighted_characters = [wc for wc in weighted_characters if wc[1]>0]
    logger.info("Weights {}".format(weights))

    _question = preprocessing(request.question, request.lang)
    response.ModQuestion = _question

    hit_character = None
    answer = None
    cached_responses = defaultdict(list)

    def _ask_character(stage, character, weight, good_match=False, reuse=False):
        logger.info("Asking character {} \"{}\" in stage {}".format(
            character.id, _question, stage))

        if not reuse and character.id in used_charaters:
            response.add_trace((character.id, stage, 'Skip used tier'))
            return False, None, None

        if character.id in used_charaters and character.type == TYPE_CS:
            response.add_trace((character.id, stage, 'Skip CS tier'))
            return False, None, None

        used_charaters.append(character.id)
        answer = None
        answered = False

        if weight == 0:
            response.add_trace((character.id, stage, 'Disabled'))
            logger.warn("Character \"{}\" in stage {} is disabled".format(
                character.id, stage))
            return False, None, None

        tier_response = character.respond(_question, request.lang, session, request.query, request.id)
        answer = str_cleanup(tier_response.get('text', ''))
        trace = tier_response.get('trace')

        if answer:
            if 'pickup' in character.id:
                cached_responses['pickup'].append((tier_response, answer, character))
                response.add_response('pickup', tier_response)
                return False, None, None
            if good_match:
                if tier_response.get('exact_match') or tier_response.get('ok_match'):
                    if tier_response.get('gambit'):
                        if random.random() < 0.3:
                            logger.info("{} has gambit but dismissed".format(character.id))
                            response.add_trace((character.id, stage, 'Ignore gambit answer. Answer: {}, Trace: {}'.format(answer, trace)))
                            cached_responses['gambit'].append((tier_response, answer, character))
                            response.add_response('gambit', tier_response)
                        else:
                            logger.info("{} has gambit".format(character.id))
                            answered = True
                    else:
                        logger.info("{} has good match".format(character.id))
                        answered = True
                else:
                    if not tier_response.get('bad'):
                        logger.info("{} has no good match".format(character.id))
                        response.add_trace((character.id, stage, 'No good match. Answer: {}, Trace: {}'.format(answer, trace)))
                        cached_responses['nogoodmatch'].append((tier_response, answer, character))
                        response.add_response('nogoodmatch', tier_response)
            elif tier_response.get('bad'):
                response.add_trace((character.id, stage, 'Bad answer. Answer: {}, Trace: {}'.format(answer, trace)))
                cached_responses['bad'].append((tier_response, answer, character))
                response.add_response('bad', tier_response)
            elif DISABLE_QUIBBLE and tier_response.get('quibble'):
                response.add_trace((character.id, stage, 'Quibble answer. Answer: {}, Trace: {}'.format(answer, trace)))
                cached_responses['quibble'].append((tier_response, answer, character))
                response.add_response('quibble', tier_response)
            else:
                answered = True
            if answered:
                if random.random() < weight:
                    response.add_trace((character.id, stage, 'Trace: {}'.format(trace)))
                else:
                    answered = False
                    response.add_trace((character.id, stage, 'Pass through. Answer: {}, Weight: {}, Trace: {}'.format(answer, weight, trace)))
                    logger.info("{} has answer but dismissed".format(character.id))
                    if character.id == 'markov':
                        cached_responses['markov'].append((tier_response, answer, character))
                        response.add_response('markov', tier_response)
                    elif character.id == 'es':
                        if tier_response.get('exact_match') or tier_response.get('ok_match'):
                            cached_responses['es'].append((tier_response, answer, character))
                            response.add_response('es', tier_response)
                        else:
                            cached_responses['nogoodmatch'].append((tier_response, answer, character))
                            response.add_response('nogoodmatch', tier_response)
                    else:
                        cached_responses['pass'].append((tier_response, answer, character))
                        response.add_response('pass', tier_response)
        else:
            if tier_response.get('repeat'):
                answer = tier_response.get('repeat')
                response.add_trace((character.id, stage, 'Repetitive answer. Answer: {}, Trace: {}'.format(answer, trace)))
                cached_responses['repeat'].append((tier_response, answer, character))
                response.add_response('repeat', tier_response)
            else:
                logger.info("{} has no answer".format(character.id))
                response.add_trace((character.id, stage, 'No answer. Trace: {}'.format(trace)))
        return answered, answer, tier_response

    # If the last input is a question, then try to use the same tier to
    # answer it.
    if not response.answered:
        if session.open_character in characters:
            answered, _answer, _response = _ask_character(
                'question', session.open_character, 1, good_match=True)
            if answered:
                response.set_default_response(_response)

    # Try the first tier to see if there is good match
    if not response.answered:
        c, weight = weighted_characters[0]
        answered, _answer, _response = _ask_character(
            'priority', c, weight, good_match=True)
        if answered:
            response.set_default_response(_response)

    # Select tier that is designed to be proper to answer the question
    if not response.answered:
        for c, weight in weighted_characters:
            if c.is_favorite(_question):
                answered, _answer, _response = _ask_character(
                    'favorite', c, 1)
                if answered:
                    response.set_default_response(_response)
                    break

    # Check the last used character
    if not response.answered:
        if session.last_used_character and session.last_used_character.dynamic_level:
            for c, weight in weighted_characters:
                if session.last_used_character.id == c.id:
                    answered, _answer, _response = _ask_character(
                        'last used', c, weight)
                    if answered:
                        response.set_default_response(_response)
                    break

    # Check the loop
    if not response.answered:
        for c, weight in weighted_characters:
            answered, _answer, _response = _ask_character(
                'loop', c, weight, reuse=True)
            if answered:
                response.set_default_response(_response)
                break

    if not response.answered:
        logger.info("Picking answer from cache %s" % cached_responses.keys())
        weights = np.array([float(RESPONSE_TYPE_WEIGHTS.get(k, 0)) for k in cached_responses.keys()])
        pweights = weights/sum(weights)
        key = np.random.choice(cached_responses.keys(), p=pweights)
        logger.info("Picked %s from cache by p=%s" % (key, pweights))
        tier_response, answer, hit_character = cached_responses.get(key)[0]
        tier_response['text'] = answer
        response.set_default_response(tier_response)
        response.add_trace(
            (hit_character.id, key,
            tier_response.get('trace') or 'No trace'))

    #if answer and re.match('.*{.*}.*', answer):
    #    logger.info("Template answer {}".format(answer))
    #    try:
    #        response['orig_text'] = answer
    #        render_result = render(answer)
    #        answer = render_result['render_result']
    #        lineno = render_result['variables'].get('lineno')
    #        response['text'] = answer
    #        response['lineno'] = lineno
    #        if re.search('{.*}', answer):
    #            logger.error("answer contains illegal characters")
    #            answer = re.sub('{.*}', '', answer)
    #    except Exception as ex:
    #        answer = ''
    #        response['text'] = ''
    #        logger.error("Error in rendering template, {}".format(ex))

    #dummy_character = get_character('dummy', lang)
    #if not answer and dummy_character:
    #    if response.get('repeat'):
    #        response = dummy_character.respond("REPEAT_ANSWER", lang, sid, query)
    #    else:
    #        response = dummy_character.respond("NO_ANSWER", lang, sid, query)
    #    hit_character = dummy_character
    #    answer = str_cleanup(response.get('text', ''))

    #if not query and hit_character is not None:
    #    logger.info("Hit by %s", hit_character)
    #    response['AnsweredBy'] = hit_character.id
    #    session.last_used_character = hit_character
    #    hit_character.use(session, response)

    #    if is_question(answer.lower().strip()):
    #        if hit_character.dynamic_level:
    #            session.open_character = hit_character
    #            logger.info("Set open dialog character {}".format(
    #                        hit_character.id))
    #    else:
    #        session.open_character = None

def is_question(question):
    if not isinstance(question, unicode):
        question = question.decode('utf-8')
    return question.endswith('?') or question.endswith('？')

def get_responding_characters(lang, sid):
    session = session_manager.get_session(sid)
    if session is None:
        return []
    if not hasattr(session.session_context, 'botname'):
        return []

    botname = session.session_context.botname
    user = session.session_context.user

    # current character > local character with the same name > solr > generic
    responding_characters = get_characters_by_name(
        botname, local=False, lang=lang, user=user)
    responding_characters = sorted(responding_characters, key=lambda x: x.level)

    generic = get_character('generic', lang)
    if generic:
        if generic not in responding_characters:
            # get shared properties
            character = get_character(botname)
            generic.set_properties(character.get_properties())
            responding_characters.append(generic)
    else:
        logger.info("Generic character is not found")

    responding_characters = sorted(responding_characters, key=lambda x: x.level)

    return responding_characters


def rate_answer(sid, idx, rate):
    session = session_manager.get_session(sid)
    if session is None:
        logger.error("Session doesn't exist")
        return False
    try:
        return session.rate(rate, idx)
    except Exception as ex:
        logger.error("Rate error: {}".format(ex))
        return False
    return True


def ask(question, lang, sid, query=False, request_id=None, **kwargs):
    response = Response()
    response.Datetime = str(dt.datetime.utcnow())
    response.Rate = ''
    response.Lang = lang
    response.Location = LOCATION
    response.ServerIP = IP
    response.RequestId = request_id
    response.Revision = REVISION

    #response = {'text': '', 'emotion': '', 'botid': '', 'botname': ''}

    session = session_manager.get_session(sid)
    if session is None:
        response.ret = codes.INVALID_SESSION
        return response

    if not question or not question.strip():
        response.ret = codes.INVALID_QUESTION
        return response

    botname = session.session_context.botname
    if not botname:
        logger.error("No botname is specified")
    user = session.session_context.user
    client_id = session.session_context.client_id
    response.BotName = botname
    response.User = user
    response.ClientId = client_id
    response.OriginalQuestion = question

    input_translated = False
    output_translated = False
    fallback_mode = False
    responding_characters = get_responding_characters(lang, sid)
    if not responding_characters and lang != FALLBACK_LANG:
        fallback_mode = True
        logger.warn("Use %s medium language, in fallback mode", FALLBACK_LANG)
        responding_characters = get_responding_characters(FALLBACK_LANG, sid)
        try:
            input_translated, question = do_translate(question, FALLBACK_LANG)
        except Exception as ex:
            logger.error(ex)
            logger.error(traceback.format_exc())
            response.ret = codes.TRANSLATE_ERROR
            return response

    if not responding_characters:
        logger.error("Wrong characer name")
        response.ret = codes.WRONG_CHARACTER_NAME
        return response

    # Handle commands
    if question == ':reset':
        session_manager.dump(sid)
        session_manager.reset_session(sid)
        logger.warn("Session {} is reset by :reset".format(sid))
    for c in responding_characters:
        if c.is_command(question):
            response.update(c.respond(question, lang, session, query, request_id))
            return response

    response['yousaid'] = question

    session.set_characters(responding_characters)
    if RESET_SESSION_BY_HELLO and question:
        question_tokens = question.lower().strip().split()
        if 'hi' in question_tokens or 'hello' in question_tokens:
            session_manager.dump(sid)
            session_manager.reset_session(sid)
            logger.warn("Session {} is reset by greeting".format(sid))
    if question and question.lower().strip() in ["what's new"]:
        session.last_used_character = None
        session.open_character = None
        logger.info("Triggered new topic")

    logger.info("Responding characters {}".format(responding_characters))
    
    request = Request()
    request.id = request_id
    request.lang = lang
    request.sid = sid
    request.question = question
    request.query = query

    response.Question = response.get('OriginalQuestion')
    response.Marker = kwargs.get('marker')
    response.RunId = kwargs.get('run_id')

    if fallback_mode:
        request.lang = FALLBACK_LANG
        _ask_characters(
            responding_characters, request, response)
    else:
        _ask_characters(
            responding_characters, request, response)

    #if not query:
        # Sync session data
        #if session.last_used_character is not None:
        #    context = session.last_used_character.get_context(session)
        #    for c in responding_characters:
        #        if c.id == session.last_used_character.id:
        #            continue
        #        try:
        #            c.set_context(session, context)
        #        except NotImplementedError:
        #            pass

        #    for c in responding_characters:
        #        if c.type != TYPE_AIML:
        #            continue
        #        try:
        #            c.check_reset_topic(sid)
        #        except Exception:
        #            continue

    record = OrderedDict()
    record['Datetime'] = dt.datetime.utcnow()
    record['Question'] = response.get('OriginalQuestion')
    record['Rate'] = ''
    record['Lang'] = lang
    record['Location'] = LOCATION
    record['ServerIP'] = IP
    record['RequestId'] = request_id
    record['Revision'] = REVISION
    record['ClientId'] = client_id
    record['User'] = user
    record['Marker'] = kwargs.get('marker')
    record['BotName'] = botname
    record['RunId'] = kwargs.get('run_id')

    if response.answered:
        #response['OriginalAnswer'] = response.get('text')
        #if fallback_mode:
        #    try:
        #        answer = response.get('text')
        #        output_translated, answer = do_translate(answer, lang)
        #        response['text'] = answer
        #    except Exception as ex:
        #        logger.error(ex)
        #        logger.error(traceback.format_exc())
        #        response.ret = codes.TRANSLATE_ERROR
        #        return response

        #record['Answer'] = response.get('text')
        #record['LineNO'] = response.get('lineno')
        #record['OriginalAnswer'] = response.get('OriginalAnswer')
        #record['TranslatedQuestion'] = question
        #record['Topic'] = response.get('topic')
        #record['ModQuestion'] = response.get('ModQuestion')
        #record['Trace'] = response.get('trace')
        #record['AnsweredBy'] = response.get('AnsweredBy')
        #record['TranslateOutput'] = output_translated
        #record['TranslateInput'] = input_translated
        #record['NormQuestion'] = norm2(response.get('OriginalQuestion'))
        #record['NormAnswer'] = norm2(response.get('text'))
        #session.add(record)
        #logger.info("Ask {}, response {}".format(response['OriginalQuestion'], response))
        #response.update(record)
        #response['Datetime'] = str(response['Datetime'])
        return response
    else:
        logger.error("No pattern match")
        response.update(record)
        response['Datetime'] = str(response['Datetime'])
        response.ret = codes.NO_PATTERN_MATCH
        return response

def said(sid, text):
    session = session_manager.get_session(sid)
    if session is None:
        return False, "No session"
    control = get_character('control')
    if control is not None:
        control.said(session, text)
        return True, "Done"
    return False, 'No control tier'

def dump_history():
    return session_manager.dump_all()


def dump_session(sid):
    return session_manager.dump(sid)


def reload_characters(**kwargs):
    global CHARACTERS, REVISION
    with sync:
        characters = None
        logger.info("Reloading")
        try:
            characters = load_characters(CHARACTER_PATH)
            del CHARACTERS[:]
            CHARACTERS = characters
            revision = kwargs.get('revision')
            if revision:
                REVISION = revision
                logger.info("Revision {}".format(revision))
        except Exception as ex:
            logger.error("Reloading characters error {}".format(ex))

def rebuild_cs_character(**kwargs):
    with sync:
        try:
            botname=kwargs.get('botname')
            characters=get_characters_by_name(botname)
            if not characters:
                logger.error("Can't find CS tier for {}".format(botname))
            for c in characters:
                if c.id == 'cs' and hasattr(c, 'rebuild'):
                    log = c.rebuild()
                    if 'ERROR SUMMARY' in log:
                        logger.error(log[log.index('ERROR SUMMARY'):])
                    logger.info("Rebuilding chatscript for {} successfully".format(botname))
        except Exception as ex:
            logger.error("Rebuilding chatscript characters error {}".format(ex))

atexit.register(dump_history)
