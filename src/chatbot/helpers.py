import time
import json
from jinja2 import Environment, meta
from chatbot.utils import (get_location, get_detected_object,
    get_weather_by_id, parse_weather, query_city_info, get_emotion)

def get_context_helpers(string):
    env = Environment()
    ast = env.parse(string)
    variables = meta.find_undeclared_variables(ast)
    helpers = []
    if 'temperature' in variables:
        helpers.append(get_weather)
    if 'location' in variables:
        helpers.append(get_venue)
    if 'faceemotion' in variables:
        helpers.append(get_faceemotion)
    if 'objectdetected' in variables:
        helpers.append(get_objectdetected)
    if 'name' in variables:
        helpers.append(get_name)
    return helpers

def get_weather(template, client):
    if hasattr(template.module, 'location'):
        location = template.module.location
    else:
        location = get_location()
        if location and 'city' in location:
            location = location.get('city')
    city = query_city_info(location)
    if city and 'id' in city:
        id = city['id']
        weather = get_weather_by_id(id)
        weather_prop = parse_weather(weather)
        desc = weather_prop['weather']
        temperature = '{} degrees'.format(weather_prop['temperature'])
        return {'weatherdesc': desc, 'temperature': temperature, 'location': city}

def get_venue(template, client):
    location = get_location()
    if location and 'city' in location:
        location = location.get('city')
        return {'venue': location}

def get_faceemotion(template, client):
    time.sleep(3)
    emotion = get_emotion(3) # the the emotion in the past 3 secs
    if emotion is not None:
        return {'faceemotion': emotion}

def get_objectdetected(template, client):
    time.sleep(3)
    item = get_detected_object(10)
    if item is not None:
        item = ' '.join(item.split('_'))
        return {'objectdetected': item}

def get_name(template, client):
    context = client.get_context()
    context['name'] = 'wenwei'
    if context and 'name' in context:
        return {'name': context['name']}

