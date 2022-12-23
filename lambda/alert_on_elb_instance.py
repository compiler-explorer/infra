import enum
import json
import boto3

import logging
from dataclasses import dataclass
import os

BASE_CW_URL = "https://console.aws.amazon.com/cloudwatch/home"
REGION = "us-east-1"
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, _context):
    sns_client = boto3.client("sns")
    topic_arn = os.getenv("TOPIC_ARN")
    for record in event.get("Records", []):
        try:
            parsed = parse_sns_message(json.loads(record["Sns"]["Message"]))
            logging.info("Parsed as %s", parsed)
            if parsed.reason in (Reason.FailedHealthCheck, Reason.Unknown):
                sns_client.publish(
                    TopicArn=topic_arn,
                    Message=json.dumps(
                        dict(
                            ElbInstanceType=parsed.reason.value,
                            Environment=parsed.environment,
                            Cause=parsed.cause,
                            Instance=parsed.instance,
                        )
                    ),
                    Subject="Instance failed health check",
                )
        except RuntimeError as e:
            logging.exception("Unable to parse")
            sns_client.publish(
                TopicArn=topic_arn,
                Message=json.dumps(dict(error=f"Problem with health check parsing: {e}")),
                Subject="Exception handling instance state",
            )
            logging.info("moo")


class Reason(enum.Enum):
    Unknown = "Unknown"
    ScaledDown = "ScaledDown"
    EnvironmentStop = "EnvironmentStop"
    FailedHealthCheck = "FailedHealthCheck"


@dataclass(frozen=True)
class ParsedMessage:
    environment: str
    instance: str
    cause: str
    reason: Reason


def parse_sns_message(sns_message: dict) -> ParsedMessage:
    logging.info("sns message: %s", json.dumps(sns_message))

    ec2_instance = sns_message["EC2InstanceId"]
    environment = sns_message["AutoScalingGroupName"]
    cause = sns_message["Cause"]
    details = sns_message["Details"]
    if "InvokingAlarms" in details:
        # Assume any alarm-based shutdown is reducing size
        reason = Reason.ScaledDown
    elif "user request update" in cause:
        reason = Reason.EnvironmentStop
    elif "ELB system health check failure" in cause:
        reason = Reason.FailedHealthCheck
    else:
        reason = Reason.Unknown

    return ParsedMessage(environment=environment, instance=ec2_instance, reason=reason, cause=cause)


# if __name__ == "__main__":
#     # Use this to test; set your env var to the CE ARN.
#     msg = {}  # copy paste from tests
#     lambda_handler(dict(Records=[{'Sns': {'Message': json.dumps(msg)}}]), None)
