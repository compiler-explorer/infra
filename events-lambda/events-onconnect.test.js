import {test} from 'node:test';
import assert from 'node:assert/strict';
import {DynamoDBClient} from '@aws-sdk/client-dynamodb';
import {handler} from './events-onconnect.js';

test('records the connection and returns 200', async t => {
    const calls = [];
    t.mock.method(DynamoDBClient.prototype, 'send', async cmd => {
        calls.push(cmd);
        return {};
    });
    const res = await handler({requestContext: {connectionId: 'conn-ok'}});
    assert.equal(res.statusCode, 200);
    assert.equal(calls.length, 1);
});

test('returns 500 when dynamo write fails', async t => {
    t.mock.method(DynamoDBClient.prototype, 'send', async () => {
        throw new Error('boom');
    });
    const res = await handler({requestContext: {connectionId: 'conn-fail'}});
    assert.equal(res.statusCode, 500);
});
