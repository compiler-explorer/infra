import datetime
import json
import logging
import os
import urllib.parse
from typing import Any

import boto3
import botocore.client

STATIC_HEADERS = {
    "Content-Type": "text/plain; charset=utf-8",
    "Cache-Control": "no-cache",
    "Access-Control-Allow-Origin": "*",
}

RECORD_KEY = "Records"
METRICS_NAMESPACE = "CompilerExplorer"

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def emit_metric(
    name: str,
    value: float,
    properties: dict[str, Any] | None = None,
    unit: str = "None",
    now: datetime.datetime | None = None,
) -> None:
    # CloudWatch derives metrics from Embedded Metric Format records in the logs.
    # The record must be a bare JSON line on stdout: routing it through `logger`
    # would prefix the line and stop CloudWatch from parsing it.
    now = now or datetime.datetime.now(datetime.UTC)
    record: dict[str, Any] = {
        "_aws": {
            "Timestamp": int(now.timestamp() * 1000),
            "CloudWatchMetrics": [
                {
                    "Namespace": METRICS_NAMESPACE,
                    "Dimensions": [[]],
                    "Metrics": [{"Name": name, "Unit": unit}],
                }
            ],
        },
        name: value,
    }
    if properties:
        record.update(properties)
    print(json.dumps(record))


def lambda_handler(event, context):
    logger.info("Received new lambda event %s", event)
    if RECORD_KEY in event:
        return handle_sqs(event, context)
    return handle_http(event)


def handle_sqs(
    event: dict,
    context,
    s3_client: botocore.client.BaseClient | None = None,
    now: datetime.datetime | None = None,
):
    s3_client = s3_client or boto3.client("s3")
    now = now or datetime.datetime.now(datetime.UTC)

    logger.info("Handling %d messages", len(event[RECORD_KEY]))
    key = f"stats/{context.function_name}-{now.strftime('%Y-%m-%d-%H:%M:%S.%f')}.log"
    body = "\n".join(r["body"] for r in event[RECORD_KEY])
    bucket_name = os.environ["S3_BUCKET_NAME"]
    logger.info("writing to %s with key %s", bucket_name, key)
    s3_client.put_object(Bucket=bucket_name, Body=body, Key=key)


def handle_http(
    event: dict,
    sqs_client: botocore.client.BaseClient | None = None,
    dynamo_client: botocore.client.BaseClient | None = None,
    now: datetime.datetime | None = None,
):
    sqs_client = sqs_client or boto3.client("sqs")
    dynamo_client = dynamo_client or boto3.client("dynamodb")
    now = now or datetime.datetime.now(datetime.UTC)

    path = event["path"].split("/")[1:]
    method = event["httpMethod"]
    if path == ["pageload"] and method == "POST":
        return handle_pageload(event, now, os.environ["SQS_STATS_QUEUE"], sqs_client)

    if len(path) == 2 and path[0] == "compiler-build" and method == "GET":
        return handle_compiler_stats(path[1], os.environ["COMPILER_BUILD_TABLE"], dynamo_client)

    return dict(
        statusCode=404,
        statusDescription="404 Not Found",
        isBase64Encoded=False,
        headers=STATIC_HEADERS,
        body="Not found",
    )


def handle_pageload(event: dict, now: datetime.datetime, queue_url: str, sqs_client: botocore.client.BaseClient):
    date = now.strftime("%Y-%m-%d")
    time = now.strftime("%H:%M:%S")
    sqs_client.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps(dict(type="PageLoad", date=date, time=time, value=""), sort_keys=True),
    )
    icons = urllib.parse.unquote_plus(event["queryStringParameters"].get("icons", ""))
    sponsors = list(filter(lambda x: x, icons.split(",")))
    for sponsor in sponsors:
        sqs_client.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(dict(type="SponsorView", date=date, time=time, value=sponsor), sort_keys=True),
        )
    emit_metric("PageLoad", 1, properties={"sponsors": sponsors}, now=now)

    return dict(statusCode=200, statusDescription="200 OK", isBase64Encoded=False, headers=STATIC_HEADERS, body="Ok")


# Example query from the UI
# {"TableName":"compiler-builds","ReturnConsumedCapacity":
# "TOTAL","Limit":50,"KeyConditionExpression":"#kn0 = :kv0",
# "ScanIndexForward":false,"FilterExpression":"#n0 = :v0",
# "ExpressionAttributeNames":{"#n0":"status","#kn0":"compiler"},
# "ExpressionAttributeValues":{":v0":{"S":"OK"},":kv0":{"S":"gcc"}}}


def _do_one_query(
    compiler: str, table: str, dynamo_client: botocore.client.BaseClient, status: str | None
) -> dict | None:
    params: dict[str, Any] = dict(
        TableName=table,
        Limit=100,  # NB limit to _evaluate_ not the limit of matches
        ScanIndexForward=False,  # items in reverse order (by time)
        KeyConditionExpression="#key = :compiler",
        ExpressionAttributeNames={"#key": "compiler"},
        ExpressionAttributeValues={":compiler": dict(S=compiler)},
    )
    if status is not None:
        params["FilterExpression"] = "#status = :status_filter"
        params["ExpressionAttributeNames"]["#status"] = "status"
        params["ExpressionAttributeValues"][":status_filter"] = dict(S=status or "na")

    query_results = dynamo_client.query(**params)
    if query_results["Count"]:
        most_recent = query_results["Items"][0]
        return dict(
            path=most_recent["path"]["S"],
            github_run_id=most_recent["github_run_id"]["S"],
            timestamp=most_recent["timestamp"]["S"],
            duration=int(most_recent["duration"]["N"]),
        )
    return None


def handle_compiler_stats(compiler: str, table: str, dynamo_client: botocore.client.BaseClient) -> dict:
    result = dict(
        last_success=_do_one_query(compiler, table, dynamo_client, "OK"),
        last_build=_do_one_query(compiler, table, dynamo_client, None),
    )
    return dict(
        statusCode=200,
        statusDescription="200 OK",
        isBase64Encoded=False,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": "max-age: 180, must-revalidate",
            "Access-Control-Allow-Origin": "*",
        },
        body=json.dumps(result),
    )
