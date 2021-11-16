# pylint: disable=redefined-outer-name
import datetime
import json
import os
from typing import Dict
from unittest import mock

import boto3
import botocore.client
import botocore.session
import pytest as pytest
from aws_embedded_metrics.logger.metrics_logger import MetricsLogger
from botocore.stub import Stubber, ANY

from stats import handle_sqs, handle_pageload, handle_compiler_stats

SOME_DATE = datetime.datetime(2020, 1, 2, 3, 4, 5, 12312)


@pytest.fixture
def sqs_client():
    return botocore.session.get_session().create_client('sqs', region_name='not-real')


@pytest.fixture
def dynamodb_client():
    return botocore.session.get_session().create_client('dynamodb', region_name='not-real')


@pytest.fixture
def s3_client():
    return botocore.session.get_session().create_client('s3', region_name='not-real')


def make_expected_body(msg_type: str, value: str):
    return f'{{"date": "2020-01-02", "time": "03:04:05", "type": "{msg_type}", "value": "{value}"}}'


@mock.patch.dict(os.environ, dict(S3_BUCKET_NAME="not-a-real-bucket"))
def test_should_store_results_from_sqs_correctly(s3_client):
    context = mock.Mock(function_name="some_func")
    event = dict(Records=[dict(body="first"), dict(body="second")])

    with Stubber(s3_client) as stubber:
        stubber.add_response(
            'put_object',
            {},
            dict(
                Body='first\nsecond',
                Bucket='not-a-real-bucket',
                Key='stats/some_func-2020-01-02-03:04:05.012312.log'
            )
        )
        handle_sqs(event, context, s3_client, SOME_DATE)


def test_pageloads_should_return_a_200_doc():
    metrics = mock.Mock(spec_set=MetricsLogger)
    queue_url = 'some-queue-url'
    result = handle_pageload(dict(queryStringParameters={}), metrics, SOME_DATE, queue_url, mock.Mock())
    assert result['statusCode'] == 200
    assert result['body'] == 'Ok'
    metrics.put_metric.assert_called_once_with('PageLoad', 1)


def test_should_handle_pageloads_with_no_sponsors(sqs_client):
    metrics = mock.Mock(spec_set=MetricsLogger)
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


def test_should_handle_pageloads_with_empty_sponsors(sqs_client):
    metrics = mock.Mock(spec_set=MetricsLogger)
    queue_url = 'some-queue-url'
    with Stubber(sqs_client) as stubber:
        stubber.add_response(
            'send_message',
            {},
            dict(QueueUrl=queue_url, MessageBody=make_expected_body('PageLoad', ''))
        )
        handle_pageload(dict(queryStringParameters=dict(icons='')), metrics, SOME_DATE, queue_url, sqs_client)
    metrics.set_property.assert_called_once_with('sponsors', [])


def test_should_handle_pageloads_with_one_sponsor(sqs_client):
    metrics = mock.Mock(spec_set=MetricsLogger)
    queue_url = 'some-queue-url'
    with Stubber(sqs_client) as stubber:
        stubber.add_response('send_message', {}, dict(QueueUrl=queue_url, MessageBody=ANY))
        stubber.add_response(
            'send_message',
            {},
            dict(QueueUrl=queue_url, MessageBody=make_expected_body('SponsorView', 'bob'))
        )
        handle_pageload(dict(queryStringParameters=dict(icons='bob')), metrics, SOME_DATE, queue_url, sqs_client)
    metrics.set_property.assert_called_once_with('sponsors', ['bob'])


def test_should_handle_pageloads_with_many_sponsors(sqs_client):
    metrics = mock.Mock(spec_set=MetricsLogger)
    queue_url = 'some-queue-url'
    with Stubber(sqs_client) as stubber:
        stubber.add_response('send_message', {}, dict(QueueUrl=queue_url, MessageBody=ANY))
        for expectation in ('bob', 'alice', 'crystal'):
            stubber.add_response(
                'send_message',
                {},
                dict(QueueUrl=queue_url, MessageBody=make_expected_body('SponsorView', expectation)))
        handle_pageload(
            dict(queryStringParameters=dict(icons='bob,alice,crystal')),
            metrics,
            SOME_DATE,
            queue_url,
            sqs_client)
    metrics.set_property.assert_called_once_with('sponsors', ['bob', 'alice', 'crystal'])


def test_should_handle_pageloads_with_many_sponsors_uri_encoded(sqs_client):
    metrics = mock.Mock(spec_set=MetricsLogger)
    queue_url = 'some-queue-url'
    with Stubber(sqs_client) as stubber:
        stubber.add_response('send_message', {}, dict(QueueUrl=queue_url, MessageBody=ANY))
        for expectation in ('bob', 'alice', 'crystal'):
            stubber.add_response(
                'send_message',
                {},
                dict(QueueUrl=queue_url, MessageBody=make_expected_body('SponsorView', expectation)))
        handle_pageload(
            dict(queryStringParameters=dict(icons='bob%2Calice%2Ccrystal')),
            metrics,
            SOME_DATE,
            queue_url,
            sqs_client)
    metrics.set_property.assert_called_once_with('sponsors', ['bob', 'alice', 'crystal'])


@pytest.mark.skip("run manually with creds")
def test_should_find_stats_on_a_compiler():
    res = handle_compiler_stats("gcc", "compiler-builds", boto3.client('dynamodb'))
    print(res)


def test_should_query_compilers_with_the_right_query(dynamodb_client):
    with Stubber(dynamodb_client) as stubber:
        stubber.add_response(
            'query',
            dict(Count=0, Items=[]),
            dict(
                TableName="compiler-table",
                Limit=100,
                ScanIndexForward=False,
                KeyConditionExpression='#key = :compiler',
                FilterExpression='#status = :status_filter',
                ExpressionAttributeNames={"#key": "compiler", "#status": "status"},
                ExpressionAttributeValues={":status_filter": dict(S="OK"), ":compiler": dict(S="some-compiler")}
            )
        )
        stubber.add_response(
            'query',
            dict(Count=0, Items=[]),
            dict(
                TableName="compiler-table",
                Limit=100,
                ScanIndexForward=False,
                KeyConditionExpression='#key = :compiler',
                ExpressionAttributeNames={"#key": "compiler"},
                ExpressionAttributeValues={":compiler": dict(S="some-compiler")}
            )
        )
        handle_compiler_stats("some-compiler", "compiler-table", dynamodb_client)


def test_should_mention_most_recent_compiler_build(dynamodb_client):
    def make_fake_item(run_id: str) -> Dict:
        return dict(
            path=dict(S="path"),
            github_run_id=dict(S=run_id),
            timestamp=dict(S="some time"),
            duration=dict(N="123"),
        )

    with Stubber(dynamodb_client) as stubber:
        stubber.add_response(
            'query', dict(Count=3, Items=[make_fake_item("first"), make_fake_item("second"), make_fake_item("third")]))
        stubber.add_response(
            'query', dict(Count=2, Items=[make_fake_item("first_b"), make_fake_item("second_b")]))
        result = handle_compiler_stats("some-compiler", "compiler-table", dynamodb_client)
    assert result['statusCode'] == 200
    assert json.loads(result['body']) == dict(
        last_success=dict(duration=123, github_run_id='first', path='path', timestamp='some time'),
        last_build=dict(duration=123, github_run_id='first_b', path='path', timestamp='some time')
    )


def test_should_handle_when_no_valid_compiler_builds(dynamodb_client):
    with Stubber(dynamodb_client) as stubber:
        stubber.add_response('query', dict(Count=0, Items=[]))
        stubber.add_response('query', dict(Count=0, Items=[]))
        result = handle_compiler_stats("some-compiler", "compiler-table", dynamodb_client)
    assert result['statusCode'] == 200
    assert json.loads(result['body']) == dict(
        last_success=None,
        last_build=None
    )
