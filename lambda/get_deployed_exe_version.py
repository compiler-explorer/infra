import boto3
import json
from typing import Dict

versionTablename = "nightly-version"
nightlyExeTablename = "nightly-exe"
db_client = boto3.client("dynamodb")


def lambda_handler(event, _context):
    if not ("queryStringParameters" in event):
        return defaultError("No event.queryStringParameters")

    jsonp = ""
    if "jsonp" in event["queryStringParameters"]:
        jsonp = event["queryStringParameters"]["jsonp"]

    item = False
    if "id" in event["queryStringParameters"]:
        exeItem = getExePathByCompilerId(event["queryStringParameters"]["id"])
        if not exeItem or not "Item" in exeItem:
            return defaultError("No exe found based on id " + event["queryStringParameters"]["id"])
        else:
            exe = exeItem["Item"]["exe"]["S"]
            item = getExeVersion(exe)
            if not item or not "Item" in item:
                return defaultError("No exe found based on path " + exe)

    if "exe" in event["queryStringParameters"]:
        exe = event["queryStringParameters"]["exe"]
        item = getExeVersion(exe)
        if not item or not "Item" in item:
            return defaultError("No exe found based on path " + exe)

    return respondWithVersion(item["Item"], jsonp)


def respondWithVersion(version: Dict, jsonp: str):
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
                }
            )
            + ");",
        )
    else:
        return dict(
            statusCode=200,
            headers={"content-type": "application/json"},
            body=json.dumps(
                {
                    "version": version["version"]["S"],
                    "full_version": version["full_version"]["S"],
                }
            ),
        )


def defaultError(errortext: str):
    return dict(statusCode=404, headers={"content-type": "application/json"}, body=json.dumps({"error": errortext}))


def getExeVersion(exe):
    return db_client.get_item(TableName=versionTablename, Key=dict(exe=dict(S=exe)))


def getExePathByCompilerId(compiler_id):
    return db_client.get_item(TableName=nightlyExeTablename, Key=dict(id=dict(S=compiler_id)))


# obj: Dict = dict(
#     Item = dict(
#         exe = dict(S = "bla.exe"),
#         version = dict(S = "1.0"),
#         full_version = dict(S = "1.0 copyright etc")
#     )
# )
# ver = respondWithVersion(obj["Item"])
# print(ver)
