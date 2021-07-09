import datetime
import os
from unittest import mock

import botocore.session
from aws_embedded_metrics.logger.metrics_logger import MetricsLogger
from botocore.stub import Stubber, ANY

from stats import handle_sqs, handle_pageload

SOME_DATE = datetime.datetime(2020, 1, 2, 3, 4, 5, 12312)


def make_expected_body(msg_type: str, value: str):
    return f'{{"date": "2020-01-02", "time": "03:04:05.012312", "type": "{msg_type}", "value": "{value}"}}'


@mock.patch.dict(os.environ, dict(S3_BUCKET_NAME="not-a-real-bucket"))
def test_should_store_results_from_sqs_correctly():
    context = mock.Mock(function_name="some_func")
    event = dict(Records=[dict(body="first"), dict(body="second")])
    s3 = botocore.session.get_session().create_client('s3')

    with Stubber(s3) as stubber:
        stubber.add_response(
            'put_object',
            {},
            dict(
                Body='first\nsecond',
                Bucket='not-a-real-bucket',
                Key='stats/some_func-2020-01-02-03:04:05.012312.log'
            )
        )
        handle_sqs(event, context, s3, SOME_DATE)


def test_pageloads_should_return_a_200_doc():
    metrics = mock.Mock(spec_set=MetricsLogger)
    queue_url = 'some-queue-url'
    result = handle_pageload(dict(queryStringParameters={}), metrics, SOME_DATE, queue_url, mock.Mock())
    assert result['statusCode'] == 200
    assert result['body'] == 'Ok'
    metrics.put_metric.assert_called_once_with('PageLoad', 1)


def test_should_handle_pageloads_with_no_sponsors():
    metrics = mock.Mock(spec_set=MetricsLogger)
    sqs_client = botocore.session.get_session().create_client('sqs')
    queue_url = 'some-queue-url'
    with Stubber(sqs_client) as stubber:
        stubber.add_response(
            'send_message',
            {},
            dict(
                QueueUrl=queue_url,
                MessageBody=make_expected_body('PageLoad', '')
            )
        )
        handle_pageload(dict(queryStringParameters={}), metrics, SOME_DATE, queue_url, sqs_client)
    metrics.set_property.assert_called_once_with('sponsors', [])
    metrics.put_metric.assert_called_once_with('PageLoad', 1)


def test_should_handle_pageloads_with_empty_sponsors():
    metrics = mock.Mock(spec_set=MetricsLogger)
    sqs_client = botocore.session.get_session().create_client('sqs')
    queue_url = 'some-queue-url'
    with Stubber(sqs_client) as stubber:
        stubber.add_response(
            'send_message',
            {},
            dict(QueueUrl=queue_url, MessageBody=make_expected_body('PageLoad', ''))
        )
        handle_pageload(dict(queryStringParameters=dict(sponsors='')), metrics, SOME_DATE, queue_url, sqs_client)
    metrics.set_property.assert_called_once_with('sponsors', [])


def test_should_handle_pageloads_with_one_sponsor():
    metrics = mock.Mock(spec_set=MetricsLogger)
    sqs_client = botocore.session.get_session().create_client('sqs')
    queue_url = 'some-queue-url'
    with Stubber(sqs_client) as stubber:
        stubber.add_response('send_message', {}, dict(QueueUrl=queue_url, MessageBody=ANY))
        stubber.add_response(
            'send_message',
            {},
            dict(QueueUrl=queue_url, MessageBody=make_expected_body('SponsorView', 'bob'))
        )
        handle_pageload(dict(queryStringParameters=dict(sponsors='bob')), metrics, SOME_DATE, queue_url, sqs_client)
    metrics.set_property.assert_called_once_with('sponsors', ['bob'])


def test_should_handle_pageloads_with_many_sponsors():
    metrics = mock.Mock(spec_set=MetricsLogger)
    sqs_client = botocore.session.get_session().create_client('sqs')
    queue_url = 'some-queue-url'
    with Stubber(sqs_client) as stubber:
        stubber.add_response('send_message', {}, dict(QueueUrl=queue_url, MessageBody=ANY))
        for expectation in ('bob', 'alice', 'crystal'):
            stubber.add_response(
                'send_message',
                {},
                dict(QueueUrl=queue_url, MessageBody=make_expected_body('SponsorView', expectation)))
        handle_pageload(
            dict(queryStringParameters=dict(sponsors='bob,alice,crystal')),
            metrics,
            SOME_DATE,
            queue_url,
            sqs_client)
    metrics.set_property.assert_called_once_with('sponsors', ['bob', 'alice', 'crystal'])
