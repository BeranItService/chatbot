import bunch
from codes import CODES

class Response(bunch.Bunch):

    def __init__(self):
        self.text = ''
        self.botid = ''
        self.botname = ''
        self.emotion = ''
        self.err_code = 0
        self.err_msg = ''

    def __str__(self):
        return self.toJSON()+'\n'

    def set_return_code(self, code):
        if code in CODES:
            logger.warn("Code %s is not valid", code)
        self.err_code = code
        self.err_msg = CODES.get(code)

class Request(bunch.Bunch):

    def __init__(self):
        self.question = None
        self.lang = None
        self.sid = None
        self.id = None

    def __str__(self):
        return self.toJSON()+'\n'

if __name__ == '__main__':
    response = Response()
    request = Request()
    response.text = 'abc'
    response.update({'x': 1})
    response.req = request
    print response
