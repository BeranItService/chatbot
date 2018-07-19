import logging

import codes
from .session import ChatSessionManager
from .model import Request, Response
from .config import CHARACTER_PATH
from .loader import ConfigFileLoader
from .utils import do_translate

logger = logging.getLogger('hr.chatbot.dialogue_manager')

class DialogueManager(object):

    def __init__(self):
        self._session_manager = ChatSessionManager()
        self._characters = ConfigFileLoader.load(CHARACTER_PATH)
        self._fallback_lang = 'en-US'

    def handle(self, request):
        assert isinstance(request, Request), "Request type error"

        response = Response()
        response.requset = request

        sess = self._session_manager.get_session(request.sid)
        if sess is None:
            return_codes.fill_return_code(response, return_codes.INVALID_SESSION)
            yield str(response.set_return_code(codes.INVALID_SESSION))

        response.botname = sess.session_context.botname
        user = sess.session_context.user
        client_id = sess.session_context.client_id

        question = request.question
        if not question or not question.strip():
            yield str(response.set_return_code(codes.INVALID_QUESTION))

        input_translated = False
        output_translated = False
        fallback_mode = False
        responding_characters = self._get_responding_characters(lang, request.sid)

        if not responding_characters and lang != self._fallback_lang:
            fallback_mode = True
            logger.warn("Use %s medium language, in fallback mode", self._fallback_lang)
            responding_characters = self._get_responding_characters(self._fallback_lang, request.sid)
            try:
                input_translated, question = do_translate(question, self._fallback_lang)
            except Exception as ex:
                logger.exception(ex)
                yield str(response.set_return_code(codes.TRANSLATE_ERROR))

        if not responding_characters:
            logger.error("Wrong characer name")
            yield str(response.set_return_code(codes.WRONG_CHARACTER_NAME))

        # Handle commands
        if question == ':reset':
            self._session_manager.dump(request.sid)
            self._session_manager.reset_session(request.sid)
            logger.warn("Session {} is reset by :reset".format(request.sid))
        for c in responding_characters:
            if c.is_command(question):
                response.update(c.respond(question, lang, sess, query, request_id))
                yield str(response)

        logger.info("Responding characters {}".format(responding_characters))
        sess.set_characters(responding_characters)
        _lang = request.lang
        if fallback_mode:
            _lang = self._fallback_lang

        count = 0
        for _response in _ask_characters(
            responding_characters, question, _lang, sid, query, request_id, **kwargs):

            if _response is not None and _response.get('text'):
                response.update(_response)
                response.OriginalAnswer = response.text
                if fallback_mode:
                    try:
                        answer = response.get('text')
                        output_translated, answer = do_translate(answer, lang)
                        response['text'] = answer
                    except Exception as ex:
                        logger.exception(ex)
                        yield str(response.set_return_code(codes.TRANSLATE_ERROR))

                sess.add(
                    response['OriginalQuestion'],
                    response.get('text'),
                    AnsweredBy=response['AnsweredBy'],
                    User=user,
                    ClientID=client_id,
                    BotName=botname,
                    Trace=response['trace'],
                    Revision=REVISION,
                    Lang=lang,
                    ModQuestion=response['ModQuestion'],
                    RequestId=request_id,
                    Marker=kwargs.get('marker'),
                    TranslateInput=input_translated,
                    TranslateOutput=output_translated,
                    TranslatedQuestion=question,
                    OriginalAnswer=response['OriginalAnswer'],
                    RunID=kwargs.get('run_id'),
                    Topic=response.get('topic'),
                    Location=LOCATION,
                    LineNO=response.get('lineno')
                )
                logger.info("Ask {}, response {}".format(response['OriginalQuestion'], response))
                yield str(response)
        if count == 0:
            logger.error("No pattern match")
            yield str(response.set_return_code(codes.NO_PATTERN_MATCH))

    def _get_responding_characters(self, lang, sid):
        sess = self._session_manager.get_session(sid)
        if sess is None:
            return []
        if not hasattr(sess.session_context, 'botname'):
            return []

        botname = sess.session_context.botname
        user = sess.session_context.user

        # current character > local character with the same name > solr > generic
        responding_characters = self._get_characters_by_name(
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

    def _get_characters_by_name(self, name, local=True, lang=None, user=None):
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
