import datetime
import json
import logging
import os
from typing import Optional, Dict

import aws_embedded_metrics
import boto3
import botocore.client
from aws_embedded_metrics.logger.metrics_logger import MetricsLogger

STATIC_HEADERS = {
    "Content-Type": "text/plain; charset=utf-8",
    "Cache-Control": "no-cache"
}

RECORD_KEY = "Records"

logger = logging.getLogger()
logger.setLevel(logging.INFO)


@aws_embedded_metrics.metric_scope
def lambda_handler(event, context, metrics):
    metrics.set_namespace("CompilerExplorer")
    logger.info("Received new lambda event %s", event)
    if RECORD_KEY in event:
        return handle_sqs(event, context)
    return handle_http(event, metrics)


def handle_sqs(
        event: Dict,
        context,
        s3_client: Optional[botocore.client.BaseClient] = None,
        now: Optional[datetime.datetime] = None):
    s3_client = s3_client or boto3.client('s3')
    now = now or datetime.datetime.utcnow()

    logger.info("Handling %d messages", len(event[RECORD_KEY]))
    key = f"stats/{context.function_name}-{now.strftime('%Y-%m-%d-%H:%M:%S.%f')}.log"
    body = "\n".join(r["body"] for r in event[RECORD_KEY])
    bucket_name = os.environ['S3_BUCKET_NAME']
    logger.info("writing to %s with key %s", bucket_name, key)
    s3_client.put_object(Bucket=bucket_name, Body=body, Key=key)


def handle_http(
        event: Dict,
        metrics: MetricsLogger,
        sqs_client: Optional[botocore.client.BaseClient] = None,
        now: Optional[datetime.datetime] = None):
    sqs_client = sqs_client or boto3.client('sqs')
    now = now or datetime.datetime.utcnow()

    if event['path'] == '/pageload':
        return handle_pageload(event, metrics, now, os.environ['SQS_STATS_QUEUE'], sqs_client)

    return dict(
        statusCode=404,
        statusDescription="404 Not Found",
        isBase64Encoded=False,
        headers=STATIC_HEADERS,
        body="Not found"
    )


def handle_pageload(
        event: Dict,
        metrics: MetricsLogger,
        now: datetime.datetime,
        queue_url: str,
        sqs_client: botocore.client.BaseClient):
    date = str(now.date())
    time = str(now.time())
    sqs_client.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps(dict(type='PageLoad', date=date, time=time, value=''), sort_keys=True))
    sponsors = list(filter(lambda x: x, event['queryStringParameters'].get('sponsors', '').split(',')))
    for sponsor in sponsors:
        sqs_client.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(dict(type='SponsorView', date=date, time=time, value=sponsor), sort_keys=True))
    metrics.set_property("sponsors", sponsors)
    metrics.put_metric("PageLoad", 1)
    return dict(
        statusCode=200,
        statusDescription="200 OK",
        isBase64Encoded=False,
        headers=STATIC_HEADERS,
        body="Ok"
    )
