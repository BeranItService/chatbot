from bunch import Bunch

class Response(Bunch):
    def __init__(self):
        self.ret = 0
        self.responses = {}
        self.trace = []
        self.default_response = None

    def add_response(self, stage, response):
        if stage in self.responses:
            self.responses[stage].append(response)
        else:
            self.responses[stage] = [response]

    def set_default_response(self, response):
        self.default_response = response
        self.add_response('_DEFAULT_', response)

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
