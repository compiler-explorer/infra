import boto3
import json

remote_archs_table = "remote-exec-archs"
db_client = boto3.client("dynamodb")


def lambda_handler(event, _context):
    jsonp = ""
    env = "prod"
    if "queryStringParameters" in event:
        try:
            jsonp = event["queryStringParameters"]["jsonp"]
        except KeyError:
            jsonp = ""
        except TypeError:
            jsonp = ""
        try:
            env = event["queryStringParameters"]["env"]
        except KeyError:
            jsonp = ""
        except TypeError:
            env = "prod"

    items = []

    result = get_remote_execution_archs(env)

    for row in result["Items"]:
        items.append(row["triple"]["S"])

    return respond_with_array(items, jsonp)


def respond_with_array(items: set, jsonp: str):
    if jsonp:
        return dict(
            statusCode=200,
            headers={"content-type": "application/javascript"},
            body=jsonp + "(" + json.dumps(items) + ");",
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
            body=json.dumps(items),
        )


def default_error(errortext: str):
    return dict(statusCode=404, headers={"content-type": "application/json"}, body=json.dumps({"error": errortext}))


def get_remote_execution_archs(env: str):
    return db_client.scan(TableName=f"{env}-{remote_archs_table}")


# print(lambda_handler({"queryStringParameters": []}, None))
