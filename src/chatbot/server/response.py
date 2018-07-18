import bunch

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

if __name__ == '__main__':
    r = Response()
    r.text = 'abc'
    r.update({'x': 1})
    print r
