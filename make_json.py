import ConfigParser
import os
import json

obj = {}
config = ConfigParser.ConfigParser()
config.read(os.path.join(os.getenv("HOME"), ".aws", "config"))
obj["MY_ACCESS_KEY"] = config.get("default", "aws_access_key_id", "")
obj["MY_SECRET_KEY"] = config.get("default", "aws_secret_access_key", "")
# TODO: remove this once we're all up to date on the live site with the AWS changes
obj["GOOGLE_API_KEY"] = config.get("google", "google_api_key", "")

with open("config.json", "w") as out:
    json.dump(obj, out)
