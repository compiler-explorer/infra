import json
from datetime import datetime
from typing import Dict

import boto3

versionTablename = "nightly-version"
nightlyExeTablename = "nightly-exe"
db_client = boto3.client("dynamodb")


def lambda_handler(event, _context):
    if "queryStringParameters" not in event:
        return default_error("No event.queryStringParameters")

    jsonp = ""
    if "jsonp" in event["queryStringParameters"]:
        jsonp = event["queryStringParameters"]["jsonp"]

    item = False
    if "id" in event["queryStringParameters"]:
        exeItem = get_exe_path_by_compiler_id(event["queryStringParameters"]["id"])
        if not exeItem or "Item" not in exeItem:
            return default_error("No exe found based on id " + event["queryStringParameters"]["id"])
        else:
            exe = exeItem["Item"]["exe"]["S"]
            item = get_exe_version(exe)
            if not item or "Item" not in item:
                return default_error("No exe found based on path " + exe)

    if "exe" in event["queryStringParameters"]:
        exe = event["queryStringParameters"]["exe"]
        item = get_exe_version(exe)
        if not item or "Item" not in item:
            return default_error("No exe found based on path " + exe)

    return respond_with_version(item["Item"], jsonp)


def respond_with_version(version: Dict, jsonp: str):
    modified_iso = None
    if "modified" in version:
        timestamp = float(version["modified"]["N"])
        modified_iso = datetime.fromtimestamp(timestamp).isoformat()
    
    if jsonp:
        return dict(
            statusCode=200,
            headers={"content-type": "application/javascript"},
            body=jsonp
            + "("
            + json.dumps(
                {
                    "version": version["version"]["S"],
                    "full_version": version["full_version"]["S"],
                    "modified": modified_iso,
                }
            )
            + ");",
        )
    else:
        return dict(
            statusCode=200,
            headers={
                "content-type": "application/json",
                "cache-control": "max-age=3600, public",
                "max-age": "3600",
                "s-maxage": "3600",
            },
            body=json.dumps(
                {
                    "version": version["version"]["S"],
                    "full_version": version["full_version"]["S"],
                    "modified": modified_iso,
                }
            ),
        )


def default_error(errortext: str):
    return dict(statusCode=404, headers={"content-type": "application/json"}, body=json.dumps({"error": errortext}))


def get_exe_version(exe):
    return db_client.get_item(TableName=versionTablename, Key=dict(exe=dict(S=exe)))


def get_exe_path_by_compiler_id(compiler_id):
    return db_client.get_item(TableName=nightlyExeTablename, Key=dict(id=dict(S=compiler_id)))
