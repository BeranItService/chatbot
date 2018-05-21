from functools import wraps
from flask import request, Response
import json

from config import HR_CHATBOT_AUTHKEY

json_encode = json.JSONEncoder().encode


def check_auth(auth):
    return auth == HR_CHATBOT_AUTHKEY


def authenticate():
    return Response(json_encode({'ret': 401, 'response': {'text': 'Could not verify your access'}}),
                    mimetype="application/json")

def get_token_auth_header():
    """Obtains the access token from the Authorization Header
    """
    auth = request.headers.get("Authorization", None)
    if not auth:
        raise AuthError({"code": "authorization_header_missing",
                        "description":
                            "Authorization header is expected"}, 401)

    parts = auth.split()

    if parts[0].lower() != "bearer":
        raise AuthError({"code": "invalid_header",
                        "description":
                            "Authorization header must start with"
                            " Bearer"}, 401)
    elif len(parts) == 1:
        raise AuthError({"code": "invalid_header",
                        "description": "Token not found"}, 401)
    elif len(parts) > 2:
        raise AuthError({"code": "invalid_header",
                        "description":
                            "Authorization header must be"
                            " Bearer token"}, 401)

    token = parts[1]
    return token



def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.args.get('Auth')
        if not auth or not check_auth(auth):
            return authenticate()
        return f(*args, **kwargs)
    return decorated
