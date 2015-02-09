import config

import json

obj = {}
for key in dir(config):
    if key[0] == '_': continue
    obj[key] = config.__dict__[key]

with open("config.json", "w") as out:
    json.dump(obj, out)
