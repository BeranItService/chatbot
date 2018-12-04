# -*- coding: utf-8 -*-

import re
import os
import requests
import subprocess
import logging
import json
import pandas as pd
import numpy as np
import datetime as dt
import six
import traceback
import time
import argparse
import pprint
from wordsub import english_word_sub

logger = logging.getLogger('hr.chatbot.utils')

try:
    from google.cloud import translate
except ImportError:
    logger.error("Can't import google translate")

OPENWEATHERAPPID = os.environ.get('OPENWEATHERAPPID')
CITY_LIST_FILE = os.environ.get('CITY_LIST_FILE')
GCLOUD_API_KEY = os.environ.get('GCLOUD_API_KEY')
PUNCTUATORS = re.compile(r"""[.|?|!]+$""")

cities = None

CHATBOT_LANGUAGE_DICT = {
    'am': ['am-ET'],
    'ar': ['ar-IL', 'ar-JO', 'ar-AE', 'ar-BH', 'ar-DZ', 'ar-SA', 'ar-IQ', 'ar-KW', 'ar-MA', 'ar-TN', 'ar-OM', 'ar-PS', 'ar-QA', 'ar-LB', 'ar-EG'],
    'zh-CN': ['cmn-Hans-CN', 'cmn-Hans-HK'],
    'zh-TW': ['cmn-Hant-TW', 'yue-Hant-HK'],
    'nl': ['nl-NL'],
    'en': ['en-AU', 'en-CA', 'en-GH', 'en-GB', 'en-IN', 'en-IE', 'en-KE', 'en-NZ', 'en-NG', 'en-PH', 'en-ZA', 'en-TZ', 'en-US'],
    'fr': ['fr-CA', 'fr-FR'],
    'de': ['de-DE'],
    'hi': ['hi-IN'],
    'it': ['it-IT'],
    'ja': ['ja-JP'],
    'ko': ['ko-KR'],
    'lt': ['lt-LT'],
    'pt': ['pt-BR', 'pt-PT'],
    'ru': ['ru-RU'],
    'es': ['es-AR', 'es-BO', 'es-CL', 'es-CO', 'es-CR', 'es-EC', 'es-SV', 'es-ES', 'es-US', 'es-GT', 'es-HN', 'es-MX', 'es-NI', 'es-PA', 'es-PY', 'es-PE', 'es-PR', 'es-DO', 'es-UY', 'es-VE'],
    'tr': ['tr-TR'],
}

BAD_WORDS = ["2 girls 1 cup", "2g1c", "4r5e", "5h1t", "5hit", "a$$", "a$$hole", "a_s_s", "a2m", "a54", "a55", "a55hole", "acrotomophilia", "aeolus", "ahole", "alabama hot pocket", "alaskan pipeline", "anal", "anal impaler", "anal leakage", "analprobe", "anilingus", "anus", "apeshit", "ar5e", "areola", "areole", "arian", "arrse", "arse", "arsehole", "aryan", "ass", "ass fuck", "ass fuck", "ass hole", "assbag", "assbandit", "assbang", "assbanged", "assbanger", "assbangs", "assbite", "assclown", "asscock", "asscracker", "asses", "assface", "assfaces", "assfuck", "assfucker", "ass-fucker", "assfukka", "assgoblin", "assh0le", "asshat", "ass-hat", "asshead", "assho1e", "asshole", "assholes", "asshopper", "ass-jabber", "assjacker", "asslick", "asslicker", "assmaster", "assmonkey", "assmucus", "assmucus", "assmunch", "assmuncher", "assnigger", "asspirate", "ass-pirate", "assshit", "assshole", "asssucker", "asswad", "asswhole", "asswipe", "asswipes", "auto erotic", "autoerotic", "axwound", "azazel", "azz", "b!tch", "b00bs", "b17ch", "b1tch", "babeland", "baby batter", "baby juice", "ball gag", "ball gravy", "ball kicking", "ball licking", "ball sack", "ball sucking", "ballbag", "balls", "ballsack", "bampot", "bang (one's) box", "bangbros", "bareback", "barely legal", "barenaked", "barf", "bastard", "bastardo", "bastards", "bastinado", "batty boy", "bawdy", "bbw", "bdsm", "beaner", "beaners", "beardedclam", "beastial", "beastiality", "beatch", "beaver", "beaver cleaver", "beaver lips", "beef curtain", "beef curtain", "beef curtains", "beeyotch", "bellend", "bender", "beotch", "bescumber", "bestial", "bestiality", "bi+ch", "biatch", "big black", "big breasts", "big knockers", "big tits", "bigtits", "bimbo", "bimbos", "bint", "birdlock", "bitch", "bitch tit", "bitch tit", "bitchass", "bitched", "bitcher", "bitchers", "bitches", "bitchin", "bitching", "bitchtits", "bitchy", "black cock", "blonde action", "blonde on blonde action", "bloodclaat", "bloody", "bloody hell", "blow job", "blow me", "blow mud", "blow your load", "blowjob", "blowjobs", "blue waffle", "blue waffle", "blumpkin", "blumpkin", "bod", "bodily", "boink", "boiolas", "bollock", "bollocks", "bollok", "bollox", "bondage", "boned", "boner", "boners", "bong", "boob", "boobies", "boobs", "booby", "booger", "bookie", "boong", "booobs", "boooobs", "booooobs", "booooooobs", "bootee", "bootie", "booty", "booty call", "booze", "boozer", "boozy", "bosom", "bosomy", "breasts", "Breeder", "brotherfucker", "brown showers", "brunette action", "buceta", "bugger", "bukkake", "bull shit", "bulldyke", "bullet vibe", "bullshit", "bullshits", "bullshitted", "bullturds", "bum", "bum boy", "bumblefuck", "bumclat", "bummer", "buncombe", "bung", "bung hole", "bunghole", "bunny fucker", "bust a load", "bust a load", "busty", "butt", "butt fuck", "butt fuck", "butt plug", "buttcheeks", "buttfuck", "buttfucka", "buttfucker", "butthole", "buttmuch", "buttmunch", "butt-pirate", "buttplug", "c.0.c.k", "c.o.c.k.", "c.u.n.t", "c0ck", "c-0-c-k", "c0cksucker", "caca", "cacafuego", "cahone", "camel toe", "cameltoe", "camgirl", "camslut", "camwhore", "carpet muncher", "carpetmuncher", "cawk", "cervix", "chesticle", "chi-chi man", "chick with a dick", "child-fucker", "chinc", "chincs", "chink", "chinky", "choad", "choade", "choade", "choc ice", "chocolate rosebuds", "chode", "chodes", "chota bags", "chota bags", "cipa", "circlejerk", "cl1t", "cleveland steamer", "climax", "clit", "clit licker", "clit licker", "clitface", "clitfuck", "clitoris", "clitorus", "clits", "clitty", "clitty litter", "clitty litter", "clover clamps", "clunge", "clusterfuck", "cnut", "cocain", "cocaine", "coccydynia", "cock", "c-o-c-k", "cock pocket", "cock pocket", "cock snot", "cock snot", "cock sucker", "cockass", "cockbite", "cockblock", "cockburger", "cockeye", "cockface", "cockfucker", "cockhead", "cockholster", "cockjockey", "cockknocker", "cockknoker", "Cocklump", "cockmaster", "cockmongler", "cockmongruel", "cockmonkey", "cockmunch", "cockmuncher", "cocknose", "cocknugget", "cocks", "cockshit", "cocksmith", "cocksmoke", "cocksmoker", "cocksniffer", "cocksuck", "cocksuck", "cocksucked", "cocksucked", "cocksucker", "cock-sucker", "cocksuckers", "cocksucking", "cocksucks", "cocksucks", "cocksuka", "cocksukka", "cockwaffle", "coffin dodger", "coital", "cok", "cokmuncher", "coksucka", "commie", "condom", "coochie", "coochy", "coon", "coonnass", "coons", "cooter", "cop some wood", "cop some wood", "coprolagnia", "coprophilia", "corksucker", "cornhole", "cornhole", "corp whore", "corp whore", "corpulent", "cox", "crabs", "crack", "cracker", "crackwhore", "crap", "crappy", "creampie", "cretin", "crikey", "cripple", "crotte", "cum", "cum chugger", "cum chugger", "cum dumpster", "cum dumpster", "cum freak", "cum freak", "cum guzzler", "cum guzzler", "cumbubble", "cumdump", "cumdump", "cumdumpster", "cumguzzler", "cumjockey", "cummer", "cummin", "cumming", "cums", "cumshot", "cumshots", "cumslut", "cumstain", "cumtart", "cunilingus", "cunillingus", "cunnie", "cunnilingus", "cunny", "cunt", "c-u-n-t", "cunt hair", "cunt hair", "cuntass", "cuntbag", "cuntbag", "cuntface", "cunthole", "cunthunter", "cuntlick", "cuntlick", "cuntlicker", "cuntlicker", "cuntlicking", "cuntlicking", "cuntrag", "cunts", "cuntsicle", "cuntsicle", "cuntslut", "cunt-struck", "cunt-struck", "cus", "cut rope", "cut rope", "cyalis", "cyberfuc", "cyberfuck", "cyberfuck", "cyberfucked", "cyberfucked", "cyberfucker", "cyberfuckers", "cyberfucking", "cyberfucking", "d0ng", "d0uch3", "d0uche", "d1ck", "d1ld0", "d1ldo", "dago", "dagos", "dammit", "damn", "damned", "damnit", "darkie", "darn", "date rape", "daterape", "dawgie-style", "deep throat", "deepthroat", "deggo", "dendrophilia", "dick", "dick head", "dick hole", "dick hole", "dick shy", "dick shy", "dickbag", "dickbeaters", "dickdipper", "dickface", "dickflipper", "dickfuck", "dickfucker", "dickhead", "dickheads", "dickhole", "dickish", "dick-ish", "dickjuice", "dickmilk", "dickmonger", "dickripper", "dicks", "dicksipper", "dickslap", "dick-sneeze", "dicksucker", "dicksucking", "dicktickler", "dickwad", "dickweasel", "dickweed", "dickwhipper", "dickwod", "dickzipper", "diddle", "dike", "dildo", "dildos", "diligaf", "dillweed", "dimwit", "dingle", "dingleberries", "dingleberry", "dink", "dinks", "dipship", "dipshit", "dirsa", "dirty", "dirty pillows", "dirty sanchez", "dirty Sanchez", "div", "dlck", "dog style", "dog-fucker", "doggie style", "doggiestyle", "doggie-style", "doggin", "dogging", "doggy style", "doggystyle", "doggy-style", "dolcett", "domination", "dominatrix", "dommes", "dong", "donkey punch", "donkeypunch", "donkeyribber", "doochbag", "doofus", "dookie", "doosh", "dopey", "double dong", "double penetration", "Doublelift", "douch3", "douche", "douchebag", "douchebags", "douche-fag", "douchewaffle", "douchey", "dp action", "drunk", "dry hump", "duche", "dumass", "dumb ass", "dumbass", "dumbasses", "Dumbcunt", "dumbfuck", "dumbshit", "dummy", "dumshit", "dvda", "dyke", "dykes", "eat a dick", "eat a dick", "eat hair pie", "eat hair pie", "eat my ass", "ecchi", "ejaculate", "ejaculated", "ejaculates", "ejaculates", "ejaculating", "ejaculating", "ejaculatings", "ejaculation", "ejakulate", "erect", "erection", "erotic", "erotism", "escort", "essohbee", "eunuch", "extacy", "extasy", "f u c k", "f u c k e r", "f.u.c.k", "f_u_c_k", "f4nny", "facial", "fack", "fag", "fagbag", "fagfucker", "fagg", "fagged", "fagging", "faggit", "faggitt", "faggot", "faggotcock", "faggots", "faggs", "fagot", "fagots", "fags", "fagtard", "faig", "faigt", "fanny", "fannybandit", "fannyflaps", "fannyfucker", "fanyy", "fart", "fartknocker", "fatass", "fcuk", "fcuker", "fcuking", "fecal", "feck", "fecker", "feist", "felch", "felcher", "felching", "fellate", "fellatio", "feltch", "feltcher", "female squirting", "femdom", "fenian", "fice", "figging", "fingerbang", "fingerfuck", "fingerfuck", "fingerfucked", "fingerfucked", "fingerfucker", "fingerfucker", "fingerfuckers", "fingerfucking", "fingerfucking", "fingerfucks", "fingerfucks", "fingering", "fist fuck", "fist fuck", "fisted", "fistfuck", "fistfucked", "fistfucked", "fistfucker", "fistfucker", "fistfuckers", "fistfuckers", "fistfucking", "fistfucking", "fistfuckings", "fistfuckings", "fistfucks", "fistfucks", "fisting", "fisty", "flamer", "flange", "flaps", "fleshflute", "flog the log", "flog the log", "floozy", "foad", "foah", "fondle", "foobar", "fook", "fooker", "foot fetish", "footjob", "foreskin", "freex", "frenchify", "frigg", "frigga", "frotting", "fubar", "fuc", "fuck", "fuck", "f-u-c-k", "fuck buttons", "fuck hole", "fuck hole", "Fuck off", "fuck puppet", "fuck puppet", "fuck trophy", "fuck trophy", "fuck yo mama", "fuck yo mama", "fuck you", "fucka", "fuckass", "fuck-ass", "fuck-ass", "fuckbag", "fuck-bitch", "fuck-bitch", "fuckboy", "fuckbrain", "fuckbutt", "fuckbutter", "fucked", "fuckedup", "fucker", "fuckers", "fuckersucker", "fuckface", "fuckhead", "fuckheads", "fuckhole", "fuckin", "fucking", "fuckings", "fuckingshitmotherfucker", "fuckme", "fuckme", "fuckmeat", "fuckmeat", "fucknugget", "fucknut", "fucknutt", "fuckoff", "fucks", "fuckstick", "fucktard", "fuck-tard", "fucktards", "fucktart", "fucktoy", "fucktoy", "fucktwat", "fuckup", "fuckwad", "fuckwhit", "fuckwit", "fuckwitt", "fudge packer", "fudgepacker", "fudge-packer", "fuk", "fuker", "fukker", "fukkers", "fukkin", "fuks", "fukwhit", "fukwit", "fuq", "futanari", "fux", "fux0r", "fvck", "fxck", "gae", "gai", "gang bang", "gangbang", "gang-bang", "gang-bang", "gangbanged", "gangbangs", "ganja", "gash", "gassy ass", "gassy ass", "gay", "gay sex", "gayass", "gaybob", "gaydo", "gayfuck", "gayfuckist", "gaylord", "gays", "gaysex", "gaytard", "gaywad", "gender bender", "genitals", "gey", "gfy", "ghay", "ghey", "giant cock", "gigolo", "ginger", "gippo", "girl on", "girl on top", "girls gone wild", "git", "glans", "goatcx", "goatse", "god", "god damn", "godamn", "godamnit", "goddam", "god-dam", "goddammit", "goddamn", "goddamned", "god-damned", "goddamnit", "godsdamn", "gokkun", "golden shower", "goldenshower", "golliwog", "gonad", "gonads", "goo girl", "gooch", "goodpoop", "gook", "gooks", "goregasm", "gringo", "grope", "group sex", "gspot", "g-spot", "gtfo", "guido", "guro", "h0m0", "h0mo", "ham flap", "ham flap", "hand job", "handjob", "hard core", "hard on", "hardcore", "hardcoresex", "he11", "hebe", "heeb", "hell", "hemp", "hentai", "heroin", "herp", "herpes", "herpy", "heshe", "he-she", "hircismus", "hitler", "hiv", "ho", "hoar", "hoare", "hobag", "hoe", "hoer", "holy shit", "hom0", "homey", "homo", "homodumbshit", "homoerotic", "homoey", "honkey", "honky", "hooch", "hookah", "hooker", "hoor", "hootch", "hooter", "hooters", "hore", "horniest", "horny", "hot carl", "hot chick", "hotsex", "how to kill", "how to murdep", "how to murder", "huge fat", "hump", "humped", "humping", "hun", "hussy", "hymen", "iap", "iberian slap", "inbred", "incest", "injun", "intercourse", "jack off", "jackass", "jackasses", "jackhole", "jackoff", "jack-off", "jaggi", "jagoff", "jail bait", "jailbait", "jap", "japs", "jelly donut", "jerk", "jerk off", "jerk0ff", "jerkass", "jerked", "jerkoff", "jerk-off", "jigaboo", "jiggaboo", "jiggerboo", "jism", "jiz", "jiz", "jizm", "jizm", "jizz", "jizzed", "jock", "juggs", "jungle bunny", "junglebunny", "junkie", "junky", "kafir", "kawk", "kike", "kikes", "kill", "kinbaku", "kinkster", "kinky", "klan", "knob", "knob end", "knobbing", "knobead", "knobed", "knobend", "knobhead", "knobjocky", "knobjokey", "kock", "kondum", "kondums", "kooch", "kooches", "kootch", "kraut", "kum", "kummer", "kumming", "kums", "kunilingus", "kunja", "kunt", "kwif", "kwif", "kyke", "l3i+ch", "l3itch", "labia", "lameass", "lardass", "leather restraint", "leather straight jacket", "lech", "lemon party", "LEN", "leper", "lesbian", "lesbians", "lesbo", "lesbos", "lez", "lezza/lesbo", "lezzie", "lmao", "lmfao", "loin", "loins", "lolita", "looney", "lovemaking", "lube", "lust", "lusting", "lusty", "m0f0", "m0fo", "m45terbate", "ma5terb8", "ma5terbate", "mafugly", "mafugly", "make me come", "male squirting", "mams", "masochist", "massa", "masterb8", "masterbat*", "masterbat3", "masterbate", "master-bate", "master-bate", "masterbating", "masterbation", "masterbations", "masturbate", "masturbating", "masturbation", "maxi", "mcfagget", "menage a trois", "menses", "menstruate", "menstruation", "meth", "m-fucking", "mick", "microphallus", "middle finger", "midget", "milf", "minge", "minger", "missionary position", "mof0", "mofo", "mo-fo", "molest", "mong", "moo moo foo foo", "moolie", "moron", "mothafuck", "mothafucka", "mothafuckas", "mothafuckaz", "mothafucked", "mothafucked", "mothafucker", "mothafuckers", "mothafuckin", "mothafucking", "mothafucking", "mothafuckings", "mothafucks", "mother fucker", "mother fucker", "motherfuck", "motherfucka", "motherfucked", "motherfucker", "motherfuckers", "motherfuckin", "motherfucking"]

def query_city_info(name):
    global cities
    if cities is None:
        if CITY_LIST_FILE:
            with open(CITY_LIST_FILE) as f:
                cities = json.load(f)
    for city in cities:
        if name.title() in city['name']:
            return city

def str_cleanup(text):
    if text:
        text = text.strip()
        text = ' '.join(text.split())
        if text and text[0] == '.':
            text = text[1:]
    return text

def norm(s):
    if s is None:
        return s
    s = re.sub(r'\[.*\]', '', s) # remote [xxx] mark
    s = ' '.join(s.split())  # remove consecutive spaces
    s = s.strip()
    return s

def shorten(text, cutoff):
    if not text or len(text) < cutoff:
        return text, ''
    sens = text.split('.')
    ret = ''
    for idx, sen in enumerate(sens):
        if len(ret) > 0 and len(ret+sen) > cutoff:
            break
        ret += (sen+'.')

    res = '.'.join(sens[idx:])

    # If first part or second part is too short, then don't cut
    if len(ret.split()) < 3 or len(res.split()) < 3:
        ret = text
        res = ''

    ret = str_cleanup(ret)
    res = str_cleanup(res)
    return ret, res

def get_ip():
    logger.info("Getting public IP address")
    ip = None
    try:
        ip = subprocess.check_output(['wget', '--timeout', '3', '-qO-',
            'ipinfo.io/ip']).strip()
        logger.info("Got IP %s", ip)
    except subprocess.CalledProcessError as ex:
        logger.error("Can't find public IP address")
        logger.error(ex)
    if not ip:
        logger.error("Public IP is invalid")
    return ip

def fill_local_ip_address(location):
    ip = location.get('ip')
    if ip == '61.244.164.169':
        location['neighborhood'] = 'Fo Tan Office'
    elif ip == '61.92.69.39':
        location['neighborhood'] = 'Science Park Office'
    elif ip == '203.185.4.45':
        location['neighborhood'] = 'Tsuen Wan Office'

def get_ip_location(ip=None):
    if not ip:
        return {}
    # docker run -d -p 8004:8004 --name freegeoip fiorix/freegeoip -http :8004
    host = os.environ.get('LOCATION_SERVER_HOST', 'localhost')
    port = os.environ.get('LOCATION_SERVER_PORT', '8004')
    location = {}
    try:
        logger.info("Getting location")
        response = requests.get('http://{host}:{port}/json/{ip}'.format(host=host, port=port, ip=ip), timeout=2).json()
        if not response:
            logger.error("Can't get location")
            return None
        logger.info("Got location info %s", location)
        if response['country_code'] == 'HK':
            location['city'] = 'Hong Kong'
        if response['country_code'] == 'TW':
            location['city'] = 'Taipei'
        if response['country_code'] == 'MO':
            location['city'] = 'Macau'
        if not response.get('city'):
           if response['time_zone']:
               time_zone = response['time_zone'].split('/')[-1]
               location['city'] = time_zone.replace('_', ' ')
               logger.warn("No city in the location info. Will use timezone name, %s", time_zone)
        location['country'] = response['country_name']
        location['neighborhood'] = response['region_name']
        location['ip'] = response['ip']
        fill_local_ip_address(location)
    except subprocess.CalledProcessError as ex:
        logger.error("Can't find public IP address")
        logger.error(ex)
    except Exception as ex:
        logger.error(ex)
    return location

def get_location(ip=None):
    location = {}
    if not ip:
        ip = get_ip()
        location['ip'] = ip
    try:
        import googlemaps
        gmaps = googlemaps.Client(key=os.environ.get('GCLOUD_API_KEY'))
        response = gmaps.geolocate()
        reverse_geocode_results = gmaps.reverse_geocode(
            (response['location']['lat'], response['location']['lng']))
        for result in reverse_geocode_results:
            for address_component in result.get('address_components'):
                name = address_component.get('long_name')
                if not name:
                    continue
                types = address_component.get('types')
                if 'political' in types:
                    if 'neighborhood' in types:
                        location['neighborhood'] = name
                    if 'locality' in types:
                        location['city'] = name
                    if 'country' in types:
                        location['country'] = name
                    if 'administrative_area_level_1' in types:
                        location['administrative_area_level_1'] = name
                    if 'administrative_area_level_2' in types:
                        location['administrative_area_level_2'] = name
                if 'route' in types:
                    location['route'] = name
                if 'street_number' in types:
                    location['street_number'] = name
        fill_local_ip_address(location)
        return location
    except Exception as ex:
        logger.error(ex)
    return get_ip_location(ip)

def format_location(location):
    address = []
    for type in ['neighborhood', 'administrative_area_level_2',
            'administrative_area_level_1', 'locality', 'country']:
        if type in location:
            address.append(location.get(type))
    return ' '.join(address)

def get_weather(city):
    logger.info("Getting weather")
    if city:
        try:
            response = requests.get(
                'http://api.openweathermap.org/data/2.5/weather',
                timeout=5,
                params={'q': city, 'appid': OPENWEATHERAPPID}).json()
        except Exception as ex:
            logger.error(ex)
            return
        return response

def get_weather_by_id(city_id):
    if city_id:
        try:
            response = requests.get(
                'http://api.openweathermap.org/data/2.5/weather',
                timeout=5,
                params={'id': city_id, 'appid': OPENWEATHERAPPID}).json()
        except Exception as ex:
            logger.error(ex)
            return
        return response

def parse_weather(weather):
    kelvin = 273.15
    prop = {}
    if weather and weather['cod'] == 200:
        if 'main' in weather:
            if 'temp_max' in weather['main']:
                prop['high_temperature'] = \
                    '{:.0f}'.format(weather['main'].get('temp_max')-kelvin)
            if 'temp_min' in weather['main']:
                prop['low_temperature'] = \
                    '{:.0f}'.format(weather['main'].get('temp_min')-kelvin)
            if 'temp' in weather['main']:
                prop['temperature'] = \
                    '{:.0f}'.format(weather['main'].get('temp')-kelvin)
        if 'weather' in weather and weather['weather']:
            prop['weather'] = weather['weather'][0]['description']
    return prop

def check_online(url='8.8.8.8', port='80', timeout=1):
    try:
        subprocess.check_output(['ping', '-q', '-w', str(timeout), '-c', '1', str(url)],
            stderr=subprocess.STDOUT)
    except Exception as ex:
        return False
    return True

def get_emotion(timedelta=3):
    emotion_file = os.path.expanduser('~/.hr/chatbot/data/emotion.csv')
    if os.path.isfile(emotion_file):
        df = pd.read_csv(emotion_file, header=None, parse_dates=[0])
        df.columns = ['Datetime', 'Emotion']
        df = df[(dt.datetime.utcnow()-df['Datetime'])/np.timedelta64(1, 's')<timedelta]
        if not df.empty:
            return df.tail(1).iloc[0].Emotion

def get_detected_object(timedelta=10):
    object_file = os.path.expanduser('~/.hr/chatbot/data/objects.csv')
    if os.path.isfile(object_file):
        df = pd.read_csv(object_file, header=None, parse_dates=[0])
        df.columns = ['Datetime', 'Item']
        df = df[(dt.datetime.utcnow()-df['Datetime'])/np.timedelta64(1, 's')<timedelta]
        if not df.empty:
            item = df.tail(1).iloc[0].Item
            logger.warn("Get item {}".format(item))
            return item

def do_translate(text, target_language='en-US'):
    lang = None
    for key, value in CHATBOT_LANGUAGE_DICT.iteritems():
        if target_language in value:
            lang = key
    if lang is None:
        logger.error("Target language '%s' is not supported.", target_language)
        return False, text

    change_encoding = False
    if isinstance(text, six.binary_type):
        change_encoding = True
        text = text.decode('utf-8')

    client = translate.Client()
    logger.info('Translating %s, target language code %s(%s)', text, target_language, lang)
    start_time = time.time()
    result = client.translate(text, target_language=lang)
    elapse = time.time() - start_time
    logger.info('Translating took %s seconds', elapse)

    detected_source_language = CHATBOT_LANGUAGE_DICT.get(result['detectedSourceLanguage'])
    if detected_source_language is None:
        logger.warn("Detected language is %s", detected_source_language)
    if detected_source_language is not None and target_language in detected_source_language:
        translated_text = text
        translated = False
        logger.info("No need to translate. The source language is the same as the target language.")
    else:
        translated_text = result['translatedText']
        translated = True
        logger.info('Translation: %s (source %s)', translated_text, detected_source_language)

    if change_encoding and isinstance(translated_text, six.text_type):
        translated_text = translated_text.encode('utf-8')

    return translated, translated_text

def detect_language(text):
    translate_client = translate.Client()
    result = translate_client.detect_language(text)
    if result['language'] == 'zh-CN':
        result['language'] == 'zh'
    return result

def norm2(text):
    if text is None:
        return text
    text = norm(text)
    text = PUNCTUATORS.sub('', text)
    text = english_word_sub.sub(text)
    text = text.lower()
    return text

def test():
    text = '''My mind is built using Hanson Robotics' character engine, a simulated humanlike brain that runs inside a personal computer. Within this framework, Hanson has modelled Phil's personality and emotions, allowing you to talk with Phil through me, using speech recognition, natural language understanding, and computer vision such as face recognition, and animation of the robotic muscles in my face.'''
    print len(text)
    print text
    print shorten(text, 123)

    text = '''My mind is built using Hanson Robotics' character engine'''
    print len(text)
    print text
    print shorten(text, 123)

    print str_cleanup('.')
    print str_cleanup(' .ss ')
    print str_cleanup(' s.ss ')
    print str_cleanup('')
    print str_cleanup(None)
    print check_online('google.com')
    print check_online('duckduckgo.com', 80)
    print get_emotion()

    print get_detected_object(100)
    print do_translate(u"你好", 'ru-RU')[1]
    print do_translate(u"о Кларе с Карлом во мраке все раки шумели в драке", 'cmn-Hans-CN')[1]
    print norm2(u"[hi] 你好What's new?")

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--location', action='store_true', help='print the current city based on IP')
    args = parser.parse_args()
    if args.location:
        location  = get_location()
        pprint.pprint(location)
