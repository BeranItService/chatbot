import os
import re
from jinja2 import Template, Environment, meta
import jinja2
from renderers import *
import logging

logger = logging.getLogger('hr.chatbot.server.template')

def render(string):
    render_result = ''
    variables = {}
    t = Template(string)
    env = Environment()
    ast = env.parse(string)
    for node in ast.body:
        if isinstance(node, jinja2.nodes.Assign):
            variables[node.target.name] = node.node.value
    func = get_render_func(ast)
    if func is not None:
        try:
            render_result = func(t) or t.render()
        except Exception as ex:
            logger.error("Rendering error, {}".format(ex))
            render_result = t.render()
    else:
        render_result = t.render()
    return {"render_result": render_result, "variables": variables}

def get_render_func(ast):
    func = None
    variables = meta.find_undeclared_variables(ast)
    if 'temperature' in variables:
        func = render_weather
    if 'location' in variables:
        func = render_location
    if 'faceemotion' in variables:
        func = render_face_emotion
    if 'objectdetected' in variables:
        func = render_object_detected
    if not func and variables:
        logger.error("Render is not found for template {}".format(string))
    return func

def render_template(answer):
    if answer and re.match('.*{.*}.*', answer):
        logger.info("Template answer {}".format(answer))
        render_result = render(answer)
        answer = render_result['render_result']
        if re.search('{.*}', answer):
            logger.error("answer contains illegal characters")
            answer = re.sub('{.*}', '', answer)
    return answer

if __name__ == '__main__':
    string = """aa {% set lineno = "file:123" %}{% set lineno2 = "file2:123" %}"""
    string  = render(string)
    print string

    string = """{% set location = "hong kong" %} {% if temperature is not defined %} I don't know {% elif temperature>30 %} it's really hot {% elif temperature<10 %} too cold here {% else %} Hmm, it\'s nice {% endif %}."""
    string  = render(string)
    print string

    string = """{% if temperature is not defined %} I don't know {% else %} The weather is {{ weather_desc }}, the temperature is {{ temperature }}. {% endif %}"""
    string  = render(string)
    print string

    string = """I think you are in {{ location }}. """
    string  = render(string)
    print string

    string = """{% if faceemotion is not defined %} I can't tell. How do you feel? {% else %} You look {{ faceemotion }}. {% endif %}"""
    string  = render(string)
    print string

    string = """{% if objectdetected is not defined %} Sorry, I don't know what's that. {% else %} Is that {{ objectdetected }}. {% endif %}"""
    string  = render(string)
    print string
