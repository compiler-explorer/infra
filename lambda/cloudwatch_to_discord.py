import json
import requests
import os
import logging

BASE_CW_URL = 'https://console.aws.amazon.com/cloudwatch/home'
REGION = 'us-east-1'
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, _context):
    webhook_url = os.getenv("WEBHOOK_URL")
    for record in event.get('Records', []):
        discord_data = parse_sns_message(json.loads(record['Sns']['Message']))

        headers = {'content-type': 'application/json'}
        logging.info(discord_data)
        response = requests.post(webhook_url, data=json.dumps(discord_data), headers=headers)

        logging.info('Discord response: %s', response.status_code)
        logging.info(response.content)


def parse_sns_message(sns_message):
    logging.info("sns message: %s", json.dumps(sns_message))
    description = ''
    title = 'CloudWatch Alert!'
    is_alarm = sns_message.get('Trigger', None)
    if is_alarm:
        parsed_message = [
            dict(name='Description', value=sns_message['AlarmDescription'], inline=False),
            dict(name='Event', value=sns_message['NewStateReason'], inline=False)
        ]
        alarm_name = sns_message["AlarmName"]
        url = f'{BASE_CW_URL}?region={REGION}#alarmsV2:alarm/{alarm_name}?'
        description = f"A [cloudwatch alarm]({url}) has posted to the SNS notification channel"
        title = f'CloudWatch Alert - {alarm_name}!'
    else:
        logging.error("Unparsed message: %s", sns_message)
        parsed_message = [
            dict(name='Something non-parseable happened...check the logs',
                 value=json.dumps(sns_message)[:100] + '...')]
    discord_data = dict(username='AWS',
                        avatar_url='https://a0.awsstatic.com/libra-css/images/logos/aws_logo_smile_1200x630.png',
                        embeds=[dict(color=0xee3333, title=title,
                                     description=description,
                                     fields=parsed_message)])
    return discord_data

# if __name__ == "__main__":
#     # Use this to test; set your env var to the webhook endpoint to try.
#     msg = {}  # copy paste from tests maybe?
#     lambda_handler(dict(Records=[{'Sns': {'Message': json.dumps(msg)}}]), None)
