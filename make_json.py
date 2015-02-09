import config
import ConfigParser
import os
import json

obj = {}
for key in dir(config):
    if key[0] == '_': continue
    obj[key] = config.__dict__[key]

config = ConfigParser.ConfigParser()
config.read(os.path.join(os.getenv("HOME"), ".aws", "config"))
obj["MY_ACCESS_KEY"] = config.get("default", "aws_access_key_id", "")
obj["MY_SECRET_KEY"] = config.get("default", "aws_secret_access_key", "")

with open("config.json", "w") as out:
    json.dump(obj, out)
