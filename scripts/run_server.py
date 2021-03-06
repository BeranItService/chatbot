#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

import os
import logging
import logging.config
import datetime as dt
import json
import shutil
import argparse
import subprocess

try:
    import colorlog
except ImportError:
    pass

import sys
import re
CWD = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(CWD, '../src'))

logger = logging.getLogger('hr.chatbot.server')
if 'HR_CHARACTER_PATH' not in os.environ:
    os.environ['HR_CHARACTER_PATH'] = os.path.join(CWD, 'characters')

from chatbot.server.config import SERVER_LOG_DIR, HISTORY_DIR

def init_logging():
    if os.environ.get('ROS_LOG_DIR'):
        SERVER_LOG_DIR = os.environ.get('ROS_LOG_DIR')
    run_id = None
    try:
        run_id = subprocess.check_output('rosparam get /run_id'.split()).strip()
    except Exception as ex:
        run_id = None
    if run_id is not None:
        SERVER_LOG_DIR = os.path.join(SERVER_LOG_DIR, run_id, 'chatbot')

    if not os.path.isdir(SERVER_LOG_DIR):
        os.makedirs(SERVER_LOG_DIR)
    log_config_file = '{}/{}.log'.format(SERVER_LOG_DIR,
        'chatbot_server-%s' % dt.datetime.strftime(dt.datetime.utcnow(), '%Y%m%d%H%M%S'))
    link_log_fname = os.path.join(SERVER_LOG_DIR, 'latest.log')
    if os.path.islink(link_log_fname):
        os.unlink(link_log_fname)
    os.symlink(log_config_file, link_log_fname)

    os.environ['ROS_LOG_FILENAME'] = log_config_file
    os.environ['ROS_LOG_DIR'] = SERVER_LOG_DIR

    config_file = os.environ.get('ROS_PYTHON_LOG_CONFIG_FILE')
    default_config_file = os.path.join(CWD, 'python_logging.conf')
    os.environ['ROS_LOG_FILENAME'] = log_config_file
    if config_file and os.path.isfile(config_file):
        logging.config.fileConfig(config_file)
    else:
        logging.config.fileConfig(default_config_file)

init_logging()

from chatbot.server.auth import requires_auth
from chatbot.server.auth import check_auth, authenticate

from flask import Flask, request, Response, send_from_directory

from chatbot.server.chatbot_agent import (
    ask, list_character, session_manager, set_weights, set_context,
    dump_history, dump_session, add_character, list_character_names,
    rate_answer, get_context, said, remove_context, update_config, feedback)
from chatbot.stats import history_stats

json_encode = json.JSONEncoder().encode
app = Flask(__name__)
VERSION = 'v2.0'
ROOT = '/{}'.format(VERSION)
INCOMING_DIR = os.path.expanduser('~/.hr/aiml/incoming')

app.config['UPLOAD_FOLDER'] = os.path.expanduser('~/.hr/aiml')


@app.route(ROOT + '/<path:path>')
def send_client(path):
    return send_from_directory('public', path)


@app.route(ROOT + '/client', methods=['GET'])
def client():
    return send_from_directory('public', 'client.html')


@app.route(ROOT + '/chat', methods=['GET'])
@requires_auth
def _chat():
    data = request.args
    question = data.get('question')
    session = data.get('session')
    lang = data.get('lang', 'en-US')
    query = data.get('query', 'false')
    query = query.lower() == 'true'
    request_id = request.headers.get('X-Request-Id')
    marker = data.get('marker', 'default')
    run_id = data.get('run_id', '')
    try:
        logger.warn("Chat request: %s", data)
        response = ask(
            question, lang, session, query,
            request_id=request_id, marker=marker, run_id=run_id)
    except Exception as ex:
        logger.exception(ex)
        raise ex
    return Response(response.toJSON(), mimetype="application/json")

@app.route(ROOT + '/feedback', methods=['GET'])
@requires_auth
def _feedback():
    data = request.args
    session = data.get('session')
    text = data.get('text')
    label = data.get('label')
    lang = data.get('lang')
    try:
        ret, response = feedback(session, text, label, lang)
        return Response(json_encode({'ret': 0 if ret else 1, 'response': response}),
                        mimetype="application/json")
    except Exception as ex:
        logger.exception(ex)
        raise ex

@app.route(ROOT + '/batch_chat', methods=['POST'])
def _batch_chat():
    auth = request.form.get('Auth')
    if not auth or not check_auth(auth):
        return authenticate()

    questions = request.form.get('questions')
    questions = json.loads(questions)
    session = request.form.get('session')
    lang = request.form.get('lang', 'en-US')
    responses = []
    for idx, question in questions:
        response, ret = ask(str(question), lang, session)
        responses.append((idx, response, ret))
    return Response(json_encode({'ret': 0, 'response': responses}),
                    mimetype="application/json")

@app.route(ROOT + '/said', methods=['GET'])
@requires_auth
def _said():
    data = request.args
    session = data.get('session')
    message = data.get('message')
    ret, response = said(session, message)
    return Response(json_encode({'ret': ret, 'response': response}),
                    mimetype="application/json")

@app.route(ROOT + '/rate', methods=['GET'])
@requires_auth
def _rate():
    data = request.args
    response = ''
    try:
        ret = rate_answer(data.get('session'), int(
            data.get('index')), data.get('rate'))
    except Exception as ex:
        response = ex.message
    return Response(json_encode({'ret': ret, 'response': response}),
                    mimetype="application/json")


@app.route(ROOT + '/chatbots', methods=['GET'])
@requires_auth
def _chatbots():
    data = request.args
    lang = data.get('lang', None)
    session = data.get('session')
    characters = list_character(lang, session)
    return Response(json_encode({'ret': 0, 'response': characters}),
                    mimetype="application/json")


@app.route(ROOT + '/bot_names', methods=['GET'])
@requires_auth
def _bot_names():
    names = list_character_names()
    return Response(json_encode({'ret': 0, 'response': names}),
                    mimetype="application/json")


@app.route(ROOT + '/start_session', methods=['GET'])
@requires_auth
def _start_session():
    botname = request.args.get('botname')
    user = request.args.get('user')
    client_id = request.args.get('client_id')
    test = request.args.get('test', 'false')
    refresh = request.args.get('refresh', 'false')
    test = test.lower() == 'true'
    refresh = refresh.lower() == 'true'
    sid = session_manager.start_session(
        client_id=client_id, user=user, test=test, refresh=refresh)
    sess = session_manager.get_session(sid)
    sess.session_context.botname = botname
    return Response(json_encode({'ret': 0, 'sid': str(sid)}),
                    mimetype="application/json")


@app.route(ROOT + '/sessions', methods=['GET'])
@requires_auth
def _sessions():
    sessions = session_manager.list_sessions()
    response = []
    for session in sessions:
        response.append('%s/%s/%s' % (session.sid,
            session.session_context.client_id, session.session_context.user))
    return Response(json_encode({'ret': 0, 'response': response}),
                    mimetype="application/json")

@app.route(ROOT + '/set_weights', methods=['GET'])
@requires_auth
def _set_weights():
    data = request.args
    lang = data.get('lang', None)
    param = data.get('param')
    sid = data.get('session')
    ret, response = set_weights(param, lang, sid)
    if ret:
        sess = session_manager.get_session(sid)
        if sess and hasattr(sess.session_context, 'weights'):
            logger.info("Set weights {} successfully".format(sess.session_context.weights))
    else:
        logger.info("Set weights failed.")
    return Response(json_encode({'ret': ret, 'response': response}),
                    mimetype="application/json")

@app.route(ROOT + '/set_context', methods=['GET'])
@requires_auth
def _set_context():
    data = request.args
    context_str = data.get('context')
    context = {}
    for tok in context_str.split(','):
        k, v = tok.split('=')
        context[k.strip()] = v.strip()
    sid = data.get('session')
    ret, response = set_context(context, sid)
    return Response(json_encode({'ret': ret, 'response': response}),
                    mimetype="application/json")


@app.route(ROOT + '/remove_context', methods=['GET'])
@requires_auth
def _remove_context():
    data = request.args
    keys = data.get('keys')
    keys = keys.split(',')
    sid = data.get('session')
    ret, response = remove_context(keys, sid)
    return Response(json_encode({'ret': ret, 'response': response}),
                    mimetype="application/json")

@app.route(ROOT + '/get_context', methods=['GET'])
@requires_auth
def _get_context():
    data = request.args
    sid = data.get('session')
    lang = data.get('lang', 'en')
    ret, _response = get_context(sid, lang)
    response = {}
    for k, v in _response.iteritems():
        if isinstance(v, basestring) or isinstance(v, unicode):
            response[k] = v
    return Response(json_encode({'ret': ret, 'response': response}),
                    mimetype="application/json")

@app.route(ROOT + '/update_config', methods=['GET'])
@requires_auth
def _update_config():
    data = request.args.to_dict()
    for k, v in data.iteritems():
        if v.lower() == 'true':
            data[k]=True
        elif v.lower() == 'false':
            data[k]=False
        elif re.match(r'[0-9]+', v):
            data[k]=int(v)
        elif re.match(r'[0-9]+\.[0-9]+', v):
            data[k]=float(v)
        else:
            data[k]=str(v)
    ret, response = update_config(**data)
    return Response(json_encode({'ret': ret, 'response': response}),
                    mimetype="application/json")

@app.route('/log')
def _log():
    def generate():
        with open(LOG_CONFIG_FILE) as f:
            for row in f:
                yield row
    return Response(generate(), mimetype='text/plain')


@app.route(ROOT + '/reset_session', methods=['GET'])
@requires_auth
def _reset_session():
    data = request.args
    sid = data.get('session')
    if session_manager.has_session(sid):
        session_manager.reset_session(sid)
        ret, response = True, "Session reset"
    else:
        ret, response = False, "No such session"
    return Response(json_encode({
        'ret': ret,
        'response': response
    }),
        mimetype="application/json")


@app.route(ROOT + '/dump_history', methods=['GET'])
def _dump_history():
    try:
        dump_history()
        ret, response = True, "Success"
    except Exception:
        ret, response = False, "Failure"
    return Response(json_encode({
        'ret': ret,
        'response': response
    }),
        mimetype="application/json")


@app.route(ROOT + '/dump_session', methods=['GET'])
@requires_auth
def _dump_session():
    try:
        data = request.args
        sid = data.get('session')
        fname = dump_session(sid)
        session_manager.remove_session(sid)
        if fname is not None and os.path.isfile(fname):
            return send_from_directory(os.path.dirname(fname), os.path.basename(fname))
        else:
            return '', 404
    except Exception as ex:
        logger.error("Dump error {}".format(ex))
        return '', 500


@app.route(ROOT + '/chat_history', methods=['GET'])
@requires_auth
def _chat_history():
    history_stats(HISTORY_DIR, 7)
    history_file = os.path.join(HISTORY_DIR, 'last_7_days.csv')
    if os.path.isfile(history_file):
        return send_from_directory(HISTORY_DIR, os.path.basename(history_file))
    else:
        return '', 404

@app.route(ROOT + '/session_history', methods=['GET'])
@requires_auth
def _session_history():
    try:
        data = request.args
        sid = data.get('session')
        sess = session_manager.get_session(sid)
        fname = sess.dump_file
        if fname is not None and os.path.isfile(fname):
            return send_from_directory(
                os.path.dirname(fname),
                os.path.basename(fname),
                mimetype='text/plain')
        else:
            return '', 404
    except Exception as ex:
        logger.error("Internal error {}".format(ex))
        return '', 500


@app.route(ROOT + '/ping', methods=['GET'])
def _ping():
    return Response(json_encode({'ret': 0, 'response': 'pong'}),
                    mimetype="application/json")


@app.route(ROOT + '/stats', methods=['GET'])
@requires_auth
def _stats():
    try:
        data = request.args
        days = int(data.get('lookback', 7))
        dump_history()
        response = history_stats(HISTORY_DIR, days)
        ret = True
    except Exception as ex:
        ret, response = False, {'err_msg': str(ex)}
        logger.error(ex)
    return Response(json_encode({'ret': ret, 'response': response}),
                    mimetype="application/json")

def main():
    parser = argparse.ArgumentParser('Chatbot Server')

    parser.add_argument(
        '-p', '--port',
        dest='port', type=int, default=8001, help='Server port')
    parser.add_argument(
        '-v', '--verbose',
        dest='verbose', action='store_true', help='Verbose')

    option = parser.parse_args()

    root_logger = logging.getLogger()
    if option.verbose:
        for h in root_logger.handlers:
            h.setLevel(logging.INFO)
    else:
        for h in root_logger.handlers:
            h.setLevel(logging.WARN)

    if 'HR_CHATBOT_SERVER_EXT_PATH' in os.environ:
        sys.path.insert(0, os.path.expanduser(
            os.environ['HR_CHATBOT_SERVER_EXT_PATH']))
        import ext
        ext.load(app, ROOT)
    app.run(host='0.0.0.0', debug=False, use_reloader=False, port=option.port)


if __name__ == '__main__':
    main()
