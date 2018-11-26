from bunch import Bunch

class Response(Bunch):
    def __init__(self):
        self.ret = 0
        self.responses = {}
        self.trace = []
        self.default_response = None
        self._default_category = '_DEFAULT_'

    def add_response(self, category, response):
        if category in self.responses:
            self.responses[category].append(response)
        else:
            self.responses[category] = [response]

    def get_responses(self, category):
        return self.responses.get(category)

    def get_default_responses(self):
        return self.get_responses(self._default_category)

    def add_default_response(self, response):
        self.add_response(self._default_category, response)

    def set_default_response(self, response):
        self.default_response = response

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
