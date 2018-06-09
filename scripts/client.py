#!/usr/bin/env python

import os
import sys
import logging
import argparse
CWD = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(CWD, '../src'))

from chatbot.client import Client

HR_CHATBOT_AUTHKEY = os.environ.get('HR_CHATBOT_AUTHKEY', 'AAAAB3NzaC')

if __name__ == '__main__':
    logging.basicConfig()
    logging.getLogger().setLevel(logging.WARN)

    parser = argparse.ArgumentParser('Chatbot Client')
    parser.add_argument(
        'botname', help='botname')
    parser.add_argument(
        '-u', '--user',
        help='user name')
    parser.add_argument(
        '-k', '--key', default=HR_CHATBOT_AUTHKEY,
        help='client key')
    parser.add_argument(
        '--host', default='localhost',
        help='server host')
    parser.add_argument(
        '-p', '--port', default=8001, type=int,
        help='server port')

    options = parser.parse_args()

    client = Client(
        options.key, options.botname, username=options.user,
        host=options.host, port=options.port)
    client.cmdloop()
