import bunch
from codes import CODES
import logging
from template import render_template
logger = logging.getLogger('hr.chatbot.server.model')

RESPONSE_TYPE_WEIGHTS = {
    '_DEFAULT_': 100,
    'sc': 100,
    'cs': 100,
    'ddg': 100,
    'pass': 100,
    'es': 50,
    'gambit': 50,
    'quibble': 40,
    'repeat': 30,
    'nogoodmatch': 20,
    'markov': 5,
}

class Request(bunch.Bunch):

    def __init__(self):
        self.question = None
        self.lang = None
        self.sid = None
        self.id = None
        self.query = None

    def __str__(self):
        return self.toJSON()+'\n'

class Response(bunch.Bunch):
    def __init__(self):
        self.ret = 0
        self.responses = {}
        self.trace = []
        self.default_response = None
        self._default_category = '_DEFAULT_'

    def render_response(self, response):
        text = response.get('text')
        try:
            response['orig_text'] = text
            text = render_template(text)
            response['text'] = text
        except Exception as ex:
            logger.error("Rendering template error %s", ex)
            response['text'] = ''

    def add_response(self, category, response):
        logger.info("Add response %s %s", category, response)
        self.render_response(response)
        response['cweight'] = RESPONSE_TYPE_WEIGHTS.get(category, 0)
        if category in self.responses:
            self.responses[category].append(response)
        else:
            self.responses[category] = [response]

    def get_responses(self, category):
        return self.responses.get(category)

    def get_default_responses(self):
        return self.get_responses(self._default_category)

    def add_default_response(self, response):
        """The default response is the one preferred to use"""
        self.add_response(self._default_category, response)

    def set_default_response(self, response):
        self.default_response = response
        self.render_response(response)

    def add_trace(self, trace):
        self.trace.append(trace)

    @property
    def answered(self):
        return self.default_response is not None

    def show(self):
        print self.toYAML()

if __name__ == '__main__':
    response = Response()
    response.add_response('stage1', 'response')
    response.add_response('stage1', 'response2')
    response.add_response('stage2', 'response3')
    response.set_default_response('response4')
    print response.toJSON()
    print response.toYAML()
    print response.answered