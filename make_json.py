from configparser import ConfigParser
import os
import json


def main():
    obj = {}
    config = ConfigParser()
    config.read(os.path.join(os.getenv("HOME", ""), ".aws", "credentials"))
    obj["MY_ACCESS_KEY"] = config.get("default", "aws_access_key_id", fallback="")
    obj["MY_SECRET_KEY"] = config.get("default", "aws_secret_access_key", fallback="")

    with open("config.json", "w", encoding="utf-8") as out:
        json.dump(obj, out)


if __name__ == "__main__":
    main()
