import json
import requests
import os
import logging

BASE_CW_URL = 'https://console.aws.amazon.com/cloudwatch/home'
REGION = 'us-east-1'
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def parse_service_event(event, service='Service'):
    return [
        dict(name='Alarm', value=event['AlarmName'], inline=True),
        dict(name=service, value=event['Trigger']['Dimensions'][0]['value'], inline=True),
        dict(name='Description', value=event['AlarmDescription'], inline=True),
        dict(name='Trigger', value=event['Trigger']['MetricName'], inline=True),
        dict(name='Event', value=event['NewStateReason'], inline=False)
    ]


def lambda_handler(event, context):
    webhook_url = os.getenv("WEBHOOK_URL")
    parsed_message = []
    for record in event.get('Records', []):
        sns_message = json.loads(record['Sns']['Message'])
        logging.info("sns message: %s", record['Sns']['Message'])
        is_alarm = sns_message.get('Trigger', None)
        description = ''
        title = 'CloudWatch Alert!'
        if is_alarm and is_alarm['Namespace'] in ('AWS/Lambda', 'AWS/ApplicationELB'):
            parsed_message = parse_service_event(sns_message, is_alarm['Namespace'])
            alarm_name = sns_message["AlarmName"]
            url = f'{BASE_CW_URL}?region={REGION}#alarmsV2:alarm/{alarm_name}?'
            description = f"A [cloudwatch alarm]({url}) has posted to the SNS notification channel"
            title = f'CloudWatch Alert - {alarm_name}!'
        if not parsed_message:
            logging.error("Unparsed message: %s", sns_message)
            parsed_message = [
                dict(name='Something non-parseable happened...check the logs',
                     value=json.dumps(sns_message)[:100] + '...')]
        discord_data = dict(username='AWS',
                            avatar_url='https://a0.awsstatic.com/libra-css/images/logos/aws_logo_smile_1200x630.png',
                            embeds=[dict(color=0xee3333, title=title,
                                         description=description,
                                         fields=parsed_message)])

        headers = {'content-type': 'application/json'}
        logging.info(discord_data)
        response = requests.post(webhook_url, data=json.dumps(discord_data), headers=headers)

        logging.info(f'Discord response: {response.status_code}')
        logging.info(response.content)


if __name__ == "__main__":
    # Use this to test; set your env var to the webhook endpoint to try.
    event = {
        "AlarmName": "Traffic",
        "AlarmDescription": "A high amount of traffic: did we just get slashdotted?",
        "AWSAccountId": "052730242331",
        "NewStateValue": "ALARM",
        "NewStateReason": "Threshold Crossed: 3 out of the last 3 datapoints [1141.0 (09/10/20 21:24:00), 1226.0 (09/10/20 21:19:00), 1390.0 (09/10/20 21:14:00)] were greater than or equal to the threshold (30.0) (minimum 3 datapoints for OK -> ALARM transition).",
        "StateChangeTime": "2020-10-09T21:32:10.617+0000",
        "Region": "US East (N. Virginia)",
        "AlarmArn": "arn:aws:cloudwatch:us-east-1:052730242331:alarm:Traffic",
        "OldStateValue": "OK",
        "Trigger": {
            "MetricName": "RequestCount",
            "Namespace": "AWS/ApplicationELB",
            "StatisticType": "Statistic",
            "Statistic": "SUM",
            "Unit": None,
            "Dimensions": [
                {
                    "value": "app/GccExplorerApp/4a4513393260c7c5",
                    "name": "LoadBalancer"
                }
            ],
            "Period": 300,
            "EvaluationPeriods": 3,
            "ComparisonOperator": "GreaterThanOrEqualToThreshold",
            "Threshold": 30,
            "TreatMissingData": "- TreatMissingData:                    missing",
            "EvaluateLowSampleCountPercentile": ""
        }
    }
    lambda_handler(dict(Records=[{'Sns': {'Message': json.dumps(event)}}]), None)
